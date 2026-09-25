"""Smart retention loop: 7 days after service expiry, send a 20% discount offer."""
import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db.models import RetentionState, User
from bot.db.repositories.coupon_repo import CouponRepository
from bot.locales.texts import t
from bot.services.formatting import parse_iso
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 6 * 3600  # Check every 6 hours
RETENTION_COUPON_CODE = "COMEBACK20"


async def ensure_retention_coupon(session) -> None:
    repo = CouponRepository(session)
    existing = await repo.get_by_code(RETENTION_COUPON_CODE)
    if existing is None:
        await repo.create(
            code=RETENTION_COUPON_CODE,
            discount_percent=20,
            discount_amount=0,
            max_uses=0,
            expires_at=None,
        )
        logger.info("Created default retention coupon %s (20%% off)", RETENTION_COUPON_CODE)


async def check_retention_for_session(
    bot: Bot, session, remnawave: RemnawaveClient
) -> None:
    await ensure_retention_coupon(session)

    panel_users = await remnawave.get_all_panel_users()
    if not panel_users:
        return

    now = datetime.now(timezone.utc)

    for p_user in panel_users:
        raw_tid = p_user.get("telegramId")
        if not raw_tid:
            continue
        try:
            telegram_id = int(str(raw_tid))
        except (ValueError, TypeError):
            continue

        expire_iso = p_user.get("expireAt")
        if not expire_iso:
            continue

        expire_dt = parse_iso(str(expire_iso))
        if not expire_dt:
            continue

        # Calculate days since expiry
        days_expired = (now - expire_dt).total_seconds() / 86400.0
        # Target window: around 7 days (6.5 to 8.0 days)
        if not (6.5 <= days_expired <= 8.0):
            continue

        # Check if user already notified
        existing_note = await session.get(RetentionState, telegram_id)
        if existing_note is not None:
            continue

        # Check user record in bot db
        user_res = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = user_res.scalar_one_or_none()
        if user and user.is_banned:
            continue

        lang = (user.language if user else None) or "fa"

        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_services"), callback_data="menu:services")
        kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
        kb.adjust(2)

        msg = (
            f"🎉 <b>{t(lang, 'retention_title')}</b>\n\n"
            f"{t(lang, 'retention_body', days=7)}\n\n"
            f"🏷 <b>{t(lang, 'retention_code_label')} :</b> <code>{RETENTION_COUPON_CODE}</code>\n\n"
            f"{t(lang, 'retention_cta')}"
        )

        try:
            await bot.send_message(
                telegram_id, msg, reply_markup=kb.as_markup()
            )
            session.add(RetentionState(telegram_id=telegram_id))
            await session.commit()
            logger.info("Sent 7-day retention offer to user %s", telegram_id)
        except Exception as exc:
            logger.debug("Could not send retention alert to %s: %s", telegram_id, exc)


_check_retention = check_retention_for_session


async def check_and_send_retention_alerts(
    bot: Bot, session_factory: async_sessionmaker, remnawave: RemnawaveClient
) -> None:
    async with session_factory() as session:
        await check_retention_for_session(bot, session, remnawave)


async def retention_loop(
    bot: Bot, session_factory: async_sessionmaker, remnawave: RemnawaveClient
) -> None:
    logger.info("Starting smart retention loop (interval: %s s)", CHECK_INTERVAL_SECONDS)
    # Wait 60s before initial check on startup
    await asyncio.sleep(60)
    while True:
        try:
            await check_and_send_retention_alerts(bot, session_factory, remnawave)
        except Exception:
            logger.exception("Error in retention loop")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
