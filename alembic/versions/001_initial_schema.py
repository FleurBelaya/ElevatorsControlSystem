"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-04

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lifts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("location", sa.String(length=256), nullable=False),
        sa.Column("is_emergency", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lifts_status"), "lifts", ["status"], unique=False)

    op.create_table(
        "technicians",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_technicians_status"), "technicians", ["status"], unique=False)

    op.create_table(
        "sensors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lift_id", sa.Integer(), nullable=False),
        sa.Column("sensor_type", sa.String(length=64), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=False),
        sa.Column("threshold_norm", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["lift_id"], ["lifts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sensors_lift_id"), "sensors", ["lift_id"], unique=False)

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lift_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["lift_id"], ["lifts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_events_lift_id"), "events", ["lift_id"], unique=False)
    op.create_index(op.f("ix_events_event_type"), "events", ["event_type"], unique=False)
    op.create_index(op.f("ix_events_status"), "events", ["status"], unique=False)

    op.create_table(
        "service_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lift_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("technician_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["lift_id"], ["lifts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["technician_id"], ["technicians.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_service_requests_lift_id"), "service_requests", ["lift_id"], unique=False)
    op.create_index(op.f("ix_service_requests_status"), "service_requests", ["status"], unique=False)
    op.create_index(
        op.f("ix_service_requests_technician_id"), "service_requests", ["technician_id"], unique=False
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("service_request_id", sa.Integer(), nullable=False),
        sa.Column("work_description", sa.Text(), nullable=False),
        sa.Column("final_lift_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["service_request_id"], ["service_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reports_service_request_id"), "reports", ["service_request_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reports_service_request_id"), table_name="reports")
    op.drop_table("reports")
    op.drop_index(op.f("ix_service_requests_technician_id"), table_name="service_requests")
    op.drop_index(op.f("ix_service_requests_status"), table_name="service_requests")
    op.drop_index(op.f("ix_service_requests_lift_id"), table_name="service_requests")
    op.drop_table("service_requests")
    op.drop_index(op.f("ix_events_status"), table_name="events")
    op.drop_index(op.f("ix_events_event_type"), table_name="events")
    op.drop_index(op.f("ix_events_lift_id"), table_name="events")
    op.drop_table("events")
    op.drop_index(op.f("ix_sensors_lift_id"), table_name="sensors")
    op.drop_table("sensors")
    op.drop_index(op.f("ix_technicians_status"), table_name="technicians")
    op.drop_table("technicians")
    op.drop_index(op.f("ix_lifts_status"), table_name="lifts")
    op.drop_table("lifts")
