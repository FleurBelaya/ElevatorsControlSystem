# 4.1.1 CQRS на уровне HTTP: GET-эндпоинты идут в LiftQueryService (raw SQL),
# а POST/PATCH/DELETE — в LiftCommandService (ORM + публикация Domain Events).
# Один URL может иметь GET и POST, но обработчики строго разделены и работают
# с разными моделями данных (lifts vs lifts_read).

from fastapi import APIRouter, Query, status

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import (
    AuthorizationDep,
    CurrentUserDep,
    LiftCmdDep,
    LiftQueryDep,
    SessionDep,
)
from elevator_control.application import cache as query_cache
from elevator_control.application.emergency_transaction import execute_emergency_demo_transaction
from elevator_control.application.queries.lift_queries import LiftReadDTO
from elevator_control.domain import entities as e
from elevator_control.domain.enums import LiftStatus

router = APIRouter(prefix="/lifts", tags=["lifts"])


def _read_dto_to_schema(dto: LiftReadDTO) -> schemas.LiftRead:
    # 4.1.2 Read Model → DTO для API. Read-модель содержит больше полей (агрегаты),
    # но клиенту v1 отдаём legacy-поля, чтобы не ломать совместимость с веб-клиентом.
    return schemas.LiftRead(
        id=dto.id,
        model=dto.model,
        status=LiftStatus(dto.status),
        location=dto.location,
        is_emergency=dto.is_emergency,
    )


def _sensor_entity_to_schema(s: e.Sensor) -> schemas.SensorRead:
    assert s.id is not None
    return schemas.SensorRead(
        id=s.id,
        lift_id=s.lift_id,
        sensor_type=s.sensor_type,
        current_value=s.current_value,
        threshold_norm=s.threshold_norm,
    )


def _entity_to_legacy(lift: e.Lift) -> schemas.LiftRead:
    assert lift.id is not None
    return schemas.LiftRead(
        id=lift.id,
        model=lift.model,
        status=lift.status,
        location=lift.location,
        is_emergency=lift.is_emergency,
    )


# 4.1.1 CQRS Query side
@router.get("", response_model=schemas.Paginated)
async def list_lifts(
    qsvc: LiftQueryDep,
    current_user: CurrentUserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> schemas.Paginated:
    # 5.2.3 Кэш: первый ключ — список лифтов с пагинацией для текущего юзера.
    cache_key = f"lifts:list:user={current_user.id}:skip={skip}:limit={limit}"
    cached = await query_cache.get(cache_key)
    if cached is not None:
        return cached
    items, total = await qsvc.list_page(current_user, skip, limit)
    # 4.1.2 Read Model: items уже содержат денормализацию (sensors_count, etc.)
    response = schemas.Paginated(
        items=[_read_dto_to_schema(x).model_dump() for x in items],
        total=total,
        skip=skip,
        limit=limit,
    )
    await query_cache.put(cache_key, response, tags=["lift"])
    return response


# 4.1.1 CQRS Query side
@router.get("/heatmap", response_model=dict)
async def lifts_heatmap(qsvc: LiftQueryDep, current_user: CurrentUserDep) -> dict:
    # 5.2.1 Тепловая карта: агрегированный read-эндпоинт для дашборда.
    return await qsvc.heatmap_summary(current_user)


# 4.1.1 CQRS Query side
@router.get("/{lift_id}", response_model=schemas.LiftRead)
async def get_lift(
    qsvc: LiftQueryDep, current_user: CurrentUserDep, lift_id: int
) -> schemas.LiftRead:
    dto = await qsvc.get_by_id(current_user, lift_id)
    return _read_dto_to_schema(dto)


# 4.1.1 CQRS Command side
@router.post("", response_model=schemas.LiftRead, status_code=status.HTTP_201_CREATED)
async def create_lift(
    csvc: LiftCmdDep, current_user: CurrentUserDep, body: schemas.LiftCreate
) -> schemas.LiftRead:
    # 6.1.2 Mass Assignment: модель LiftCreate НЕ содержит owner_id — он берётся из токена.
    created = await csvc.create(
        current_user,
        e.Lift(
            id=None,
            owner_id=current_user.id,
            model=body.model,
            status=body.status,
            location=body.location,
            is_emergency=body.is_emergency,
        ),
    )
    return _entity_to_legacy(created)


# 4.1.1 CQRS Command side
@router.patch("/{lift_id}", response_model=schemas.LiftRead)
async def patch_lift(
    csvc: LiftCmdDep,
    current_user: CurrentUserDep,
    lift_id: int,
    body: schemas.LiftUpdate,
) -> schemas.LiftRead:
    # 6.1.2 LiftUpdate тоже не содержит owner_id/id — Mass Assignment блокируется на уровне DTO.
    data = body.model_dump(exclude_unset=True)
    updated = await csvc.update(current_user, lift_id, **data)
    return _entity_to_legacy(updated)


# 4.1.1 CQRS Command side
@router.delete("/{lift_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lift(csvc: LiftCmdDep, current_user: CurrentUserDep, lift_id: int) -> None:
    await csvc.delete(current_user, lift_id)


# 4.1.1 CQRS Command side
@router.post(
    "/{lift_id}/restore-state",
    response_model=schemas.LiftRestoreStateResponse,
    summary="Восстановить состояние лифта и датчиков",
)
async def restore_lift_state(
    csvc: LiftCmdDep,
    current_user: CurrentUserDep,
    lift_id: int,
    body: schemas.LiftRestoreStateRequest | None = None,
) -> schemas.LiftRestoreStateResponse:
    payload = body or schemas.LiftRestoreStateRequest()
    lift, sensors = await csvc.restore_operational_state(
        current_user,
        lift_id,
        target_status=payload.target_status,
        reset_sensors=payload.reset_sensors,
    )
    return schemas.LiftRestoreStateResponse(
        lift=_entity_to_legacy(lift),
        sensors=[_sensor_entity_to_schema(s) for s in sensors],
    )


# 4.1.1 CQRS Command side (с собственной транзакцией)
@router.post(
    "/{lift_id}/simulate-critical-emergency",
    response_model=schemas.EmergencyDemoResponse,
    summary="Демо: атомарная аварийная транзакция",
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
    # 5.2.3 Кэш: после ручной командной транзакции форсируем инвалидацию связанных read-ключей.
    await query_cache.invalidate_for_aggregate("lift")
    return schemas.EmergencyDemoResponse(
        lift_id=result.lift_id,
        event_id=result.event_id,
        service_request_id=result.service_request_id,
        sensor_id=result.sensor_id,
        sensor_value_after=result.sensor_value_after,
        message=result.message,
    )
