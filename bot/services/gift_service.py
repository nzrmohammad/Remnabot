"""Gift Cards and Voucher Service: supports Direct Send to friend and Shareable Links."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from html import escape
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import GiftCard, Service, User, Wallet

logger = logging.getLogger(__name__)


def generate_gift_code() -> str:
    """Generate a clean, unambiguous 12-character alphanumeric code."""
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    token = "".join(secrets.choice(alphabet) for _ in range(10))
    return f"GIFT-{token}"


async def create_gift(
    session: AsyncSession,
    sender_telegram_id: int,
    sender_name: str | None = None,
    delivery_type: str = "LINK",  # "DIRECT" or "LINK"
    gift_type: str = "BALANCE",    # "BALANCE" or "SERVICE"
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
        if service_obj.max_purchases and (service_obj.purchases_count or 0) >= service_obj.max_purchases:
            return {"ok": False, "message": "سقف فروش این سرویس تکمیل شده است."}
        service_name = service_obj.name
        # Charge full retail price on gifts to prevent VIP loyalty discount arbitrage across accounts.
        cost_to_charge = int(service_obj.price)

    # 1. Atomic Balance Check & Deduction
    row = await session.execute(
        text(
            "UPDATE wallets SET balance = balance - :cost "
            "WHERE telegram_id = :tid AND balance >= :cost "
            "RETURNING balance"
        ),
        {"cost": cost_to_charge, "tid": sender_telegram_id},
    )
    new_bal = row.scalar_one_or_none()
    if new_bal is None:
        chk_res = await session.execute(
            select(Wallet).where(Wallet.telegram_id == sender_telegram_id)
        )
        wallet = chk_res.scalar_one_or_none()
        return {
            "ok": False,
            "error": "insufficient_balance",
            "needed": cost_to_charge,
            "current": wallet.balance if wallet else 0,
            "message": "موجودی کیف پول شما برای ارسال این هدیه کافی نیست.",
        }

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
            
            gift_title = (
                f"{amount:,} تومان اعتبار"
                if gift_type == "BALANCE"
                else f"اشتراک «{escape(str(service_name or ''))}»"
            )
            safe_sender = escape(str(sender_name or "دوست شما"))
            msg_text = (
                f"🎁 <b>یک هدیه ویژه برای شما ارسال شد!</b>\n\n"
                f"👤 از طرف: <b>{safe_sender}</b>\n"
                f"📦 هدیه: <b>{gift_title}</b>\n"
            )
            if message:
                msg_text += f"💌 پیام همراه: <i>«{escape(str(message))}»</i>\n"
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
        if gift.receiver_username:
            r_uname = gift.receiver_username.lstrip("@").strip().lower()
            c_uname = claimer_username.lstrip("@").strip().lower() if claimer_username else None
            if gift.receiver_telegram_id != claimer_telegram_id and (not c_uname or c_uname != r_uname):
                return {"ok": False, "message": "این کارت هدیه اختصاصاً برای کاربر دیگری ارسال شده است."}

    sender_id = gift.sender_telegram_id
    if sender_id == claimer_telegram_id:
        return {"ok": False, "message": "شما نمی‌توانید هدیه‌ای که خودتان ساخته‌اید را تحویل بگیرید."}

    orig_receiver_id = gift.receiver_telegram_id
    now_utc = datetime.now(timezone.utc)

    # Atomically claim the gift record BEFORE external panel calls / cross-session execution
    claim_res = await session.execute(
        update(GiftCard)
        .where(GiftCard.id == gift.id, GiftCard.is_claimed.is_(False))
        .values(
            is_claimed=True,
            claimed_at=now_utc,
            receiver_telegram_id=claimer_telegram_id,
        )
    )
    if (claim_res.rowcount or 0) != 1:
        return {"ok": False, "message": "این کارت هدیه قبلاً استفاده شده است."}

    sub_url = None

    # 1. Apply Reward
    if gift.gift_type == "BALANCE":
        from bot.db.repositories.wallet_repo import WalletRepository
        await WalletRepository(session).add_balance_atomic(claimer_telegram_id, gift.amount)
        await session.commit()

    elif gift.gift_type == "SERVICE":
        service = None
        if gift.service_id:
            s_res = await session.execute(select(Service).where(Service.id == gift.service_id))
            service = s_res.scalar_one_or_none()

        service_unavailable = (
            not service
            or not service.is_active
            or bool(service.max_purchases and (service.purchases_count or 0) >= service.max_purchases)
        )
        if service_unavailable:
            # Permanent unavailability -> convert gift to equivalent wallet credit once
            from bot.db.repositories.wallet_repo import WalletRepository
            await WalletRepository(session).add_balance_atomic(claimer_telegram_id, gift.amount)
            await session.commit()
        else:
            # Persist claim lock immediately so another session/worker cannot claim concurrently
            await session.commit()
            from bot.services.purchases import execute_purchase
            purchase_res = None
            try:
                if session_factory:
                    async with session_factory() as purchase_session:
                        p_service = await purchase_session.get(Service, service.id)
                        purchase_res = await execute_purchase(
                            remnawave=remnawave,
                            session=purchase_session,
                            service=p_service or service,
                            telegram_id=claimer_telegram_id,
                            create_new=True,
                            discount_amount=(p_service.price if p_service else service.price),
                            bot=bot,
                            session_factory=session_factory,
                        )
                else:
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
            except Exception as p_exc:
                logger.error("Gift execute_purchase exception: %s", p_exc)
                purchase_res = None

            if not purchase_res or not purchase_res.ok:
                # Revert claim cleanly on transient/panel failure instead of converting downtime into cash
                await session.execute(
                    update(GiftCard)
                    .where(GiftCard.id == gift.id)
                    .values(
                        is_claimed=False,
                        claimed_at=None,
                        receiver_telegram_id=orig_receiver_id,
                    )
                )
                await session.commit()
                return {
                    "ok": False,
                    "message": "در حال حاضر امکان فعال‌سازی اشتراک هدیه وجود ندارد. کارت هدیه شما محفوظ است؛ لطفاً دقایقی دیگر مجدداً تلاش کنید.",
                }
            sub_url = getattr(purchase_res, "subscription_url", None)
            await session.commit()

    # 3. Notify Sender
    if bot and sender_id:
        try:
            claimer_label = f"@{claimer_username}" if claimer_username else f"شناسه {claimer_telegram_id}"
            notify_text = (
                f"🎉 <b>هدیه ارسالی شما تحویل گرفته شد!</b>\n\n"
                f"دوست شما <b>{escape(claimer_label)}</b> کارت هدیه شما را دریافت و فعال کرد.\n"
                f"از همراهی و مهر شما در خانواده ما سپاسگزاریم. ❤️"
            )
            await bot.send_message(chat_id=sender_id, text=notify_text, parse_mode="HTML")
        except Exception as notify_err:
            logger.debug("Failed notifying gift sender %s: %s", sender_id, notify_err)

    gift_title = (
        f"{gift.amount:,} تومان اعتبار کیف‌پول"
        if gift.gift_type == "BALANCE"
        else f"اشتراک «{escape(str(gift.service_name or ''))}»"
    )

    return {
        "ok": True,
        "gift_type": gift.gift_type,
        "amount": gift.amount,
        "service_name": gift.service_name,
        "sender_name": gift.sender_name,
        "subscription_url": sub_url,
        "message": f"تبریک! {gift_title} با موفقیت به حساب شما اضافه شد.",
    }


async def get_user_gifts(
    session: AsyncSession,
    telegram_id: int,
    bot_username: str = "",
) -> dict[str, list[dict[str, Any]]]:
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
        share_url = f"https://t.me/{bot_username}?start=gift_{g.code}" if bot_username else g.code
        created_at_jalali = ""
        if g.created_at:
            try:
                import jdatetime
                created_at_jalali = jdatetime.datetime.fromgregorian(datetime=g.created_at).strftime("%Y/%m/%d %H:%M")
            except Exception:
                created_at_jalali = g.created_at.strftime("%Y/%m/%d")

        gift_desc = (
            f"{g.amount:,} تومان اعتبار"
            if g.gift_type == "BALANCE"
            else f"اشتراک {g.service_name or ''}".strip()
        )
        return {
            "id": g.id,
            "code": g.code,
            "share_url": share_url,
            "gift_type": g.gift_type,
            "gift_desc": gift_desc,
            "amount": g.amount,
            "service_name": g.service_name,
            "sender_name": g.sender_name,
            "receiver_username": g.receiver_username,
            "receiver_telegram_id": g.receiver_telegram_id,
            "delivery_type": g.delivery_type,
            "message": g.message,
            "is_claimed": g.is_claimed,
            "created_at": g.created_at.isoformat() if g.created_at else None,
            "created_at_jalali": created_at_jalali,
            "claimed_at": g.claimed_at.isoformat() if g.claimed_at else None,
        }

    return {
        "sent": [_fmt(g) for g in sent_items],
        "received": [_fmt(g) for g in received_items],
    }


async def redeem_code_to_wallet(
    session: AsyncSession,
    code: str,
    telegram_id: int,
    username: str | None = None,
    remnawave: Any = None,
    bot: Any = None,
    session_factory: Any = None,
) -> dict[str, Any]:
    """Unified SSOT helper to redeem either a credit voucher coupon or a friend GiftCard."""
    from bot.db.repositories.coupon_repo import CouponRepository

    clean_code = code.strip().upper()
    if clean_code.startswith("GIFT-"):
        return await claim_gift(
            session=session,
            code=clean_code,
            claimer_telegram_id=telegram_id,
            claimer_username=username,
            remnawave=remnawave,
            bot=bot,
            session_factory=session_factory,
        )

    coupon_repo = CouponRepository(session)
    ok, amount, msg = await coupon_repo.redeem_credit_voucher(clean_code, telegram_id)
    if ok:
        await session.commit()
        return {"ok": True, "amount": amount, "message": msg}

    # Check if the code belongs to a GiftCard without standard GIFT- prefix
    gift_exists = await session.execute(select(GiftCard.id).where(GiftCard.code == clean_code))
    if gift_exists.scalar_one_or_none() is not None:
        return await claim_gift(
            session=session,
            code=clean_code,
            claimer_telegram_id=telegram_id,
            claimer_username=username,
            remnawave=remnawave,
            bot=bot,
            session_factory=session_factory,
        )

    return {"ok": False, "amount": 0, "message": msg}
