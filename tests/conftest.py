"""Shared Pytest configuration and session-scoped fixtures.

Provides pre-initialized in-memory SQLite database and connection pooling
to eliminate redundant table creation overhead across the test suite.
"""
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

# Register explicit Python 3.12+ SQLite date/datetime adapters to avoid deprecated default adapter warnings.
sqlite3.register_adapter(datetime, lambda val: val.isoformat(sep=" "))
sqlite3.register_adapter(date, lambda val: val.isoformat())

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Mock default required settings for CI/testing environments without .env
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz")
os.environ.setdefault("ADMIN_CHAT_ID", "-1001234567890")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REMNAWAVE_BASE_URL", "https://mock-panel.local")
os.environ.setdefault("REMNAWAVE_TOKEN", "mock_token")

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.db.models import Base


@pytest.fixture(scope="session")
def anyio_backend():
    """Default anyio backend for async test execution."""
    return "asyncio"


_shared_sqlite_engine = None
_pg_schema_ready = False


async def _get_shared_sqlite_engine():
    """Return process-cached SQLite in-memory engine with FK enforcement enabled."""
    global _shared_sqlite_engine
    if _shared_sqlite_engine is None:
        from sqlalchemy.pool import StaticPool

        worker = os.environ.get("PYTEST_XDIST_WORKER") or f"p{os.getpid()}"
        _shared_sqlite_engine = create_async_engine(
            f"sqlite+aiosqlite:///file:test_shared_mem_{worker}?mode=memory&cache=shared&uri=true",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(_shared_sqlite_engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        async with _shared_sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    return _shared_sqlite_engine


@pytest.fixture
async def shared_db_engine():
    """Function-scoped async DB engine: NullPool on PostgreSQL avoids cross-loop Future errors."""
    global _pg_schema_ready
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url.startswith("postgresql"):
        from sqlalchemy.pool import NullPool

        engine = create_async_engine(db_url, poolclass=NullPool)
        if not _pg_schema_ready:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            _pg_schema_ready = True
        try:
            yield engine
        finally:
            await engine.dispose()
    else:
        yield await _get_shared_sqlite_engine()


@pytest.fixture
async def session_factory(shared_db_engine):
    """Function-scoped session factory reusing the schema with clean per-test isolation."""
    db_url = os.environ.get("DATABASE_URL", "")
    is_pg = db_url.startswith("postgresql")
    if not is_pg:
        async with shared_db_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(shared_db_engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        async with shared_db_engine.begin() as conn:
            if is_pg:
                table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
                if table_names:
                    await conn.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
            else:
                await conn.execute(text("PRAGMA foreign_keys=OFF"))
                try:
                    for table in reversed(Base.metadata.sorted_tables):
                        await conn.execute(table.delete())
                finally:
                    await conn.execute(text("PRAGMA foreign_keys=ON"))
