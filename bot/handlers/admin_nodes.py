"""Admin Node & Server Telemetry Inspector."""
import logging
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.common import SEPARATOR, is_admin
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.formatting import country_flag
from bot.services.menu import render_menu
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)
router = Router(name="admin_nodes")

def _is_admin(user_id: int) -> bool:
    import bot.handlers.admin_ops as _ops
    fn = getattr(_ops, "_is_admin", is_admin)
    return fn(user_id)

# --------------------------------------------------------------------- #
# Node / Server Status Monitor
# --------------------------------------------------------------------- #
COUNTRY_FLAGS_MAP: dict[str, tuple[str, str]] = {
    "netherlands": ("🇳🇱", "NL"),
    "netherland": ("🇳🇱", "NL"),
    "holland": ("🇳🇱", "NL"),
    "germany": ("🇩🇪", "DE"),
    "deutschland": ("🇩🇪", "DE"),
    "france": ("🇫🇷", "FR"),
    "united states": ("🇺🇸", "US"),
    "usa": ("🇺🇸", "US"),
    "united kingdom": ("🇬🇧", "GB"),
    "uk": ("🇬🇧", "GB"),
    "great britain": ("🇬🇧", "GB"),
    "england": ("🇬🇧", "GB"),
    "turkey": ("🇹🇷", "TR"),
    "turkiye": ("🇹🇷", "TR"),
    "finland": ("🇫🇮", "FI"),
    "sweden": ("🇸🇪", "SE"),
    "canada": ("🇨🇦", "CA"),
    "iran": ("🇮🇷", "IR"),
    "russia": ("🇷🇺", "RU"),
    "poland": ("🇵🇱", "PL"),
    "italy": ("🇮🇹", "IT"),
    "spain": ("🇪🇸", "ES"),
    "switzerland": ("🇨🇭", "CH"),
    "united arab emirates": ("🇦🇪", "AE"),
    "uae": ("🇦🇪", "AE"),
    "dubai": ("🇦🇪", "AE"),
    "singapore": ("🇸🇬", "SG"),
    "austria": ("🇦🇹", "AT"),
    "australia": ("🇦🇺", "AU"),
    "brazil": ("🇧🇷", "BR"),
    "norway": ("🇳🇴", "NO"),
    "denmark": ("🇩🇰", "DK"),
    "belgium": ("🇧🇪", "BE"),
    "japan": ("🇯🇵", "JP"),
}


def _extract_versions(n: dict) -> tuple[str | None, str | None]:
    versions = n.get("versions")
    if not isinstance(versions, dict):
        versions = {}

    sys_info = n.get("system") or n.get("sys") or {}
    if isinstance(sys_info, dict) and isinstance(sys_info.get("versions"), dict):
        versions = {**sys_info.get("versions"), **versions}

    xray_ver = (
        versions.get("xray")
        or versions.get("xrayVersion")
        or n.get("xrayVersion")
        or (n.get("core") if isinstance(n.get("core"), str) else None)
    )
    singbox_ver = (
        versions.get("singbox")
        or versions.get("sing-box")
        or versions.get("singboxVersion")
        or n.get("singboxVersion")
    )
    node_ver = (
        versions.get("node")
        or versions.get("nodeVersion")
        or n.get("nodeVersion")
        or versions.get("agent")
        or n.get("agentVersion")
    )
    core_ver = (
        versions.get("core")
        or n.get("coreVersion")
        or n.get("version")
    )

    core_label = None
    if xray_ver:
        core_label = f"Xray {xray_ver}"
    elif singbox_ver:
        core_label = f"Sing-Box {singbox_ver}"
    elif core_ver:
        core_label = f"Core {core_ver}" if not str(core_ver).lower().startswith("core") else str(core_ver)

    node_label = f"Node {node_ver}" if node_ver else None
    return core_label, node_label


def _extract_core_version(n: dict) -> str | None:
    core_label, node_label = _extract_versions(n)
    if core_label and node_label:
        return f"{core_label} | {node_label}"
    return core_label or node_label


