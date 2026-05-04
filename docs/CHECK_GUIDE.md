# Гайд по проверке выполненности заданий 4.x / 5.x / 6.x

Документ описывает **как руками убедиться**, что каждый пункт задания реализован.
Все команды рассчитаны на запуск из корня проекта.

---

## 0. Подготовка окружения (один раз)

```bash
# 0.1. Зависимости
pip install -r requirements.txt

# 0.2. PostgreSQL и Redis должны быть запущены на localhost:5432 и localhost:6379
pg_isready -h localhost -p 5432
redis-cli -h localhost -p 6379 ping   # PONG

# 0.3. .env (если ещё нет): см. README.md, секция 2.2.
# Минимально нужны DATABASE_URL, JWT_SECRET_KEY, CELERY_BROKER_URL, CELERY_RESULT_BACKEND.

# 0.4. Применить миграции (создаст read-таблицы, outbox и blacklist)
# Если БД уже была — сначала зарегистрировать текущее состояние:
alembic stamp 002 || true
alembic upgrade head
```

После `alembic upgrade head` в БД появятся: `lifts_read`, `events_read`,
`service_requests_read`, `technicians_read`, `reports_read`, `sensors_read`,
`domain_events_log`, `revoked_tokens`.

```bash
# 0.5. Запуск API и worker'а в двух терминалах:
python -m uvicorn elevator_control.main:app --reload --port 8000
celery -A elevator_control.infrastructure.celery_app worker --loglevel=info --pool=solo
```

```bash
# 0.6. Регистрация и логин (получить access_token).
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@local","password":"password123","role":"administrator"}'

# Если уже есть — пропустите. Получаем токен:
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login-json \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@local","password":"password123"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
echo "$TOKEN"
```

> Если у первого администратора нет прав (миграция 002 могла назначить их `dispatcher`),
> однократно выполните: `INSERT INTO role_permissions (role_id, permission_id) SELECT 1, id FROM permissions ON CONFLICT DO NOTHING;`

---

## Задание 4. CQRS / BFF / Events / Eventual Consistency

### 4.1.1 — Разделение Command/Query, один эндпоинт для read+write запрещён

**Что проверяем:** GET и write идут в РАЗНЫЕ сервисы.

```bash
# Открыть код:
grep -nR "QueryService" elevator_control/adapters/inbound/api/v1 | head
grep -nR "CommandService\|CmdDep" elevator_control/adapters/inbound/api/v1 | head
```
Ожидаем: каждый GET-handler принимает `*QueryDep`, каждый write — `*CmdDep`.

```bash
# В рантайме: GET возвращает данные из read-модели
curl -s "http://localhost:8000/api/v1/lifts?limit=2" -H "Authorization: Bearer $TOKEN"
```
Ожидаем JSON с `items`, без 5xx.

### 4.1.2 — Разные модели данных (write нормализована, read денормализована)

```bash
# Сравните DDL write- и read-таблицы:
PGPASSWORD=0519 psql -h localhost -U postgres -d elevator_control \
  -c "\d lifts" -c "\d lifts_read"
```
Ожидаем: в `lifts_read` дополнительные колонки `sensors_count`, `open_events_count`,
`open_requests_count`, `last_event_type`, `max_sensor_ratio`, `synced_at`.

### 4.1.3 — Query без ORM

```bash
# Проверяем, что в queries/ нет SQLAlchemy ORM, только asyncpg.
grep -nR "sqlalchemy" elevator_control/application/queries/ || echo "OK: ORM не используется"
grep -nR "asyncpg\|_fetch_" elevator_control/application/queries/ | head
```
Ожидаем: SQLAlchemy не упомянут (только в `read_sync.py`, который относится к воркеру),
asyncpg/`_fetch_*` — есть.

### 4.2.1 — У каждого клиента свой backend (BFF)

```bash
ls elevator_control/adapters/inbound/api/bff/
# Ожидаем: web.py, mobile.py, desktop.py + schemas.py
curl -s -o /dev/null -w "web=%{http_code}\n"     "http://localhost:8000/bff/web/dashboard"           -H "Authorization: Bearer $TOKEN"
curl -s -o /dev/null -w "mobile=%{http_code}\n"  "http://localhost:8000/bff/mobile/feed"             -H "Authorization: Bearer $TOKEN"
curl -s -o /dev/null -w "desktop=%{http_code}\n" "http://localhost:8000/bff/desktop/lift-workbench/1" -H "Authorization: Bearer $TOKEN"
```
Ожидаем: все три = 200.

### 4.2.2 — Разные DTO для разных клиентов

