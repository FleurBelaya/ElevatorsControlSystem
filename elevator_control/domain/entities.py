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
    owner_id: int
    model: str
    status: LiftStatus
    location: str
    is_emergency: bool


@dataclass(slots=True)
class Sensor:
    id: int | None
    owner_id: int
    lift_id: int
    sensor_type: str
    current_value: float
    threshold_norm: float


@dataclass(slots=True)
class Event:
    id: int | None
    owner_id: int
    lift_id: int
    event_type: EventType
    description: str
    status: EventStatus


@dataclass(slots=True)
class ServiceRequest:
    id: int | None
    owner_id: int
    lift_id: int
    reason: str
    status: ServiceRequestStatus
    technician_id: int | None


@dataclass(slots=True)
class Technician:
    id: int | None
    owner_id: int
    name: str
    status: TechnicianStatus


@dataclass(slots=True)
class Report:
    id: int | None
    owner_id: int
    service_request_id: int
    work_description: str
    final_lift_status: LiftStatus
    created_at: datetime | None = None
