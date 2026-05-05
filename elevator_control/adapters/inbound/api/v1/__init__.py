from fastapi import APIRouter

from elevator_control.adapters.inbound.api.v1 import (
    auth,
    control,
    events,
    lifts,
    reports,
    sensors,
    service_requests,
    tasks,
    technicians,
)

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
# КРИТИЧНО: control должен быть ДО lifts, иначе /lifts/panels попадает в /lifts/{lift_id}.
api_v1_router.include_router(control.router)
api_v1_router.include_router(lifts.router)
api_v1_router.include_router(sensors.router)
api_v1_router.include_router(sensors.item_router)
api_v1_router.include_router(events.router)
api_v1_router.include_router(service_requests.router)
api_v1_router.include_router(technicians.router)
api_v1_router.include_router(reports.router)
# 2.5 - Фоновые задачи: роутер для управления задачами через очередь
api_v1_router.include_router(tasks.router)
