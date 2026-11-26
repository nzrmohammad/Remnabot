"""Remnawave system metrics, nodes, and live sessions mixin."""
import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_LIVE_EXPLORER_CACHE_TTL = 10.0


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
            if resp.status_code in (400, 404, 422):
                return None
            resp.raise_for_status()
            data = resp.json().get("response") or {}
            return data.get("series") or []
        except httpx.HTTPError as exc:
            logger.debug("Remnawave bandwidth-stats error (user_id=%s): %s", user_id, exc)
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
            total = 0
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
        """Return all nodes from the panel with retry on transient 5xx."""
        for attempt in range(2):
            try:
                resp = await self._client.get("/api/nodes")
                if resp.status_code == 404:
                    return []
                resp.raise_for_status()
                data = resp.json().get("response") or {}
                if isinstance(data, list):
                    return data
                return data.get("nodes") or []
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (500, 502, 503, 504) and attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                logger.warning("Remnawave get_nodes upstream error (status=%s): %s", exc.response.status_code, exc)
                return None
            except httpx.HTTPError as exc:
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                logger.warning("Remnawave get_nodes error: %s", exc)
                return None
        return None

    async def get_live_sessions_explorer(
        self, ttl_seconds: float = _LIVE_EXPLORER_CACHE_TTL, force_refresh: bool = False
    ) -> dict[str, Any]:
        """Scan real-time active connections across online nodes (with singleflight lock + short TTL cache)."""
        now = time.monotonic()
        cached = getattr(self, "_live_explorer_cache", None)
        if not force_refresh and ttl_seconds > 0 and cached is not None:
            expires_at, cached_payload = cached
            if now < expires_at:
                return cached_payload

        lock = getattr(self, "_live_explorer_lock", None)
        if lock is None:
            lock = asyncio.Lock()
            self._live_explorer_lock = lock

        async with lock:
            now = time.monotonic()
            cached = getattr(self, "_live_explorer_cache", None)
            if not force_refresh and ttl_seconds > 0 and cached is not None:
                expires_at, cached_payload = cached
                if now < expires_at:
                    return cached_payload

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

            result_payload = {
                "total_users_online": len(agg),
                "total_connections": total_connections,
                "total_unique_ips": len(all_unique_ips),
                "nodes_scanned": len(valid_nodes),
                "total_nodes": len(online_nodes),
                "multi_ip_users": multi_ip_users,
                "all_online_users": all_sorted,
                "top_active_users": all_sorted,
            }
            if ttl_seconds > 0:
                self._live_explorer_cache = (time.monotonic() + ttl_seconds, result_payload)
            return result_payload

    async def get_user_live_sessions(self, user_id: int | str) -> dict[str, Any]:
        """Get live sessions for a user, preferring direct endpoints before falling back to explorer."""
        if getattr(self, "_direct_user_conn_supported", True) and hasattr(self, "_client"):
            for path in (f"/api/connections/by-user/{user_id}", f"/api/users/{user_id}/connections"):
                try:
                    resp = await self._client.get(path, timeout=3.0)
                    if resp.status_code == 200:
                        raw = resp.json().get("response") or resp.json()
                        if isinstance(raw, dict) and ("nodeConnections" in raw or "ips" in raw or "connections" in raw):
                            conns = raw.get("nodeConnections") or raw.get("connections") or []
                            ips_raw = raw.get("uniqueIps") or raw.get("ips") or []
                            ips_list = sorted({str(i.get("ip") if isinstance(i, dict) else i) for i in ips_raw if i})
                            return {
                                "isOnline": bool(conns or ips_list or raw.get("isOnline")),
                                "totalConnections": int(raw.get("totalConnections") or len(ips_list) or len(conns)),
                                "uniqueIps": ips_list,
                                "nodeConnections": conns if isinstance(conns, list) else [],
                            }
                except Exception:
                    continue
            self._direct_user_conn_supported = False

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
                continue
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
                continue
        return None

    async def get_infra_providers(self) -> list[dict[str, Any]]:
        """Fetch configured infrastructure billing providers from the Remnawave panel."""
        for path in ("/api/infra-billing/providers", "/api/infra/providers"):
            try:
                resp = await self._client.get(path)
                if resp.status_code != 200:
                    continue
                body = resp.json()
                inner = body.get("response") if isinstance(body, dict) else body
                if isinstance(inner, dict):
                    items = inner.get("providers") or inner.get("items") or []
                elif isinstance(inner, list):
                    items = inner
                else:
                    items = body.get("providers") or [] if isinstance(body, dict) else []
                providers = []
                for p in items:
                    if not isinstance(p, dict):
                        continue
                    p_uuid = str(p.get("uuid") or p.get("id") or "").strip()
                    p_name = str(p.get("name") or "").strip()
                    if p_uuid and p_name:
                        providers.append({
                            "uuid": p_uuid,
                            "name": p_name,
                            "login": p.get("loginUrl") or p.get("login") or "",
                            "icon_url": p.get("faviconLink") or p.get("iconUrl") or "",
                        })
                return providers
            except Exception as exc:
                logger.warning("Failed to fetch infra providers from %s: %s", path, exc)
                continue
        return []

    @staticmethod
    def _extract_panel_error(resp: Any) -> str:
        """Extract readable error detail from a Remnawave HTTP response."""
        try:
            data = resp.json()
            if isinstance(data, dict):
                raw_msg = data.get("message") or data.get("error") or ""
                msg = ", ".join(str(x) for x in raw_msg) if isinstance(raw_msg, list) else str(raw_msg or "")
                errors = data.get("errors")
                if isinstance(errors, list) and errors:
                    details = []
                    for err in errors[:3]:
                        if isinstance(err, dict):
                            path = ".".join(str(p) for p in (err.get("path") or []) if p is not None)
                            emsg = str(err.get("message") or err.get("code") or err)
                            details.append(f"{path}: {emsg}" if path else emsg)
                        elif err:
                            details.append(str(err))
                    if details:
                        detail_str = "; ".join(details)
                        return f"{msg} ({detail_str})" if msg else detail_str
                if msg:
                    return msg
        except Exception:
            pass
        return f"HTTP {getattr(resp, 'status_code', '?')}"

    async def update_node(
        self, node_uuid: str, fields: dict[str, Any]
    ) -> tuple[bool, dict[str, Any] | str]:
        """Update Remnawave node settings (multipliers, tracking, description, providerUuid)."""
        node_uuid = str(node_uuid or "").strip()
        if not node_uuid:
            return False, "شناسه نود معتبر نیست."

        payload: dict[str, Any] = {"uuid": node_uuid}
        payload.update(fields)

        async def _patch(body: dict[str, Any]):
            return await self._client.patch("/api/nodes", json=body)

        try:
            resp = await _patch(payload)
            if resp.status_code in (200, 201):
                data = resp.json()
                node_obj = data.get("response") if isinstance(data, dict) else {}
                return True, node_obj if isinstance(node_obj, dict) else {}

            err_text = self._extract_panel_error(resp)
            # Older Remnawave panels (< v2.8.1) reject unknown nodeConsumptionMultiplier
            if resp.status_code in (400, 422) and "nodeConsumptionMultiplier" in payload and "nodeConsumptionMultiplier" in err_text:
                retry_payload = {k: v for k, v in payload.items() if k != "nodeConsumptionMultiplier"}
                resp = await _patch(retry_payload)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    node_obj = data.get("response") if isinstance(data, dict) else {}
                    return True, node_obj if isinstance(node_obj, dict) else {}
                err_text = self._extract_panel_error(resp)
                payload = retry_payload

            # Some panel schemas require name/address/port alongside updated fields
            if resp.status_code in (400, 422) and any(k in err_text for k in ("name", "address", "port")):
                nodes = await self.get_nodes() or []
                current = next(
                    (n for n in nodes if str(n.get("uuid") or n.get("id") or "") == node_uuid),
                    None,
                )
                if isinstance(current, dict):
                    merged = dict(payload)
                    for req_key in ("name", "address", "port"):
                        if req_key not in merged and current.get(req_key) is not None:
                            merged[req_key] = current.get(req_key)
                    resp = await _patch(merged)
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        node_obj = data.get("response") if isinstance(data, dict) else {}
                        return True, node_obj if isinstance(node_obj, dict) else {}
                    err_text = self._extract_panel_error(resp)

            return False, err_text
        except httpx.HTTPError as exc:
            logger.error("Remnawave update_node error (uuid=%s): %s", node_uuid, exc)
            return False, str(exc)

    async def restart_node(
        self, node_uuid: str, *, force_restart: bool = False
    ) -> tuple[bool, str]:
        """Restart a single Remnawave node via panel REST API."""
        node_uuid = str(node_uuid or "").strip()
        if not node_uuid:
            return False, "شناسه نود معتبر نیست."

        url = f"/api/nodes/{node_uuid}/actions/restart"
        try:
            resp = await self._client.post(url, json={"forceRestart": bool(force_restart)})
            if resp.status_code == 400 and "forceRestart" in self._extract_panel_error(resp):
                resp = await self._client.post(url, json={})
            if resp.status_code in (200, 201, 202, 204):
                return True, "دستور ریستارت سرور با موفقیت به پنل ارسال شد."
            return False, self._extract_panel_error(resp)
        except httpx.HTTPError as exc:
            logger.error("Remnawave restart_node error (uuid=%s): %s", node_uuid, exc)
            return False, str(exc)