```bash
# Web: компактный дашборд + risk_score
curl -s "http://localhost:8000/bff/web/dashboard" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -30
# Mobile: title и status="ok|warning|critical"
curl -s "http://localhost:8000/bff/mobile/feed"   -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -25
# Desktop: lift+sensors+events+service_requests одним ответом
curl -s "http://localhost:8000/bff/desktop/lift-workbench/1" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -25
```
Ожидаем три РАЗНЫЕ структуры ответа.

### 4.2.3 — Агрегация (несколько query → один ответ)

```bash
grep -n "asyncio.gather" elevator_control/adapters/inbound/api/bff/*.py
```
Ожидаем 3 совпадения (по одному на каждый BFF-эндпоинт).

### 4.3.1 — Domain Events (минимум 2)

```bash
grep -nE "make_(lift|service_request|sensor|event|technician|report)_" \
  elevator_control/application/events/domain_events.py | wc -l
```
Ожидаем число ≥ 12 (12 фабрик событий, обязательные — `make_lift_created` и `make_service_request_created`).

### 4.3.2 — Command → Event → Queue → Worker

```bash
# 1) Очистим лог метрик
> /tmp/check_celery.log
# 2) Создадим лифт (Command)
RESP=$(curl -s -X POST "http://localhost:8000/api/v1/lifts" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model":"CHK-433","status":"active","location":"check"}')
echo "Created: $RESP"
LIFT_ID=$(echo "$RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

# 3) В outbox должна появиться запись 'pending'
PGPASSWORD=0519 psql -h localhost -U postgres -d elevator_control \
  -c "SELECT id, event_type, aggregate_id, status FROM domain_events_log ORDER BY id DESC LIMIT 3;"

# 4) Подождём worker
sleep 4

# 5) После обработки status='processed', строка появилась в lifts_read
PGPASSWORD=0519 psql -h localhost -U postgres -d elevator_control \
  -c "SELECT id, event_type, status, processed_at FROM domain_events_log ORDER BY id DESC LIMIT 3;" \
  -c "SELECT id, model FROM lifts_read WHERE id=$LIFT_ID;"
```
Ожидаем переход `pending → processed` и строку в `lifts_read`.

### 4.4 — Eventual Consistency

```bash
# Сразу после POST GET по read-модели может ещё НЕ догнать.
RESP=$(curl -s -X POST "http://localhost:8000/api/v1/lifts" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model":"CHK-44","status":"active","location":"chk"}')
LIFT_ID=$(echo "$RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

# А) сразу
curl -s -o /dev/null -w "immediately=%{http_code}\n" \
  "http://localhost:8000/api/v1/lifts/$LIFT_ID" -H "Authorization: Bearer $TOKEN"
# Ожидаем 404 (read-модель ещё пуста — задержка CQRS_EVENT_DELAY_SECONDS=2)

sleep 4
# Б) через 4 секунды
curl -s -o /dev/null -w "after_4s=%{http_code}\n" \
  "http://localhost:8000/api/v1/lifts/$LIFT_ID" -H "Authorization: Bearer $TOKEN"
# Ожидаем 200 — read-модель догнала.
```

---

## Задание 5. Git / Observability / Кэш / Документация

### 5.1.1 — Стратегия веток

```bash
git branch -r
```
Ожидаем: `origin/main` + 5 feature-веток + `docs/readme-and-report`.

### 5.1.2 — Feature workflow

```bash
git log --oneline --decorate --graph --all | head -20
```
Ожидаем: каждая feature-ветка слита в main отдельным merge-коммитом (`Merge PR feature/...`).

### 5.1.3 — Pull request с описанием

```bash
ls docs/pull_requests/
cat docs/pull_requests/PR-4.1-cqrs.md | head -25
```
Ожидаем 5 файлов PR-*.md с разделами «Что реализовано», «Файлы», «Как проверить».

### 5.1.4 — Стандартизированные commit-message

```bash
git log --oneline d219cf4..HEAD
```
Ожидаем: каждый коммит — `feat(...)` / `docs(...)` / `Merge PR ...`, в заголовке номер пункта.

### 5.2.1 — Тепловая карта горячих точек

Три hot-points: `query` (GET list), `command` (write), `worker` (очередь).

```bash
# Прогреем все три:
curl -s -o /dev/null "http://localhost:8000/api/v1/lifts" -H "Authorization: Bearer $TOKEN"
curl -s -o /dev/null -X POST "http://localhost:8000/api/v1/lifts" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model":"hp","status":"active","location":"hp"}'
sleep 4
curl -s "http://localhost:8000/metrics" | python3 -m json.tool | head -40
```
Ожидаем: в `hot_points` непустые `query`, `command`. Метрики worker — в логах celery.

### 5.2.2 — Метрики через логи (время и количество записей)

