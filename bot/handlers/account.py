"""Account Management section.

Per panel account: view/copy/open the subscription link, list the
registered HWID devices (with removal), and regenerate (revoke) the
subscription link when it leaked.

Every callback re-fetches the user's accounts from the panel and checks
that the requested account UUID really belongs to this Telegram ID, so
callback data can never be used to touch someone else's account.
"""
import contextlib
import io
import logging
from html import escape

import qrcode
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.repositories.user_repo import UserRepository
from bot.keyboards.inline import welcome_keyboard
from bot.locales.texts import t
from bot.services.formatting import format_date, format_datetime, now_tz, parse_iso
from bot.services.menu import render_menu
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)
router = Router(name="account")

SEPARATOR = "─" * 18

STATUS_KEYS = {
    "ACTIVE": "status_active",
    "DISABLED": "status_disabled",
    "LIMITED": "status_limited",
    "EXPIRED": "status_expired",
}

PLATFORM_EMOJI = {
    "android": "🤖",
    "ios": "🍏",
    "windows": "🖥",
    "macos": "💻",
    "linux": "🐧",
}


async def _get_accounts(
    remnawave: RemnawaveClient, telegram_id: int
) -> list[dict] | None:
    raw = await remnawave.get_users_by_telegram_id(telegram_id)
    if raw is None:
        return None
    seen = set()
    deduped = []
    for a in raw:
        aid = str(a.get("id"))
        if aid not in seen and str(a.get("status", "")).upper() not in ("DELETED",):
            seen.add(aid)
            deduped.append(a)
    return deduped


def _safe_int(value: str | int | None) -> int | None:
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return None


def _find_account(accounts: list[dict], account_id: str | int) -> dict | None:
    for account in accounts:
        if str(account.get("id")) == str(account_id):
            return account
    return None


def _format_account_btn(account: dict, lang: str) -> str:
    username = account.get("username", "—")
    limit = int(account.get("trafficLimitBytes") or 0)
    traffic = account.get("userTraffic") or {}
    used = int(traffic.get("usedTrafficBytes") or account.get("usedTrafficBytes") or 0)

    # Traffic compact string (e.g. 30 GB or 500 MB)
    if limit > 0:
        remaining = max(0, limit - used)
        gb = remaining / (1024 ** 3)
        if gb >= 1:
            traffic_str = f"{gb:.0f} GB" if gb.is_integer() or round(gb, 1).is_integer() else f"{gb:.1f} GB"
        else:
            mb = remaining / (1024 ** 2)
            traffic_str = f"{mb:.0f} MB" if mb >= 1 else "0 MB"
    else:
        traffic_str = t(lang, "stats_unlimited")

    # Expiry days (e.g. 12 or 12 روز)
    expire_at = parse_iso(account.get("expireAt"))
    if expire_at is None:
        days_str = t(lang, "stats_no_expire")
    else:
        now = now_tz(get_settings().TIMEZONE)
        delta_days = (expire_at - now).days
        if delta_days >= 0:
            days_str = f"{delta_days} روز" if lang == "fa" else f"{delta_days}d"
        else:
            days_str = "منقضی" if lang == "fa" else "Expired"

    return f"👤 {username} - {traffic_str} - {days_str}"


# --------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------- #
def _account_view_text(account: dict, lang: str) -> str:
    username = escape(str(account.get("username", "—")))
    status = str(account.get("status", "")).upper()
    status_text = t(lang, STATUS_KEYS.get(status, "status_active"))

    lines = [
        t(lang, "acc_title"),
        SEPARATOR,
        f"{t(lang, 'stats_account')} : <code>{username}</code>",
        f"{t(lang, 'stats_status')} : {status_text}",
    ]

    expire_at = parse_iso(account.get("expireAt"))
    if expire_at is None:
        lines.append(f"{t(lang, 'stats_expire')} : {t(lang, 'stats_no_expire')}")
    else:
        now = now_tz(get_settings().TIMEZONE)
        delta_days = (expire_at - now).days
        date_str = format_date(expire_at.astimezone(now.tzinfo), lang)
        if delta_days >= 0:
            when = t(lang, "stats_days_left", days=delta_days)
        else:
            when = t(lang, "stats_expired_ago", days=abs(delta_days))
        lines.append(f"{t(lang, 'stats_expire')} : <b>{when}</b> ({date_str})")

    sub_url = account.get("subscriptionUrl")
    if sub_url:
        lines += ["", t(lang, "acc_sub_link"), f"<code>{escape(sub_url)}</code>"]

    return "\n".join(lines)


