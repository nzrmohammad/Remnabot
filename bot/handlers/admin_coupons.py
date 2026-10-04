"""Admin Coupon Management (list, view, create, toggle, delete)."""
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt, is_admin, parse_int
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.coupon_repo import CouponRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.formatting import format_datetime
from bot.services.menu import delete_message_silently, render_menu
from bot.states.admin import CouponManagementStates

logger = logging.getLogger(__name__)
router = Router(name="admin_coupons")

_is_admin = is_admin
_parse_int = parse_int


@router.callback_query(F.data == "adm:coupons")
async def admin_coupons_list(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    coupon_repo = CouponRepository(session)
    coupons = await coupon_repo.list_all()

    lines = [
        f"{t(lang, 'coupons_admin_title')}\n{SEPARATOR}",
    ]
    if not coupons:
        lines.append("هیچ کد تخفیفی ثبت نشده است." if lang == "fa" else "No discount coupons created yet.")
    else:
        for c in coupons:
            status_icon = "🟢" if c.is_active else "🔴"
            disc_str = f"{c.discount_percent}%" if c.discount_percent else f"{fmt(c.discount_amount)} {t(lang, 'svc_currency')}"
            uses_str = f"{c.used_count}/{c.max_uses}" if c.max_uses else f"{c.used_count}/∞"
            lines.append(f"{status_icon} <code>{c.code}</code> — {disc_str} ({uses_str})")

    kb = InlineKeyboardBuilder()
    for c in coupons:
        status_icon = "🟢" if c.is_active else "🔴"
        disc_str = f"{c.discount_percent}%" if c.discount_percent else f"{fmt(c.discount_amount)}"
        kb.button(text=f"{status_icon} {c.code} ({disc_str})", callback_data=f"adm:cpn:view:{c.id}")
    kb.adjust(2)

    bottom_kb = InlineKeyboardBuilder()
    bottom_kb.button(text=t(lang, "btn_create_coupon"), callback_data="adm:cpn:add")
    bottom_kb.button(text=t(lang, "btn_back"), callback_data="adm:services")
    bottom_kb.adjust(1)
    kb.attach(bottom_kb)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("adm:cpn:view:"))
