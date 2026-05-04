# 4.1.1 CQRS — Query Side: только чтение заявок из read-модели.
# 4.1.3 Query без ORM.

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime

from elevator_control.application.queries.base import BaseQueryService
from elevator_control.domain import auth as domain_auth
from elevator_control.domain.enums import ServiceRequestStatus
from elevator_control.domain.exceptions import NotFoundError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ServiceRequestReadDTO:
    id: int
    owner_id: int
    lift_id: int
    lift_model: str
    lift_location: str
    reason: str
    status: str
    technician_id: int | None
    technician_name: str | None
    created_at: datetime
    synced_at: datetime


class ServiceRequestQueryService(BaseQueryService):
    # 4.1.1 CQRS — Query Side
    async def get_by_id(self, actor: domain_auth.User, rid: int) -> ServiceRequestReadDTO:
        await self._authz.require(actor.id, "service_requests:read")
        t0 = time.perf_counter()
        owner = await self._owner_filter(actor)
        if owner is None:
            sql = """
                SELECT id, owner_id, lift_id, lift_model, lift_location,
                       reason, status, technician_id, technician_name,
                       created_at, synced_at
                FROM service_requests_read WHERE id = $1
            """
            row = await self._fetch_one(sql, rid)
        else:
            sql = """
                SELECT id, owner_id, lift_id, lift_model, lift_location,
                       reason, status, technician_id, technician_name,
                       created_at, synced_at
                FROM service_requests_read WHERE id = $1 AND owner_id = $2
            """
            row = await self._fetch_one(sql, rid, owner)
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info("5.2.2 metric: query service_requests.get_by_id rows=%s time=%.1fms",
                    0 if row is None else 1, duration_ms)
        if row is None:
            raise NotFoundError("Заявка не найдена")
        return ServiceRequestReadDTO(**dict(row))

    async def list_page(
        self,
        actor: domain_auth.User,
        skip: int,
        limit: int,
        lift_id: int | None,
        status_filter: ServiceRequestStatus | None,
    ) -> tuple[list[ServiceRequestReadDTO], int]:
        await self._authz.require(actor.id, "service_requests:read")
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
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        count_sql = f"SELECT COUNT(*) FROM service_requests_read {where_sql}"
        total = int(await self._fetch_value(count_sql, *params) or 0)

        params_with_paging = list(params) + [int(limit), int(skip)]
        list_sql = f"""
            SELECT id, owner_id, lift_id, lift_model, lift_location,
                   reason, status, technician_id, technician_name,
                   created_at, synced_at
            FROM service_requests_read
            {where_sql}
            ORDER BY id DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """
        rows = await self._fetch_all(list_sql, *params_with_paging)
        items = [ServiceRequestReadDTO(**dict(r)) for r in rows]
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "5.2.2 metric: query service_requests.list_page rows=%s total=%s time=%.1fms",
            len(items), total, duration_ms,
        )
        return items, total
