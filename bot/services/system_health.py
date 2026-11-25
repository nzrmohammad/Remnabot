"""System Health Telemetry, Reconciliation Audit, and 5xx Spike Alerting."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text

from bot.common import admin_thread_kwargs
from bot.config import get_settings
from bot.db.models import CardAutoInvoice, CryptoInvoice, Order, Service
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.services.app_settings import get_store_settings
from bot.services.panel_snapshot import get_cached_panel_snapshot
from bot.services.task_queue import get_queue_metrics

logger = logging.getLogger(__name__)

_SUBSYSTEM_KEYS = (
    "remnawave_snapshot",
    "ton_watcher",
    "sms_webhook",
    "reconcile",
    "auto_backup",
)
_5XX_SPIKE_THRESHOLD = 5
_5XX_WINDOW_SECONDS = 300
_5XX_ALERT_COOLDOWN_SECONDS = 900


async def record_api_error_spike(
    bot: Any,
    session_factory: Any,
    cache: Any,
    *,
    status_code: int,
    path: str,
) -> bool:
    """Count 5xx errors in a 5-minute rolling bucket and alert Admin topic on spikes."""
    if not cache or not hasattr(cache, "incr") or status_code < 500:
        return False
    bucket = int(time.time()) // _5XX_WINDOW_SECONDS
    err_key = f"health:err5xx:bucket:{bucket}"
    try:
        count = int(await cache.incr(err_key, ttl_seconds=_5XX_WINDOW_SECONDS * 2))
        if count < _5XX_SPIKE_THRESHOLD:
            return False
        if hasattr(cache, "set_nx"):
            can_alert = await cache.set_nx(
                "health:err5xx:alert_cooldown",
                "1",
                ttl_seconds=_5XX_ALERT_COOLDOWN_SECONDS,
            )
            if not can_alert:
                return False
        if not bot:
            return False
        settings = get_settings()
        admin_chat_id = getattr(settings, "ADMIN_CHAT_ID", None)
        if not admin_chat_id:
            return False
        thread_kwargs = {}
        if session_factory:
            try:
                async with session_factory() as sess:
                    store = await get_store_settings(sess)
                    thread_kwargs = admin_thread_kwargs(store, settings, kind="errors")
            except Exception:
                pass
        from html import escape
        msg = (
            "🚨 <b>هشدار افزایش ناگهانی خطاهای سرور (5xx Spike)</b>\n"
            "──────────────────\n"
            f"⚠️ تعداد <b>{count}</b> خطای <code>HTTP {status_code}+</code> در ۵ دقیقه اخیر ثبت شده است.\n"
            f"📍 آخرین مسیر خطا: <code>{escape(str(path)[:120])}</code>\n"
            "لطفاً وضعیت پنل Remnawave، دیتابیس و لاگ‌های سرور را بررسی نمایید."
        )
        await bot.send_message(admin_chat_id, msg, parse_mode="HTML", **thread_kwargs)
        return True
    except Exception as exc:
        logger.debug("record_api_error_spike failed: %s", exc)
        return False


def _inspect_latest_backup(backup_dir: Path) -> dict[str, Any]:
    """Return latest local backup archive metadata without blocking on large I/O."""
    if not backup_dir.exists() or not backup_dir.is_dir():
        return {"exists": False, "filename": None, "size_mb": 0.0, "age_hours": None, "encrypted": False}
    files = sorted(
        (f for f in backup_dir.glob("remnabot_backup_*") if f.is_file()),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return {"exists": False, "filename": None, "size_mb": 0.0, "age_hours": None, "encrypted": False}
    newest = files[0]
    stat = newest.stat()
    age_hours = round(max(0.0, (time.time() - stat.st_mtime) / 3600.0), 1)
    return {
        "exists": True,
        "filename": newest.name,
        "size_mb": round(stat.st_size / (1024 * 1024), 2),
        "age_hours": age_hours,
        "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "encrypted": newest.suffix.lower() == ".zip",
    }


async def collect_reconciliation_audit(
    session: Any,
    panel_users: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute cross-check mismatches between local paid/pending records and Remnawave panel."""
    now_utc = datetime.now(timezone.utc)
    stale_cutoff = now_utc - timedelta(minutes=15)

    stale_orders = int(
        (await session.execute(
            select(func.count(Order.id)).where(Order.status == "pending", Order.created_at <= stale_cutoff)
        )).scalar_one() or 0
    )
    stalled_crypto = int(
        (await session.execute(
            select(func.count(CryptoInvoice.id)).where(
                CryptoInvoice.status == "pending",
                CryptoInvoice.expires_at.is_not(None),
                CryptoInvoice.expires_at <= now_utc,
            )
        )).scalar_one() or 0
    )
    stalled_card_auto = int(
        (await session.execute(
            select(func.count(CardAutoInvoice.id)).where(
                CardAutoInvoice.status == "pending",
                CardAutoInvoice.expires_at.is_not(None),
                CardAutoInvoice.expires_at <= now_utc,
            )
        )).scalar_one() or 0
    )

    mismatches: list[dict[str, Any]] = []
    if panel_users:
        panel_by_id = {str(u.get("id")): u for u in panel_users if u.get("id") is not None}
        recent_paid_res = await session.execute(
            select(Order, Service.name)
            .outerjoin(Service, Order.service_id == Service.id)
            .where(Order.status == "paid", Order.panel_user_id.is_not(None))
            .order_by(Order.id.desc())
            .limit(150)
        )
        seen_panel_ids: set[str] = set()
        for order, svc_name in recent_paid_res.all():
            pid = str(order.panel_user_id)
            if pid in seen_panel_ids:
                continue
            seen_panel_ids.add(pid)
            p_acc = panel_by_id.get(pid)
            if p_acc is None:
                mismatches.append({
                    "order_id": order.id,
                    "telegram_id": order.telegram_id,
                    "panel_user_id": pid,
                    "service_name": svc_name or "سرویس",
                    "issue": "missing_on_panel",
                    "issue_label": "اکانت در پنل یافت نشد",
                    "created_at": order.created_at.isoformat() if order.created_at else "",
                })
                if len(mismatches) >= 15:
                    break

    return {
        "stale_pending_orders": stale_orders,
        "stalled_crypto_invoices": stalled_crypto,
        "stalled_card_invoices": stalled_card_auto,
        "panel_mismatches_count": len(mismatches),
        "panel_mismatches": mismatches,
    }


