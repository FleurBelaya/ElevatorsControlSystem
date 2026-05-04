# 4.2 BFF — Mobile: бэкенд для мобильного клиента. Минимум данных, плоская структура,
# подготовленные для UI строки. Только read-эндпоинты.

import asyncio

from fastapi import APIRouter

from elevator_control.adapters.inbound.api.bff import schemas as bff_schemas
from elevator_control.adapters.inbound.api.deps import (
    CurrentUserDep,
    LiftQueryDep,
    ServiceRequestQueryDep,
)


router = APIRouter()


def _zone_for(ratio: float | None) -> str:
    # Mobile-DTO агрегирует «зону» для иконки светофора.
    r = ratio or 0
    if r > 1.2:
        return "critical"
    if r > 1.0:
        return "warning"
    return "ok"


# 4.2.3 Агрегация: одна страница «лента» мобильного приложения.
@router.get("/feed", response_model=bff_schemas.MobileFeedResponse)
async def mobile_feed(
    current_user: CurrentUserDep,
    lift_q: LiftQueryDep,
    sr_q: ServiceRequestQueryDep,
) -> bff_schemas.MobileFeedResponse:
    # Мобильный клиент видит компактный список с заранее подготовленным title.
    (lifts, _), (requests, _) = await asyncio.gather(
        lift_q.list_page(current_user, 0, 20),
        sr_q.list_page(current_user, 0, 20, None, None),
    )
    cards = [
        bff_schemas.MobileLiftCard(
            id=l.id,
            title=f"{l.model} · {l.location}",
            status=_zone_for(l.max_sensor_ratio),
            badge=l.open_events_count,
        )
        for l in lifts
    ]
    my_tasks = [
        bff_schemas.MobileMyTask(
            request_id=r.id,
            lift_title=f"{r.lift_model} · {r.lift_location}",
            status=r.status,
            reason=r.reason,
        )
        for r in requests
    ]
    return bff_schemas.MobileFeedResponse(lifts=cards, my_tasks=my_tasks)