def _format_node_title(n: dict, index: int) -> str:
    raw_name = str(n.get("name") or f"Node {index}").strip()
    country_code = str(n.get("countryCode") or n.get("country_code") or "").strip().upper()
    country_name = str(n.get("country") or "").strip().lower()

    flag = None
    if len(country_code) == 2 and country_code.isalpha() and country_code != "XX":
        flag = country_flag(country_code)

    clean_name = raw_name
    for kw, (f_emoji, _) in sorted(COUNTRY_FLAGS_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        pattern = re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
        if pattern.search(clean_name):
            if not flag or flag == "🌐":
                flag = f_emoji
            clean_name = pattern.sub("", clean_name)
            break

    if (not flag or flag == "🌐") and country_name:
        for kw, (f_emoji, _) in COUNTRY_FLAGS_MAP.items():
            if kw in country_name:
                flag = f_emoji
                break

    if country_code and len(country_code) == 2 and country_code != "XX":
        code_pat = re.compile(rf"\b{re.escape(country_code)}\b", re.IGNORECASE)
        clean_name = code_pat.sub("", clean_name)

    clean_name = re.sub(r"[\-_:]+", " ", clean_name).strip()
    clean_name = re.sub(r"\s+", " ", clean_name).strip()

    # Check if a flag emoji is already present in clean_name
    has_flag = any(0x1F1E6 <= ord(c) <= 0x1F1FF for c in clean_name)
    if not has_flag:
        flag_prefix = flag if flag else (country_flag(country_code) if country_code else "🌐")
        if clean_name:
            final_title = f"{flag_prefix} {escape(clean_name)}"
        else:
            final_title = f"{flag_prefix}"
    else:
        final_title = escape(clean_name)

    return final_title


@router.callback_query(F.data == "adm:nodes")
async def admin_nodes_monitor(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    nodes = await remnawave.get_nodes()
    lines = [
        f"🖥 <b>{t(lang, 'nodes_title')}</b>",
        SEPARATOR,
    ]
    if nodes is None:
        lines.append(t(lang, "stats_error"))
    elif not nodes:
        lines.append("هیچ سرور یا نودی یافت نشد." if lang == "fa" else "No nodes found.")
    else:
        for i, n in enumerate(nodes, start=1):
            title = _format_node_title(n, i)
            address = escape(str(n.get("address") or "—"))
            port = n.get("port")
            addr_str = f"{address}:{port}" if port else address
            is_connected = n.get("isConnected")
            if is_connected is None:
                is_connected = str(n.get("status", "")).upper() == "CONNECTED"
            status_badge = "🟢" if is_connected else "🔴"

            core_version, node_version = _extract_versions(n)
            user_mult = (
                n.get("consumptionMultiplier")
                if n.get("consumptionMultiplier") is not None
                else n.get("userConsumptionMultiplier")
                if n.get("userConsumptionMultiplier") is not None
                else n.get("userTrafficMultiplier")
                if n.get("userTrafficMultiplier") is not None
                else n.get("trafficMultiplier")
                if n.get("trafficMultiplier") is not None
                else 1.0
            )
            node_mult = (
                n.get("nodeConsumptionMultiplier")
                if n.get("nodeConsumptionMultiplier") is not None
                else n.get("nodeTrafficMultiplier")
                if n.get("nodeTrafficMultiplier") is not None
                else n.get("multiplier")
            )

            sys_info = n.get("system") or n.get("sys") or {}
            cpu = sys_info.get("cpu") or n.get("cpu")
            ram = sys_info.get("ram") or sys_info.get("memory") or n.get("memory")
            os_name = sys_info.get("os") or n.get("os")
            uptime_raw = sys_info.get("uptime") or n.get("uptime") or n.get("uptimeSeconds")

            uptime_str = None
            if uptime_raw is not None:
                try:
                    s = int(uptime_raw)
                    if s > 0:
                        days = s // 86400
                        s %= 86400
                        hours = s // 3600
                        s %= 3600
                        minutes = s // 60
                        seconds = s % 60
                        parts = []
                        if days > 0:
                            parts.append(f"{days}d")
                        if hours > 0 or days > 0:
                            parts.append(f"{hours}h")
                        if minutes > 0 or hours > 0 or days > 0:
                            parts.append(f"{minutes}m")
                        parts.append(f"{seconds}s")
                        uptime_str = " ".join(parts)
                except (ValueError, TypeError):
                    uptime_str = str(uptime_raw)

            daily_traffic = n.get("trafficDailyBytes") or n.get("dailyTrafficBytes") or n.get("todayTrafficBytes")
            daily_str = f"{daily_traffic / (1024**3):.2f} GB" if daily_traffic else None
            traffic_used = n.get("trafficUsedBytes") or n.get("usedTrafficBytes")
            traf_str = f"{traffic_used / (1024**3):.2f} GB" if traffic_used else None
            online_users = n.get("usersOnline") or n.get("connectionCount")

            node_desc = [
                f"<b>{i}. {title}</b> ({status_badge})",
                f"   🌐 آدرس: <code>{addr_str}</code>" if lang == "fa" else f"   🌐 Host: <code>{addr_str}</code>",
            ]
            if core_version:
                node_desc.append(
                    f"   ⚙️ نسخه هسته: {escape(str(core_version))}" if lang == "fa" else f"   ⚙️ Core: {escape(str(core_version))}"
                )
            if node_version:
                node_desc.append(
                    f"   📡 نسخه نود: {escape(str(node_version))}" if lang == "fa" else f"   📡 Node: {escape(str(node_version))}"
                )
            specs_parts = []
            if cpu:
                specs_parts.append(f"CPU: {cpu}")
            if ram:
                specs_parts.append(f"RAM: {ram}")
            if os_name:
                specs_parts.append(f"OS: {os_name}")
            disk = sys_info.get("disk") or sys_info.get("storage") or n.get("disk")
            if disk:
                specs_parts.append(f"Disk: {disk}")
            load = sys_info.get("load") or sys_info.get("loadAvg") or n.get("load")
            if load:
                specs_parts.append(f"Load: {load}")
            if specs_parts:
                specs_str = escape(" | ".join(specs_parts))
                node_desc.append(
                    f"   💻 مشخصات سرور: {specs_str}" if lang == "fa" else f"   💻 System: {specs_str}"
                )
            if user_mult is not None:
                node_desc.append(
                    f"   👤 ضریب مصرف کاربر: <b>{user_mult}x</b>" if lang == "fa" else f"   👤 User Multiplier: <b>{user_mult}x</b>"
                )
            if node_mult is not None:
                node_desc.append(
                    f"   📡 ضریب مصرف نود: <b>{node_mult}x</b>" if lang == "fa" else f"   📡 Node Multiplier: <b>{node_mult}x</b>"
                )
            traf_info = []
            if daily_str:
                traf_info.append(f"امروز: <b>{daily_str}</b>" if lang == "fa" else f"Today: <b>{daily_str}</b>")
            if traf_str:
                traf_info.append(f"کل: <b>{traf_str}</b>" if lang == "fa" else f"Total: <b>{traf_str}</b>")
            if traf_info:
                node_desc.append(
                    f"   📊 ترافیک مصرفی: {' | '.join(traf_info)}" if lang == "fa" else f"   📊 Used Traffic: {' | '.join(traf_info)}"
                )
            if uptime_str:
                node_desc.append(
                    f"   ⏱ آپ‌تایم: {uptime_str}" if lang == "fa" else f"   ⏱ Uptime: {uptime_str}"
                )
            if online_users is not None:
                node_desc.append(
                    f"   👥 آنلاین: <b>{online_users}</b>" if lang == "fa" else f"   👥 Online: <b>{online_users}</b>"
                )
            lines.append("\n".join(node_desc))
            if i < len(nodes):
                lines.append("")

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 بروزرسانی" if lang == "fa" else "🔄 Refresh", callback_data="adm:nodes")
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(1, 1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()
