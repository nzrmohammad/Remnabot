"""Lucky Wheel Bot Handler: Daily spins, slot animations, streaks and prize delivery."""
from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR
from bot.config import get_settings
from bot.db.repositories.user_repo import UserRepository
from bot.services.formatting import ltr_frag
from bot.services.menu import render_menu
from bot.services.remnawave import RemnawaveClient
from bot.services.wheel_service import (
    execute_lucky_wheel_spin,
    get_wheel_status,
)
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)
router = Router(name="wheel")


@router.callback_query(F.data == "menu:wheel")
async def wheel_hub(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    cache: FastCache | None = None,
):
    """View Lucky Wheel hub, streaks, tickets and ready state."""
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    tz = get_settings().TIMEZONE

    status = await get_wheel_status(session, cache, call.from_user.id, tz_name=tz)

    streak = status["streak"]
    streak_bonus = " (ضریب شانس 1.5x 🔥)" if streak >= 3 else (" (ضریب شانس 1.2x ⚡️)" if streak == 2 else "")
    tickets = status["spin_tickets"]
    won_gb = status["total_won_traffic"]

    if status["can_spin"] and not status["is_cooldown"]:
        ready_text = "✅ <b>آماده چرخش رایگان!</b>" if lang == "fa" else "✅ <b>Ready to spin!</b>"
    elif status["is_cooldown"]:
        h = status["hours_left"]
        m = status["mins_left"]
        ready_text = (
            f"⏳ <b>{h} ساعت و {m} دقیقه تا شارژ مجدد</b>"
            if lang == "fa"
            else f"⏳ <b>{h}h {m}m until next free spin</b>"
        )
    else:
        ready_text = "آماده چرخش" if lang == "fa" else "Ready"

    lines = [
        "🎡 <b>گردونه شانس و جوایز روزانه</b>" if lang == "fa" else "🎡 <b>Daily Lucky Wheel</b>",
        SEPARATOR,
        f"🔥 زنجیره روزانه : <b>{streak} روز پیاپی</b>{streak_bonus}" if lang == "fa" else f"🔥 Daily Streak : <b>{streak} days</b>{streak_bonus}",
        f"🎟 تیکت‌های شانس : <b>{tickets} عدد</b>" if lang == "fa" else f"🎟 Spin Tickets : <b>{tickets}</b>",
        f"🎁 کل حجم برنده شده : <b>{won_gb:.1f} گیگابایت</b>" if lang == "fa" else f"🎁 Total Won : <b>{ltr_frag(f'{won_gb:.1f} GB')}</b>",
        f"⏰ وضعیت شانس : {ready_text}" if lang == "fa" else f"⏰ Status : {ready_text}",
        SEPARATOR,
        "💡 با ورود و چرخاندن روزانه گردونه، زنجیره شانس شما افزایش یافته و احتمال برد جوایز بزرگ بیشتر می‌شود!"
        if lang == "fa"
        else "💡 Spin daily to build streaks and unlock higher jackpot probabilities!",
    ]

    kb = InlineKeyboardBuilder()

    # Free spin button (if not in cooldown)
    if not status["is_cooldown"]:
        spin_btn_text = "🎰 چرخاندن رایگان گردونه" if lang == "fa" else "🎰 Free Spin"
        kb.button(text=spin_btn_text, callback_data="wheel:spin")

    # Ticket spin button (if user has tickets)
    if tickets > 0:
        ticket_btn_text = (
            f"🎟 چرخش با تیکت شانس ({tickets} عدد)"
            if lang == "fa"
            else f"🎟 Spin with Ticket ({tickets})"
        )
        kb.button(text=ticket_btn_text, callback_data="wheel:spin_ticket")

    prizes_btn_text = "📋 فهرست جوایز و شانس‌ها" if lang == "fa" else "📋 Prize List"
    coupons_btn_text = "🎟 کدهای تخفیف من" if lang == "fa" else "🎟 My Coupons"
    kb.button(text=prizes_btn_text, callback_data="wheel:prizes")
    kb.button(text=coupons_btn_text, callback_data="wheel:my_coupons")

    back_btn_text = "🏠 منوی اصلی" if lang == "fa" else "🏠 Main Menu"
    kb.button(text=back_btn_text, callback_data="nav:main_menu")

    kb.adjust(1)
    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.in_({"wheel:spin", "wheel:spin_ticket"}))
