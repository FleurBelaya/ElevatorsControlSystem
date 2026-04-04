from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from elevator_control.infrastructure.database import Base


class LiftModel(Base):
    __tablename__ = "lifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(256), nullable=False)
    is_emergency: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    sensors: Mapped[list["SensorModel"]] = relationship(back_populates="lift", cascade="all, delete-orphan")
    events: Mapped[list["EventModel"]] = relationship(back_populates="lift", cascade="all, delete-orphan")
    service_requests: Mapped[list["ServiceRequestModel"]] = relationship(
        back_populates="lift", cascade="all, delete-orphan"
    )


class SensorModel(Base):
    __tablename__ = "sensors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lift_id: Mapped[int] = mapped_column(ForeignKey("lifts.id", ondelete="CASCADE"), nullable=False, index=True)
    sensor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    current_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_norm: Mapped[float] = mapped_column(Float, nullable=False)

    lift: Mapped["LiftModel"] = relationship(back_populates="sensors")


class EventModel(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lift_id: Mapped[int] = mapped_column(ForeignKey("lifts.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    lift: Mapped["LiftModel"] = relationship(back_populates="events")


class TechnicianModel(Base):
    __tablename__ = "technicians"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    service_requests: Mapped[list["ServiceRequestModel"]] = relationship(back_populates="technician")


class ServiceRequestModel(Base):
    __tablename__ = "service_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lift_id: Mapped[int] = mapped_column(ForeignKey("lifts.id", ondelete="CASCADE"), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    technician_id: Mapped[int | None] = mapped_column(
        ForeignKey("technicians.id", ondelete="SET NULL"), nullable=True, index=True
    )

    lift: Mapped["LiftModel"] = relationship(back_populates="service_requests")
    technician: Mapped["TechnicianModel | None"] = relationship(back_populates="service_requests")
    reports: Mapped[list["ReportModel"]] = relationship(back_populates="service_request", cascade="all, delete-orphan")


class ReportModel(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_request_id: Mapped[int] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_description: Mapped[str] = mapped_column(Text, nullable=False)
    final_lift_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    service_request: Mapped["ServiceRequestModel"] = relationship(back_populates="reports")
