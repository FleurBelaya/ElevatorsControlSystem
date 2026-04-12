from fastapi import APIRouter, Query, status

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import LiftSvcDep
from elevator_control.application.emergency_transaction import execute_emergency_demo_transaction
from elevator_control.domain import entities as e
from elevator_control.infrastructure.database import AsyncSessionLocal

router = APIRouter(prefix="/lifts", tags=["lifts"])


def _to_read(lift: e.Lift) -> schemas.LiftRead:
    assert lift.id is not None
    return schemas.LiftRead(
        id=lift.id,
        model=lift.model,
        status=lift.status,
        location=lift.location,
        is_emergency=lift.is_emergency,
    )


@router.get("", response_model=schemas.Paginated)
async def list_lifts(
    svc: LiftSvcDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> schemas.Paginated:
    items, total = await svc.list_page(skip, limit)
    return schemas.Paginated(
        items=[_to_read(x).model_dump() for x in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=schemas.LiftRead, status_code=status.HTTP_201_CREATED)
async def create_lift(svc: LiftSvcDep, body: schemas.LiftCreate) -> schemas.LiftRead:
    created = await svc.create(
        e.Lift(
            id=None,
            model=body.model,
            status=body.status,
            location=body.location,
            is_emergency=body.is_emergency,
        )
    )
    return _to_read(created)


@router.get("/{lift_id}", response_model=schemas.LiftRead)
async def get_lift(svc: LiftSvcDep, lift_id: int) -> schemas.LiftRead:
    return _to_read(await svc.get(lift_id))


@router.patch("/{lift_id}", response_model=schemas.LiftRead)
async def patch_lift(svc: LiftSvcDep, lift_id: int, body: schemas.LiftUpdate) -> schemas.LiftRead:
    data = body.model_dump(exclude_unset=True)
    updated = await svc.update(lift_id, **data)
    return _to_read(updated)


@router.delete("/{lift_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lift(svc: LiftSvcDep, lift_id: int) -> None:
    await svc.delete(lift_id)


@router.post(
    "/{lift_id}/simulate-critical-emergency",
    response_model=schemas.EmergencyDemoResponse,
    summary="Демо: атомарная аварийная транзакция",
    description=(
        "Одна транзакция БД: критическое показание датчика, остановка лифта и флаг аварии, "
        "запись инцидента (critical), автоматическая заявка для диспетчера. "
        "Не использовать в продакшене без авторизации."
    ),
)
async def simulate_critical_emergency(
    lift_id: int,
    body: schemas.EmergencyDemoRequest | None = None,
) -> schemas.EmergencyDemoResponse:
    """
    Отдельная сессия и `async with session.begin()` — один COMMIT на все шаги
    (или полный ROLLBACK при ошибке).
    """
    payload = body or schemas.EmergencyDemoRequest()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await execute_emergency_demo_transaction(
                session,
                lift_id,
                payload.sensor_id,
                payload.note,
            )
    return schemas.EmergencyDemoResponse(
        lift_id=result.lift_id,
        event_id=result.event_id,
        service_request_id=result.service_request_id,
        sensor_id=result.sensor_id,
        sensor_value_after=result.sensor_value_after,
        message=result.message,
    )
