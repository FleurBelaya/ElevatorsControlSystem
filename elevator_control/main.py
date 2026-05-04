# запуск: python -m uvicorn elevator_control.main:app --reload

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from elevator_control.adapters.inbound.api.v1 import api_v1_router
from elevator_control.adapters.inbound.api.bff import bff_router
from elevator_control.adapters.outbound.persistence import repositories_impl as impl
from elevator_control.application import observability
from elevator_control.application.simulation import run_sensor_simulation_tick
from elevator_control.domain.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from elevator_control.infrastructure.config import settings
from elevator_control.infrastructure.database import AsyncSessionLocal, engine
from elevator_control.infrastructure.raw_pool import close_pool, get_pool

# 2.4 - Логгирование: настройка структурированного формата логов
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def _simulation_tick_once() -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            lifts = impl.SqlLiftRepository(session)
            sensors = impl.SqlSensorRepository(session)
            events = impl.SqlEventRepository(session)
            requests = impl.SqlServiceRequestRepository(session)
            await run_sensor_simulation_tick(lifts, sensors, events, requests)


async def _simulation_loop() -> None:
    while True:
        try:
            await asyncio.sleep(settings.simulation_interval_seconds)
            await _simulation_tick_once()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Ошибка фоновой симуляции датчиков")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("БД (asyncpg): проверка подключения успешна")
    except Exception:
        logger.exception(
            "БД: подключение не удалось. Проверьте DATABASE_URL в .env "
            "(для API нужен рабочий PostgreSQL; строка postgresql+psycopg:// преобразуется в asyncpg)."
        )
    # 4.1.3 Query без ORM: инициализируем asyncpg pool заранее, а не при первом запросе.
    try:
        await get_pool()
    except Exception:
        logger.exception("4.1.3 не удалось создать asyncpg pool для read-стороны")

    task = asyncio.create_task(_simulation_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await close_pool()
    await engine.dispose()


app = FastAPI(
    title="Elevator Control API",
    version="2.0.0",
    lifespan=lifespan,
)


# 6.3.4 CORS whitelist: ТОЛЬКО разрешённые домены, никаких "*".
# 6.3.4 + cookies/credentials: allow_credentials=False, чтобы безопасно работать с
# несколькими доменами; для бэкенда это нормально, токен передаётся в заголовке.
_cors_origins = settings.cors_allowed_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Client", "Accept"],
    max_age=600,
)
logger.info("6.3.4 CORS whitelist: %s", _cors_origins)


# 6.3.3 XSS / общие security headers: добавляем consvервативные заголовки.
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    # 6.3.3 Защита от XSS: запрещаем браузеру угадывать MIME, грузить во фрейме,
    # включаем CSP и Referrer-Policy. JSON-API всегда отдаёт application/json,
    # поэтому жёсткий CSP (default-src 'none') не ломает фронт.
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # Для статической SPA (web-клиент) разрешаем self/inline-скрипты,
        # для API-ответов (JSON) браузер всё равно не исполняет HTML.
        path = request.url.path
        if path.startswith("/api/") or path.startswith("/bff/"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'",
            )
        else:
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                "connect-src 'self'; frame-ancestors 'none'",
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)


