"""Зависимости FastAPI (внедрение сессии БД и сервисов).

TODO: добавить Depends(get_current_user) с JWT и проверкой ролей
(диспетчер / техник / администратор) для защищённых маршрутов.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from elevator_control.application.auth import AuthApplicationService, AuthorizationService
from elevator_control.application import services as svc
from elevator_control.adapters.outbound.persistence import repositories_impl as impl
from elevator_control.infrastructure.config import settings
from elevator_control.infrastructure.database import get_session
from elevator_control.domain import auth as domain_auth

SessionDep = Annotated[AsyncSession, Depends(get_session)]


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
TokenDep = Annotated[str, Depends(oauth2_scheme)]


def get_auth_repo(session: SessionDep) -> impl.SqlAuthRepository:
    return impl.SqlAuthRepository(session)


def get_auth_service(session: SessionDep) -> AuthApplicationService:
    # 2.1 Авторизация RBAC
    return AuthApplicationService(
        get_auth_repo(session),
        jwt_secret_key=settings.jwt_secret_key,
        access_token_ttl_seconds=settings.access_token_ttl_seconds,
        registration_admin_code=settings.registration_admin_code,
    )


def get_authorization_service(session: SessionDep) -> AuthorizationService:
    # 2.1 Авторизация RBAC
    return AuthorizationService(get_auth_repo(session))


async def get_current_user(auth_svc: Annotated[AuthApplicationService, Depends(get_auth_service)], token: TokenDep) -> domain_auth.User:
    # 2.1 Авторизация RBAC
    return await auth_svc.get_user_from_token(token)


AuthSvcDep = Annotated[AuthApplicationService, Depends(get_auth_service)]
AuthorizationDep = Annotated[AuthorizationService, Depends(get_authorization_service)]
CurrentUserDep = Annotated[domain_auth.User, Depends(get_current_user)]


def get_lift_service(session: SessionDep) -> svc.LiftApplicationService:
    return svc.LiftApplicationService(
        get_authorization_service(session),
        impl.SqlLiftRepository(session),
        impl.SqlSensorRepository(session),
    )


def get_sensor_service(session: SessionDep) -> svc.SensorApplicationService:
    return svc.SensorApplicationService(
        get_authorization_service(session),
        impl.SqlLiftRepository(session),
        impl.SqlSensorRepository(session),
    )


def get_event_service(session: SessionDep) -> svc.EventApplicationService:
    return svc.EventApplicationService(
        get_authorization_service(session),
        impl.SqlLiftRepository(session),
        impl.SqlEventRepository(session),
    )


def get_service_request_service(session: SessionDep) -> svc.ServiceRequestApplicationService:
    return svc.ServiceRequestApplicationService(
        get_authorization_service(session),
        impl.SqlLiftRepository(session),
        impl.SqlTechnicianRepository(session),
        impl.SqlServiceRequestRepository(session),
    )


def get_technician_service(session: SessionDep) -> svc.TechnicianApplicationService:
    return svc.TechnicianApplicationService(
        get_authorization_service(session),
        impl.SqlTechnicianRepository(session),
    )


def get_report_service(session: SessionDep) -> svc.ReportApplicationService:
    return svc.ReportApplicationService(
        get_authorization_service(session),
        impl.SqlServiceRequestRepository(session),
        impl.SqlLiftRepository(session),
        impl.SqlTechnicianRepository(session),
        impl.SqlReportRepository(session),
    )


LiftSvcDep = Annotated[svc.LiftApplicationService, Depends(get_lift_service)]
SensorSvcDep = Annotated[svc.SensorApplicationService, Depends(get_sensor_service)]
EventSvcDep = Annotated[svc.EventApplicationService, Depends(get_event_service)]
ServiceRequestSvcDep = Annotated[svc.ServiceRequestApplicationService, Depends(get_service_request_service)]
TechnicianSvcDep = Annotated[svc.TechnicianApplicationService, Depends(get_technician_service)]
ReportSvcDep = Annotated[svc.ReportApplicationService, Depends(get_report_service)]
