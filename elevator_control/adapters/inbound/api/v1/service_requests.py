# 4.1.1 CQRS на уровне HTTP: GET → ServiceRequestQueryService, write → CommandService.

from fastapi import APIRouter, Query, status

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import (
    CurrentUserDep,
    ServiceRequestCmdDep,
    ServiceRequestQueryDep,
)
from elevator_control.application.queries.service_request_queries import ServiceRequestReadDTO
from elevator_control.domain import entities as e
from elevator_control.domain.enums import ServiceRequestStatus

router = APIRouter(prefix="/service-requests", tags=["service-requests"])


def _read_dto_to_schema(dto: ServiceRequestReadDTO) -> schemas.ServiceRequestRead:
    return schemas.ServiceRequestRead(
        id=dto.id,
        lift_id=dto.lift_id,
        reason=dto.reason,
        status=ServiceRequestStatus(dto.status),
        technician_id=dto.technician_id,
    )


def _entity_to_schema(req: e.ServiceRequest) -> schemas.ServiceRequestRead:
    assert req.id is not None
    return schemas.ServiceRequestRead(
        id=req.id,
        lift_id=req.lift_id,
        reason=req.reason,
        status=req.status,
        technician_id=req.technician_id,
    )


# 4.1.1 CQRS Query side
@router.get("", response_model=schemas.Paginated)
async def list_service_requests(
    qsvc: ServiceRequestQueryDep,
    current_user: CurrentUserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    lift_id: int | None = None,
    status_filter: ServiceRequestStatus | None = Query(None, alias="status"),
) -> schemas.Paginated:
    items, total = await qsvc.list_page(current_user, skip, limit, lift_id, status_filter)
    return schemas.Paginated(
        items=[_read_dto_to_schema(x).model_dump() for x in items],
        total=total,
        skip=skip,
        limit=limit,
    )


# 4.1.1 CQRS Command side
@router.post("", response_model=schemas.ServiceRequestRead, status_code=status.HTTP_201_CREATED)
async def create_service_request(
    csvc: ServiceRequestCmdDep,
    current_user: CurrentUserDep,
    body: schemas.ServiceRequestCreate,
) -> schemas.ServiceRequestRead:
    created = await csvc.create(
        current_user,
        e.ServiceRequest(
            id=None,
            owner_id=current_user.id,
            lift_id=body.lift_id,
            reason=body.reason,
            status=body.status,
            technician_id=body.technician_id,
        ),
    )
    return _entity_to_schema(created)


# 4.1.1 CQRS Query side
@router.get("/{request_id}", response_model=schemas.ServiceRequestRead)
async def get_service_request(
    qsvc: ServiceRequestQueryDep, current_user: CurrentUserDep, request_id: int
) -> schemas.ServiceRequestRead:
    return _read_dto_to_schema(await qsvc.get_by_id(current_user, request_id))


# 4.1.1 CQRS Command side
@router.patch("/{request_id}", response_model=schemas.ServiceRequestRead)
async def patch_service_request(
    csvc: ServiceRequestCmdDep,
    current_user: CurrentUserDep,
    request_id: int,
    body: schemas.ServiceRequestUpdate,
) -> schemas.ServiceRequestRead:
    data = body.model_dump(exclude_unset=True)
    updated = await csvc.update(current_user, request_id, **data)
    return _entity_to_schema(updated)


# 4.1.1 CQRS Command side
@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_request(
    csvc: ServiceRequestCmdDep, current_user: CurrentUserDep, request_id: int
) -> None:
    await csvc.delete(current_user, request_id)
