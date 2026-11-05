"""Async SQLAlchemy engine / session factory."""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from bot.config import get_settings

logger = logging.getLogger(__name__)


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


def _migrate_db_schema(sync_conn) -> None:
    """Introspect tables and safely add any missing columns from models to the DB."""
    import bot.db.models  # noqa: F401 - ensure models are registered on Base.metadata

    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    dialect_name = sync_conn.dialect.name

    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            continue

        existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
        for col in table.columns:
            if col.name in existing_columns:
                continue

            col_type = col.type.compile(sync_conn.dialect)
            default_str = ""
            if col.server_default is not None:
                arg = getattr(col.server_default, "arg", None)
                if hasattr(arg, "name") and arg.name == "now":
                    default_str = " DEFAULT CURRENT_TIMESTAMP"
                elif isinstance(arg, str):
                    default_str = f" DEFAULT {arg}"
                elif isinstance(arg, text):
                    default_str = f" DEFAULT {arg.text}"
            elif col.default is not None and getattr(col.default, "is_scalar", False):
                val = col.default.arg
                if isinstance(val, bool):
                    if dialect_name == "postgresql":
                        default_str = f" DEFAULT {str(val).upper()}"
                    else:
                        default_str = f" DEFAULT {1 if val else 0}"
                elif isinstance(val, (int, float)):
                    default_str = f" DEFAULT {val}"
                elif isinstance(val, str):
                    default_str = f" DEFAULT '{val}'"

            if dialect_name == "postgresql":
                stmt = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{col.name}" {col_type}{default_str};'
            else:
                stmt = f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {col_type}{default_str};'

            try:
                sync_conn.execute(text(stmt))
                logger.info("Migrated schema: added column %s.%s (%s)", table_name, col.name, col_type)
            except Exception as exc:
                logger.warning("Could not add column %s.%s: %s", table_name, col.name, exc)

        # Inspect and create missing table indexes (e.g. partial unique indexes on upgraded DBs)
        try:
            existing_indexes = {idx["name"] for idx in inspector.get_indexes(table_name) if idx.get("name")}
        except Exception:
            existing_indexes = set()

        for idx in table.indexes:
            if idx.name and idx.name not in existing_indexes:
                try:
                    idx.create(bind=sync_conn)
                    logger.info("Migrated schema: created missing index %s on %s", idx.name, table_name)
                except Exception as exc:
                    logger.warning("Could not create index %s on %s: %s", idx.name, table_name, exc)


async def init_db(engine) -> None:
    """Create all tables on boot and apply non-destructive schema migrations."""
    import bot.db.models  # noqa: F401 - ensure models registered
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_db_schema)
        dialect_name = conn.dialect.name
        if dialect_name == "postgresql":
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
