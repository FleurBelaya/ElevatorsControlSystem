from fastapi import APIRouter, status

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import SensorSvcDep
from elevator_control.domain import entities as e

router = APIRouter(prefix="/lifts", tags=["sensors"])
item_router = APIRouter(prefix="/sensors", tags=["sensors"])


def _to_read(s: e.Sensor) -> schemas.SensorRead:
    assert s.id is not None
    return schemas.SensorRead(
        id=s.id,
        lift_id=s.lift_id,
        sensor_type=s.sensor_type,
        current_value=s.current_value,
        threshold_norm=s.threshold_norm,
    )


@router.get("/{lift_id}/sensors", response_model=list[schemas.SensorRead])
def list_sensors(svc: SensorSvcDep, lift_id: int) -> list[schemas.SensorRead]:
    return [_to_read(x) for x in svc.list_for_lift(lift_id)]


@router.post(
    "/{lift_id}/sensors",
    response_model=schemas.SensorRead,
    status_code=status.HTTP_201_CREATED,
)
def create_sensor(svc: SensorSvcDep, lift_id: int, body: schemas.SensorCreate) -> schemas.SensorRead:
    created = svc.create(
        e.Sensor(
            id=None,
            lift_id=lift_id,
            sensor_type=body.sensor_type,
            current_value=body.current_value,
            threshold_norm=body.threshold_norm,
        )
    )
    return _to_read(created)


@item_router.get("/{sensor_id}", response_model=schemas.SensorRead)
def get_sensor(svc: SensorSvcDep, sensor_id: int) -> schemas.SensorRead:
    return _to_read(svc.get(sensor_id))


@item_router.patch("/{sensor_id}", response_model=schemas.SensorRead)
def patch_sensor(svc: SensorSvcDep, sensor_id: int, body: schemas.SensorUpdate) -> schemas.SensorRead:
    data = body.model_dump(exclude_unset=True)
    updated = svc.update(sensor_id, **data)
    return _to_read(updated)


@item_router.delete("/{sensor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sensor(svc: SensorSvcDep, sensor_id: int) -> None:
    svc.delete(sensor_id)