def _account_view_keyboard(
    account: dict, lang: str, multi: bool
) -> InlineKeyboardMarkup:
    """Row items render left→right, so the right-side (RTL) button is second."""
    account_id = account.get("id")
    kb = InlineKeyboardBuilder()
    sizes = []
    sub_url = account.get("subscriptionUrl")
    if sub_url:
        # تعویض لینک | باز کردن لینک
        kb.button(text=t(lang, "btn_revoke"), callback_data=f"acc:revoke:{account_id}")
        kb.button(text=t(lang, "btn_open_sub"), url=sub_url)
        sizes.append(2)
        # کد QR | دستگاه‌های متصل
        kb.button(text=t(lang, "btn_qr"), callback_data=f"acc:qr:{account_id}")
        kb.button(text=t(lang, "btn_devices"), callback_data=f"acc:devices:{account_id}")
        sizes.append(2)
        # دریافت کانفیگ
        kb.button(text=t(lang, "btn_get_configs"), callback_data=f"cfg:acc:{account_id}")
        sizes.append(1)
    else:
        kb.button(text=t(lang, "btn_revoke"), callback_data=f"acc:revoke:{account_id}")
        kb.button(text=t(lang, "btn_devices"), callback_data=f"acc:devices:{account_id}")
        sizes += [1, 1]
    if multi:
        kb.button(text=t(lang, "btn_back"), callback_data="menu:account")
    else:
        kb.button(text=t(lang, "btn_back"), callback_data="nav:main_menu")
    sizes.append(1)
    kb.adjust(*sizes)
    return kb.as_markup()


def _device_line(device: dict, num: int, lang: str, tz_name: str) -> str:
    platform = str(device.get("platform") or "—")
    emoji = PLATFORM_EMOJI.get(platform.lower(), "📱")
    model = escape(str(device.get("deviceModel") or "—"))
    lines = [f"{num}) {emoji} <b>{escape(platform)}</b> — {model}"]

    seen = parse_iso(device.get("updatedAt"))
    if seen is not None:
        now = now_tz(tz_name)
        seen_str = format_datetime(seen.astimezone(now.tzinfo), lang)
        lines.append(f"      {t(lang, 'device_last_seen')} : {seen_str}")

    ip = device.get("requestIp")
    if ip:
        lines.append(f"      {t(lang, 'device_ip')} : <code>{escape(str(ip))}</code>")

    return "\n".join(lines)


async def _render_devices(
    bot: Bot, user, user_repo: UserRepository,
    remnawave: RemnawaveClient, account: dict, lang: str,
) -> None:
    account_id = account.get("id")
    devices = await remnawave.get_user_hwid_devices(account_id)
    tz = get_settings().TIMEZONE

    lines = [t(lang, "devices_title"), SEPARATOR]

    limit = account.get("hwidDeviceLimit")
    count = str(len(devices)) if not limit else f"{len(devices)} / {limit}"
    lines.append(f"{t(lang, 'devices_count')} : <b>{count}</b>")
    lines.append("")

    if devices:
        lines.append(
            "\n\n".join(
                _device_line(d, i, lang, tz) for i, d in enumerate(devices, start=1)
            )
        )
    else:
        lines.append(t(lang, "devices_empty"))

    kb = InlineKeyboardBuilder()
    device_indices = list(range(1, len(devices) + 1))
    sizes = []
    i = 0
    while i < len(device_indices):
        if i + 1 < len(device_indices):
            odd = device_indices[i]      # e.g. 1
            even = device_indices[i + 1] # e.g. 2
            # Add even first (left), odd second (right) so odd is on the RIGHT in RTL
            kb.button(
                text=t(lang, "btn_device_delete", num=even),
                callback_data=f"acc:devrm:{account_id}:{even - 1}",
            )
            kb.button(
                text=t(lang, "btn_device_delete", num=odd),
                callback_data=f"acc:devrm:{account_id}:{odd - 1}",
            )
            sizes.append(2)
            i += 2
        else:
            odd = device_indices[i]
            kb.button(
                text=t(lang, "btn_device_delete", num=odd),
                callback_data=f"acc:devrm:{account_id}:{odd - 1}",
            )
            sizes.append(1)
            i += 1
    kb.button(text=t(lang, "btn_back"), callback_data=f"acc:view:{account_id}")
    sizes.append(1)
    kb.adjust(*sizes)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


