# 2.3 - Оптимизация ORM: в репозиториях используется явный eager loading
# через selectinload/joinedload для связей, которые нужны в конкретном запросе.
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from elevator_control.adapters.outbound.persistence import mappers, models as m
from elevator_control.domain import auth
from elevator_control.domain import entities as e
from elevator_control.domain.enums import EventStatus, EventType, ServiceRequestStatus
from elevator_control.domain.exceptions import NotFoundError


class SqlAuthRepository:
    # 2.1 Авторизация RBAC
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def count_users(self) -> int:
        return int((await self._s.execute(select(func.count()).select_from(m.UserModel))).scalar_one())

    async def get_user_by_id(self, user_id: int) -> auth.User | None:
        # 2.3 - eager load roles→permissions через selectinload (RBAC всегда нужен целиком)
        q = (
            select(m.UserModel)
            .options(
                selectinload(m.UserModel.roles).selectinload(m.RoleModel.permissions)
            )
            .where(m.UserModel.id == user_id)
        )
        row = (await self._s.execute(q)).scalar_one_or_none()
        if row is None:
            return None
        return auth.User(id=row.id, email=row.email, roles=[r.name for r in row.roles])

    async def get_user_credentials_by_email(self, email: str) -> auth.UserCredentials | None:
        row = (
            await self._s.execute(select(m.UserModel).where(m.UserModel.email == email))
        ).scalar_one_or_none()
        if row is None:
            return None
        return auth.UserCredentials(
            id=row.id,
            email=row.email,
            password_hash=row.password_hash,
            is_active=row.is_active,
        )

    async def create_user(self, email: str, password_hash: str) -> auth.User:
        row = m.UserModel(email=email, password_hash=password_hash, is_active=True)
        self._s.add(row)
        await self._s.flush()
        return auth.User(id=row.id, email=row.email, roles=[])

    async def assign_role_to_user(self, user_id: int, role_name: str) -> None:
        user = await self._s.get(m.UserModel, user_id)
        if user is None:
            raise NotFoundError("Пользователь не найден")
        role = (
            await self._s.execute(select(m.RoleModel).where(m.RoleModel.name == role_name))
        ).scalar_one_or_none()
        if role is None:
            raise NotFoundError("Роль не найдена")
        if role not in user.roles:
            user.roles.append(role)
        await self._s.flush()

    async def list_permission_names_for_user(self, user_id: int) -> set[str]:
        q = (
            select(m.PermissionModel.name)
            .select_from(m.PermissionModel)
            .join(m.role_permissions, m.role_permissions.c.permission_id == m.PermissionModel.id)
            .join(m.RoleModel, m.RoleModel.id == m.role_permissions.c.role_id)
            .join(m.user_roles, m.user_roles.c.role_id == m.RoleModel.id)
            .where(m.user_roles.c.user_id == user_id)
        )
        rows = (await self._s.execute(q)).scalars().all()
        return set(rows)


class SqlLiftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_id(self, lift_id: int) -> e.Lift | None:
        # 2.3 - eager load sensors при получении одного лифта (часто нужны для проверки)
        q = (
            select(m.LiftModel)
            .options(selectinload(m.LiftModel.sensors))
            .where(m.LiftModel.id == lift_id)
        )
        row = (await self._s.execute(q)).scalar_one_or_none()
        return mappers.lift_to_domain(row) if row else None

    async def list_paginated(
        self, owner_id: int | None, offset: int, limit: int
    ) -> tuple[list[e.Lift], int]:
        # 2.3 - eager load sensors через selectinload при пагинации лифтов
        base_q = select(m.LiftModel).options(selectinload(m.LiftModel.sensors))
        count_q = select(func.count()).select_from(m.LiftModel)
        if owner_id is not None:
            base_q = base_q.where(m.LiftModel.owner_id == owner_id)
            count_q = count_q.where(m.LiftModel.owner_id == owner_id)
        total = (await self._s.execute(count_q)).scalar_one()
        result = await self._s.execute(
            base_q.order_by(m.LiftModel.id).offset(offset).limit(limit)
        )
        rows = result.scalars().all()
        return [mappers.lift_to_domain(r) for r in rows], int(total)

    async def create(self, lift: e.Lift) -> e.Lift:
        row = m.LiftModel(
            owner_id=lift.owner_id,
            model=lift.model,
            status=lift.status.value,
            location=lift.location,
            is_emergency=lift.is_emergency,
        )
        self._s.add(row)
        await self._s.flush()
        return mappers.lift_to_domain(row)

    async def update(self, lift: e.Lift) -> e.Lift | None:
        row = await self._s.get(m.LiftModel, lift.id)
        if row is None:
            return None
        row.model = lift.model
        row.status = lift.status.value
        row.location = lift.location
        row.is_emergency = lift.is_emergency
        await self._s.flush()
        return mappers.lift_to_domain(row)

    async def delete(self, lift_id: int) -> bool:
        row = await self._s.get(m.LiftModel, lift_id)
        if row is None:
            return False
        self._s.delete(row)
        return True


class SqlSensorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_id(self, sensor_id: int) -> e.Sensor | None:
        row = await self._s.get(m.SensorModel, sensor_id)
        return mappers.sensor_to_domain(row) if row else None

    async def list_by_lift(self, lift_id: int) -> list[e.Sensor]:
        result = await self._s.execute(
            select(m.SensorModel).where(m.SensorModel.lift_id == lift_id).order_by(m.SensorModel.id)
        )
        rows = result.scalars().all()
        return [mappers.sensor_to_domain(r) for r in rows]

    async def list_all(self) -> list[e.Sensor]:
        result = await self._s.execute(select(m.SensorModel).order_by(m.SensorModel.id))
        rows = result.scalars().all()
        return [mappers.sensor_to_domain(r) for r in rows]

    async def create(self, sensor: e.Sensor) -> e.Sensor:
        row = m.SensorModel(
            owner_id=sensor.owner_id,
            lift_id=sensor.lift_id,
            sensor_type=sensor.sensor_type,
            current_value=sensor.current_value,
            threshold_norm=sensor.threshold_norm,
        )
        self._s.add(row)
        await self._s.flush()
        return mappers.sensor_to_domain(row)

    async def update(self, sensor: e.Sensor) -> e.Sensor | None:
        row = await self._s.get(m.SensorModel, sensor.id)
        if row is None:
            return None
        row.sensor_type = sensor.sensor_type
        row.current_value = sensor.current_value
        row.threshold_norm = sensor.threshold_norm
        await self._s.flush()
        return mappers.sensor_to_domain(row)

    async def delete(self, sensor_id: int) -> bool:
        row = await self._s.get(m.SensorModel, sensor_id)
        if row is None:
            return False
        self._s.delete(row)
        return True


class SqlEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_id(self, event_id: int) -> e.Event | None:
        row = await self._s.get(m.EventModel, event_id)
        return mappers.event_to_domain(row) if row else None

    async def list_filtered(
        self,
        owner_id: int | None,
        offset: int,
        limit: int,
        lift_id: int | None,
        status: EventStatus | None,
        event_type: EventType | None,
    ) -> tuple[list[e.Event], int]:
        filters = []
        if lift_id is not None:
            filters.append(m.EventModel.lift_id == lift_id)
        if owner_id is not None:
            filters.append(m.EventModel.owner_id == owner_id)
        if status is not None:
            filters.append(m.EventModel.status == status.value)
        if event_type is not None:
            filters.append(m.EventModel.event_type == event_type.value)
        count_q = select(func.count()).select_from(m.EventModel)
        if filters:
            count_q = count_q.where(*filters)
        total = (await self._s.execute(count_q)).scalar_one()
        q = select(m.EventModel)
        if filters:
            q = q.where(*filters)
        result = await self._s.execute(
            q.order_by(m.EventModel.id.desc()).offset(offset).limit(limit)
        )
        rows = result.scalars().all()
        return [mappers.event_to_domain(r) for r in rows], int(total)

    async def create(self, event: e.Event) -> e.Event:
        row = m.EventModel(
            owner_id=event.owner_id,
            lift_id=event.lift_id,
            event_type=event.event_type.value,
            description=event.description,
            status=event.status.value,
        )
        self._s.add(row)
        await self._s.flush()
        return mappers.event_to_domain(row)

    async def update(self, event: e.Event) -> e.Event | None:
        row = await self._s.get(m.EventModel, event.id)
        if row is None:
            return None
        row.event_type = event.event_type.value
        row.description = event.description
        row.status = event.status.value
        await self._s.flush()
        return mappers.event_to_domain(row)

    async def has_open_critical_for_lift(self, lift_id: int) -> bool:
        q = (
            select(func.count())
            .select_from(m.EventModel)
            .where(
                m.EventModel.lift_id == lift_id,
                m.EventModel.event_type == EventType.CRITICAL.value,
                m.EventModel.status.in_([EventStatus.NEW.value, EventStatus.IN_PROGRESS.value]),
            )
        )
        n = (await self._s.execute(q)).scalar_one()
        return int(n) > 0


class SqlServiceRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_id(self, request_id: int) -> e.ServiceRequest | None:
        # 2.3 - eager load technician через joinedload (связь один-к-одному)
        q = (
            select(m.ServiceRequestModel)
            .options(joinedload(m.ServiceRequestModel.technician))
            .where(m.ServiceRequestModel.id == request_id)
        )
        row = (await self._s.execute(q)).scalar_one_or_none()
        return mappers.service_request_to_domain(row) if row else None

    async def list_filtered(
        self,
        owner_id: int | None,
        offset: int,
        limit: int,
        lift_id: int | None,
        status: ServiceRequestStatus | None,
    ) -> tuple[list[e.ServiceRequest], int]:
        filters = []
        if lift_id is not None:
            filters.append(m.ServiceRequestModel.lift_id == lift_id)
        if owner_id is not None:
            filters.append(m.ServiceRequestModel.owner_id == owner_id)
        if status is not None:
            filters.append(m.ServiceRequestModel.status == status.value)
        count_q = select(func.count()).select_from(m.ServiceRequestModel)
        if filters:
            count_q = count_q.where(*filters)
        total = (await self._s.execute(count_q)).scalar_one()
        # 2.3 - eager load technician через joinedload при фильтрации заявок
        q = select(m.ServiceRequestModel).options(joinedload(m.ServiceRequestModel.technician))
        if filters:
            q = q.where(*filters)
        result = await self._s.execute(
            q.order_by(m.ServiceRequestModel.id.desc()).offset(offset).limit(limit)
        )
        rows = result.unique().scalars().all()
        return [mappers.service_request_to_domain(r) for r in rows], int(total)

    async def create(self, req: e.ServiceRequest) -> e.ServiceRequest:
        row = m.ServiceRequestModel(
            owner_id=req.owner_id,
            lift_id=req.lift_id,
            reason=req.reason,
            status=req.status.value,
            technician_id=req.technician_id,
        )
        self._s.add(row)
        await self._s.flush()
        return mappers.service_request_to_domain(row)

    async def update(self, req: e.ServiceRequest) -> e.ServiceRequest | None:
        row = await self._s.get(m.ServiceRequestModel, req.id)
        if row is None:
            return None
        row.reason = req.reason
        row.status = req.status.value
        row.technician_id = req.technician_id
        await self._s.flush()
        return mappers.service_request_to_domain(row)

    async def delete(self, request_id: int) -> bool:
        row = await self._s.get(m.ServiceRequestModel, request_id)
        if row is None:
            return False
        self._s.delete(row)
        return True


class SqlTechnicianRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_id(self, tech_id: int) -> e.Technician | None:
        row = await self._s.get(m.TechnicianModel, tech_id)
        return mappers.technician_to_domain(row) if row else None

    async def list_paginated(
        self, owner_id: int | None, offset: int, limit: int
    ) -> tuple[list[e.Technician], int]:
        base_q = select(m.TechnicianModel)
        count_q = select(func.count()).select_from(m.TechnicianModel)
        if owner_id is not None:
            base_q = base_q.where(m.TechnicianModel.owner_id == owner_id)
            count_q = count_q.where(m.TechnicianModel.owner_id == owner_id)
        total = (await self._s.execute(count_q)).scalar_one()
        result = await self._s.execute(
            base_q.order_by(m.TechnicianModel.id).offset(offset).limit(limit)
        )
        rows = result.scalars().all()
        return [mappers.technician_to_domain(r) for r in rows], int(total)

    async def create(self, tech: e.Technician) -> e.Technician:
        row = m.TechnicianModel(owner_id=tech.owner_id, name=tech.name, status=tech.status.value)
        self._s.add(row)
        await self._s.flush()
        return mappers.technician_to_domain(row)

    async def update(self, tech: e.Technician) -> e.Technician | None:
        row = await self._s.get(m.TechnicianModel, tech.id)
        if row is None:
            return None
        row.name = tech.name
        row.status = tech.status.value
        await self._s.flush()
        return mappers.technician_to_domain(row)

    async def delete(self, tech_id: int) -> bool:
        row = await self._s.get(m.TechnicianModel, tech_id)
        if row is None:
            return False
        self._s.delete(row)
        return True


class SqlReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_id(self, report_id: int) -> e.Report | None:
        row = await self._s.get(m.ReportModel, report_id)
        return mappers.report_to_domain(row) if row else None

    async def list_paginated(
        self, owner_id: int | None, offset: int, limit: int
    ) -> tuple[list[e.Report], int]:
        base_q = select(m.ReportModel)
        count_q = select(func.count()).select_from(m.ReportModel)
        if owner_id is not None:
            base_q = base_q.where(m.ReportModel.owner_id == owner_id)
            count_q = count_q.where(m.ReportModel.owner_id == owner_id)
        total = (await self._s.execute(count_q)).scalar_one()
        result = await self._s.execute(
            base_q.order_by(m.ReportModel.id.desc()).offset(offset).limit(limit)
        )
        rows = result.scalars().all()
        return [mappers.report_to_domain(r) for r in rows], int(total)

    async def create(self, report: e.Report) -> e.Report:
        row = m.ReportModel(
            owner_id=report.owner_id,
            service_request_id=report.service_request_id,
            work_description=report.work_description,
            final_lift_status=report.final_lift_status.value,
        )
        self._s.add(row)
        await self._s.flush()
        await self._s.refresh(row)
        return mappers.report_to_domain(row)

    async def update(self, report: e.Report) -> e.Report | None:
        row = await self._s.get(m.ReportModel, report.id)
        if row is None:
            return None
        row.work_description = report.work_description
        row.final_lift_status = report.final_lift_status.value
        await self._s.flush()
        return mappers.report_to_domain(row)

    async def delete(self, report_id: int) -> bool:
        row = await self._s.get(m.ReportModel, report_id)
        if row is None:
            return False
        self._s.delete(row)
        return True
