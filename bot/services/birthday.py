"""Automated Daily Birthday Reward Cron Service."""
import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import jdatetime
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db.models import Coupon, User
from bot.services.app_settings import get_store_settings
from bot.services.remnawave import RemnawaveClient
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)


async def birthday_sweep_loop(
    bot, session_factory: async_sessionmaker, remnawave: RemnawaveClient, cache: FastCache | None = None
) -> None:
    """Daily sweep: congratulate users on their Jalali birthday and award VIP gifts."""
    while True:
        try:
            async with session_factory() as session:
                store = await get_store_settings(session)
                if not getattr(store, "birthday_reward_enabled", True):
                    await asyncio.sleep(3600)
                    continue

                now_tehran = datetime.now(ZoneInfo("Asia/Tehran"))
                today_j = jdatetime.date.fromgregorian(date=now_tehran.date())
                jalali_year = today_j.year
                m_str = f"{today_j.month:02d}"
                d_str = f"{today_j.day:02d}"

                query = select(User).where(
                    User.birth_date.is_not(None),
                    or_(
                        User.birth_date.like(f"%/{m_str}/{d_str}"),
                        User.birth_date.like(f"%-{m_str}-{d_str}"),
                        User.birth_date.like(f"%/{today_j.month}/{today_j.day}"),
                    ),
                )
                res = await session.execute(query)
                users = res.scalars().all()

                traffic_gb = getattr(store, "birthday_reward_traffic_gb", 2) or 2
                discount_pct = getattr(store, "birthday_reward_discount_percent", 20) or 20

                for user in users:
                    dedup_key = f"birthday_reward:{user.telegram_id}:{jalali_year}"
                    if cache:
                        already_given = await cache.get(dedup_key)
                        if already_given:
                            continue

                    panel_users = []
                    try:
                        panel_users = await remnawave.get_users_by_telegram_id(user.telegram_id) or []
                    except Exception as e:
                        logger.warning("Failed fetching remnawave users for birthday reward %s: %s", user.telegram_id, e)

                    active_sub = next(
                        (u for u in panel_users if (u.get("status") or "").upper() == "ACTIVE"),
                        None,
                    )
                    traffic_added = False
                    if active_sub:
                        try:
                            primary_id = int(active_sub.get("id"))
                            current_expire = active_sub.get("expireAt")
                            current_limit = int(active_sub.get("trafficLimitBytes") or 0)
                            new_limit = current_limit + int(traffic_gb * 1024 * 1024 * 1024)
                            await remnawave.update_user_subscription(primary_id, current_expire, new_limit)
                            traffic_added = True
                        except Exception as e:
                            logger.warning("Failed adding birthday traffic for %s: %s", user.telegram_id, e)

                    coupon_code = f"BDAY_{user.telegram_id}_{secrets.token_hex(2).upper()}"
                    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
                    coupon = Coupon(
                        code=coupon_code,
                        discount_percent=discount_pct,
                        discount_amount=0,
                        max_uses=1,
                        expires_at=expires_at,
                        is_active=True,
                    )
                    session.add(coupon)
                    await session.commit()

                    traffic_msg = (
                        f"🎁 <b>{traffic_gb} گیگابایت حجم هدیه آنی</b> (به اشتراک فعال شما افزوده شد)\n"
                        if traffic_added
                        else f"🎁 <b>{traffic_gb} گیگابایت حجم هدیه</b>\n"
                    )
                    congrats_text = (
                        "🎂 <b>زادروزتان فرخنده و همایون باد!</b> 🎉\n\n"
                        "کاربر گرامی، فرا رسیدن سالروز تولدتان را صمیمانه تبریک عرض می‌کنیم! 🌸\n\n"
                        "به مناسبت روز زادروز شما، پکیج هدیه اختصاصی VIP تقدیم حضورتان می‌گردد:\n"
                        f"{traffic_msg}"
                        f"🎟 <b>کد تخفیف اختصاصی {discount_pct}٪ برای سفارش یا تمدید بعدی:</b>\n"
                        f"<code>{coupon_code}</code>\n"
                        "⏱ <i>(مهلت استفاده: ۷ روز در مینی‌اپ و ربات)</i>\n\n"
                        "با آرزوی بهترین‌ها و لحظاتی سرشار از سلامتی و شادی برای شما! 💫"
                    )
                    try:
                        await bot.send_message(user.telegram_id, congrats_text, parse_mode="HTML")
                    except Exception as msg_err:
                        logger.warning("Failed to send birthday congratulations to %s: %s", user.telegram_id, msg_err)

                    if cache:
                        await cache.set(dedup_key, "1", ttl_seconds=86400 * 400)

            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            break
        except Exception as loop_err:
            logger.exception("Error in birthday_sweep_loop: %s", loop_err)
            await asyncio.sleep(300)
