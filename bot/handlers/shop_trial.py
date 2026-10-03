"""Shop free trial and new service requests."""
import logging
import re
from datetime import datetime, timedelta, timezone
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, CopyTextButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, admin_thread_kwargs, parse_int, resolve_op
from bot.config import get_settings
from bot.db.repositories.support_repo import SupportMessageRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings
from bot.services.formatting import format_datetime, now_tz
from bot.services.menu import delete_message_silently, render_menu
from bot.services.remnawave import RemnawaveClient
from bot.states.service_request import ServiceRequestStates
from bot.handlers.shop_purchase import _maybe_reward_referrer

logger = logging.getLogger(__name__)
router = Router(name="shop_trial")

_safe_int = parse_int
_REQUEST_DONE_NOTIFIED: set[int] = set()


def _request_done_kb(telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=t("fa", "btn_request_done"),
        callback_data=f"svc:reqdone:{telegram_id}",
    )
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data.startswith("svc:reqdone:"))
async def request_done_notify(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession,
):
    """Admin pressed «سرویس ساخته شد» under a service request → tell the
    user their account is ready and they can hit «ورود» in the bot."""
    if call.from_user.id not in get_settings().ADMIN_IDS:
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return

    telegram_id = _safe_int(call.data.rsplit(":", 1)[1])
    if telegram_id is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    if telegram_id in _REQUEST_DONE_NOTIFIED:
        await call.answer(t("fa", "request_done_already"), show_alert=True)
        return
    _REQUEST_DONE_NOTIFIED.add(telegram_id)
    if len(_REQUEST_DONE_NOTIFIED) > 2000:
        _REQUEST_DONE_NOTIFIED.clear()

    target = await UserRepository(session).get_by_telegram_id(telegram_id)
    lang = (target.language if target else None) or "fa"

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_login"), callback_data="auth:login")
    kb.adjust(1)
    notified = False
    try:
        await bot.send_message(
            telegram_id,
            t(lang, "request_done_user"),
            reply_markup=kb.as_markup(),
        )
        notified = True
    except Exception:
        logger.exception("could not notify user %s about created service", telegram_id)
        _REQUEST_DONE_NOTIFIED.discard(telegram_id)

    if call.message is not None:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    await call.answer(t("fa", "request_done_admin") if notified else t("fa", "support_failed"))


@router.callback_query(F.data == "service:new")
async def service_new_request(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    """«درخواست سرویس جدید» / «اکانت تست رایگان». If trial is enabled, asks for username
    and provisions a 1-day / 1GB trial account, verifies user, and binds Telegram ID."""
    render_fn = resolve_op("render_menu", render_menu)

    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    store = await get_store_settings(session)
    if store.trial_enabled:
        if user.has_claimed_trial:
            kb = InlineKeyboardBuilder()
            kb.button(text=t(lang, "btn_services"), callback_data="menu:services")
            kb.button(text=t(lang, "btn_back"), callback_data="nav:welcome")
            kb.adjust(1)
            await render_fn(bot, user, user_repo, t(lang, "trial_already_claimed"), kb.as_markup())
            await call.answer()
            return

        await state.set_state(ServiceRequestStates.waiting_trial_username)
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="nav:welcome")
        kb.adjust(1)
        text = t(
            lang,
            "trial_prompt_username",
            traffic=store.trial_traffic_gb,
            days=store.trial_duration_days,
        )
        await render_fn(bot, user, user_repo, text, kb.as_markup())
        await call.answer()
        return

    # Fallback to free-text request if trial is disabled in settings
    await state.set_state(ServiceRequestStates.waiting_text)
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="nav:welcome")
    kb.adjust(1)
    await render_fn(bot, user, user_repo, t(lang, "request_prompt"), kb.as_markup())
    await call.answer()


