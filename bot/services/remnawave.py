"""Async client for the Remnawave panel REST API.

Only the endpoints the bot currently needs are implemented.
Extend this class as the project grows (subscriptions, traffic, etc.).
"""
import asyncio
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

    async def get_all_hwid_devices(self, size: int = 500) -> list[dict[str, Any]]:
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
        for path in (
            "/api/subscription-request-history/stats",
            "/api/srh/stats",
            "/api/srh",
            "/api/srh/requests",
        ):
            try:
                resp = await self._client.get(path, params={"size": 100})
                if resp.status_code == 200:
                    return resp.json().get("response") or resp.json()
            except Exception:
                pass
        return None

    async def get_live_sessions_explorer(self) -> dict[str, Any]:
        """Scan real-time active connections across all online nodes to match Sessions Explorer in Remnawave v3."""
        nodes = await self.get_nodes() or []
        online_nodes = [n for n in nodes if n.get("isConnected") and not n.get("isDisabled")]

        async def scan_node(node: dict[str, Any]) -> dict[str, Any] | None:
            uuid = node.get("uuid")
            if not uuid:
                return None
            try:
                resp = await self._client.post(f"/api/connections/by-node/{uuid}", timeout=8.0)
                if resp.status_code not in (200, 201):
                    return None
                job_id = resp.json().get("response", {}).get("jobId")
                if not job_id:
                    return None
                for _ in range(12):
                    await asyncio.sleep(0.5)
                    r_res = await self._client.get(f"/api/connections/by-node/{job_id}", timeout=8.0)
                    if r_res.status_code == 200:
                        data = r_res.json().get("response") or {}
                        if data.get("isCompleted"):
                            result = data.get("result") or {}
                            if result.get("success"):
                                return {
                                    "nodeUuid": uuid,
                                    "nodeName": node.get("name") or "Node",
                                    "countryCode": node.get("countryCode"),
                                    "users": result.get("users") or [],
                                }
                            return None
            except Exception:
                return None
            return None

        node_results = await asyncio.gather(*(scan_node(n) for n in online_nodes))
        valid_nodes = [r for r in node_results if r is not None]

        panel_users = await self.get_all_panel_users() or []
        user_map = {u["id"]: u.get("username", f"User {u['id']}") for u in panel_users if "id" in u}

        # Aggregate users across nodes
        agg: dict[int, dict[str, Any]] = {}
        total_connections = 0
        all_unique_ips: set[str] = set()

        for nr in valid_nodes:
            n_name = nr["nodeName"]
            c_code = nr.get("countryCode")
            for u in nr["users"]:
                uid = u.get("userId")
                if uid is None:
                    continue
                if uid not in agg:
                    agg[uid] = {
                        "userId": uid,
                        "username": user_map.get(uid, f"User {uid}"),
                        "uniqueIps": set(),
                        "totalConnections": 0,
                        "nodeConnections": [],
                    }
                ips_list = [item.get("ip") for item in u.get("ips", []) if item.get("ip")]
                agg[uid]["nodeConnections"].append({
                    "nodeName": n_name,
                    "countryCode": c_code,
                    "ips": ips_list,
                })
                for ip in ips_list:
                    agg[uid]["uniqueIps"].add(ip)
                    all_unique_ips.add(ip)
                agg[uid]["totalConnections"] += len(ips_list)
                total_connections += len(ips_list)

        all_sorted = sorted(
            agg.values(),
            key=lambda x: (len(x["uniqueIps"]), x["totalConnections"]),
            reverse=True,
        )

        multi_ip_users = [u for u in all_sorted if len(u["uniqueIps"]) > 1]

        return {
            "total_users_online": len(agg),
            "total_connections": total_connections,
            "total_unique_ips": len(all_unique_ips),
            "nodes_scanned": len(valid_nodes),
            "total_nodes": len(online_nodes),
            "multi_ip_users": multi_ip_users,
            "all_online_users": all_sorted,
        }

    async def get_user_live_sessions(self, user_id: int | str) -> dict[str, Any]:
        """Scan active connections and find live sessions for a specific user across all nodes."""
        explorer = await self.get_live_sessions_explorer()
        all_online = explorer.get("all_online_users", [])
        user_id_int = int(user_id) if str(user_id).isdigit() else user_id
        for u in all_online:
            if u.get("userId") == user_id_int or str(u.get("userId")) == str(user_id):
                ips = list(u.get("uniqueIps", []))
                if isinstance(ips, set):
                    ips = sorted(list(ips))
                return {
                    "isOnline": True,
                    "totalConnections": u.get("totalConnections", 0),
                    "uniqueIps": ips,
                    "nodeConnections": u.get("nodeConnections", []),
                }
        return {
            "isOnline": False,
            "totalConnections": 0,
            "uniqueIps": [],
            "nodeConnections": [],
        }

    async def get_multi_ip_sessions(self) -> dict[str, Any]:
        """Audit active HWID devices to detect users connected via multiple concurrent/distinct IPs."""
        devices = await self.get_all_hwid_devices(size=500)
        panel_users = await self.get_all_panel_users() or []
        user_map = {
            u.get("id"): u.get("username", f"User {u.get('id')}")
            for u in panel_users
            if "id" in u
        }

        from collections import defaultdict
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

    async def get_system_recap(self) -> dict[str, Any] | None:
        """Fetch system recap/overview from Remnawave."""
        for path in (
            "/api/system/stats/recap",
            "/api/system/stats",
            "/api/system/stats/digest",
            "/api/system/info",
        ):
            try:
                resp = await self._client.get(path)
                if resp.status_code == 200:
                    data = resp.json().get("response") or resp.json()
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return None


