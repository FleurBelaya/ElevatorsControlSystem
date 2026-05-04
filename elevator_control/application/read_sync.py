# 4.1.1 CQRS — Sync layer: код, который переносит изменения из write-модели в read-модель.
# 4.4 Eventual Consistency: эти функции вызываются ИЗ воркера очереди, поэтому
# read-модель догоняет write-модель с задержкой (а не в той же транзакции команды).
# Допустимо вызвать их и синхронно — для случаев, когда eventual consistency не нужна.

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# 4.1.2 Read Model: SQL для пересборки одной строки в каждой read-таблице.
# Если строки в write-таблице нет — удаляем из read-таблицы (handle delete).
_LIFT_UPSERT = text(
    """
    INSERT INTO lifts_read (
        id, owner_id, model, status, location, is_emergency,
        sensors_count, open_events_count, open_requests_count,
        last_event_type, last_event_at, max_sensor_ratio, synced_at
    )
    SELECT
        l.id, l.owner_id, l.model, l.status, l.location, l.is_emergency,
        COALESCE((SELECT COUNT(*) FROM sensors s WHERE s.lift_id = l.id), 0),
        COALESCE((SELECT COUNT(*) FROM events e WHERE e.lift_id = l.id AND e.status IN ('new','in_progress')), 0),
        COALESCE((SELECT COUNT(*) FROM service_requests sr WHERE sr.lift_id = l.id AND sr.status IN ('pending','assigned','in_progress')), 0),
        (SELECT e.event_type FROM events e WHERE e.lift_id = l.id ORDER BY e.id DESC LIMIT 1),
        now(),
        COALESCE((SELECT MAX(s.current_value / NULLIF(s.threshold_norm, 0)) FROM sensors s WHERE s.lift_id = l.id), 0),
        now()
    FROM lifts l
    WHERE l.id = :lift_id
    ON CONFLICT (id) DO UPDATE SET
        owner_id = EXCLUDED.owner_id,
        model = EXCLUDED.model,
        status = EXCLUDED.status,
        location = EXCLUDED.location,
        is_emergency = EXCLUDED.is_emergency,
        sensors_count = EXCLUDED.sensors_count,
        open_events_count = EXCLUDED.open_events_count,
        open_requests_count = EXCLUDED.open_requests_count,
        last_event_type = EXCLUDED.last_event_type,
        last_event_at = EXCLUDED.last_event_at,
        max_sensor_ratio = EXCLUDED.max_sensor_ratio,
        synced_at = EXCLUDED.synced_at
    """
)

_EVENT_UPSERT = text(
    """
    INSERT INTO events_read (
        id, owner_id, lift_id, lift_model, lift_location,
        event_type, description, status, created_at, synced_at
    )
    SELECT
        e.id, e.owner_id, e.lift_id, l.model, l.location,
        e.event_type, e.description, e.status, now(), now()
    FROM events e JOIN lifts l ON l.id = e.lift_id
    WHERE e.id = :event_id
    ON CONFLICT (id) DO UPDATE SET
        owner_id = EXCLUDED.owner_id,
        lift_id = EXCLUDED.lift_id,
        lift_model = EXCLUDED.lift_model,
        lift_location = EXCLUDED.lift_location,
        event_type = EXCLUDED.event_type,
        description = EXCLUDED.description,
        status = EXCLUDED.status,
        synced_at = EXCLUDED.synced_at
    """
)

_SR_UPSERT = text(
    """
    INSERT INTO service_requests_read (
        id, owner_id, lift_id, lift_model, lift_location,
        reason, status, technician_id, technician_name, created_at, synced_at
    )
    SELECT
        sr.id, sr.owner_id, sr.lift_id, l.model, l.location,
        sr.reason, sr.status, sr.technician_id, t.name, now(), now()
    FROM service_requests sr
    JOIN lifts l ON l.id = sr.lift_id
    LEFT JOIN technicians t ON t.id = sr.technician_id
    WHERE sr.id = :request_id
    ON CONFLICT (id) DO UPDATE SET
        owner_id = EXCLUDED.owner_id,
        lift_id = EXCLUDED.lift_id,
        lift_model = EXCLUDED.lift_model,
        lift_location = EXCLUDED.lift_location,
        reason = EXCLUDED.reason,
        status = EXCLUDED.status,
        technician_id = EXCLUDED.technician_id,
        technician_name = EXCLUDED.technician_name,
        synced_at = EXCLUDED.synced_at
    """
)

_TECH_UPSERT = text(
    """
    INSERT INTO technicians_read (id, owner_id, name, status, active_requests_count, synced_at)
    SELECT
        t.id, t.owner_id, t.name, t.status,
        COALESCE((SELECT COUNT(*) FROM service_requests sr WHERE sr.technician_id = t.id AND sr.status IN ('assigned','in_progress')), 0),
        now()
    FROM technicians t WHERE t.id = :tech_id
    ON CONFLICT (id) DO UPDATE SET
        owner_id = EXCLUDED.owner_id,
        name = EXCLUDED.name,
        status = EXCLUDED.status,
        active_requests_count = EXCLUDED.active_requests_count,
        synced_at = EXCLUDED.synced_at
    """
)

