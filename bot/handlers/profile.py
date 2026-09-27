"""«حساب کاربری» — wallet balance, login status, panel accounts and
the user's own order history («سفارش‌های من»)."""
from html import escape

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import User
from bot.db.repositories.order_repo import OrderRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.formatting import format_date, format_datetime, now_tz, parse_iso
from bot.services.menu import render_menu
from bot.services.remnawave import RemnawaveClient
from bot.services.topups import fmt

router = Router(name="profile")

SEPARATOR = "─" * 18


@router.callback_query(F.data == "menu:profile")
async def profile_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient,
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_profile(bot, user, user_repo, session, remnawave)
    await call.answer()


async def _render_profile(
    bot: Bot, user: User, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient,
) -> None:
    lang = user.language or "fa"

    wallet = await WalletRepository(session).get_wallet(user.telegram_id)
    accounts = await remnawave.get_users_by_telegram_id(user.telegram_id) or []
    orders_count = len(await OrderRepository(session).list_for_user(user.telegram_id, limit=100))

    status_key = "profile_status_verified" if user.is_verified else "profile_status_unverified"
    lines = [
        t(lang, "profile_title"),
        SEPARATOR,
        f"👛 {t(lang, 'user_balance')} : <b>{fmt(wallet.balance)}</b> {t(lang, 'svc_currency')}",
        f"🔐 {t(lang, 'profile_status')} : {t(lang, status_key)}",
        f"🗂 {t(lang, 'user_panel_accounts')} : <b>{len(accounts)}</b>",
        f"🧾 {t(lang, 'orders_count')} : <b>{orders_count}</b>",
    ]
    if user.created_at is not None:
        lines.append(f"📅 {t(lang, 'profile_member_since')} : "
                     f"{format_datetime(user.created_at, lang)}")
    if accounts:
        lines.append("")
        now = now_tz(get_settings().TIMEZONE)
        for acc in accounts[:5]:
            uname = escape(str(acc.get("username", "—")))
            expire_at = parse_iso(acc.get("expireAt"))
            if expire_at is None:
                exp_text = t(lang, "stats_no_expire")
            else:
                date_str = format_date(expire_at.astimezone(now.tzinfo), lang)
                exp_text = date_str
            lines.append(f"   • <code>{uname}</code> — {exp_text}")

    kb = InlineKeyboardBuilder()
    if lang == "fa":
        # Persian RTL: Left = My Orders, Right = Referral
        kb.button(text=t(lang, "btn_my_orders"), callback_data="profile:orders")
        kb.button(text=t(lang, "btn_referral"), callback_data="menu:referral")
    else:
        kb.button(text=t(lang, "btn_my_orders"), callback_data="profile:orders")
        kb.button(text=t(lang, "btn_referral"), callback_data="menu:referral")

    sizes = [2]
    if not user.is_verified:
        kb.button(text=t(lang, "btn_login"), callback_data="auth:login")
        sizes.append(1)
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    sizes.append(1)
    kb.adjust(*sizes)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data == "profile:orders")
async def my_orders(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    orders = await OrderRepository(session).list_for_user(user.telegram_id, limit=10)

    lines = [t(lang, "orders_title"), SEPARATOR]
    if not orders:
        lines.append(t(lang, "orders_empty"))
    else:
        for i, order in enumerate(orders):
            mark = "✅" if order.status == "paid" else "↩️"
            when = format_datetime(order.created_at, lang)
            lines.append(
                f"{mark} #{order.id} · {escape(order.service_name)} · "
                f"<b>{fmt(order.amount)}</b> {t(lang, 'svc_currency')}\n"
                f"   🕒 {when}"
            )
            if i < len(orders) - 1:
                lines.append("")

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_back"), callback_data="menu:profile")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()
