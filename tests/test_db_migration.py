import pytest
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import create_async_engine
from bot.db.base import Base, _migrate_db, init_db


@pytest.mark.anyio
async def test_db_migration_adds_missing_columns():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # 1. Create a legacy table without the new columns
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE services (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(64) NOT NULL,
                    price BIGINT NOT NULL,
                    duration_days INTEGER NOT NULL,
                    traffic_gb INTEGER NOT NULL,
                    description TEXT,
                    is_active BOOLEAN DEFAULT 1
                )
                """
            )
        )

    # Verify column does NOT exist yet
    async with engine.connect() as conn:
        def check_cols(sync_conn):
            inspector = inspect(sync_conn)
            return {c["name"] for c in inspector.get_columns("services")}
        cols_before = await conn.run_sync(check_cols)
        assert "max_purchases" not in cols_before
        assert "purchases_count" not in cols_before

    # 2. Run init_db which triggers _migrate_db
    await init_db(engine)

    # 3. Verify missing columns WERE added
    async with engine.connect() as conn:
        cols_after = await conn.run_sync(check_cols)
        assert "max_purchases" in cols_after
        assert "purchases_count" in cols_after
        assert "badge" in cols_after
        assert "squad_uuid" in cols_after

    await engine.dispose()
