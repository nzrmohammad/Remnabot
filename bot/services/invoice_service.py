"""Digital Invoice & Official Receipt Service: DRY & SSOT for generating printable and shareable receipts."""
from __future__ import annotations

import logging
from typing import Any
from zoneinfo import ZoneInfo

import jdatetime
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Order, OrderStatus, User
from bot.services.formatting import ltr_frag

logger = logging.getLogger(__name__)


def generate_invoice_number(order_id: int, created_at_jalali: jdatetime.datetime) -> str:
    """Generate official Iranian digital invoice code e.g. INV-140308-00123."""
    return f"INV-{created_at_jalali.year % 100:02d}{created_at_jalali.month:02d}-{order_id:05d}"


async def get_order_invoice_data(
    session: AsyncSession,
    order_id: int,
    telegram_id: int,
    store_name: str = "سرویس ابری رمنا",
    support_contact: str = "",
    tz_name: str = "Asia/Tehran",
) -> dict[str, Any] | None:
    """Fetch order and compile complete official digital invoice data dictionary."""
    stmt = (
        select(Order, User)
        .join(User, Order.telegram_id == User.telegram_id)
        .where(Order.id == order_id, Order.telegram_id == telegram_id)
    )
    res = await session.execute(stmt)
    row = res.first()
    if not row:
        return None

    order: Order = row[0]
    user: User = row[1]

    # Jalali conversion
    tz = ZoneInfo(tz_name)
    o_dt = order.created_at
    if o_dt and o_dt.tzinfo:
        o_dt_local = o_dt.astimezone(tz)
    elif o_dt:
        o_dt_local = o_dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
    else:
        o_dt_local = None

    if o_dt_local:
        j_dt = jdatetime.datetime.fromgregorian(datetime=o_dt_local)
        date_jalali = f"{j_dt.year}/{j_dt.month:02d}/{j_dt.day:02d}"
        time_jalali = f"{j_dt.hour:02d}:{j_dt.minute:02d}:{j_dt.second:02d}"
        invoice_number = generate_invoice_number(order.id, j_dt)
    else:
        date_jalali = "—"
        time_jalali = "—"
        invoice_number = f"INV-0000-{order.id:05d}"

    buyer_name = user.full_name or (f"@{user.username}" if user.username else f"کاربر {user.telegram_id}")
    phone = user.phone_number or "—"

    traffic_desc = f"{order.traffic_gb} گیگابایت" if order.traffic_gb > 0 else "نامحدود"
    duration_desc = f"{order.duration_days} روز" if order.duration_days > 0 else "بدون محدودیت زمانی"

    is_paid = (order.status == OrderStatus.PAID.value) or (str(order.status).lower() == "paid")
    status_label = "پرداخت شده و فعال" if is_paid else "ناموفق / لغو شده"

    amount_toman = int(order.amount or 0)
    amount_rial = amount_toman * 10

    # Tracking reference code
    tracking_code = f"TRX-{(order.id * 7919) % 100000000:08d}"

    return {
        "order_id": order.id,
        "invoice_number": invoice_number,
        "date_jalali": date_jalali,
        "time_jalali": time_jalali,
        "created_at_iso": o_dt.isoformat() if o_dt else "",
        "seller": {
            "name": store_name,
            "type": "خدمات رایانش و شبکه ابری",
            "support": support_contact or "پشتیبانی ربات تلگرام",
            "verified": True,
        },
        "buyer": {
            "name": buyer_name,
            "telegram_id": user.telegram_id,
            "username": f"@{user.username}" if user.username else "",
            "phone": phone,
        },
        "item": {
            "service_id": order.service_id,
            "title": order.service_name,
            "traffic_gb": order.traffic_gb,
            "traffic_text": traffic_desc,
            "duration_days": order.duration_days,
            "duration_text": duration_desc,
            "is_renewal": order.is_renewal,
        },
        "payment": {
            "amount_toman": amount_toman,
            "amount_toman_formatted": f"{amount_toman:,} تومان",
            "amount_rial_formatted": f"{amount_rial:,} ریال",
            "method": "کیف پول الکترونیک (اعتبار داخلی)",
            "status": status_label,
            "is_paid": is_paid,
            "tracking_code": tracking_code,
        },
    }


async def send_invoice_to_telegram(bot: Bot, telegram_id: int, invoice: dict[str, Any], web_app_url: str = "") -> bool:
    """Send a beautifully formatted digital invoice directly to the user's Telegram chat."""
    inv_num = invoice["invoice_number"]
    date_str = f"{invoice['date_jalali']} ساعت {invoice['time_jalali']}"
    buyer = invoice["buyer"]
    item = invoice["item"]
    pay = invoice["payment"]
    tracking = pay["tracking_code"]

    msg = (
        f"🧾 <b>صورت‌حساب و فاکتور رسمی خدمات دیجیتال</b>\n\n"
        f"📋 <b>شماره فاکتور:</b> <code>{inv_num}</code>\n"
        f"📅 <b>تاریخ و زمان:</b> {date_str}\n"
        f"👤 <b>خریدار:</b> {buyer['name']} (شناسه: <code>{buyer['telegram_id']}</code>)\n\n"
        f"📦 <b>شرح خدمات:</b>\n"
        f"• سرویس: <b>{item['title']}</b>\n"
        f"• مشخصات: {item['traffic_text']} | {item['duration_text']}\n"
        f"• نوع تراکنش: {'تمدید اشتراک' if item['is_renewal'] else 'خرید اشتراک جدید'}\n\n"
        f"💳 <b>اطلاعات پرداخت:</b>\n"
        f"• مبلغ پرداختی: <b>{pay['amount_toman_formatted']}</b>\n"
        f"• معادل ریالی: {pay['amount_rial_formatted']}\n"
        f"• وضعیت: <b>{pay['status']} ✅</b>\n"
        f"• شناسه رهگیری: <code>{tracking}</code>\n\n"
        f"✨ <i>این فاکتور دیجیتال سند رسمی خرید شما در سامانه می‌باشد.</i>"
    )

    markup = None
    if web_app_url:
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📄 مشاهده نسخه وب و چاپ", url=web_app_url)
        ]])

    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=msg,
            reply_markup=markup,
            parse_mode="HTML",
        )
        return True
    except Exception as exc:
        logger.warning("Failed sending invoice to Telegram %s: %s", telegram_id, exc)
        return False
