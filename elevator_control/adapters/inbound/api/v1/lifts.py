from fastapi import APIRouter, Query, status

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import AuthorizationDep, CurrentUserDep, LiftSvcDep
from elevator_control.application.emergency_transaction import execute_emergency_demo_transaction
from elevator_control.domain import entities as e
from elevator_control.adapters.inbound.api.deps import SessionDep

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


def _sensor_to_read(s: e.Sensor) -> schemas.SensorRead:
    assert s.id is not None
    return schemas.SensorRead(
        id=s.id,
        lift_id=s.lift_id,
        sensor_type=s.sensor_type,
        current_value=s.current_value,
        threshold_norm=s.threshold_norm,
    )


@router.get("", response_model=schemas.Paginated)
async def list_lifts(
    svc: LiftSvcDep,
    current_user: CurrentUserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> schemas.Paginated:
    items, total = await svc.list_page(current_user, skip, limit)
    return schemas.Paginated(
        items=[_to_read(x).model_dump() for x in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=schemas.LiftRead, status_code=status.HTTP_201_CREATED)
async def create_lift(svc: LiftSvcDep, current_user: CurrentUserDep, body: schemas.LiftCreate) -> schemas.LiftRead:
    created = await svc.create(
        current_user,
        e.Lift(
            id=None,
            owner_id=current_user.id,
            model=body.model,
            status=body.status,
            location=body.location,
            is_emergency=body.is_emergency,
        )
    )
    return _to_read(created)


@router.get("/{lift_id}", response_model=schemas.LiftRead)
async def get_lift(svc: LiftSvcDep, current_user: CurrentUserDep, lift_id: int) -> schemas.LiftRead:
    return _to_read(await svc.get(current_user, lift_id))


@router.patch("/{lift_id}", response_model=schemas.LiftRead)
async def patch_lift(
    svc: LiftSvcDep, current_user: CurrentUserDep, lift_id: int, body: schemas.LiftUpdate
) -> schemas.LiftRead:
    data = body.model_dump(exclude_unset=True)
    updated = await svc.update(current_user, lift_id, **data)
    return _to_read(updated)


@router.delete("/{lift_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lift(svc: LiftSvcDep, current_user: CurrentUserDep, lift_id: int) -> None:
    await svc.delete(current_user, lift_id)


@router.post(
    "/{lift_id}/restore-state",
    response_model=schemas.LiftRestoreStateResponse,
    summary="Восстановить состояние лифта и датчиков",
    description=(
        "Сбрасывает аварию (is_emergency=false), выставляет целевой статус лифта (по умолчанию active), "
        "опционально приводит показания всех датчиков лифта в безопасную зону ниже порога."
    ),
)
async def restore_lift_state(
    svc: LiftSvcDep,
    current_user: CurrentUserDep,
    lift_id: int,
    body: schemas.LiftRestoreStateRequest | None = None,
) -> schemas.LiftRestoreStateResponse:
    payload = body or schemas.LiftRestoreStateRequest()
    lift, sensors = await svc.restore_operational_state(
        current_user,
        lift_id,
        target_status=payload.target_status,
        reset_sensors=payload.reset_sensors,
    )
    return schemas.LiftRestoreStateResponse(
        lift=_to_read(lift),
        sensors=[_sensor_to_read(s) for s in sensors],
    )


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
    session: SessionDep,
    current_user: CurrentUserDep,
    authz: AuthorizationDep,
    lift_id: int,
    body: schemas.EmergencyDemoRequest | None = None,
) -> schemas.EmergencyDemoResponse:
    """Один COMMIT на все шаги (или полный ROLLBACK при ошибке)."""
    payload = body or schemas.EmergencyDemoRequest()
    async with session.begin():
        result = await execute_emergency_demo_transaction(
            session,
            authz,
            current_user,
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
