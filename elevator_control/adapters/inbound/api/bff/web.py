# 4.2 BFF — Web: бэкенд для веб-клиента (SPA). Не вызывает write-сервисы,
# только агрегирует Query-данные под UI веб-дашборда.

import asyncio
import logging

from fastapi import APIRouter

from elevator_control.adapters.inbound.api.bff import schemas as bff_schemas
from elevator_control.adapters.inbound.api.deps import (
    CurrentUserDep,
    EventQueryDep,
    LiftQueryDep,
    ServiceRequestQueryDep,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# 4.2.3 Агрегация данных: один эндпоинт объединяет 3 query-вызова.
@router.get("/dashboard", response_model=bff_schemas.WebDashboardResponse)
async def web_dashboard(
    current_user: CurrentUserDep,
    lift_q: LiftQueryDep,
    event_q: EventQueryDep,
    sr_q: ServiceRequestQueryDep,
) -> bff_schemas.WebDashboardResponse:
    # 4.2.3 Параллельный запуск нескольких query — экономия latency.
    summary, (lifts, _), (events, _), (requests, _) = await asyncio.gather(
        lift_q.heatmap_summary(current_user),
        lift_q.list_page(current_user, 0, 50),
        event_q.list_page(current_user, 0, 10, None, None, None),
        sr_q.list_page(current_user, 0, 10, None, None),
    )

    web_lifts = [
        bff_schemas.WebDashboardLift(
            id=l.id,
            model=l.model,
            status=l.status,
            location=l.location,
            is_emergency=l.is_emergency,
            open_events_count=l.open_events_count,
            open_requests_count=l.open_requests_count,
            sensors_count=l.sensors_count,
            risk_score=min(1.0, l.max_sensor_ratio or 0.0),
        )
        for l in lifts
    ]
    web_events = [
        bff_schemas.WebDashboardEvent(
            id=e.id,
            lift_id=e.lift_id,
            lift_model=e.lift_model,
            event_type=e.event_type,
            description=e.description,
            status=e.status,
        )
        for e in events
    ]
    web_requests = [
        bff_schemas.WebDashboardServiceRequest(
            id=r.id,
            lift_id=r.lift_id,
            lift_model=r.lift_model,
            technician_name=r.technician_name,
            status=r.status,
        )
        for r in requests
    ]
    return bff_schemas.WebDashboardResponse(
        summary=dict(summary),
        lifts=web_lifts,
        recent_events=web_events,
        open_service_requests=web_requests,
    )
