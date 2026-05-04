# 4.1.1 CQRS — Query Side: базовый класс с общими утилитами для query-сервисов.
# 4.1.3 Query без ORM: все запросы идут через asyncpg pool, без SQLAlchemy.

from __future__ import annotations

import logging
from typing import Any

import asyncpg

from elevator_control.application.auth import AuthorizationService
from elevator_control.domain import auth as domain_auth

logger = logging.getLogger(__name__)


class BaseQueryService:
    # 4.1.1 CQRS — Query Side
    def __init__(self, pool: asyncpg.Pool, authz: AuthorizationService) -> None:
        self._pool = pool
        self._authz = authz

    async def _owner_filter(self, actor: domain_auth.User) -> int | None:
        # 4.1.1 CQRS: уважаем тот же ownership, что и в command-стороне (RBAC).
        return None if await self._authz.can_bypass_ownership(actor.id) else actor.id

    async def _fetch_all(self, sql: str, *args: Any) -> list[asyncpg.Record]:
        # 4.1.3 Query без ORM: prepared-параметры через asyncpg ($1, $2, ...).
        # 6.3.2 SQL-инъекция: значения никогда не интерполируются в текст SQL —
        # только через параметры драйвера.
        async with self._pool.acquire() as conn:
            return await conn.fetch(sql, *args)

    async def _fetch_one(self, sql: str, *args: Any) -> asyncpg.Record | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(sql, *args)

    async def _fetch_value(self, sql: str, *args: Any) -> Any:
        async with self._pool.acquire() as conn:
            return await conn.fetchval(sql, *args)
