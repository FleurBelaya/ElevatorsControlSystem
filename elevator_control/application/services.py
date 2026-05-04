# 4.1.1 CQRS — Command Side: сервисы с суффиксом *CommandService отвечают
# ИСКЛЮЧИТЕЛЬНО за изменение данных (create/update/delete). Чтение делается
# отдельными QueryService в application.queries (raw SQL без ORM).
#
# 2.4 - Логгирование: добавлен логгер для слоя Application Services.
# 4.3.1/4.3.2 — после каждой write-операции публикуется Domain Event и
# ставится задача в очередь Celery для обновления read-модели.
import logging

from elevator_control.application.auth import AuthorizationService
from elevator_control.application.events import domain_events as ev
from elevator_control.application.events.publisher import publish
from elevator_control.application import cache as query_cache
from elevator_control.domain import auth as domain_auth
from elevator_control.domain import entities as e
from elevator_control.domain.enums import (
    EventStatus,
    EventType,
    LiftStatus,
    ServiceRequestStatus,
    TechnicianStatus,
)
from elevator_control.domain.exceptions import NotFoundError
from elevator_control.ports.outbound import repositories as r
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _not_found(msg: str) -> NotFoundError:
    # 2.2 Ownership
    return NotFoundError(msg)


async def _publish_and_invalidate(session: AsyncSession, *events: ev.DomainEvent) -> None:
    # 4.3.2 Event-очередь: пишем outbox + помечаем сессию для постановки задач после commit.
    # 5.2.3 Кэш: чистим закэшированные query-ответы по агрегатам, затронутым командой.
    if not events:
        return
    inserted_ids = await publish(session, list(events))
    pending = session.info.setdefault("pending_event_payloads", [])
    for event, log_id in zip(events, inserted_ids):
        pending.append(
            {
                "event_type": event.event_type,
                "aggregate_type": event.aggregate_type,
                "aggregate_id": event.aggregate_id,
                "occurred_at": event.occurred_at.isoformat(),
                "log_id": int(log_id),
            }
        )
    affected_aggregates = {event.aggregate_type for event in events}
    for aggregate in affected_aggregates:
        # 5.2.3 Кэш: предварительная инвалидация (даже если воркер не отработал).
        await query_cache.invalidate_for_aggregate(aggregate)


