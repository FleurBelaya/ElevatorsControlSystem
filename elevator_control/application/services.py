# 2.4 - Логгирование: добавлен логгер для слоя Application Services
import logging

from elevator_control.application.auth import AuthorizationService
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

logger = logging.getLogger(__name__)


def _not_found(msg: str) -> NotFoundError:
    # 2.2 Ownership
    return NotFoundError(msg)


class LiftApplicationService:
    def __init__(
        self,
        authz: AuthorizationService,
        lifts: r.LiftRepository,
        sensors: r.SensorRepository,
    ) -> None:
        self._authz = authz
        self._lifts = lifts
        self._sensors = sensors

    async def _owner_filter(self, actor: domain_auth.User) -> int | None:
        return None if await self._authz.can_bypass_ownership(actor.id) else actor.id

    async def get(self, actor: domain_auth.User, lift_id: int) -> e.Lift:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "lifts:read")
        # 2.4 - Логгирование: запрос конкретного лифта
        logger.info("Пользователь id=%s запрашивает лифт id=%s", actor.id, lift_id)
        lift = await self._lifts.get_by_id(lift_id)
        if lift is None:
            logger.warning("Лифт id=%s не найден", lift_id)
            raise _not_found("Лифт не найден")
        if (await self._owner_filter(actor)) is not None and lift.owner_id != actor.id:
            logger.warning("Доступ запрещён: лифт id=%s не принадлежит пользователю id=%s", lift_id, actor.id)
            raise _not_found("Лифт не найден")
        return lift

    async def list_page(self, actor: domain_auth.User, skip: int, limit: int) -> tuple[list[e.Lift], int]:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "lifts:read")
        # 2.4 - Логгирование: список лифтов
        logger.info("Пользователь id=%s запрашивает список лифтов (skip=%s, limit=%s)", actor.id, skip, limit)
        return await self._lifts.list_paginated(await self._owner_filter(actor), skip, limit)

    async def create(self, actor: domain_auth.User, lift: e.Lift) -> e.Lift:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "lifts:create")
        # 2.4 - Логгирование: создание лифта
        logger.info("Пользователь id=%s создаёт лифт model=%s", actor.id, lift.model)
        return await self._lifts.create(
            e.Lift(
                id=None,
                owner_id=actor.id,
                model=lift.model,
                status=lift.status,
                location=lift.location,
                is_emergency=lift.is_emergency,
            )
        )

    async def update(self, actor: domain_auth.User, lift_id: int, **fields) -> e.Lift:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "lifts:update")
        # 2.4 - Логгирование: обновление лифта
        logger.info("Пользователь id=%s обновляет лифт id=%s, поля=%s", actor.id, lift_id, list(fields.keys()))
        current = await self.get(actor, lift_id)
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
        return result

    async def delete(self, actor: domain_auth.User, lift_id: int) -> None:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "lifts:delete")
        # 2.4 - Логгирование: удаление лифта
        logger.info("Пользователь id=%s удаляет лифт id=%s", actor.id, lift_id)
        _ = await self.get(actor, lift_id)
        if not await self._lifts.delete(lift_id):
            raise _not_found("Лифт не найден")

    async def restore_operational_state(
        self,
        actor: domain_auth.User,
        lift_id: int,
        *,
        target_status: LiftStatus = LiftStatus.ACTIVE,
        reset_sensors: bool = True,
    ) -> tuple[e.Lift, list[e.Sensor]]:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "lifts:restore_state")
        # 2.4 - Логгирование: восстановление состояния лифта
        logger.info("Пользователь id=%s восстанавливает лифт id=%s, статус=%s", actor.id, lift_id, target_status.value)
        current = await self.get(actor, lift_id)
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
        all_sensors = await self._sensors.list_by_lift(lift_id)
        if (await self._owner_filter(actor)) is not None:
            all_sensors = [s for s in all_sensors if s.owner_id == actor.id]
        return restored_lift, all_sensors


