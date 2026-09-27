"""Async client for the Remnawave panel REST API.

Only the endpoints the bot currently needs are implemented.
Extend this class as the project grows (subscriptions, traffic, etc.).
"""
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RemnawaveClient:
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

    # ------------------------------------------------------------------ #
    # Users
    # ------------------------------------------------------------------ #
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
                "/api/users", json={"id": user_id, "usedTrafficBytes": 0}
            )
            return patch_resp.status_code in (200, 201, 204)
        except httpx.HTTPError as exc:
            logger.error("Remnawave reset traffic error (user_id=%s): %s", user_id, exc)
            return False

    async def revoke_user_subscription(self, user_id: int) -> dict[str, Any] | None:
        """Regenerate the user's subscription link (new short UUID).

        Remnawave endpoint: POST /api/users/{userId}/actions/revoke
        Returns the updated user object (with the new `subscriptionUrl`),
        or None on failure.
        """
        try:
            resp = await self._client.post(
                f"/api/users/{user_id}/actions/revoke", json={}
            )
            resp.raise_for_status()
            data = resp.json().get("response")
            return data if isinstance(data, dict) else None
        except httpx.HTTPError as exc:
            logger.error("Remnawave revoke error (user_id=%s): %s", user_id, exc)
            return None

    # Alias for convenience
    revoke_user_sub = revoke_user_subscription

    async def get_internal_squads(self) -> list[dict[str, Any]]:
        """Return all internal squads.

        Remnawave endpoint: GET /api/internal-squads
        """
        try:
            resp = await self._client.get("/api/internal-squads")
            resp.raise_for_status()
            data = resp.json().get("response") or {}
            squads = data.get("internalSquads") or []
            return squads if isinstance(squads, list) else []
        except httpx.HTTPError as exc:
            logger.error("Remnawave get_internal_squads error: %s", exc)
            return []

    async def set_user_squads(self, user_id: int, squad_uuids: list[str]) -> dict[str, Any] | None:
        """Update active internal squads for a panel user."""
        try:
            resp = await self._client.patch(
                "/api/users", json={"id": user_id, "activeInternalSquads": squad_uuids}
            )
            resp.raise_for_status()
            data = resp.json().get("response")
            return data if isinstance(data, dict) else None
        except httpx.HTTPError as exc:
            logger.error("Remnawave set_user_squads error (user_id=%s): %s", user_id, exc)
            return None

    async def create_user(
        self,
        username: str,
        expire_at_iso: str,
        traffic_limit_bytes: int,
        telegram_id: int,
        traffic_limit_strategy: str = "NO_RESET",
        hwid_device_limit: int | None = None,
        internal_squads: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Create a new panel user with an active subscription.

        Remnawave endpoint: POST /api/users
        Returns the created user object (with `id`, `shortUuid`,
        `subscriptionUrl`), or None on failure.
        """
        payload: dict[str, Any] = {
            "username": username,
            "status": "ACTIVE",
            "expireAt": expire_at_iso,
            "trafficLimitBytes": traffic_limit_bytes,
            "trafficLimitStrategy": traffic_limit_strategy,
            "telegramId": telegram_id,
        }
        if hwid_device_limit is not None:
            payload["hwidDeviceLimit"] = hwid_device_limit
        if internal_squads:
            payload["activeInternalSquads"] = list(internal_squads)
        try:
            resp = await self._client.post("/api/users", json=payload)
            resp.raise_for_status()
            data = resp.json().get("response")
            return data if isinstance(data, dict) else None
        except httpx.HTTPError as exc:
            logger.error("Remnawave create user error (username=%s): %s", username, exc)
            return None

    async def update_user_subscription(
        self,
        user_id: int,
        expire_at_iso: str,
        traffic_limit_bytes: int,
        traffic_limit_strategy: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any] | None:
        """Extend / renew an existing panel user's subscription.

        Remnawave endpoint: PATCH /api/users
        `status="ACTIVE"` reactivates accounts the expiry job auto-disabled,
        so a renewal never leaves the user paid-but-disabled.
        Returns the updated user object, or None on failure.
        """
        payload: dict[str, Any] = {
            "id": user_id,
            "expireAt": expire_at_iso,
            "trafficLimitBytes": traffic_limit_bytes,
        }
        if traffic_limit_strategy:
            payload["trafficLimitStrategy"] = traffic_limit_strategy
        if status:
            payload["status"] = status
        try:
            resp = await self._client.patch("/api/users", json=payload)
            resp.raise_for_status()
            data = resp.json().get("response")
            return data if isinstance(data, dict) else None
        except httpx.HTTPError as exc:
            logger.error("Remnawave update user error (user_id=%s): %s", user_id, exc)
            return None

    async def set_user_status(self, user_id: int, status: str) -> dict[str, Any] | None:
        """Enable/disable a panel user (ACTIVE / DISABLED).

        Remnawave endpoint: PATCH /api/users with {"id", "status"}.
        Returns the updated user object, or None on failure.
        """
        try:
            resp = await self._client.patch(
                "/api/users", json={"id": user_id, "status": status}
            )
            resp.raise_for_status()
            data = resp.json().get("response")
            return data if isinstance(data, dict) else None
        except httpx.HTTPError as exc:
            logger.error("Remnawave set-status error (user_id=%s): %s", user_id, exc)
            return None

    async def update_user_fields(self, user_id: int, **fields: Any) -> dict[str, Any] | None:
        """Update arbitrary user fields (e.g. hwidDeviceLimit, telegramId, description).

        Remnawave endpoint: PATCH /api/users
        """
        payload = {"id": user_id, **fields}
        try:
            resp = await self._client.patch("/api/users", json=payload)
            resp.raise_for_status()
            data = resp.json().get("response")
            return data if isinstance(data, dict) else None
        except httpx.HTTPError as exc:
            logger.error("Remnawave update_user_fields error (user_id=%s): %s", user_id, exc)
            return None

    # ------------------------------------------------------------------ #
    # HWID devices
    # ------------------------------------------------------------------ #
    async def get_user_hwid_devices(self, user_id: int) -> list[dict[str, Any]]:
        """Devices registered on this user.

        Remnawave endpoint: GET /api/hwid/devices/{userId}
        """
        try:
            resp = await self._client.get(f"/api/hwid/devices/{user_id}")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json().get("response") or {}
            devices = data.get("devices")
            return devices if isinstance(devices, list) else []
        except httpx.HTTPError as exc:
            logger.error("Remnawave hwid list error (user_id=%s): %s", user_id, exc)
            return []

    async def delete_hwid_device(self, user_id: int, hwid: str) -> bool:
        """Remove one device from the user.

        Remnawave endpoint: POST /api/hwid/devices/delete
        """
        try:
            resp = await self._client.post(
                "/api/hwid/devices/delete",
                json={"userId": user_id, "hwid": hwid},
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.error("Remnawave hwid delete error (user_id=%s): %s", user_id, exc)
            return False

    async def get_user_bandwidth_stats(
        self, user_id: int, start_date: str, end_date: str
    ) -> list[dict[str, Any]] | None:
        """Per-node bandwidth of one user within [start_date, end_date].

        Remnawave endpoint:
        GET /api/bandwidth-stats/users/{userId}?start=YYYY-MM-DD&end=YYYY-MM-DD
        Returns None when the endpoint does not exist on this panel version.
        """
        try:
            resp = await self._client.get(
                f"/api/bandwidth-stats/users/{user_id}",
                params={"start": start_date, "end": end_date},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json().get("response") or {}
            return data.get("series") or []
        except httpx.HTTPError as exc:
            logger.error("Remnawave bandwidth-stats error (user_id=%s): %s", user_id, exc)
            return None

    async def get_user_today_usage(
        self, user_id: int, start_iso: str, end_iso: str
    ) -> tuple[int, list[dict[str, Any]]]:
        """(total_bytes, per-node rows) consumed between start and end.

        Each row: {"name": str, "countryCode": str | None, "total": int},
        sorted by usage descending, zero-usage nodes dropped.
        """
        raw = await self.get_user_bandwidth_stats(user_id, start_iso[:10], end_iso[:10])
        if raw is None:
            return 0, []

        rows: list[dict[str, Any]] = []
        for row in raw:
            value = row.get("total") or row.get("totalBytes") or 0
            try:
                total = int(float(value))
            except (TypeError, ValueError):
                continue
            if total <= 0:
                continue
            rows.append(
                {
                    "name": row.get("name") or row.get("nodeName") or "",
                    "countryCode": row.get("countryCode"),
                    "total": total,
                }
            )
        rows.sort(key=lambda r: r["total"], reverse=True)
        return sum(r["total"] for r in rows), rows

    # ------------------------------------------------------------------ #
    # Nodes
    # ------------------------------------------------------------------ #
    async def get_nodes(self) -> list[dict[str, Any]] | None:
        """Return all nodes from the panel.

        Remnawave endpoint: GET /api/nodes
        """
        try:
            resp = await self._client.get("/api/nodes")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json().get("response") or {}
            if isinstance(data, list):
                return data
            return data.get("nodes") or []
        except httpx.HTTPError as exc:
            logger.error("Remnawave get_nodes error: %s", exc)
            return None

    # ------------------------------------------------------------------ #
    # Inspectors & Diagnostics (HWID, SRH, Sessions, System)
    # ------------------------------------------------------------------ #
    async def get_hwid_stats(self) -> dict[str, Any] | None:
        """Fetch HWID device summary statistics."""
        for path in ("/api/hwid/devices/stats", "/api/hwid/stats"):
            try:
                resp = await self._client.get(path)
                if resp.status_code == 200:
                    data = resp.json().get("response") or resp.json()
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return None

    async def get_all_hwid_devices(self, size: int = 50) -> list[dict[str, Any]]:
        """Fetch registered devices across all users."""
        for path in ("/api/hwid/devices", "/api/hwid/devices/all"):
            try:
                resp = await self._client.get(path, params={"size": size})
                if resp.status_code == 200:
                    data = resp.json().get("response") or {}
                    devices = data.get("devices") if isinstance(data, dict) else data
                    if isinstance(devices, list):
                        return devices
            except Exception:
                pass
        return []

    async def get_srh_stats(self) -> dict[str, Any] | None:
        """Fetch Subscription Request History (SRH) stats."""
        for path in ("/api/srh/stats", "/api/srh", "/api/srh/requests"):
            try:
                resp = await self._client.get(path, params={"size": 30})
                if resp.status_code == 200:
                    return resp.json().get("response") or resp.json()
            except Exception:
                pass
        return None

    async def get_active_sessions(self) -> list[dict[str, Any]] | None:
        """Fetch active user sessions and connection telemetry."""
        for path in ("/api/sessions", "/api/v1/sessions/active", "/api/sessions/active"):
            try:
                resp = await self._client.get(path)
                if resp.status_code == 200:
                    data = resp.json().get("response") or resp.json()
                    sessions = data.get("sessions") if isinstance(data, dict) else data
                    if isinstance(sessions, list):
                        return sessions
            except Exception:
                pass
        return None

    async def get_system_digest(self) -> dict[str, Any] | None:
        """Fetch host and panel system metrics/digest."""
        for path in ("/api/system/stats/digest", "/api/system/info", "/api/system/stats", "/api/system"):
            try:
                resp = await self._client.get(path)
                if resp.status_code == 200:
                    data = resp.json().get("response") or resp.json()
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return None