class LiftCommandService:
    # 4.1.1 CQRS — Command Side: write-only.
    def __init__(
        self,
        authz: AuthorizationService,
        lifts: r.LiftRepository,
        sensors: r.SensorRepository,
        session: AsyncSession,
    ) -> None:
        self._authz = authz
        self._lifts = lifts
        self._sensors = sensors
        self._session = session

    async def _owner_filter(self, actor: domain_auth.User) -> int | None:
        return None if await self._authz.can_bypass_ownership(actor.id) else actor.id

    async def _get_internal(self, actor: domain_auth.User, lift_id: int) -> e.Lift:
        # 4.1.1 Внутреннее чтение для command-логики допустимо: команда должна знать
        # текущее состояние агрегата, чтобы построить новое. Это НЕ публичный read.
        await self._authz.require(actor.id, "lifts:read")
        logger.info("Пользователь id=%s читает лифт id=%s (для command)", actor.id, lift_id)
        lift = await self._lifts.get_by_id(lift_id)
        if lift is None:
            raise _not_found("Лифт не найден")
        if (await self._owner_filter(actor)) is not None and lift.owner_id != actor.id:
            raise _not_found("Лифт не найден")
        return lift

    async def create(self, actor: domain_auth.User, lift: e.Lift) -> e.Lift:
        # 2.1 Авторизация RBAC
        # 6.1.3 Ограничение доступа: owner_id всегда берётся из токена (actor.id),
        # а не из тела запроса.
        await self._authz.require(actor.id, "lifts:create")
        logger.info("Пользователь id=%s создаёт лифт model=%s", actor.id, lift.model)
        created = await self._lifts.create(
            e.Lift(
                id=None,
                owner_id=actor.id,
                model=lift.model,
                status=lift.status,
                location=lift.location,
                is_emergency=lift.is_emergency,
            )
        )
        assert created.id is not None
        # 4.3.1 Domain Event: LiftCreated
        await _publish_and_invalidate(self._session, ev.make_lift_created(created.id))
        return created

    async def update(self, actor: domain_auth.User, lift_id: int, **fields) -> e.Lift:
        await self._authz.require(actor.id, "lifts:update")
        logger.info("Пользователь id=%s обновляет лифт id=%s, поля=%s", actor.id, lift_id, list(fields.keys()))
        current = await self._get_internal(actor, lift_id)
        updated = e.Lift(
            id=current.id,
            owner_id=current.owner_id,
            model=fields.get("model", current.model),
            status=fields.get("status", current.status),
            location=fields.get("location", current.location),
            is_emergency=fields.get("is_emergency", current.is_emergency),
        )
        result = await self._lifts.update(updated)
        assert result is not None
        await _publish_and_invalidate(self._session, ev.make_lift_updated(lift_id))
        return result

    async def delete(self, actor: domain_auth.User, lift_id: int) -> None:
        await self._authz.require(actor.id, "lifts:delete")
        logger.info("Пользователь id=%s удаляет лифт id=%s", actor.id, lift_id)
        _ = await self._get_internal(actor, lift_id)
        if not await self._lifts.delete(lift_id):
            raise _not_found("Лифт не найден")
        await _publish_and_invalidate(self._session, ev.make_lift_deleted(lift_id))

    async def restore_operational_state(
        self,
        actor: domain_auth.User,
        lift_id: int,
        *,
        target_status: LiftStatus = LiftStatus.ACTIVE,
        reset_sensors: bool = True,
    ) -> tuple[e.Lift, list[e.Sensor]]:
        await self._authz.require(actor.id, "lifts:restore_state")
        logger.info(
            "Пользователь id=%s восстанавливает лифт id=%s, статус=%s",
            actor.id, lift_id, target_status.value,
        )
        current = await self._get_internal(actor, lift_id)
        restored_lift = await self._lifts.update(
            e.Lift(
                id=current.id,
                owner_id=current.owner_id,
                model=current.model,
                status=target_status,
                location=current.location,
                is_emergency=False,
            )
        )
        assert restored_lift is not None
        events_to_publish: list[ev.DomainEvent] = [ev.make_lift_updated(lift_id)]
        if reset_sensors:
            for s in await self._sensors.list_by_lift(lift_id):
                if (await self._owner_filter(actor)) is not None and s.owner_id != actor.id:
                    continue
                assert s.id is not None
                thr = max(s.threshold_norm, 1e-9)
                safe_value = min(thr * 0.45, max(0.0, thr - 1e-6))
                await self._sensors.update(
                    e.Sensor(
                        id=s.id,
                        owner_id=s.owner_id,
                        lift_id=s.lift_id,
                        sensor_type=s.sensor_type,
                        current_value=safe_value,
                        threshold_norm=s.threshold_norm,
                    )
                )
                events_to_publish.append(ev.make_sensor_changed(s.id))
        all_sensors = await self._sensors.list_by_lift(lift_id)
        if (await self._owner_filter(actor)) is not None:
            all_sensors = [s for s in all_sensors if s.owner_id == actor.id]
        await _publish_and_invalidate(self._session, *events_to_publish)
        return restored_lift, all_sensors


