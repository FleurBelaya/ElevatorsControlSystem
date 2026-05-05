"""
Ручной сидер демо-аккаунтов для всех трёх ролей.

Запуск из корня проекта:
    python -m scripts.seed_demo_users

Создаёт (идемпотентно):

    Email                          Пароль             Роль
    -----------------------------  -----------------  --------------
    admin@elevator.local           Admin12345         administrator
    dispatcher@elevator.local      Dispatch12345      dispatcher
    technician@elevator.local      Technician12345    technician

Если пользователь уже есть — пароль и роль будут обновлены.

Та же функция автоматически вызывается на старте API в lifespan().
"""
from __future__ import annotations

import asyncio

from elevator_control.infrastructure.seed import DEMO_USERS, seed_demo_users


async def main() -> None:
    print("Создаю демо-аккаунты...")
    rows = await seed_demo_users(DEMO_USERS)
    for (email, uid), (_, password, role) in zip(rows, DEMO_USERS):
        print(f"  ✓ {email:32}  роль={role:14}  id={uid}")
    print()
    print("Готово. Демо-аккаунты:")
    for email, password, role in DEMO_USERS:
        print(f"   {role:14}  →  {email}  /  {password}")


if __name__ == "__main__":
    asyncio.run(main())