```bash
# В терминале с uvicorn увидите строки '5.2.2 metric: ...':
# - HTTP <method> <path> status=N time=Xms
# - query lifts.list_page rows=N total=M time=Xms
# В терминале celery:
# - 5.2.2 metric: worker process_domain_event log_id=N ok=True time=Xms
# - 5.2.2 metric: read_sync lift time=Xms
grep -n "5.2.2 metric" elevator_control/application/queries/lift_queries.py | head
grep -n "5.2.2 metric" elevator_control/application/events/handlers.py
```

### 5.2.3 — Кэш + инвалидация после command

```bash
# 1) Первый GET → MISS (лог: 5.2.3 cache PUT)
curl -s -o /dev/null "http://localhost:8000/api/v1/lifts?limit=2" -H "Authorization: Bearer $TOKEN"
# 2) Второй GET → HIT (лог: 5.2.3 cache HIT)
curl -s -o /dev/null "http://localhost:8000/api/v1/lifts?limit=2" -H "Authorization: Bearer $TOKEN"
# 3) POST → INVALIDATE (лог: 5.2.3 cache INVALIDATE aggregate=lift cleared=1)
curl -s -o /dev/null -X POST "http://localhost:8000/api/v1/lifts" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model":"cache","status":"active","location":"x"}'
# 4) Третий GET → снова MISS
curl -s -o /dev/null "http://localhost:8000/api/v1/lifts?limit=2" -H "Authorization: Bearer $TOKEN"
```
В логах uvicorn ищите `5.2.3 cache PUT`, `5.2.3 cache HIT`, `5.2.3 cache INVALIDATE`.

### 5.3 — README

```bash
sed -n '1,80p' README.md
```
Ожидаем разделы: Архитектура / Как запустить / API / Где CQRS / Где очередь / Безопасность / Поиск по коду.

---

## Задание 6. Безопасность

### 6.1.1 — Валидация входных данных

```bash
# Слишком короткий пароль (min_length=8)
curl -s -o /dev/null -w "short_pwd=%{http_code}\n" -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' -d '{"email":"a@b.c","password":"123"}'
# Невалидный email
curl -s -o /dev/null -w "bad_email=%{http_code}\n" -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' -d '{"email":"not-email","password":"password123"}'
```
Ожидаем оба = 422.

### 6.1.2 — Защита от Mass Assignment

```bash
# Лишнее поле owner_id в payload — должно отвергаться
curl -s -X POST "http://localhost:8000/api/v1/lifts" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model":"X","status":"active","location":"Y","owner_id":99999}'
```
Ожидаем `422 + extra_forbidden`.

### 6.1.3 — owner_id из токена, а не из тела

```bash
# Создаём лифт; owner_id в payload не передаём
curl -s -X POST "http://localhost:8000/api/v1/lifts" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model":"OWN","status":"active","location":"Z"}' | python3 -m json.tool
# Затем в БД проверяем — owner_id == id текущего юзера
PGPASSWORD=0519 psql -h localhost -U postgres -d elevator_control \
  -c "SELECT id, owner_id, model FROM lifts WHERE model='OWN' ORDER BY id DESC LIMIT 1;"
```
Ожидаем `owner_id` = ID администратора (например, 3).

### 6.2.1 — Срок жизни access-токена

```bash
# Декодируем payload — поле exp.
echo "$TOKEN" | cut -d. -f2 | python3 -c '
import base64, json, sys, time
s = sys.stdin.read().strip()
s += "=" * (-len(s) % 4)
p = json.loads(base64.urlsafe_b64decode(s))
print("type:", p.get("type"), "exp_in_sec:", p["exp"]-int(time.time()))
'
```
Ожидаем `type: access` и `exp_in_sec` ≈ 900 (15 минут).

### 6.2.2 — Refresh-токен (обновление)

```bash
# Получаем пару
PAIR=$(curl -s -X POST http://localhost:8000/api/v1/auth/login-json \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@local","password":"password123"}')
REFRESH=$(echo "$PAIR" | python3 -c 'import json,sys; print(json.load(sys.stdin)["refresh_token"])')

# Обмениваем refresh → новая пара
NEW=$(curl -s -X POST http://localhost:8000/api/v1/auth/refresh \
  -H 'Content-Type: application/json' \
  -d "{\"refresh_token\":\"$REFRESH\"}")
echo "$NEW" | python3 -m json.tool

# Повторное использование старого refresh — должно отклоняться (rotation)
curl -s -X POST http://localhost:8000/api/v1/auth/refresh \
  -H 'Content-Type: application/json' \
  -d "{\"refresh_token\":\"$REFRESH\"}"
```
Ожидаем: первый `/refresh` → 200 + новые токены; повтор → 401 «Refresh-токен отозван».

### 6.2.3 — Logout (blacklist)

