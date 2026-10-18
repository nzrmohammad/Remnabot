"""Database session helpers for WebApp request handlers."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def db_session(request: web.Request) -> AsyncIterator[AsyncSession]:
    """Provide an AsyncSession context from request.app['session_factory'] or request['session']."""
    if "session" in request:
        yield request["session"]
        return
    session_factory = request.app.get("session_factory")
    if session_factory is None:
        yield None
        return
    async with session_factory() as session:
        yield session
