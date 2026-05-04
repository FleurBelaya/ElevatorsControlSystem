# 4.1.1 CQRS — Query Side: только чтение лифтов из read-модели.
# 4.1.2 Read Model: используется денормализованная таблица lifts_read.
# 4.1.3 Query без ORM: чистый SQL поверх asyncpg.

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime

from elevator_control.application.queries.base import BaseQueryService
from elevator_control.domain import auth as domain_auth
from elevator_control.domain.exceptions import NotFoundError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LiftReadDTO:
    # 4.1.2 Read Model: денормализованный DTO лифта (с агрегатами).
    id: int
    owner_id: int
    model: str
    status: str
    location: str
    is_emergency: bool
    sensors_count: int
    open_events_count: int
    open_requests_count: int
    last_event_type: str | None
    last_event_at: datetime | None
    max_sensor_ratio: float | None
    synced_at: datetime


class LiftQueryService(BaseQueryService):
    # 4.1.1 CQRS — Query Side: только чтение
    async def get_by_id(self, actor: domain_auth.User, lift_id: int) -> LiftReadDTO:
        await self._authz.require(actor.id, "lifts:read")
        # 5.2.1, 5.2.2 Observability: засекаем время выполнения hot-point запроса
        t0 = time.perf_counter()
        owner = await self._owner_filter(actor)
        if owner is None:
            sql = """
                SELECT id, owner_id, model, status, location, is_emergency,
                       sensors_count, open_events_count, open_requests_count,
                       last_event_type, last_event_at, max_sensor_ratio, synced_at
                FROM lifts_read WHERE id = $1
            """
            row = await self._fetch_one(sql, lift_id)
        else:
            sql = """
                SELECT id, owner_id, model, status, location, is_emergency,
                       sensors_count, open_events_count, open_requests_count,
                       last_event_type, last_event_at, max_sensor_ratio, synced_at
                FROM lifts_read WHERE id = $1 AND owner_id = $2
            """
            row = await self._fetch_one(sql, lift_id, owner)
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "5.2.2 metric: query lifts.get_by_id id=%s rows=%s time=%.1fms",
            lift_id, 0 if row is None else 1, duration_ms,
        )
        if row is None:
            raise NotFoundError("Лифт не найден")
        return LiftReadDTO(**dict(row))

    async def list_page(
        self,
        actor: domain_auth.User,
        skip: int,
        limit: int,
        status_filter: str | None = None,
    ) -> tuple[list[LiftReadDTO], int]:
        await self._authz.require(actor.id, "lifts:read")
        # 5.2.1 Observability hot-point: список — самый частый запрос
        t0 = time.perf_counter()
        owner = await self._owner_filter(actor)
        where_parts: list[str] = []
        params: list = []
        if owner is not None:
            params.append(owner)
            where_parts.append(f"owner_id = ${len(params)}")
        if status_filter is not None:
            params.append(status_filter)
            where_parts.append(f"status = ${len(params)}")
        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        # 6.3.2 SQL-инъекция: значения только через $-параметры,
        # текст WHERE формируется только из доверенных кусков с известными именами полей.
        count_sql = f"SELECT COUNT(*) FROM lifts_read {where}"
        total = int(await self._fetch_value(count_sql, *params) or 0)

        params_with_paging = list(params) + [int(limit), int(skip)]
        list_sql = f"""
            SELECT id, owner_id, model, status, location, is_emergency,
                   sensors_count, open_events_count, open_requests_count,
                   last_event_type, last_event_at, max_sensor_ratio, synced_at
            FROM lifts_read
            {where}
            ORDER BY id
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """
        rows = await self._fetch_all(list_sql, *params_with_paging)
        items = [LiftReadDTO(**dict(r)) for r in rows]
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "5.2.2 metric: query lifts.list_page rows=%s total=%s time=%.1fms",
            len(items), total, duration_ms,
        )
        return items, total

    async def heatmap_summary(self, actor: domain_auth.User) -> dict:
        # 5.2.1 Тепловая карта: агрегированный читательский запрос для дашборда.
        await self._authz.require(actor.id, "lifts:read")
        owner = await self._owner_filter(actor)
        t0 = time.perf_counter()
        sql_owner = "WHERE owner_id = $1" if owner is not None else ""
        params = [owner] if owner is not None else []
        sql = f"""
            SELECT
                COUNT(*) AS total_lifts,
                COUNT(*) FILTER (WHERE is_emergency) AS emergency_lifts,
                COUNT(*) FILTER (WHERE status = 'stopped') AS stopped_lifts,
                COALESCE(SUM(open_events_count), 0) AS total_open_events,
                COALESCE(SUM(open_requests_count), 0) AS total_open_requests,
                COALESCE(MAX(max_sensor_ratio), 0) AS max_sensor_ratio
            FROM lifts_read {sql_owner}
        """
        row = await self._fetch_one(sql, *params)
        duration_ms = (time.perf_counter() - t0) * 1000
        result = dict(row) if row else {}
        logger.info("5.2.2 metric: query lifts.heatmap_summary time=%.1fms", duration_ms)
        return result