async def _render_account_view(
    bot, user, user_repo, account: dict, lang: str, multi: bool
) -> None:
    await render_menu(
        bot, user, user_repo,
        _account_view_text(account, lang),
        _account_view_keyboard(account, lang, multi),
    )


# --------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------- #
@router.callback_query(F.data == "menu:account")
async def account_entry(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, remnawave: RemnawaveClient
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    accounts = await _get_accounts(remnawave, call.from_user.id)
    if accounts is None:
        await render_menu(bot, user, user_repo, t(lang, "acc_error"),
                          welcome_keyboard(lang))
        await call.answer()
        return
    if not accounts:
        await user_repo.set_verified(user, False)
        await render_menu(
            bot, user, user_repo, t(lang, "not_verified"), welcome_keyboard(lang)
        )
        await call.answer()
        return

    await user_repo.set_verified(user, True)

    if len(accounts) == 1:
        await _render_account_view(bot, user, user_repo, accounts[0], lang, multi=False)
        await call.answer()
        return

    # several panel accounts on this Telegram ID → pick one first
    kb = InlineKeyboardBuilder()
    for account in accounts:
        kb.button(
            text=_format_account_btn(account, lang),
            callback_data=f"acc:view:{account.get('id')}",
        )
    kb.button(text=t(lang, "btn_back"), callback_data="nav:main_menu")
    kb.adjust(1)

    text = f"{t(lang, 'acc_title')}\n{SEPARATOR}\n{t(lang, 'acc_pick')}"
    await render_menu(bot, user, user_repo, text, kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("acc:view:"))
async def account_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, remnawave: RemnawaveClient
):
    account_id = call.data.split(":", 2)[2]
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    accounts = await _get_accounts(remnawave, call.from_user.id)
    if accounts is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return
    account = _find_account(accounts, account_id)
    if account is None:
        await call.answer(t(lang, "not_authorized"), show_alert=True)
        return

    await _render_account_view(
        bot, user, user_repo, account, lang, multi=len(accounts) > 1
    )
    await call.answer()


@router.callback_query(F.data.startswith("acc:devices:"))
async def account_devices(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, remnawave: RemnawaveClient
):
    account_id = call.data.split(":", 2)[2]
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    accounts = await _get_accounts(remnawave, call.from_user.id)
    if accounts is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return
    account = _find_account(accounts, account_id)
    if account is None:
        await call.answer(t(lang, "not_authorized"), show_alert=True)
        return

    await _render_devices(bot, user, user_repo, remnawave, account, lang)
    await call.answer()


@router.callback_query(F.data.startswith("acc:devrm:"))
async def device_delete_confirm(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, remnawave: RemnawaveClient
):
    _, _, account_id, idx = call.data.split(":", 3)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    accounts = await _get_accounts(remnawave, call.from_user.id)
    if accounts is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return
    account = _find_account(accounts, account_id)
    if account is None:
        await call.answer(t(lang, "not_authorized"), show_alert=True)
        return

    panel_id = _safe_int(account_id)
    index = _safe_int(idx)
    if panel_id is None or index is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return
    devices = await remnawave.get_user_hwid_devices(panel_id)
    if index >= len(devices):
        # list changed meanwhile → just re-render it
        await _render_devices(bot, user, user_repo, remnawave, account, lang)
        await call.answer()
        return

    device_text = _device_line(devices[index], index + 1, lang, get_settings().TIMEZONE)
    kb = InlineKeyboardBuilder()
    kb.button(
        text=t(lang, "btn_yes_delete"),
        callback_data=f"acc:devrm_yes:{account_id}:{index}",
    )
    kb.button(text=t(lang, "btn_cancel"), callback_data=f"acc:devices:{account_id}")
    kb.adjust(1)

    await render_menu(
        bot, user, user_repo,
        t(lang, "device_delete_confirm", device=device_text),
        kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("acc:devrm_yes:"))
