# PR: feat(observability) — 5.2 Hot points / Метрики / Кэш

## Что реализовано
- 5.2.1 Тепловая карта: hot points query / command / worker.
- 5.2.2 Метрики через логи + эндпоинт `/metrics` (avg/max/calls/errors за 60 секунд).
- 5.2.3 Кэш query (TTL 30s) + инвалидация по агрегату после command и в воркере.

## Файлы
- `elevator_control/application/observability.py` — record + snapshot.
- `elevator_control/application/cache.py` — TTL-кэш с тегами.
- `elevator_control/main.py` — `/metrics` эндпоинт + middleware вызывает `observability.record`.
- `elevator_control/application/events/handlers.py` — record для worker.

## Как проверить
- Сделать несколько GET `/api/v1/lifts` → в логах `5.2.3 cache PUT/HIT`.
- Сделать POST → `5.2.3 cache INVALIDATE`.
- GET `/metrics` → snapshot hot points за последние 60 секунд.
