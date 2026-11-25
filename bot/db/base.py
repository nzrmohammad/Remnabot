"""Async SQLAlchemy engine / session factory."""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from bot.config import get_settings


class Base(DeclarativeBase):
    pass


def create_engine_and_sessionmaker():
    db_url = get_settings().DATABASE_URL
    kwargs = {"echo": False, "pool_pre_ping": True}
    if "sqlite" not in db_url:
        kwargs.update({
            "pool_size": 20,
            "max_overflow": 10,
            "pool_timeout": 30,
            "pool_recycle": 1800,
        })
    engine = create_async_engine(db_url, **kwargs)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


def async_session_factory() -> AsyncSession:
    """Convenience helper returning an active AsyncSession instance for CLI and scripts."""
    _, sf = create_engine_and_sessionmaker()
    return sf()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return an async_sessionmaker instance."""
    _, sf = create_engine_and_sessionmaker()
    return sf


async def init_db(engine) -> None:
    """Create missing ORM tables on fresh dev/test databases (schema migrations live in Alembic)."""
    import bot.db.models  # noqa: F401 - ensure models registered

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
