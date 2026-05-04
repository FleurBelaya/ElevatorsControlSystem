# 4.1.3 Query без ORM: модуль создаёт прямой пул asyncpg для read-запросов.
# Write-сторона использует SQLAlchemy ORM (см. database.py),
# read-сторона использует исключительно raw SQL поверх asyncpg.

from __future__ import annotations

import logging
from typing import Optional

import asyncpg

from elevator_control.infrastructure.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


def _to_asyncpg_dsn(url: str) -> str:
    # 4.1.3 Query без ORM: преобразуем DSN из формата SQLAlchemy в формат asyncpg.
    raw = url.strip()
    if raw.startswith("postgresql+asyncpg://"):
        return "postgresql://" + raw.removeprefix("postgresql+asyncpg://")
    if raw.startswith("postgresql+psycopg://"):
        return "postgresql://" + raw.removeprefix("postgresql+psycopg://")
    if raw.startswith("postgres://") or raw.startswith("postgresql://"):
        return raw
    raise ValueError(f"Unsupported database URL for asyncpg: {url!r}")


async def get_pool() -> asyncpg.Pool:
    # 4.1.3 Query без ORM: ленивая инициализация пула при первом обращении.
    global _pool
    if _pool is None:
        dsn = _to_asyncpg_dsn(settings.database_url_async)
        _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10, command_timeout=10.0)
        logger.info("4.1.3 Query без ORM: инициализирован asyncpg pool")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("4.1.3 Query без ORM: asyncpg pool закрыт")
