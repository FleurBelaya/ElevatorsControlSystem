"""
Транспортный слой (FastAPI).

TODO: добавить аутентификацию и авторизацию:
- JWT (OAuth2 password flow или bearer tokens)
- сопоставление ролей: диспетчер / техник / администратор
- зависимости FastAPI Depends(get_current_user), проверка прав на эндпоинты
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from elevator_control.adapters.inbound.api.v1 import api_v1_router
from elevator_control.adapters.outbound.persistence import repositories_impl as impl
from elevator_control.application.simulation import run_sensor_simulation_tick
from elevator_control.domain.exceptions import NotFoundError
from elevator_control.infrastructure.config import settings
from elevator_control.infrastructure.database import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _simulation_tick_sync() -> None:
    session = SessionLocal()
    try:
        lifts = impl.SqlLiftRepository(session)
        sensors = impl.SqlSensorRepository(session)
        events = impl.SqlEventRepository(session)
        requests = impl.SqlServiceRequestRepository(session)
        run_sensor_simulation_tick(lifts, sensors, events, requests)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def _simulation_loop() -> None:
    while True:
        try:
            await asyncio.sleep(settings.simulation_interval_seconds)
            await asyncio.to_thread(_simulation_tick_sync)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Ошибка фоновой симуляции датчиков")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_simulation_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Elevator Control API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(NotFoundError)
async def not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_v1_router, prefix="/api/v1")