class SensorApplicationService:
    def __init__(self, authz: AuthorizationService, lifts: r.LiftRepository, sensors: r.SensorRepository) -> None:
        self._authz = authz
        self._lifts = lifts
        self._sensors = sensors

    async def _can_bypass(self, actor: domain_auth.User) -> bool:
        return await self._authz.can_bypass_ownership(actor.id)

    async def _ensure_lift_access(self, actor: domain_auth.User, lift_id: int) -> e.Lift:
        lift = await self._lifts.get_by_id(lift_id)
        if lift is None:
            raise _not_found("Лифт не найден")
        if not await self._can_bypass(actor) and lift.owner_id != actor.id:
            raise _not_found("Лифт не найден")
        return lift

    async def list_for_lift(self, actor: domain_auth.User, lift_id: int) -> list[e.Sensor]:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "sensors:read")
        await self._ensure_lift_access(actor, lift_id)
        items = await self._sensors.list_by_lift(lift_id)
        if not await self._can_bypass(actor):
            items = [x for x in items if x.owner_id == actor.id]
        return items

    async def get(self, actor: domain_auth.User, sensor_id: int) -> e.Sensor:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "sensors:read")
        s = await self._sensors.get_by_id(sensor_id)
        if s is None:
            raise _not_found("Датчик не найден")
        if not await self._can_bypass(actor) and s.owner_id != actor.id:
            raise _not_found("Датчик не найден")
        return s

    async def create(self, actor: domain_auth.User, sensor: e.Sensor) -> e.Sensor:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "sensors:create")
        lift = await self._ensure_lift_access(actor, sensor.lift_id)
        return await self._sensors.create(
            e.Sensor(
                id=None,
                owner_id=lift.owner_id,
                lift_id=sensor.lift_id,
                sensor_type=sensor.sensor_type,
                current_value=sensor.current_value,
                threshold_norm=sensor.threshold_norm,
            )
        )

    async def update(self, actor: domain_auth.User, sensor_id: int, **fields) -> e.Sensor:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "sensors:update")
        current = await self.get(actor, sensor_id)
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
        return result

    async def delete(self, actor: domain_auth.User, sensor_id: int) -> None:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "sensors:delete")
        _ = await self.get(actor, sensor_id)
        if not await self._sensors.delete(sensor_id):
            raise _not_found("Датчик не найден")


class EventApplicationService:
    def __init__(
        self,
        lifts: r.LiftRepository,
        events: r.EventRepository,
    ) -> None:
        self._lifts = lifts
        self._events = events

    async def get(self, event_id: int) -> e.Event:
        ev = await self._events.get_by_id(event_id)
        if ev is None:
            raise NotFoundError("Событие не найдено")
        return ev

    async def list_page(
        self,
        skip: int,
        limit: int,
        lift_id: int | None,
        status: EventStatus | None,
        event_type: EventType | None,
    ) -> tuple[list[e.Event], int]:
        return await self._events.list_filtered(skip, limit, lift_id, status, event_type)

    async def create(self, event: e.Event) -> e.Event:
        if await self._lifts.get_by_id(event.lift_id) is None:
            raise NotFoundError("Лифт не найден")
        return await self._events.create(event)

    async def update(self, event_id: int, **fields) -> e.Event:
        current = await self._events.get_by_id(event_id)
        if current is None:
            raise NotFoundError("Событие не найдено")
        updated = e.Event(
            id=current.id,
            lift_id=current.lift_id,
            event_type=fields.get("event_type", current.event_type),
            description=fields.get("description", current.description),
            status=fields.get("status", current.status),
        )
        result = await self._events.update(updated)
        assert result is not None
        return result


