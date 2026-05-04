from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session

from elevator_control.infrastructure.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url_async,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# 4.3.2 Event-очередь: после успешного commit сессии достаём накопленные
# pending_event_payloads и ставим Celery-задачи для воркера. Это outbox-pattern:
# событие точно зафиксировано в domain_events_log, потому что publisher.publish()
# сделал INSERT в той же транзакции — поэтому воркер найдёт его в БД.
@event.listens_for(Session, "after_commit")
def _after_commit_schedule_handlers(session: Session) -> None:  # noqa: ANN001
    payloads = session.info.pop("pending_event_payloads", [])
    if not payloads:
        return
    # Импорт внутри хука: на момент импорта database.py celery_app может быть
    # ещё не инициализирован.
    from elevator_control.application.events.publisher import schedule_handlers

    schedule_handlers(payloads)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
