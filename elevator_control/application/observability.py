# 5.2.1 Тепловая карта / горячие точки. Три hot-points:
#   1. Самый частый вопрос: GET list (api/v1/lifts, /events, /service-requests).
#   2. Тяжёлые операции: command (POST/PATCH/DELETE) — создание лифта, аварийная транзакция.
#   3. Очереди: воркер (process_domain_event).
# 5.2.2 Метрики через логи (см. logger.info "5.2.2 metric: ..."). Этот модуль
# собирает простой агрегат в памяти на 60 секунд для быстрого ответа /metrics.

from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Deque

# структура: тип hot-point → ключ → deque((ts, duration_ms, rows, ok))
_lock = Lock()
_buckets: dict[str, dict[str, Deque[tuple[float, float, int, bool]]]] = {
    "query": {},
    "command": {},
    "worker": {},
}
_WINDOW = 60.0


def record(hot_point: str, key: str, duration_ms: float, *, rows: int = 0, ok: bool = True) -> None:
    # 5.2.2 Метрики: добавляем точку в кольцевой буфер.
    if hot_point not in _buckets:
        return
    now = time.time()
    with _lock:
        bucket = _buckets[hot_point].setdefault(key, deque())
        bucket.append((now, duration_ms, rows, ok))
        # очищаем старые
        cutoff = now - _WINDOW
        while bucket and bucket[0][0] < cutoff:
            bucket.popleft()


def snapshot() -> dict:
    # 5.2.1 Снимок горячих точек: используется в /metrics эндпоинте и для тепловой карты.
    out: dict = {"window_seconds": _WINDOW, "hot_points": {}}
    now = time.time()
    cutoff = now - _WINDOW
    with _lock:
        for hp_name, keys in _buckets.items():
            entries: list[dict] = []
            for key, bucket in keys.items():
                fresh = [item for item in bucket if item[0] >= cutoff]
                if not fresh:
                    continue
                durations = [d for _, d, _, _ in fresh]
                rows = sum(r for _, _, r, _ in fresh)
                errors = sum(0 if ok else 1 for _, _, _, ok in fresh)
                entries.append(
                    {
                        "key": key,
                        "calls": len(fresh),
                        "rows": rows,
                        "errors": errors,
                        "avg_ms": round(sum(durations) / len(durations), 2),
                        "max_ms": round(max(durations), 2),
                    }
                )
            entries.sort(key=lambda e: -e["calls"])
            out["hot_points"][hp_name] = entries
    return out
