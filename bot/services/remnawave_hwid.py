"""Remnawave HWID, SRH and multi-IP session auditing mixin."""
from collections import defaultdict
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RemnawaveHwidMixin:
    """Mixin for HWID device control, SRH history, and multi-IP auditing."""

    _client: httpx.AsyncClient

    async def get_user_hwid_devices(
        self, user_id: int | str, user_uuid: str | None = None
    ) -> list[dict[str, Any]]:
        """Devices registered on this user.

        Remnawave endpoints:
        - GET /api/hwid/devices/{userId or userUuid}
        - Fallback: filtered list from /api/hwid/devices
        """
        targets = []
        if user_uuid:
            targets.append(str(user_uuid))
        if user_id and str(user_id) not in targets:
            targets.append(str(user_id))

        for target in targets:
            for path in (f"/api/hwid/devices/{target}", f"/api/users/{target}/hwid/devices"):
                try:
                    resp = await self._client.get(path)
                    if resp.status_code == 200:
                        data = resp.json().get("response") or resp.json() or {}
                        devices = data.get("devices") if isinstance(data, dict) else data
                        if isinstance(devices, list):
                            return devices
                    elif resp.status_code == 404:
                        return []
                except httpx.HTTPError as exc:
                    logger.debug("Remnawave hwid path %s error (user_id=%s): %s", path, user_id, exc)

        # Fallback: scan panel devices if single endpoint is not supported on this panel version
        try:
            all_devices = await self.get_all_hwid_devices(size=500) or []
            target_ids = {str(t).lower() for t in targets}
            filtered = [
                d for d in all_devices
                if str(d.get("userId") or "").lower() in target_ids
                or str(d.get("userUuid") or (d.get("user") or {}).get("uuid") or "").lower() in target_ids
            ]
            return filtered
        except Exception as exc:
            logger.warning("Remnawave hwid list warning (user_id=%s): %s", user_id, exc)
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

    async def get_hwid_stats(self) -> dict[str, Any] | None:
        """Fetch HWID device summary statistics."""
        for path in ("/api/hwid/devices/stats", "/api/hwid/stats"):
            try:
                resp = await self._client.get(path)
                if resp.status_code == 200:
                    data = resp.json().get("response") or resp.json()
                    if isinstance(data, dict):
                        return data
            except Exception as exc:
                logger.warning("Failed to fetch HWID stats from %s: %s", path, exc)
                return None
        return None

    async def get_all_hwid_devices(self, size: int = 500) -> list[dict[str, Any]] | None:
        """Fetch registered devices across all users."""
        for path in ("/api/hwid/devices", "/api/hwid/devices/all"):
            try:
                resp = await self._client.get(path, params={"size": size})
                if resp.status_code == 200:
                    data = resp.json().get("response") or {}
                    devices = data.get("devices") if isinstance(data, dict) else data
                    if isinstance(devices, list):
                        return devices
            except Exception as exc:
                logger.warning("Failed to fetch HWID devices from %s: %s", path, exc)
                return None
        return None

    async def get_srh_stats(self) -> dict[str, Any] | None:
        """Fetch Subscription Request History (SRH) stats."""
        for path in (
            "/api/subscription-request-history/stats",
            "/api/srh/stats",
            "/api/srh",
            "/api/srh/requests",
        ):
            try:
                resp = await self._client.get(path, params={"size": 1000})
                if resp.status_code == 200:
                    return resp.json().get("response") or resp.json()
            except Exception as exc:
                logger.warning("Failed to fetch SRH stats from %s: %s", path, exc)
                return None
        return None

    async def get_user_srh(
        self,
        user_id: int | str,
        user_uuid: str | None = None,
        size: int = 50,
    ) -> list[dict[str, Any]] | None:
        """Fetch Subscription Request History for a specific panel user."""
        candidates = []
        if user_id:
            candidates.append((f"/api/users/{user_id}/subscription-request-history", {"size": size}))
            candidates.append((f"/api/users/{user_id}/srh", {"size": size}))
            candidates.append((f"/api/subscription-request-history/user/{user_id}", {"size": size}))
            candidates.append((f"/api/subscription-request-history/{user_id}", {"size": size}))
        if user_uuid and str(user_uuid) != str(user_id):
            candidates.append((f"/api/users/{user_uuid}/subscription-request-history", {"size": size}))
            candidates.append((f"/api/users/{user_uuid}/srh", {"size": size}))
            candidates.append((f"/api/subscription-request-history/user/{user_uuid}", {"size": size}))

        # Try user-specific endpoints first
        for path, params in candidates:
            try:
                resp = await self._client.get(path, params=params)
                if resp.status_code == 200:
                    data = resp.json().get("response") or resp.json()
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        records = (
                            data.get("records")
                            or data.get("requests")
                            or data.get("history")
                            or data.get("items")
                            or data.get("data")
                            or []
                        )
                        if isinstance(records, list) and records:
                            return records
            except Exception as exc:
                logger.warning("Failed to fetch user SRH from %s: %s", path, exc)
                return None

        # Try global subscription-request-history endpoint with filter or client-side filtering
        for path, params in (
            ("/api/subscription-request-history", {"userId": str(user_id), "size": size}),
            ("/api/subscription-request-history", {"userUuid": str(user_uuid or user_id), "size": size}),
            ("/api/subscription-request-history", {"size": 1000}),
            ("/api/srh", {"userId": str(user_id), "size": size}),
        ):
            try:
                resp = await self._client.get(path, params=params)
                if resp.status_code == 200:
                    data = resp.json().get("response") or resp.json()
                    records = []
                    if isinstance(data, list):
                        records = data
                    elif isinstance(data, dict):
                        records = (
                            data.get("records")
                            or data.get("requests")
                            or data.get("history")
                            or data.get("items")
                            or data.get("data")
                            or []
                        )
                    if isinstance(records, list) and records:
                        if "userId" not in params and "userUuid" not in params:
                            target_uids = {str(user_id)}
                            if user_uuid:
                                target_uids.add(str(user_uuid).lower())
                            filtered = [
                                r for r in records
                                if str(r.get("userId") or (r.get("user") or {}).get("id") or "").lower() in target_uids
                                or str(r.get("userUuid") or (r.get("user") or {}).get("uuid") or "").lower() in target_uids
                            ]
                            if filtered:
                                return filtered
                        else:
                            return records
            except Exception as exc:
                logger.warning("Failed to fetch global SRH from %s: %s", path, exc)
                return None

        return None

    async def get_multi_ip_sessions(self) -> dict[str, Any]:
        """Audit active HWID devices to detect users connected via multiple concurrent/distinct IPs."""
        devices = await self.get_all_hwid_devices(size=500) or []
        panel_users = await getattr(self, "get_all_panel_users", lambda: [])() or []
        user_map = {
            u.get("id"): u.get("username", f"User {u.get('id')}")
            for u in panel_users
            if "id" in u
        }

        user_devices: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for d in devices:
            uid = d.get("userId")
            if uid is not None:
                user_devices[uid].append(d)

        multi_ip_users = []
        for uid, d_list in user_devices.items():
            ips = {d.get("requestIp") for d in d_list if d.get("requestIp")}
            if len(ips) > 1:
                multi_ip_users.append({
                    "userId": uid,
                    "username": user_map.get(uid, f"User {uid}"),
                    "ips": sorted(list(ips)),
                    "devices": d_list,
                    "ip_count": len(ips),
                    "device_count": len(d_list),
                })

        multi_ip_users.sort(key=lambda x: (x["ip_count"], x["device_count"]), reverse=True)

        return {
            "total_users_with_devices": len(user_devices),
            "total_devices": len(devices),
            "multi_ip_users_count": len(multi_ip_users),
            "multi_ip_users": multi_ip_users,
        }
