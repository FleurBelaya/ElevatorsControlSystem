"""
REST API дистанционного управления лифтом (пульт диспетчера/администратора).

Все endpoints требуют permission lifts:update (управление) или lifts:read (просмотр).
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field

from elevator_control.adapters.inbound.api.deps import (
    AuthorizationDep,
    CurrentUserDep,
    SessionDep,
)
from elevator_control.application import lift_panel as lp


router = APIRouter(prefix="/lifts", tags=["lifts-control"])


class _Forbid(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MoveRequest(_Forbid):
    target_floor: int = Field(..., ge=1, le=200)


class DoorsRequest(_Forbid):
    open: bool


class LightsRequest(_Forbid):
    on: bool


class SensorPanel(BaseModel):
    id: int
    sensor_type: str
    current_value: float
    threshold_norm: float
    ratio: float


class PanelResponse(BaseModel):
    lift_id: int
    model: str
    location: str
    status: str
    is_emergency: bool
    current_floor: int
    target_floor: int
    total_floors: int
    doors_open: bool
    lights_on: bool
    direction: Literal["idle", "up", "down"]
    sensors: list[SensorPanel]


def _to_response(p: lp.LiftPanel) -> PanelResponse:
    return PanelResponse(
        lift_id=p.lift_id,
        model=p.model,
        location=p.location,
        status=p.status,
        is_emergency=p.is_emergency,
        current_floor=p.current_floor,
        target_floor=p.target_floor,
        total_floors=p.total_floors,
        doors_open=p.doors_open,
        lights_on=p.lights_on,
        direction=p.direction,  # type: ignore[arg-type]
        sensors=[SensorPanel(**s) for s in p.sensors],
    )


@router.get("/panels", response_model=list[PanelResponse])
async def list_panels(
    session: SessionDep, authz: AuthorizationDep, current_user: CurrentUserDep
) -> list[PanelResponse]:
    panels = await lp.list_panels(session, authz, current_user)
    return [_to_response(p) for p in panels]


@router.get("/{lift_id}/panel", response_model=PanelResponse)
async def get_panel(
    session: SessionDep,
    authz: AuthorizationDep,
    current_user: CurrentUserDep,
    lift_id: int,
) -> PanelResponse:
    panel = await lp.get_panel(session, authz, current_user, lift_id)
    return _to_response(panel)


@router.post("/{lift_id}/control/move", response_model=PanelResponse)
async def control_move(
    session: SessionDep,
    authz: AuthorizationDep,
    current_user: CurrentUserDep,
    lift_id: int,
    body: MoveRequest,
) -> PanelResponse:
    panel = await lp.set_target_floor(session, authz, current_user, lift_id, body.target_floor)
    return _to_response(panel)


@router.post("/{lift_id}/control/doors", response_model=PanelResponse)
async def control_doors(
    session: SessionDep,
    authz: AuthorizationDep,
    current_user: CurrentUserDep,
    lift_id: int,
    body: DoorsRequest,
) -> PanelResponse:
    panel = await lp.set_doors(session, authz, current_user, lift_id, body.open)
    return _to_response(panel)


@router.post("/{lift_id}/control/lights", response_model=PanelResponse)
async def control_lights(
    session: SessionDep,
    authz: AuthorizationDep,
    current_user: CurrentUserDep,
    lift_id: int,
    body: LightsRequest,
) -> PanelResponse:
    panel = await lp.set_lights(session, authz, current_user, lift_id, body.on)
    return _to_response(panel)


@router.post(
    "/{lift_id}/control/stop",
    response_model=PanelResponse,
    status_code=status.HTTP_200_OK,
    summary="Аварийная остановка кабины",
)
async def control_stop(
    session: SessionDep,
    authz: AuthorizationDep,
    current_user: CurrentUserDep,
    lift_id: int,
) -> PanelResponse:
    panel = await lp.emergency_stop(session, authz, current_user, lift_id)
    return _to_response(panel)
