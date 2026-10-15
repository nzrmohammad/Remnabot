"""Auto-Renew Background Service.

Periodically inspects users with auto_renew=True whose subscriptions are
about to expire or exhausted, and auto-renews them using their wallet balance.
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db.models import Order, User, Wallet
from bot.db.repositories.order_repo import OrderRepository
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.purchases import execute_purchase
from bot.services.remnawave import RemnawaveClient
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)


async def auto_renew_sweep_loop(
    bot,
    session_factory: async_sessionmaker,
    remnawave: RemnawaveClient,
    cache: FastCache | None = None,
) -> None:
    """Runs every 6 hours to automatically renew expiring subscriptions."""
    logger.info("Starting auto-renew background service")
    while True:
        try:
            await asyncio.sleep(60)  # Initial delay after bot start
            async with session_factory() as session:
                user_stmt = select(User).where(User.auto_renew.is_(True), User.is_banned.is_(False))
                res = await session.execute(user_stmt)
                users = list(res.scalars().all())

                for user in users:
                    try:
                        panel_users = await remnawave.get_users_by_telegram_id(user.telegram_id) or []
                        if not panel_users:
                            continue

                        primary = next(
                            (u for u in panel_users if (u.get("status") or "").upper() == "ACTIVE"),
                            panel_users[0],
                        )

                        # Check if expiring soon
                        expire_str = primary.get("expireAt")
                        days_left = 999
                        if expire_str:
                            try:
                                exp_dt = datetime.fromisoformat(str(expire_str).replace("Z", "+00:00"))
                                days_left = (exp_dt - datetime.now(timezone.utc)).total_seconds() / 86400.0
                            except Exception:
                                pass

                        used_bytes = int(primary.get("usedTrafficBytes") or 0)
                        limit_bytes = int(primary.get("trafficLimitBytes") or 0)
                        traffic_exhausted = (limit_bytes > 0 and used_bytes >= limit_bytes)
                        expiring_soon = (days_left <= 1.0 or traffic_exhausted)

                        if not expiring_soon:
                            continue

                        # Find user's last paid order to determine plan
                        order_repo = OrderRepository(session)
                        last_order_stmt = (
                            select(Order)
                            .where(Order.telegram_id == user.telegram_id, Order.status == "paid")
                            .order_by(Order.id.desc())
                            .limit(1)
                        )
                        order_res = await session.execute(last_order_stmt)
                        last_order = order_res.scalar_one_or_none()
                        if not last_order or not last_order.service_id:
                            continue

                        service_repo = ServiceRepository(session)
                        service = await service_repo.get(last_order.service_id)
                        if not service or not service.is_active:
                            continue

                        wallet_repo = WalletRepository(session)
                        wallet = await wallet_repo.get_wallet(user.telegram_id)
                        balance = wallet.balance if wallet else 0

                        dedup_key = f"auto_renew_attempt:{user.telegram_id}:{primary.get('id')}"
                        if cache and await cache.get(dedup_key):
                            continue

                        if balance >= service.price:
                            # Execute purchase
                            pur_res = await execute_purchase(
                                remnawave=remnawave,
                                session=session,
                                service=service,
                                telegram_id=user.telegram_id,
                                chosen_account=primary,
                                discount_amount=0,
                                bot=bot,
                                session_factory=session_factory,
                            )
                            if pur_res.ok:
                                if cache:
                                    await cache.set(dedup_key, "1", ttl=86400)
                                if bot:
                                    try:
                                        await bot.send_message(
                                            user.telegram_id,
                                            f"🔄 <b>تمدید خودکار اشتراک شما با موفقیت انجام شد!</b>\n\n"
                                            f"📦 پلن: <b>{service.name}</b>\n"
                                            f"💳 مبلغ پرداختی: <b>{service.price:,} تومان</b>\n"
                                            f"👛 موجودی باقیمانده: <b>{pur_res.new_balance:,} تومان</b>\n\n"
                                            f"از همراهی و اعتماد شما سپاسگزاریم.",
                                        )
                                    except Exception:
                                        pass
                        else:
                            # Insufficient balance notice
                            if cache:
                                await cache.set(dedup_key, "1", ttl=43200)
                            if bot:
                                try:
                                    shortage = service.price - balance
                                    await bot.send_message(
                                        user.telegram_id,
                                        f"⚠️ <b>هشدار تمدید خودکار اشتراک</b>\n\n"
                                        f"اعتبار سرویس شما رو به اتمام است اما موجودی کیف پول شما جهت تمدید خودکار کافی نمی‌باشد.\n\n"
                                        f"📦 پلن مورد نیاز: <b>{service.name}</b> ({service.price:,} تومان)\n"
                                        f"👛 موجودی فعلی شما: <b>{balance:,} تومان</b>\n"
                                        f"کسری موجودی: <b>{shortage:,} تومان</b>\n\n"
                                        f"لطفاً جهت جلوگیری از قطع شدن اتصال، نسبت به شارژ کیف پول خود اقدام فرمایید.",
                                    )
                                except Exception:
                                    pass
                    except Exception as u_exc:
                        logger.warning("Error checking auto_renew for user %s: %s", user.telegram_id, u_exc)

            await asyncio.sleep(21600)  # Check every 6 hours
        except asyncio.CancelledError:
            break
        except Exception as loop_err:
            logger.exception("Error in auto_renew_sweep_loop: %s", loop_err)
            await asyncio.sleep(300)
