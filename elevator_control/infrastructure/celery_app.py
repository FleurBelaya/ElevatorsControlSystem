# 2.5.2 - Интеграция очереди: конфигурация Celery с брокером Redis.
# Архитектура: API (FastAPI) → Queue (Redis) → Worker (Celery).
# Запуск воркера: celery -A elevator_control.infrastructure.celery_app worker --loglevel=info

from celery import Celery

from elevator_control.infrastructure.config import settings

celery_app = Celery(
    "elevator_control",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    result_expires=3600,
)

# Автообнаружение задач из модуля tasks
celery_app.autodiscover_tasks(["elevator_control.application"])