_REPORT_UPSERT = text(
    """
    INSERT INTO reports_read (
        id, owner_id, service_request_id, lift_id, lift_model,
        work_description, final_lift_status, created_at, synced_at
    )
    SELECT
        r.id, r.owner_id, r.service_request_id, sr.lift_id, l.model,
        r.work_description, r.final_lift_status, r.created_at, now()
    FROM reports r
    JOIN service_requests sr ON sr.id = r.service_request_id
    JOIN lifts l ON l.id = sr.lift_id
    WHERE r.id = :report_id
    ON CONFLICT (id) DO UPDATE SET
        owner_id = EXCLUDED.owner_id,
        service_request_id = EXCLUDED.service_request_id,
        lift_id = EXCLUDED.lift_id,
        lift_model = EXCLUDED.lift_model,
        work_description = EXCLUDED.work_description,
        final_lift_status = EXCLUDED.final_lift_status,
        synced_at = EXCLUDED.synced_at
    """
)

_SENSOR_UPSERT = text(
    """
    INSERT INTO sensors_read (
        id, owner_id, lift_id, lift_model, sensor_type,
        current_value, threshold_norm, ratio, zone, synced_at
    )
    SELECT
        s.id, s.owner_id, s.lift_id, l.model, s.sensor_type,
        s.current_value, s.threshold_norm,
        CASE WHEN s.threshold_norm > 0 THEN s.current_value / s.threshold_norm ELSE 0 END,
        CASE
            WHEN s.threshold_norm <= 0 THEN 'ok'
            WHEN s.current_value > s.threshold_norm * 1.2 THEN 'critical'
            WHEN s.current_value > s.threshold_norm THEN 'warning'
            ELSE 'ok'
        END,
        now()
    FROM sensors s JOIN lifts l ON l.id = s.lift_id
    WHERE s.id = :sensor_id
    ON CONFLICT (id) DO UPDATE SET
        owner_id = EXCLUDED.owner_id,
        lift_id = EXCLUDED.lift_id,
        lift_model = EXCLUDED.lift_model,
        sensor_type = EXCLUDED.sensor_type,
        current_value = EXCLUDED.current_value,
        threshold_norm = EXCLUDED.threshold_norm,
        ratio = EXCLUDED.ratio,
        zone = EXCLUDED.zone,
        synced_at = EXCLUDED.synced_at
    """
)


async def _measure(name: str, coro: Any) -> Any:
    # 5.2.2 Метрики: фиксируем длительность каждой операции синхронизации.
    t0 = time.perf_counter()
    try:
        return await coro
    finally:
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info("5.2.2 metric: read_sync %s time=%.1fms", name, duration_ms)


async def sync_lift(session: AsyncSession, lift_id: int) -> None:
    # 4.1.1 Sync layer + 4.4 Eventual Consistency
    await _measure("lift", session.execute(_LIFT_UPSERT, {"lift_id": lift_id}))


async def sync_lift_delete(session: AsyncSession, lift_id: int) -> None:
    await session.execute(text("DELETE FROM lifts_read WHERE id = :id"), {"id": lift_id})


async def sync_sensor(session: AsyncSession, sensor_id: int) -> None:
    await _measure("sensor", session.execute(_SENSOR_UPSERT, {"sensor_id": sensor_id}))


async def sync_sensor_delete(session: AsyncSession, sensor_id: int) -> None:
    await session.execute(text("DELETE FROM sensors_read WHERE id = :id"), {"id": sensor_id})


async def sync_event(session: AsyncSession, event_id: int) -> None:
    await _measure("event", session.execute(_EVENT_UPSERT, {"event_id": event_id}))


async def sync_service_request(session: AsyncSession, request_id: int) -> None:
    await _measure("service_request", session.execute(_SR_UPSERT, {"request_id": request_id}))


async def sync_service_request_delete(session: AsyncSession, request_id: int) -> None:
    await session.execute(
        text("DELETE FROM service_requests_read WHERE id = :id"), {"id": request_id}
    )


async def sync_technician(session: AsyncSession, tech_id: int) -> None:
    await _measure("technician", session.execute(_TECH_UPSERT, {"tech_id": tech_id}))


async def sync_technician_delete(session: AsyncSession, tech_id: int) -> None:
    await session.execute(text("DELETE FROM technicians_read WHERE id = :id"), {"id": tech_id})


async def sync_report(session: AsyncSession, report_id: int) -> None:
    await _measure("report", session.execute(_REPORT_UPSERT, {"report_id": report_id}))


async def sync_report_delete(session: AsyncSession, report_id: int) -> None:
    await session.execute(text("DELETE FROM reports_read WHERE id = :id"), {"id": report_id})


async def sync_lift_aggregate_for_changed_event(session: AsyncSession, lift_id: int) -> None:
    # При изменении событий/заявок/датчиков нужно пересчитать агрегаты в lifts_read.
    await sync_lift(session, lift_id)