@router.message(ServiceRequestStates.waiting_trial_username)
async def service_trial_username(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient, state: FSMContext,
):
    render_fn = resolve_op("render_menu", render_menu)
    reward_ref_fn = resolve_op("_maybe_reward_referrer", _maybe_reward_referrer)

    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language or "fa"
    raw_name = (message.text or "").strip()

    await delete_message_silently(bot, message.chat.id, message.message_id)

    if not re.match(r"^[a-zA-Z0-9_]{3,32}$", raw_name):
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="nav:welcome")
        kb.adjust(1)
        await render_fn(bot, user, user_repo, t(lang, "trial_username_invalid"), kb.as_markup())
        return

    store = await get_store_settings(session)
    if not store.trial_enabled or user.has_claimed_trial:
        await state.clear()
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_back"), callback_data="nav:welcome")
        kb.adjust(1)
        await render_fn(bot, user, user_repo, t(lang, "trial_already_claimed"), kb.as_markup())
        return

    existing = await remnawave.get_user_by_username(raw_name)
    if existing is not None:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="nav:welcome")
        kb.adjust(1)
        await render_fn(bot, user, user_repo, t(lang, "trial_username_taken"), kb.as_markup())
        return

    now = datetime.now(timezone.utc)
    dur_days = store.trial_duration_days if store.trial_duration_days > 0 else 1
    expire_at_iso = (now + timedelta(days=dur_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    traffic_bytes = max(1, store.trial_traffic_gb) * (1024 ** 3)
    squad_uuid = store.default_squad_uuid or None

    created = await remnawave.create_user(
        username=raw_name,
        expire_at_iso=expire_at_iso,
        traffic_limit_bytes=traffic_bytes,
        telegram_id=user.telegram_id,
        traffic_limit_strategy="NO_RESET",
        internal_squads=[squad_uuid] if squad_uuid else None,
    )

    if created is None:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="nav:welcome")
        kb.adjust(1)
        await render_fn(bot, user, user_repo, t(lang, "acc_error"), kb.as_markup())
        return

    await user_repo.set_verified(user)
    await user_repo.set_claimed_trial(user.telegram_id)
    await state.clear()

    # Reward referrer if applicable
    await reward_ref_fn(bot, session, remnawave, user)

    sub_url = created.get("subscriptionUrl")
    panel_user_id = created.get("id")

    kb = InlineKeyboardBuilder()
    if sub_url:
        kb.button(text=t(lang, "btn_copy_sub_link"), copy_text=CopyTextButton(text=sub_url))

    cfg_cb = f"cfg:acc:{panel_user_id}" if panel_user_id else "cfg:root"
    if lang == "fa":
        kb.button(text=t(lang, "btn_connection_guide"), callback_data="menu:guide")
        kb.button(text=t(lang, "btn_get_configs"), callback_data=cfg_cb)
    else:
        kb.button(text=t(lang, "btn_get_configs"), callback_data=cfg_cb)
        kb.button(text=t(lang, "btn_connection_guide"), callback_data="menu:guide")

    if lang == "fa":
        kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
        kb.button(text=t(lang, "btn_account_mgmt"), callback_data="menu:account")
    else:
        kb.button(text=t(lang, "btn_account_mgmt"), callback_data="menu:account")
        kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")

    if sub_url:
        kb.adjust(1, 2, 2)
    else:
        kb.adjust(2, 2)

    tz = get_settings().TIMEZONE
    dt_str = format_datetime(now_tz(tz), lang)

    receipt_lines = [
        f"🎁 <b>{t(lang, 'trial_receipt_title')}</b>",
        SEPARATOR,
        f"📅 {t(lang, 'receipt_date')} : <code>{dt_str}</code>",
        f"💳 {t(lang, 'receipt_status')} : <b>{t(lang, 'receipt_status_paid')}</b>",
        f"{t(lang, 'stats_account')} : <code>{escape(raw_name)}</code>",
        f"⏳ {t(lang, 'receipt_duration')} : <b>{t(lang, 'svc_days', days=dur_days)}</b>",
        f"🌐 {t(lang, 'receipt_traffic')} : <b>{t(lang, 'svc_gb', gb=store.trial_traffic_gb)}</b>",
    ]
    if sub_url:
        receipt_lines.append(SEPARATOR)
        receipt_lines.append(t(lang, "buy_success_link", url=escape(sub_url)))
    receipt_lines.append(f"\n💡 {t(lang, 'trial_welcome_hint')}")

    await render_fn(bot, user, user_repo, "\n".join(receipt_lines), kb.as_markup())

    tg_username = f"@{user.username}" if user.username else "—"
    admin_text = (
        f"🎁 <b>سرویس تست ایجاد شد</b>\n\n"
        f"👤 کاربر: {escape(user.username or '')} (<code>{user.telegram_id}</code>)\n"
        f"🔑 اکانت پنل: <code>{escape(raw_name)}</code>\n"
        f"🌐 حجم: {store.trial_traffic_gb} GB | ⏳ مدت: {dur_days} روز\n"
        f"🔗 شناسه تلگرام: {escape(tg_username)}"
    )
    thread_kwargs = admin_thread_kwargs(store, get_settings(), kind="orders")
    try:
        await bot.send_message(get_settings().ADMIN_CHAT_ID, admin_text, **thread_kwargs)
    except Exception:
        logger.exception("failed to notify admin about trial user")


@router.message(ServiceRequestStates.waiting_text)
async def service_new_forward(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    render_fn = resolve_op("render_menu", render_menu)

    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    settings = get_settings()

    store = await get_store_settings(session)
    topic_id = (
        store.topic_support
        or store.topic_orders
        or settings.ADMIN_TOPIC_SUPPORT
        or settings.ADMIN_TOPIC_ORDERS
    )
    thread_kwargs = admin_thread_kwargs(topic_id=topic_id)
    sent = False
    tg_username = f"@{message.from_user.username}" if message.from_user.username else "—"
    admin_header_text = t(
        "fa", "request_admin_header",
        name=escape(message.from_user.full_name),
        tid=user.telegram_id,
        username=escape(tg_username),
    )
    repo = SupportMessageRepository(session)

    try:
        content = await bot.copy_message(
            chat_id=settings.ADMIN_CHAT_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            **thread_kwargs,
        )
        header = await bot.send_message(
            settings.ADMIN_CHAT_ID,
            admin_header_text,
            reply_parameters={"message_id": content.message_id},
            reply_markup=_request_done_kb(user.telegram_id),
            **thread_kwargs,
        )
        await repo.map_message(content.message_id, user.telegram_id)
        await repo.map_message(header.message_id, user.telegram_id)
        sent = True
    except Exception as exc:
        logger.warning(
            "Failed to deliver new-service request to admin chat %s (%s). Attempting fallback...",
            settings.ADMIN_CHAT_ID, exc,
        )

    if not sent and settings.ADMIN_IDS:
        for admin_id in settings.ADMIN_IDS:
            try:
                content = await bot.copy_message(
                    chat_id=admin_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
                header = await bot.send_message(
                    admin_id,
                    admin_header_text,
                    reply_parameters={"message_id": content.message_id},
                    reply_markup=_request_done_kb(user.telegram_id),
                )
                await repo.map_message(content.message_id, user.telegram_id)
                await repo.map_message(header.message_id, user.telegram_id)
                sent = True
            except Exception as admin_exc:
                logger.warning(
                    "Fallback delivery of service request to admin %s failed: %s",
                    admin_id, admin_exc,
                )

    await delete_message_silently(bot, message.chat.id, message.message_id)
    await state.clear()

    lang = user.language or "fa"
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    kb.adjust(1)
    await render_fn(
        bot, user, user_repo,
        t(lang, "request_sent" if sent else "support_failed"),
        kb.as_markup(),
    )
