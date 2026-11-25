"""Admin broadcast messaging with audience targeting."""
import asyncio
import logging
from datetime import datetime, timezone
from html import escape
from typing import Any

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import _back_admin, is_admin
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.menu import delete_message_silently, render_menu
from bot.services.remnawave import RemnawaveClient
from bot.services.task_queue import execute_broadcast_job, request_job_stop
from bot.states.admin import BroadcastStates

logger = logging.getLogger(__name__)
router = Router(name="admin_broadcast")

_is_admin = is_admin

from bot.services.broadcast import resolve_broadcast_recipients as _resolve_broadcast_recipients

BROADCAST_CONFIRM_KEY = "bcast:draft"


@router.callback_query(F.data == "adm:broadcast")
async def broadcast_audience_select(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    kb = InlineKeyboardBuilder()
    if lang == "fa":
        # Persian RTL: first added is LEFT, second added is RIGHT
        # Row 1: Right = All, Left = Active
        kb.button(text=t(lang, "bcast_target_active"), callback_data="adm:bcast:target:active")
        kb.button(text=t(lang, "bcast_target_all"), callback_data="adm:bcast:target:all")
        # Row 2: Right = Expired, Left = Balance
        kb.button(text=t(lang, "bcast_target_balance"), callback_data="adm:bcast:target:balance")
        kb.button(text=t(lang, "bcast_target_expired"), callback_data="adm:bcast:target:expired")
    else:
        kb.button(text=t(lang, "bcast_target_all"), callback_data="adm:bcast:target:all")
        kb.button(text=t(lang, "bcast_target_active"), callback_data="adm:bcast:target:active")
        kb.button(text=t(lang, "bcast_target_expired"), callback_data="adm:bcast:target:expired")
        kb.button(text=t(lang, "bcast_target_balance"), callback_data="adm:bcast:target:balance")

    # Row 3: Buyers
    kb.button(text=t(lang, "bcast_target_buyers"), callback_data="adm:bcast:target:buyers")
    # Row 4: Back
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(2, 2, 1, 1)

    await call.answer()
    await render_menu(bot, user, user_repo, t(lang, "bcast_target_title"), kb.as_markup())


@router.callback_query(F.data.startswith("adm:bcast:target:"))
async def broadcast_target_picked(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    target = call.data.rsplit(":", 1)[1]
    await state.set_state(BroadcastStates.waiting_text)
    await state.update_data(bcast_target=target)

    target_label = t(lang, f"bcast_target_{target}")
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:broadcast")
    kb.adjust(1)

    prompt = f"🎯 <b>{target_label}</b>\n\n{t(lang, 'broadcast_prompt')}"
    await call.answer()
    await render_menu(bot, user, user_repo, prompt, kb.as_markup())


@router.message(BroadcastStates.waiting_text, F.text | F.photo)
async def broadcast_text(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    draft = (message.caption if message.photo else message.text or "").strip()
    photo_id = message.photo[-1].file_id if message.photo else None
    data = await state.get_data()
    target = str(data.get("bcast_target", "all"))
    target_label = t(lang, f"bcast_target_{target}")

    if not draft and not photo_id:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="adm:broadcast")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "broadcast_prompt"), kb.as_markup())
        return

    recipients = await _resolve_broadcast_recipients(session, remnawave, target)
    await state.update_data(draft=draft, photo_id=photo_id, recipient_ids=recipients)

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_send"), callback_data=BROADCAST_CONFIRM_KEY)
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:broadcast")
    kb.adjust(1)

    preview_text = t(
        lang, "bcast_preview_target",
        target=target_label,
        count=len(recipients),
        text=escape(draft) if draft else "(فقط تصویر)",
    )
    if photo_id:
        preview_text = f"🖼 <b>[دارای تصویر پیوست]</b>\n\n{preview_text}"
    await render_menu(bot, user, user_repo, preview_text, kb.as_markup())


ACTIVE_BROADCASTS: dict[str, dict] = {}
_BACKGROUND_TASKS: set[asyncio.Task] = set()
_BROADCAST_TTL_SECONDS = 86400 * 7


