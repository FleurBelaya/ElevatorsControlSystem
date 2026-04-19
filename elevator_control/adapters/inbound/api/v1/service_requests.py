from fastapi import APIRouter, Query, status

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import CurrentUserDep, ServiceRequestSvcDep
from elevator_control.domain import entities as e
from elevator_control.domain.enums import ServiceRequestStatus

router = APIRouter(prefix="/service-requests", tags=["service-requests"])


def _to_read(req: e.ServiceRequest) -> schemas.ServiceRequestRead:
    assert req.id is not None
    return schemas.ServiceRequestRead(
        id=req.id,
        lift_id=req.lift_id,
        reason=req.reason,
        status=req.status,
        technician_id=req.technician_id,
    )


@router.get("", response_model=schemas.Paginated)
async def list_service_requests(
    svc: ServiceRequestSvcDep,
    current_user: CurrentUserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    lift_id: int | None = None,
    status_filter: ServiceRequestStatus | None = Query(None, alias="status"),
) -> schemas.Paginated:
    items, total = await svc.list_page(current_user, skip, limit, lift_id, status_filter)
    return schemas.Paginated(
        items=[_to_read(x).model_dump() for x in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=schemas.ServiceRequestRead, status_code=status.HTTP_201_CREATED)
async def create_service_request(
    svc: ServiceRequestSvcDep, current_user: CurrentUserDep, body: schemas.ServiceRequestCreate
) -> schemas.ServiceRequestRead:
    created = await svc.create(
        current_user,
        e.ServiceRequest(
            id=None,
            owner_id=current_user.id,
            lift_id=body.lift_id,
            reason=body.reason,
            status=body.status,
            technician_id=body.technician_id,
        )
    )
    return _to_read(created)


@router.get("/{request_id}", response_model=schemas.ServiceRequestRead)
async def get_service_request(
    svc: ServiceRequestSvcDep, current_user: CurrentUserDep, request_id: int
) -> schemas.ServiceRequestRead:
    return _to_read(await svc.get(current_user, request_id))


@router.patch("/{request_id}", response_model=schemas.ServiceRequestRead)
async def patch_service_request(
    svc: ServiceRequestSvcDep, current_user: CurrentUserDep, request_id: int, body: schemas.ServiceRequestUpdate
) -> schemas.ServiceRequestRead:
    data = body.model_dump(exclude_unset=True)
    updated = await svc.update(current_user, request_id, **data)
    return _to_read(updated)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_request(
    svc: ServiceRequestSvcDep, current_user: CurrentUserDep, request_id: int
) -> None:
    await svc.delete(current_user, request_id)
