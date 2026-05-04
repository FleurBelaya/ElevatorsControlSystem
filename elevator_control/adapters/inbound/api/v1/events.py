# 4.1.1 CQRS на уровне HTTP: GET → EventQueryService, POST/PATCH → EventCommandService.

from fastapi import APIRouter, Query, status

from elevator_control.adapters.inbound.api import schemas
from elevator_control.adapters.inbound.api.deps import (
    CurrentUserDep,
    EventCmdDep,
    EventQueryDep,
)
from elevator_control.application.queries.event_queries import EventReadDTO
from elevator_control.domain import entities as e
from elevator_control.domain.enums import EventStatus, EventType

router = APIRouter(prefix="/events", tags=["events"])


def _read_dto_to_schema(dto: EventReadDTO) -> schemas.EventRead:
    # 4.1.2 Read Model: денормализованный DTO → плоский ответ для legacy v1 API.
    return schemas.EventRead(
        id=dto.id,
        lift_id=dto.lift_id,
        event_type=EventType(dto.event_type),
        description=dto.description,
        status=EventStatus(dto.status),
    )


def _entity_to_schema(ev: e.Event) -> schemas.EventRead:
    assert ev.id is not None
    return schemas.EventRead(
        id=ev.id,
        lift_id=ev.lift_id,
        event_type=ev.event_type,
        description=ev.description,
        status=ev.status,
    )


# 4.1.1 CQRS Query side
@router.get("", response_model=schemas.Paginated)
async def list_events(
    qsvc: EventQueryDep,
    current_user: CurrentUserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    lift_id: int | None = None,
    status_filter: EventStatus | None = Query(None, alias="status"),
    event_type: EventType | None = None,
) -> schemas.Paginated:
    items, total = await qsvc.list_page(current_user, skip, limit, lift_id, status_filter, event_type)
    return schemas.Paginated(
        items=[_read_dto_to_schema(x).model_dump() for x in items],
        total=total,
        skip=skip,
        limit=limit,
    )


# 4.1.1 CQRS Command side
@router.post("", response_model=schemas.EventRead, status_code=status.HTTP_201_CREATED)
async def create_event(
    csvc: EventCmdDep, current_user: CurrentUserDep, body: schemas.EventCreate
) -> schemas.EventRead:
    # 6.1.2 Mass Assignment: owner_id берётся из current_user, не из тела.
    created = await csvc.create(
        current_user,
        e.Event(
            id=None,
            owner_id=current_user.id,
            lift_id=body.lift_id,
            event_type=body.event_type,
            description=body.description,
            status=body.status,
        ),
    )
    return _entity_to_schema(created)


# 4.1.1 CQRS Query side
@router.get("/{event_id}", response_model=schemas.EventRead)
async def get_event(
    qsvc: EventQueryDep, current_user: CurrentUserDep, event_id: int
) -> schemas.EventRead:
    return _read_dto_to_schema(await qsvc.get_by_id(current_user, event_id))


# 4.1.1 CQRS Command side
@router.patch("/{event_id}", response_model=schemas.EventRead)
async def patch_event(
    csvc: EventCmdDep,
    current_user: CurrentUserDep,
    event_id: int,
    body: schemas.EventUpdate,
) -> schemas.EventRead:
    data = body.model_dump(exclude_unset=True)
    updated = await csvc.update(current_user, event_id, **data)
    return _entity_to_schema(updated)
