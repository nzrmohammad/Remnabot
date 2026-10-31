"""Gift Cards and Voucher Service: supports Direct Send to friend and Shareable Links."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import GiftCard, Order, OrderStatus, Service, User, Wallet
from bot.services.loyalty import apply_loyalty_discount, get_user_loyalty

logger = logging.getLogger(__name__)


def generate_gift_code() -> str:
    """Generate a clean, unambiguous 12-character alphanumeric code."""
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    token = "".join(secrets.choice(alphabet) for _ in range(10))
    return f"GIFT-{token}"


async def create_gift(
    session: AsyncSession,
    sender_telegram_id: int,
    sender_name: str | None,
    delivery_type: str,  # "DIRECT" or "LINK"
    gift_type: str,      # "BALANCE" or "SERVICE"
    amount: int = 0,     # Toman for balance
    service_id: int | None = None,
    receiver_target: str | None = None,  # @username or telegram_id
    message: str | None = None,
    bot: Any = None,
    bot_username: str = "",
    cache: Any = None,
) -> dict[str, Any]:
    """Create a gift card, deduct sender's balance atomically, and optionally notify receiver."""
    delivery_type = delivery_type.upper() if delivery_type else "LINK"
    if delivery_type not in ("DIRECT", "LINK"):
        delivery_type = "LINK"

    gift_type = gift_type.upper() if gift_type else "BALANCE"
    if gift_type not in ("BALANCE", "SERVICE"):
        return {"ok": False, "message": "نوع هدیه نامعتبر است."}

    cost_to_charge = 0
    service_obj = None
    service_name = None

    if gift_type == "BALANCE":
        if amount < 10000:
            return {"ok": False, "message": "حداقل مبلغ هدیه اعتبار ۱۰,۰۰۰ تومان است."}
        cost_to_charge = amount
    elif gift_type == "SERVICE":
        if not service_id:
            return {"ok": False, "message": "شناسه سرویس الزامی است."}
        srv_res = await session.execute(select(Service).where(Service.id == service_id, Service.is_active.is_(True)))
        service_obj = srv_res.scalar_one_or_none()
        if not service_obj:
            return {"ok": False, "message": "سرویس مورد نظر یافت نشد یا غیرفعال است."}
        service_name = service_obj.name
        
        # Apply sender's loyalty discount
        loyalty = await get_user_loyalty(session, sender_telegram_id, cache=cache)
        discount_pct = loyalty.get("discount_percent", 0)
        _, final_cost = apply_loyalty_discount(service_obj.price, discount_pct)
        cost_to_charge = final_cost

    # 1. Atomic Balance Check & Deduction
    wallet_res = await session.execute(
        select(Wallet).where(Wallet.telegram_id == sender_telegram_id).with_for_update()
    )
    wallet = wallet_res.scalar_one_or_none()
    if not wallet or wallet.balance < cost_to_charge:
        return {
            "ok": False,
            "error": "insufficient_balance",
            "needed": cost_to_charge,
            "current": wallet.balance if wallet else 0,
            "message": "موجودی کیف پول شما برای ارسال این هدیه کافی نیست.",
        }

    # Deduct atomically
    wallet.balance -= cost_to_charge

    # 2. Resolve recipient if direct
    receiver_tg_id: int | None = None
    receiver_uname: str | None = None

    if delivery_type == "DIRECT" and receiver_target:
        clean_target = receiver_target.strip().lstrip("@")
        if clean_target.isdigit():
            receiver_tg_id = int(clean_target)
            u_res = await session.execute(select(User).where(User.telegram_id == receiver_tg_id))
            target_u = u_res.scalar_one_or_none()
            if target_u and target_u.username:
                receiver_uname = target_u.username
        else:
            receiver_uname = clean_target.lower()
            u_res = await session.execute(select(User).where(func.lower(User.username) == receiver_uname))
            target_u = u_res.scalar_one_or_none()
            if target_u:
                receiver_tg_id = target_u.telegram_id

    # 3. Create Gift Record
    code = generate_gift_code()
    gift = GiftCard(
        code=code,
        sender_telegram_id=sender_telegram_id,
        sender_name=sender_name or "یک دوست",
        receiver_telegram_id=receiver_tg_id,
        receiver_username=receiver_uname,
        delivery_type=delivery_type,
        gift_type=gift_type,
        amount=amount if gift_type == "BALANCE" else cost_to_charge,
        service_id=service_id if gift_type == "SERVICE" else None,
        service_name=service_name,
        message=(message or "").strip()[:250],
        is_claimed=False,
    )
    session.add(gift)
    await session.commit()

    share_url = f"https://t.me/{bot_username}?start=gift_{code}" if bot_username else code

    # 4. If direct delivery and receiver has telegram_id, notify them immediately
    if delivery_type == "DIRECT" and receiver_tg_id and bot:
        try:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            kb = InlineKeyboardBuilder()
            kb.button(text="🎁 دریافت و باز کردن هدیه", url=share_url)
            
            gift_title = f"{amount:,} تومان اعتبار" if gift_type == "BALANCE" else f"اشتراک «{service_name}»"
            msg_text = (
                f"🎁 <b>یک هدیه ویژه برای شما ارسال شد!</b>\n\n"
                f"👤 از طرف: <b>{sender_name or 'دوست شما'}</b>\n"
                f"📦 هدیه: <b>{gift_title}</b>\n"
            )
            if message:
                msg_text += f"💌 پیام همراه: <i>«{message}»</i>\n"
            msg_text += "\nبرای دریافت و فعال‌سازی روی دکمه زیر بزنید:"

            await bot.send_message(
                chat_id=receiver_tg_id,
                text=msg_text,
                reply_markup=kb.as_markup(),
                parse_mode="HTML",
            )
        except Exception as notify_err:
            logger.debug("Failed notifying gift recipient %s: %s", receiver_tg_id, notify_err)

    return {
        "ok": True,
        "code": code,
        "share_url": share_url,
        "cost": cost_to_charge,
        "gift_type": gift_type,
        "delivery_type": delivery_type,
        "message": "کارت هدیه با موفقیت صادر شد.",
    }


