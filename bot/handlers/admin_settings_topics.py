"""Admin Telegram Supergroup Topics Settings."""
import logging
import time
from html import escape

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, is_admin, resolve_op
from bot.config import get_settings
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings
from bot.services.menu import render_menu

logger = logging.getLogger(__name__)
router = Router(name="admin_settings_topics")

_cached_admin_group_title: str | None = None
_cached_admin_group_title_time: float = 0


async def get_admin_group_title(bot: Bot) -> str | None:
    global _cached_admin_group_title, _cached_admin_group_title_time
    now = time.time()
    if _cached_admin_group_title is not None and (now - _cached_admin_group_title_time) < 300:
        return _cached_admin_group_title
    cfg = get_settings()
    chat_id = getattr(cfg, "ADMIN_CHAT_ID", None)
    if not chat_id:
        return None
    try:
        chat = await bot.get_chat(chat_id)
        _cached_admin_group_title = chat.title or None
        _cached_admin_group_title_time = now
        return _cached_admin_group_title
    except Exception:
        return _cached_admin_group_title


async def _render_topics_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    store_fn = resolve_op("get_store_settings", get_store_settings)
    render_menu_fn = resolve_op("render_menu", render_menu)
    group_title_fn = resolve_op("_get_admin_group_title", get_admin_group_title)

    lang = user.language or "fa"
    store = await store_fn(session)
    kb = InlineKeyboardBuilder()

    t_topups = f"{store.topic_topups} (Topups)" if store.topic_topups is not None else "— (Topups)"
    t_orders = f"{store.topic_orders} (Orders)" if store.topic_orders is not None else "— (Orders)"
    t_support = f"{store.topic_support} (Support)" if store.topic_support is not None else "— (Support)"
    t_alerts = f"{store.topic_alerts} (Alerts)" if store.topic_alerts is not None else "— (Alerts)"
    t_crypto = f"{store.topic_crypto} (Crypto)" if store.topic_crypto is not None else "— (Crypto)"
    t_errors = f"{store.topic_errors} (Errors)" if store.topic_errors is not None else "— (Errors)"

    if lang == "fa":
        kb.button(text="🛒 تاپیک سفارشات", callback_data="adm:set:topic_orders")
        kb.button(text="💳 تاپیک شارژها", callback_data="adm:set:topic_topups")
        kb.button(text="🚨 تاپیک هشدار و بکاپ", callback_data="adm:set:topic_alerts")
        kb.button(text="🎧 تاپیک پشتیبانی", callback_data="adm:set:topic_support")
        kb.button(text="⚠️ تاپیک لاگ‌های ارور", callback_data="adm:set:topic_errors")
        kb.button(text="💎 تاپیک کریپتو و نرخ", callback_data="adm:set:topic_crypto")
    else:
        kb.button(text="💳 Top-ups Topic", callback_data="adm:set:topic_topups")
        kb.button(text="🛒 Orders Topic", callback_data="adm:set:topic_orders")
        kb.button(text="🎧 Support Topic", callback_data="adm:set:topic_support")
        kb.button(text="🚨 Alerts & Backup", callback_data="adm:set:topic_alerts")
        kb.button(text="💎 Crypto & Rates Topic", callback_data="adm:set:topic_crypto")
        kb.button(text="⚠️ Error Logs Topic", callback_data="adm:set:topic_errors")

    kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
    kb.adjust(2, 2, 2, 1)

    grp_title = await group_title_fn(bot)
    topics_title = f"{t(lang, 'settings_topics_title')} ({escape(grp_title)})" if grp_title else t(lang, 'settings_topics_title')

    text = (
        f"{topics_title}\n{SEPARATOR}\n"
        f"💳 <b>تاپیک تایید شارژها :</b> {t_topups}\n"
        f"🛒 <b>تاپیک ثبت سفارشات :</b> {t_orders}\n"
        f"🎧 <b>تاپیک پیام‌های پشتیبانی :</b> {t_support}\n"
        f"🚨 <b>تاپیک هشدارهای سیستم و بکاپ :</b> {t_alerts}\n"
        f"💎 <b>تاپیک کریپتو و نرخ ارز :</b> {t_crypto}\n"
        f"⚠️ <b>تاپیک لاگ‌های ارور :</b> {t_errors}\n\n"
        f"💡 جهت اتصال هر بخش به تاپیک، روی دکمه مربوطه کلیک کنید و شناسه عددی (Topic ID) آن را ارسال نمایید.\n"
        f"(برای غیرفعال‌سازی هر تاپیک مقدار 0 یا /skip ارسال کنید)"
    ) if lang == "fa" else (
        f"{topics_title}\n{SEPARATOR}\n"
        f"💳 <b>Top-ups Topic :</b> {t_topups}\n"
        f"🛒 <b>Orders Topic :</b> {t_orders}\n"
        f"🎧 <b>Support Topic :</b> {t_support}\n"
        f"🚨 <b>System Alerts & Backup :</b> {t_alerts}\n"
        f"💎 <b>Crypto & Rates Topic :</b> {t_crypto}\n"
        f"⚠️ <b>Error Logs Topic :</b> {t_errors}\n\n"
        f"<i>(Send 0 or /skip to disable any topic)</i>"
    )
    await render_menu_fn(bot, user, user_repo, text, kb.as_markup())


@router.callback_query(F.data == "adm:settings:topics")
async def topics_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    render_topics_fn = resolve_op("_render_topics_settings", _render_topics_settings)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_topics_fn(bot, user, user_repo, session)
    await call.answer()
