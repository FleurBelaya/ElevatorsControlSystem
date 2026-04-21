# 2.5.2 - Интеграция очереди: конфигурация Celery.
# По умолчанию используется файловый брокер (filesystem://) и SQLite для результатов —
# это работает без установки Redis/RabbitMQ (достаточно pip install celery).
# Для продакшена можно переключить на Redis через переменные окружения в .env.
#
# Архитектура: API (FastAPI) → Queue (filesystem/Redis) → Worker (Celery).
# Запуск воркера: celery -A elevator_control.infrastructure.celery_app worker --loglevel=info --pool=solo

import os

from celery import Celery

from elevator_control.infrastructure.config import settings

celery_app = Celery(
    "elevator_control",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# 2.5.2 - Настройка файлового брокера (создаём директории для очередей)
if settings.celery_broker_url.startswith("filesystem://"):
    broker_folder = os.path.join(os.getcwd(), "celery_broker")
    os.makedirs(os.path.join(broker_folder, "out"), exist_ok=True)
    os.makedirs(os.path.join(broker_folder, "processed"), exist_ok=True)
    celery_app.conf.broker_transport_options = {
        "data_folder_in": os.path.join(broker_folder, "out"),
        "data_folder_out": os.path.join(broker_folder, "out"),
        "data_folder_processed": os.path.join(broker_folder, "processed"),
    }

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
