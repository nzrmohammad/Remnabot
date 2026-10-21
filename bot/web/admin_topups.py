"""Admin Topups, Payment Approvals, and Card Receipt Verification API endpoints."""
import asyncio
import inspect
import json
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

# Bot instance resolved dynamically from request.app["bot"]
from aiohttp import web
from sqlalchemy import desc, func, select

from bot.common import admin_thread_kwargs
from bot.common.helpers import get_limit_bytes, get_used_bytes
from bot.db.models import (
    AdminLog,
    AppSetting,
    Coupon,
    CryptoInvoice,
    KnownDevice,
    NodeCost,
    Order,
    Service,
    SupportMessage,
    Topup,
    User,
    Wallet,
)
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.coupon_repo import CouponRepository
from bot.db.repositories.node_cost_repo import NodeCostRepository
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.support_repo import SupportMessageRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.broadcast import resolve_broadcast_recipients as _resolve_broadcast_recipients
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings
from bot.web.admin_common import _check_admin, db_session, format_service_name_icon_first
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)


async def get_admin_topups(request: web.Request) -> web.Response:
    """Return list of pending card-to-card topups."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        async with db_session(request) as session:
            wallet_repo = WalletRepository(session)
            user_repo = UserRepository(session)
            pending = await wallet_repo.list_pending_topups()

            items = []
            receipts_dir = Path("data/receipts")
            for t in pending:
                u = await user_repo.get_by_telegram_id(t.telegram_id)
                receipt_ref = getattr(t, "receipt_photo_id", None) or getattr(t, "receipt_hash", None)
                u_full_name = getattr(u, "full_name", None)
                if not u_full_name:
                    u_full_name = f"@{u.username}" if (u and u.username) else f"کاربر {t.telegram_id}"
                r_hash = getattr(t, "receipt_hash", "") or ""
                photo_id = getattr(t, "receipt_photo_id", None)
                local_file = receipts_dir / f"receipt_{t.id}.jpg"
                has_photo = bool(
                    photo_id
                    or local_file.exists()
                    or r_hash.startswith("img:")
                    or r_hash.startswith("photo:")
                )
                items.append({
                    "id": t.id,
                    "telegram_id": t.telegram_id,
                    "username": u.username if u else None,
                    "full_name": u_full_name,
                    "avatar_url": f"/api/user/avatar?user_id={t.telegram_id}",
                    "amount": t.amount,
                    "status": t.status,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "receipt_hash": getattr(t, "receipt_hash", None),
                    "receipt_photo_id": photo_id,
                    "has_photo": has_photo,
                    "photo_url": f"/api/admin/topup/photo?id={t.id}" if has_photo else None,
                })
            return web.json_response({"ok": True, "topups": items})
    except Exception as exc:
        logger.exception("Error in get_admin_topups: %s", exc)
        return web.json_response({"ok": False, "error": "خطا در پردازش لیست فیش‌ها"}, status=500)


async def post_admin_topup_action(request: web.Request) -> web.Response:
    """Approve or reject a pending card-to-card topup."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    topup_id = body.get("topup_id")
    approved = bool(body.get("approved", True))
    if not topup_id:
        return web.json_response({"ok": False, "error": "شناسه فیش الزامی است."}, status=400)

    bot = request.app["bot"]

    async with db_session(request) as session:
        wallet_repo = WalletRepository(session)
        claimed = await wallet_repo.claim_topup(int(topup_id), approved)
        if not claimed:
            return web.json_response({"ok": False, "error": "این فیش قبلاً تعیین وضعیت شده است."}, status=400)

        if approved:
            try:
                await wallet_repo.add_balance_atomic(claimed.telegram_id, claimed.amount)
            except Exception as exc:
                logger.error("Failed to add balance for topup #%s (user=%s, amount=%s): %s", claimed.id, claimed.telegram_id, claimed.amount, exc)
                try:
                    from bot.services.error_reporter import report_error
                    await report_error(
                        bot,
                        session=session,
                        exc=exc,
                        context=f"Admin topup approval failed #{claimed.id} amount={claimed.amount}",
                        user_id=claimed.telegram_id,
                    )
                except Exception:
                    pass
                raise
            session.add(
                AdminLog(
                    admin_id=admin["id"],
                    action="topup_approved",
                    detail=f"تایید فیش {claimed.id} و شارژ {claimed.amount:,} تومان برای {claimed.telegram_id}",
                )
            )
            msg = f"✅ <b>واریز شما تایید شد!</b>\n\nمبلغ {claimed.amount:,} تومان به کیف پول شما اضافه شد."
        else:
            session.add(
                AdminLog(
                    admin_id=admin["id"],
                    action="topup_rejected",
                    detail=f"رد فیش {claimed.id} برای {claimed.telegram_id}",
                )
            )
            msg = "❌ <b>فیش ارسالی شما رد شد.</b>\n\nدر صورت وجود مغایرت با پشتیبانی در ارتباط باشید."

        await session.commit()

    # Clear cache
    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{claimed.telegram_id}:dashboard")
    await cache.delete("tma:admin:overview")

    # Send telegram notification to user with navigation keyboard
    try:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from bot.locales.texts import t

        user_lang = "fa"
        async with db_session(request) as session:
            user_repo = UserRepository(session)
            u_obj = await user_repo.get_by_telegram_id(claimed.telegram_id)
            if u_obj and u_obj.language:
                user_lang = u_obj.language

            kb = InlineKeyboardBuilder()
            if approved:
                if user_lang == "fa":
                    kb.button(text=t(user_lang, "btn_services"), callback_data="menu:services")
                    kb.button(text=t(user_lang, "btn_wallet"), callback_data="menu:wallet")
                else:
                    kb.button(text=t(user_lang, "btn_wallet"), callback_data="menu:wallet")
                    kb.button(text=t(user_lang, "btn_services"), callback_data="menu:services")
                kb.adjust(2)
            else:
                kb.button(text=t(user_lang, "btn_support"), callback_data="menu:support")
                kb.adjust(1)

            if bot:
                if u_obj:
                    from bot.services.menu import delete_message_silently
                    await delete_message_silently(bot, u_obj.telegram_id, u_obj.menu_message_id)
                sent_msg = await bot.send_message(
                    chat_id=claimed.telegram_id,
                    text=msg,
                    reply_markup=kb.as_markup(),
                    parse_mode="HTML",
                )
                if u_obj and isinstance(getattr(sent_msg, "message_id", None), int):
                    await user_repo.set_menu_message_id(u_obj, sent_msg.message_id)
    except Exception as exc:
        logger.warning("Could not send topup decision notice to %s: %s", claimed.telegram_id, exc)

    # Sync status with admin supergroup / topic
    settings = request.app.get("settings")
    admin_chat_id = settings.ADMIN_CHAT_ID if settings else None
    if admin_chat_id and bot:
        store = None
        try:
            async with db_session(request) as session:
                store = await get_store_settings(session)
        except Exception:
            pass

        thread_kwargs = admin_thread_kwargs(store, settings, kind="topups") if store and settings else {}
        status_badge = "✅ تایید شد (از طریق پنل ادمین)" if approved else "❌ رد شد (از طریق پنل ادمین)"
        admin_name = admin.get("first_name") or admin.get("username") or str(admin.get("id"))

        # 1. Remove pending inline buttons from the original receipt prompt
        if claimed.admin_message_id:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=admin_chat_id,
                    message_id=claimed.admin_message_id,
                    reply_markup=None,
                )
            except Exception as exc:
                logger.debug("Could not remove reply markup for topup %s: %s", claimed.id, exc)

        # 2. Announce resolution into the admin supergroup topic
        admin_id_val = admin.get("id")
        admin_id_str = f" (<code>{admin_id_val}</code>)" if admin_id_val else ""
        notice_text = (
            f"📌 <b>تعیین وضعیت فیش {claimed.id}</b>\n"
            f"👤 کاربر: <code>{claimed.telegram_id}</code>\n"
            f"💰 مبلغ: <b>{claimed.amount:,}</b> تومان\n"
            f"📊 وضعیت: <b>{status_badge}</b>\n"
            f"👮 توسط ادمین: <b>{escape(str(admin_name))}</b>{admin_id_str}"
        )
        try:
            kwargs = dict(thread_kwargs)
            if claimed.admin_message_id:
                kwargs["reply_to_message_id"] = claimed.admin_message_id
            await bot.send_message(
                chat_id=admin_chat_id,
                text=notice_text,
                parse_mode="HTML",
                **kwargs,
            )
        except Exception:
            try:
                await bot.send_message(
                    chat_id=admin_chat_id,
                    text=notice_text,
                    parse_mode="HTML",
                    **thread_kwargs,
                )
            except Exception as exc:
                logger.warning("Failed to send topup update notice to admin chat: %s", exc)

    return web.json_response({
        "ok": True,
        "message": "فیش با موفقیت تایید شد." if approved else "فیش با موفقیت رد شد.",
    })


