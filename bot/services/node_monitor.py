"""Background job: Real-time Node Health and Resource Monitor.

Monitors nodes every 2 minutes:
1. Sends Telegram alerts to admins if any node goes OFFLINE.
2. Sends alert if memory (RAM) or CPU exceeds 90%.
3. Sends recovery notification when an offline node comes back ONLINE.
4. Prevents duplicate alert spam via cooldown timestamps.
"""
import asyncio
from datetime import datetime, timezone
import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot.config import get_settings
from bot.services.formatting import country_flag
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)

# In-memory alert state: {node_id_or_name: {"is_offline": bool, "last_alert_ts": float}}
_NODE_STATES: dict[str, dict[str, Any]] = {}
COOLDOWN_SECONDS = 3600  # 1 hour cooldown for repeated high-resource or offline alerts


async def _notify_admins(bot: Bot, text: str) -> None:
    """Send alert message to all configured super admins."""
    settings = get_settings()
    admin_ids = settings.ADMIN_IDS or []
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except TelegramAPIError as exc:
            logger.warning("Failed to send node alert to admin %s: %s", admin_id, exc)


async def check_nodes_health_once(bot: Bot, remnawave: RemnawaveClient) -> None:
    """Run one health check iteration across all cluster nodes."""
    try:
        nodes = await remnawave.get_nodes()
        if not nodes:
            return
    except Exception as exc:
        logger.warning("Failed to fetch nodes for health monitor: %s", exc)
        return

    now_ts = datetime.now(timezone.utc).timestamp()
    time_str = datetime.now(timezone.utc).strftime("%H:%M:%S")

    for n in nodes:
        node_id = str(n.get("id") or n.get("uuid") or n.get("name") or "unknown")
        raw_name = n.get("name") or "Node"
        country_code = n.get("countryCode") or n.get("country_code")
        flag = country_flag(country_code) if country_code else "🌐"
        address = str(n.get("address") or "—")
        online_users = int(n.get("usersOnline") or n.get("connectionCount") or 0)

        is_connected = n.get("isConnected")
        if is_connected is None:
            is_connected = str(n.get("status", "")).upper() in ("CONNECTED", "ONLINE")

        state = _NODE_STATES.setdefault(node_id, {"is_offline": False, "last_alert_ts": 0.0})

        # --- 1. Offline Check ---
        if not is_connected:
            # If newly offline or cooldown expired
            if not state["is_offline"] or (now_ts - state["last_alert_ts"] > COOLDOWN_SECONDS):
                state["is_offline"] = True
                state["last_alert_ts"] = now_ts
                msg = (
                    f"🚨 <b>هشدار قطعی سرور (Node Offline)</b>\n\n"
                    f"سرور: <b>{flag} {raw_name}</b>\n"
                    f"آدرس: <code>{address}</code>\n"
                    f"وضعیت: ❌ <b>آفلاین / قطع اتصال</b>\n"
                    f"کاربران متأثر: <b>{online_users} نفر</b>\n"
                    f"زمان بررسی: <code>{time_str} UTC</code>"
                )
                await _notify_admins(bot, msg)
        else:
            # Node is connected
            if state["is_offline"]:
                # Was offline before, now recovered!
                state["is_offline"] = False
                state["last_alert_ts"] = now_ts
                msg = (
                    f"✅ <b>اتصال سرور برقرار شد (Node Recovered)</b>\n\n"
                    f"سرور: <b>{flag} {raw_name}</b>\n"
                    f"آدرس: <code>{address}</code>\n"
                    f"وضعیت: 🟢 <b>آنلاین و متصل</b>\n"
                    f"زمان بازیابی: <code>{time_str} UTC</code>"
                )
                await _notify_admins(bot, msg)

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
                    f"سرور: <b>{flag} {raw_name}</b>\n"
                    f"مصرف رم (RAM): <b>{ram:.1f}%</b>\n"
                    f"مصرف پردازنده (CPU): <b>{cpu:.1f}%</b>\n"
                    f"کاربران آنلاین: <b>{online_users} نفر</b>\n"
                    f"زمان: <code>{time_str} UTC</code>\n\n"
                    f"<i>توصیه: ترافیک یا سرویس‌های سرور را بررسی فرمایید.</i>"
                )
                await _notify_admins(bot, msg)


async def check_nodes_billing_due_dates(bot: Bot, session_factory: Any) -> None:
    """Check if any nodes are approaching their billing due date (<= 3 days) and alert admins."""
    if not session_factory:
        return
    try:
        from bot.db.repositories.node_cost_repo import NodeCostRepository
        async with session_factory() as session:
            repo = NodeCostRepository(session)
            due_nodes = await repo.list_due_soon(days_threshold=3)
            if not due_nodes:
                return

            now_utc = datetime.now(timezone.utc)
            for node in due_nodes:
                if not node.due_date:
                    continue
                days_left = (node.due_date.date() - now_utc.date()).days
                node_name = node.node_name or f"Node {node.node_id or (node.node_uuid[:8] if node.node_uuid else '')}"
                provider = node.provider or "نامشخص"

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
                    f"<i>لطفاً جهت جلوگیری از مسدود شدن یا حذف سرور نسبت به پرداخت فاکتور اقدام فرمایید.</i>"
                )
                await _notify_admins(bot, msg)
                await repo.mark_alert_sent(node.node_uuid, True)

            await session.commit()
    except Exception as exc:
        logger.warning("Error checking node billing due dates: %s", exc)


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
            await check_nodes_health_once(bot, remnawave)

            # Check billing due dates once every hour
            now_ts = datetime.now(timezone.utc).timestamp()
            if session_factory and (now_ts - last_billing_check_ts >= 3600):
                last_billing_check_ts = now_ts
                await check_nodes_billing_due_dates(bot, session_factory)
        except asyncio.CancelledError:
            logger.info("Nodes monitor loop canceled.")
            break
        except Exception as exc:
            logger.error("Error in nodes monitor loop: %s", exc)

        await asyncio.sleep(interval_seconds)

