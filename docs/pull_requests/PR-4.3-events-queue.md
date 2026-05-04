# PR: feat(events) — 4.3 Domain Events / Очередь / 4.4 Eventual Consistency

## Что реализовано
- 4.3.1 Domain Events: 12 типов, минимум двух обязательных (LiftCreated,
  ServiceRequestCreated) выполнен.
- 4.3.2 Command → Event → Queue → Worker:
  * outbox в `domain_events_log` пишется в той же транзакции, что и команда;
  * `Session.after_commit` хук ставит задачу в Celery (`process_domain_event`);
  * worker применяет событие к read-модели через `read_sync.sync_*`.
- 4.4 Eventual Consistency: задача ставится с `countdown=CQRS_EVENT_DELAY_SECONDS`
  (по умолчанию 2 с). После POST GET по read-модели может ещё не вернуть новую строку.

## Файлы
- `elevator_control/application/events/domain_events.py`
- `elevator_control/application/events/publisher.py`
- `elevator_control/application/events/handlers.py`
- `elevator_control/infrastructure/database.py` (after_commit hook)
- `elevator_control/infrastructure/celery_app.py` (регистрация task)

## Как проверить
1. Запустить worker:
   `celery -A elevator_control.infrastructure.celery_app worker --loglevel=info --pool=solo`
2. POST `/api/v1/lifts` — в логах celery появится `process_domain_event`,
   в `domain_events_log` строка `processed`, в `lifts_read` новая строка.
3. Сделать паузу `CQRS_EVENT_DELAY_SECONDS` и сравнить «до/после» — это и есть eventual consistency.
