"""Digital Invoice & Official Receipt Service: DRY & SSOT for generating printable and shareable receipts."""
from __future__ import annotations

import logging
from typing import Any
from zoneinfo import ZoneInfo

import jdatetime
from aiogram import Bot
from aiogram.types import BufferedInputFile, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Order, OrderStatus, User

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
    store_logo_url: str = "",
    tz_name: str = "Asia/Tehran",
    invoice_type: str | None = None,
) -> dict[str, Any] | None:
    """Fetch order or wallet topup and compile complete official digital invoice data dictionary."""
    is_topup_requested = invoice_type == "topup"
    is_order_requested = invoice_type == "order"

    row = None
    if not is_topup_requested:
        stmt = (
            select(Order, User)
            .outerjoin(User, Order.telegram_id == User.telegram_id)
            .where(Order.id == order_id, Order.telegram_id == telegram_id)
        )
        res = await session.execute(stmt)
        row = res.first()

    if not row and not is_order_requested:
        from bot.db.models import Topup
        t_stmt = (
            select(Topup, User)
            .outerjoin(User, Topup.telegram_id == User.telegram_id)
            .where(Topup.id == order_id, Topup.telegram_id == telegram_id)
        )
        t_res = await session.execute(t_stmt)
        t_row = t_res.first()
        if not t_row:
            return None
        topup: Topup = t_row[0]
        user: User | None = t_row[1]

        tz = ZoneInfo(tz_name)
        t_dt = topup.created_at
        if t_dt and t_dt.tzinfo:
            t_dt_local = t_dt.astimezone(tz)
        elif t_dt:
            t_dt_local = t_dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        else:
            t_dt_local = None

        if t_dt_local:
            j_dt = jdatetime.datetime.fromgregorian(datetime=t_dt_local)
            date_jalali = f"{j_dt.year}/{j_dt.month:02d}/{j_dt.day:02d}"
            time_jalali = f"{j_dt.hour:02d}:{j_dt.minute:02d}:{j_dt.second:02d}"
            invoice_number = f"TOP-{j_dt.year % 100:02d}{j_dt.month:02d}-{topup.id:05d}"
        else:
            date_jalali = "—"
            time_jalali = "—"
            invoice_number = f"TOP-0000-{topup.id:05d}"

        buyer_name = (
            user.full_name or (f"@{user.username}" if user.username else f"کاربر {topup.telegram_id}")
        ) if user else f"کاربر {topup.telegram_id}"
        phone = (user.phone_number or "—") if user else "—"

        raw_st = (topup.status or "pending").lower()
        is_paid = raw_st == "approved"
        if is_paid:
            status_label = "تایید و شارژ شده"
        elif raw_st == "rejected":
            status_label = "رد شده"
        else:
            status_label = "در انتظار بررسی"

        amount_toman = int(topup.amount or 0)
        amount_rial = amount_toman * 10
        tracking_code = f"TRX-TOP-{(topup.id * 7919) % 100000000:08d}"

        return {
            "order_id": topup.id,
            "invoice_number": invoice_number,
            "date_jalali": date_jalali,
            "time_jalali": time_jalali,
            "created_at_iso": t_dt.isoformat() if t_dt else "",
            "seller": {
                "name": store_name,
                "logo_url": store_logo_url,
                "type": "خدمات رایانش و شبکه ابری",
                "support": support_contact or "پشتیبانی ربات تلگرام",
                "verified": True,
            },
            "buyer": {
                "name": buyer_name,
                "telegram_id": topup.telegram_id,
                "username": (f"@{user.username}" if user.username else "") if user else "",
                "phone": phone,
            },
            "item": {
                "service_id": 0,
                "title": "افزایش اعتبار کیف پول (کارت به کارت)",
                "traffic_gb": 0,
                "traffic_text": "شارژ ریالی موجودی",
                "duration_days": 0,
                "duration_text": "بدون محدودیت زمانی",
                "is_renewal": False,
            },
            "payment": {
                "amount_toman": amount_toman,
                "amount_toman_formatted": f"{amount_toman:,} تومان",
                "amount_rial_formatted": f"{amount_rial:,} ریال",
                "method": "کارت‌به‌کارت بانکی",
                "status": status_label,
                "is_paid": is_paid,
                "tracking_code": tracking_code,
                "deducted_amount": amount_toman if is_paid else 0,
                "deducted_formatted": f"{amount_toman:,} تومان" if is_paid else "0 تومان",
                "deduction_note": "افزایش یافته به موجودی کیف پول" if is_paid else "هیچ مبلغی شارژ نشده است",
            },
        }

    if not row:
        return None

    order: Order = row[0]
    user: User | None = row[1]

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

    buyer_name = (
        user.full_name or (f"@{user.username}" if user.username else f"کاربر {order.telegram_id}")
    ) if user else f"کاربر {order.telegram_id}"
    phone = (user.phone_number or "—") if user else "—"

    traffic_gb = int(order.traffic_gb or 0)
    duration_days = int(order.duration_days or 0)
    traffic_desc = f"{traffic_gb} گیگابایت" if traffic_gb > 0 else "نامحدود"
    duration_desc = f"{duration_days} روز" if duration_days > 0 else "بدون محدودیت زمانی"

    raw_status = (
        order.status.value if hasattr(order.status, "value") else str(order.status or "")
    ).lower()
    is_paid = raw_status in (OrderStatus.PAID.value, "paid")
    if is_paid:
        status_label = "پرداخت شده"
    elif raw_status in (OrderStatus.REFUNDED.value, "refunded"):
        status_label = "مسترد شده (مرجوع)"
    elif raw_status in (OrderStatus.PENDING.value, "pending"):
        status_label = "در انتظار پرداخت"
    else:
        status_label = "ناموفق / لغو شده"

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
            "logo_url": store_logo_url,
            "type": "خدمات رایانش و شبکه ابری",
            "support": support_contact or "پشتیبانی ربات تلگرام",
            "verified": True,
        },
        "buyer": {
            "name": buyer_name,
            "telegram_id": order.telegram_id,
            "username": (f"@{user.username}" if user.username else "") if user else "",
            "phone": phone,
        },
        "item": {
            "service_id": order.service_id,
            "title": order.service_name or "بسته اشتراک",
            "traffic_gb": traffic_gb,
            "traffic_text": traffic_desc,
            "duration_days": duration_days,
            "duration_text": duration_desc,
            "is_renewal": bool(order.is_renewal),
        },
        "payment": {
            "amount_toman": amount_toman,
            "amount_toman_formatted": f"{amount_toman:,} تومان",
            "amount_rial_formatted": f"{amount_rial:,} ریال",
            "method": "کیف پول الکترونیک (اعتبار داخلی)",
            "status": status_label,
            "is_paid": is_paid,
            "tracking_code": tracking_code,
            "deducted_amount": amount_toman if is_paid else 0,
            "deducted_formatted": f"{amount_toman:,} تومان" if is_paid else "0 تومان",
            "deduction_note": "کسر شده از موجودی کیف پول" if is_paid else ("مسترد شده به کیف پول" if raw_status in (OrderStatus.REFUNDED.value, "refunded") else "هیچ هزینه‌ای کسر نشده است"),
        },
    }


