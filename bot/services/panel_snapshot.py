"""Cached Remnawave cluster snapshot service + background warmer."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

SNAPSHOT_CLUSTER_KEY = "snapshot:remnawave:cluster"
SNAPSHOT_HEALTH_KEY = "snapshot:remnawave:health"
SNAPSHOT_TTL_SECONDS = 180
SNAPSHOT_INTERVAL_SECONDS = 90

_SNAPSHOT_LOCK = asyncio.Lock()


async def record_subsystem_heartbeat(
    cache: Any,
    name: str,
    *,
    status: str = "ok",
    latency_ms: float | None = None,
    detail: str = "",
) -> None:
    """Persist lightweight subsystem heartbeat metadata into Redis/FastCache."""
    if not (cache and hasattr(cache, "set")):
        return
    payload = {
        "name": name,
        "status": status,
        "latency_ms": latency_ms,
        "detail": detail[:200] if detail else "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "timestamp": int(time.time()),
    }
    try:
        await cache.set(f"health:subsys:{name}", payload, ttl_seconds=86400)
    except Exception:
        pass


async def refresh_panel_snapshot(
    remnawave: Any,
    cache: Any = None,
    *,
    warm_charts: bool = False,
) -> dict[str, Any]:
    """Fetch nodes, panel users, and HWID stats once, caching snapshot + lightweight API RTT."""
    async with _SNAPSHOT_LOCK:
        async def _probe_nodes() -> tuple[Any, float]:
            t_ping = time.monotonic()
            nodes_res = await remnawave.get_nodes()
            return nodes_res, round((time.monotonic() - t_ping) * 1000.0, 1)

        from bot.web.admin_overview_nodes import fetch_panel_billing_nodes

        t0 = time.monotonic()
        results = await asyncio.gather(
            _probe_nodes(),
            remnawave.get_all_panel_users(size=1000),
            remnawave.get_hwid_stats(),
            fetch_panel_billing_nodes(remnawave),
            return_exceptions=True,
        )
        nodes_probe, raw_users, raw_hwid, raw_infra_billing = results
        if isinstance(nodes_probe, Exception):
            raw_nodes = nodes_probe
            latency_ms = round((time.monotonic() - t0) * 1000.0, 1)
        else:
            raw_nodes, latency_ms = nodes_probe
        nodes_ok = isinstance(raw_nodes, list)
        users_ok = isinstance(raw_users, list)
        nodes = raw_nodes if nodes_ok else []
        panel_users = raw_users if users_ok else []
        hwid_stats = raw_hwid if isinstance(raw_hwid, dict) else {}
        infra_billing_nodes = raw_infra_billing if isinstance(raw_infra_billing, list) else []

        nodes_online = sum(1 for n in nodes if n.get("isConnected") and not n.get("isDisabled"))
        active_users = sum(1 for u in panel_users if str(u.get("status", "")).upper() == "ACTIVE")
        healthy = bool(nodes_ok or users_ok)

        snapshot = {
            "nodes": nodes,
            "panel_users": panel_users,
            "hwid_stats": hwid_stats,
            "infra_billing_nodes": infra_billing_nodes,
            "latency_ms": latency_ms,
            "healthy": healthy,
            "nodes_online": nodes_online,
            "nodes_total": len(nodes),
            "panel_users_count": len(panel_users),
            "active_panel_users_count": active_users,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "timestamp": int(time.time()),
        }

        if cache and hasattr(cache, "set"):
            try:
                # Only cache cluster data if at least one upstream list succeeded
                if healthy:
                    await cache.set(SNAPSHOT_CLUSTER_KEY, snapshot, ttl_seconds=SNAPSHOT_TTL_SECONDS)
                await cache.set(
                    SNAPSHOT_HEALTH_KEY,
                    {
                        "healthy": healthy,
                        "latency_ms": latency_ms,
                        "nodes_online": nodes_online,
                        "nodes_total": len(nodes),
                        "panel_users_count": len(panel_users),
                        "updated_at": snapshot["updated_at"],
                        "timestamp": snapshot["timestamp"],
                    },
                    ttl_seconds=SNAPSHOT_TTL_SECONDS * 2,
                )
            except Exception as exc:
                logger.debug("Panel snapshot cache store error: %s", exc)

        if warm_charts and healthy and cache is not None:
            try:
                from bot.web.admin_overview_charts import get_periodic_users_bandwidth
                await get_periodic_users_bandwidth(
                    remnawave, cache, panel_users, datetime.now(timezone.utc), is_refresh=False
                )
            except Exception as chart_err:
                logger.debug("Snapshot chart warmer skipped: %s", chart_err)

        await record_subsystem_heartbeat(
            cache,
            "remnawave_snapshot",
            status="ok" if healthy else "error",
            latency_ms=latency_ms,
            detail=f"nodes={nodes_online}/{len(nodes)} users={len(panel_users)}",
        )
        return snapshot


async def get_cached_panel_snapshot(
    remnawave: Any,
    cache: Any = None,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Return Redis-cached Remnawave cluster snapshot when warm, otherwise refresh singleflight."""
    if not force_refresh and cache and hasattr(cache, "get"):
        try:
            snap = await cache.get(SNAPSHOT_CLUSTER_KEY)
            if isinstance(snap, dict) and "nodes" in snap and "panel_users" in snap:
                return snap
        except Exception:
            pass
    return await refresh_panel_snapshot(remnawave, cache)


async def remnawave_snapshot_loop(
    remnawave: Any,
    cache: Any,
    interval_seconds: int = SNAPSHOT_INTERVAL_SECONDS,
) -> None:
    """Periodic background loop warming Redis cluster snapshot every 90s."""
    await asyncio.sleep(10)
    logger.info("Remnawave snapshot loop started (every %ds)", interval_seconds)
    while True:
        try:
            await refresh_panel_snapshot(remnawave, cache, warm_charts=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Remnawave snapshot loop error: %s", exc)
        await asyncio.sleep(interval_seconds)