async def device_delete(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    remnawave: RemnawaveClient,
    session: AsyncSession,
):
    _, _, account_id, idx = call.data.split(":", 3)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    accounts = await _get_accounts(remnawave, call.from_user.id)
    if accounts is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return
    account = _find_account(accounts, account_id)
    if account is None:
        await call.answer(t(lang, "not_authorized"), show_alert=True)
        return

    panel_id = _safe_int(account_id)
    index = _safe_int(idx)
    if panel_id is None or index is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return
    devices = await remnawave.get_user_hwid_devices(panel_id)
    ok = False
    if index < len(devices):
        hwid = devices[index].get("hwid")
        if hwid:
            ok = await remnawave.delete_hwid_device(panel_id, hwid)
            if ok:
                from bot.db.repositories.device_repo import DeviceRepository

                await DeviceRepository(session).remove_device(panel_id, hwid)

    await call.answer(
        t(lang, "device_deleted") if ok else t(lang, "acc_error"), show_alert=not ok
    )
    await _render_devices(bot, user, user_repo, remnawave, account, lang)


@router.callback_query(F.data.startswith("acc:qr:"))
async def show_qr(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, remnawave: RemnawaveClient
):
    account_id = call.data.split(":", 2)[2]
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    accounts = await _get_accounts(remnawave, call.from_user.id)
    if accounts is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return
    account = _find_account(accounts, account_id)
    if account is None:
        await call.answer(t(lang, "not_authorized"), show_alert=True)
        return

    sub_url = account.get("subscriptionUrl")
    if not sub_url:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return

    try:
        buf = io.BytesIO()
        qrcode.make(sub_url).save(buf)
        photo = BufferedInputFile(buf.getvalue(), filename="subscription-qr.png")
    except Exception:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_close"), callback_data="acc:qr_close")

    # QR is sent as an extra photo message (the clean menu stays a text
    # message); the Close button deletes it again.
    await bot.send_photo(
        chat_id=call.from_user.id,
        photo=photo,
        caption=t(lang, "qr_caption", link=escape(sub_url)),
        reply_markup=kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "acc:qr_close")
async def qr_close(call: CallbackQuery):
    with contextlib.suppress(TelegramBadRequest):
        await call.message.delete()
    await call.answer()


@router.callback_query(F.data.startswith("acc:revoke:"))
async def revoke_confirm(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, remnawave: RemnawaveClient
):
    account_id = call.data.split(":", 2)[2]
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    accounts = await _get_accounts(remnawave, call.from_user.id)
    if accounts is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return
    account = _find_account(accounts, account_id)
    if account is None:
        await call.answer(t(lang, "not_authorized"), show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    # 2 columns (RTL: first is Left = Cancel, second is Right = Yes)
    kb.button(text=t(lang, "btn_cancel"), callback_data=f"acc:view:{account_id}")
    kb.button(text=t(lang, "btn_yes_revoke"), callback_data=f"acc:revoke_yes:{account_id}")
    kb.adjust(2)

    await render_menu(bot, user, user_repo, t(lang, "revoke_confirm"), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("acc:revoke_yes:"))
async def revoke_do(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, remnawave: RemnawaveClient
):
    account_id = call.data.split(":", 2)[2]
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    accounts = await _get_accounts(remnawave, call.from_user.id)
    if accounts is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return
    account = _find_account(accounts, account_id)
    if account is None:
        await call.answer(t(lang, "not_authorized"), show_alert=True)
        return

    panel_id = _safe_int(account_id)
    if panel_id is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return
    updated = await remnawave.revoke_user_subscription(panel_id)
    if updated is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return

    sub_url = updated.get("subscriptionUrl") or ""
    text = (
        f"{t(lang, 'revoke_done')}\n"
        f"<code>{escape(sub_url)}</code>"
    )
    kb = InlineKeyboardBuilder()
    if sub_url:
        kb.button(text=t(lang, "btn_open_sub"), url=sub_url)
    kb.button(text=t(lang, "btn_back"), callback_data=f"acc:view:{account_id}")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, text, kb.as_markup())
    await call.answer()
