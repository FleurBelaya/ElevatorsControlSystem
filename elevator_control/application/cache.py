# 5.2.3 Кэш: in-process TTL-кэш для read-стороны (query). Не требует внешних зависимостей.
# Принцип: команды публикуют события, воркер инвалидует ключи кэша по типу агрегата.
# Без воркера кэш можно сбрасывать вручную из command-сервисов (тоже сделано — см. commands.py).

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 30.0
_lock = asyncio.Lock()
_storage: dict[str, tuple[float, Any]] = {}
# Привязка ключей к агрегатам, чтобы invalidate_for_aggregate точно знал что чистить.
_index: dict[str, set[str]] = {}


async def get(key: str) -> Any | None:
    # 5.2.3 Кэш: чтение значения с проверкой TTL.
    async with _lock:
        item = _storage.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at < time.time():
            _storage.pop(key, None)
            for tag, keys in list(_index.items()):
                keys.discard(key)
                if not keys:
                    _index.pop(tag, None)
            return None
        logger.info("5.2.3 cache HIT key=%s", key)
        return value


async def put(key: str, value: Any, *, tags: list[str] | None = None, ttl_seconds: float | None = None) -> None:
    # 5.2.3 Кэш: запись значения с тегами для целевой инвалидации.
    ttl = ttl_seconds if ttl_seconds is not None else _DEFAULT_TTL_SECONDS
    async with _lock:
        _storage[key] = (time.time() + ttl, value)
        for tag in tags or []:
            _index.setdefault(tag, set()).add(key)
    logger.info("5.2.3 cache PUT key=%s ttl=%.0fs tags=%s", key, ttl, tags or [])


async def invalidate_for_aggregate(aggregate_type: str) -> None:
    # 5.2.3 Инвалидация после command: чистим все ключи, связанные с агрегатом.
    # Также инвалидируем «cross-влияющие» теги (изменение sensor влияет на lifts и т.д.).
    cascade = {
        "lift": ["lift", "sensor", "event", "service_request", "report"],
        "sensor": ["lift", "sensor"],
        "event": ["lift", "event"],
        "service_request": ["lift", "service_request", "technician"],
        "technician": ["technician", "service_request"],
        "report": ["lift", "report", "service_request"],
    }
    tags = cascade.get(aggregate_type, [aggregate_type])
    async with _lock:
        cleared = 0
        for tag in tags:
            keys = _index.pop(tag, set())
            for k in keys:
                if _storage.pop(k, None) is not None:
                    cleared += 1
    logger.info("5.2.3 cache INVALIDATE aggregate=%s tags=%s cleared=%s",
                aggregate_type, tags, cleared)


async def invalidate_all() -> None:
    # 5.2.3 Тотальная инвалидация (используется в тестах и при ошибках).
    async with _lock:
        _storage.clear()
        _index.clear()
    logger.info("5.2.3 cache CLEAR ALL")