async def get_admin_topup_photo(request: web.Request) -> web.Response:
    """Stream receipt photo for a topup request from Telegram servers."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    topup_id_raw = request.query.get("id")
    if not topup_id_raw:
        return web.json_response({"ok": False, "error": "شناسه فیش الزامی است."}, status=400)

    try:
        topup_id = int(topup_id_raw)
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "شناسه فیش نامعتبر است."}, status=400)

    bot = request.app.get("bot")

    # 1. Fast local disk check (highest speed and reliability)
    local_file = Path("data/receipts") / f"receipt_{topup_id}.jpg"
    if local_file.exists():
        content = await asyncio.to_thread(local_file.read_bytes)
        return web.Response(
            body=content,
            content_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=86400"},
        )

    try:
        async with db_session(request) as session:
            wallet_repo = WalletRepository(session)
            topup = await wallet_repo.get_topup(topup_id)
            if not topup:
                return web.Response(text="فیش مورد نظر یافت نشد", status=404)

            photo_id = getattr(topup, "receipt_photo_id", None)
            if photo_id and photo_id.startswith("local:"):
                target_name = photo_id.split("local:", 1)[1]
                target_path = Path("data/receipts") / target_name
                if target_path.exists():
                    content = await asyncio.to_thread(target_path.read_bytes)
                    return web.Response(
                        body=content,
                        content_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400"},
                    )

            if not photo_id:
                return web.Response(text="تصویری برای این فیش یافت نشد", status=404)

            if not bot:
                return web.Response(text="Bot not available", status=503)

            file_info = await bot.get_file(photo_id)
            if not file_info or not file_info.file_path:
                return web.Response(text="فایل تصویر در سرور تلگرام یافت نشد", status=404)

            file_bio = await bot.download_file(file_info.file_path)
            if inspect.iscoroutine(file_bio):
                file_bio = await file_bio
            if isinstance(file_bio, bytes):
                content = file_bio
            elif hasattr(file_bio, "getvalue"):
                content = file_bio.getvalue()
            elif hasattr(file_bio, "read"):
                content = file_bio.read()
                if inspect.iscoroutine(content):
                    content = await content
            else:
                content = bytes(file_bio)

            # Cache locally to disk for instant subsequent loads
            try:
                local_file.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(local_file.write_bytes, content)
            except Exception as cache_err:
                logger.debug("Could not cache receipt photo locally: %s", cache_err)

            return web.Response(
                body=content,
                content_type="image/jpeg",
                headers={
                    "Cache-Control": "private, max-age=86400",
                },
            )
    except Exception as exc:
        logger.exception("Error serving topup photo for #%s: %s", topup_id, exc)
        return web.Response(text="خطا در دریافت تصویر فیش", status=500)