class SensorCommandService:
    # 4.1.1 CQRS — Command Side
    def __init__(
        self,
        authz: AuthorizationService,
        lifts: r.LiftRepository,
        sensors: r.SensorRepository,
        session: AsyncSession,
    ) -> None:
        self._authz = authz
        self._lifts = lifts
        self._sensors = sensors
        self._session = session

    async def _can_bypass(self, actor: domain_auth.User) -> bool:
        return await self._authz.can_bypass_ownership(actor.id)

    async def _ensure_lift_access(self, actor: domain_auth.User, lift_id: int) -> e.Lift:
        lift = await self._lifts.get_by_id(lift_id)
        if lift is None:
            raise _not_found("Лифт не найден")
        if not await self._can_bypass(actor) and lift.owner_id != actor.id:
            raise _not_found("Лифт не найден")
        return lift

    async def _get_internal(self, actor: domain_auth.User, sensor_id: int) -> e.Sensor:
        await self._authz.require(actor.id, "sensors:read")
        s = await self._sensors.get_by_id(sensor_id)
        if s is None:
            raise _not_found("Датчик не найден")
        if not await self._can_bypass(actor) and s.owner_id != actor.id:
            raise _not_found("Датчик не найден")
        return s

    async def create(self, actor: domain_auth.User, sensor: e.Sensor) -> e.Sensor:
        await self._authz.require(actor.id, "sensors:create")
        # 6.1.3 owner_id берётся из лифта-владельца, не из тела запроса.
        lift = await self._ensure_lift_access(actor, sensor.lift_id)
        created = await self._sensors.create(
            e.Sensor(
                id=None,
                owner_id=lift.owner_id,
                lift_id=sensor.lift_id,
                sensor_type=sensor.sensor_type,
                current_value=sensor.current_value,
                threshold_norm=sensor.threshold_norm,
            )
        )
        assert created.id is not None
        await _publish_and_invalidate(
            self._session,
            ev.make_sensor_changed(created.id),
            ev.make_lift_updated(sensor.lift_id),
        )
        return created

    async def update(self, actor: domain_auth.User, sensor_id: int, **fields) -> e.Sensor:
        await self._authz.require(actor.id, "sensors:update")
        current = await self._get_internal(actor, sensor_id)
        updated = e.Sensor(
            id=current.id,
            owner_id=current.owner_id,
            lift_id=current.lift_id,
            sensor_type=fields.get("sensor_type", current.sensor_type),
            current_value=fields.get("current_value", current.current_value),
            threshold_norm=fields.get("threshold_norm", current.threshold_norm),
        )
        result = await self._sensors.update(updated)
        assert result is not None
        await _publish_and_invalidate(
            self._session,
            ev.make_sensor_changed(sensor_id),
            ev.make_lift_updated(current.lift_id),
        )
        return result

    async def delete(self, actor: domain_auth.User, sensor_id: int) -> None:
        await self._authz.require(actor.id, "sensors:delete")
        current = await self._get_internal(actor, sensor_id)
        if not await self._sensors.delete(sensor_id):
            raise _not_found("Датчик не найден")
        await _publish_and_invalidate(
            self._session,
            ev.make_sensor_deleted(sensor_id),
            ev.make_lift_updated(current.lift_id),
        )


class EventCommandService:
    # 4.1.1 CQRS — Command Side
    def __init__(
        self,
        authz: AuthorizationService,
        lifts: r.LiftRepository,
        events: r.EventRepository,
        session: AsyncSession,
    ) -> None:
        self._authz = authz
        self._lifts = lifts
        self._events = events
        self._session = session

    async def _owner_filter(self, actor: domain_auth.User) -> int | None:
        return None if await self._authz.can_bypass_ownership(actor.id) else actor.id

    async def _ensure_lift_access(self, actor: domain_auth.User, lift_id: int) -> e.Lift:
        lift = await self._lifts.get_by_id(lift_id)
        if lift is None:
            raise _not_found("Лифт не найден")
        if (await self._owner_filter(actor)) is not None and lift.owner_id != actor.id:
            raise _not_found("Лифт не найден")
        return lift

    async def _get_internal(self, actor: domain_auth.User, event_id: int) -> e.Event:
        await self._authz.require(actor.id, "events:read")
        ev_obj = await self._events.get_by_id(event_id)
        if ev_obj is None:
            raise _not_found("Событие не найдено")
        if (await self._owner_filter(actor)) is not None and ev_obj.owner_id != actor.id:
            raise _not_found("Событие не найдено")
        return ev_obj

    async def create(self, actor: domain_auth.User, event: e.Event) -> e.Event:
        await self._authz.require(actor.id, "events:create")
        logger.info(
            "Пользователь id=%s создаёт событие типа=%s для лифта id=%s",
            actor.id, event.event_type.value, event.lift_id,
        )
        lift = await self._ensure_lift_access(actor, event.lift_id)
        created = await self._events.create(
            e.Event(
                id=None,
                owner_id=lift.owner_id,
                lift_id=event.lift_id,
                event_type=event.event_type,
                description=event.description,
                status=event.status,
            )
        )
        assert created.id is not None
        await _publish_and_invalidate(
            self._session,
            ev.make_event_logged(created.id),
            ev.make_lift_updated(event.lift_id),
        )
        return created

    async def update(self, actor: domain_auth.User, event_id: int, **fields) -> e.Event:
        await self._authz.require(actor.id, "events:update")
        logger.info("Пользователь id=%s обновляет событие id=%s", actor.id, event_id)
        current = await self._get_internal(actor, event_id)
        updated = e.Event(
            id=current.id,
            owner_id=current.owner_id,
            lift_id=current.lift_id,
            event_type=fields.get("event_type", current.event_type),
            description=fields.get("description", current.description),
            status=fields.get("status", current.status),
        )
        result = await self._events.update(updated)
        assert result is not None
        await _publish_and_invalidate(
            self._session,
            ev.make_event_logged(event_id),
            ev.make_lift_updated(current.lift_id),
        )
        return result


