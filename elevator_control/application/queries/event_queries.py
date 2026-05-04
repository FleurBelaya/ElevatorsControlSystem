# 4.1.1 CQRS — Query Side: только чтение событий из read-модели.
# 4.1.3 Query без ORM.

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime

from elevator_control.application.queries.base import BaseQueryService
from elevator_control.domain import auth as domain_auth
from elevator_control.domain.enums import EventStatus, EventType
from elevator_control.domain.exceptions import NotFoundError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EventReadDTO:
    # 4.1.2 Read Model: денормализованное событие (с моделью лифта внутри).
    id: int
    owner_id: int
    lift_id: int
    lift_model: str
    lift_location: str
    event_type: str
    description: str
    status: str
    created_at: datetime
    synced_at: datetime


class EventQueryService(BaseQueryService):
    # 4.1.1 CQRS — Query Side
    async def get_by_id(self, actor: domain_auth.User, event_id: int) -> EventReadDTO:
        await self._authz.require(actor.id, "events:read")
        t0 = time.perf_counter()
        owner = await self._owner_filter(actor)
        if owner is None:
            sql = """
                SELECT id, owner_id, lift_id, lift_model, lift_location,
                       event_type, description, status, created_at, synced_at
                FROM events_read WHERE id = $1
            """
            row = await self._fetch_one(sql, event_id)
        else:
            sql = """
                SELECT id, owner_id, lift_id, lift_model, lift_location,
                       event_type, description, status, created_at, synced_at
                FROM events_read WHERE id = $1 AND owner_id = $2
            """
            row = await self._fetch_one(sql, event_id, owner)
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info("5.2.2 metric: query events.get_by_id rows=%s time=%.1fms",
                    0 if row is None else 1, duration_ms)
        if row is None:
            raise NotFoundError("Событие не найдено")
        return EventReadDTO(**dict(row))

    async def list_page(
        self,
        actor: domain_auth.User,
        skip: int,
        limit: int,
        lift_id: int | None,
        status_filter: EventStatus | None,
        event_type: EventType | None,
    ) -> tuple[list[EventReadDTO], int]:
        await self._authz.require(actor.id, "events:read")
        t0 = time.perf_counter()
        owner = await self._owner_filter(actor)
        where: list[str] = []
        params: list = []
        if owner is not None:
            params.append(owner)
            where.append(f"owner_id = ${len(params)}")
        if lift_id is not None:
            params.append(lift_id)
            where.append(f"lift_id = ${len(params)}")
        if status_filter is not None:
            params.append(status_filter.value)
            where.append(f"status = ${len(params)}")
        if event_type is not None:
            params.append(event_type.value)
            where.append(f"event_type = ${len(params)}")
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        count_sql = f"SELECT COUNT(*) FROM events_read {where_sql}"
        total = int(await self._fetch_value(count_sql, *params) or 0)

        params_with_paging = list(params) + [int(limit), int(skip)]
        list_sql = f"""
            SELECT id, owner_id, lift_id, lift_model, lift_location,
                   event_type, description, status, created_at, synced_at
            FROM events_read
            {where_sql}
            ORDER BY id DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """
        rows = await self._fetch_all(list_sql, *params_with_paging)
        items = [EventReadDTO(**dict(r)) for r in rows]
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "5.2.2 metric: query events.list_page rows=%s total=%s time=%.1fms",
            len(items), total, duration_ms,
        )
        return items, total