def _prune_active_broadcasts(max_keep: int = 5) -> None:
    """Prune finished/stopped broadcasts to bound memory usage."""
    if len(ACTIVE_BROADCASTS) <= max_keep:
        return
    finished_keys = [
        k for k, v in ACTIVE_BROADCASTS.items()
        if v.get("status") in ("finished", "stopped", "revoked")
    ]
    for k in finished_keys[:-max_keep]:
        ACTIVE_BROADCASTS.pop(k, None)


def _normalize_broadcast_state(raw: dict) -> dict:
    sent_raw = raw.get("sent") or []
    normalized_sent = [
        (int(item[0]), int(item[1]))
        for item in sent_raw
        if isinstance(item, (list, tuple)) and len(item) == 2
    ]
    return {
        "status": str(raw.get("status") or "finished"),
        "sent": normalized_sent,
        "ok": int(raw.get("ok") or 0),
        "fail": int(raw.get("fail") or 0),
        "total": int(raw.get("total") or 0),
        "target": str(raw.get("target") or "all"),
        "admin_id": int(raw.get("admin_id") or 0),
    }


async def _persist_broadcast_state(bot: Bot, bcast_id: str) -> None:
    """Sync in-memory broadcast state to Redis so stop/revoke survives restarts."""
    state = ACTIVE_BROADCASTS.get(bcast_id)
    cache = getattr(bot, "cache", None)
    if not state or not (cache and hasattr(cache, "set")):
        return
    try:
        payload = {
            **state,
            "sent": [[int(cid), int(mid)] for cid, mid in (state.get("sent") or [])],
        }
        await cache.set(f"bcast:bot:{bcast_id}", payload, ttl_seconds=_BROADCAST_TTL_SECONDS)
    except Exception as exc:
        logger.debug("Failed persisting broadcast state %s: %s", bcast_id, exc)


async def _load_broadcast_state(bot: Bot, bcast_id: str) -> dict | None:
    """Load broadcast state from memory or fall back to Redis after restart."""
    if bcast_id in ACTIVE_BROADCASTS:
        return ACTIVE_BROADCASTS[bcast_id]
    cache = getattr(bot, "cache", None)
    if not (cache and hasattr(cache, "get")):
        return None
    try:
        raw = await cache.get(f"bcast:bot:{bcast_id}")
        if isinstance(raw, dict):
            state = _normalize_broadcast_state(raw)
            ACTIVE_BROADCASTS[bcast_id] = state
            return state
    except Exception as exc:
        logger.debug("Failed loading broadcast state %s: %s", bcast_id, exc)
    return None


async def _render_broadcast_admin_status(
    bot: Bot,
    session_factory: Any,
    admin_id: int,
    text: str,
    markup: Any,
    *,
    log_detail: str | None = None,
) -> None:
    """Render progress/completion UI and optionally write AdminLog using short-lived session."""
    if session_factory is not None:
        try:
            async with session_factory() as bg_session:
                if log_detail:
                    await AdminLogRepository(bg_session).log(admin_id, "broadcast", detail=log_detail)
                bg_user_repo = UserRepository(bg_session)
                admin_user = await bg_user_repo.get_by_telegram_id(admin_id)
                if admin_user is not None:
                    await render_menu(bot, admin_user, bg_user_repo, text, markup)
                else:
                    await bot.send_message(admin_id, text, reply_markup=markup)
                await bg_session.commit()
                return
        except Exception as exc:
            logger.debug("Broadcast status render via session_factory failed: %s", exc)
    try:
        await bot.send_message(admin_id, text, reply_markup=markup)
    except Exception:
        pass


async def _sync_bot_status(bot: Bot, bcast_id: str) -> None:
    await _persist_broadcast_state(bot, bcast_id)


