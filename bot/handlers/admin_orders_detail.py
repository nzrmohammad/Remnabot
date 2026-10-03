"""Admin Order Detail View, Refund Processing, and Panel Subscription Reversion."""
import logging
from datetime import datetime, timezone
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt, is_admin, parse_int, resolve_op
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.order_repo import OrderRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.formatting import format_datetime
from bot.services.menu import render_menu
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)
router = Router(name="admin_orders_detail")

_is_admin = is_admin
_safe_int = parse_int
GB = 1024 ** 3

PLATFORM_EMOJI = {
    "android": "🤖",
    "ios": "🍏",
    "windows": "🖥",
    "macos": "💻",
    "linux": "🐧",
}


def _back_admin(lang: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(1)
    return kb


async def _revert_panel_subscription(remnawave: RemnawaveClient, order) -> None:
    """Roll back what the purchase granted: subtract duration/traffic.

    Best-effort: if the panel is down or the account is gone, the wallet
    refund already happened, so we only log.
    """
    accounts = await remnawave.get_users_by_telegram_id(order.telegram_id)
    if not accounts:
        return
    acc = next(
        (a for a in accounts if str(a.get("id")) == str(order.panel_user_id)), None
    )
    if acc is None:
        return
    try:
        current_limit = int(acc.get("trafficLimitBytes") or 0)
    except (ValueError, TypeError):
        current_limit = 0
    new_limit = current_limit
    if (order.traffic_gb or 0) > 0 and current_limit > 0:
        new_limit = max(0, current_limit - int(order.traffic_gb) * GB)
    expire_iso = acc.get("expireAt")
    new_expire_iso = expire_iso
    if (order.duration_days or 0) > 0 and expire_iso:
        try:
            from datetime import timedelta
            cur = datetime.fromisoformat(str(expire_iso).replace("Z", "+00:00"))
            new_expire_iso = (cur - timedelta(days=int(order.duration_days))).astimezone(
                timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError):
            new_expire_iso = expire_iso
    await remnawave.update_user_subscription(
        int(order.panel_user_id), str(new_expire_iso), int(new_limit)
    )


async def _render_order_detail(
    bot: Bot,
    user,
    user_repo: UserRepository,
    session: AsyncSession,
    order_id: int,
    toast: str | None = None,
    status: str = "all",
    page: int = 0,
) -> None:
    order_repo_cls = resolve_op("OrderRepository", OrderRepository)
    render_menu_fn = resolve_op("render_menu", render_menu)

    lang = user.language or "fa"
    order = await order_repo_cls(session).get(order_id)
    if order is None:
        await render_menu_fn(
            bot,
            user,
            user_repo,
            t(lang, "acc_error"),
            _back_admin(lang).as_markup(),
        )
        return

    status_key = "ord_status_paid" if order.status == "paid" else "ord_status_refunded"
    lines = [
        f"🧾 <b>{t(lang, 'ord_title')} #{order.id}</b>",
        SEPARATOR,
        f"📦 {escape(order.service_name)}",
        f"💰 {fmt(order.amount)} {t(lang, 'svc_currency')}",
        f"📌 {t(lang, 'ord_status')} : <b>{t(lang, status_key)}</b>",
        f"👤 <code>{order.telegram_id}</code>",
        f"🔑 <code>{escape(str(order.panel_username or '—'))}</code>",
        f"🕒 {format_datetime(order.created_at, lang)}",
    ]
    if order.subscription_url:
        lines.append(f"\n🔗 <code>{escape(order.subscription_url)}</code>")
    if toast:
        lines.insert(2, toast)

    kb = InlineKeyboardBuilder()
    if order.status == "paid":
        kb.button(
            text=t(lang, "btn_refund"),
            callback_data=f"adm:ord:ref:{order.id}:{status}:{page}",
        )
        kb.adjust(1)
    kb.button(text=t(lang, "btn_back"), callback_data=f"adm:orders:{status}:{page}")
    kb.adjust(1)
    await render_menu_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data.startswith("adm:ord:"))
async def order_view_or_refund(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    remnawave: RemnawaveClient | None = None,
):
    """Dispatches: adm:ord:{id} | adm:ord:ref:{id} | adm:ord:refyes:{id}."""
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    parts = call.data.split(":")
    if len(parts) >= 3 and parts[2] in ("ref", "refyes"):
        action = parts[2]
        order_id = _safe_int(parts[3])
        status = parts[4] if len(parts) > 4 else "all"
        page = _safe_int(parts[5]) if len(parts) > 5 else 0
    else:
        action = "view"
        order_id = _safe_int(parts[2])
        status = parts[3] if len(parts) > 3 else "all"
        page = _safe_int(parts[4]) if len(parts) > 4 else 0

    if order_id is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    if page is None:
        page = 0

    order_repo_cls = resolve_op("OrderRepository", OrderRepository)
    render_menu_fn = resolve_op("render_menu", render_menu)
    render_detail_fn = resolve_op("_render_order_detail", _render_order_detail)

    order_repo = order_repo_cls(session)
    order = await order_repo.get(order_id)
    if order is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    if action == "refyes":
        claimed = await order_repo.claim_refund(order_id)
        if claimed is None:
            await call.answer(t("fa", "acc_error"), show_alert=True)
            return
        order = claimed
        new_balance = await WalletRepository(session).add_balance_atomic(
            order.telegram_id, order.amount
        )
        if order.panel_user_id is not None and remnawave is not None:
            try:
                await _revert_panel_subscription(remnawave, order)
            except Exception:
                pass
        await AdminLogRepository(session).log(
            call.from_user.id,
            "refund",
            detail=f"#{order.id} user={order.telegram_id} amount={order.amount}",
        )
        target = await UserRepository(session).get_by_telegram_id(order.telegram_id)
        user_lang = (target.language if target else None) or "fa"
        try:
            await bot.send_message(
                order.telegram_id,
                t(
                    user_lang,
                    "refund_notice_user",
                    id=order.id,
                    amount=fmt(order.amount),
                ),
            )
        except Exception:
            pass
        await render_detail_fn(
            bot,
            user,
            user_repo,
            session,
            order_id,
            toast=t(
                lang,
                "ord_refunded",
                amount=fmt(order.amount),
                balance=fmt(new_balance),
            ),
            status=status,
            page=page,
        )
        await call.answer()
        return

    if action == "ref":
        kb = InlineKeyboardBuilder()
        kb.button(
            text=t(lang, "btn_yes_delete"),
            callback_data=f"adm:ord:refyes:{order.id}:{status}:{page}",
        )
        kb.button(
            text=t(lang, "btn_cancel"),
            callback_data=f"adm:ord:{order.id}:{status}:{page}",
        )
        kb.adjust(2)
        await render_menu_fn(
            bot,
            user,
            user_repo,
            t(
                lang,
                "ord_refund_confirm",
                id=order.id,
                name=escape(order.service_name),
                amount=fmt(order.amount),
            ),
            kb.as_markup(),
        )
        await call.answer()
        return

    # plain detail view
    await state.clear()
    await render_detail_fn(bot, user, user_repo, session, order_id, status=status, page=page)
    await call.answer()
