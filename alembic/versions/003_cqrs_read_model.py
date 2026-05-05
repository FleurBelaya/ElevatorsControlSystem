# 4.1.2 Разные модели данных. Write Model — нормализованная (исходные таблицы),
# Read Model — денормализованная (lifts_read, events_read и т.д.).
# Эта миграция создаёт read-таблицы и заполняет их из write-модели.
"""cqrs read model

Revision ID: 003
Revises: 002
Create Date: 2026-05-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 4.1.2 Read Model: денормализованная таблица для лифтов с агрегатами
    op.create_table(
        "lifts_read",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("location", sa.String(length=256), nullable=False),
        sa.Column("is_emergency", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        # Денормализация: подсчёт связанных сущностей и кэш последних значений
        sa.Column("sensors_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_events_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_requests_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_event_type", sa.String(length=32), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_sensor_ratio", sa.Float(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_lifts_read_owner_id"), "lifts_read", ["owner_id"], unique=False)
    op.create_index(op.f("ix_lifts_read_status"), "lifts_read", ["status"], unique=False)

    # 4.1.2 Read Model: денормализованные события (с моделью лифта внутри)
    op.create_table(
        "events_read",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("lift_id", sa.Integer(), nullable=False),
        sa.Column("lift_model", sa.String(length=128), nullable=False),
        sa.Column("lift_location", sa.String(length=256), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_events_read_owner_id"), "events_read", ["owner_id"], unique=False)
    op.create_index(op.f("ix_events_read_lift_id"), "events_read", ["lift_id"], unique=False)
    op.create_index(op.f("ix_events_read_event_type"), "events_read", ["event_type"], unique=False)
    op.create_index(op.f("ix_events_read_status"), "events_read", ["status"], unique=False)

    # 4.1.2 Read Model: денормализованные заявки (с моделью лифта и именем техника)
    op.create_table(
        "service_requests_read",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("lift_id", sa.Integer(), nullable=False),
        sa.Column("lift_model", sa.String(length=128), nullable=False),
        sa.Column("lift_location", sa.String(length=256), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("technician_id", sa.Integer(), nullable=True),
        sa.Column("technician_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_service_requests_read_owner_id"), "service_requests_read", ["owner_id"], unique=False)
    op.create_index(op.f("ix_service_requests_read_lift_id"), "service_requests_read", ["lift_id"], unique=False)
    op.create_index(op.f("ix_service_requests_read_status"), "service_requests_read", ["status"], unique=False)

    # 4.1.2 Read Model: денормализованные техники с подсчётом активных заявок
    op.create_table(
        "technicians_read",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("active_requests_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_technicians_read_owner_id"), "technicians_read", ["owner_id"], unique=False)
    op.create_index(op.f("ix_technicians_read_status"), "technicians_read", ["status"], unique=False)

    # 4.1.2 Read Model: денормализованные отчёты с моделью лифта
    op.create_table(
        "reports_read",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("service_request_id", sa.Integer(), nullable=False),
        sa.Column("lift_id", sa.Integer(), nullable=False),
        sa.Column("lift_model", sa.String(length=128), nullable=False),
        sa.Column("work_description", sa.Text(), nullable=False),
        sa.Column("final_lift_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_reports_read_owner_id"), "reports_read", ["owner_id"], unique=False)
    op.create_index(op.f("ix_reports_read_service_request_id"), "reports_read", ["service_request_id"], unique=False)

    # 4.1.2 Read Model: денормализованные датчики (с моделью лифта)
    op.create_table(
        "sensors_read",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("lift_id", sa.Integer(), nullable=False),
        sa.Column("lift_model", sa.String(length=128), nullable=False),
        sa.Column("sensor_type", sa.String(length=64), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=False),
        sa.Column("threshold_norm", sa.Float(), nullable=False),
        sa.Column("ratio", sa.Float(), nullable=False, server_default="0"),
        sa.Column("zone", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_sensors_read_owner_id"), "sensors_read", ["owner_id"], unique=False)
    op.create_index(op.f("ix_sensors_read_lift_id"), "sensors_read", ["lift_id"], unique=False)

    # 4.3.1 Domain Event: журнал доменных событий (для очереди и аудита)
    op.create_table(
        "domain_events_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="published"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_domain_events_log_event_type"), "domain_events_log", ["event_type"], unique=False)
    op.create_index(op.f("ix_domain_events_log_status"), "domain_events_log", ["status"], unique=False)

    # 6.2.3 Logout (blacklist): таблица для отозванных JWT-токенов
    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_revoked_tokens_user_id"), "revoked_tokens", ["user_id"], unique=False)
    op.create_index(op.f("ix_revoked_tokens_expires_at"), "revoked_tokens", ["expires_at"], unique=False)

    # Backfill: первичная синхронизация read-таблиц из write-таблиц
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            INSERT INTO lifts_read (
                id, owner_id, model, status, location, is_emergency,
                sensors_count, open_events_count, open_requests_count,
                last_event_type, last_event_at, max_sensor_ratio, synced_at
            )
            SELECT
                l.id, l.owner_id, l.model, l.status, l.location, l.is_emergency,
                COALESCE((SELECT COUNT(*) FROM sensors s WHERE s.lift_id = l.id), 0),
                COALESCE((SELECT COUNT(*) FROM events e WHERE e.lift_id = l.id AND e.status IN ('new','in_progress')), 0),
                COALESCE((SELECT COUNT(*) FROM service_requests sr WHERE sr.lift_id = l.id AND sr.status IN ('pending','assigned','in_progress')), 0),
                NULL, NULL,
                COALESCE((SELECT MAX(s.current_value / NULLIF(s.threshold_norm, 0)) FROM sensors s WHERE s.lift_id = l.id), 0),
                now()
            FROM lifts l
            """
        )
    )

    conn.execute(
        sa.text(
            """
            INSERT INTO events_read (
                id, owner_id, lift_id, lift_model, lift_location,
                event_type, description, status, created_at, synced_at
            )
            SELECT
                e.id, e.owner_id, e.lift_id, l.model, l.location,
                e.event_type, e.description, e.status, now(), now()
            FROM events e JOIN lifts l ON l.id = e.lift_id
            """
        )
    )

    conn.execute(
        sa.text(
            """
            INSERT INTO service_requests_read (
                id, owner_id, lift_id, lift_model, lift_location,
                reason, status, technician_id, technician_name, created_at, synced_at
            )
            SELECT
                sr.id, sr.owner_id, sr.lift_id, l.model, l.location,
                sr.reason, sr.status, sr.technician_id, t.name, now(), now()
            FROM service_requests sr
            JOIN lifts l ON l.id = sr.lift_id
            LEFT JOIN technicians t ON t.id = sr.technician_id
            """
        )
    )

    conn.execute(
        sa.text(
            """
            INSERT INTO technicians_read (id, owner_id, name, status, active_requests_count, synced_at)
            SELECT
                t.id, t.owner_id, t.name, t.status,
                COALESCE((SELECT COUNT(*) FROM service_requests sr WHERE sr.technician_id = t.id AND sr.status IN ('assigned','in_progress')), 0),
                now()
            FROM technicians t
            """
        )
    )

    conn.execute(
        sa.text(
            """
            INSERT INTO reports_read (
                id, owner_id, service_request_id, lift_id, lift_model,
                work_description, final_lift_status, created_at, synced_at
            )
            SELECT
                r.id, r.owner_id, r.service_request_id, sr.lift_id, l.model,
                r.work_description, r.final_lift_status, r.created_at, now()
            FROM reports r
            JOIN service_requests sr ON sr.id = r.service_request_id
            JOIN lifts l ON l.id = sr.lift_id
            """
        )
    )

    conn.execute(
        sa.text(
            """
            INSERT INTO sensors_read (
                id, owner_id, lift_id, lift_model, sensor_type,
                current_value, threshold_norm, ratio, zone, synced_at
            )
            SELECT
                s.id, s.owner_id, s.lift_id, l.model, s.sensor_type,
                s.current_value, s.threshold_norm,
                CASE WHEN s.threshold_norm > 0 THEN s.current_value / s.threshold_norm ELSE 0 END,
                CASE
                    WHEN s.threshold_norm <= 0 THEN 'ok'
                    WHEN s.current_value > s.threshold_norm * 1.2 THEN 'critical'
                    WHEN s.current_value > s.threshold_norm THEN 'warning'
                    ELSE 'ok'
                END,
                now()
            FROM sensors s JOIN lifts l ON l.id = s.lift_id
            """
        )
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_revoked_tokens_expires_at"), table_name="revoked_tokens")
    op.drop_index(op.f("ix_revoked_tokens_user_id"), table_name="revoked_tokens")
    op.drop_table("revoked_tokens")

    op.drop_index(op.f("ix_domain_events_log_status"), table_name="domain_events_log")
    op.drop_index(op.f("ix_domain_events_log_event_type"), table_name="domain_events_log")
    op.drop_table("domain_events_log")

    op.drop_index(op.f("ix_sensors_read_lift_id"), table_name="sensors_read")
    op.drop_index(op.f("ix_sensors_read_owner_id"), table_name="sensors_read")
    op.drop_table("sensors_read")

    op.drop_index(op.f("ix_reports_read_service_request_id"), table_name="reports_read")
    op.drop_index(op.f("ix_reports_read_owner_id"), table_name="reports_read")
    op.drop_table("reports_read")

    op.drop_index(op.f("ix_technicians_read_status"), table_name="technicians_read")
    op.drop_index(op.f("ix_technicians_read_owner_id"), table_name="technicians_read")
    op.drop_table("technicians_read")

    op.drop_index(op.f("ix_service_requests_read_status"), table_name="service_requests_read")
    op.drop_index(op.f("ix_service_requests_read_lift_id"), table_name="service_requests_read")
    op.drop_index(op.f("ix_service_requests_read_owner_id"), table_name="service_requests_read")
    op.drop_table("service_requests_read")

    op.drop_index(op.f("ix_events_read_status"), table_name="events_read")
    op.drop_index(op.f("ix_events_read_event_type"), table_name="events_read")
    op.drop_index(op.f("ix_events_read_lift_id"), table_name="events_read")
    op.drop_index(op.f("ix_events_read_owner_id"), table_name="events_read")
    op.drop_table("events_read")

    op.drop_index(op.f("ix_lifts_read_status"), table_name="lifts_read")
    op.drop_index(op.f("ix_lifts_read_owner_id"), table_name="lifts_read")
    op.drop_table("lifts_read")
