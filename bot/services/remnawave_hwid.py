"""Remnawave HWID, SRH and multi-IP session auditing mixin."""
import logging
from collections import defaultdict
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

    @staticmethod
    def _clean_srh_ident(val: Any) -> str | None:
        if val is None:
            return None
        s = str(val).strip()
        if not s or s.lower() in ("none", "null", "undefined"):
            return None
        return s

    @staticmethod
    def _extract_srh_records(data: Any) -> tuple[list[dict[str, Any]] | None, bool]:
        """Extract record list and whether response explicitly represents an SRH container."""
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)], True
        if isinstance(data, dict):
            for key in ("records", "requests", "history", "items", "data"):
                val = data.get(key)
                if isinstance(val, list):
                    return [r for r in val if isinstance(r, dict)], True
        return None, False

    @staticmethod
    def _filter_srh_records(
        records: list[dict[str, Any]],
        target_uids: set[str],
        allow_untagged: bool,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Filter SRH records to target_uids whenever user identifiers exist on records."""
        def _record_uids(r: dict[str, Any]) -> set[str]:
            u_obj = r.get("user") if isinstance(r.get("user"), dict) else {}
            candidates = (
                r.get("userId"),
                r.get("user_id"),
                r.get("userUuid"),
                r.get("user_uuid"),
                u_obj.get("id"),
                u_obj.get("uuid"),
            )
            return {
                str(c).strip().lower()
                for c in candidates
                if c is not None and str(c).strip().lower() not in ("", "none", "null", "undefined")
            }

        has_user_fields = any(bool(_record_uids(r)) for r in records)
        if has_user_fields:
            return [r for r in records if _record_uids(r) & target_uids], True
        if allow_untagged:
            return list(records), False
        return [], False

    async def get_user_srh(
        self,
        user_id: int | str,
        user_uuid: str | None = None,
        size: int = 50,
    ) -> list[dict[str, Any]] | None:
        """Fetch Subscription Request History for a specific panel user."""
        clean_id = self._clean_srh_ident(user_id)
        clean_uuid = self._clean_srh_ident(user_uuid)
        target_uids = {s.lower() for s in (clean_id, clean_uuid) if s}
        if not target_uids:
            return []

        ordered_uids: list[str] = []
        if clean_uuid:
            ordered_uids.append(clean_uuid)
        if clean_id and clean_id not in ordered_uids:
            ordered_uids.append(clean_id)

        candidates: list[tuple[str, dict[str, Any]]] = []
        for uid in ordered_uids:
            candidates.append((f"/api/users/{uid}/subscription-request-history", {"size": size}))
            candidates.append((f"/api/users/{uid}/srh", {"size": size}))
            candidates.append((f"/api/subscription-request-history/user/{uid}", {"size": size}))
            candidates.append((f"/api/subscription-request-history/{uid}", {"size": size}))

        # Try user-specific endpoints first
        for path, params in candidates:
            try:
                resp = await self._client.get(path, params=params)
                if resp.status_code != 200:
                    continue
                raw_json = resp.json()
                data = raw_json.get("response") if isinstance(raw_json, dict) and "response" in raw_json else raw_json
                records, is_srh_shape = self._extract_srh_records(data)
                if not is_srh_shape or records is None:
                    continue
                if not records:
                    return []
                filtered, had_uids = self._filter_srh_records(records, target_uids, allow_untagged=True)
                if filtered:
                    return filtered[:size]
                if had_uids:
                    # Endpoint returned records belonging to other users (e.g. ignored path param)
                    continue
            except Exception as exc:
                logger.debug("Failed to fetch user SRH from %s: %s", path, exc)
                continue

        # Fallback: global subscription-request-history endpoint, ALWAYS filtered locally if user fields exist
        global_size = max(size, 1000)
        global_candidates: list[tuple[str, dict[str, Any], bool]] = []
        if clean_uuid:
            global_candidates.append(("/api/subscription-request-history", {"userUuid": clean_uuid, "size": global_size}, True))
        if clean_id:
            global_candidates.append(("/api/subscription-request-history", {"userId": clean_id, "size": global_size}, True))
        global_candidates.append(("/api/subscription-request-history", {"size": global_size}, False))
        if clean_id:
            global_candidates.append(("/api/srh", {"userId": clean_id, "size": global_size}, True))

        saw_valid_global_empty = False
        for path, params, has_filter_param in global_candidates:
            try:
                resp = await self._client.get(path, params=params)
                if resp.status_code != 200:
                    continue
                raw_json = resp.json()
                data = raw_json.get("response") if isinstance(raw_json, dict) and "response" in raw_json else raw_json
                records, is_srh_shape = self._extract_srh_records(data)
                if not is_srh_shape or records is None:
                    continue
                if not records:
                    saw_valid_global_empty = True
                    continue
                filtered, had_uids = self._filter_srh_records(
                    records,
                    target_uids,
                    allow_untagged=has_filter_param,
                )
                if filtered:
                    return filtered[:size]
                if had_uids:
                    # Global list contained other users' records and none for this user
                    return []
            except Exception as exc:
                logger.debug("Failed to fetch global SRH from %s: %s", path, exc)
                continue

        return [] if saw_valid_global_empty else None

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
