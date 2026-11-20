"""Async SQLAlchemy engine / session factory."""
import logging

from sqlalchemy import UniqueConstraint, inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.elements import TextClause

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


def async_session_factory() -> AsyncSession:
    """Convenience helper returning an active AsyncSession instance for CLI and scripts."""
    _, sf = create_engine_and_sessionmaker()
    return sf()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return an async_sessionmaker instance."""
    _, sf = create_engine_and_sessionmaker()
    return sf


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
        added_columns: set[str] = set()
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
                    if arg.isdigit() or arg.lower() in ("true", "false", "null", "current_timestamp") or (arg.startswith("'") and arg.endswith("'")):
                        default_str = f" DEFAULT {arg}"
                    else:
                        default_str = f" DEFAULT '{arg}'"
                elif isinstance(arg, TextClause) or hasattr(arg, "text"):
                    default_str = f" DEFAULT {getattr(arg, 'text', str(arg))}"
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
                with sync_conn.begin_nested():
                    sync_conn.execute(text(stmt))
                added_columns.add(col.name)
                logger.info("Migrated schema: added column %s.%s (%s)", table_name, col.name, col_type)
            except Exception as exc:
                logger.warning("Could not add column %s.%s: %s", table_name, col.name, exc)

        if table_name == "coupons" and "kind" in added_columns:
            try:
                with sync_conn.begin_nested():
                    sync_conn.execute(
                        text(
                            "UPDATE coupons SET kind = 'voucher' "
                            "WHERE discount_percent = 0 AND discount_amount > 0 AND code LIKE 'GIFT-%'"
                        )
                    )
            except Exception as exc:
                logger.warning("Could not backfill legacy coupon kinds: %s", exc)

        # Inspect and create missing table indexes (e.g. partial unique indexes on upgraded DBs)
        try:
            existing_indexes = {idx["name"] for idx in inspector.get_indexes(table_name) if idx.get("name")}
        except Exception:
            existing_indexes = set()

        for idx in table.indexes:
            if idx.name and idx.name not in existing_indexes:
                try:
                    with sync_conn.begin_nested():
                        idx.create(bind=sync_conn)
                    logger.info("Migrated schema: created missing index %s on %s", idx.name, table_name)
                except Exception as exc:
                    logger.warning("Could not create index %s on %s: %s", idx.name, table_name, exc)

        # Inspect and create missing table unique constraints on PostgreSQL
        if sync_conn.dialect.name == "postgresql":
            try:
                existing_ucs = {uc["name"] for uc in inspector.get_unique_constraints(table_name) if uc.get("name")}
            except Exception:
                existing_ucs = set()

            for c in table.constraints:
                if isinstance(c, UniqueConstraint) and c.name and c.name not in existing_ucs:
                    try:
                        cols = ", ".join(f'"{col.name}"' for col in c.columns)
                        with sync_conn.begin_nested():
                            sync_conn.execute(text(f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{c.name}" UNIQUE ({cols});'))
                        logger.info("Migrated schema: added unique constraint %s on %s", c.name, table_name)
                    except Exception as exc:
                        logger.debug("Could not add unique constraint %s on %s: %s", c.name, table_name, exc)


async def init_db(engine) -> None:
    """Create all tables on boot and apply non-destructive schema migrations."""
    import bot.db.models  # noqa: F401 - ensure models registered
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_db_schema)
        dialect_name = conn.dialect.name
        if dialect_name == "postgresql":
            def _check_and_alter_postgres(sync_c):
                insp = inspect(sync_c)
                try:
                    cols = {c["name"]: c for c in insp.get_columns("crypto_invoices")}
                    comment_col = cols.get("comment")
                    if comment_col and getattr(comment_col.get("type"), "length", None) != 64:
                        with sync_c.begin_nested():
                            sync_c.execute(text("ALTER TABLE crypto_invoices ALTER COLUMN comment TYPE VARCHAR(64);"))
                    nanotons_col = cols.get("nanotons")
                    if nanotons_col and getattr(nanotons_col.get("type"), "precision", None) != 38:
                        with sync_c.begin_nested():
                            sync_c.execute(text("ALTER TABLE crypto_invoices ALTER COLUMN nanotons TYPE NUMERIC(38, 0);"))
                except Exception as e:
                    logger.debug("PostgreSQL crypto_invoices column inspection: %s", e)

                try:
                    orders_cols = {c["name"]: c for c in insp.get_columns("orders")}
                    svc_col = orders_cols.get("service_id")
                    if svc_col and svc_col.get("nullable") is False:
                        with sync_c.begin_nested():
                            sync_c.execute(text("ALTER TABLE orders ALTER COLUMN service_id DROP NOT NULL;"))
                except Exception as e:
                    logger.debug("PostgreSQL orders column inspection: %s", e)

                try:
                    with sync_c.begin_nested():
                        sync_c.execute(text(
                            "CREATE INDEX IF NOT EXISTS ix_crypto_invoices_currency ON crypto_invoices (currency);"
                        ))
                except Exception:
                    pass

            await conn.run_sync(_check_and_alter_postgres)
