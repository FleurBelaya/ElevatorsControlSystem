from fastapi import APIRouter, Query, status

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import ReportSvcDep
from elevator_control.domain import entities as e

router = APIRouter(prefix="/reports", tags=["reports"])


def _to_read(r: e.Report) -> schemas.ReportRead:
    assert r.id is not None
    assert r.created_at is not None
    return schemas.ReportRead(
        id=r.id,
        service_request_id=r.service_request_id,
        work_description=r.work_description,
        final_lift_status=r.final_lift_status,
        created_at=r.created_at,
    )


@router.get("", response_model=schemas.Paginated)
def list_reports(
    svc: ReportSvcDep,
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


@router.post("", response_model=schemas.ReportRead, status_code=status.HTTP_201_CREATED)
def create_report(svc: ReportSvcDep, body: schemas.ReportCreate) -> schemas.ReportRead:
    created = svc.create(
        e.Report(
            id=None,
            service_request_id=body.service_request_id,
            work_description=body.work_description,
            final_lift_status=body.final_lift_status,
            created_at=None,
        )
    )
    return _to_read(created)


@router.get("/{report_id}", response_model=schemas.ReportRead)
def get_report(svc: ReportSvcDep, report_id: int) -> schemas.ReportRead:
    return _to_read(svc.get(report_id))


@router.patch("/{report_id}", response_model=schemas.ReportRead)
def patch_report(svc: ReportSvcDep, report_id: int, body: schemas.ReportUpdate) -> schemas.ReportRead:
    data = body.model_dump(exclude_unset=True)
    updated = svc.update(report_id, **data)
    return _to_read(updated)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(svc: ReportSvcDep, report_id: int) -> None:
    svc.delete(report_id)
