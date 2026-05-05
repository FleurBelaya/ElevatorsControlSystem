"""lift runtime panel state

Revision ID: 004
Revises: 003
Create Date: 2026-05-05

Добавляет таблицу lift_runtime для дистанционного управления лифтом
(этаж, двери, свет, направление). Изменяется без write/read разделения,
потому что состояние меняется быстро и нам нужно реальное время.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lift_runtime",
        sa.Column(
            "lift_id",
            sa.Integer(),
            sa.ForeignKey("lifts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("current_floor", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("target_floor", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("total_floors", sa.Integer(), nullable=False, server_default="9"),
        sa.Column("doors_open", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("lights_on", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "direction",
            sa.String(length=8),
            nullable=False,
            server_default="idle",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Бэкфилл: создаём runtime-запись для каждого существующего лифта.
    op.execute(
        """
        INSERT INTO lift_runtime (lift_id, current_floor, target_floor, total_floors, doors_open, lights_on, direction)
        SELECT id, 1, 1, 9, FALSE, TRUE, 'idle' FROM lifts
        ON CONFLICT (lift_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("lift_runtime")