# 6.3.1 Rate limiting: token-bucket per-IP, простая память без внешних зависимостей.
class RateLimitMiddleware(BaseHTTPMiddleware):
    # 6.3.1 Лимиты: rate_limit_per_minute и rate_limit_burst_per_10s из настроек.
    # Превышение → 429 Too Many Requests.
    def __init__(self, app, *, per_minute: int, burst_per_10s: int) -> None:
        super().__init__(app)
        self._per_minute = max(1, per_minute)
        self._burst_per_10s = max(1, burst_per_10s)
        self._buckets: dict[str, deque[float]] = {}

    def _client_key(self, request: Request) -> str:
        # 6.3.1: учитываем X-Forwarded-For (если есть прокси) — но только первый IP,
        # чтобы клиент не подделывал несколько IP в одном заголовке.
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",", 1)[0].strip()
        if request.client is not None:
            return request.client.host
        return "unknown"

    async def dispatch(self, request: Request, call_next):
        # 6.3.1 Не лимитируем preflight CORS и health-check.
        if request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path
        if path in ("/health", "/healthz") or path.startswith("/clients"):
            return await call_next(request)

        key = self._client_key(request)
        now = time.monotonic()
        bucket = self._buckets.setdefault(key, deque())
        # Чистим устаревшие записи (>60 секунд)
        cutoff = now - 60.0
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        # 60-секундное окно
        if len(bucket) >= self._per_minute:
            return JSONResponse(
                status_code=429,
                content={"detail": "6.3.1 Rate limit (60s window) exceeded"},
                headers={"Retry-After": "10"},
            )
        # 10-секундный burst
        burst_cutoff = now - 10.0
        burst_count = sum(1 for ts in bucket if ts >= burst_cutoff)
        if burst_count >= self._burst_per_10s:
            return JSONResponse(
                status_code=429,
                content={"detail": "6.3.1 Rate limit (10s burst) exceeded"},
                headers={"Retry-After": "5"},
            )
        bucket.append(now)
        return await call_next(request)


app.add_middleware(
    RateLimitMiddleware,
    per_minute=settings.rate_limit_per_minute,
    burst_per_10s=settings.rate_limit_burst_per_10s,
)
logger.info(
    "6.3.1 Rate limit включен: %s req/min, burst %s/10s",
    settings.rate_limit_per_minute,
    settings.rate_limit_burst_per_10s,
)


# 2.4 - Логгирование + 5.2.2 метрики: middleware для логирования каждого HTTP-запроса
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "5.2.2 metric: HTTP %s %s ERROR time=%.1fms",
                request.method, request.url.path, duration_ms,
            )
            raise
        duration_ms = (time.perf_counter() - start) * 1000
        # 5.2.2 Метрики: время, путь, статус. Для GET (read) и POST (command) метрика одинакова —
        # разделять hot-points можно по тегу пути.
        logger.info(
            "5.2.2 metric: HTTP %s %s status=%s time=%.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        # 5.2.1 Горячие точки: классификация по HTTP-методу.
        path = request.url.path
        if path.startswith("/api/") or path.startswith("/bff/"):
            hp = "query" if request.method == "GET" else "command"
            observability.record(
                hp,
                f"{request.method} {path}",
                duration_ms,
                ok=response.status_code < 400,
            )
        return response


app.add_middleware(RequestLoggingMiddleware)


@app.exception_handler(NotFoundError)
async def not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
async def conflict_handler(_request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(UnauthorizedError)
async def unauthorized_handler(_request: Request, exc: UnauthorizedError) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": str(exc)})


@app.exception_handler(ForbiddenError)
async def forbidden_handler(_request: Request, exc: ForbiddenError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# 5.2.1 Тепловая карта горячих точек / 5.2.2 Метрики: снимок за последние 60 сек.
@app.get("/metrics")
async def metrics() -> dict:
    return observability.snapshot()


# 4.1.1 CQRS API v1: содержит все command/query эндпоинты.
app.include_router(api_v1_router, prefix="/api/v1")
# 4.2 BFF: отдельные роутеры под каждый клиент (web/mobile/desktop).
app.include_router(bff_router, prefix="/bff")

# 3.1 Единый Backend API: статические клиенты подключены под /clients.
_clients_dir = Path(__file__).resolve().parent / "adapters" / "inbound" / "web_clients"
if _clients_dir.exists():
    app.mount("/clients", StaticFiles(directory=str(_clients_dir), html=True), name="clients")


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/clients/", status_code=307)


@app.get("/clients", include_in_schema=False)
async def clients_index_redirect() -> RedirectResponse:
    return RedirectResponse(url="/clients/", status_code=307)


@app.get("/clients/", include_in_schema=False)
async def clients_index() -> HTMLResponse:
    index_path = _clients_dir / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>Clients not found</h1>", status_code=404)
    return HTMLResponse(index_path.read_text(encoding="utf-8"))
