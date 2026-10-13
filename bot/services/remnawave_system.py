"""Remnawave system metrics, nodes, and live sessions mixin."""
import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RemnawaveSystemMixin:
    """Mixin for Remnawave nodes, system telemetry, and live sessions."""

    _client: httpx.AsyncClient

    async def get_user_bandwidth_stats(
        self, user_id: int, start_date: str, end_date: str
    ) -> list[dict[str, Any]] | None:
        """Per-node bandwidth of one user within [start_date, end_date]."""
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
            logger.warning("Remnawave bandwidth-stats error (user_id=%s): %s", user_id, exc)
            return None

    async def get_user_today_usage(
        self, user_id: int, start_iso: str, end_iso: str
    ) -> tuple[int, list[dict[str, Any]]]:
        """(total_bytes, per-node rows) consumed between start and end."""
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

    async def get_nodes(self) -> list[dict[str, Any]] | None:
        """Return all nodes from the panel."""
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
            except Exception as exc:
                logger.warning("Failed to scan node %s: %s", uuid, exc)
                return None
            return None

        node_results = await asyncio.gather(*(scan_node(n) for n in online_nodes))
        valid_nodes = [r for r in node_results if r is not None]

        panel_users = await getattr(self, "get_all_panel_users", lambda: [])() or []
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
            except Exception as exc:
                logger.warning("Failed to fetch active sessions from %s: %s", path, exc)
                return None
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
            except Exception as exc:
                logger.warning("Failed to fetch system digest from %s: %s", path, exc)
                return None
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
            except Exception as exc:
                logger.warning("Failed to fetch system recap from %s: %s", path, exc)
                return None
        return None

    async def get_system_nodes_metrics(self) -> dict[str, Any] | list[Any] | None:
        """Fetch system-level node telemetry & metrics from Remnawave."""
        for path in ("/api/system/nodes/metrics", "/api/system/nodes", "/api/system/metrics"):
            try:
                resp = await self._client.get(path, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json().get("response") or resp.json()
                    return data
            except Exception as exc:
                logger.warning("Failed to fetch system nodes metrics from %s: %s", path, exc)
                return None
        return None
