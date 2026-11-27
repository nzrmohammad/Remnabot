"""Background job: Real-time Node Health and Resource Monitor.

Monitors nodes every 2 minutes:
1. Sends Telegram alerts to admins if any node goes OFFLINE.
2. Sends alert if memory (RAM) or CPU exceeds 90%.
3. Sends recovery notification when an offline node comes back ONLINE.
4. Prevents duplicate alert spam via cooldown timestamps.
"""
import asyncio
import html
import logging
from datetime import datetime, timezone
from typing import Any

from aiogram import Bot

from bot.config import get_settings
from bot.services.formatting import country_flag, format_datetime, ltr_frag, now_tz
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)

# In-memory alert state: {node_id_or_name: {"is_offline": bool, "last_alert_ts": float}}
_NODE_STATES: dict[str, dict[str, Any]] = {}
COOLDOWN_SECONDS = 3600  # 1 hour cooldown for repeated high-resource or offline alerts


async def _notify_admins(bot: Bot, text: str, session_factory: Any = None) -> bool:
    """Send alert message to the dedicated alerts topic in the admin group, fallback to super admins."""
    settings = get_settings()
    from bot.services.admin_notifier import send_admin_topic_notification
    msg = await send_admin_topic_notification(
        bot=bot,
        text=text,
        kind="nodes",
        session_factory=session_factory,
        settings=settings,
    )
    return msg is not None