class ServiceRequestCommandService:
    # 4.1.1 CQRS — Command Side
    def __init__(
        self,
        authz: AuthorizationService,
        lifts: r.LiftRepository,
        technicians: r.TechnicianRepository,
        requests: r.ServiceRequestRepository,
        session: AsyncSession,
    ) -> None:
        self._authz = authz
        self._lifts = lifts
        self._technicians = technicians
        self._requests = requests
        self._session = session

    async def _owner_filter(self, actor: domain_auth.User) -> int | None:
        return None if await self._authz.can_bypass_ownership(actor.id) else actor.id

    async def _ensure_lift_access(self, actor: domain_auth.User, lift_id: int) -> e.Lift:
        lift = await self._lifts.get_by_id(lift_id)
        if lift is None:
            raise _not_found("Лифт не найден")
        if (await self._owner_filter(actor)) is not None and lift.owner_id != actor.id:
            raise _not_found("Лифт не найден")
        return lift

    async def _ensure_technician_access(
        self, actor: domain_auth.User, technician_id: int
    ) -> e.Technician:
        tech = await self._technicians.get_by_id(technician_id)
        if tech is None:
            raise _not_found("Техник не найден")
        if (await self._owner_filter(actor)) is not None and tech.owner_id != actor.id:
            raise _not_found("Техник не найден")
        return tech

    async def _get_internal(self, actor: domain_auth.User, rid: int) -> e.ServiceRequest:
        await self._authz.require(actor.id, "service_requests:read")
        req = await self._requests.get_by_id(rid)
        if req is None:
            raise _not_found("Заявка не найдена")
        if (await self._owner_filter(actor)) is not None and req.owner_id != actor.id:
            raise _not_found("Заявка не найдена")
        return req

    async def create(self, actor: domain_auth.User, req: e.ServiceRequest) -> e.ServiceRequest:
        await self._authz.require(actor.id, "service_requests:create")
        logger.info("Пользователь id=%s создаёт заявку для лифта id=%s", actor.id, req.lift_id)
        lift = await self._ensure_lift_access(actor, req.lift_id)
        if req.technician_id is not None:
            await self._ensure_technician_access(actor, req.technician_id)
        created = await self._requests.create(
            e.ServiceRequest(
                id=None,
                owner_id=lift.owner_id,
                lift_id=req.lift_id,
                reason=req.reason,
                status=req.status,
                technician_id=req.technician_id,
            )
        )
        assert created.id is not None
        await self._sync_technician_status(
            None, created.technician_id, ServiceRequestStatus.PENDING, created.status
        )
        events_to_publish: list[ev.DomainEvent] = [
            ev.make_service_request_created(created.id),
            ev.make_lift_updated(req.lift_id),
        ]
        if created.technician_id is not None:
            events_to_publish.append(ev.make_technician_changed(created.technician_id))
        await _publish_and_invalidate(self._session, *events_to_publish)
        return created

    async def update(self, actor: domain_auth.User, rid: int, **fields) -> e.ServiceRequest:
        await self._authz.require(actor.id, "service_requests:update")
        current = await self._get_internal(actor, rid)
        new_tid = fields.get("technician_id", current.technician_id)
        if new_tid is not None:
            await self._ensure_technician_access(actor, new_tid)
        updated = e.ServiceRequest(
            id=current.id,
            owner_id=current.owner_id,
            lift_id=current.lift_id,
            reason=fields.get("reason", current.reason),
            status=fields.get("status", current.status),
            technician_id=new_tid,
        )
        result = await self._requests.update(updated)
        assert result is not None
        await self._sync_technician_status(
            current.technician_id, result.technician_id, current.status, result.status
        )
        events_to_publish: list[ev.DomainEvent] = [
            ev.make_service_request_updated(rid),
            ev.make_lift_updated(current.lift_id),
        ]
        if current.technician_id is not None:
            events_to_publish.append(ev.make_technician_changed(current.technician_id))
        if result.technician_id is not None and result.technician_id != current.technician_id:
            events_to_publish.append(ev.make_technician_changed(result.technician_id))
        await _publish_and_invalidate(self._session, *events_to_publish)
        return result

    async def _sync_technician_status(
        self,
        old_tid: int | None,
        new_tid: int | None,
        old_status: ServiceRequestStatus,
        new_status: ServiceRequestStatus,
    ) -> None:
        # 2.2 Ownership-aware sync технического статуса.
        assigned_states = {ServiceRequestStatus.ASSIGNED, ServiceRequestStatus.IN_PROGRESS}
        terminal = {ServiceRequestStatus.COMPLETED, ServiceRequestStatus.CANCELLED}

        if old_tid is not None and old_tid != new_tid and old_status in assigned_states:
            t = await self._technicians.get_by_id(old_tid)
            if t is not None:
                await self._technicians.update(
                    e.Technician(id=t.id, owner_id=t.owner_id, name=t.name, status=TechnicianStatus.FREE)
                )

        if new_tid is not None and new_status in assigned_states:
            t = await self._technicians.get_by_id(new_tid)
            if t is not None:
                await self._technicians.update(
                    e.Technician(id=t.id, owner_id=t.owner_id, name=t.name, status=TechnicianStatus.BUSY)
                )
        elif new_tid is not None and new_status in terminal:
            t = await self._technicians.get_by_id(new_tid)
            if t is not None:
                await self._technicians.update(
                    e.Technician(id=t.id, owner_id=t.owner_id, name=t.name, status=TechnicianStatus.FREE)
                )

    async def delete(self, actor: domain_auth.User, rid: int) -> None:
        await self._authz.require(actor.id, "service_requests:delete")
        current = await self._get_internal(actor, rid)
        if not await self._requests.delete(rid):
            raise _not_found("Заявка не найдена")
        events_to_publish: list[ev.DomainEvent] = [
            ev.make_service_request_deleted(rid),
            ev.make_lift_updated(current.lift_id),
        ]
        if current.technician_id is not None:
            events_to_publish.append(ev.make_technician_changed(current.technician_id))
        await _publish_and_invalidate(self._session, *events_to_publish)


