"""Зависимости FastAPI (внедрение сессии БД и сервисов).

TODO: добавить Depends(get_current_user) с JWT и проверкой ролей
(диспетчер / техник / администратор) для защищённых маршрутов.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from elevator_control.application import services as svc
from elevator_control.adapters.outbound.persistence import repositories_impl as impl
from elevator_control.infrastructure.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_lift_service(session: SessionDep) -> svc.LiftApplicationService:
    return svc.LiftApplicationService(
        impl.SqlLiftRepository(session),
        impl.SqlSensorRepository(session),
    )


def get_sensor_service(session: SessionDep) -> svc.SensorApplicationService:
    return svc.SensorApplicationService(
        impl.SqlLiftRepository(session),
        impl.SqlSensorRepository(session),
    )


def get_event_service(session: SessionDep) -> svc.EventApplicationService:
    return svc.EventApplicationService(
        impl.SqlLiftRepository(session),
        impl.SqlEventRepository(session),
    )


def get_service_request_service(session: SessionDep) -> svc.ServiceRequestApplicationService:
    return svc.ServiceRequestApplicationService(
        impl.SqlLiftRepository(session),
        impl.SqlTechnicianRepository(session),
        impl.SqlServiceRequestRepository(session),
    )


def get_technician_service(session: SessionDep) -> svc.TechnicianApplicationService:
    return svc.TechnicianApplicationService(impl.SqlTechnicianRepository(session))


def get_report_service(session: SessionDep) -> svc.ReportApplicationService:
    return svc.ReportApplicationService(
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