async def check_nodes_health_once(
    bot: Bot, remnawave: RemnawaveClient, session_factory: Any = None
) -> None:
    """Run one health check iteration across all cluster nodes."""
    try:
        nodes = await remnawave.get_nodes()
        if not nodes:
            return
    except Exception as exc:
        logger.warning("Failed to fetch nodes for health monitor: %s", exc)
        return

    settings = get_settings()
    now_ts = datetime.now(timezone.utc).timestamp()
    now_dt = now_tz(settings.TIMEZONE)
    shamsi_time = format_datetime(now_dt, "fa")

    for n in nodes:
        node_id = str(n.get("id") or n.get("uuid") or n.get("name") or "unknown")
        raw_name = str(n.get("name") or "Node")
        safe_name = html.escape(raw_name)
        country_code = n.get("countryCode") or n.get("country_code")
        flag = country_flag(country_code) if country_code else "🌐"
        address = str(n.get("address") or "—")
        safe_address = html.escape(address)
        online_users = int(n.get("usersOnline") or n.get("connectionCount") or 0)

        is_connected = n.get("isConnected")
        if is_connected is None:
            is_connected = str(n.get("status", "")).upper() in ("CONNECTED", "ONLINE")

        state = _NODE_STATES.setdefault(node_id, {"is_offline": False, "last_alert_ts": 0.0})

        # --- 1. Offline Check ---
        if not is_connected:
            # If newly offline or cooldown expired (dampen flapping with minimum 5-min gap)
            time_since_alert = now_ts - state["last_alert_ts"]
            if (not state["is_offline"] and time_since_alert > min(300.0, COOLDOWN_SECONDS)) or (time_since_alert > COOLDOWN_SECONDS):
                state["is_offline"] = True
                state["last_alert_ts"] = now_ts
                msg = (
                    f"🚨 <b>هشدار قطعی سرور (Node Offline)</b>\n\n"
                    f"سرور: <b>{flag} {safe_name}</b>\n"
                    f"آدرس: <code>{safe_address}</code>\n"
                    f"وضعیت: ❌ <b>آفلاین / قطع اتصال</b>\n"
                    f"کاربران متأثر: <b>{online_users} نفر</b>\n"
                    f"زمان بررسی: <code>{shamsi_time}</code>"
                )
                await _notify_admins(bot, msg, session_factory=session_factory)
        else:
            # Node is connected
            if state["is_offline"]:
                # Was offline before, now recovered!
                state["is_offline"] = False
                state["last_alert_ts"] = now_ts
                msg = (
                    f"✅ <b>اتصال سرور برقرار شد (Node Recovered)</b>\n\n"
                    f"سرور: <b>{flag} {safe_name}</b>\n"
                    f"آدرس: <code>{safe_address}</code>\n"
                    f"وضعیت: 🟢 <b>آنلاین</b>\n"
                    f"زمان بازیابی: <code>{shamsi_time}</code>"
                )
                await _notify_admins(bot, msg, session_factory=session_factory)

            # --- 2. Resource Overload Check (RAM / CPU > 90%) ---
            sys_info = n.get("system") or n.get("sys") or n.get("metrics") or {}
            raw_cpu = sys_info.get("cpu") or sys_info.get("cpuUsage") or n.get("cpu") or 0
            raw_ram = sys_info.get("ram") or sys_info.get("memory") or sys_info.get("memoryUsage") or n.get("memory") or 0

            cpu = float(raw_cpu) * 100.0 if 0.0 < float(raw_cpu) <= 1.0 else float(raw_cpu)
            ram = float(raw_ram) * 100.0 if 0.0 < float(raw_ram) <= 1.0 else float(raw_ram)

            if (ram >= 90.0 or cpu >= 90.0) and (now_ts - state["last_alert_ts"] > COOLDOWN_SECONDS):
                state["last_alert_ts"] = now_ts
                msg = (
                    f"⚠️ <b>هشدار فشار سنگین منابع (High Resource Alert)</b>\n\n"
                    f"سرور: <b>{flag} {safe_name}</b>\n"
                    f"مصرف رم (RAM): <b>{ram:.1f}%</b>\n"
                    f"مصرف پردازنده (CPU): <b>{cpu:.1f}%</b>\n"
                    f"کاربران آنلاین: <b>{online_users} نفر</b>\n"
                    f"زمان بررسی: <code>{shamsi_time}</code>\n\n"
                    f"توصیه: ترافیک یا سرویس‌های سرور را بررسی فرمایید."
                )
                await _notify_admins(bot, msg, session_factory=session_factory)

            # --- 3. Panel Track-Traffic Quota Alert ---
            is_track = bool(n.get("isTrafficTrackingActive"))
            try:
                limit_bytes = int(n.get("trafficLimitBytes") or 0)
                used_bytes = int(n.get("trafficUsedBytes") or n.get("usedTrafficBytes") or 0)
                notify_pct = int(n.get("notifyPercent") or 0)
            except (TypeError, ValueError):
                limit_bytes, used_bytes, notify_pct = 0, 0, 0

            if is_track and limit_bytes > 0 and notify_pct > 0:
                used_pct = (used_bytes / limit_bytes) * 100.0
                last_traffic_ts = float(state.get("last_traffic_alert_ts") or 0.0)
                if used_pct >= notify_pct and (now_ts - last_traffic_ts > COOLDOWN_SECONDS * 6):
                    state["last_traffic_alert_ts"] = now_ts
                    used_gb = used_bytes / (1024 ** 3)
                    limit_gb = limit_bytes / (1024 ** 3)
                    usage_str = ltr_frag(f"{used_gb:.1f} / {limit_gb:.1f} GB ({used_pct:.1f}%)")
                    msg = (
                        f"📊 <b>هشدار مصرف ترافیک سرور (Node Traffic Alert)</b>\n\n"
                        f"سرور: <b>{flag} {safe_name}</b>\n"
                        f"مصرف فعلی: <b>{usage_str}</b>\n"
                        f"آستانه هشدار تنظیم‌شده: <b>{notify_pct}%</b>\n"
                        f"زمان بررسی: <code>{shamsi_time}</code>\n\n"
                        f"توصیه: برای جلوگیری از محدودیت ترافیک سرور، وضعیت مصرف یا پلن هاست را بررسی کنید."
                    )
                    await _notify_admins(bot, msg, session_factory=session_factory)


# Track panel-only infra-billing alerts to avoid duplicate notifications per due day
_PANEL_BILLING_ALERTED: dict[str, str] = {}