```bash
TOK=$(curl -s -X POST http://localhost:8000/api/v1/auth/login-json \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@local","password":"password123"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

# /me должен пройти
curl -s -o /dev/null -w "before_logout=%{http_code}\n" http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer $TOK"
# Logout
curl -s -o /dev/null -w "logout=%{http_code}\n"        -X POST http://localhost:8000/api/v1/auth/logout -H "Authorization: Bearer $TOK"
# /me с тем же токеном — должен отвергаться
curl -s http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer $TOK"
```
Ожидаем: `before_logout=200`, `logout=204`, после logout — `{"detail":"Токен отозван"}`.

### 6.3.1 — Rate limiting

```bash
# Burst 30 за 10 секунд по умолчанию.
for i in $(seq 1 35); do
  curl -s -o /dev/null -w "%{http_code} " "http://localhost:8000/api/v1/lifts/heatmap" -H "Authorization: Bearer $TOK"
done; echo
```
Ожидаем последовательность `200 ... 200 429 429 ...` (после ~27 запросов 429).

### 6.3.2 — SQL-инъекция

```bash
# Попытка инъекции в path-параметр (int) → 422 (валидация типа)
curl -s -X GET "http://localhost:8000/api/v1/lifts/1%20OR%201=1" -H "Authorization: Bearer $TOKEN"

# В коде: все запросы — параметризованные
grep -n "fetch\|fetchrow\|fetchval" elevator_control/application/queries/*.py | head
grep -n ":\\b\\(id\\|sensor_id\\|jti\\|user_id\\|expires_at\\)\\b" elevator_control/application/auth.py | head
```
Ожидаем 422 в HTTP-проверке и параметризованные запросы в коде.

### 6.3.3 — XSS / security headers

```bash
curl -s -D - -o /dev/null "http://localhost:8000/api/v1/lifts?limit=1" -H "Authorization: Bearer $TOKEN" \
  | grep -iE "x-content-type-options|x-frame-options|content-security-policy|referrer-policy"
```
Ожидаем все 4 заголовка: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`, `Referrer-Policy: no-referrer`.

### 6.3.4 — CORS только разрешённые домены

```bash
# Разрешённый origin
curl -s -o /dev/null -w "allowed=%{http_code}\n" -X OPTIONS http://localhost:8000/api/v1/lifts \
  -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: GET"

# Чужой origin
curl -s -i -X OPTIONS http://localhost:8000/api/v1/lifts \
  -H "Origin: http://evil.example.com" -H "Access-Control-Request-Method: GET" \
  | head -1
```
Ожидаем: разрешённый = 200, чужой = `HTTP/1.1 400 Bad Request`.

---

## Чек-лист

| Пункт | Команда | Ожидание |
|-------|---------|----------|
| 4.1.1 | `grep -nR "QueryService\|CommandService" elevator_control/adapters/inbound/api/v1` | разные сервисы для GET/write |
| 4.1.2 | `psql ... \d lifts_read` | денормализованная схема |
| 4.1.3 | `grep -nR sqlalchemy elevator_control/application/queries/` | пусто |
| 4.2.1 | `curl /bff/{web,mobile,desktop}/...` | 3×200 |
| 4.2.2 | три `curl` к BFF | 3 разные структуры |
| 4.2.3 | `grep asyncio.gather elevator_control/adapters/inbound/api/bff/` | ≥3 |
| 4.3.1 | `grep make_*_ events/domain_events.py` | ≥2 |
| 4.3.2 | POST → проверка `domain_events_log` и `lifts_read` | `pending → processed` |
| 4.4   | POST → GET сразу vs через 4 сек | `404 → 200` |
| 5.1.x | `git log --graph --all` | feature workflow + merge-PR |
| 5.2.1 | `GET /metrics` | hot points: query/command/worker |
| 5.2.2 | логи uvicorn/celery содержат `5.2.2 metric:` | да |
| 5.2.3 | GET, GET, POST, GET → cache MISS/HIT/INVALIDATE/MISS | да |
| 5.3   | `README.md` | все разделы есть |
| 6.1.1 | POST `register` с `password:"123"` | 422 |
| 6.1.2 | POST `lifts` с `owner_id` | 422 extra_forbidden |
| 6.1.3 | POST `lifts` без owner_id, проверить БД | owner_id = ID токена |
| 6.2.1 | decode JWT | `exp - now ≈ 900` |
| 6.2.2 | refresh старого jti дважды | 200 → 401 |
| 6.2.3 | logout, затем `/me` | 401 «Токен отозван» |
| 6.3.1 | 35×GET/heatmap | первые 27 = 200, далее 429 |
| 6.3.2 | `/lifts/1%20OR%201=1` | 422 |
| 6.3.3 | заголовки ответа | 4 security headers |
| 6.3.4 | OPTIONS чужой origin | 400 |
