"""Admin settings FSM wizard for editing individual store values."""
import logging
import re

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, is_admin
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.user_repo import UserRepository
from bot.handlers.admin_settings_common import (
    SETTING_DESCRIPTIONS,
    SETTING_FIELDS,
    _parse_int,
    delete_message_silently,
    render_menu,
)
from bot.handlers.admin_settings_crypto import _render_crypto_settings
from bot.handlers.admin_settings_pickers import (
    _render_grace_days_picker,
    _render_remind_days_picker,
)
from bot.handlers.admin_settings_topics import _render_topics_settings
from bot.handlers.admin_settings_trial_referral import (
    _render_referral_settings,
    _render_trial_settings,
)
from bot.handlers.admin_settings_views import _render_settings
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings
from bot.services.remnawave import RemnawaveClient
from bot.states.admin import SettingsStates

logger = logging.getLogger(__name__)


async def settings_edit_start(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    field = call.data.rsplit(":", 1)[1]
    if field not in SETTING_FIELDS:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language


    # Special handling for expiry remind days: show multi-select picker!
    if field == "expiry_remind_days":
        await state.clear()
        await _render_remind_days_picker(bot, user, user_repo, session)
        await call.answer()
        return

    # Special handling for expiry grace days: show single-select picker!
    if field == "expiry_grace_days":
        await state.clear()
        await _render_grace_days_picker(bot, user, user_repo, session)
        await call.answer()
        return

    # Special handling for default squad: show squad list buttons!
    if field == "default_squad_uuid":
        await state.clear()
        store = await get_store_settings(session)
        squads = await remnawave.get_internal_squads()
        lines = [
            "🧩 <b>انتخاب اسکواد پیش‌فرض فروشگاه</b>" if lang == "fa" else "🧩 <b>Select Default Store Squad</b>",
            SEPARATOR,
            "اسکوادی که اکانت‌های جدید پس از خرید خودکار به آن متصل می‌شوند را انتخاب کنید:" if lang == "fa" else "Select default squad for new accounts created via shop:",
        ]
        kb = InlineKeyboardBuilder()
        for sq in squads:
            sq_name = sq.get("name") or "Squad"
            sq_uuid = sq.get("uuid")
            is_active = (store.default_squad_uuid == sq_uuid)
            icon = "✅" if is_active else "🧩"
            kb.button(text=f"{icon} {sq_name}", callback_data=f"adm:setsquad:{sq_uuid}")
        kb.button(
            text="❌ بدون اسکواد پیش‌فرض (غیرفعال)" if lang == "fa" else "❌ No Default Squad (None)",
            callback_data="adm:setsquad:none",
        )
        kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
        sq_count = len(squads)
        sizes = [2] * (sq_count // 2)
        if sq_count % 2:
            sizes.append(1)
        sizes += [1, 1]
        kb.adjust(*sizes)
        await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
        await call.answer()
        return

    await state.set_state(SettingsStates.waiting_value)
    await state.update_data(settings_field=field)

    cancel_target = (
        "adm:settings:crypto" if ("ton_" in field or field in ("crypto_enabled", "usdt_rate_toman"))
        else ("adm:settings:topics" if field.startswith("topic_")
        else ("adm:settings:trial" if "trial" in field else ("adm:settings:referral" if "referral" in field else "adm:settings")))
    )
    kb = InlineKeyboardBuilder()
    if field == "card_number":
        store = await get_store_settings(session)
        c_badge = "✅" if store.card_enabled else "❌"
        card_toggle_txt = f"💳 وضعیت درگاه کارت {c_badge}" if lang == "fa" else f"💳 Card Gateway {c_badge}"
        kb.button(text=card_toggle_txt, callback_data="adm:settings:toggle:card_enabled")
    kb.button(text=t(lang, "btn_cancel"), callback_data=cancel_target)
    kb.adjust(1)

    prompt_key = SETTING_FIELDS[field][0]
    extra = t(lang, "skip_for_none") if SETTING_FIELDS[field][1] is False else ""
    desc = SETTING_DESCRIPTIONS.get(lang, SETTING_DESCRIPTIONS["fa"]).get(field, "")

    parts = [f"⚙️ <b>{t(lang, prompt_key)}</b>", SEPARATOR]
    if desc:
        parts.append(f"💡 {desc}\n")
    parts.append(t(lang, "settings_value_prompt"))
    if extra:
        parts.append(f"\n{extra}")

    await render_menu(bot, user, user_repo, "\n".join(parts), kb.as_markup())
    await call.answer()


async def settings_value_save(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    data = await state.get_data()
    field = data.get("settings_field", "card_number")
    is_numeric = SETTING_FIELDS.get(field, ("", False))[1]

    raw = message.text.strip()
    value = raw
    SKIP_WORDS = ("/skip", "-", "—")
    cancel_target = (
        "adm:settings:crypto" if ("ton_" in field or field in ("crypto_enabled", "usdt_rate_toman"))
        else ("adm:settings:topics" if field.startswith("topic_")
        else ("adm:settings:trial" if "trial" in field else ("adm:settings:referral" if "referral" in field else "adm:settings")))
    )

    if field.startswith("topic_") or field == "expiry_grace_days":
        if raw in SKIP_WORDS or raw == "0":
            value = ""
        else:
            parsed = _parse_int(raw)
            if parsed is None or parsed < 0:
                kb = InlineKeyboardBuilder()
                kb.button(text=t(lang, "btn_cancel"), callback_data=cancel_target)
                kb.adjust(1)
                await render_menu(bot, user, user_repo, t(lang, "settings_invalid_number"), kb.as_markup())
                return
            value = str(parsed)
    elif field in ("trial_enabled", "referral_enabled"):
        parsed = _parse_int(raw)
        if parsed not in (0, 1):
            kb = InlineKeyboardBuilder()
            kb.button(text=t(lang, "btn_cancel"), callback_data=cancel_target)
            kb.adjust(1)
            await render_menu(bot, user, user_repo, "❌ لطفاً فقط عدد 1 (فعال) یا 0 (غیرفعال) را وارد کنید:", kb.as_markup())
            return
        value = str(parsed)
    elif is_numeric:
        parsed = _parse_int(raw)
        if parsed is None or parsed < 0:
            kb = InlineKeyboardBuilder()
            kb.button(text=t(lang, "btn_cancel"), callback_data=cancel_target)
            kb.adjust(1)
            await render_menu(bot, user, user_repo, t(lang, "settings_invalid_number"), kb.as_markup())
            return
        value = str(parsed)
    elif field == "support_contact":
        if raw in SKIP_WORDS or raw == "0":
            value = ""
            await AppSettingRepository(session).set("support_direct_enabled", "0")
        else:
            clean_contact = raw.strip()
            t_me_match = re.match(
                r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([A-Za-z0-9_]{3,32})/?$",
                clean_contact,
                re.IGNORECASE,
            )
            user_match = re.match(r"^@?([A-Za-z0-9_]{3,32})$", clean_contact)
            url_match = re.match(r"^https?://[^\s]+$", clean_contact)

            if t_me_match:
                uname = t_me_match.group(1)
                value = f"https://t.me/{uname}"
            elif user_match:
                uname = user_match.group(1)
                value = f"@{uname}"
            elif url_match:
                value = clean_contact
            else:
                kb = InlineKeyboardBuilder()
                kb.button(text=t(lang, "btn_cancel"), callback_data="adm:settings")
                kb.adjust(1)
                err_msg = (
                    "❌ فرمت نامعتبر است.\n\n"
                    "لطفاً آیدی پشتیبانی را با <b>@</b> (مانند <code>@SupportUsername</code>) "
                    "یا لینک تلگرام (مانند <code>t.me/SupportUsername</code>) ارسال کنید:\n\n"
                    "<i>(برای حذف مقدار می‌توانید /skip یا 0 بفرستید)</i>"
                ) if lang == "fa" else (
                    "❌ Invalid format.\n\n"
                    "Please provide a Telegram username with <b>@</b> (e.g. <code>@SupportUsername</code>) "
                    "or link (e.g. <code>t.me/SupportUsername</code>):\n\n"
                    "<i>(Send /skip or 0 to clear)</i>"
                )
                await render_menu(bot, user, user_repo, err_msg, kb.as_markup())
                return
    elif raw in SKIP_WORDS:
        value = ""

    await AppSettingRepository(session).set(field, value)
    await AdminLogRepository(session).log(
        message.from_user.id, "setting", detail=f"{field}={value[:40]}"
    )
    await state.clear()
    if field.startswith("topic_"):
        await _render_topics_settings(bot, user, user_repo, session)
    elif "ton_" in field or field in ("crypto_enabled", "usdt_rate_toman"):
        await _render_crypto_settings(bot, user, user_repo, session)
    elif "trial" in field:
        await _render_trial_settings(bot, user, user_repo, session)
    elif "referral" in field:
        await _render_referral_settings(bot, user, user_repo, session)
    else:
        await _render_settings(bot, user, user_repo, session)
