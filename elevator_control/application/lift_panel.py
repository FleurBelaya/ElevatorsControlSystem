"""
Сервис дистанционного управления лифтом.

Работает с таблицей lift_runtime (миграция 004) — отдельной от write/read CQRS-цикла,
потому что состояние «куда едем / открыты ли двери / горит ли свет» меняется быстро
и должно быть видно сразу. Никаких domain events для этих микро-операций мы не
публикуем (иначе очередь захлебнётся).

Доступ:
  * чтение panel       → permission lifts:read
  * управление         → permission lifts:update

Owner-фильтр: пользователи без ownership:bypass видят/управляют только своими лифтами.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from elevator_control.application.auth import AuthorizationService
from elevator_control.domain import auth as domain_auth
from elevator_control.domain.exceptions import ConflictError, NotFoundError


@dataclass(slots=True)
class LiftPanel:
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
    direction: str  # idle/up/down
    sensors: list[dict]


def _not_found(msg: str = "Лифт не найден") -> NotFoundError:
    return NotFoundError(msg)


async def _check_lift_access(
    session: AsyncSession,
    authz: AuthorizationService,
    actor: domain_auth.User,
    lift_id: int,
    *,
    require_perm: str,
) -> None:
    await authz.require(actor.id, require_perm)
    bypass = await authz.can_bypass_ownership(actor.id)
    if bypass:
        # admin/dispatcher с привилегией — доступ ко всем
        row = (
            await session.execute(
                text("SELECT 1 FROM lifts WHERE id = :id"),
                {"id": lift_id},
            )
        ).first()
    else:
        row = (
            await session.execute(
                text("SELECT 1 FROM lifts WHERE id = :id AND owner_id = :uid"),
                {"id": lift_id, "uid": actor.id},
            )
        ).first()
    if row is None:
        raise _not_found()


async def _ensure_runtime_row(session: AsyncSession, lift_id: int) -> None:
    """Создаёт runtime-строку, если её нет (для лифтов, добавленных до миграции)."""
    await session.execute(
        text(
            """
            INSERT INTO lift_runtime
                (lift_id, current_floor, target_floor, total_floors, doors_open, lights_on, direction)
            VALUES (:id, 1, 1, 9, FALSE, TRUE, 'idle')
            ON CONFLICT (lift_id) DO NOTHING
            """
        ),
        {"id": lift_id},
    )


async def get_panel(
    session: AsyncSession,
    authz: AuthorizationService,
    actor: domain_auth.User,
    lift_id: int,
) -> LiftPanel:
    await _check_lift_access(session, authz, actor, lift_id, require_perm="lifts:read")
    await _ensure_runtime_row(session, lift_id)

    row = (
        await session.execute(
            text(
                """
                SELECT l.id, l.model, l.location, l.status, l.is_emergency,
                       r.current_floor, r.target_floor, r.total_floors,
                       r.doors_open, r.lights_on, r.direction
                FROM lifts l
                JOIN lift_runtime r ON r.lift_id = l.id
                WHERE l.id = :id
                """
            ),
            {"id": lift_id},
        )
    ).first()
    if row is None:
        raise _not_found()

    sensors_rows = (
        await session.execute(
            text(
                """
                SELECT id, sensor_type, current_value, threshold_norm
                FROM sensors WHERE lift_id = :id ORDER BY id
                """
            ),
            {"id": lift_id},
        )
    ).all()

    sensors = [
        {
            "id": int(s[0]),
            "sensor_type": s[1],
            "current_value": float(s[2]),
            "threshold_norm": float(s[3]),
            "ratio": float(s[2]) / float(s[3]) if float(s[3]) > 0 else 0.0,
        }
        for s in sensors_rows
    ]

    return LiftPanel(
        lift_id=int(row[0]),
        model=row[1],
        location=row[2],
        status=row[3],
        is_emergency=bool(row[4]),
        current_floor=int(row[5]),
        target_floor=int(row[6]),
        total_floors=int(row[7]),
        doors_open=bool(row[8]),
        lights_on=bool(row[9]),
        direction=row[10],
        sensors=sensors,
    )


async def list_panels(
    session: AsyncSession,
    authz: AuthorizationService,
    actor: domain_auth.User,
) -> list[LiftPanel]:
    """Возвращает пульт по всем лифтам, доступным пользователю."""
    await authz.require(actor.id, "lifts:read")
    bypass = await authz.can_bypass_ownership(actor.id)

    # Гарантируем runtime-строки для всех лифтов
    await session.execute(
        text(
            """
            INSERT INTO lift_runtime (lift_id) SELECT id FROM lifts
            ON CONFLICT (lift_id) DO NOTHING
            """
        )
    )

    where = "" if bypass else "WHERE l.owner_id = :uid"
    params: dict = {} if bypass else {"uid": actor.id}
    rows = (
        await session.execute(
            text(
                f"""
                SELECT l.id, l.model, l.location, l.status, l.is_emergency,
                       r.current_floor, r.target_floor, r.total_floors,
                       r.doors_open, r.lights_on, r.direction
                FROM lifts l
                JOIN lift_runtime r ON r.lift_id = l.id
                {where}
                ORDER BY l.id
                """
            ),
            params,
        )
    ).all()
    if not rows:
        return []

    lift_ids = [int(r[0]) for r in rows]
    sensors_rows = (
        await session.execute(
            text(
                """
                SELECT lift_id, id, sensor_type, current_value, threshold_norm
                FROM sensors WHERE lift_id = ANY(:ids) ORDER BY id
                """
            ),
            {"ids": lift_ids},
        )
    ).all()
    by_lift: dict[int, list[dict]] = {}
    for s in sensors_rows:
        by_lift.setdefault(int(s[0]), []).append(
            {
                "id": int(s[1]),
                "sensor_type": s[2],
                "current_value": float(s[3]),
                "threshold_norm": float(s[4]),
                "ratio": float(s[3]) / float(s[4]) if float(s[4]) > 0 else 0.0,
            }
        )

    return [
        LiftPanel(
            lift_id=int(r[0]),
            model=r[1],
            location=r[2],
            status=r[3],
            is_emergency=bool(r[4]),
            current_floor=int(r[5]),
            target_floor=int(r[6]),
            total_floors=int(r[7]),
            doors_open=bool(r[8]),
            lights_on=bool(r[9]),
            direction=r[10],
            sensors=by_lift.get(int(r[0]), []),
        )
        for r in rows
    ]


async def set_target_floor(
    session: AsyncSession,
    authz: AuthorizationService,
    actor: domain_auth.User,
    lift_id: int,
    target_floor: int,
) -> LiftPanel:
    await _check_lift_access(session, authz, actor, lift_id, require_perm="lifts:update")
    await _ensure_runtime_row(session, lift_id)

    row = (
        await session.execute(
            text(
                "SELECT current_floor, total_floors, doors_open FROM lift_runtime WHERE lift_id = :id"
            ),
            {"id": lift_id},
        )
    ).first()
    if row is None:
        raise _not_found()
    current_floor, total_floors, doors_open = int(row[0]), int(row[1]), bool(row[2])

    if target_floor < 1 or target_floor > total_floors:
        raise ConflictError(f"Этаж должен быть в диапазоне 1..{total_floors}")

    # Если двери открыты — сначала закрываем (вежливо отказываемся)
    if doors_open and target_floor != current_floor:
        raise ConflictError("Сначала закройте двери, затем отправьте на этаж")

    direction = "idle"
    if target_floor > current_floor:
        direction = "up"
    elif target_floor < current_floor:
        direction = "down"

    await session.execute(
        text(
            """
            UPDATE lift_runtime SET
                target_floor = :tf,
                direction = :d,
                updated_at = now()
            WHERE lift_id = :id
            """
        ),
        {"id": lift_id, "tf": target_floor, "d": direction},
    )
    await session.commit()
    return await get_panel(session, authz, actor, lift_id)


async def set_doors(
    session: AsyncSession,
    authz: AuthorizationService,
    actor: domain_auth.User,
    lift_id: int,
    open_: bool,
) -> LiftPanel:
    await _check_lift_access(session, authz, actor, lift_id, require_perm="lifts:update")
    await _ensure_runtime_row(session, lift_id)

    row = (
        await session.execute(
            text("SELECT direction FROM lift_runtime WHERE lift_id = :id"),
            {"id": lift_id},
        )
    ).first()
    if row is None:
        raise _not_found()
    direction = row[0]

    if open_ and direction != "idle":
        raise ConflictError("Нельзя открывать двери в движении")

    await session.execute(
        text("UPDATE lift_runtime SET doors_open = :o, updated_at = now() WHERE lift_id = :id"),
        {"id": lift_id, "o": bool(open_)},
    )
    await session.commit()
    return await get_panel(session, authz, actor, lift_id)


async def set_lights(
    session: AsyncSession,
    authz: AuthorizationService,
    actor: domain_auth.User,
    lift_id: int,
    on_: bool,
) -> LiftPanel:
    await _check_lift_access(session, authz, actor, lift_id, require_perm="lifts:update")
    await _ensure_runtime_row(session, lift_id)
    await session.execute(
        text("UPDATE lift_runtime SET lights_on = :v, updated_at = now() WHERE lift_id = :id"),
        {"id": lift_id, "v": bool(on_)},
    )
    await session.commit()
    return await get_panel(session, authz, actor, lift_id)


async def emergency_stop(
    session: AsyncSession,
    authz: AuthorizationService,
    actor: domain_auth.User,
    lift_id: int,
) -> LiftPanel:
    await _check_lift_access(session, authz, actor, lift_id, require_perm="lifts:update")
    await _ensure_runtime_row(session, lift_id)
    # Сбрасываем target = current, направление idle, двери закрываются.
    await session.execute(
        text(
            """
            UPDATE lift_runtime SET
                target_floor = current_floor,
                direction = 'idle',
                doors_open = FALSE,
                updated_at = now()
            WHERE lift_id = :id
            """
        ),
        {"id": lift_id},
    )
    await session.commit()
    return await get_panel(session, authz, actor, lift_id)


async def tick_runtime(session: AsyncSession) -> int:
    """
    Один шаг симуляции: для каждого лифта, у которого есть target != current и
    двери закрыты, сдвигаем current_floor на 1 в сторону target. Возвращает
    количество затронутых строк.
    """
    res = await session.execute(
        text(
            """
            UPDATE lift_runtime
            SET current_floor = CASE
                    WHEN current_floor < target_floor THEN current_floor + 1
                    WHEN current_floor > target_floor THEN current_floor - 1
                    ELSE current_floor
                END,
                direction = CASE
                    WHEN current_floor + 1 = target_floor THEN 'idle'
                    WHEN current_floor - 1 = target_floor THEN 'idle'
                    WHEN current_floor < target_floor THEN 'up'
                    WHEN current_floor > target_floor THEN 'down'
                    ELSE 'idle'
                END,
                updated_at = now()
            WHERE current_floor != target_floor AND doors_open = FALSE
            """
        )
    )
    return res.rowcount or 0
