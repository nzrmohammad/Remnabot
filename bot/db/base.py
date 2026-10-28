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


async def init_db(engine) -> None:
    """Create all tables on boot and apply non-destructive schema migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        dialect_name = conn.dialect.name
        from sqlalchemy import text
        if dialect_name == "postgresql":
            try:
                await conn.execute(text(
                    "ALTER TABLE crypto_invoices ADD COLUMN IF NOT EXISTS currency VARCHAR(16) DEFAULT 'TON';"
                ))
            except Exception:
                pass
            try:
                await conn.execute(text(
                    "ALTER TABLE crypto_invoices ALTER COLUMN comment TYPE VARCHAR(64);"
                ))
            except Exception:
                pass
            try:
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_crypto_invoices_currency ON crypto_invoices (currency);"
                ))
            except Exception:
                pass
        elif dialect_name == "sqlite":
            try:
                await conn.execute(text(
                    "ALTER TABLE crypto_invoices ADD COLUMN currency VARCHAR(16) DEFAULT 'TON';"
                ))
            except Exception:
                pass