async def _on_recovered_bot_complete(
    bot: Bot,
    session_factory: Any,
    job: dict[str, Any],
) -> None:
    """Finalize recovered/completed bot broadcast UI & AdminLog."""
    bcast_id = str(job["job_id"])
    admin_id = int(job.get("admin_id") or 0)
    lang = str(job.get("lang") or "fa")
    target = str(job.get("target") or "all")
    target_label = str(job.get("target_label") or t(lang, f"bcast_target_{target}"))
    final_state = job.get("status", "finished")
    final_ok = int(job.get("ok") or 0)
    final_fail = int(job.get("fail") or 0)
    sent_pairs = job.get("sent") or []

    kb_done = InlineKeyboardBuilder()
    if len(sent_pairs) > 0:
        kb_done.button(text="🗑 پاک‌کردن پیام‌های ارسال‌شده", callback_data=f"adm:bcast:del:{bcast_id}")
    kb_done.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb_done.adjust(1)

    if final_state == "stopped":
        done_text = (
            f"🛑 <b>ارسال همگانی متوقف شد.</b>\n\n"
            f"✅ ارسال‌شده تا توقف: {final_ok:,}\n"
            f"❌ ناموفق: {final_fail:,}\n\n"
            f"می‌توانید پیام‌های ارسال شده را از چت کاربران پاک کنید."
        )
    else:
        done_text = (
            f"✅ <b>ارسال همگانی با موفقیت پایان یافت.</b>\n\n"
            f"🎯 مخاطبان: {target_label}\n"
            f"✅ ارسال موفق: {final_ok:,}\n"
            f"❌ ناموفق: {final_fail:,}"
        )

    await _render_broadcast_admin_status(
        bot,
        session_factory,
        admin_id,
        done_text,
        kb_done.as_markup(),
        log_detail=f"target={target} ok={final_ok} fail={final_fail} stopped={final_state == 'stopped'}",
    )


async def _run_bot_broadcast(
    bot: Bot,
    session_factory: Any,
    admin_id: int,
    lang: str,
    target: str,
    target_label: str,
    draft: str,
    photo_id: str | None,
    recipient_ids: list[int],
    bcast_id: str,
    kb_cancel_markup: Any,
) -> None:
    """Execute bot broadcast sending loop via durable Redis task queue."""
    cache = getattr(bot, "cache", None)
    job = {
        "job_id": bcast_id,
        "kind": "bot",
        "admin_id": admin_id,
        "lang": lang,
        "target": target,
        "target_label": target_label,
        "draft": draft,
        "text": "",
        "photo_id": photo_id,
        "photo_raw": "",
        "recipient_ids": [int(x) for x in recipient_ids],
        "cursor_idx": 0,
        "ok": int(ACTIVE_BROADCASTS[bcast_id].get("ok") or 0),
        "fail": int(ACTIVE_BROADCASTS[bcast_id].get("fail") or 0),
        "sent": [],
        "status": "running",
        "start_time": datetime.now(timezone.utc).isoformat(),
    }

    async def _sync_cb(_job: dict, _done: bool) -> None:
        await _persist_broadcast_state(bot, bcast_id)

    async def _progress_cb(j: dict) -> None:
        cur_ok = int(j.get("ok") or 0)
        cur_fail = int(j.get("fail") or 0)
        live_text = (
            f"🚀 <b>در حال ارسال همگانی...</b>\n\n"
            f"🎯 مخاطبان: {target_label}\n"
            f"👥 کل: {len(recipient_ids):,}\n"
            f"✅ ارسال شده: {cur_ok:,} | ❌ ناموفق: {cur_fail:,}"
        )
        await _render_broadcast_admin_status(
            bot, session_factory, admin_id, live_text, kb_cancel_markup
        )

    async def _complete_cb(j: dict) -> None:
        await _on_recovered_bot_complete(bot, session_factory, j)

    await execute_broadcast_job(
        bot,
        job,
        cache=cache,
        in_memory_ref=ACTIVE_BROADCASTS[bcast_id],
        sync_status_fn=_sync_cb,
        on_progress=_progress_cb,
        on_complete=_complete_cb,
    )


