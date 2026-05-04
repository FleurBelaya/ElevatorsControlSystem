# 4.1.1 CQRS на уровне HTTP: GET → TechnicianQueryService, write → CommandService.

from fastapi import APIRouter, Query, status

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import (
    CurrentUserDep,
    TechnicianCmdDep,
    TechnicianQueryDep,
)
from elevator_control.application.queries.technician_queries import TechnicianReadDTO
from elevator_control.domain import entities as e
from elevator_control.domain.enums import TechnicianStatus

router = APIRouter(prefix="/technicians", tags=["technicians"])


def _read_dto_to_schema(dto: TechnicianReadDTO) -> schemas.TechnicianRead:
    return schemas.TechnicianRead(id=dto.id, name=dto.name, status=TechnicianStatus(dto.status))


def _entity_to_schema(t: e.Technician) -> schemas.TechnicianRead:
    assert t.id is not None
    return schemas.TechnicianRead(id=t.id, name=t.name, status=t.status)


# 4.1.1 CQRS Query side
@router.get("", response_model=schemas.Paginated)
async def list_technicians(
    qsvc: TechnicianQueryDep,
    current_user: CurrentUserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> schemas.Paginated:
    items, total = await qsvc.list_page(current_user, skip, limit)
    return schemas.Paginated(
        items=[_read_dto_to_schema(x).model_dump() for x in items],
        total=total,
        skip=skip,
        limit=limit,
    )


# 4.1.1 CQRS Command side
@router.post("", response_model=schemas.TechnicianRead, status_code=status.HTTP_201_CREATED)
async def create_technician(
    csvc: TechnicianCmdDep,
    current_user: CurrentUserDep,
    body: schemas.TechnicianCreate,
) -> schemas.TechnicianRead:
    created = await csvc.create(
        current_user,
        e.Technician(id=None, owner_id=current_user.id, name=body.name, status=body.status),
    )
    return _entity_to_schema(created)


# 4.1.1 CQRS Query side
@router.get("/{technician_id}", response_model=schemas.TechnicianRead)
async def get_technician(
    qsvc: TechnicianQueryDep, current_user: CurrentUserDep, technician_id: int
) -> schemas.TechnicianRead:
    return _read_dto_to_schema(await qsvc.get_by_id(current_user, technician_id))


# 4.1.1 CQRS Command side
@router.patch("/{technician_id}", response_model=schemas.TechnicianRead)
async def patch_technician(
    csvc: TechnicianCmdDep,
    current_user: CurrentUserDep,
    technician_id: int,
    body: schemas.TechnicianUpdate,
) -> schemas.TechnicianRead:
    data = body.model_dump(exclude_unset=True)
    updated = await csvc.update(current_user, technician_id, **data)
    return _entity_to_schema(updated)


# 4.1.1 CQRS Command side
@router.delete("/{technician_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_technician(
    csvc: TechnicianCmdDep, current_user: CurrentUserDep, technician_id: int
) -> None:
    await csvc.delete(current_user, technician_id)
