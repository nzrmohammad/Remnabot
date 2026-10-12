"""Shared Pytest configuration and session-scoped fixtures.

Provides pre-initialized in-memory SQLite database and connection pooling
to eliminate redundant table creation overhead across the test suite.
"""
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


@pytest.fixture(scope="session")
async def shared_db_engine():
    """Session-scoped async SQLite engine."""
    engine = await _get_shared_engine()
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(shared_db_engine):
    """Function-scoped session factory reusing the session-scoped engine."""
    return async_sessionmaker(shared_db_engine, expire_on_commit=False)
