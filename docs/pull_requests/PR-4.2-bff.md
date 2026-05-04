# PR: feat(bff) — 4.2 Backend for Frontend

## Что реализовано
- 4.2.1 Отдельный backend под каждого клиента: `/bff/web`, `/bff/mobile`, `/bff/desktop`.
- 4.2.2 Разные DTO под особенности UI (плотность экрана, объём данных, преподготовленные строки).
- 4.2.3 Агрегация: каждый BFF-эндпоинт параллельно дёргает 3–4 Query-сервиса и собирает один JSON.

## Файлы
- `elevator_control/adapters/inbound/api/bff/__init__.py` — корневой роутер.
- `elevator_control/adapters/inbound/api/bff/web.py` — `/dashboard`.
- `elevator_control/adapters/inbound/api/bff/mobile.py` — `/feed`.
- `elevator_control/adapters/inbound/api/bff/desktop.py` — `/lift-workbench/{id}`.
- `elevator_control/adapters/inbound/api/bff/schemas.py` — DTO под каждый клиент.

## Как проверить
- `GET /bff/web/dashboard` — компактный дашборд для SPA.
- `GET /bff/mobile/feed` — карточки с подготовленным title и status.
- `GET /bff/desktop/lift-workbench/1` — лифт + датчики + события + заявки в одном ответе.