class TechnicianCommandService:
    # 4.1.1 CQRS — Command Side
    def __init__(
        self,
        authz: AuthorizationService,
        tech: r.TechnicianRepository,
        session: AsyncSession,
    ) -> None:
        self._authz = authz
        self._tech = tech
        self._session = session

    async def _owner_filter(self, actor: domain_auth.User) -> int | None:
        return None if await self._authz.can_bypass_ownership(actor.id) else actor.id

    async def _get_internal(self, actor: domain_auth.User, tid: int) -> e.Technician:
        await self._authz.require(actor.id, "technicians:read")
        t = await self._tech.get_by_id(tid)
        if t is None:
            raise _not_found("Техник не найден")
        if (await self._owner_filter(actor)) is not None and t.owner_id != actor.id:
            raise _not_found("Техник не найден")
        return t

    async def create(self, actor: domain_auth.User, tech: e.Technician) -> e.Technician:
        await self._authz.require(actor.id, "technicians:create")
        # 6.1.3 owner_id из токена.
        created = await self._tech.create(
            e.Technician(id=None, owner_id=actor.id, name=tech.name, status=tech.status)
        )
        assert created.id is not None
        await _publish_and_invalidate(self._session, ev.make_technician_changed(created.id))
        return created

    async def update(self, actor: domain_auth.User, tid: int, **fields) -> e.Technician:
        await self._authz.require(actor.id, "technicians:update")
        current = await self._get_internal(actor, tid)
        updated = e.Technician(
            id=current.id,
            owner_id=current.owner_id,
            name=fields.get("name", current.name),
            status=fields.get("status", current.status),
        )
        result = await self._tech.update(updated)
        assert result is not None
        await _publish_and_invalidate(self._session, ev.make_technician_changed(tid))
        return result

    async def delete(self, actor: domain_auth.User, tid: int) -> None:
        await self._authz.require(actor.id, "technicians:delete")
        _ = await self._get_internal(actor, tid)
        if not await self._tech.delete(tid):
            raise _not_found("Техник не найден")
        await _publish_and_invalidate(self._session, ev.make_technician_deleted(tid))


