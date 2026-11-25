"""Async client for the Remnawave panel REST API.

Modularized into domain mixins:
- RemnawaveUsersMixin: User CRUD, squad assignment, bulk updates, traffic reset.
- RemnawaveHwidMixin: HWID registration, device limits, SRH history, multi-IP audit.
- RemnawaveSystemMixin: Node telemetry, bandwidth statistics, live session explorer.
"""
import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from bot.services.remnawave_hwid import RemnawaveHwidMixin
from bot.services.remnawave_system import RemnawaveSystemMixin
from bot.services.remnawave_users import RemnawaveUsersMixin

logger = logging.getLogger(__name__)

_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE"})

# Reusable tenacity retry decorator for transient network failures
panel_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, min=0.2, max=1.5),
    retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
    reraise=True,
)


class RemnawaveClient(RemnawaveUsersMixin, RemnawaveHwidMixin, RemnawaveSystemMixin):
    """Unified client for the Remnawave REST API."""

    def __init__(self, base_url: str, token: str, timeout: float = 15.0):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        # Retry idempotent requests on transient errors without duplicating non-idempotent POST calls
        raw_request = self._client.request
        retrying_request = panel_retry(raw_request)

        async def _safe_request(method: str, *args, **kwargs):
            if str(method).upper() in _IDEMPOTENT_METHODS:
                return await retrying_request(method, *args, **kwargs)
            return await raw_request(method, *args, **kwargs)

        _safe_request.retry = retrying_request.retry
        self._client.request = _safe_request

    async def close(self) -> None:
        await self._client.aclose()


__all__ = [
    "RemnawaveClient",
    "RemnawaveUsersMixin",
    "RemnawaveHwidMixin",
    "RemnawaveSystemMixin",
    "panel_retry",
]
