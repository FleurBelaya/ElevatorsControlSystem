# 2.5.1 - Выделение фоновой задачи: генерация диагностического отчёта по лифту.
# Операция занимает время (сбор данных, анализ датчиков, формирование текста),
# поэтому выполняется в фоне через очередь, а API возвращает мгновенный ответ.
#
# 2.5.2 - Интеграция очереди: задачи выполняются через Celery + Redis (broker + backend).
# Архитектура: API → Redis (очередь) → Celery Worker (исполнитель).
#
# 2.5.3 - Статус задачи: Celery отслеживает PENDING → STARTED → SUCCESS/FAILURE.
# Статус доступен через endpoint GET /api/v1/tasks/{task_id}/status.
#
# 2.6 - Отложенная задача: delayed_lift_status_check выполняется через 10 секунд
# после постановки в очередь (countdown=10).

import logging
import time

from elevator_control.infrastructure.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="generate_diagnostic_report")
def generate_diagnostic_report(self, lift_id: int, user_id: int) -> dict:
    """2.5.1 - Фоновая задача: генерация диагностического отчёта по лифту.

    Эта операция имитирует долгую работу (сбор и анализ данных с датчиков,
    формирование текстового отчёта). API не ждёт выполнения — возвращает
    task_id для отслеживания статуса.
    """
    # 2.5.3 - Обновляем мета-данные задачи для отслеживания прогресса
    self.update_state(state="STARTED", meta={"progress": 0, "step": "Инициализация"})
    logger.info("Начало генерации диагностического отчёта для лифта id=%s, пользователь id=%s", lift_id, user_id)

    # Шаг 1: Сбор данных с датчиков (имитация длительной операции)
    self.update_state(state="PROGRESS", meta={"progress": 25, "step": "Сбор данных с датчиков"})
    time.sleep(3)

    # Шаг 2: Анализ показаний
    self.update_state(state="PROGRESS", meta={"progress": 50, "step": "Анализ показаний датчиков"})
    time.sleep(2)

    # Шаг 3: Формирование отчёта
    self.update_state(state="PROGRESS", meta={"progress": 75, "step": "Формирование отчёта"})
    time.sleep(2)

    # Шаг 4: Завершение
    report_data = {
        "lift_id": lift_id,
        "user_id": user_id,
        "status": "completed",
        "summary": f"Диагностический отчёт по лифту #{lift_id} успешно сгенерирован.",
        "details": {
            "sensors_checked": True,
            "anomalies_detected": False,
            "recommendation": "Лифт в рабочем состоянии. Плановое ТО через 30 дней.",
        },
    }

    logger.info("Диагностический отчёт для лифта id=%s готов", lift_id)
    return report_data


@celery_app.task(bind=True, name="delayed_lift_status_check")
def delayed_lift_status_check(self, lift_id: int) -> dict:
    """2.6 - Отложенная задача: проверка статуса лифта через 10 секунд.

    Задача ставится в очередь с countdown=10 (задержка 10 секунд).
    Используется, например, для отложенной проверки после восстановления лифта,
    чтобы убедиться, что показания датчиков стабилизировались.
    """
    logger.info("Отложенная проверка статуса лифта id=%s (запущена после задержки 10 сек)", lift_id)

    self.update_state(state="STARTED", meta={"step": "Проверка статуса лифта после задержки"})
    time.sleep(1)

    result = {
        "lift_id": lift_id,
        "status": "completed",
        "message": f"Отложенная проверка лифта #{lift_id} выполнена. Статус стабилен.",
        "delayed_seconds": 10,
    }

    logger.info("Отложенная проверка лифта id=%s завершена", lift_id)
    return result