class ReportCommandService:
    # 4.1.1 CQRS — Command Side
    def __init__(
        self,
        authz: AuthorizationService,
        requests: r.ServiceRequestRepository,
        lifts: r.LiftRepository,
        technicians: r.TechnicianRepository,
        reports: r.ReportRepository,
        session: AsyncSession,
    ) -> None:
        self._authz = authz
        self._requests = requests
        self._lifts = lifts
        self._technicians = technicians
        self._reports = reports
        self._session = session

    async def _owner_filter(self, actor: domain_auth.User) -> int | None:
        return None if await self._authz.can_bypass_ownership(actor.id) else actor.id

    async def _get_internal(self, actor: domain_auth.User, report_id: int) -> e.Report:
        await self._authz.require(actor.id, "reports:read")
        rep = await self._reports.get_by_id(report_id)
        if rep is None:
            raise _not_found("Отчёт не найден")
        if (await self._owner_filter(actor)) is not None and rep.owner_id != actor.id:
            raise _not_found("Отчёт не найден")
        return rep

    async def create(self, actor: domain_auth.User, report: e.Report) -> e.Report:
        await self._authz.require(actor.id, "reports:create")
        logger.info("Пользователь id=%s создаёт отчёт для заявки id=%s", actor.id, report.service_request_id)
        req = await self._requests.get_by_id(report.service_request_id)
        if req is None:
            raise _not_found("Заявка не найдена")
        if (await self._owner_filter(actor)) is not None and req.owner_id != actor.id:
            raise _not_found("Заявка не найдена")
        lift = await self._lifts.get_by_id(req.lift_id)
        if lift is None:
            raise _not_found("Лифт не найден")
        if (await self._owner_filter(actor)) is not None and lift.owner_id != actor.id:
            raise _not_found("Лифт не найден")
        created = await self._reports.create(
            e.Report(
                id=None,
                owner_id=req.owner_id,
                service_request_id=report.service_request_id,
                work_description=report.work_description,
                final_lift_status=report.final_lift_status,
                created_at=None,
            )
        )
        await self._requests.update(
            e.ServiceRequest(
                id=req.id,
                owner_id=req.owner_id,
                lift_id=req.lift_id,
                reason=req.reason,
                status=ServiceRequestStatus.COMPLETED,
                technician_id=req.technician_id,
            )
        )
        await self._lifts.update(
            e.Lift(
                id=lift.id,
                owner_id=lift.owner_id,
                model=lift.model,
                status=report.final_lift_status,
                location=lift.location,
                is_emergency=False,
            )
        )
        events_to_publish: list[ev.DomainEvent] = [
            ev.make_report_created(created.id),
            ev.make_service_request_updated(req.id),
            ev.make_lift_updated(lift.id),
        ]
        if req.technician_id is not None:
            tech = await self._technicians.get_by_id(req.technician_id)
            if tech is not None:
                await self._technicians.update(
                    e.Technician(
                        id=tech.id,
                        owner_id=tech.owner_id,
                        name=tech.name,
                        status=TechnicianStatus.FREE,
                    )
                )
                events_to_publish.append(ev.make_technician_changed(tech.id))
        await _publish_and_invalidate(self._session, *events_to_publish)
        return created

    async def update(self, actor: domain_auth.User, report_id: int, **fields) -> e.Report:
        await self._authz.require(actor.id, "reports:update")
        current = await self._get_internal(actor, report_id)
        updated = e.Report(
            id=current.id,
            owner_id=current.owner_id,
            service_request_id=current.service_request_id,
            work_description=fields.get("work_description", current.work_description),
            final_lift_status=fields.get("final_lift_status", current.final_lift_status),
            created_at=current.created_at,
        )
        result = await self._reports.update(updated)
        assert result is not None
        await _publish_and_invalidate(self._session, ev.make_report_created(report_id))
        return result

    async def delete(self, actor: domain_auth.User, report_id: int) -> None:
        await self._authz.require(actor.id, "reports:delete")
        _ = await self._get_internal(actor, report_id)
        if not await self._reports.delete(report_id):
            raise _not_found("Отчёт не найден")
        await _publish_and_invalidate(self._session, ev.make_report_deleted(report_id))


# 4.1.1 Backward-compatibility alias'ы: чтобы старый код, который использует
# *ApplicationService, продолжал работать как до CQRS-разделения. Новый код
# должен использовать *CommandService.
LiftApplicationService = LiftCommandService
SensorApplicationService = SensorCommandService
EventApplicationService = EventCommandService
ServiceRequestApplicationService = ServiceRequestCommandService
TechnicianApplicationService = TechnicianCommandService
ReportApplicationService = ReportCommandService
