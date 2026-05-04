# PR: feat(security) — 6.1 / 6.2 / 6.3

## Что реализовано
- 6.1.1 Валидация: Pydantic `extra="forbid"`, длины и форматы во всех DTO.
- 6.1.2 Mass Assignment: лишние поля → 422; DTO не содержат owner_id/id.
- 6.1.3 owner_id из токена: command-сервис всегда выставляет owner_id из current_user.
- 6.2.1 Короткий TTL access (15 мин).
- 6.2.2 Refresh + rotation: `/auth/refresh` выдаёт новую пару, старый refresh попадает в blacklist.
- 6.2.3 Logout / blacklist: `/auth/logout` помечает jti в `revoked_tokens`.
- 6.3.1 Rate limit per-IP (60s окно, 10s burst) → 429.
- 6.3.2 SQL: только параметризованные запросы.
- 6.3.3 XSS: `X-Content-Type-Options`, `X-Frame-Options`, CSP.
- 6.3.4 CORS whitelist (`CORS_ALLOWED_ORIGINS`), никаких `*`.

## Файлы
- `elevator_control/application/auth.py` (refresh/logout/blacklist).
- `elevator_control/adapters/inbound/api/v1/auth.py` (новые эндпоинты).
- `elevator_control/adapters/inbound/api/schemas.py` (extra=forbid).
- `elevator_control/main.py` (RateLimitMiddleware, SecurityHeadersMiddleware, CORS).
- `elevator_control/infrastructure/config.py` (TTL, лимиты, CORS-white-list).

## Как проверить
- POST `/api/v1/lifts` с `"owner_id": 99999` → 422.
- POST `/api/v1/auth/logout` затем GET `/auth/me` тем же токеном → 401 'Токен отозван'.
- 35 быстрых GET → последние 8 уйдут с 429.
- preflight CORS с разрешённого/чужого Origin → 200/400.
