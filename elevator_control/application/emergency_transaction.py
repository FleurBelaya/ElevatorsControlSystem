from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from elevator_control.adapters.outbound.persistence import models as m
from elevator_control.domain.enums import EventStatus, EventType, LiftStatus, ServiceRequestStatus
from elevator_control.domain.exceptions import NotFoundError

CRITICAL_MULTIPLIER = 1.2


@dataclass(slots=True)
class EmergencyDemoResult:
    lift_id: int
    event_id: int
    service_request_id: int
    sensor_id: int
    sensor_value_after: float
    message: str


async def execute_emergency_demo_transaction(
    session: AsyncSession,
    lift_id: int,
    sensor_id: int | None = None,
    note: str | None = None,
) -> EmergencyDemoResult:
    lift = await session.get(m.LiftModel, lift_id)
    if lift is None:
        raise NotFoundError("Лифт не найден")

    sensor: m.SensorModel | None
    if sensor_id is not None:
        sensor = await session.get(m.SensorModel, sensor_id)
        if sensor is None or sensor.lift_id != lift_id:
            raise NotFoundError("Датчик не найден для данного лифта")
    else:
        sensor = (
            await session.execute(
                select(m.SensorModel)
                .where(m.SensorModel.lift_id == lift_id)
                .order_by(m.SensorModel.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if sensor is None:
            raise NotFoundError("У лифта нет датчиков")

    sensor.current_value = max(sensor.threshold_norm, 1e-6) * CRITICAL_MULTIPLIER
    lift.status = LiftStatus.STOPPED.value
    lift.is_emergency = True

    base_desc = (
        f"авария: критическое значение датчика '{sensor.sensor_type}' "
        f"{sensor.current_value:.3f} при пороге {sensor.threshold_norm:.3f}"
    )
    if note:
        base_desc = f"{base_desc}. {note}"

    event = m.EventModel(
        lift_id=lift.id,
        event_type=EventType.CRITICAL.value,
        description=base_desc,
        status=EventStatus.NEW.value,
    )
    session.add(event)

    req = m.ServiceRequestModel(
        lift_id=lift.id,
        reason=f"Автоматическая заявка: {base_desc}",
        status=ServiceRequestStatus.PENDING.value,
        technician_id=None,
    )
    session.add(req)

    await session.flush()

    return EmergencyDemoResult(
        lift_id=lift.id,
        event_id=event.id,
        service_request_id=req.id,
        sensor_id=sensor.id,
        sensor_value_after=sensor.current_value,
        message="Аварийная транзакция успешно выполнена",
    )
