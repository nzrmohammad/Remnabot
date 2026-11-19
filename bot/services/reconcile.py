"""Reconcile job: close stale `pending` orders left by crashes.

Runs every 30 minutes. Any order still `pending` after 15 minutes means the
process died between the panel call and the wallet deduction (or the panel
call itself hung). The job marks it `failed` and pings the admin chat so a
possibly-free service never goes unnoticed — the admin can check the panel
and revoke/charge manually.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.common import admin_thread_kwargs
from bot.config import get_settings
from bot.db.models import Order
from bot.db.repositories.order_repo import OrderRepository
from bot.services.app_settings import get_store_settings

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 30 * 60
STALE_MINUTES = 15


async def run_reconcile(
    bot: Bot,
    session_factory: async_sessionmaker,
    remnawave: Any = None,
) -> int:
    """Mark stale pending orders failed + notify admin. Returns count."""
    closed = 0
    async with session_factory() as session:
        repo = OrderRepository(session)
        stale = await repo.list_pending(older_than_minutes=STALE_MINUTES)
        for order in stale:
            panel_handled = True
            if remnawave:
                if getattr(order, "is_renewal", False):
                    # Renewal compensation: revert panel account back to pre-purchase snapshot
                    if order.panel_user_id and getattr(order, "snapshot_data", None):
                        try:
                            # 1. Check if newer paid order exists for this panel user
                            newer_paid_stmt = (
                                select(Order)
                                .where(
                                    Order.panel_user_id == order.panel_user_id,
                                    Order.status == "paid",
                                    Order.id > order.id,
                                )
                                .limit(1)
                            )
                            newer_paid = (await session.execute(newer_paid_stmt)).scalar_one_or_none()
                            if newer_paid:
                                logger.info(
                                    "Reconcile: newer paid order %s exists for panel_user_id %s; skipping rollback for stale order %s",
                                    newer_paid.id,
                                    order.panel_user_id,
                                    order.id,
                                )
                            else:
                                snap = json.loads(order.snapshot_data)
                                orig_expire = snap.get("expireAt")
                                orig_traffic = snap.get("trafficLimitBytes")
                                orig_status = snap.get("status") or "ACTIVE"

                                curr_panel_user = None
                                if hasattr(remnawave, "get_panel_user_by_id"):
                                    curr_panel_user = await remnawave.get_panel_user_by_id(int(order.panel_user_id))

                                if curr_panel_user:
                                    curr_exp = curr_panel_user.get("expireAt")
                                    curr_traf = curr_panel_user.get("trafficLimitBytes")
                                    if curr_exp == orig_expire and curr_traf == orig_traffic:
                                        logger.info(
                                            "Reconcile: panel user %s state matches snapshot; no revert needed for order %s",
                                            order.panel_user_id,
                                            order.id,
                                        )
                                    else:
                                        await remnawave.update_user_subscription(
                                            int(order.panel_user_id),
                                            orig_expire,
                                            int(orig_traffic) if orig_traffic is not None else 0,
                                            status=orig_status,
                                        )
                                        logger.warning(
                                            "Reconcile reverted uncharged renewal order %s for panel user %s to original state",
                                            order.id,
                                            order.panel_user_id,
                                        )
                                else:
                                    await remnawave.update_user_subscription(
                                        int(order.panel_user_id),
                                        orig_expire,
                                        int(orig_traffic) if orig_traffic is not None else 0,
                                        status=orig_status,
                                    )
                                    logger.warning(
                                        "Reconcile reverted uncharged renewal order %s for panel user %s to original state",
                                        order.id,
                                        order.panel_user_id,
                                    )
                        except Exception as r_err:
                            panel_handled = False
                            logger.error(
                                "Reconcile failed to revert renewal for user %s: %s",
                                order.panel_user_id,
                                r_err,
                            )
                else:
                    # New account: disable uncharged panel user
                    user_id_to_disable = order.panel_user_id
                    if not user_id_to_disable and order.panel_username:
                        try:
                            p_user = await remnawave.get_user_by_username(order.panel_username)
                            if p_user and p_user.get("id"):
                                user_id_to_disable = int(p_user["id"])
                        except Exception as u_err:
                            logger.error("Reconcile could not lookup user by username %s: %s", order.panel_username, u_err)

                    if user_id_to_disable:
                        try:
                            await remnawave.set_user_status(int(user_id_to_disable), "DISABLED")
                            logger.warning(
                                "Reconcile disabled uncharged new panel user %s for order %s",
                                user_id_to_disable,
                                order.id,
                            )
                        except Exception as p_err:
                            panel_handled = False
                            logger.error(
                                "Reconcile could not disable panel user %s: %s",
                                user_id_to_disable,
                                p_err,
                            )

            if panel_handled:
                await repo.mark_failed(order)
                closed += 1

        # Check for service gifts stuck in claimed state past crash window without a fulfilled order
        from bot.db.models import GiftCard
        stale_gift_cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_MINUTES)
        stale_gifts_res = await session.execute(
            select(GiftCard).where(
                GiftCard.gift_type == "SERVICE",
                GiftCard.is_claimed.is_(True),
                GiftCard.claimed_at.is_not(None),
                GiftCard.claimed_at <= stale_gift_cutoff,
            )
        )
        for gc in stale_gifts_res.scalars().all():
            ord_res = await session.execute(
                select(Order).where(
                    Order.telegram_id == gc.receiver_telegram_id,
                    Order.service_id == gc.service_id,
                    Order.created_at >= (gc.claimed_at - timedelta(minutes=2)),
                    Order.status == "paid",
                )
            )
            if not ord_res.scalar_one_or_none():
                logger.warning("Reconcile: auto-reverting orphaned gift card %s (id=%s) stuck since %s", gc.code, gc.id, gc.claimed_at)
                gc.is_claimed = False
                gc.claimed_at = None
                if getattr(gc, "delivery_type", "LINK") != "DIRECT":
                    gc.receiver_telegram_id = None
                closed += 1

        await session.commit()

    if closed:
        settings = get_settings()
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
        except Exception as exc:
            logger.exception("reconcile: could not notify admin chat: %s", exc)
    return closed


async def reconcile_loop(
    bot: Bot,
    session_factory: async_sessionmaker,
    remnawave: Any = None,
) -> None:
    await asyncio.sleep(60)  # let startup finish first
    logger.info("reconcile loop started (every %s s)", INTERVAL_SECONDS)
    while True:
        try:
            await run_reconcile(bot, session_factory, remnawave=remnawave)
        except Exception as exc:  # noqa: BLE001
            logger.exception("reconcile sweep failed: %s", exc)
        await asyncio.sleep(INTERVAL_SECONDS)