async def wheel_spin_action(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    remnawave: RemnawaveClient,
    cache: FastCache | None = None,
):
    """Execute spin with native Telegram slot machine animation."""
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    tz = get_settings().TIMEZONE
    use_ticket = (call.data == "wheel:spin_ticket")

    # Check lock to prevent simultaneous clicks
    spin_lock_key = f"lock:user:{call.from_user.id}:spin"
    if cache and hasattr(cache, "set_nx"):
        lock_ok = await cache.set_nx(spin_lock_key, "1", ttl_seconds=5)
        if not lock_ok:
            await call.answer("درخواست قبلی در حال پردازش است...", show_alert=True)
            return

    try:
        # Pre-validate before showing animation
        res = await execute_lucky_wheel_spin(
            session=session,
            remnawave=remnawave,
            cache=cache,
            bot=bot,
            telegram_id=call.from_user.id,
            use_ticket=use_ticket,
            tz_name=tz,
        )

        if not res.get("ok"):
            err_code = res.get("code")
            if err_code == "channel_required" and res.get("channel_url"):
                kb = InlineKeyboardBuilder()
                kb.button(text="📢 عضویت در کانال", url=res["channel_url"])
                kb.button(text="🎡 بازگشت به گردونه", callback_data="menu:wheel")
                kb.adjust(1)
                await render_menu(
                    bot,
                    user,
                    user_repo,
                    "⚠️ <b>عضویت در کانال الزامی است:</b>\n\nبرای چرخاندن گردونه ابتدا در کانال ما عضو شوید.",
                    kb.as_markup(),
                )
                await call.answer()
                return

            await call.answer(res.get("error", "خطا در چرخش گردونه"), show_alert=True)
            return

        await call.answer("🎰 گردونه به حرکت درآمد!")

        # Telegram native slot animation
        try:
            await bot.send_dice(chat_id=call.message.chat.id, emoji="🎰")
        except Exception:
            pass

        await asyncio.sleep(2.5)

        prize = res["prize"]
        streak = res["streak"]
        applied = res["applied"]
        tickets_left = res["spin_tickets"]

        ptype = prize.get("type")
        pname = prize.get("name", "")

        lines = [
            "🎡 <b>نتیجه چرخش گردونه شانس</b>",
            SEPARATOR,
        ]

        if ptype == "blank":
            lines.append("❌ <b>این بار شانس با شما یار نبود!</b>")
            lines.append("فردا دوباره برگردید تا زنجیره شانس شما حفظ شود.")
        elif ptype == "again":
            lines.append("🔄 <b>شما برنده شانس مجدد شدید!</b>")
            lines.append("می‌توانید همین الان یک بار دیگر گردونه را بچرخانید!")
        elif ptype == "coupon":
            lines.append("🎉 <b>تبریک! شما برنده کد تخفیف ویژه شدید:</b>")
            lines.append(f"🎟 <b>کد:</b> <code>{escape(prize.get('code', ''))}</code>")
            lines.append("⏳ <b>مهلت استفاده:</b> 7 روز (قابل استفاده در بخش خرید سرویس)")
        elif ptype == "traffic":
            lines.append(f"🎉 <b>تبریک! برنده {pname} شدید!</b>")
            if applied:
                lines.append("✅ این حجم به صورت خودکار به اشتراک فعال شما افزوده شد.")
            else:
                lines.append("ℹ️ جایزه در سیستم ثبت گردید.")
        else:
            lines.append(f"🎁 <b>تبریک! برنده {pname} شدید!</b>")

        lines.append(SEPARATOR)
        lines.append(f"🔥 زنجیره روزانه شما: <b>{streak} روز</b>")
        if tickets_left > 0:
            lines.append(f"🎟 تیکت‌های شانس باقیمانده: <b>{tickets_left} عدد</b>")

        kb = InlineKeyboardBuilder()
        if ptype == "again" or tickets_left > 0:
            kb.button(
                text="🎰 چرخش مجدد",
                callback_data="wheel:spin" if ptype == "again" else "wheel:spin_ticket",
            )
        kb.button(text="🎡 صفحه گردونه شانس", callback_data="menu:wheel")
        kb.button(text="🏠 منوی اصلی", callback_data="nav:main_menu")
        kb.adjust(1)

        await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())

    finally:
        if cache and hasattr(cache, "delete"):
            await cache.delete(spin_lock_key)


@router.callback_query(F.data == "wheel:prizes")
async def wheel_prizes_list(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
):
    """Display the full prize catalogue and streak multiplier explanations."""
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)

    lines = [
        "📋 <b>فهرست جوایز گردونه شانس</b>",
        SEPARATOR,
        "👑 <b>2 گیگابایت اینترنت هدیه</b> — سوپر شانس طلایی",
        "🎁 <b>1 گیگابایت اینترنت هدیه</b> — ترافیک مستقیم به سرویس",
        "⚡️ <b>500 مگابایت اینترنت هدیه</b> — شارژ آنی سرویس",
        "🎟 <b>10٪ کد تخفیف ویژه</b> — مهلت استفاده 7 روزه",
        "🔄 <b>شانس مجدد</b> — چرخش دوباره بدون کسر شانس",
        "❌ <b>پوچ</b> — شانس بعدی فردا",
        SEPARATOR,
        "🔥 <b>سیستم تقویت زنجیره (Streak Multiplier):</b>",
        "• روز اول: شانس استاندارد (1.0x)",
        "• روز دوم: افزایش شانس (1.2x)",
        "• 3 روز یا بیشتر: حداکثر شانس برد (1.5x)",
    ]

    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 بازگشت به گردونه", callback_data="menu:wheel")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data == "wheel:my_coupons")
async def wheel_my_coupons(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    cache: FastCache | None = None,
):
    """Display coupons won by user from lucky wheel."""
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)

    status = await get_wheel_status(session, cache, call.from_user.id)
    coupons = status.get("user_coupons") or []

    lines = [
        "🎟 <b>کدهای تخفیف فعال شما از گردونه</b>",
        SEPARATOR,
    ]

    if not coupons:
        lines.append("شما در حال حاضر کد تخفیف فعالی از گردونه ندارید.")
        lines.append("با چرخاندن روزانه گردونه شانس می‌توانید کدهای 10٪ برنده شوید!")
    else:
        for c in coupons[:5]:
            code = escape(str(c.get("code", "")))
            pct = c.get("discount_percent", 10)
            lines.append(f"• کد: <code>{code}</code> — <b>{pct}٪ تخفیف</b>")

    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 بازگشت به گردونه", callback_data="menu:wheel")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()