async def check_nodes_billing_due_dates(
    bot: Bot, session_factory: Any, remnawave: Any = None
) -> None:
    """Check if any nodes are approaching their billing due date (<= 3 days) and alert admins."""
    if not session_factory:
        return
    try:
        from bot.db.repositories.node_cost_repo import NodeCostRepository
        from bot.web.admin_overview_nodes import (
            extract_panel_billing_map,
            fetch_panel_billing_nodes,
        )

        settings = get_settings()
        raw_tz = getattr(settings, "TIMEZONE", "Asia/Tehran")
        tz_name = raw_tz if isinstance(raw_tz, str) and raw_tz else "Asia/Tehran"
        now_local = now_tz(tz_name)

        panel_billing_map: dict[str, dict[str, Any]] = {}
        panel_node_names: dict[str, str] = {}
        raw_bn = await fetch_panel_billing_nodes(remnawave) if remnawave else []
        if raw_bn:
            panel_billing_map = extract_panel_billing_map(raw_bn)
            if panel_billing_map and hasattr(remnawave, "get_nodes"):
                try:
                    raw_nodes = await remnawave.get_nodes() or []
                    if isinstance(raw_nodes, list):
                        for rn in raw_nodes:
                            if isinstance(rn, dict) and rn.get("uuid"):
                                panel_node_names[str(rn["uuid"])] = str(rn.get("name") or "")
                except Exception as panel_exc:
                    logger.debug("Panel node name fetch skipped: %s", panel_exc)

        async with session_factory() as session:
            repo = NodeCostRepository(session)
            all_local = await repo.list_all()
            local_by_uuid = {str(n.node_uuid): n for n in all_local}

            # Sync panel nextBillingAt updates into local NodeCost rows if dates differ
            for nuuid, pinfo in panel_billing_map.items():
                p_dt = pinfo.get("next_billing_dt")
                existing = local_by_uuid.get(nuuid)
                if p_dt is not None and existing is not None:
                    if existing.due_date is None or existing.due_date.date() != p_dt.date():
                        existing.due_date = p_dt
                        existing.alert_notified = False
                        if pinfo.get("provider_name") and not existing.provider:
                            existing.provider = pinfo["provider_name"]

            due_nodes = await repo.list_due_soon(days_threshold=3, reference_date=now_local)

            for node in due_nodes:
                if not node.due_date:
                    continue
                days_left = (node.due_date.date() - now_local.date()).days
                node_name = html.escape(node.node_name or f"Node {node.node_id or (node.node_uuid[:8] if node.node_uuid else '')}")
                provider = html.escape(node.provider or "نامشخص")

                cost_parts = []
                if node.monthly_cost_toman:
                    cost_parts.append(f"{node.monthly_cost_toman:,} تومان")
                if node.monthly_cost_eur:
                    curr_sym = "$" if getattr(node, "currency", "EUR") == "USD" else "€"
                    cost_parts.append(f"{curr_sym}{node.monthly_cost_eur:.2f}")
                cost_str = " / ".join(cost_parts) if cost_parts else "ثبت نشده"

                due_date_str = node.due_date.strftime("%Y-%m-%d")

                if days_left < 0:
                    status_text = f"🚨 <b>سررسید منقضی شده است! ({abs(days_left)} روز گذشته)</b>"
                elif days_left == 0:
                    status_text = "⚠️ <b>موعد سررسید امروز است!</b>"
                else:
                    status_text = f"⏳ <b>فقط {days_left} روز تا موعد تمدید باقی مانده</b>"

                msg = (
                    f"💳 <b>هشدار موعد تمدید سرور (Server Billing Due)</b>\n\n"
                    f"سرور: <b>🖥️ {node_name}</b>\n"
                    f"ارائه‌دهنده: <b>{provider}</b>\n"
                    f"هزینه ماهانه: <b>{cost_str}</b>\n"
                    f"تاریخ سررسید: <code>{due_date_str}</code>\n"
                    f"وضعیت: {status_text}\n\n"
                    f"لطفاً جهت جلوگیری از مسدود شدن یا حذف سرور نسبت به پرداخت فاکتور اقدام فرمایید."
                )
                delivered = await _notify_admins(bot, msg, session_factory=session_factory)
                if delivered:
                    await repo.mark_alert_sent(node.node_uuid, True)
                else:
                    logger.warning("Node billing due alert delivery failed for %s; will retry next cycle.", node.node_uuid)

            # Also notify for panel-only infra-billing nodes not yet saved in local node_costs
            for nuuid, pinfo in panel_billing_map.items():
                if nuuid in local_by_uuid:
                    continue
                p_dt = pinfo.get("next_billing_dt")
                if p_dt is None:
                    continue
                days_left = (p_dt.date() - now_local.date()).days
                due_date_str = p_dt.strftime("%Y-%m-%d")
                if days_left > 3 or _PANEL_BILLING_ALERTED.get(nuuid) == due_date_str:
                    continue
                node_name = html.escape(panel_node_names.get(nuuid) or nuuid[:8])
                provider = html.escape(pinfo.get("provider_name") or "پنل Remnawave")
                status_text = (
                    f"🚨 <b>سررسید منقضی شده است! ({abs(days_left)} روز گذشته)</b>"
                    if days_left < 0
                    else ("⚠️ <b>موعد سررسید امروز است!</b>" if days_left == 0 else f"⏳ <b>فقط {days_left} روز تا موعد تمدید باقی مانده</b>")
                )
                msg = (
                    f"💳 <b>هشدار موعد تمدید سرور (Infra Billing پنل)</b>\n\n"
                    f"سرور: <b>🖥️ {node_name}</b>\n"
                    f"ارائه‌دهنده: <b>{provider}</b>\n"
                    f"تاریخ سررسید: <code>{due_date_str}</code>\n"
                    f"وضعیت: {status_text}\n\n"
                    f"لطفاً جهت جلوگیری از مسدود شدن سرور نسبت به ثبت پرداخت و تمدید اقدام فرمایید."
                )
                if await _notify_admins(bot, msg, session_factory=session_factory):
                    _PANEL_BILLING_ALERTED[nuuid] = due_date_str

            await session.commit()
    except Exception as exc:
        logger.warning("Error checking node billing due dates: %s", exc)


