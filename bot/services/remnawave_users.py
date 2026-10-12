"""Remnawave user and subscription operations mixin."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RemnawaveUsersMixin:
    """Mixin for Remnawave user and subscription lifecycle management."""

    _client: httpx.AsyncClient

    async def get_users_by_telegram_id(self, telegram_id: int) -> list[dict[str, Any]] | None:
        """Return all panel users whose `telegramId` equals the given ID.

        Remnawave endpoint: GET /api/users/stream?telegramId={telegramId}
        Returns [] when nothing was found, None when the panel is
        unreachable (so callers can tell "no account" apart from
        "panel down" and must NOT de-verify the user on None).
        """
        try:
            resp = await self._client.get(
                "/api/users/stream",
                params={"telegramId": str(telegram_id), "size": 1000},
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json().get("response") or {}
            return data.get("users") or []
        except httpx.HTTPError as exc:
            logger.error("Remnawave API error (telegram_id=%s): %s", telegram_id, exc)
            return None

    async def telegram_id_exists(self, telegram_id: int) -> bool | None:
        """True if registered, False if not found, None if panel is down."""
        users = await self.get_users_by_telegram_id(telegram_id)
        if users is None:
            return None
        return bool(users)

    async def get_all_panel_users(self, size: int = 1000) -> list[dict[str, Any]] | None:
        """Return all panel users.

        Remnawave endpoint: GET /api/users/stream?size={size} (or fallback GET /api/users).
        """
        try:
            resp = await self._client.get("/api/users/stream", params={"size": size})
            if resp.status_code == 404:
                resp = await self._client.get("/api/users", params={"size": size})
            resp.raise_for_status()
            data = resp.json().get("response") or {}
            if isinstance(data, list):
                return data
            return data.get("users") or []
        except httpx.HTTPError as exc:
            logger.error("Remnawave get_all_panel_users error: %s", exc)
            return None

    async def get_panel_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        """Return user details from the panel by user_id."""
        try:
            resp = await self._client.get(f"/api/users/{user_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json().get("response")
            return data if isinstance(data, dict) else None
        except httpx.HTTPError as exc:
            logger.error("Remnawave get_panel_user_by_id error (user_id=%s): %s", user_id, exc)
            return None

    async def reset_user_traffic(self, user_id: int) -> bool:
        """Reset consumed traffic for this user."""
        try:
            resp = await self._client.post(
                f"/api/users/{user_id}/actions/reset-traffic", json={}
            )
            if resp.status_code in (200, 201, 204):
                return True
            patch_resp = await self._client.patch(
                "/api/users",
                json={"id": user_id, "usedTrafficBytes": 0},
            )
            return patch_resp.status_code in (200, 201, 204)
        except httpx.HTTPError as exc:
            logger.error("Remnawave reset_user_traffic error (user_id=%s): %s", user_id, exc)
            return False

    async def revoke_user_subscription(self, user_id: int) -> dict[str, Any] | None:
        """Revoke subscription for user (generate new short UUID / sub link)."""
        endpoints = [
            f"/api/users/{user_id}/actions/revoke-sub",
            f"/api/users/{user_id}/actions/revoke-subscription",
            f"/api/users/{user_id}/actions/reissue",
        ]
        for ep in endpoints:
            try:
                resp = await self._client.post(ep, json={})
                if resp.status_code in (200, 201):
                    return resp.json().get("response") or resp.json()
            except httpx.HTTPError as exc:
                logger.debug("Remnawave revoke_user_subscription endpoint %s failed: %s", ep, exc)
                continue

        logger.warning("Remnawave revoke_user_subscription failed across all endpoints for user %s", user_id)
        return None

    async def get_internal_squads(self) -> list[dict[str, Any]]:
        """Fetch internal squads from Remnawave panel."""
        for path in ("/api/internal-squads", "/api/squads"):
            try:
                resp = await self._client.get(path)
                if resp.status_code == 200:
                    data = resp.json().get("response") or resp.json()
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        return data.get("internalSquads") or data.get("squads") or []
            except httpx.HTTPError as exc:
                logger.debug("Remnawave squad path %s failed: %s", path, exc)
        return []

    async def set_user_squads(self, user_id: int, squad_uuids: list[str]) -> dict[str, Any] | None:
        """Assign squad UUIDs to an existing user."""
        payload = {
            "id": user_id,
            "activeInternalSquads": squad_uuids,
        }
        try:
            resp = await self._client.patch("/api/users", json=payload)
            resp.raise_for_status()
            return resp.json().get("response")
        except httpx.HTTPError as exc:
            logger.error("Remnawave set_user_squads error (user_id=%s): %s", user_id, exc)
            return None

    async def create_user(
        self,
        username: str,
        expire_days: int,
        traffic_gb: int,
        telegram_id: int | None = None,
        squad_uuids: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Create a new user in the panel.

        Returns user dict (including `subscriptionUrl`) or None on failure.
        """
        now = datetime.now(timezone.utc)
        expire_at = now + timedelta(days=expire_days)
        traffic_bytes = traffic_gb * (1024**3)

        payload: dict[str, Any] = {
            "username": username,
            "expireAt": expire_at.isoformat(),
            "trafficLimitBytes": traffic_bytes,
        }
        if telegram_id:
            payload["telegramId"] = telegram_id
        if squad_uuids:
            payload["activeInternalSquads"] = squad_uuids

        try:
            resp = await self._client.post("/api/users", json=payload)
            resp.raise_for_status()
            return resp.json().get("response")
        except httpx.HTTPError as exc:
            logger.error("Remnawave create_user error: %s", exc)
            return None

    async def update_user_subscription(
        self,
        user_id: int,
        add_days: int = 0,
        add_traffic_gb: int = 0,
        status: str = "ACTIVE",
    ) -> dict[str, Any] | None:
        """Extend user's subscription (add days and/or traffic) and ensure status is active."""
        current = await self.get_panel_user_by_id(user_id)
        if not current:
            logger.error("Cannot update user %s: not found in panel", user_id)
            return None

        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {"id": user_id}
        if status:
            payload["status"] = status

        if add_days > 0:
            current_expire = current.get("expireAt")
            if current_expire:
                base_date = datetime.fromisoformat(current_expire.replace("Z", "+00:00"))
                if base_date < now:
                    base_date = now
            else:
                base_date = now
            new_expire = base_date + timedelta(days=add_days)
            payload["expireAt"] = new_expire.isoformat()

        if add_traffic_gb > 0:
            current_limit = current.get("trafficLimitBytes", 0) or 0
            new_limit = current_limit + (add_traffic_gb * (1024**3))
            payload["trafficLimitBytes"] = new_limit

        try:
            resp = await self._client.patch("/api/users", json=payload)
            resp.raise_for_status()
            return resp.json().get("response")
        except httpx.HTTPError as exc:
            logger.error("Remnawave update_user_subscription error (user_id=%s): %s", user_id, exc)
            return None

    async def set_user_status(self, user_id: int, status: str) -> dict[str, Any] | None:
        """Update a user's status in the Remnawave panel.

        Allowed statuses: 'active', 'disabled', 'limited', 'expired'.
        """
        payload = {
            "id": user_id,
            "status": status,
        }
        try:
            resp = await self._client.patch("/api/users", json=payload)
            resp.raise_for_status()
            return resp.json().get("response")
        except httpx.HTTPError as exc:
            logger.error("Remnawave set_user_status error (user_id=%s, status=%s): %s", user_id, status, exc)
            return None

    async def update_user_fields(self, user_id: int, **fields: Any) -> dict[str, Any] | None:
        """Update arbitrary user fields in Remnawave panel."""
        payload: dict[str, Any] = {"id": user_id, **fields}
        try:
            resp = await self._client.patch("/api/users", json=payload)
            resp.raise_for_status()
            return resp.json().get("response")
        except httpx.HTTPError as exc:
            logger.error("Remnawave update_user_fields error (user_id=%s): %s", user_id, exc)
            return None

    async def bulk_update_users(
        self,
        users_list: list[dict[str, Any]],
        extra_gb: int = 0,
        extra_days: int = 0,
    ) -> dict[str, Any]:
        """Perform bulk credit or extension across users in safe concurrent batches."""
        now_utc = datetime.now(timezone.utc)
        success_count = 0
        failed_count = 0

        async def _update_single(user: dict[str, Any]) -> bool:
            u_id = user.get("id")
            if not u_id:
                return False

            payload: dict[str, Any] = {"id": u_id}

            if extra_gb > 0:
                current_limit = int(user.get("trafficLimitBytes") or 0)
                payload["trafficLimitBytes"] = current_limit + (extra_gb * (1024**3))

            if extra_days > 0:
                current_expire_raw = user.get("expireAt") or user.get("expire")
                base_dt = now_utc
                if current_expire_raw:
                    try:
                        parsed = datetime.fromisoformat(str(current_expire_raw).replace("Z", "+00:00"))
                        if parsed > now_utc:
                            base_dt = parsed
                    except Exception as exc:
                        logger.warning("Failed to parse expire date %s: %s", current_expire_raw, exc)
                new_expire = base_dt + timedelta(days=extra_days)
                payload["expireAt"] = new_expire.isoformat()

            try:
                resp = await self._client.patch("/api/users", json=payload)
                return resp.status_code in (200, 201, 204)
            except Exception as e:
                logger.warning("Bulk update failed for user %s: %s", u_id, e)
                return False

        chunk_size = 15
        for i in range(0, len(users_list), chunk_size):
            chunk = users_list[i : i + chunk_size]
            results = await asyncio.gather(*(_update_single(u) for u in chunk), return_exceptions=True)
            for res in results:
                if res is True:
                    success_count += 1
                else:
                    failed_count += 1
            if i + chunk_size < len(users_list):
                await asyncio.sleep(0.05)

        return {
            "success_count": success_count,
            "failed_count": failed_count,
            "total": len(users_list),
        }
