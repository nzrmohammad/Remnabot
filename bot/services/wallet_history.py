"""Unified wallet transaction history & top-up method classification (SSOT for Bot and Mini App)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import jdatetime
from sqlalchemy import select

from bot.db.models import AdminLog, CardAutoInvoice, CryptoInvoice, Order, Topup

logger = logging.getLogger(__name__)

_TOPUP_METHOD_MAP: tuple[tuple[str, tuple[str, str]], ...] = (
    ("stars:", ("⭐️ تلگرام استارز", "⭐️ Telegram Stars")),
    ("ton:", ("💎 تون (TON)", "💎 TON")),
    ("trx:", ("🔴 ترون (TRX)", "🔴 TRX")),
    ("pol:", ("🟣 پلیگان (POL)", "🟣 POL")),
    ("voucher:", ("🎟 کارت شارژ", "🎟 Voucher")),
    ("admin:", ("👤 شارژ دستی", "👤 Admin Top-up")),
    ("c2c:", ("⚡️ کارت‌به‌کارت آنی", "⚡️ Instant Card Transfer")),
    ("auto_c2c:", ("⚡️ کارت‌به‌کارت آنی", "⚡️ Instant Card Transfer")),
)

_AMOUNT_EN_RE = re.compile(r"amount=(\d+)")
_AMOUNT_FA_RE = re.compile(r"([\d,]+)\s*تومان")


def classify_topup_method(receipt_hash: str | None, lang: str = "fa") -> tuple[str, str]:
    """Return (method_key, localized_label) for a Topup receipt_hash."""
    raw = str(receipt_hash or "")
    idx = 0 if lang == "fa" else 1
    for prefix, labels in _TOPUP_METHOD_MAP:
        if raw.startswith(prefix):
            return prefix.rstrip(":"), labels[idx]
    return "card", ("💳 کارت به کارت" if lang == "fa" else "💳 Card Transfer")


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_jalali_dt(dt: Any, tz_name: str) -> str:
    """Format a datetime object into YYYY/MM/DD - HH:MM Jalali string in target timezone."""
    if not dt:
        return ""
    local_dt = dt.astimezone(ZoneInfo(tz_name)) if getattr(dt, "tzinfo", None) else dt
    j_dt = jdatetime.datetime.fromgregorian(datetime=local_dt)
    return f"{j_dt.year}/{j_dt.month:02d}/{j_dt.day:02d} - {j_dt.hour:02d}:{j_dt.minute:02d}"


async def fetch_user_transactions(
    session: Any,
    telegram_id: int,
    tz_name: str = "Asia/Tehran",
    *,
    include_failed_orders: bool = True,
    limit: int = 50,
    lang: str = "fa",
) -> list[dict[str, Any]]:
    """Fetch unified wallet movements (Orders, Topups, CardAuto, Crypto, AdminAdjust) newest first."""
    history_items: list[dict[str, Any]] = []
    try:
        orders_res = await session.execute(
            select(Order).where(Order.telegram_id == telegram_id).order_by(Order.id.desc()).limit(limit)
        )
        for o in orders_res.scalars().all():
            raw_st = (o.status.value if hasattr(o.status, "value") else str(o.status or "")).lower()
            if not include_failed_orders and raw_st == "failed":
                continue
            o_dt = _as_utc(o.created_at)
            if raw_st == "paid":
                st_text, st_color, is_pos = "موفق", "emerald", False
            elif raw_st == "refunded":
                st_text, st_color, is_pos = "مسترد شده", "purple", True
            elif raw_st == "pending":
                st_text, st_color, is_pos = "در انتظار پرداخت", "amber", False
            else:
                st_text, st_color, is_pos = "ناموفق", "rose", False

            history_items.append({
                "id": o.id,
                "type": "order",
                "title": f"خرید {o.service_name}",
                "service_id": o.service_id,
                "service_name": o.service_name,
                "is_custom": not bool(o.service_id) and "دلخواه" in (o.service_name or ""),
                "traffic_gb": o.traffic_gb or 0,
                "duration_days": o.duration_days or 0,
                "amount": o.amount,
                "amount_formatted": f"{o.amount:,} تومان",
                "is_positive": is_pos,
                "status": st_text,
                "raw_status": raw_st,
                "status_color": st_color,
                "date_jalali": format_jalali_dt(o.created_at, tz_name),
                "timestamp": o_dt.timestamp() if o_dt else 0,
            })

        topups_res = await session.execute(
            select(Topup).where(Topup.telegram_id == telegram_id).order_by(Topup.id.desc()).limit(limit)
        )
        for tp in topups_res.scalars().all():
            t_dt = _as_utc(tp.created_at)
            st = (tp.status or "pending").lower()
            _, method_label = classify_topup_method(getattr(tp, "receipt_hash", None), lang=lang)
            clean_method = method_label.split(" ", 1)[1] if " " in method_label else method_label
            history_items.append({
                "id": tp.id,
                "type": "topup",
                "title": f"افزایش موجودی ({clean_method})",
                "method_label": method_label,
                "amount": tp.amount,
                "amount_formatted": f"{tp.amount:,} تومان",
                "is_positive": st == "approved",
                "status": "تایید شده" if st == "approved" else ("رد شده" if st == "rejected" else "در انتظار بررسی"),
                "raw_status": st,
                "status_color": "emerald" if st == "approved" else ("rose" if st == "rejected" else "amber"),
                "date_jalali": format_jalali_dt(tp.created_at, tz_name),
                "timestamp": t_dt.timestamp() if t_dt else 0,
            })

        admin_logs_res = await session.execute(
            select(AdminLog).where(
                AdminLog.action.in_(["wallet_charge", "wallet_deduct", "balance_add", "balance_sub"]),
                AdminLog.target_user_id == telegram_id,
            ).order_by(AdminLog.id.desc()).limit(15)
        )
        for al in admin_logs_res.scalars().all():
            al_dt = _as_utc(al.created_at)
            is_pos = al.action in ("wallet_charge", "balance_add")
            parsed_amt = 0
            m = _AMOUNT_EN_RE.search(al.detail or "") or _AMOUNT_FA_RE.search(al.detail or "")
            if m:
                try:
                    parsed_amt = int(m.group(1).replace(",", ""))
                except Exception:
                    parsed_amt = 0
            history_items.append({
                "id": al.id,
                "type": "admin_adjust",
                "title": "شارژ دستی مدیریت" if is_pos else "کسر دستی مدیریت",
                "amount": parsed_amt,
                "amount_formatted": f"{parsed_amt:,} تومان" if parsed_amt else "--",
                "is_positive": is_pos,
                "status": "ثبت شد",
                "raw_status": "approved" if is_pos else "deducted",
                "status_color": "emerald" if is_pos else "rose",
                "date_jalali": format_jalali_dt(al.created_at, tz_name),
                "timestamp": al_dt.timestamp() if al_dt else 0,
            })

        card_auto_res = await session.execute(
            select(CardAutoInvoice).where(
                CardAutoInvoice.telegram_id == telegram_id,
                CardAutoInvoice.status == "paid",
            ).order_by(CardAutoInvoice.id.desc()).limit(30)
        )
        for ca in card_auto_res.scalars().all():
            raw_ca_dt = ca.paid_at or ca.created_at
            ca_dt = _as_utc(raw_ca_dt)
            history_items.append({
                "id": f"ca_{ca.id}",
                "type": "card_auto",
                "title": "افزایش موجودی (کارت به کارت خودکار)",
                "amount": ca.exact_amount,
                "amount_formatted": f"{ca.exact_amount:,} تومان",
                "is_positive": True,
                "status": "تایید خودکار",
                "raw_status": "paid",
                "status_color": "emerald",
                "date_jalali": format_jalali_dt(raw_ca_dt, tz_name),
                "timestamp": ca_dt.timestamp() if ca_dt else 0,
            })

        crypto_res = await session.execute(
            select(CryptoInvoice).where(
                CryptoInvoice.telegram_id == telegram_id,
                CryptoInvoice.status == "paid",
            ).order_by(CryptoInvoice.id.desc()).limit(30)
        )
        for cr in crypto_res.scalars().all():
            raw_cr_dt = cr.paid_at or cr.created_at
            cr_dt = _as_utc(raw_cr_dt)
            cr_curr = (cr.currency or "TON").upper()
            history_items.append({
                "id": f"cr_{cr.id}",
                "type": "crypto",
                "currency": cr_curr,
                "title": f"شارژ کیف پول (رمزارز {cr_curr})",
                "amount": cr.amount_toman,
                "amount_formatted": f"{cr.amount_toman:,} تومان",
                "is_positive": True,
                "status": "تایید شده",
                "raw_status": "paid",
                "status_color": "emerald",
                "date_jalali": format_jalali_dt(raw_cr_dt, tz_name),
                "timestamp": cr_dt.timestamp() if cr_dt else 0,
            })

        history_items.sort(key=lambda x: x["timestamp"], reverse=True)
    except Exception as exc:
        logger.warning("Failed to fetch transaction history for %s: %s", telegram_id, exc)

    return history_items