# Track alerted SSL domains: {domain: last_alert_timestamp}
_SSL_ALERTED: dict[str, float] = {}


async def check_ssl_certificates_due_dates(
    bot: Bot, session_factory: Any = None, remnawave: Any = None
) -> None:
    """Check SSL certificate expirations for custom and system domains and alert admins if expiring <= 7 days."""
    if not session_factory:
        return
    try:
        from bot.services.ssl_checker import check_domains_ssl, get_system_ssl_domains
        async with session_factory() as session:
            domain_items = await get_system_ssl_domains(remnawave, session)
        if not domain_items:
            return

        domains = [item["domain"] for item in domain_items]
        results = await check_domains_ssl(domains)
        now_ts = datetime.now(timezone.utc).timestamp()

        for res in results:
            if not res or not res.get("valid"):
                continue
            days_left = res.get("days_left")
            domain = res.get("domain") or ""
            if days_left is None or not domain:
                continue

            # Only alert if expiring within 7 days or expired
            if days_left <= 7:
                last_alert = _SSL_ALERTED.get(domain, 0.0)
                # Alert once every 24 hours per domain
                if now_ts - last_alert < 86400:
                    continue

                issuer = res.get("issuer") or "نامشخص"
                shamsi_exp = res.get("not_after_shamsi") or res.get("not_after") or "—"
                if days_left < 0:
                    status_text = f"🚨 <b>گواهی امنیتی منقضی شده است! ({abs(days_left)} روز گذشته)</b>"
                elif days_left == 0:
                    status_text = "⚠️ <b>گواهی امنیتی امروز منقضی می‌شود!</b>"
                else:
                    status_text = f"⏳ <b>فقط {days_left} روز تا انقضای گواهی SSL باقی مانده</b>"

                msg = (
                    f"🔒 <b>هشدار موعد انقضای گواهی SSL</b>\n\n"
                    f"دامنه: <code>{domain}</code>\n"
                    f"صادرکننده: <b>{issuer}</b>\n"
                    f"تاریخ انقضا: <code>{shamsi_exp}</code>\n"
                    f"وضعیت: {status_text}\n\n"
                    f"لطفاً نسبت به تمدید گواهی SSL دامنه اقدام فرمایید تا دسترسی کاربران دچار اختلال نشود."
                )
                await _notify_admins(bot, msg, session_factory=session_factory)
                _SSL_ALERTED[domain] = now_ts
    except Exception as exc:
        logger.warning("Error checking SSL certificates due dates: %s", exc)


async def nodes_monitor_loop(
    bot: Bot,
    remnawave: RemnawaveClient,
    session_factory: Any = None,
    interval_seconds: int = 120,
) -> None:
    """Loop that continuously monitors node health, resource limits, and billing renewal dates."""
    logger.info("📡 Nodes health monitor loop started (every %ds)", interval_seconds)
    # Initial sleep to allow system boot & network stabilization
    await asyncio.sleep(20)
    last_billing_check_ts = 0.0
    while True:
        try:
            await check_nodes_health_once(bot, remnawave, session_factory=session_factory)

            # Check billing and SSL due dates once every hour
            now_ts = datetime.now(timezone.utc).timestamp()
            if session_factory and (now_ts - last_billing_check_ts >= 3600):
                last_billing_check_ts = now_ts
                await check_nodes_billing_due_dates(bot, session_factory, remnawave=remnawave)
                await check_ssl_certificates_due_dates(bot, session_factory, remnawave)
        except asyncio.CancelledError:
            logger.info("Nodes monitor loop canceled.")
            break
        except Exception as exc:
            logger.error("Error in nodes monitor loop: %s", exc)

        await asyncio.sleep(interval_seconds)

