# 2.5 - Фоновая загрузка: API-эндпоинты для работы с фоновыми задачами.
# 2.5.1 - POST /tasks/diagnostic-report — запуск генерации отчёта (мгновенный ответ).
# 2.5.3 - GET /tasks/{task_id}/status — отслеживание статуса задачи.
# 2.6 - POST /tasks/delayed-status-check — отложенная задача (запуск через 10 секунд).

import logging

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from elevator_control.adapters.inbound.api.deps import CurrentUserDep
from elevator_control.application.tasks import generate_diagnostic_report, delayed_lift_status_check
from elevator_control.infrastructure.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks (background)"])


# --- Схемы запросов/ответов ---

class DiagnosticReportRequest(BaseModel):
    """2.5.1 - Запрос на генерацию диагностического отчёта."""
    lift_id: int = Field(..., description="ID лифта для диагностики")


class TaskStartedResponse(BaseModel):
    """2.5.1 - Мгновенный ответ: задача поставлена в очередь."""
    task_id: str = Field(..., description="Уникальный ID задачи для отслеживания")
    status: str = Field(default="queued", description="Начальный статус задачи")
    message: str


class TaskStatusResponse(BaseModel):
    """2.5.3 - Ответ с текущим статусом задачи."""
    task_id: str
    status: str
    progress: int | None = None
    step: str | None = None
    result: dict | None = None


class DelayedCheckRequest(BaseModel):
    """2.6 - Запрос на отложенную проверку."""
    lift_id: int = Field(..., description="ID лифта для отложенной проверки")


# --- Эндпоинты ---

@router.post(
    "/diagnostic-report",
    response_model=TaskStartedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="2.5.1 - Запуск фоновой генерации диагностического отчёта",
    description=(
        "Ставит задачу генерации диагностического отчёта в очередь Celery/Redis. "
        "API возвращает мгновенный ответ с task_id. Статус задачи можно отслеживать "
        "через GET /tasks/{task_id}/status."
    ),
)
async def start_diagnostic_report(
    body: DiagnosticReportRequest,
    current_user: CurrentUserDep,
) -> TaskStartedResponse:
    # 2.5.1 - API не ждёт выполнения задачи — мгновенный ответ
    # 2.4 - Логгирование
    logger.info(
        "Пользователь id=%s запустил генерацию диагностического отчёта для лифта id=%s",
        current_user.id, body.lift_id,
    )
    task = generate_diagnostic_report.delay(body.lift_id, current_user.id)
    return TaskStartedResponse(
        task_id=task.id,
        status="queued",
        message=f"Задача генерации отчёта для лифта #{body.lift_id} поставлена в очередь.",
    )


@router.get(
    "/{task_id}/status",
    response_model=TaskStatusResponse,
    summary="2.5.3 - Получение статуса фоновой задачи",
    description="Возвращает текущий статус задачи: PENDING, STARTED, PROGRESS, SUCCESS или FAILURE.",
)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    # 2.5.3 - Отслеживание статуса задачи через Celery AsyncResult
    result = celery_app.AsyncResult(task_id)

    response = TaskStatusResponse(
        task_id=task_id,
        status=result.status,
    )

    if result.state == "PROGRESS":
        meta = result.info or {}
        response.progress = meta.get("progress", 0)
        response.step = meta.get("step", "")
    elif result.state == "STARTED":
        meta = result.info or {}
        response.progress = meta.get("progress", 0)
        response.step = meta.get("step", "Запущено")
    elif result.state == "SUCCESS":
        response.progress = 100
        response.step = "Завершено"
        response.result = result.result
    elif result.state == "FAILURE":
        response.step = f"Ошибка: {str(result.info)}"

    return response


@router.post(
    "/delayed-status-check",
    response_model=TaskStartedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="2.6 - Отложенная задача: проверка лифта через 10 секунд",
    description=(
        "Ставит задачу проверки статуса лифта в очередь с задержкой 10 секунд (countdown=10). "
        "Задача начнёт выполняться только через 10 секунд после вызова API."
    ),
)
async def start_delayed_status_check(
    body: DelayedCheckRequest,
    current_user: CurrentUserDep,
) -> TaskStartedResponse:
    # 2.6 - Отложенная задача: countdown=10 означает задержку в 10 секунд
    # 2.4 - Логгирование
    logger.info(
        "Пользователь id=%s запустил отложенную проверку лифта id=%s (задержка 10 сек)",
        current_user.id, body.lift_id,
    )
    task = delayed_lift_status_check.apply_async(args=[body.lift_id], countdown=10)
    return TaskStartedResponse(
        task_id=task.id,
        status="queued",
        message=f"Отложенная проверка лифта #{body.lift_id} запланирована через 10 секунд.",
    )
