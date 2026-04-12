from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from elevator_control.domain.enums import (
    EventStatus,
    EventType,
    LiftStatus,
    ServiceRequestStatus,
    TechnicianStatus,
)


class LiftCreate(BaseModel):
    model: str = Field(..., max_length=128)
    status: LiftStatus = LiftStatus.ACTIVE
    location: str = Field(..., max_length=256)
    is_emergency: bool = False


class LiftUpdate(BaseModel):
    model: str | None = None
    status: LiftStatus | None = None
    location: str | None = None
    is_emergency: bool | None = None


class LiftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model: str
    status: LiftStatus
    location: str
    is_emergency: bool


class SensorCreate(BaseModel):
    sensor_type: str = Field(..., max_length=64)
    current_value: float = 0.0
    threshold_norm: float


class SensorUpdate(BaseModel):
    sensor_type: str | None = Field(None, max_length=64)
    current_value: float | None = None
    threshold_norm: float | None = None


class SensorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lift_id: int
    sensor_type: str
    current_value: float
    threshold_norm: float


class EventCreate(BaseModel):
    lift_id: int
    event_type: EventType
    description: str
    status: EventStatus = EventStatus.NEW


class EventUpdate(BaseModel):
    event_type: EventType | None = None
    description: str | None = None
    status: EventStatus | None = None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lift_id: int
    event_type: EventType
    description: str
    status: EventStatus


class ServiceRequestCreate(BaseModel):
    lift_id: int
    reason: str
    status: ServiceRequestStatus = ServiceRequestStatus.PENDING
    technician_id: int | None = None


class ServiceRequestUpdate(BaseModel):
    reason: str | None = None
    status: ServiceRequestStatus | None = None
    technician_id: int | None = None


class ServiceRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lift_id: int
    reason: str
    status: ServiceRequestStatus
    technician_id: int | None


class TechnicianCreate(BaseModel):
    name: str = Field(..., max_length=128)
    status: TechnicianStatus = TechnicianStatus.FREE


class TechnicianUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    status: TechnicianStatus | None = None


class TechnicianRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: TechnicianStatus


class ReportCreate(BaseModel):
    service_request_id: int
    work_description: str
    final_lift_status: LiftStatus


class ReportUpdate(BaseModel):
    work_description: str | None = None
    final_lift_status: LiftStatus | None = None


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service_request_id: int
    work_description: str
    final_lift_status: LiftStatus
    created_at: datetime


class Paginated(BaseModel):
    items: list
    total: int
    skip: int
    limit: int


class EmergencyDemoRequest(BaseModel):
    """Тело POST для демонстрации атомарной аварийной транзакции."""

    sensor_id: int | None = Field(
        default=None,
        description="Если не указан — берётся первый датчик лифта по id",
    )
    note: str | None = Field(default=None, max_length=512, description="Доп. текст в описание инцидента")


class EmergencyDemoResponse(BaseModel):
    lift_id: int
    event_id: int
    service_request_id: int
    sensor_id: int
    sensor_value_after: float
    message: str
