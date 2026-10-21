"""Shared Pytest configuration and session-scoped fixtures.

Provides pre-initialized in-memory SQLite database and connection pooling
to eliminate redundant table creation overhead across the test suite.
"""
import sys
from pathlib import Path

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.db.models import Base


@pytest.fixture(scope="session")
def anyio_backend():
    """Default anyio backend for async test execution."""
    return "asyncio"


_shared_engine = None


async def _get_shared_engine():
    """Return session-cached in-memory SQLite engine with pre-created tables."""
    global _shared_engine
    if _shared_engine is None:
        _shared_engine = create_async_engine(
            "sqlite+aiosqlite:///file:test_shared_mem?mode=memory&cache=shared&uri=true",
            pool_pre_ping=True,
        )
        async with _shared_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    return _shared_engine


@pytest.fixture
async def shared_db_engine():
    """Function-scoped async SQLite engine reusing shared in-memory DB."""
    engine = await _get_shared_engine()
    yield engine


@pytest.fixture
async def session_factory(shared_db_engine):
    """Function-scoped session factory reusing the session-scoped engine with clean isolation."""
    factory = async_sessionmaker(shared_db_engine, expire_on_commit=False)
    yield factory
    async with shared_db_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
