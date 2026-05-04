# 4.2.2 Разные DTO для разных клиентов: каждое подмножество данных адаптировано
# под особенности конкретного UI (плотность экрана, объём трафика, способ отображения).

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ----------------- 4.2.2 Web BFF DTO (компактный дашборд) -----------------

class WebDashboardLift(BaseModel):
    # Веб-клиент видит таблицу с агрегатами: подсветить «горячие» лифты.
    id: int
    model: str
    status: str
    location: str
    is_emergency: bool
    open_events_count: int
    open_requests_count: int
    sensors_count: int
    risk_score: float = Field(..., description="0..1 — нормированный max(sensor_value/threshold)")


class WebDashboardEvent(BaseModel):
    id: int
    lift_id: int
    lift_model: str
    event_type: str
    description: str
    status: str


class WebDashboardServiceRequest(BaseModel):
    id: int
    lift_id: int
    lift_model: str
    technician_name: str | None
    status: str


class WebDashboardResponse(BaseModel):
    # 4.2.3 Агрегация: один ответ объединяет несколько query (lifts/events/requests/heatmap).
    summary: dict
    lifts: list[WebDashboardLift]
    recent_events: list[WebDashboardEvent]
    open_service_requests: list[WebDashboardServiceRequest]


# ----------------- 4.2.2 Mobile BFF DTO (минимум данных, плоская структура) -----------------

class MobileLiftCard(BaseModel):
    # Мобильному клиенту нужен только короткий список «карточек».
    id: int
    title: str  # уже подготовленная строка для UI: "Otis-2000 · подъезд 3"
    status: Literal["ok", "warning", "critical"]
    badge: int  # количество активных событий — отрисовывается как точка


class MobileMyTask(BaseModel):
    # Техник на телефоне видит свои текущие заявки.
    request_id: int
    lift_title: str
    status: str
    reason: str


class MobileFeedResponse(BaseModel):
    # 4.2.3 Агрегация: одна страница "лента" мобильного приложения.
    lifts: list[MobileLiftCard]
    my_tasks: list[MobileMyTask]


# ----------------- 4.2.2 Desktop BFF DTO (богатый таб с полной информацией) -----------------

class DesktopSensor(BaseModel):
    id: int
    sensor_type: str
    current_value: float
    threshold_norm: float
    ratio: float
    zone: str


class DesktopEvent(BaseModel):
    id: int
    event_type: str
    description: str
    status: str
    created_at: datetime


class DesktopServiceRequest(BaseModel):
    id: int
    reason: str
    status: str
    technician_name: str | None


class DesktopLiftWorkbench(BaseModel):
    # 4.2.3 Агрегация: десктопный клиент получает «рабочее место по лифту»
    # — лифт + датчики + последние события + активные заявки в одном ответе.
    model_config = ConfigDict(from_attributes=False)

    lift: dict
    sensors: list[DesktopSensor]
    events: list[DesktopEvent]
    service_requests: list[DesktopServiceRequest]