class ServiceRequestApplicationService:
    def __init__(
        self,
        lifts: r.LiftRepository,
        technicians: r.TechnicianRepository,
        requests: r.ServiceRequestRepository,
    ) -> None:
        self._lifts = lifts
        self._technicians = technicians
        self._requests = requests

    async def get(self, rid: int) -> e.ServiceRequest:
        req = await self._requests.get_by_id(rid)
        if req is None:
            raise NotFoundError("Заявка не найдена")
        return req

    async def list_page(
        self,
        skip: int,
        limit: int,
        lift_id: int | None,
        status: ServiceRequestStatus | None,
    ) -> tuple[list[e.ServiceRequest], int]:
        return await self._requests.list_filtered(skip, limit, lift_id, status)

    async def create(self, req: e.ServiceRequest) -> e.ServiceRequest:
        if await self._lifts.get_by_id(req.lift_id) is None:
            raise NotFoundError("Лифт не найден")
        if req.technician_id is not None and await self._technicians.get_by_id(req.technician_id) is None:
            raise NotFoundError("Техник не найден")
        status = req.status
        if req.technician_id is not None and status == ServiceRequestStatus.PENDING:
            status = ServiceRequestStatus.ASSIGNED
        to_save = e.ServiceRequest(
            id=req.id,
            lift_id=req.lift_id,
            reason=req.reason,
            status=status,
            technician_id=req.technician_id,
        )
        created = await self._requests.create(to_save)
        if req.technician_id is not None:
            tech = await self._technicians.get_by_id(req.technician_id)
            if tech is not None:
                await self._technicians.update(
                    e.Technician(id=tech.id, name=tech.name, status=TechnicianStatus.BUSY)
                )
        return created

    async def update(self, rid: int, **fields) -> e.ServiceRequest:
        current = await self._requests.get_by_id(rid)
        if current is None:
            raise NotFoundError("Заявка не найдена")
        new_tech_id = fields.get("technician_id", current.technician_id)
        new_status = fields.get("status", current.status)
        if (
            new_tech_id is not None
            and current.technician_id is None
            and new_status == ServiceRequestStatus.PENDING
        ):
            new_status = ServiceRequestStatus.ASSIGNED
        if new_tech_id is not None and await self._technicians.get_by_id(new_tech_id) is None:
            raise NotFoundError("Техник не найден")
        old_tech_id = current.technician_id
        updated = e.ServiceRequest(
            id=current.id,
            lift_id=current.lift_id,
            reason=fields.get("reason", current.reason),
            status=new_status,
            technician_id=new_tech_id,
        )
        result = await self._requests.update(updated)
        assert result is not None
        await self._sync_technician_status(old_tech_id, new_tech_id, current.status, new_status)
        return result

    async def _sync_technician_status(
        self,
        old_tid: int | None,
        new_tid: int | None,
        old_status: ServiceRequestStatus,
        new_status: ServiceRequestStatus,
    ) -> None:
        assigned_states = {
            ServiceRequestStatus.ASSIGNED,
            ServiceRequestStatus.IN_PROGRESS,
        }
        terminal = {ServiceRequestStatus.COMPLETED, ServiceRequestStatus.CANCELLED}

        if old_tid is not None and old_tid != new_tid:
            t = await self._technicians.get_by_id(old_tid)
            if t is not None and old_status in assigned_states:
                await self._technicians.update(
                    e.Technician(id=t.id, name=t.name, status=TechnicianStatus.FREE)
                )

        if new_tid is not None and new_status in assigned_states:
            t = await self._technicians.get_by_id(new_tid)
            if t is not None:
                await self._technicians.update(
                    e.Technician(id=t.id, name=t.name, status=TechnicianStatus.BUSY)
                )
        elif new_tid is not None and new_status in terminal:
            t = await self._technicians.get_by_id(new_tid)
            if t is not None:
                await self._technicians.update(
                    e.Technician(id=t.id, name=t.name, status=TechnicianStatus.FREE)
                )

    async def delete(self, rid: int) -> None:
        if not await self._requests.delete(rid):
            raise NotFoundError("Заявка не найдена")


