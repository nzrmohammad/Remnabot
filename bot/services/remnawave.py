"""Async client for the Remnawave panel REST API.

Modularized into domain mixins:
- RemnawaveUsersMixin: User CRUD, squad assignment, bulk updates, traffic reset.
- RemnawaveHwidMixin: HWID registration, device limits, SRH history, multi-IP audit.
- RemnawaveSystemMixin: Node telemetry, bandwidth statistics, live session explorer.
"""
import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from bot.services.remnawave_users import RemnawaveUsersMixin
from bot.services.remnawave_hwid import RemnawaveHwidMixin
from bot.services.remnawave_system import RemnawaveSystemMixin

logger = logging.getLogger(__name__)

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

    async def close(self) -> None:
        await self._client.aclose()


__all__ = [
    "RemnawaveClient",
    "RemnawaveUsersMixin",
    "RemnawaveHwidMixin",
    "RemnawaveSystemMixin",
    "panel_retry",
]
