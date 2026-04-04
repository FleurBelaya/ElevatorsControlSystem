from fastapi import APIRouter, Query, status

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import LiftSvcDep
from elevator_control.domain import entities as e
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
def list_lifts(
    svc: LiftSvcDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> schemas.Paginated:
    items, total = svc.list_page(skip, limit)
    return schemas.Paginated(
        items=[_to_read(x).model_dump() for x in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=schemas.LiftRead, status_code=status.HTTP_201_CREATED)
def create_lift(svc: LiftSvcDep, body: schemas.LiftCreate) -> schemas.LiftRead:
    created = svc.create(
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
def get_lift(svc: LiftSvcDep, lift_id: int) -> schemas.LiftRead:
    return _to_read(svc.get(lift_id))


@router.patch("/{lift_id}", response_model=schemas.LiftRead)
def patch_lift(svc: LiftSvcDep, lift_id: int, body: schemas.LiftUpdate) -> schemas.LiftRead:
    data = body.model_dump(exclude_unset=True)
    updated = svc.update(lift_id, **data)
    return _to_read(updated)


@router.delete("/{lift_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lift(svc: LiftSvcDep, lift_id: int) -> None:
    svc.delete(lift_id)
