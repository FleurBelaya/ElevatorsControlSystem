# Elevator Control System

FastAPI + PostgreSQL + Celery: учебный пример системы управления лифтовым оборудованием.
Демонстрирует CQRS (разделение command/query), eventual consistency через очередь,
несколько BFF-бэкендов под разных клиентов и набор практик безопасности API.

## 1. Архитектура

Hexagonal-архитектура (Ports & Adapters) + CQRS + Event Queue:

```
                 ┌────────────────────────────────────────────────────────┐
                 │                  HTTP edge (FastAPI)                   │
                 │  /api/v1/...           │   /bff/{web,mobile,desktop}   │
                 │  единые правила/RBAC   │   агрегаты под конкретный UI  │
                 └────────────────┬───────┴───────────┬────────────────────┘
                                  │                   │
                            (POST/PATCH/DELETE)     (GET)
                                  │                   │
              ┌───────────────────▼─────────┐   ┌─────▼────────────────────────┐
              │   *CommandService (ORM)     │   │  *QueryService (raw SQL)     │
              │   • валидация Pydantic      │   │  • НЕ использует ORM         │
              │   • RBAC + ownership        │   │  • asyncpg pool              │
              │   • запись write-модели     │   │  • читает только из read-мод.│
              │   • публикация Domain Event │   └──────────────┬───────────────┘
              └───────────┬───────────┬─────┘                  │
                          │           │                        │
                  outbox  │           │   Celery task          │
                          │           ▼                        │
                          │   ┌─────────────────┐              │
                          │   │ Celery worker   │              │
                          │   │ process_domain_ │              │
                          │   │ event           │              │
                          │   └───────┬─────────┘              │
                          ▼           │                        │
              ┌─────────────────┐     │ read_sync.sync_*()     │
              │  Write Model    │     ▼                        │
              │ lifts/sensors/… │  ┌─────────────────────────┐ │
              │ (нормализована) │  │ Read Model              │◄┘
              └─────────────────┘  │ lifts_read/events_read/…│
                                   │ (денормализована)       │
                                   └─────────────────────────┘
```

### Слои

- `domain/` — чистые сущности и enum-ы (без зависимостей).
- `ports/outbound/` — Protocol-интерфейсы репозиториев.
- `application/` — бизнес-логика:
  - `services.py` — **Command** сервисы (write).
  - `queries/` — **Query** сервисы (read, raw SQL).
  - `events/` — Domain Events, publisher (outbox), worker handlers.
  - `read_sync.py` — апсерты для read-модели.
  - `cache.py` — TTL-кэш query-стороны с инвалидацией.
  - `observability.py` — снимок hot-points для `/metrics`.
- `adapters/inbound/api/` — HTTP-edge (FastAPI):
  - `v1/` — основной API (CQRS под одним префиксом).
  - `bff/` — отдельные backend-роутеры под web/mobile/desktop.
- `adapters/outbound/persistence/` — реализация репозиториев SQLAlchemy.
- `infrastructure/` — конфиг, AsyncEngine для ORM, asyncpg pool для query, Celery.

## 2. Как запустить

### 2.1. Требования

- Python 3.13+
- PostgreSQL 14+ (на `localhost:5432`)
- Redis 6+ (на `localhost:6379`) — для Celery broker/backend
- `pip install -r requirements.txt`

### 2.2. Конфигурация

Создайте `.env` в корне проекта:

```
DATABASE_URL=postgresql+psycopg://postgres:0519@localhost:5432/elevator_control
SIMULATION_INTERVAL_SECONDS=7.0

# 6.2 JWT
JWT_SECRET_KEY=замените-на-длинную-случайную-строку
ELEVATOR_REGISTRATION_ADMIN_CODE=ADMIN123

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# 6.3.4 CORS — только эти домены допустимы
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:8000

# 4.4 eventual consistency — задержка применения событий воркером, секунды
CQRS_EVENT_DELAY_SECONDS=2

# 6.3.1 Rate limit
RATE_LIMIT_PER_MINUTE=120
RATE_LIMIT_BURST_PER_10S=30
```

### 2.3. База данных

```bash
# Применить миграции (включая 004 — read-модель + outbox + blacklist).
alembic upgrade head
```

Если БД уже существовала и в ней нет таблицы `alembic_version`, выполните перед `upgrade`:
```
alembic stamp 002
```

### 2.4. Запуск приложения

```bash
# 1) API
python -m uvicorn elevator_control.main:app --reload --port 8000

# 2) Воркер очереди — НУЖЕН для обновления read-модели (4.3.2 и 4.4)
celery -A elevator_control.infrastructure.celery_app worker --loglevel=info --pool=solo
```

OpenAPI: `http://localhost:8000/docs`

## 3. API описание

### 3.1 Auth

| Method | Path | Описание |
|--------|------|----------|
| POST | `/api/v1/auth/register` | Регистрация (роль `dispatcher` по умолчанию) |
| POST | `/api/v1/auth/login` | OAuth2 form login → access+refresh |
| POST | `/api/v1/auth/login-json` | JSON login |
| POST | `/api/v1/auth/refresh` | Обмен refresh-токена на новую пару |
| POST | `/api/v1/auth/logout` | Помещает текущий jti в blacklist |
| GET  | `/api/v1/auth/me` | Профиль текущего пользователя |

