# 4.1.1 CQRS — Query Side: только чтение отчётов.
# 4.1.3 Query без ORM.

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
class ReportReadDTO:
    id: int
    owner_id: int
    service_request_id: int
    lift_id: int
    lift_model: str
    work_description: str
    final_lift_status: str
    created_at: datetime
    synced_at: datetime


class ReportQueryService(BaseQueryService):
    # 4.1.1 CQRS — Query Side
    async def get_by_id(self, actor: domain_auth.User, report_id: int) -> ReportReadDTO:
        await self._authz.require(actor.id, "reports:read")
        t0 = time.perf_counter()
        owner = await self._owner_filter(actor)
        if owner is None:
            sql = """
                SELECT id, owner_id, service_request_id, lift_id, lift_model,
                       work_description, final_lift_status, created_at, synced_at
                FROM reports_read WHERE id = $1
            """
            row = await self._fetch_one(sql, report_id)
        else:
            sql = """
                SELECT id, owner_id, service_request_id, lift_id, lift_model,
                       work_description, final_lift_status, created_at, synced_at
                FROM reports_read WHERE id = $1 AND owner_id = $2
            """
            row = await self._fetch_one(sql, report_id, owner)
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info("5.2.2 metric: query reports.get_by_id rows=%s time=%.1fms",
                    0 if row is None else 1, duration_ms)
        if row is None:
            raise NotFoundError("Отчёт не найден")
        return ReportReadDTO(**dict(row))

    async def list_page(
        self, actor: domain_auth.User, skip: int, limit: int
    ) -> tuple[list[ReportReadDTO], int]:
        await self._authz.require(actor.id, "reports:read")
        t0 = time.perf_counter()
        owner = await self._owner_filter(actor)
        where_sql = ""
        params: list = []
        if owner is not None:
            params.append(owner)
            where_sql = f"WHERE owner_id = ${len(params)}"

        total = int(await self._fetch_value(
            f"SELECT COUNT(*) FROM reports_read {where_sql}", *params
        ) or 0)

        params_with_paging = list(params) + [int(limit), int(skip)]
        list_sql = f"""
            SELECT id, owner_id, service_request_id, lift_id, lift_model,
                   work_description, final_lift_status, created_at, synced_at
            FROM reports_read
            {where_sql}
            ORDER BY id DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """
        rows = await self._fetch_all(list_sql, *params_with_paging)
        items = [ReportReadDTO(**dict(r)) for r in rows]
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "5.2.2 metric: query reports.list_page rows=%s total=%s time=%.1fms",
            len(items), total, duration_ms,
        )
        return items, total