class TechnicianApplicationService:
    def __init__(self, authz: AuthorizationService, tech: r.TechnicianRepository) -> None:
        self._authz = authz
        self._tech = tech

    async def _owner_filter(self, actor: domain_auth.User) -> int | None:
        return None if await self._authz.can_bypass_ownership(actor.id) else actor.id

    async def get(self, actor: domain_auth.User, tid: int) -> e.Technician:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "technicians:read")
        t = await self._tech.get_by_id(tid)
        if t is None:
            raise _not_found("Техник не найден")
        if (await self._owner_filter(actor)) is not None and t.owner_id != actor.id:
            raise _not_found("Техник не найден")
        return t

    async def list_page(self, actor: domain_auth.User, skip: int, limit: int) -> tuple[list[e.Technician], int]:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "technicians:read")
        return await self._tech.list_paginated(await self._owner_filter(actor), skip, limit)

    async def create(self, actor: domain_auth.User, tech: e.Technician) -> e.Technician:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "technicians:create")
        return await self._tech.create(e.Technician(id=None, owner_id=actor.id, name=tech.name, status=tech.status))

    async def update(self, actor: domain_auth.User, tid: int, **fields) -> e.Technician:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "technicians:update")
        current = await self.get(actor, tid)
        updated = e.Technician(
            id=current.id,
            owner_id=current.owner_id,
            name=fields.get("name", current.name),
            status=fields.get("status", current.status),
        )
        result = await self._tech.update(updated)
        assert result is not None
        return result

    async def delete(self, actor: domain_auth.User, tid: int) -> None:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "technicians:delete")
        _ = await self.get(actor, tid)
        if not await self._tech.delete(tid):
            raise _not_found("Техник не найден")


class ReportApplicationService:
    def __init__(
        self,
        authz: AuthorizationService,
        requests: r.ServiceRequestRepository,
        lifts: r.LiftRepository,
        technicians: r.TechnicianRepository,
        reports: r.ReportRepository,
    ) -> None:
        self._authz = authz
        self._requests = requests
        self._lifts = lifts
        self._technicians = technicians
        self._reports = reports

    async def _owner_filter(self, actor: domain_auth.User) -> int | None:
        return None if await self._authz.can_bypass_ownership(actor.id) else actor.id

    async def get(self, actor: domain_auth.User, report_id: int) -> e.Report:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "reports:read")
        rep = await self._reports.get_by_id(report_id)
        if rep is None:
            raise _not_found("Отчёт не найден")
        if (await self._owner_filter(actor)) is not None and rep.owner_id != actor.id:
            raise _not_found("Отчёт не найден")
        return rep

    async def list_page(self, actor: domain_auth.User, skip: int, limit: int) -> tuple[list[e.Report], int]:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "reports:read")
        return await self._reports.list_paginated(await self._owner_filter(actor), skip, limit)

    async def create(self, actor: domain_auth.User, report: e.Report) -> e.Report:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "reports:create")
        # 2.4 - Логгирование: создание отчёта
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
        return created

    async def update(self, actor: domain_auth.User, report_id: int, **fields) -> e.Report:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "reports:update")
        current = await self.get(actor, report_id)
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
        return result

    async def delete(self, actor: domain_auth.User, report_id: int) -> None:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "reports:delete")
        _ = await self.get(actor, report_id)
        if not await self._reports.delete(report_id):
            raise _not_found("Отчёт не найден")


class EventApplicationService:
    def __init__(self, authz: AuthorizationService, lifts: r.LiftRepository, events: r.EventRepository) -> None:
        self._authz = authz
        self._lifts = lifts
        self._events = events

    async def _owner_filter(self, actor: domain_auth.User) -> int | None:
        return None if await self._authz.can_bypass_ownership(actor.id) else actor.id

    async def _ensure_lift_access(self, actor: domain_auth.User, lift_id: int) -> e.Lift:
        lift = await self._lifts.get_by_id(lift_id)
        if lift is None:
            raise _not_found("Лифт не найден")
        if (await self._owner_filter(actor)) is not None and lift.owner_id != actor.id:
            raise _not_found("Лифт не найден")
        return lift

    async def get(self, actor: domain_auth.User, event_id: int) -> e.Event:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "events:read")
        ev = await self._events.get_by_id(event_id)
        if ev is None:
            raise _not_found("Событие не найдено")
        if (await self._owner_filter(actor)) is not None and ev.owner_id != actor.id:
            raise _not_found("Событие не найдено")
        return ev

    async def list_page(
        self,
        actor: domain_auth.User,
        skip: int,
        limit: int,
        lift_id: int | None,
        status: EventStatus | None,
        event_type: EventType | None,
    ) -> tuple[list[e.Event], int]:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "events:read")
        if lift_id is not None:
            await self._ensure_lift_access(actor, lift_id)
        return await self._events.list_filtered(await self._owner_filter(actor), skip, limit, lift_id, status, event_type)

    async def create(self, actor: domain_auth.User, event: e.Event) -> e.Event:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "events:create")
        # 2.4 - Логгирование: создание события
        logger.info("Пользователь id=%s создаёт событие типа=%s для лифта id=%s", actor.id, event.event_type.value, event.lift_id)
        lift = await self._ensure_lift_access(actor, event.lift_id)
        return await self._events.create(
            e.Event(
                id=None,
                owner_id=lift.owner_id,
                lift_id=event.lift_id,
                event_type=event.event_type,
                description=event.description,
                status=event.status,
            )
        )

    async def update(self, actor: domain_auth.User, event_id: int, **fields) -> e.Event:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "events:update")
        # 2.4 - Логгирование: обновление события
        logger.info("Пользователь id=%s обновляет событие id=%s", actor.id, event_id)
        current = await self.get(actor, event_id)
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
        return result


