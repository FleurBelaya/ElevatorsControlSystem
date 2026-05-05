"""
Идемпотентный сидер демо-аккаунтов: переиспользуется в:
  - scripts/seed_demo_users.py (ручной запуск)
  - elevator_control/main.py    (автоматический сид при старте FastAPI)
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import text

from elevator_control.application.auth import hash_password
from elevator_control.infrastructure.database import AsyncSessionLocal


DEMO_USERS: list[tuple[str, str, str]] = [
    ("admin@elevator.local",      "Admin12345",      "administrator"),
    ("dispatcher@elevator.local", "Dispatch12345",   "dispatcher"),
    ("technician@elevator.local", "Technician12345", "technician"),
]


async def _upsert_user(session, email: str, password: str, role: str) -> int:
    pw_hash = hash_password(password)
    row = (
        await session.execute(
            text(
                """
                INSERT INTO users (email, password_hash, is_active)
                VALUES (:email, :pw, TRUE)
                ON CONFLICT (email) DO UPDATE SET
                    password_hash = EXCLUDED.password_hash,
                    is_active = TRUE
                RETURNING id
                """
            ),
            {"email": email.lower(), "pw": pw_hash},
        )
    ).first()
    user_id = int(row[0])

    role_row = (
        await session.execute(
            text("SELECT id FROM roles WHERE name = :name"),
            {"name": role},
        )
    ).first()
    if role_row is None:
        raise RuntimeError(
            f"Роль '{role}' не найдена в таблице roles. "
            f"Сначала примените миграции: alembic upgrade head"
        )
    role_id = int(role_row[0])

    await session.execute(
        text("DELETE FROM user_roles WHERE user_id = :uid"),
        {"uid": user_id},
    )
    await session.execute(
        text(
            "INSERT INTO user_roles (user_id, role_id) VALUES (:uid, :rid) "
            "ON CONFLICT DO NOTHING"
        ),
        {"uid": user_id, "rid": role_id},
    )
    return user_id


async def seed_demo_users(users: Iterable[tuple[str, str, str]] = DEMO_USERS) -> list[tuple[str, int]]:
    """Создаёт/обновляет demo-аккаунты. Возвращает список (email, user_id)."""
    result: list[tuple[str, int]] = []
    async with AsyncSessionLocal() as session:
        try:
            for email, password, role in users:
                uid = await _upsert_user(session, email, password, role)
                result.append((email, uid))
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return result
