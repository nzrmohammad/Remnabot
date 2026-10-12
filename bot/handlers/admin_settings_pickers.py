"""Pickers for Remind Days, Grace Days, and Squads."""
import logging

from aiogram import Bot
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, is_admin
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.user_repo import UserRepository
from bot.handlers.admin_settings_common import render_menu
from bot.handlers.admin_settings_views import _render_settings
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings

logger = logging.getLogger(__name__)

REMIND_DAYS_CHOICES = [0, 1, 2, 3, 5, 7, 10, 14]
GRACE_DAYS_CHOICES = [0, 1, 2, 3, 5, 7, 10, 14, 30]


def _parse_remind_days_set(raw: str | None) -> set[int]:
    if not raw:
        return set()
    result = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            result.add(int(part))
    return result


async def _render_remind_days_picker(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:

    lang = user.language or "fa"
    store = await get_store_settings(session)
    active_days = _parse_remind_days_set(store.expiry_remind_days)
    kb = InlineKeyboardBuilder()

    if lang == "fa":
        for d in [3, 2, 1, 0]:
            mark = " ✅" if d in active_days else ""
            kb.button(text=f"{d} روز{mark}", callback_data=f"adm:remind:toggle:{d}")
        for d in [14, 10, 7, 5]:
            mark = " ✅" if d in active_days else ""
            kb.button(text=f"{d} روز{mark}", callback_data=f"adm:remind:toggle:{d}")

        kb.button(text="❌ غیرفعال‌سازی همه هشدارهای انقضا", callback_data="adm:remind:toggle:clear")
        kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
    else:
        for d in [0, 1, 2, 3]:
            mark = " ✅" if d in active_days else ""
            kb.button(text=f"{d}d{mark}", callback_data=f"adm:remind:toggle:{d}")
        for d in [5, 7, 10, 14]:
            mark = " ✅" if d in active_days else ""
            kb.button(text=f"{d}d{mark}", callback_data=f"adm:remind:toggle:{d}")

        kb.button(text="❌ Disable All Expiry Reminders", callback_data="adm:remind:toggle:clear")
        kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")

    kb.adjust(4, 4, 1, 1)

    active_sorted = sorted(active_days, reverse=True)
    if lang == "fa":
        if active_sorted:
            display_str = "، ".join(f"{d} روز" for d in active_sorted)
        else:
            display_str = "هیچ‌کدام (غیرفعال)"
        text = (
            f"🔔 <b>تنظیم روزهای هشدار انقضا</b>\n{SEPARATOR}\n"
            f"روزهای انتخابی فعلی: <b>{display_str}</b>\n\n"
            f"💡 با لمس هر گزینه، می‌توانید آن را فعال یا غیرفعال کنید (امکان انتخاب همزمان چند روز وجود دارد):\n"
            f"پیام یادآوری تمدید اشتراک در این روزها به صورت خودکار برای کاربران ارسال خواهد شد."
        )
    else:
        if active_sorted:
            display_str = ", ".join(f"{d}d" for d in active_sorted)
        else:
            display_str = "None (Disabled)"
        text = (
            f"🔔 <b>Expiry Reminder Days</b>\n{SEPARATOR}\n"
            f"Currently selected: <b>{display_str}</b>\n\n"
            f"💡 Tap any option to toggle it on or off (multiple choices supported):\n"
            f"Renewal reminder messages will be sent automatically to users on these days."
        )

    await render_menu(bot, user, user_repo, text, kb.as_markup())


async def remind_days_picker_entry(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_remind_days_picker(bot, user, user_repo, session)
    await call.answer()


async def remind_days_toggle(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return

    action = call.data.rsplit(":", 1)[1]
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    store = await get_store_settings(session)
    active_days = _parse_remind_days_set(store.expiry_remind_days)

    if action == "clear":
        active_days.clear()
        new_val = ""
        ans_msg = "❌ تمام هشدارهای انقضا غیرفعال شدند" if user.language == "fa" else "All reminders disabled"
    else:
        try:
            day_num = int(action)
        except ValueError:
            await call.answer(t("fa", "acc_error"), show_alert=True)
            return
        if day_num in active_days:
            active_days.remove(day_num)
            ans_msg = f"❌ هشدار {day_num} روز حذف شد" if user.language == "fa" else f"Removed {day_num}d reminder"
        else:
            active_days.add(day_num)
            ans_msg = f"✅ هشدار {day_num} روز افزوده شد" if user.language == "fa" else f"Added {day_num}d reminder"
        new_val = ",".join(str(d) for d in sorted(active_days, reverse=True))

    await AppSettingRepository(session).set("expiry_remind_days", new_val)
    await AdminLogRepository(session).log(
        call.from_user.id, "setting", detail=f"expiry_remind_days={new_val}"
    )
    await _render_remind_days_picker(bot, user, user_repo, session)
    await call.answer(ans_msg)


async def _render_grace_days_picker(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:

    lang = user.language or "fa"
    store = await get_store_settings(session)
    current_grace = store.expiry_grace_days
    kb = InlineKeyboardBuilder()

    if lang == "fa":
        for d in [2, 1, 0]:
            label = "بدون مهلت (0)" if d == 0 else f"{d} روز"
            mark = " ✅" if current_grace == d else ""
            kb.button(text=f"{label}{mark}", callback_data=f"adm:grace:set:{d}")
        for d in [7, 5, 3]:
            mark = " ✅" if current_grace == d else ""
            kb.button(text=f"{d} روز{mark}", callback_data=f"adm:grace:set:{d}")
        for d in [30, 14, 10]:
            mark = " ✅" if current_grace == d else ""
            kb.button(text=f"{d} روز{mark}", callback_data=f"adm:grace:set:{d}")
    else:
        for d in [0, 1, 2]:
            label = "No grace (0)" if d == 0 else f"{d}d"
            mark = " ✅" if current_grace == d else ""
            kb.button(text=f"{label}{mark}", callback_data=f"adm:grace:set:{d}")
        for d in [3, 5, 7]:
            mark = " ✅" if current_grace == d else ""
            kb.button(text=f"{d}d{mark}", callback_data=f"adm:grace:set:{d}")
        for d in [10, 14, 30]:
            mark = " ✅" if current_grace == d else ""
            kb.button(text=f"{d}d{mark}", callback_data=f"adm:grace:set:{d}")

    kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
    kb.adjust(3, 3, 3, 1)

    grace_display = "بدون مهلت (سرویس بلافاصله مسدود می‌شود)" if current_grace == 0 else f"{current_grace} روز"
    if lang == "fa":
        text = (
            f"⏳ <b>تنظیم مهلت پس از انقضا (Grace Period)</b>\n{SEPARATOR}\n"
            f"مهلت فعلی: <b>{grace_display}</b>\n\n"
            f"💡 تعداد روزهایی که سرویس کاربر پس از انقضا فعال می‌ماند (مهلت تمدید/پرداخت قبل از قطع شدن) را انتخاب کنید:"
        )
    else:
        text = (
            f"⏳ <b>Expiry Grace Period</b>\n{SEPARATOR}\n"
            f"Current grace period: <b>{current_grace}d</b>\n\n"
            f"💡 Select how many days after expiry the service remains active before being suspended:"
        )

    await render_menu(bot, user, user_repo, text, kb.as_markup())


async def grace_days_picker_entry(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_grace_days_picker(bot, user, user_repo, session)
    await call.answer()


async def grace_days_set(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return

    action = call.data.rsplit(":", 1)[1]
    try:
        days_num = int(action)
    except ValueError:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    if days_num not in GRACE_DAYS_CHOICES and not (0 <= days_num <= 365):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await AppSettingRepository(session).set("expiry_grace_days", str(days_num))
    await AdminLogRepository(session).log(
        call.from_user.id, "setting", detail=f"expiry_grace_days={days_num}"
    )
    await _render_grace_days_picker(bot, user, user_repo, session)
    ans_msg = f"✅ مهلت پس از انقضا: {days_num} روز" if user.language == "fa" else f"Grace period set to {days_num}d"
    await call.answer(ans_msg)


async def settings_set_squad(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return

    choice = call.data.rsplit(":", 1)[1]
    val = "" if choice == "none" else choice
    await AppSettingRepository(session).set("default_squad_uuid", val)
    await AdminLogRepository(session).log(
        call.from_user.id, "setting", detail=f"default_squad_uuid={val[:40]}"
    )
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_settings(bot, user, user_repo, session)
    await call.answer(t(user.language or "fa", "toast_squads_updated"))