@router.callback_query(F.data == BROADCAST_CONFIRM_KEY)
async def broadcast_send(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, session_factory=None,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    data = await state.get_data()
    draft = data.get("draft", "")
    photo_id = data.get("photo_id")
    recipient_ids = data.get("recipient_ids") or []
    target = data.get("bcast_target", "all")
    await state.clear()

    if not draft and not photo_id:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    _prune_active_broadcasts(max_keep=5)
    import time
    import uuid
    bcast_id = f"bc_{int(time.time())}_{call.from_user.id}_{uuid.uuid4().hex[:6]}"
    ACTIVE_BROADCASTS[bcast_id] = {
        "status": "running",
        "sent": [],  # list of (chat_id, message_id)
        "ok": 0,
        "fail": 0,
        "total": len(recipient_ids),
        "target": target,
        "admin_id": call.from_user.id,
    }
    await _persist_broadcast_state(bot, bcast_id)

    # Show initial running UI with Cancel button
    kb_cancel = InlineKeyboardBuilder()
    kb_cancel.button(text="🛑 توقف ارسال", callback_data=f"adm:bcast:stop:{bcast_id}")
    kb_cancel.adjust(1)

    target_label = t(lang, f"bcast_target_{target}")
    progress_text = (
        f"🚀 <b>در حال ارسال همگانی...</b>\n\n"
        f"🎯 مخاطبان: {target_label}\n"
        f"👥 کل دریافت‌کنندگان: {len(recipient_ids):,}\n"
        f"📊 وضعیت: در حال ارسال (0 از {len(recipient_ids):,})"
    )
    await call.answer("🚀 ارسال همگانی آغاز شد.")
    await render_menu(bot, user, user_repo, progress_text, kb_cancel.as_markup())

    # Commit and release request-scoped DB session before spawning background broadcast task.
    await session.commit()

    sf = session_factory or getattr(bot, "session_factory", None)
    bg_task = asyncio.create_task(
        _run_bot_broadcast(
            bot=bot,
            session_factory=sf,
            admin_id=call.from_user.id,
            lang=lang,
            target=target,
            target_label=target_label,
            draft=draft,
            photo_id=photo_id,
            recipient_ids=recipient_ids,
            bcast_id=bcast_id,
            kb_cancel_markup=kb_cancel.as_markup(),
        ),
        name=f"bot-broadcast-{bcast_id}",
    )
    _BACKGROUND_TASKS.add(bg_task)
    bg_task.add_done_callback(_BACKGROUND_TASKS.discard)


@router.callback_query(F.data.startswith("adm:bcast:stop:"))
async def broadcast_stop_handler(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    bcast_id = call.data.removeprefix("adm:bcast:stop:")
    task = await _load_broadcast_state(bot, bcast_id)
    if task and task.get("status") == "running":
        task["status"] = "stopped"
        await _persist_broadcast_state(bot, bcast_id)
        await request_job_stop(getattr(bot, "cache", None), bcast_id)
        await call.answer("🛑 دستور توقف ارسال همگانی صادر شد.", show_alert=True)
    else:
        await call.answer("ارسال در حال اجرا نیست یا به پایان رسیده است.", show_alert=True)


@router.callback_query(F.data.startswith("adm:bcast:del:"))
async def broadcast_revoke_handler(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    bcast_id = call.data.removeprefix("adm:bcast:del:")
    task = await _load_broadcast_state(bot, bcast_id)
    if not task:
        await call.answer("اطلاعات این ارسال یافت نشد.", show_alert=True)
        return

    sent_list = task.get("sent", [])
    if not sent_list:
        await call.answer("پیامی برای حذف وجود ندارد.", show_alert=True)
        return

    await call.answer("⏳ در حال حذف پیام‌های ارسال‌شده از چت کاربران...", show_alert=False)
    del_count = 0
    for chat_id, msg_id in sent_list:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            del_count += 1
        except Exception:
            pass
        if del_count % 30 == 0:
            await asyncio.sleep(0.5)

    task["sent"] = []
    task["status"] = "revoked"
    await _persist_broadcast_state(bot, bcast_id)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    result_text = (
        f"🗑 <b>پیام‌های همگانی با موفقیت حذف شدند.</b>\n\n"
        f"تعداد {del_count:,} پیام از چت کاربران با موفقیت پاک شد."
    )
    await render_menu(bot, user, user_repo, result_text, _back_admin(lang).as_markup())
