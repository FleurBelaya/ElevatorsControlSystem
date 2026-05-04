from datetime import datetime
from typing import Literal

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 6.1.1 Валидация: своя проверка email без зависимости email-validator.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _validate_email(v: str) -> str:
    if not isinstance(v, str) or not _EMAIL_RE.match(v):
        raise ValueError("Некорректный email")
    return v.lower()

from elevator_control.domain.enums import (
    EventStatus,
    EventType,
    LiftStatus,
    ServiceRequestStatus,
    TechnicianStatus,
)

# 6.1.1 Валидация входных данных: ключевой принцип — все DTO имеют extra="forbid",
# что блокирует Mass Assignment (любое неизвестное поле в payload отвергается).
# 6.1.2 Mass Assignment: ни один Create/Update DTO не содержит owner_id, id или
# created_at — серверная логика заполняет эти поля сама.

_FORBID = ConfigDict(extra="forbid")


class LiftCreate(BaseModel):
    model_config = _FORBID
    model: str = Field(..., min_length=1, max_length=128)
    status: LiftStatus = LiftStatus.ACTIVE
    location: str = Field(..., min_length=1, max_length=256)
    is_emergency: bool = False


class LiftUpdate(BaseModel):
    model_config = _FORBID
    model: str | None = Field(None, min_length=1, max_length=128)
    status: LiftStatus | None = None
    location: str | None = Field(None, min_length=1, max_length=256)
    is_emergency: bool | None = None


class LiftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model: str
    status: LiftStatus
    location: str
    is_emergency: bool


class LiftRestoreStateRequest(BaseModel):
    model_config = _FORBID
    target_status: LiftStatus = Field(default=LiftStatus.ACTIVE)
    reset_sensors: bool = Field(default=True)


class SensorCreate(BaseModel):
    model_config = _FORBID
    sensor_type: str = Field(..., min_length=1, max_length=64)
    current_value: float = Field(0.0, ge=-1e6, le=1e6)
    threshold_norm: float = Field(..., ge=0, le=1e6)


class SensorUpdate(BaseModel):
    model_config = _FORBID
    sensor_type: str | None = Field(None, min_length=1, max_length=64)
    current_value: float | None = Field(None, ge=-1e6, le=1e6)
    threshold_norm: float | None = Field(None, ge=0, le=1e6)


class SensorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lift_id: int
    sensor_type: str
    current_value: float
    threshold_norm: float


class LiftRestoreStateResponse(BaseModel):
    lift: LiftRead
    sensors: list[SensorRead]


class EventCreate(BaseModel):
    model_config = _FORBID
    lift_id: int = Field(..., ge=1)
    event_type: EventType
    description: str = Field(..., min_length=1, max_length=4000)
    status: EventStatus = EventStatus.NEW


class EventUpdate(BaseModel):
    model_config = _FORBID
    event_type: EventType | None = None
    description: str | None = Field(None, min_length=1, max_length=4000)
    status: EventStatus | None = None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lift_id: int
    event_type: EventType
    description: str
    status: EventStatus


class ServiceRequestCreate(BaseModel):
    model_config = _FORBID
    lift_id: int = Field(..., ge=1)
    reason: str = Field(..., min_length=1, max_length=4000)
    status: ServiceRequestStatus = ServiceRequestStatus.PENDING
    technician_id: int | None = Field(None, ge=1)


class ServiceRequestUpdate(BaseModel):
    model_config = _FORBID
    reason: str | None = Field(None, min_length=1, max_length=4000)
    status: ServiceRequestStatus | None = None
    technician_id: int | None = Field(None, ge=1)


class ServiceRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lift_id: int
    reason: str
    status: ServiceRequestStatus
    technician_id: int | None


class TechnicianCreate(BaseModel):
    model_config = _FORBID
    name: str = Field(..., min_length=1, max_length=128)
    status: TechnicianStatus = TechnicianStatus.FREE


class TechnicianUpdate(BaseModel):
    model_config = _FORBID
    name: str | None = Field(None, min_length=1, max_length=128)
    status: TechnicianStatus | None = None


class TechnicianRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: TechnicianStatus


class ReportCreate(BaseModel):
    model_config = _FORBID
    service_request_id: int = Field(..., ge=1)
    work_description: str = Field(..., min_length=1, max_length=8000)
    final_lift_status: LiftStatus


class ReportUpdate(BaseModel):
    model_config = _FORBID
    work_description: str | None = Field(None, min_length=1, max_length=8000)
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
    model_config = _FORBID
    sensor_id: int | None = Field(default=None)
    note: str | None = Field(default=None, max_length=512)

    @field_validator("sensor_id", mode="before")
    @classmethod
    def sensor_id_zero_means_auto(cls, v: object) -> object:
        if v == 0:
            return None
        return v


class EmergencyDemoResponse(BaseModel):
    lift_id: int
    event_id: int
    service_request_id: int
    sensor_id: int
    sensor_value_after: float
    message: str


class UserRegister(BaseModel):
    # 6.1.1 Валидация: жёсткий формат email и минимальная длина пароля.
    model_config = _FORBID
    email: str = Field(..., max_length=320)
    password: str = Field(..., min_length=8, max_length=256)
    role: Literal["dispatcher", "technician", "administrator"] = "dispatcher"
    admin_code: str | None = Field(default=None, max_length=128)

    @field_validator("email")
    @classmethod
    def _email_format(cls, v: str) -> str:
        return _validate_email(v)


class UserLogin(BaseModel):
    model_config = _FORBID
    email: str = Field(..., max_length=320)
    password: str = Field(..., min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def _email_format(cls, v: str) -> str:
        return _validate_email(v)


class TokenResponse(BaseModel):
    # 6.2.1 access + 6.2.2 refresh
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    # 6.2.2 Refresh-эндпоинт принимает только refresh_token.
    model_config = _FORBID
    refresh_token: str = Field(..., min_length=10, max_length=8000)


class UserRead(BaseModel):
    id: int
    email: str
    roles: list[str] = []
