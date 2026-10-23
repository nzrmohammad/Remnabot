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


def _migrate_db(sync_conn) -> None:
    """Idempotently add any missing columns across SQLite and PostgreSQL."""
    import logging
    from sqlalchemy import inspect, text

    logger = logging.getLogger("bot.db.migration")
    inspector = inspect(sync_conn)
    tables = set(inspector.get_table_names())
    is_pg = sync_conn.dialect.name == "postgresql"

    # Define schema migrations: (table_name, column_name, sql_type_def)
    migrations = [
        # Services table
        ("services", "max_purchases", "INTEGER DEFAULT NULL"),
        ("services", "purchases_count", "INTEGER NOT NULL DEFAULT 0"),
        ("services", "badge", "VARCHAR(32) DEFAULT NULL"),
        ("services", "squad_uuid", "VARCHAR(64) DEFAULT NULL"),
        ("services", "hwid_limit", "INTEGER DEFAULT NULL"),
        ("services", "traffic_strategy", "VARCHAR(16) NOT NULL DEFAULT 'NO_RESET'"),
        # Users table
        ("users", "phone_number", "VARCHAR(32) DEFAULT NULL"),
        ("users", "birth_date", "VARCHAR(32) DEFAULT NULL"),
        ("users", "campaign_code", "VARCHAR(32) DEFAULT NULL"),
        ("users", "auto_renew", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("users", "wheel_streak", "INTEGER NOT NULL DEFAULT 0"),
        ("users", "wheel_last_spin_at", "TIMESTAMP WITH TIME ZONE DEFAULT NULL" if is_pg else "DATETIME DEFAULT NULL"),
        ("users", "spin_tickets", "INTEGER NOT NULL DEFAULT 0"),
        # Orders table
        ("orders", "is_renewal", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("orders", "snapshot_data", "TEXT DEFAULT NULL"),
        # Topups table
        ("topups", "receipt_hash", "VARCHAR(128) DEFAULT NULL"),
        ("topups", "receipt_photo_id", "VARCHAR(256) DEFAULT NULL"),
        ("topups", "admin_message_id", "BIGINT DEFAULT NULL"),
        # Report Settings table
        ("report_settings", "wheel_notify", "BOOLEAN NOT NULL DEFAULT TRUE"),
        ("report_settings", "wheel_notified", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("report_settings", "wheel_last_spin_at", "TIMESTAMP WITH TIME ZONE DEFAULT NULL" if is_pg else "DATETIME DEFAULT NULL"),
        ("report_settings", "last_wheel_message_id", "BIGINT DEFAULT NULL"),
    ]

    for table, col_name, col_def in migrations:
        if table in tables:
            try:
                existing_cols = {c["name"] for c in inspector.get_columns(table)}
                if col_name not in existing_cols:
                    logger.info("Migrating schema: adding column %s.%s", table, col_name)
                    sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))
            except Exception as exc:
                logger.warning("Error checking or adding column %s.%s: %s", table, col_name, exc)


async def init_db(engine) -> None:
    """Create all tables and idempotently migrate missing columns on boot."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_db)

