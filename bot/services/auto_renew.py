"""Auto-Renew Background Service.

Periodically inspects users with auto_renew=True whose subscriptions are
about to expire or exhausted, and auto-renews them using their wallet balance.
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db.models import Order, User
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.purchases import execute_purchase
from bot.services.remnawave import RemnawaveClient
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)


async def process_auto_renewals(
    bot,
    session_factory: async_sessionmaker,
    remnawave: RemnawaveClient,
    cache: FastCache | None = None,
) -> int:
    """Process all eligible auto-renewals in a single pass. Returns count of renewed users."""
    renewed_count = 0
    # 1. Fetch eligible user IDs only to prevent ORM instance expiration on rollback
    async with session_factory() as session:
        user_stmt = select(User.telegram_id).where(User.auto_renew.is_(True), User.is_banned.is_(False))
        res = await session.execute(user_stmt)
        user_ids = list(res.scalars().all())

    now_utc = datetime.now(timezone.utc)
    for tid in user_ids:
        try:
            panel_users = await remnawave.get_users_by_telegram_id(tid) or []
            if not panel_users:
                continue

            # Multi-account support: check ALL accounts and find the ones expiring soon
            for acc in panel_users:
                expire_str = acc.get("expireAt")
                days_left = 999.0
                if expire_str:
                    try:
                        exp_dt = datetime.fromisoformat(str(expire_str).replace("Z", "+00:00"))
                        days_left = (exp_dt - now_utc).total_seconds() / 86400.0
                    except Exception:
                        pass

                used_bytes = int(acc.get("usedTrafficBytes") or 0)
                limit_bytes = int(acc.get("trafficLimitBytes") or 0)
                traffic_exhausted = (limit_bytes > 0 and used_bytes >= limit_bytes)
                expiring_soon = (days_left <= 1.0 or traffic_exhausted)

                if not expiring_soon:
                    continue

                acc_id = acc.get("id")
                dedup_key = f"auto_renew_attempt:{tid}:{acc_id}"
                if cache and await cache.get(dedup_key):
                    continue

                # Each renewal attempt runs in its own session to guarantee safe transaction boundary
                async with session_factory() as session:
                    # Find plan specifically for this panel account (fallback to user's last base plan)
                    last_order_stmt = (
                        select(Order)
                        .where(
                            Order.telegram_id == tid,
                            Order.panel_user_id == int(acc_id) if acc_id else None,
                            Order.status == "paid",
                            Order.duration_days > 0,
                        )
                        .order_by(Order.id.desc())
                        .limit(1)
                    )
                    last_order = (await session.execute(last_order_stmt)).scalar_one_or_none()
                    if not last_order or not last_order.service_id:
                        # Fallback to user's general last paid base order
                        gen_stmt = (
                            select(Order)
                            .where(
                                Order.telegram_id == tid,
                                Order.status == "paid",
                                Order.duration_days > 0,
                            )
                            .order_by(Order.id.desc())
                            .limit(1)
                        )
                        last_order = (await session.execute(gen_stmt)).scalar_one_or_none()

                    if not last_order or not last_order.service_id:
                        continue

                    service_repo = ServiceRepository(session)
                    service = await service_repo.get(last_order.service_id)
                    if not service or not service.is_active:
                        discontinued_dedup = f"auto_renew_discontinued:{tid}:{acc_id}"
                        if cache and not await cache.get(discontinued_dedup):
                            await cache.set(discontinued_dedup, "1", ttl_seconds=86400)
                            if bot:
                                try:
                                    await bot.send_message(
                                        tid,
                                        "⚠️ <b>اطلاعیه تمدید خودکار اشتراک</b>\n\n"
                                        "اعتبار سرویس شما رو به اتمام است، اما بسته قبلی شما در حال حاضر در فروشگاه فعال نمی‌باشد.\n\n"
                                        "موجودی کیف پول شما دست‌نخورده باقی مانده است. جهت تمدید سرویس، لطفاً وارد مینی‌اپ شده و یک پلن جدید انتخاب فرمایید.",
                                    )
                                except Exception:
                                    pass
                        continue

                    wallet_repo = WalletRepository(session)
                    wallet = await wallet_repo.get_wallet(tid)
                    balance = wallet.balance if wallet else 0

                    if balance >= service.price:
                        pur_res = await execute_purchase(
                            remnawave=remnawave,
                            session=session,
                            service=service,
                            telegram_id=tid,
                            chosen_account=acc,
                            discount_amount=0,
                            bot=bot,
                            session_factory=session_factory,
                            cache=cache,
                        )
                        if pur_res.ok:
                            await session.commit()
                            renewed_count += 1
                            if cache:
                                await cache.set(dedup_key, "1", ttl_seconds=86400)
                            if bot:
                                try:
                                    await bot.send_message(
                                        tid,
                                        f"🔄 <b>تمدید خودکار اشتراک شما با موفقیت انجام شد!</b>\n\n"
                                        f"📦 پلن: <b>{service.name}</b>\n"
                                        f"💳 مبلغ پرداختی: <b>{service.price:,} تومان</b>\n"
                                        f"👛 موجودی باقیمانده: <b>{pur_res.new_balance:,} تومان</b>\n\n"
                                        f"از همراهی و اعتماد شما سپاسگزاریم.",
                                    )
                                except Exception:
                                    pass
                        else:
                            await session.rollback()
                    else:
                        # Insufficient balance notice
                        if cache:
                            await cache.set(dedup_key, "1", ttl_seconds=43200)
                        if bot:
                            try:
                                shortage = service.price - balance
                                await bot.send_message(
                                    tid,
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
            logger.warning("Error checking auto_renew for telegram_id %s: %s", tid, u_exc)

    return renewed_count


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
            await process_auto_renewals(
                bot=bot,
                session_factory=session_factory,
                remnawave=remnawave,
                cache=cache,
            )
            await asyncio.sleep(21600)  # Check every 6 hours
        except asyncio.CancelledError:
            break
        except Exception as loop_err:
            logger.exception("Error in auto_renew_sweep_loop: %s", loop_err)
            await asyncio.sleep(300)
