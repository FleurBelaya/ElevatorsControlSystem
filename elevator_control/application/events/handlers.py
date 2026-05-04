# 4.3.2 Worker handlers: Celery-задачи, обновляющие read-модель из write-модели.
# 4.4 Eventual Consistency: эти задачи выполняются после того, как команда уже
# отдала ответ клиенту — поэтому read-модель догоняет с задержкой.
# 5.2.1 Observability hot-point: воркер — один из трёх hot-points для метрик.

from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool

from elevator_control.application import read_sync
from elevator_control.application import observability
from elevator_control.application.cache import invalidate_for_aggregate
from elevator_control.infrastructure.celery_app import celery_app
from elevator_control.infrastructure.config import settings

logger = logging.getLogger(__name__)


def _make_worker_session_factory():
    # 4.3.2 Воркер запускает asyncio.run() в каждом таске — отдельный event loop.
    # Чтобы не было ошибки "Future attached to a different loop", создаём новый
    # AsyncEngine с NullPool в каждом таске (без долгого пула соединений).
    engine = create_async_engine(
        settings.database_url_async,
        poolclass=NullPool,
    )
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    return engine, factory


@celery_app.task(bind=True, name="process_domain_event")
def process_domain_event(self, log_id: int) -> dict:
    # 4.3.2 Worker: загружает событие из outbox, применяет к read-модели, помечает processed.
    # 5.2.2 Метрики: фиксируем длительность обработки и количество затронутых строк.
    t0 = time.perf_counter()
    try:
        result = asyncio.run(_process_async(log_id))
    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.exception(
            "5.2.2 metric: worker process_domain_event log_id=%s FAILED time=%.1fms err=%s",
            log_id, duration_ms, exc,
        )
        raise
    duration_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "5.2.2 metric: worker process_domain_event log_id=%s ok=%s time=%.1fms",
        log_id, result.get("ok"), duration_ms,
    )
    # 5.2.1 Горячие точки → очередь
    observability.record("worker", "process_domain_event", duration_ms, ok=bool(result.get("ok")))
    return result


async def _process_async(log_id: int) -> dict:
    # 4.3.2 Чтение события из outbox + применение к read-модели — всё в одной транзакции.
    engine, session_factory = _make_worker_session_factory()
    try:
        async with session_factory() as session:
            async with session.begin():
                row = (
                    await session.execute(
                        text(
                            "SELECT id, event_type, aggregate_type, aggregate_id, status "
                            "FROM domain_events_log WHERE id = :id"
                        ),
                        {"id": log_id},
                    )
                ).first()
                if row is None:
                    logger.warning("4.3.2 worker: event log_id=%s не найден", log_id)
                    return {"ok": False, "reason": "not_found"}
                if row[4] == "processed":
                    return {"ok": True, "reason": "already_processed"}

                event_type: str = row[1]
                aggregate_type: str = row[2]
                aggregate_id: int = int(row[3])

                await _apply_event(session, event_type, aggregate_type, aggregate_id)
                await session.execute(
                    text(
                        "UPDATE domain_events_log SET status = 'processed', processed_at = now() "
                        "WHERE id = :id"
                    ),
                    {"id": log_id},
                )

            # 5.2.3 Кэш: после применения события чистим закэшированные query-ответы.
            await invalidate_for_aggregate(aggregate_type)

            return {"ok": True, "event_type": event_type, "aggregate": f"{aggregate_type}/{aggregate_id}"}
    finally:
        await engine.dispose()


async def _apply_event(session, event_type: str, aggregate_type: str, aggregate_id: int) -> None:
    # 4.1.1 Sync layer + 4.4 Eventual Consistency:
    # переносим изменения из write-модели в read-модель через подходящий sync-метод.
    if aggregate_type == "lift":
        if event_type == "LiftDeleted":
            await read_sync.sync_lift_delete(session, aggregate_id)
        else:
            await read_sync.sync_lift(session, aggregate_id)
    elif aggregate_type == "sensor":
        if event_type == "SensorDeleted":
            await read_sync.sync_sensor_delete(session, aggregate_id)
        else:
            await read_sync.sync_sensor(session, aggregate_id)
            lift_id_row = (
                await session.execute(
                    text("SELECT lift_id FROM sensors_read WHERE id = :id"),
                    {"id": aggregate_id},
                )
            ).first()
            if lift_id_row is not None:
                await read_sync.sync_lift(session, int(lift_id_row[0]))
    elif aggregate_type == "event":
        await read_sync.sync_event(session, aggregate_id)
        lift_id_row = (
            await session.execute(
                text("SELECT lift_id FROM events_read WHERE id = :id"),
                {"id": aggregate_id},
            )
        ).first()
        if lift_id_row is not None:
            await read_sync.sync_lift(session, int(lift_id_row[0]))
    elif aggregate_type == "service_request":
        if event_type == "ServiceRequestDeleted":
            await read_sync.sync_service_request_delete(session, aggregate_id)
        else:
            await read_sync.sync_service_request(session, aggregate_id)
            sr_row = (
                await session.execute(
                    text("SELECT lift_id, technician_id FROM service_requests_read WHERE id = :id"),
                    {"id": aggregate_id},
                )
            ).first()
            if sr_row is not None:
                await read_sync.sync_lift(session, int(sr_row[0]))
                if sr_row[1] is not None:
                    await read_sync.sync_technician(session, int(sr_row[1]))
    elif aggregate_type == "technician":
        if event_type == "TechnicianDeleted":
            await read_sync.sync_technician_delete(session, aggregate_id)
        else:
            await read_sync.sync_technician(session, aggregate_id)
    elif aggregate_type == "report":
        if event_type == "ReportDeleted":
            await read_sync.sync_report_delete(session, aggregate_id)
        else:
            await read_sync.sync_report(session, aggregate_id)
    else:
        logger.warning("4.3.2 worker: неизвестный aggregate_type=%s", aggregate_type)
