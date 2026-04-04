from fastapi import APIRouter, Query, status

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import TechnicianSvcDep
from elevator_control.domain import entities as e

router = APIRouter(prefix="/technicians", tags=["technicians"])


def _to_read(t: e.Technician) -> schemas.TechnicianRead:
    assert t.id is not None
    return schemas.TechnicianRead(id=t.id, name=t.name, status=t.status)


@router.get("", response_model=schemas.Paginated)
def list_technicians(
    svc: TechnicianSvcDep,
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


@router.post("", response_model=schemas.TechnicianRead, status_code=status.HTTP_201_CREATED)
def create_technician(svc: TechnicianSvcDep, body: schemas.TechnicianCreate) -> schemas.TechnicianRead:
    created = svc.create(e.Technician(id=None, name=body.name, status=body.status))
    return _to_read(created)


@router.get("/{technician_id}", response_model=schemas.TechnicianRead)
def get_technician(svc: TechnicianSvcDep, technician_id: int) -> schemas.TechnicianRead:
    return _to_read(svc.get(technician_id))


@router.patch("/{technician_id}", response_model=schemas.TechnicianRead)
def patch_technician(
    svc: TechnicianSvcDep, technician_id: int, body: schemas.TechnicianUpdate
) -> schemas.TechnicianRead:
    data = body.model_dump(exclude_unset=True)
    updated = svc.update(technician_id, **data)
    return _to_read(updated)


@router.delete("/{technician_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_technician(svc: TechnicianSvcDep, technician_id: int) -> None:
    svc.delete(technician_id)