async def admin_coupon_detail(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, coupon_id: int | None = None,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    if coupon_id is None:
        try:
            coupon_id = int(call.data.rsplit(":", 1)[1])
        except (ValueError, TypeError):
            await call.answer(t("fa", "acc_error"), show_alert=True)
            return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    coupon_repo = CouponRepository(session)
    c = await coupon_repo.get_by_id(coupon_id)
    if c is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    disc_str = f"{c.discount_percent}%" if c.discount_percent else f"{fmt(c.discount_amount)} {t(lang, 'svc_currency')}"
    uses_str = f"{c.used_count} از {c.max_uses}" if c.max_uses else f"{c.used_count} (نامحدود)"
    status_str = "🟢 فعال" if c.is_active else "🔴 غیرفعال"

    lines = [
        f"🏷 <b>جزئیات کد تخفیف: <code>{c.code}</code></b>\n{SEPARATOR}",
        f"💰 میزان تخفیف: <b>{disc_str}</b>",
        f"👥 دفعات استفاده: <b>{uses_str}</b>",
        f"🔘 وضعیت: <b>{status_str}</b>",
    ]
    if c.expires_at:
        lines.append(f"📅 تاریخ انقضا: <code>{format_datetime(c.expires_at, lang)}</code>")

    kb = InlineKeyboardBuilder()
    toggle_text = "🔴 غیرفعال‌سازی" if c.is_active else "🟢 فعال‌سازی"
    kb.button(text=toggle_text, callback_data=f"adm:cpn:toggle:{c.id}")
    kb.button(text="🗑 حذف کد تخفیف", callback_data=f"adm:cpn:del:{c.id}")
    kb.button(text=t(lang, "btn_back"), callback_data="adm:coupons")
    kb.adjust(2, 1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("adm:cpn:toggle:"))
async def admin_coupon_toggle(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    coupon_id = int(call.data.rsplit(":", 1)[1])
    coupon_repo = CouponRepository(session)
    await coupon_repo.toggle_active(coupon_id)
    await admin_coupon_detail(call, bot, user_repo, session, coupon_id=coupon_id)


@router.callback_query(F.data.startswith("adm:cpn:del:"))
async def admin_coupon_delete(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    coupon_id = int(call.data.rsplit(":", 1)[1])
    coupon_repo = CouponRepository(session)
    await coupon_repo.delete(coupon_id)
    await call.answer("کد تخفیف حذف شد." if call.from_user.language_code == "fa" else "Coupon deleted.")
    await admin_coupons_list(call, bot, user_repo, session, state)


@router.callback_query(F.data == "adm:cpn:add")
async def admin_coupon_add_start(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    await state.set_state(CouponManagementStates.waiting_code)
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:coupons")
    kb.adjust(1)

    text = "🏷 <b>عنوان کد تخفیف را وارد کنید:</b>\n(مثال: NOROOZ, DISCOUNT20, ...)" if lang == "fa" else "🏷 <b>Enter Coupon Code:</b>\n<i>(e.g., SUMMER20)</i>"
    await render_menu(bot, user, user_repo, text, kb.as_markup())
    await call.answer()


@router.message(CouponManagementStates.waiting_code, F.text)
async def admin_coupon_add_code(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language or "fa"
    await delete_message_silently(bot, message.chat.id, message.message_id)

    code = message.text.strip().upper()
    if len(code) < 3 or len(code) > 32:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="adm:coupons")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, "❌ کد نامعتبر است (بین ۳ تا ۳۲ کاراکتر):", kb.as_markup())
        return

    await state.update_data(coupon_code=code)
    await state.set_state(CouponManagementStates.waiting_discount)

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:coupons")
    kb.adjust(1)

    text = (
        "💰 <b>میزان تخفیف را وارد کنید:</b>\n\n"
        "• برای درصد تخفیف، علامت % بگذارید (مثال: <code>20%</code>)\n"
        "• برای مبلغ ثابت، مبلغ را به تومان وارد کنید (مثال: <code>50000</code>)"
        if lang == "fa"
        else "💰 <b>Enter discount value:</b>\n\n• For percentage, use % (e.g. <code>20%</code>)\n• For fixed amount, enter Toman (e.g. <code>50000</code>)"
    )
    await render_menu(bot, user, user_repo, text, kb.as_markup())


@router.message(CouponManagementStates.waiting_discount, F.text)
async def admin_coupon_add_discount(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language or "fa"
    await delete_message_silently(bot, message.chat.id, message.message_id)

    raw = message.text.strip().replace("٪", "%")
    is_percent = "%" in raw
    clean_val = raw.replace("%", "").strip()
    val = _parse_int(clean_val)
    if val is None or val <= 0 or (is_percent and val > 100):
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="adm:coupons")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, "❌ مقدار نامعتبر است. لطفاً عدد معتبر وارد کنید:", kb.as_markup())
        return

    if is_percent:
        await state.update_data(discount_percent=val, discount_amount=0)
    else:
        await state.update_data(discount_percent=0, discount_amount=val)

    await state.set_state(CouponManagementStates.waiting_max_uses)
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:coupons")
    kb.adjust(1)

    text = (
        "👥 <b>حداکثر دفعات مجاز استفاده را وارد کنید:</b>\n"
        "(برای استفاده نامحدود عدد 0 یا /skip ارسال کنید)"
        if lang == "fa"
        else "👥 <b>Enter maximum total uses:</b>\n<i>(Enter 0 or /skip for unlimited)</i>"
    )
    await render_menu(bot, user, user_repo, text, kb.as_markup())


@router.message(CouponManagementStates.waiting_max_uses, F.text)
async def admin_coupon_add_max_uses(
    message: Message, bot: Bot, user_repo: UserRepository, session: AsyncSession, state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language or "fa"
    await delete_message_silently(bot, message.chat.id, message.message_id)

    raw = message.text.strip()
    max_uses = None
    if raw not in ("/skip", "-", "—", "0"):
        val = _parse_int(raw)
        if val is not None and val > 0:
            max_uses = val

    data = await state.get_data()
    code = data.get("coupon_code")
    discount_percent = data.get("discount_percent") or None
    discount_amount = data.get("discount_amount") or 0

    coupon_repo = CouponRepository(session)
    await coupon_repo.create(
        code=code,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
        max_uses=max_uses,
    )
    await AdminLogRepository(session).log(
        message.from_user.id, "setting", detail=f"create_coupon={code}"
    )
    await state.clear()

    coupons = await coupon_repo.list_all()
    lines = [
        t(lang, "coupon_created", code=code),
        SEPARATOR,
        f"{t(lang, 'coupons_admin_title')}\n{SEPARATOR}",
    ]
    for c in coupons:
        status_icon = "🟢" if c.is_active else "🔴"
        disc_str = f"{c.discount_percent}%" if c.discount_percent else f"{fmt(c.discount_amount)} {t(lang, 'svc_currency')}"
        uses_str = f"{c.used_count}/{c.max_uses}" if c.max_uses else f"{c.used_count}/∞"
        lines.append(f"{status_icon} <code>{c.code}</code> — {disc_str} ({uses_str})")

    kb = InlineKeyboardBuilder()
    for c in coupons:
        status_icon = "🟢" if c.is_active else "🔴"
        disc_str = f"{c.discount_percent}%" if c.discount_percent else f"{fmt(c.discount_amount)}"
        kb.button(text=f"{status_icon} {c.code} ({disc_str})", callback_data=f"adm:cpn:view:{c.id}")
    kb.button(text=t(lang, "btn_create_coupon"), callback_data="adm:cpn:add")
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
