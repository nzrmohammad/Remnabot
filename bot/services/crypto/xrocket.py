"""xRocket payment gateway client (t.me/xrocket / pay.xrocket.tg)."""
import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

XROCKET_BASE_URL = "https://pay.xrocket.tg"


class XRocketClient:
    """Async client for xRocket Pay API."""

    def __init__(self, api_key: str):
        self.api_key = api_key.strip()
        self.headers = {
            "Rocket-Pay-Key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "Remnabot/1.0",
        }

    async def create_invoice(
        self,
        amount_usd: float,
        currency: str = "USDT",
        description: str = "شارژ کیف پول",
        payload: str = "",
        callback_url: str = "",
        return_url: str = "",
    ) -> dict[str, Any] | None:
        """Create a new invoice in xRocket Pay.

        Returns invoice data including 'link' (t.me/xrocket link) or None on failure.
        """
        if not self.api_key:
            return None

        body = {
            "amount": round(amount_usd, 2),
            "currency": currency.upper(),
            "description": description[:100],
            "hidden": False,
        }
        if payload:
            body["payload"] = payload[:255]
        if callback_url:
            body["callbackUrl"] = callback_url
        if return_url:
            body["returnUrl"] = return_url

        url = f"{XROCKET_BASE_URL}/tg-invoices"
        timeout = aiohttp.ClientTimeout(total=8)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=body, headers=self.headers) as resp:
                    if resp.status in (200, 201):
                        res = await resp.json()
                        if res.get("success") and "data" in res:
                            return res["data"]
                    else:
                        err_text = await resp.text()
                        logger.warning("xRocket create_invoice error (%s): %s", resp.status, err_text)
        except Exception as exc:
            logger.warning("xRocket create_invoice exception: %s", exc)

        return None

    async def get_invoice(self, invoice_id: str | int) -> dict[str, Any] | None:
        """Fetch invoice status from xRocket."""
        if not self.api_key:
            return None

        url = f"{XROCKET_BASE_URL}/tg-invoices/{invoice_id}"
        timeout = aiohttp.ClientTimeout(total=6)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        res = await resp.json()
                        if res.get("success") and "data" in res:
                            return res["data"]
        except Exception as exc:
            logger.warning("xRocket get_invoice exception: %s", exc)

        return None
