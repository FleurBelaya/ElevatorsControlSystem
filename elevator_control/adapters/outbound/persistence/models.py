# 2.3 - Оптимизация ORM: lazy и eager loading
# Стратегии загрузки связей разделены на lazy ("select") и eager ("selectin").
# lazy="select" — связь загружается только при обращении (по умолчанию, экономит ресурсы).
# lazy="selectin" — связь загружается сразу вместе с родителем (eager, используется
#   для связей, которые нужны практически в каждом запросе, например roles -> permissions).
# В репозиториях при необходимости подгрузки используются options(selectinload(...)).

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from elevator_control.infrastructure.database import Base



user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    roles: Mapped[list["RoleModel"]] = relationship(
        secondary=user_roles,
        back_populates="users",
        lazy="selectin",
    )


class RoleModel(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    users: Mapped[list[UserModel]] = relationship(
        secondary=user_roles,
        back_populates="roles",
        lazy="selectin",
    )
    permissions: Mapped[list["PermissionModel"]] = relationship(
        secondary=role_permissions,
        back_populates="roles",
        lazy="selectin",
    )


class PermissionModel(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    roles: Mapped[list[RoleModel]] = relationship(
        secondary=role_permissions,
        back_populates="permissions",
        lazy="selectin",
    )


class LiftModel(Base):
    __tablename__ = "lifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(256), nullable=False)
    is_emergency: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 2.3 - lazy="select": owner загружается только при обращении
    owner: Mapped[UserModel] = relationship(lazy="select")
    # 2.3 - lazy="select": коллекции загружаются лениво, т.к. списки потенциально большие
    sensors: Mapped[list["SensorModel"]] = relationship(back_populates="lift", cascade="all, delete-orphan", lazy="select")
    events: Mapped[list["EventModel"]] = relationship(back_populates="lift", cascade="all, delete-orphan", lazy="select")
    service_requests: Mapped[list["ServiceRequestModel"]] = relationship(
        back_populates="lift", cascade="all, delete-orphan", lazy="select"
    )


class SensorModel(Base):
    __tablename__ = "sensors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    lift_id: Mapped[int] = mapped_column(ForeignKey("lifts.id", ondelete="CASCADE"), nullable=False, index=True)
    sensor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    current_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_norm: Mapped[float] = mapped_column(Float, nullable=False)

    # 2.3 - lazy="select": owner и lift загружаются только при необходимости
    owner: Mapped[UserModel] = relationship(lazy="select")
    lift: Mapped["LiftModel"] = relationship(back_populates="sensors", lazy="select")


class EventModel(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    lift_id: Mapped[int] = mapped_column(ForeignKey("lifts.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # 2.3 - lazy="select": owner и lift загружаются только при необходимости
    owner: Mapped[UserModel] = relationship(lazy="select")
    lift: Mapped["LiftModel"] = relationship(back_populates="events", lazy="select")


class TechnicianModel(Base):
    __tablename__ = "technicians"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # 2.3 - lazy="select": owner загружается лениво
    owner: Mapped[UserModel] = relationship(lazy="select")
    service_requests: Mapped[list["ServiceRequestModel"]] = relationship(back_populates="technician", lazy="select")


class ServiceRequestModel(Base):
    __tablename__ = "service_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    lift_id: Mapped[int] = mapped_column(ForeignKey("lifts.id", ondelete="CASCADE"), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    technician_id: Mapped[int | None] = mapped_column(
        ForeignKey("technicians.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # 2.3 - lazy="select": связи загружаются лениво; eager подгрузка выполняется в репозиториях
    owner: Mapped[UserModel] = relationship(lazy="select")
    lift: Mapped["LiftModel"] = relationship(back_populates="service_requests", lazy="select")
    technician: Mapped["TechnicianModel | None"] = relationship(back_populates="service_requests", lazy="select")
    reports: Mapped[list["ReportModel"]] = relationship(back_populates="service_request", cascade="all, delete-orphan", lazy="select")


class ReportModel(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    service_request_id: Mapped[int] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_description: Mapped[str] = mapped_column(Text, nullable=False)
    final_lift_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 2.3 - lazy="select": owner загружается лениво
    owner: Mapped[UserModel] = relationship(lazy="select")
    service_request: Mapped["ServiceRequestModel"] = relationship(back_populates="reports", lazy="select")
