# 4.3.2 Event-очередь: публикация доменных событий.
# Поток: Command → запись в domain_events_log → постановка в Celery → Worker.
# 4.4 Eventual Consistency: после возврата команды клиенту read-модель обновляется
# асинхронно, через воркер; до момента обработки воркером её содержимое отстаёт.

from __future__ import annotations

import json
import logging
import os
from datetime import timezone
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from elevator_control.application.events.domain_events import DomainEvent

logger = logging.getLogger(__name__)


# 4.4 Eventual Consistency demo: задержка обработки события воркером в секундах.
# Включается переменной окружения CQRS_EVENT_DELAY_SECONDS=N.
# Когда N=0 — обновление практически мгновенное (но всё равно асинхронное через очередь).
# Когда N>0 — после команды read-модель отстаёт на N секунд, что хорошо иллюстрирует
# eventual consistency для проверки задания 4.4.
def _event_delay_seconds() -> int:
    try:
        return max(0, int(os.getenv("CQRS_EVENT_DELAY_SECONDS", "2")))
    except ValueError:
        return 0


async def publish(session: AsyncSession, events: Iterable[DomainEvent]) -> list[int]:
    # 4.3.2 Шаг 1: пишем событие в domain_events_log в той же транзакции, что и команда.
    # Это outbox-pattern: гарантирует, что событие не потеряется при сбое воркера.
    inserted_ids: list[int] = []
    payloads: list[dict] = []
    for ev in events:
        payload = {
            "event_type": ev.event_type,
            "aggregate_type": ev.aggregate_type,
            "aggregate_id": ev.aggregate_id,
            "occurred_at": ev.occurred_at.astimezone(timezone.utc).isoformat(),
        }
        result = await session.execute(
            text(
                """
                INSERT INTO domain_events_log (event_type, aggregate_type, aggregate_id, payload_json, status)
                VALUES (:event_type, :aggregate_type, :aggregate_id, :payload_json, 'pending')
                RETURNING id
                """
            ),
            {
                "event_type": ev.event_type,
                "aggregate_type": ev.aggregate_type,
                "aggregate_id": ev.aggregate_id,
                "payload_json": json.dumps(payload, ensure_ascii=False),
            },
        )
        row = result.first()
        if row is not None:
            inserted_ids.append(int(row[0]))
            payloads.append({**payload, "log_id": int(row[0])})
        logger.info(
            "4.3.1 Domain Event published: type=%s aggregate=%s/%s",
            ev.event_type, ev.aggregate_type, ev.aggregate_id,
        )

    # 4.3.2 Шаг 2: после коммита SQLAlchemy ставим задачи в Celery (это делает caller —
    # вызов schedule_after_commit() передаёт payloads наружу).
    return inserted_ids


def schedule_handlers(payloads: list[dict]) -> None:
    # 4.3.2 Шаг 3: постановка задач в Celery.
    # Импорт внутри функции — чтобы не было circular import.
    from elevator_control.application.events.handlers import process_domain_event

    delay = _event_delay_seconds()
    for p in payloads:
        log_id = int(p["log_id"])
        if delay > 0:
            # 4.4 Eventual Consistency: read-модель обновится с задержкой
            process_domain_event.apply_async(args=[log_id], countdown=delay)
            logger.info(
                "4.4 Eventual Consistency: queued event log_id=%s with delay=%ss",
                log_id, delay,
            )
        else:
            process_domain_event.delay(log_id)
            logger.info("4.3.2 Queue: queued event log_id=%s", log_id)
