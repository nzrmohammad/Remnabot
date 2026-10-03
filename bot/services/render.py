"""Centralized menu rendering services for user dashboards, services, and wallet."""
import logging
import sys

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.menu import render_menu
from bot.services.service_display import fmt_price, fmt_traffic, service_block

logger = logging.getLogger(__name__)


async def render_services(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
    renew_account_id: str | None = None,
) -> None:
    """Render the active services catalog keyboard and balance status."""
    sr = sys.modules.get("bot.handlers.service_request")
    s_repo_cls = getattr(sr, "ServiceRepository", ServiceRepository) if sr else ServiceRepository
    w_repo_cls = getattr(sr, "WalletRepository", WalletRepository) if sr else WalletRepository
    render_fn = getattr(sr, "render_menu", render_menu) if sr else render_menu

    lang = user.language or "fa"
    services = await s_repo_cls(session).list_active()
    wallet = await w_repo_cls(session).get_wallet(user.telegram_id)
    balance = wallet.balance

    lines = [t(lang, "services_title"), SEPARATOR]
    if not services:
        lines.append(t(lang, "services_active_empty"))
    else:
        for i, service in enumerate(services, start=1):
            indicator = "✅" if balance >= service.price else "❌"
            lines.append(f"{i}) {indicator} {service_block(service, lang)}")
            if i < len(services):
                lines.append("")
        lines.append(SEPARATOR)
        lines.append(t(lang, "services_policy_hint"))

    kb = InlineKeyboardBuilder()
    for service in services:
        indicator = "✅" if balance >= service.price else "❌"
        cb = (
            f"svc:buya:{service.id}:{renew_account_id}"
            if renew_account_id
            else f"svc:view:{service.id}"
        )
        traffic_str = fmt_traffic(service.traffic_gb, lang)
        price_str = f"{fmt_price(service.price)} {t(lang, 'svc_currency')}"
        kb.button(
            text=f"{indicator} {service.name} — {traffic_str} — {price_str}",
            callback_data=cb,
        )
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    kb.adjust(1)

    await render_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())


async def render_wallet(
    bot: Bot, user, user_repo: UserRepository, wallet_repo: WalletRepository, lang: str,
) -> None:
    """Render user wallet balance and options."""
    w_mod = sys.modules.get("bot.handlers.wallet")
    render_fn = getattr(w_mod, "render_menu", render_menu) if w_mod else render_menu

    wallet = await wallet_repo.get_wallet(user.telegram_id)
    pending = await wallet_repo.pending_count(user.telegram_id)

    lines = [
        t(lang, "wallet_title"),
        SEPARATOR,
        t(lang, "wallet_balance", balance=fmt(wallet.balance)),
    ]
    if pending:
        lines.append(t(lang, "wallet_pending", count=pending))

    kb = InlineKeyboardBuilder()
    if lang == "fa":
        kb.button(text=t(lang, "btn_topup_history"), callback_data="wallet:history")
        kb.button(text=t(lang, "btn_topup"), callback_data="wallet:topup")
    else:
        kb.button(text=t(lang, "btn_topup"), callback_data="wallet:topup")
        kb.button(text=t(lang, "btn_topup_history"), callback_data="wallet:history")

    menu_label = "🏠 منوی اصلی" if lang == "fa" else "🏠 Main Menu"
    kb.button(text=menu_label, callback_data="nav:main_menu")
    kb.adjust(2, 1)

    await render_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())


_render_services = render_services
_render_wallet = render_wallet
