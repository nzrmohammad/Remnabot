"""Admin Orders List, Filtering, Search, and Pagination."""
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt, is_admin, parse_int, resolve_op
from bot.db.repositories.order_repo import OrderRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.menu import delete_message_silently, render_menu
from bot.states.admin import OrderManagementStates

logger = logging.getLogger(__name__)
router = Router(name="admin_orders_list")

_is_admin = is_admin
_safe_int = parse_int

ORDERS_PER_PAGE = 8


async def _render_orders_list(
    bot: Bot,
    user,
    user_repo: UserRepository,
    session: AsyncSession,
    status: str = "all",
    page: int = 0,
    query: str | None = None,
) -> None:
    order_repo_cls = resolve_op("OrderRepository", OrderRepository)
    render_menu_fn = resolve_op("render_menu", render_menu)

    lang = user.language or "fa"
    order_repo = order_repo_cls(session)
    total_rev = await order_repo.total_revenue()
    total_cnt = await order_repo.count()
    counts = await order_repo.status_counts(query=query)
    matching_count = counts.get(status, 0) if status != "all" else counts.get("all", 0)
    total_pages = max(1, (matching_count + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    orders = await order_repo.list_filtered(
        status=status, query=query, offset=page * ORDERS_PER_PAGE, limit=ORDERS_PER_PAGE
    )

    filter_title_map = {
        "all": "همه" if lang == "fa" else "All",
        "paid": "موفق" if lang == "fa" else "Paid",
        "pending": "در انتظار" if lang == "fa" else "Pending",
        "failed": "ناموفق" if lang == "fa" else "Failed",
        "refunded": "مرجوعی" if lang == "fa" else "Refunded",
    }
    curr_filter_title = filter_title_map.get(status, status)

    lines = [
        t(lang, "sales_title"),
        SEPARATOR,
        f"{t(lang, 'sales_total')} : <b>{fmt(total_rev)}</b> {t(lang, 'svc_currency')}",
        f"{t(lang, 'sales_count')} : <b>{total_cnt}</b>",
        SEPARATOR,
    ]
    if query:
        lines.append(t(lang, "ord_search_active", query=escape(query)))
    lines.append(t(lang, "ord_active_filter", filter=curr_filter_title, count=matching_count))
    if matching_count > 0:
        lines.append(t(lang, "ord_page_info", page=page + 1, pages=total_pages))
    lines.append(SEPARATOR)

    if not orders:
        if query or status != "all":
            lines.append(t(lang, "ord_empty_filtered"))
        else:
            lines.append(t(lang, "sales_empty"))

    kb = InlineKeyboardBuilder()

    def _fmt_filter_btn(st: str) -> str:
        c = counts.get(st, 0)
        label = t(lang, f"ord_filter_{st}", n=c)
        return f"• {label} •" if st == status else label

    if lang == "fa":
        # Row 1 (RTL: pending, paid, all)
        kb.button(text=_fmt_filter_btn("pending"), callback_data="adm:orders:pending:0")
        kb.button(text=_fmt_filter_btn("paid"), callback_data="adm:orders:paid:0")
        kb.button(text=_fmt_filter_btn("all"), callback_data="adm:orders:all:0")
        # Row 2 (RTL: refunded, failed)
        kb.button(text=_fmt_filter_btn("refunded"), callback_data="adm:orders:refunded:0")
        kb.button(text=_fmt_filter_btn("failed"), callback_data="adm:orders:failed:0")
    else:
        # LTR
        kb.button(text=_fmt_filter_btn("all"), callback_data="adm:orders:all:0")
        kb.button(text=_fmt_filter_btn("paid"), callback_data="adm:orders:paid:0")
        kb.button(text=_fmt_filter_btn("pending"), callback_data="adm:orders:pending:0")
        kb.button(text=_fmt_filter_btn("failed"), callback_data="adm:orders:failed:0")
        kb.button(text=_fmt_filter_btn("refunded"), callback_data="adm:orders:refunded:0")
    kb.adjust(3, 2)

    # Search Row
    if query:
        if lang == "fa":
            kb.button(text=t(lang, "btn_order_clear_search"), callback_data=f"adm:orders:clear:{status}")
            kb.button(text=t(lang, "btn_order_search"), callback_data="adm:orders:search")
        else:
            kb.button(text=t(lang, "btn_order_search"), callback_data="adm:orders:search")
            kb.button(text=t(lang, "btn_order_clear_search"), callback_data=f"adm:orders:clear:{status}")
        kb.adjust(2)
    else:
        kb.button(text=t(lang, "btn_order_search"), callback_data="adm:orders:search")
        kb.adjust(1)

    # Order item buttons
    for order in orders:
        badge = {
            "paid": "✅",
            "pending": "⏳",
            "failed": "❌",
            "refunded": "🔄",
        }.get(order.status, "📦")
        btn_title = f"{badge} #{order.id} — {order.service_name} — {fmt(order.amount)}"
        kb.button(
            text=btn_title,
            callback_data=f"adm:ord:{order.id}:{status}:{page}",
        )
        kb.adjust(1)

    # Pagination controls
    if total_pages > 1:
        if lang == "fa":
            if page < total_pages - 1:
                kb.button(text="بعدی ➡️", callback_data=f"adm:orders:{status}:{page + 1}")
            else:
                kb.button(text=" ", callback_data="adm:noop")

            kb.button(text=f"📄 {page + 1}/{total_pages}", callback_data="adm:noop")

            if page > 0:
                kb.button(text="⬅️ قبلی", callback_data=f"adm:orders:{status}:{page - 1}")
            else:
                kb.button(text=" ", callback_data="adm:noop")
        else:
            if page > 0:
                kb.button(text="⬅️ Prev", callback_data=f"adm:orders:{status}:{page - 1}")
            else:
                kb.button(text=" ", callback_data="adm:noop")

            kb.button(text=f"📄 {page + 1}/{total_pages}", callback_data="adm:noop")

            if page < total_pages - 1:
                kb.button(text="Next ➡️", callback_data=f"adm:orders:{status}:{page + 1}")
            else:
                kb.button(text=" ", callback_data="adm:noop")
        kb.adjust(3)

    kb.button(text="🔙 بازگشت به گزارشات" if lang == "fa" else "🔙 Back to Reports", callback_data="adm:sales")
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(1, 1)

    await render_menu_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data == "adm:noop")
async def admin_noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data == "adm:orders:search")
async def orders_search_prompt(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    await state.set_state(OrderManagementStates.waiting_search)
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:orders:all:0")
    kb.adjust(1)

    render_menu_fn = resolve_op("render_menu", render_menu)
    await render_menu_fn(bot, user, user_repo, t(lang, "ord_search_prompt"), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("adm:orders:clear:"))
async def orders_clear_search(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    render_orders_fn = resolve_op("_render_orders_list", _render_orders_list)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    status = call.data.rsplit(":", 1)[1]
    await state.update_data(order_search_query=None)
    await render_orders_fn(bot, user, user_repo, session, status=status, page=0, query=None)
    await call.answer()


@router.callback_query(F.data.startswith("adm:orders:"))
async def orders_filtered_view(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    render_orders_fn = resolve_op("_render_orders_list", _render_orders_list)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)

    parts = call.data.split(":")
    status = parts[2] if len(parts) > 2 else "all"
    page = _safe_int(parts[3]) if len(parts) > 3 else 0
    if page is None:
        page = 0

    data = await state.get_data()
    query = data.get("order_search_query")
    await render_orders_fn(bot, user, user_repo, session, status=status, page=page, query=query)
    await call.answer()


@router.message(OrderManagementStates.waiting_search)
async def orders_search_submit(
    message: Message,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
):
    if not _is_admin(message.from_user.id):
        return
    del_msg_fn = resolve_op("delete_message_silently", delete_message_silently)
    render_orders_fn = resolve_op("_render_orders_list", _render_orders_list)

    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    query = (message.text or "").strip()
    await del_msg_fn(bot, message.chat.id, message.message_id)

    if not query:
        return

    await state.update_data(order_search_query=query)
    await state.set_state(None)
    await render_orders_fn(bot, user, user_repo, session, status="all", page=0, query=query)
