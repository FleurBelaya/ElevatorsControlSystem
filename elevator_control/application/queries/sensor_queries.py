# 4.1.1 CQRS — Query Side: только чтение датчиков из read-модели.
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
class SensorReadDTO:
    # 4.1.2 Read Model
    id: int
    owner_id: int
    lift_id: int
    lift_model: str
    sensor_type: str
    current_value: float
    threshold_norm: float
    ratio: float
    zone: str
    synced_at: datetime


class SensorQueryService(BaseQueryService):
    # 4.1.1 CQRS — Query Side
    async def list_for_lift(self, actor: domain_auth.User, lift_id: int) -> list[SensorReadDTO]:
        await self._authz.require(actor.id, "sensors:read")
        t0 = time.perf_counter()
        owner = await self._owner_filter(actor)
        if owner is None:
            sql = """
                SELECT id, owner_id, lift_id, lift_model, sensor_type,
                       current_value, threshold_norm, ratio, zone, synced_at
                FROM sensors_read WHERE lift_id = $1 ORDER BY id
            """
            rows = await self._fetch_all(sql, lift_id)
        else:
            sql = """
                SELECT id, owner_id, lift_id, lift_model, sensor_type,
                       current_value, threshold_norm, ratio, zone, synced_at
                FROM sensors_read WHERE lift_id = $1 AND owner_id = $2 ORDER BY id
            """
            rows = await self._fetch_all(sql, lift_id, owner)
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "5.2.2 metric: query sensors.list_for_lift lift_id=%s rows=%s time=%.1fms",
            lift_id, len(rows), duration_ms,
        )
        return [SensorReadDTO(**dict(r)) for r in rows]

    async def get_by_id(self, actor: domain_auth.User, sensor_id: int) -> SensorReadDTO:
        await self._authz.require(actor.id, "sensors:read")
        t0 = time.perf_counter()
        owner = await self._owner_filter(actor)
        if owner is None:
            sql = """
                SELECT id, owner_id, lift_id, lift_model, sensor_type,
                       current_value, threshold_norm, ratio, zone, synced_at
                FROM sensors_read WHERE id = $1
            """
            row = await self._fetch_one(sql, sensor_id)
        else:
            sql = """
                SELECT id, owner_id, lift_id, lift_model, sensor_type,
                       current_value, threshold_norm, ratio, zone, synced_at
                FROM sensors_read WHERE id = $1 AND owner_id = $2
            """
            row = await self._fetch_one(sql, sensor_id, owner)
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "5.2.2 metric: query sensors.get_by_id id=%s rows=%s time=%.1fms",
            sensor_id, 0 if row is None else 1, duration_ms,
        )
        if row is None:
            raise NotFoundError("Датчик не найден")
        return SensorReadDTO(**dict(row))