async def send_invoice_to_telegram(
    bot: Bot,
    telegram_id: int,
    invoice: dict[str, Any],
    web_app_url: str = "",
    image_bytes: bytes | None = None,
) -> bool:
    """Send a beautifully formatted digital invoice (or rendered PNG image) directly to Telegram chat."""
    import html
    inv_num = html.escape(str(invoice.get("invoice_number", "")))
    date_str = html.escape(f"{invoice.get('date_jalali', '')} ساعت {invoice.get('time_jalali', '')}")
    buyer = invoice.get("buyer") or {}
    item = invoice.get("item") or {}
    pay = invoice.get("payment") or {}
    tracking = html.escape(str(pay.get("tracking_code", "")))
    buyer_name = html.escape(str(buyer.get("name", "")))
    buyer_id = html.escape(str(buyer.get("telegram_id", "")))
    item_title = html.escape(str(item.get("title", "")))
    traffic_text = html.escape(str(item.get("traffic_text", "")))
    duration_text = html.escape(str(item.get("duration_text", "")))
    toman_fmt = html.escape(str(pay.get("amount_toman_formatted", "")))
    rial_fmt = html.escape(str(pay.get("amount_rial_formatted", "")))
    status_str = html.escape(str(pay.get("status", "")))
    is_renewal = bool(item.get("is_renewal"))

    msg = (
        f"🧾 <b>صورت‌حساب و فاکتور رسمی خدمات دیجیتال</b>\n\n"
        f"📋 <b>شماره فاکتور:</b> <code>{inv_num}</code>\n"
        f"📅 <b>تاریخ و زمان:</b> {date_str}\n"
        f"👤 <b>خریدار:</b> {buyer_name} (شناسه: <code>{buyer_id}</code>)\n\n"
        f"📦 <b>شرح خدمات:</b>\n"
        f"• سرویس: <b>{item_title}</b>\n"
        f"• مشخصات: {traffic_text} | {duration_text}\n"
        f"• نوع تراکنش: {'تمدید اشتراک' if is_renewal else 'خرید اشتراک جدید'}\n\n"
        f"💳 <b>اطلاعات پرداخت:</b>\n"
        f"• مبلغ پرداختی: <b>{toman_fmt}</b>\n"
        f"• معادل ریالی: {rial_fmt}\n"
        f"• وضعیت: <b>{status_str} {'✅' if pay.get('is_paid') else '❌'}</b>\n"
        f"• شناسه رهگیری: <code>{tracking}</code>\n\n"
        f"✨ این فاکتور دیجیتال سند رسمی خرید شما در سامانه می‌باشد."
    )

    markup = None
    if web_app_url:
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📄 مشاهده نسخه وب و چاپ", url=web_app_url)
        ]])

    logo_url = invoice.get("seller", {}).get("logo_url") or ""
    try:
        from pathlib import Path
        photo_sent = False
        if image_bytes:
            try:
                safe_num = "".join(ch for ch in str(invoice.get("invoice_number", "receipt")) if ch.isalnum() or ch in ("-", "_")) or "receipt"
                await bot.send_photo(
                    chat_id=telegram_id,
                    photo=BufferedInputFile(image_bytes, filename=f"Invoice-{safe_num}.png"),
                    caption=msg[:1024],
                    reply_markup=markup,
                    parse_mode="HTML",
                )
                photo_sent = True
            except Exception as img_err:
                logger.debug("Failed sending generated invoice image: %s", img_err)
        if not photo_sent and logo_url:
            if logo_url.startswith("http://") or logo_url.startswith("https://"):
                try:
                    await bot.send_photo(
                        chat_id=telegram_id,
                        photo=logo_url,
                        caption=msg,
                        reply_markup=markup,
                        parse_mode="HTML",
                    )
                    photo_sent = True
                except Exception as p_err:
                    logger.debug("Failed sending remote logo photo: %s", p_err)
            else:
                clean_path = logo_url.split("?")[0].lstrip("/")
                base_dir = (Path(__file__).resolve().parent.parent / "web" / "static").resolve()
                candidate_paths = [
                    (base_dir / clean_path).resolve(),
                    (base_dir / clean_path.removeprefix("static/")).resolve(),
                ]
                disk_path = None
                for cand in candidate_paths:
                    if cand.is_relative_to(base_dir) and cand.is_file():
                        disk_path = cand
                        break

                if disk_path:
                    try:
                        await bot.send_photo(
                            chat_id=telegram_id,
                            photo=FSInputFile(str(disk_path)),
                            caption=msg,
                            reply_markup=markup,
                            parse_mode="HTML",
                        )
                        photo_sent = True
                    except Exception as p_err:
                        logger.debug("Failed sending local logo photo: %s", p_err)

        if not photo_sent:
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