async def claim_gift(
    session: AsyncSession,
    code: str,
    claimer_telegram_id: int,
    claimer_username: str | None = None,
    remnawave: Any = None,
    bot: Any = None,
    session_factory: Any = None,
) -> dict[str, Any]:
    """Claim a gift card by code. Validates ownership, provisions balance or service, and notifies sender."""
    clean_code = code.strip().upper()
    
    # Atomic lookup with row lock
    res = await session.execute(
        select(GiftCard).where(GiftCard.code == clean_code).with_for_update()
    )
    gift = res.scalar_one_or_none()
    if not gift:
        return {"ok": False, "message": "کد هدیه نامعتبر است یا یافت نشد."}

    if gift.is_claimed:
        return {"ok": False, "message": "این کارت هدیه قبلاً استفاده شده است."}

    # Ownership checks for DIRECT delivery
    if gift.delivery_type == "DIRECT":
        if gift.receiver_telegram_id and gift.receiver_telegram_id != claimer_telegram_id:
            return {"ok": False, "message": "این کارت هدیه اختصاصاً برای کاربر دیگری ارسال شده است."}
        if gift.receiver_username and claimer_username:
            if gift.receiver_username.lower() != claimer_username.lower() and gift.receiver_telegram_id != claimer_telegram_id:
                return {"ok": False, "message": "این کارت هدیه اختصاصاً برای کاربر دیگری ارسال شده است."}

    sender_id = gift.sender_telegram_id
    if sender_id == claimer_telegram_id:
        return {"ok": False, "message": "شما نمی‌توانید هدیه‌ای که خودتان ساخته‌اید را تحویل بگیرید."}

    # 1. Apply Reward
    if gift.gift_type == "BALANCE":
        # Charge claimer wallet
        wallet_res = await session.execute(
            select(Wallet).where(Wallet.telegram_id == claimer_telegram_id).with_for_update()
        )
        wallet = wallet_res.scalar_one_or_none()
        if not wallet:
            wallet = Wallet(telegram_id=claimer_telegram_id, balance=0)
            session.add(wallet)
        wallet.balance += gift.amount

    elif gift.gift_type == "SERVICE":
        # Provision service for claimer
        service = None
        if gift.service_id:
            s_res = await session.execute(select(Service).where(Service.id == gift.service_id))
            service = s_res.scalar_one_or_none()
        
        if not service:
            # Fallback to credit wallet with the amount if service was deleted
            wallet_res = await session.execute(
                select(Wallet).where(Wallet.telegram_id == claimer_telegram_id).with_for_update()
            )
            wallet = wallet_res.scalar_one_or_none()
            if not wallet:
                wallet = Wallet(telegram_id=claimer_telegram_id, balance=0)
                session.add(wallet)
            wallet.balance += gift.amount
        else:
            from bot.services.purchases import execute_purchase
            # Execute purchase with 100% discount since it's already paid by sender
            purchase_res = await execute_purchase(
                remnawave=remnawave,
                session=session,
                service=service,
                telegram_id=claimer_telegram_id,
                create_new=True,
                discount_amount=service.price,
                bot=bot,
                session_factory=session_factory,
            )
            if not purchase_res.ok:
                # If panel call fails, credit balance instead so user doesn't lose the gift
                wallet_res = await session.execute(
                    select(Wallet).where(Wallet.telegram_id == claimer_telegram_id).with_for_update()
                )
                wallet = wallet_res.scalar_one_or_none()
                if not wallet:
                    wallet = Wallet(telegram_id=claimer_telegram_id, balance=0)
                    session.add(wallet)
                wallet.balance += gift.amount

    # 2. Mark Gift Claimed
    gift.is_claimed = True
    gift.claimed_at = datetime.now(timezone.utc)
    gift.receiver_telegram_id = claimer_telegram_id
    await session.commit()

    # 3. Notify Sender
    if bot and sender_id:
        try:
            claimer_name = f"@{claimer_username}" if claimer_username else f"شناسه {claimer_telegram_id}"
            notify_text = (
                f"🎉 <b>هدیه ارسالی شما تحویل گرفته شد!</b>\n\n"
                f"دوست شما <b>{claimer_name}</b> کارت هدیه شما را دریافت و فعال کرد.\n"
                f"از همراهی و مهر شما در خانواده ما سپاسگزاریم. ❤️"
            )
            await bot.send_message(chat_id=sender_id, text=notify_text, parse_mode="HTML")
        except Exception as notify_err:
            logger.debug("Failed notifying gift sender %s: %s", sender_id, notify_err)

    gift_title = f"{gift.amount:,} تومان اعتبار کیف‌پول" if gift.gift_type == "BALANCE" else f"اشتراک «{gift.service_name}»"
    return {
        "ok": True,
        "gift_type": gift.gift_type,
        "amount": gift.amount,
        "service_name": gift.service_name,
        "sender_name": gift.sender_name,
        "message": f"تبریک! {gift_title} با موفقیت به حساب شما اضافه شد.",
    }


