"""Симуляция показаний датчиков и аварийная логика (вызывается из фоновой задачи)."""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

from elevator_control.domain import entities as e
from elevator_control.domain.enums import EventStatus, EventType, LiftStatus, ServiceRequestStatus

if TYPE_CHECKING:
    from elevator_control.ports.outbound import repositories as r

logger = logging.getLogger(__name__)

# Выше порога — предупреждение; выше порога * CRITICAL_MULTIPLIER — критическое / авария
CRITICAL_MULTIPLIER = 1.2


def _classify(value: float, threshold: float) -> str | None:
    if threshold <= 0:
        threshold = 1e-6
    if value <= threshold:
        return None
    if value > threshold * CRITICAL_MULTIPLIER:
        return "critical"
    return "warning"


def run_sensor_simulation_tick(
    lifts: r.LiftRepository,
    sensors: r.SensorRepository,
    events: r.EventRepository,
    requests: r.ServiceRequestRepository,
) -> None:
    """Один цикл: небольшой случайный дрейф показаний, фиксация отклонений и аварийная реакция."""
    all_sensors = sensors.list_all()
    for sensor in all_sensors:
        lift = lifts.get_by_id(sensor.lift_id)
        if lift is None:
            continue
        if lift.status == LiftStatus.MAINTENANCE:
            continue

        base = max(sensor.threshold_norm, 1e-6)
        drift = random.uniform(-0.015, 0.015) * base
        old_value = sensor.current_value
        new_value = max(0.0, old_value + drift)

        old_zone = _classify(old_value, sensor.threshold_norm)
        new_zone = _classify(new_value, sensor.threshold_norm)

        sensors.update(
            e.Sensor(
                id=sensor.id,
                lift_id=sensor.lift_id,
                sensor_type=sensor.sensor_type,
                current_value=new_value,
                threshold_norm=sensor.threshold_norm,
            )
        )

        if new_zone is None:
            continue

        if new_zone == "critical":
            _handle_critical(lifts, events, requests, lift, sensor, new_value)
        elif new_zone == "warning" and old_zone is None:
            _handle_warning(events, lift, sensor, new_value)


def _handle_critical(
    lifts: r.LiftRepository,
    events: r.EventRepository,
    requests: r.ServiceRequestRepository,
    lift: e.Lift,
    sensor: e.Sensor,
    new_value: float,
) -> None:
    if events.has_open_critical_for_lift(lift.id):
        lifts.update(
            e.Lift(
                id=lift.id,
                model=lift.model,
                status=LiftStatus.STOPPED,
                location=lift.location,
                is_emergency=True,
            )
        )
        return

    desc = (
        f"Критическое отклонение датчика «{sensor.sensor_type}»: "
        f"значение {new_value:.3f}, порог {sensor.threshold_norm:.3f}"
    )
    events.create(
        e.Event(
            id=None,
            lift_id=lift.id,
            event_type=EventType.CRITICAL,
            description=desc,
            status=EventStatus.NEW,
        )
    )
    requests.create(
        e.ServiceRequest(
            id=None,
            lift_id=lift.id,
            reason=f"Автоматическая заявка: {desc}",
            status=ServiceRequestStatus.PENDING,
            technician_id=None,
        )
    )
    lifts.update(
        e.Lift(
            id=lift.id,
            model=lift.model,
            status=LiftStatus.STOPPED,
            location=lift.location,
            is_emergency=True,
        )
    )
    logger.warning("Аварийная остановка лифта id=%s, датчик id=%s", lift.id, sensor.id)


def _handle_warning(events: r.EventRepository, lift: e.Lift, sensor: e.Sensor, new_value: float) -> None:
    desc = (
        f"Предупреждение по датчику «{sensor.sensor_type}»: "
        f"значение {new_value:.3f}, порог {sensor.threshold_norm:.3f}"
    )
    events.create(
        e.Event(
            id=None,
            lift_id=lift.id,
            event_type=EventType.WARNING,
            description=desc,
            status=EventStatus.NEW,
        )
    )
