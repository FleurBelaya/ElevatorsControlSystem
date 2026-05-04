# 4.3.1 Domain Event: типизированные доменные события.
# Содержат минимум данных, нужный воркеру для обновления read-модели.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class DomainEvent:
    # 4.3.1 Domain Event: базовый класс события.
    event_type: str
    aggregate_type: str
    aggregate_id: int
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# 4.3.1 Domain Event #1: создан новый лифт.
@dataclass(slots=True)
class LiftCreated(DomainEvent):
    pass


@dataclass(slots=True)
class LiftUpdated(DomainEvent):
    pass


@dataclass(slots=True)
class LiftDeleted(DomainEvent):
    pass


# 4.3.1 Domain Event #2: создана заявка на обслуживание.
@dataclass(slots=True)
class ServiceRequestCreated(DomainEvent):
    pass


@dataclass(slots=True)
class ServiceRequestUpdated(DomainEvent):
    pass


@dataclass(slots=True)
class ServiceRequestDeleted(DomainEvent):
    pass


# Дополнительные события для полноценной CQRS-синхронизации.
@dataclass(slots=True)
class SensorChanged(DomainEvent):
    pass


@dataclass(slots=True)
class SensorDeleted(DomainEvent):
    pass


@dataclass(slots=True)
class EventLogged(DomainEvent):
    pass


@dataclass(slots=True)
class TechnicianChanged(DomainEvent):
    pass


@dataclass(slots=True)
class TechnicianDeleted(DomainEvent):
    pass


@dataclass(slots=True)
class ReportCreated(DomainEvent):
    pass


@dataclass(slots=True)
class ReportDeleted(DomainEvent):
    pass


def make_lift_created(lift_id: int) -> LiftCreated:
    # 4.3.1 Domain Event #1
    return LiftCreated(event_type="LiftCreated", aggregate_type="lift", aggregate_id=lift_id)


def make_lift_updated(lift_id: int) -> LiftUpdated:
    return LiftUpdated(event_type="LiftUpdated", aggregate_type="lift", aggregate_id=lift_id)


def make_lift_deleted(lift_id: int) -> LiftDeleted:
    return LiftDeleted(event_type="LiftDeleted", aggregate_type="lift", aggregate_id=lift_id)


def make_service_request_created(request_id: int) -> ServiceRequestCreated:
    # 4.3.1 Domain Event #2
    return ServiceRequestCreated(
        event_type="ServiceRequestCreated", aggregate_type="service_request", aggregate_id=request_id
    )


def make_service_request_updated(request_id: int) -> ServiceRequestUpdated:
    return ServiceRequestUpdated(
        event_type="ServiceRequestUpdated", aggregate_type="service_request", aggregate_id=request_id
    )


def make_service_request_deleted(request_id: int) -> ServiceRequestDeleted:
    return ServiceRequestDeleted(
        event_type="ServiceRequestDeleted", aggregate_type="service_request", aggregate_id=request_id
    )


def make_sensor_changed(sensor_id: int) -> SensorChanged:
    return SensorChanged(event_type="SensorChanged", aggregate_type="sensor", aggregate_id=sensor_id)


def make_sensor_deleted(sensor_id: int) -> SensorDeleted:
    return SensorDeleted(event_type="SensorDeleted", aggregate_type="sensor", aggregate_id=sensor_id)


def make_event_logged(event_id: int) -> EventLogged:
    return EventLogged(event_type="EventLogged", aggregate_type="event", aggregate_id=event_id)


def make_technician_changed(tech_id: int) -> TechnicianChanged:
    return TechnicianChanged(
        event_type="TechnicianChanged", aggregate_type="technician", aggregate_id=tech_id
    )


def make_technician_deleted(tech_id: int) -> TechnicianDeleted:
    return TechnicianDeleted(
        event_type="TechnicianDeleted", aggregate_type="technician", aggregate_id=tech_id
    )


def make_report_created(report_id: int) -> ReportCreated:
    return ReportCreated(event_type="ReportCreated", aggregate_type="report", aggregate_id=report_id)


def make_report_deleted(report_id: int) -> ReportDeleted:
    return ReportDeleted(event_type="ReportDeleted", aggregate_type="report", aggregate_id=report_id)
