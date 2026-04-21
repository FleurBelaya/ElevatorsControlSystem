from fastapi import APIRouter

from elevator_control.adapters.inbound.api.v1 import (
    auth,
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
api_v1_router.include_router(lifts.router)
api_v1_router.include_router(sensors.router)
api_v1_router.include_router(sensors.item_router)
api_v1_router.include_router(events.router)
api_v1_router.include_router(service_requests.router)
api_v1_router.include_router(technicians.router)
api_v1_router.include_router(reports.router)
# 2.5 - Фоновые задачи: роутер для управления задачами через очередь
api_v1_router.include_router(tasks.router)