async def get_user_gifts(session: AsyncSession, telegram_id: int) -> dict[str, list[dict[str, Any]]]:
    """Return sent and received gifts for a user."""
    sent_res = await session.execute(
        select(GiftCard).where(GiftCard.sender_telegram_id == telegram_id).order_by(GiftCard.created_at.desc()).limit(20)
    )
    sent_items = sent_res.scalars().all()

    received_res = await session.execute(
        select(GiftCard).where(GiftCard.receiver_telegram_id == telegram_id, GiftCard.is_claimed.is_(True)).order_by(GiftCard.claimed_at.desc()).limit(20)
    )
    received_items = received_res.scalars().all()

    def _fmt(g: GiftCard) -> dict[str, Any]:
        return {
            "id": g.id,
            "code": g.code,
            "gift_type": g.gift_type,
            "amount": g.amount,
            "service_name": g.service_name,
            "sender_name": g.sender_name,
            "receiver_username": g.receiver_username,
            "receiver_telegram_id": g.receiver_telegram_id,
            "delivery_type": g.delivery_type,
            "message": g.message,
            "is_claimed": g.is_claimed,
            "created_at": g.created_at.isoformat() if g.created_at else None,
            "claimed_at": g.claimed_at.isoformat() if g.claimed_at else None,
        }

    return {
        "sent": [_fmt(g) for g in sent_items],
        "received": [_fmt(g) for g in received_items],
    }
