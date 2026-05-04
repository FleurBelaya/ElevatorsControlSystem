# 4.1.1 CQRS на уровне HTTP: GET → ReportQueryService, write → CommandService.

from fastapi import APIRouter, Query, status

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import (
    CurrentUserDep,
    ReportCmdDep,
    ReportQueryDep,
)
from elevator_control.application.queries.report_queries import ReportReadDTO
from elevator_control.domain import entities as e
from elevator_control.domain.enums import LiftStatus

router = APIRouter(prefix="/reports", tags=["reports"])


def _read_dto_to_schema(dto: ReportReadDTO) -> schemas.ReportRead:
    return schemas.ReportRead(
        id=dto.id,
        service_request_id=dto.service_request_id,
        work_description=dto.work_description,
        final_lift_status=LiftStatus(dto.final_lift_status),
        created_at=dto.created_at,
    )


def _entity_to_schema(r: e.Report) -> schemas.ReportRead:
    assert r.id is not None
    assert r.created_at is not None
    return schemas.ReportRead(
        id=r.id,
        service_request_id=r.service_request_id,
        work_description=r.work_description,
        final_lift_status=r.final_lift_status,
        created_at=r.created_at,
    )


# 4.1.1 CQRS Query side
@router.get("", response_model=schemas.Paginated)
async def list_reports(
    qsvc: ReportQueryDep,
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
@router.post("", response_model=schemas.ReportRead, status_code=status.HTTP_201_CREATED)
async def create_report(
    csvc: ReportCmdDep, current_user: CurrentUserDep, body: schemas.ReportCreate
) -> schemas.ReportRead:
    created = await csvc.create(
        current_user,
        e.Report(
            id=None,
            owner_id=current_user.id,
            service_request_id=body.service_request_id,
            work_description=body.work_description,
            final_lift_status=body.final_lift_status,
            created_at=None,
        ),
    )
    return _entity_to_schema(created)


# 4.1.1 CQRS Query side
@router.get("/{report_id}", response_model=schemas.ReportRead)
async def get_report(
    qsvc: ReportQueryDep, current_user: CurrentUserDep, report_id: int
) -> schemas.ReportRead:
    return _read_dto_to_schema(await qsvc.get_by_id(current_user, report_id))


# 4.1.1 CQRS Command side
@router.patch("/{report_id}", response_model=schemas.ReportRead)
async def patch_report(
    csvc: ReportCmdDep,
    current_user: CurrentUserDep,
    report_id: int,
    body: schemas.ReportUpdate,
) -> schemas.ReportRead:
    data = body.model_dump(exclude_unset=True)
    updated = await csvc.update(current_user, report_id, **data)
    return _entity_to_schema(updated)


# 4.1.1 CQRS Command side
@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    csvc: ReportCmdDep, current_user: CurrentUserDep, report_id: int
) -> None:
    await csvc.delete(current_user, report_id)
