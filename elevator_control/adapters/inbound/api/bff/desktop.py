# 4.2 BFF — Desktop: бэкенд для десктопного клиента (pywebview). Богатый ответ
# «рабочее место по лифту» — всё, что нужно для одной страницы, в одном запросе.

import asyncio

from fastapi import APIRouter

from elevator_control.adapters.inbound.api.bff import schemas as bff_schemas
from elevator_control.adapters.inbound.api.deps import (
    CurrentUserDep,
    EventQueryDep,
    LiftQueryDep,
    SensorQueryDep,
    ServiceRequestQueryDep,
)


router = APIRouter()


# 4.2.3 Агрегация данных: один запрос → 4 query-вызова, объединённые в один JSON.
@router.get("/lift-workbench/{lift_id}", response_model=bff_schemas.DesktopLiftWorkbench)
async def desktop_lift_workbench(
    lift_id: int,
    current_user: CurrentUserDep,
    lift_q: LiftQueryDep,
    sensor_q: SensorQueryDep,
    event_q: EventQueryDep,
    sr_q: ServiceRequestQueryDep,
) -> bff_schemas.DesktopLiftWorkbench:
    lift, sensors, (events, _), (requests, _) = await asyncio.gather(
        lift_q.get_by_id(current_user, lift_id),
        sensor_q.list_for_lift(current_user, lift_id),
        event_q.list_page(current_user, 0, 20, lift_id, None, None),
        sr_q.list_page(current_user, 0, 20, lift_id, None),
    )

    return bff_schemas.DesktopLiftWorkbench(
        lift={
            "id": lift.id,
            "model": lift.model,
            "status": lift.status,
            "location": lift.location,
            "is_emergency": lift.is_emergency,
            "open_events_count": lift.open_events_count,
            "open_requests_count": lift.open_requests_count,
            "sensors_count": lift.sensors_count,
            "max_sensor_ratio": lift.max_sensor_ratio,
        },
        sensors=[
            bff_schemas.DesktopSensor(
                id=s.id,
                sensor_type=s.sensor_type,
                current_value=s.current_value,
                threshold_norm=s.threshold_norm,
                ratio=s.ratio,
                zone=s.zone,
            )
            for s in sensors
        ],
        events=[
            bff_schemas.DesktopEvent(
                id=e.id,
                event_type=e.event_type,
                description=e.description,
                status=e.status,
                created_at=e.created_at,
            )
            for e in events
        ],
        service_requests=[
            bff_schemas.DesktopServiceRequest(
                id=r.id,
                reason=r.reason,
                status=r.status,
                technician_name=r.technician_name,
            )
            for r in requests
        ],
    )
