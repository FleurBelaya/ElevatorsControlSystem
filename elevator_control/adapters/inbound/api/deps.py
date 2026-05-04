"""Зависимости FastAPI: внедрение сессии БД, asyncpg-пула и сервисов CQRS."""

from typing import Annotated

import asyncpg
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from elevator_control.adapters.outbound.persistence import repositories_impl as impl
from elevator_control.application import services as svc
from elevator_control.application.auth import AuthApplicationService, AuthorizationService
from elevator_control.application.queries.event_queries import EventQueryService
from elevator_control.application.queries.lift_queries import LiftQueryService
from elevator_control.application.queries.report_queries import ReportQueryService
from elevator_control.application.queries.sensor_queries import SensorQueryService
from elevator_control.application.queries.service_request_queries import ServiceRequestQueryService
from elevator_control.application.queries.technician_queries import TechnicianQueryService
from elevator_control.domain import auth as domain_auth
from elevator_control.infrastructure.config import settings
from elevator_control.infrastructure.database import get_session
from elevator_control.infrastructure.raw_pool import get_pool

SessionDep = Annotated[AsyncSession, Depends(get_session)]


# 4.1.3 Query без ORM: единый asyncpg pool для всех Query-сервисов.
async def get_query_pool() -> asyncpg.Pool:
    return await get_pool()


PoolDep = Annotated[asyncpg.Pool, Depends(get_query_pool)]


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
TokenDep = Annotated[str | None, Depends(oauth2_scheme)]


def get_auth_repo(session: SessionDep) -> impl.SqlAuthRepository:
    return impl.SqlAuthRepository(session)


def get_auth_service(session: SessionDep) -> AuthApplicationService:
    # 2.1 Авторизация RBAC + 6.2 JWT (TTL/refresh/logout)
    return AuthApplicationService(
        get_auth_repo(session),
        session,
        jwt_secret_key=settings.jwt_secret_key,
        access_token_ttl_seconds=settings.access_token_ttl_seconds,
        refresh_token_ttl_seconds=settings.refresh_token_ttl_seconds,
        registration_admin_code=settings.registration_admin_code,
    )


def get_authorization_service(session: SessionDep) -> AuthorizationService:
    # 2.1 Авторизация RBAC
    return AuthorizationService(get_auth_repo(session))


async def get_current_user(
    auth_svc: Annotated[AuthApplicationService, Depends(get_auth_service)],
    token: TokenDep,
) -> domain_auth.User:
    # 2.1 Авторизация RBAC
    # 6.2.3 Logout: токен может быть в blacklist — проверка идёт внутри auth_svc.
    if not token:
        from elevator_control.domain.exceptions import UnauthorizedError

        raise UnauthorizedError("Требуется авторизация")
    return await auth_svc.get_user_from_access_token(token)


AuthSvcDep = Annotated[AuthApplicationService, Depends(get_auth_service)]
AuthorizationDep = Annotated[AuthorizationService, Depends(get_authorization_service)]
CurrentUserDep = Annotated[domain_auth.User, Depends(get_current_user)]


# ----------------- 4.1.1 CQRS — Command side DI -----------------

def get_lift_command_service(session: SessionDep) -> svc.LiftCommandService:
    return svc.LiftCommandService(
        get_authorization_service(session),
        impl.SqlLiftRepository(session),
        impl.SqlSensorRepository(session),
        session,
    )


def get_sensor_command_service(session: SessionDep) -> svc.SensorCommandService:
    return svc.SensorCommandService(
        get_authorization_service(session),
        impl.SqlLiftRepository(session),
        impl.SqlSensorRepository(session),
        session,
    )


def get_event_command_service(session: SessionDep) -> svc.EventCommandService:
    return svc.EventCommandService(
        get_authorization_service(session),
        impl.SqlLiftRepository(session),
        impl.SqlEventRepository(session),
        session,
    )


def get_service_request_command_service(session: SessionDep) -> svc.ServiceRequestCommandService:
    return svc.ServiceRequestCommandService(
        get_authorization_service(session),
        impl.SqlLiftRepository(session),
        impl.SqlTechnicianRepository(session),
        impl.SqlServiceRequestRepository(session),
        session,
    )


def get_technician_command_service(session: SessionDep) -> svc.TechnicianCommandService:
    return svc.TechnicianCommandService(
        get_authorization_service(session),
        impl.SqlTechnicianRepository(session),
        session,
    )


def get_report_command_service(session: SessionDep) -> svc.ReportCommandService:
    return svc.ReportCommandService(
        get_authorization_service(session),
        impl.SqlServiceRequestRepository(session),
        impl.SqlLiftRepository(session),
        impl.SqlTechnicianRepository(session),
        impl.SqlReportRepository(session),
        session,
    )


LiftCmdDep = Annotated[svc.LiftCommandService, Depends(get_lift_command_service)]
SensorCmdDep = Annotated[svc.SensorCommandService, Depends(get_sensor_command_service)]
EventCmdDep = Annotated[svc.EventCommandService, Depends(get_event_command_service)]
ServiceRequestCmdDep = Annotated[svc.ServiceRequestCommandService, Depends(get_service_request_command_service)]
TechnicianCmdDep = Annotated[svc.TechnicianCommandService, Depends(get_technician_command_service)]
ReportCmdDep = Annotated[svc.ReportCommandService, Depends(get_report_command_service)]

# Backward-compat aliases (старый код использует эти имена)
LiftSvcDep = LiftCmdDep
SensorSvcDep = SensorCmdDep
EventSvcDep = EventCmdDep
ServiceRequestSvcDep = ServiceRequestCmdDep
TechnicianSvcDep = TechnicianCmdDep
ReportSvcDep = ReportCmdDep


# ----------------- 4.1.1 CQRS — Query side DI (raw SQL без ORM) -----------------

def get_lift_query_service(pool: PoolDep, session: SessionDep) -> LiftQueryService:
    # 4.1.3 Query без ORM: pool — asyncpg, session нужен только для AuthorizationService.
    return LiftQueryService(pool, get_authorization_service(session))


def get_sensor_query_service(pool: PoolDep, session: SessionDep) -> SensorQueryService:
    return SensorQueryService(pool, get_authorization_service(session))


def get_event_query_service(pool: PoolDep, session: SessionDep) -> EventQueryService:
    return EventQueryService(pool, get_authorization_service(session))


def get_service_request_query_service(pool: PoolDep, session: SessionDep) -> ServiceRequestQueryService:
    return ServiceRequestQueryService(pool, get_authorization_service(session))


def get_technician_query_service(pool: PoolDep, session: SessionDep) -> TechnicianQueryService:
    return TechnicianQueryService(pool, get_authorization_service(session))


def get_report_query_service(pool: PoolDep, session: SessionDep) -> ReportQueryService:
    return ReportQueryService(pool, get_authorization_service(session))


LiftQueryDep = Annotated[LiftQueryService, Depends(get_lift_query_service)]
SensorQueryDep = Annotated[SensorQueryService, Depends(get_sensor_query_service)]
EventQueryDep = Annotated[EventQueryService, Depends(get_event_query_service)]
ServiceRequestQueryDep = Annotated[ServiceRequestQueryService, Depends(get_service_request_query_service)]
TechnicianQueryDep = Annotated[TechnicianQueryService, Depends(get_technician_query_service)]
ReportQueryDep = Annotated[ReportQueryService, Depends(get_report_query_service)]