### 3.2 Domain (CQRS)

GET-эндпоинты идут через **Query** (raw SQL по read-модели), остальные — через **Command** (ORM + Domain Events).

| Метод | Путь | Сторона |
|-------|------|---------|
| GET | `/api/v1/lifts` | Query |
| POST | `/api/v1/lifts` | Command |
| GET | `/api/v1/lifts/{id}` | Query |
| PATCH | `/api/v1/lifts/{id}` | Command |
| DELETE | `/api/v1/lifts/{id}` | Command |
| GET | `/api/v1/lifts/heatmap` | Query (агрегаты тепловой карты) |
| POST | `/api/v1/lifts/{id}/restore-state` | Command |
| POST | `/api/v1/lifts/{id}/simulate-critical-emergency` | Command (атомарная транзакция) |

Аналогично для `/sensors`, `/events`, `/service-requests`, `/technicians`, `/reports`.

### 3.3 BFF (Backend for Frontend)

| Path | Описание |
|------|----------|
| GET `/bff/web/dashboard` | Дашборд для веб-клиента: 4 query → 1 ответ |
| GET `/bff/mobile/feed` | Лента мобильного клиента: компактные карточки |
| GET `/bff/desktop/lift-workbench/{lift_id}` | «Рабочее место по лифту» для десктопа |

### 3.4 Observability

| Path | Описание |
|------|----------|
| GET `/health` | Liveness |
| GET `/metrics` | Снимок hot-points за последние 60 секунд |

## 4. Где CQRS

- **Разделение Command/Query** — `application/services.py` (CommandService) vs `application/queries/*` (QueryService).
- **Разные модели данных** — write-таблицы `lifts/events/...` (миграция 001) и read-таблицы `lifts_read/events_read/...` (миграция 004 — `alembic/versions/003_cqrs_read_model.py`).
- **Query без ORM** — `application/queries/*.py` используют пул `asyncpg` (`infrastructure/raw_pool.py`); каждый SQL — c prepared-параметрами `$1/$2/...`.
- **HTTP-edge** — `adapters/inbound/api/v1/*.py`, GET → `*QueryDep`, POST/PATCH/DELETE → `*CmdDep`.

## 5. Где очередь

- **Domain Events** — `application/events/domain_events.py` (LiftCreated, ServiceRequestCreated, и ещё 10 типов).
- **Outbox + публикация** — `application/events/publisher.py` пишет событие в `domain_events_log` в той же транзакции, что и команда.
- **Хук commit** — `infrastructure/database.py` ловит `Session.after_commit` и ставит задачу в Celery.
- **Worker** — `application/events/handlers.py::process_domain_event` читает событие, применяет к read-модели через `application/read_sync.py`, помечает `processed`.
- **Eventual Consistency** — задача ставится с `countdown=CQRS_EVENT_DELAY_SECONDS` (по умолчанию 2 сек), что моделирует задержку догоняющей read-модели.

## 6. Безопасность

- **6.1.1 Валидация** — Pydantic `extra="forbid"` + длины/min/max во всех DTO.
- **6.1.2 Mass Assignment** — DTO не содержат `owner_id/id/created_at`.
- **6.1.3 owner_id из токена** — Command-сервисы выставляют `owner_id = current_user.id`.
- **6.2.1** Короткий TTL access-токена (15 минут).
- **6.2.2** Refresh с rotation — `/auth/refresh`.
- **6.2.3** Logout / blacklist — `revoked_tokens` (jti).
- **6.3.1** Rate limit per-IP (60s окно + 10s burst) — middleware в `main.py`.
- **6.3.2** SQL-инъекции — все запросы через параметры драйвера, никакой интерполяции значений.
- **6.3.3** XSS / security headers — `X-Content-Type-Options`, `X-Frame-Options`, CSP.
- **6.3.4** CORS whitelist — `CORS_ALLOWED_ORIGINS`, никаких `*`.

## 7. Поиск по коду

Все добавленные строки помечены номером пункта задания и заголовком, чтобы IDE-поиск работал точечно. Примеры:

- `4.1.1 CQRS` — разделение Command/Query.
- `4.1.2 Read Model` — денормализованная read-модель.
- `4.1.3 Query без ORM` — raw SQL поверх asyncpg.
- `4.3.1 Domain Event` — типы событий.
- `4.3.2 Event-очередь` — outbox + Celery worker.
- `4.4 Eventual Consistency` — задержка применения событий.
- `5.2.1 Тепловая карта` — hot points.
- `5.2.2 metric:` — структурированные логи.
- `5.2.3 cache` — кэш query.
- `6.1.1 Валидация`, `6.1.2 Mass Assignment`, `6.1.3 owner_id из токена`.
- `6.2.1`, `6.2.2`, `6.2.3` — JWT TTL/refresh/blacklist.
- `6.3.1`, `6.3.2`, `6.3.3`, `6.3.4` — Rate limit / SQL / XSS / CORS.
