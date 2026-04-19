"""rbac + ownership

Revision ID: 002
Revises: 001
Create Date: 2026-04-20

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 2.1 Авторизация RBAC
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_roles_name"), "roles", ["name"], unique=True)

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_permissions_name"), "permissions", ["name"], unique=True)

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    # 2.2 Ownership
    for table in ["lifts", "sensors", "events", "service_requests", "technicians", "reports"]:
        op.add_column(table, sa.Column("owner_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_owner_id_users",
            table,
            "users",
            ["owner_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(op.f(f"ix_{table}_owner_id"), table, ["owner_id"], unique=False)

    conn = op.get_bind()
    has_data = False
    for table in ["lifts", "sensors", "events", "service_requests", "technicians", "reports"]:
        if int(conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()) > 0:
            has_data = True
            break

    if has_data:
        conn.execute(
            sa.text(
                "INSERT INTO users (id, email, password_hash, is_active) "
                "VALUES (1, 'system@local', 'disabled', false) "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        for table in ["lifts", "sensors", "events", "service_requests", "technicians", "reports"]:
            conn.execute(sa.text(f"UPDATE {table} SET owner_id = 1 WHERE owner_id IS NULL"))

    for table in ["lifts", "sensors", "events", "service_requests", "technicians", "reports"]:
        op.alter_column(table, "owner_id", existing_type=sa.Integer(), nullable=False)

    roles = [
        {"id": 1, "name": "administrator"},
        {"id": 2, "name": "dispatcher"},
        {"id": 3, "name": "technician"},
    ]
    op.bulk_insert(sa.table("roles", sa.column("id", sa.Integer), sa.column("name", sa.String)), roles)

    permissions = [
        (1, "ownership:bypass", "Видеть/изменять чужие данные"),
        (2, "lifts:create", None),
        (3, "lifts:read", None),
        (4, "lifts:update", None),
        (5, "lifts:delete", None),
        (6, "lifts:restore_state", None),
        (7, "lifts:simulate_emergency", None),
        (8, "sensors:create", None),
        (9, "sensors:read", None),
        (10, "sensors:update", None),
        (11, "sensors:delete", None),
        (12, "events:create", None),
        (13, "events:read", None),
        (14, "events:update", None),
        (15, "service_requests:create", None),
        (16, "service_requests:read", None),
        (17, "service_requests:update", None),
        (18, "service_requests:delete", None),
        (19, "technicians:create", None),
        (20, "technicians:read", None),
        (21, "technicians:update", None),
        (22, "technicians:delete", None),
        (23, "reports:create", None),
        (24, "reports:read", None),
        (25, "reports:update", None),
        (26, "reports:delete", None),
    ]
    op.bulk_insert(
        sa.table(
            "permissions",
            sa.column("id", sa.Integer),
            sa.column("name", sa.String),
            sa.column("description", sa.Text),
        ),
        [{"id": pid, "name": name, "description": desc} for pid, name, desc in permissions],
    )

    def rp(role_id: int, perm_ids: list[int]) -> list[dict]:
        return [{"role_id": role_id, "permission_id": pid} for pid in perm_ids]

    administrator_perms = [pid for pid, _, _ in permissions]
    dispatcher_perms = administrator_perms[:]  # диспетчеру пока даём полный доступ
    technician_perms = [
        3,  # lifts:read
        9,  # sensors:read
        13,  # events:read
        16,  # service_requests:read
        17,  # service_requests:update
        23,  # reports:create
        24,  # reports:read
    ]

    op.bulk_insert(
        sa.table(
            "role_permissions",
            sa.column("role_id", sa.Integer),
            sa.column("permission_id", sa.Integer),
        ),
        rp(1, administrator_perms) + rp(2, dispatcher_perms) + rp(3, technician_perms),
    )


def downgrade() -> None:
    for table in ["reports", "service_requests", "events", "sensors", "technicians", "lifts"]:
        op.drop_index(op.f(f"ix_{table}_owner_id"), table_name=table)
        op.drop_constraint(f"fk_{table}_owner_id_users", table_name=table, type_="foreignkey")
        op.drop_column(table, "owner_id")

    op.drop_table("role_permissions")
    op.drop_table("user_roles")
    op.drop_index(op.f("ix_permissions_name"), table_name="permissions")
    op.drop_table("permissions")
    op.drop_index(op.f("ix_roles_name"), table_name="roles")
    op.drop_table("roles")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