class ServiceRequestApplicationService:
    def __init__(
        self,
        authz: AuthorizationService,
        lifts: r.LiftRepository,
        technicians: r.TechnicianRepository,
        requests: r.ServiceRequestRepository,
    ) -> None:
        self._authz = authz
        self._lifts = lifts
        self._technicians = technicians
        self._requests = requests

    async def _owner_filter(self, actor: domain_auth.User) -> int | None:
        return None if await self._authz.can_bypass_ownership(actor.id) else actor.id

    async def _ensure_lift_access(self, actor: domain_auth.User, lift_id: int) -> e.Lift:
        lift = await self._lifts.get_by_id(lift_id)
        if lift is None:
            raise _not_found("Лифт не найден")
        if (await self._owner_filter(actor)) is not None and lift.owner_id != actor.id:
            raise _not_found("Лифт не найден")
        return lift

    async def _ensure_technician_access(self, actor: domain_auth.User, technician_id: int) -> e.Technician:
        tech = await self._technicians.get_by_id(technician_id)
        if tech is None:
            raise _not_found("Техник не найден")
        if (await self._owner_filter(actor)) is not None and tech.owner_id != actor.id:
            raise _not_found("Техник не найден")
        return tech

    async def get(self, actor: domain_auth.User, rid: int) -> e.ServiceRequest:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "service_requests:read")
        req = await self._requests.get_by_id(rid)
        if req is None:
            raise _not_found("Заявка не найдена")
        if (await self._owner_filter(actor)) is not None and req.owner_id != actor.id:
            raise _not_found("Заявка не найдена")
        return req

    async def list_page(
        self,
        actor: domain_auth.User,
        skip: int,
        limit: int,
        lift_id: int | None,
        status: ServiceRequestStatus | None,
    ) -> tuple[list[e.ServiceRequest], int]:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "service_requests:read")
        if lift_id is not None:
            await self._ensure_lift_access(actor, lift_id)
        return await self._requests.list_filtered(await self._owner_filter(actor), skip, limit, lift_id, status)

    async def create(self, actor: domain_auth.User, req: e.ServiceRequest) -> e.ServiceRequest:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "service_requests:create")
        # 2.4 - Логгирование: создание заявки на обслуживание
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
        await self._sync_technician_status(None, created.technician_id, ServiceRequestStatus.PENDING, created.status)
        return created

    async def update(self, actor: domain_auth.User, rid: int, **fields) -> e.ServiceRequest:
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "service_requests:update")
        current = await self.get(actor, rid)
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
            current.technician_id,
            result.technician_id,
            current.status,
            result.status,
        )
        return result

    async def _sync_technician_status(
        self,
        old_tid: int | None,
        new_tid: int | None,
        old_status: ServiceRequestStatus,
        new_status: ServiceRequestStatus,
    ) -> None:
        # 2.2 Ownership
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
        # 2.1 Авторизация RBAC
        await self._authz.require(actor.id, "service_requests:delete")
        _ = await self.get(actor, rid)
        if not await self._requests.delete(rid):
            raise _not_found("Заявка не найдена")
