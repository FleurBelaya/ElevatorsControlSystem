from dataclasses import dataclass
from datetime import datetime

from elevator_control.domain.enums import (
    EventStatus,
    EventType,
    LiftStatus,
    ServiceRequestStatus,
    TechnicianStatus,
)


@dataclass(slots=True)
class Lift:
    id: int | None
    model: str
    status: LiftStatus
    location: str
    is_emergency: bool


@dataclass(slots=True)
class Sensor:
    id: int | None
    lift_id: int
    sensor_type: str
    current_value: float
    threshold_norm: float


@dataclass(slots=True)
class Event:
    id: int | None
    lift_id: int
    event_type: EventType
    description: str
    status: EventStatus


@dataclass(slots=True)
class ServiceRequest:
    id: int | None
    lift_id: int
    reason: str
    status: ServiceRequestStatus
    technician_id: int | None


@dataclass(slots=True)
class Technician:
    id: int | None
    name: str
    status: TechnicianStatus


@dataclass(slots=True)
class Report:
    id: int | None
    service_request_id: int
    work_description: str
    final_lift_status: LiftStatus
    created_at: datetime | None = None