async def collect_system_health(
    session: Any,
    remnawave: Any,
    cache: Any = None,
    *,
    settings: Any = None,
    backup_dir: Path = Path("backups"),
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Gather holistic system diagnostics (DB, Redis, Remnawave, Backup, Watchers, Reconcile, Queue)."""
    cfg = settings or get_settings()

    # 1. DB latency probe
    db_ok = True
    db_latency_ms = 0.0
    try:
        t0 = time.monotonic()
        await session.execute(text("SELECT 1"))
        db_latency_ms = round((time.monotonic() - t0) * 1000.0, 1)
    except Exception as exc:
        db_ok = False
        logger.warning("System health DB probe failed: %s", exc)

    # 2. Redis latency probe
    redis_client = getattr(cache, "_redis", None) if cache else None
    redis_status = "disabled"
    redis_latency_ms: float | None = None
    if redis_client is not None:
        try:
            t0 = time.monotonic()
            await redis_client.ping()
            redis_latency_ms = round((time.monotonic() - t0) * 1000.0, 1)
            redis_status = "connected"
        except Exception as exc:
            logger.warning("System health Redis ping failed: %s", exc)
            redis_status = "error"

    # 3. Remnawave snapshot & latency
    snap = await get_cached_panel_snapshot(remnawave, cache, force_refresh=force_refresh)
    panel_health = {
        "healthy": bool(snap.get("healthy", False)),
        "latency_ms": snap.get("latency_ms"),
        "nodes_online": int(snap.get("nodes_online") or 0),
        "nodes_total": int(snap.get("nodes_total") or 0),
        "panel_users_count": int(snap.get("panel_users_count") or 0),
        "updated_at": snap.get("updated_at"),
    }

    # 4. Backup metadata
    backup_info = _inspect_latest_backup(backup_dir)
    backup_info["password_configured"] = bool(getattr(cfg, "BACKUP_PASSWORD", ""))
    try:
        app_repo = AppSettingRepository(session)
        last_bkp = await app_repo.get("last_admin_backup_msg_record")
        backup_info["last_telegram_record"] = bool(last_bkp)
    except Exception:
        backup_info["last_telegram_record"] = False

    # 5. Subsystem heartbeats
    watchers: dict[str, Any] = {}
    if cache and hasattr(cache, "get"):
        for name in _SUBSYSTEM_KEYS:
            try:
                watchers[name] = await cache.get(f"health:subsys:{name}")
            except Exception:
                watchers[name] = None

    # 6. Reconciliation cross-check & Queue metrics
    reconcile_summary = await collect_reconciliation_audit(session, snap.get("panel_users") or [])
    queue_summary = await get_queue_metrics(cache)

    return {
        "db": {"ok": db_ok, "latency_ms": db_latency_ms},
        "redis": {"status": redis_status, "latency_ms": redis_latency_ms},
        "remnawave": panel_health,
        "backup": backup_info,
        "watchers": watchers,
        "reconciliation": reconcile_summary,
        "queue": queue_summary,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
