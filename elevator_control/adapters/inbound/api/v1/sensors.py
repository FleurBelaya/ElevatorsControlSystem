# 4.1.1 CQRS на уровне HTTP: GET → SensorQueryService (raw SQL),
# POST/PATCH/DELETE → SensorCommandService (ORM + Domain Events).

from fastapi import APIRouter, status

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import (
    CurrentUserDep,
    SensorCmdDep,
    SensorQueryDep,
)
from elevator_control.application.queries.sensor_queries import SensorReadDTO
from elevator_control.domain import entities as e

router = APIRouter(prefix="/lifts", tags=["sensors"])
item_router = APIRouter(prefix="/sensors", tags=["sensors"])


def _read_dto_to_schema(dto: SensorReadDTO) -> schemas.SensorRead:
    # 4.1.2 Read Model → DTO: read-DTO содержит lift_model/ratio/zone, в schema v1 их нет.
    return schemas.SensorRead(
        id=dto.id,
        lift_id=dto.lift_id,
        sensor_type=dto.sensor_type,
        current_value=dto.current_value,
        threshold_norm=dto.threshold_norm,
    )


def _entity_to_schema(s: e.Sensor) -> schemas.SensorRead:
    assert s.id is not None
    return schemas.SensorRead(
        id=s.id,
        lift_id=s.lift_id,
        sensor_type=s.sensor_type,
        current_value=s.current_value,
        threshold_norm=s.threshold_norm,
    )


# 4.1.1 CQRS Query side
@router.get("/{lift_id}/sensors", response_model=list[schemas.SensorRead])
async def list_sensors(
    qsvc: SensorQueryDep, current_user: CurrentUserDep, lift_id: int
) -> list[schemas.SensorRead]:
    items = await qsvc.list_for_lift(current_user, lift_id)
    return [_read_dto_to_schema(x) for x in items]


# 4.1.1 CQRS Command side
@router.post(
    "/{lift_id}/sensors",
    response_model=schemas.SensorRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_sensor(
    csvc: SensorCmdDep,
    current_user: CurrentUserDep,
    lift_id: int,
    body: schemas.SensorCreate,
) -> schemas.SensorRead:
    # 6.1.2 Mass Assignment: в SensorCreate нет owner_id/id, owner вычисляется из лифта-владельца.
    created = await csvc.create(
        current_user,
        e.Sensor(
            id=None,
            owner_id=current_user.id,
            lift_id=lift_id,
            sensor_type=body.sensor_type,
            current_value=body.current_value,
            threshold_norm=body.threshold_norm,
        ),
    )
    return _entity_to_schema(created)


# 4.1.1 CQRS Query side
@item_router.get("/{sensor_id}", response_model=schemas.SensorRead)
async def get_sensor(
    qsvc: SensorQueryDep, current_user: CurrentUserDep, sensor_id: int
) -> schemas.SensorRead:
    return _read_dto_to_schema(await qsvc.get_by_id(current_user, sensor_id))


# 4.1.1 CQRS Command side
@item_router.patch("/{sensor_id}", response_model=schemas.SensorRead)
async def patch_sensor(
    csvc: SensorCmdDep,
    current_user: CurrentUserDep,
    sensor_id: int,
    body: schemas.SensorUpdate,
) -> schemas.SensorRead:
    data = body.model_dump(exclude_unset=True)
    updated = await csvc.update(current_user, sensor_id, **data)
    return _entity_to_schema(updated)


# 4.1.1 CQRS Command side
@item_router.delete("/{sensor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sensor(
    csvc: SensorCmdDep, current_user: CurrentUserDep, sensor_id: int
) -> None:
    await csvc.delete(current_user, sensor_id)
