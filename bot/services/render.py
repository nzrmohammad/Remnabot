"""Centralized menu rendering services for user dashboards, services, and wallet."""
import logging
from typing import Any

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
    remnawave: Any = None,
) -> None:
    """Render the active services catalog keyboard and balance status with squad-aware filtering."""
    lang = user.language or "fa"
    active_squad_uuids: set[str] = set()
    has_active_account = False
    if remnawave:
        try:
            accounts = await remnawave.get_users_by_telegram_id(user.telegram_id) or []
            target_accounts = (
                [a for a in accounts if str(a.get("id")) == str(renew_account_id)]
                if renew_account_id
                else accounts
            )
            for acc in target_accounts:
                status = str(acc.get("status", "")).upper()
                if status not in ("DELETED",):
                    has_active_account = True
                    raw_sqs = (
                        acc.get("activeInternalSquads")
                        or acc.get("internalSquads")
                        or acc.get("squads")
                        or []
                    )
                    for sq in raw_sqs:
                        if isinstance(sq, dict):
                            uid = sq.get("uuid") or sq.get("id")
                            if uid:
                                active_squad_uuids.add(str(uid).strip().lower())
                        elif isinstance(sq, str):
                            active_squad_uuids.add(sq.strip().lower())
        except Exception as exc:
            logger.debug("Failed fetching user squads for services catalog: %s", exc)

    all_services = await ServiceRepository(session).list_active()
    services = []
    for s in all_services:
        is_addon = (
            (s.traffic_gb > 0 and s.duration_days == 0)
            or (s.duration_days > 0 and s.traffic_gb == 0)
            or bool(s.badge and s.badge.lower() in ("traffic", "time"))
        )
        if is_addon:
            # Add-ons strictly require an active account and matching squad
            if not has_active_account or not s.squad_uuid:
                continue
            if str(s.squad_uuid).strip().lower() not in active_squad_uuids:
                continue
        services.append(s)
    wallet = await WalletRepository(session).get_wallet(user.telegram_id)
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

    if not renew_account_id:
        try:
            from bot.services.app_settings import get_store_settings
            store_settings = await get_store_settings(session)
            if getattr(store_settings, "custom_plan_enabled", True):
                custom_btn_label = "🛠 ساخت بسته دلخواه (سفارشی)" if lang == "fa" else "🛠 Build Custom Plan"
                kb.button(text=custom_btn_label, callback_data="menu:custom_plan")
        except Exception:
            pass

    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


async def render_wallet(
    bot: Bot, user, user_repo: UserRepository, wallet_repo: WalletRepository, lang: str,
) -> None:
    """Render user wallet balance and options."""
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

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


_render_services = render_services
_render_wallet = render_wallet
