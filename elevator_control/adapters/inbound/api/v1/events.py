from fastapi import APIRouter, Query, status

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import CurrentUserDep, EventSvcDep
from elevator_control.domain import entities as e
from elevator_control.domain.enums import EventStatus, EventType

router = APIRouter(prefix="/events", tags=["events"])


def _to_read(ev: e.Event) -> schemas.EventRead:
    assert ev.id is not None
    return schemas.EventRead(
        id=ev.id,
        lift_id=ev.lift_id,
        event_type=ev.event_type,
        description=ev.description,
        status=ev.status,
    )


@router.get("", response_model=schemas.Paginated)
async def list_events(
    svc: EventSvcDep,
    current_user: CurrentUserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    lift_id: int | None = None,
    status_filter: EventStatus | None = Query(None, alias="status"),
    event_type: EventType | None = None,
) -> schemas.Paginated:
    items, total = await svc.list_page(current_user, skip, limit, lift_id, status_filter, event_type)
    return schemas.Paginated(
        items=[_to_read(x).model_dump() for x in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=schemas.EventRead, status_code=status.HTTP_201_CREATED)
async def create_event(svc: EventSvcDep, current_user: CurrentUserDep, body: schemas.EventCreate) -> schemas.EventRead:
    created = await svc.create(
        current_user,
        e.Event(
            id=None,
            owner_id=current_user.id,
            lift_id=body.lift_id,
            event_type=body.event_type,
            description=body.description,
            status=body.status,
        )
    )
    return _to_read(created)


@router.get("/{event_id}", response_model=schemas.EventRead)
async def get_event(svc: EventSvcDep, current_user: CurrentUserDep, event_id: int) -> schemas.EventRead:
    return _to_read(await svc.get(current_user, event_id))


@router.patch("/{event_id}", response_model=schemas.EventRead)
async def patch_event(
    svc: EventSvcDep, current_user: CurrentUserDep, event_id: int, body: schemas.EventUpdate
) -> schemas.EventRead:
    data = body.model_dump(exclude_unset=True)
    updated = await svc.update(current_user, event_id, **data)
    return _to_read(updated)
