"""Reconcile job: close stale `pending` orders left by crashes.

Runs every 30 minutes. Any order still `pending` after 15 minutes means the
process died between the panel call and the wallet deduction (or the panel
call itself hung). The job marks it `failed` and pings the admin chat so a
possibly-free service never goes unnoticed — the admin can check the panel
and revoke/charge manually.
"""
import asyncio
import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.common import admin_thread_kwargs
from bot.config import get_settings
from bot.db.repositories.order_repo import OrderRepository

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 30 * 60
STALE_MINUTES = 15


async def run_reconcile(
    bot: Bot,
    session_factory: async_sessionmaker,
) -> int:
    """Mark stale pending orders failed + notify admin. Returns count."""
    closed = 0
    async with session_factory() as session:
        repo = OrderRepository(session)
        stale = await repo.list_pending(older_than_minutes=STALE_MINUTES)
        for order in stale:
            await repo.mark_failed(order)
            closed += 1
        await session.commit()

    if closed:
        settings = get_settings()
        from bot.services.app_settings import get_store_settings
        async with session_factory() as session:
            store = await get_store_settings(session)
        thread_kwargs = admin_thread_kwargs(store, settings, kind="alerts")
        try:
            await bot.send_message(
                settings.ADMIN_CHAT_ID,
                f"⚠️ <b>Reconcile:</b> {closed} pending order(s) were stuck "
                f"(possible crash mid-purchase) and marked <b>failed</b>.\n"
                f"Please check the panel — the service may have been activated "
                f"without charge.",
                **thread_kwargs,
            )
        except Exception:
            logger.exception("reconcile: could not notify admin chat")
    return closed


async def reconcile_loop(
    bot: Bot,
    session_factory: async_sessionmaker,
) -> None:
    await asyncio.sleep(60)  # let startup finish first
    logger.info("reconcile loop started (every %s s)", INTERVAL_SECONDS)
    while True:
        try:
            await run_reconcile(bot, session_factory)
        except Exception:  # noqa: BLE001
            logger.exception("reconcile sweep failed")
        await asyncio.sleep(INTERVAL_SECONDS)
