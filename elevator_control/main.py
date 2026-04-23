# запуск: python -m uvicorn elevator_control.main:app --reload

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text

from elevator_control.adapters.inbound.api.v1 import api_v1_router
from elevator_control.adapters.outbound.persistence import repositories_impl as impl
from elevator_control.application.simulation import run_sensor_simulation_tick
from elevator_control.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from elevator_control.infrastructure.config import settings
from elevator_control.infrastructure.database import AsyncSessionLocal, engine

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
    task = asyncio.create_task(_simulation_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await engine.dispose()


app = FastAPI(
    title="Elevator Control API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: без этого браузер с другого порта (React/Vue), file:// или другой хост даёт «Failed to fetch».
# allow_credentials=True несовместим с allow_origins=["*"] по спецификации CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 2.4 - Логгирование: middleware для логирования каждого HTTP-запроса
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s → %s (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
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


# @app.get("/health")
# async def health() -> dict[str, str]:
#     return {"status": "ok"}


app.include_router(api_v1_router, prefix="/api/v1")

# 3.1 Единый Backend API:
# Бэкенд является единственным источником истины и обслуживает ВСЕХ клиентов. Клиенты здесь — статические страницы,
# но они используют один и тот же API по /api/v1 и не содержат локальной логики данных (только рендеринг + вызовы API).
_clients_dir = Path(__file__).resolve().parent / "adapters" / "inbound" / "web_clients"
if _clients_dir.exists():
    app.mount("/clients", StaticFiles(directory=str(_clients_dir), html=True), name="clients")


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    # 3.1 Единый Backend API: один входной URL сервера для API и клиентов.
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
