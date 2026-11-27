"""Event-loop-scoped shared aiohttp.ClientSession pool for outbound HTTP requests."""
from __future__ import annotations

import asyncio
import weakref
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import aiohttp

_ORIG_CLIENT_SESSION = aiohttp.ClientSession
_LOOP_SESSIONS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, aiohttp.ClientSession] = (
    weakref.WeakKeyDictionary()
)


class _PooledSessionView:
    """Thin per-call wrapper applying default timeout/headers over one pooled ClientSession."""

    __slots__ = ("_session", "_timeout", "_headers")

    def __init__(
        self,
        session: aiohttp.ClientSession,
        timeout: aiohttp.ClientTimeout | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._session = session
        self._timeout = timeout
        self._headers = headers

    def _merge(self, kwargs: dict) -> dict:
        if self._timeout is not None and "timeout" not in kwargs:
            kwargs["timeout"] = self._timeout
        if self._headers:
            req_headers = kwargs.get("headers")
            kwargs["headers"] = {**self._headers, **(req_headers or {})}
        return kwargs

    def get(self, url: str, **kwargs):
        return self._session.get(url, **self._merge(kwargs))

    def post(self, url: str, **kwargs):
        return self._session.post(url, **self._merge(kwargs))

    def request(self, method: str, url: str, **kwargs):
        return self._session.request(method, url, **self._merge(kwargs))

    def __getattr__(self, name: str):
        return getattr(self._session, name)


@asynccontextmanager
async def shared_http_session(
    *,
    timeout: aiohttp.ClientTimeout | None = None,
    headers: dict[str, str] | None = None,
) -> AsyncIterator[aiohttp.ClientSession | _PooledSessionView]:
    """Yield a shared pooled ClientSession for the running event loop (or patched test ClientSession)."""
    if aiohttp.ClientSession is not _ORIG_CLIENT_SESSION:
        kw = {}
        if timeout is not None:
            kw["timeout"] = timeout
        if headers is not None:
            kw["headers"] = headers
        async with aiohttp.ClientSession(**kw) as patched_session:
            yield patched_session
        return

    loop = asyncio.get_running_loop()
    sess = _LOOP_SESSIONS.get(loop)
    if sess is None or sess.closed:
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=20, ttl_dns_cache=300)
        sess = _ORIG_CLIENT_SESSION(connector=connector)
        _LOOP_SESSIONS[loop] = sess
    if timeout is None and not headers:
        yield sess
    else:
        yield _PooledSessionView(sess, timeout=timeout, headers=headers)


async def close_http_sessions() -> None:
    """Close all tracked shared aiohttp ClientSessions cleanly on shutdown."""
    for sess in list(_LOOP_SESSIONS.values()):
        if not sess.closed:
            await sess.close()
    _LOOP_SESSIONS.clear()
