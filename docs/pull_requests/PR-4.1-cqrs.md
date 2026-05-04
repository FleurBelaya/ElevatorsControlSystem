# PR: feat(cqrs) — 4.1 CQRS / Read Model / Query без ORM

## Что реализовано
- 4.1.1 Разделение Command/Query: GET идёт в `*QueryService`, write — в `*CommandService`.
- 4.1.2 Денормализованная read-модель: таблицы `lifts_read`, `events_read`,
  `service_requests_read`, `technicians_read`, `reports_read`, `sensors_read`,
  плюс outbox `domain_events_log` и blacklist `revoked_tokens` (миграция 003).
- 4.1.3 Query без ORM: пул `asyncpg` (`infrastructure/raw_pool.py`) и сервисы
  в `application/queries/`, все запросы — параметризованные.

## Файлы (ключевые)
- `alembic/versions/003_cqrs_read_model.py`
- `elevator_control/infrastructure/raw_pool.py`
- `elevator_control/application/queries/*.py`
- `elevator_control/application/read_sync.py`
- `elevator_control/adapters/inbound/api/v1/*.py` (GET → Query, write → Command)
- `elevator_control/adapters/inbound/api/deps.py` (раздельные DI)

## Как проверить
1. `alembic upgrade head` — применятся 003-миграция и backfill.
2. Запустить API: `uvicorn elevator_control.main:app --reload --port 8000`.
3. Зарегистрироваться, залогиниться, GET `/api/v1/lifts` — приходит из `lifts_read` (raw SQL).
4. POST `/api/v1/lifts` — пишется в `lifts` (ORM); read-модель догонит после worker'а (см. PR 4.3).
