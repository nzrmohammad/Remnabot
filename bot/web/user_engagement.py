"""TMA User Engagement API endpoints (Quests, Loyalty Themes, Red Packets, P2P Wallet Transfers)."""
from __future__ import annotations

import logging

from aiohttp import web

from bot.locales.texts import t
from bot.services.engagement_service import (
    PUBLIC_QUEST_EVENTS,
    claim_red_packet,
    claim_weekly_quest_reward,
    create_red_packet,
    get_user_red_packets,
    get_weekly_quests_state,
    record_weekly_quest_event,
    refund_red_packet,
    set_user_card_theme,
    transfer_wallet_balance,
)
from bot.web.cache import FastCache, invalidate_user_cache, user_action_lock
from bot.web.user_common import db_session, enforce_invite_only, require_user, resolve_tma_lang

logger = logging.getLogger(__name__)


async def _parse_json_dict(request: web.Request) -> dict:
    try:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    except Exception:
        return {}


async def post_user_quest_event(request: web.Request) -> web.Response:
    """Record a verified interactive quest activity (speedtest, wallet_card_check)."""
    user_auth, err = require_user(request)
    if err or not user_auth:
        return err
    req_lang = resolve_tma_lang(request)
    if user_auth.get("is_preview"):
        return web.json_response({"ok": True, "preview": True})

    body = await _parse_json_dict(request)
    event_name = str(body.get("event") or "").strip().lower()
    if event_name not in PUBLIC_QUEST_EVENTS:
        return web.json_response(
            {"ok": False, "message": "Invalid quest event." if req_lang == "en" else "رویداد مأموریت معتبر نیست."},
            status=400,
        )

    telegram_id = int(user_auth["id"])
    tz_name = getattr(request.app.get("settings"), "TIMEZONE", "Asia/Tehran")
    cache: FastCache | None = request.app.get("cache")

    async with db_session(request) as session:
        inv_err = await enforce_invite_only(session, telegram_id, user_auth, remnawave=request.app.get("remnawave"))
        if inv_err:
            return inv_err
        await record_weekly_quest_event(session, telegram_id, event_name, tz_name=tz_name, commit=True)
        quests = await get_weekly_quests_state(session, telegram_id, tz_name=tz_name, lang=req_lang)

    await invalidate_user_cache(cache, telegram_id)
    return web.json_response({"ok": True, "quests": quests})


async def post_user_quest_claim(request: web.Request) -> web.Response:
    """Claim a completed weekly quest rewarding spin_tickets ONLY."""
    user_auth, err = require_user(request)
    if err or not user_auth:
        return err
    req_lang = resolve_tma_lang(request)
    if user_auth.get("is_preview"):
        return web.json_response({"ok": False, "message": t(req_lang, "spin_preview_blocked")}, status=400)

    body = await _parse_json_dict(request)
    quest_id = str(body.get("quest_id") or "").strip()
    telegram_id = int(user_auth["id"])
    cache: FastCache | None = request.app.get("cache")
    tz_name = getattr(request.app.get("settings"), "TIMEZONE", "Asia/Tehran")

    async with user_action_lock(cache, telegram_id, "quest_claim", ttl_seconds=15) as acquired:
        if not acquired:
            return web.json_response({"ok": False, "message": t(req_lang, "spin_rate_limited")}, status=429)

        async with db_session(request) as session:
            inv_err = await enforce_invite_only(session, telegram_id, user_auth, remnawave=request.app.get("remnawave"))
            if inv_err:
                return inv_err
            res = await claim_weekly_quest_reward(
                session,
                telegram_id,
                quest_id,
                tz_name=tz_name,
                cache=cache,
                lang=req_lang,
            )

    status_code = int(res.pop("status_code", 200 if res.get("ok") else 400))
    return web.json_response(res, status=status_code)


async def post_user_set_theme(request: web.Request) -> web.Response:
    """Persist selected loyalty-unlocked Story & Subscription Card theme."""
    user_auth, err = require_user(request)
    if err or not user_auth:
        return err
    req_lang = resolve_tma_lang(request)
    body = await _parse_json_dict(request)
    theme_id = str(body.get("theme_id") or "").strip()
    telegram_id = int(user_auth["id"])
    cache: FastCache | None = request.app.get("cache")

    if user_auth.get("is_preview"):
        return web.json_response({"ok": True, "card_theme": theme_id or "ocean"})

    async with db_session(request) as session:
        res = await set_user_card_theme(session, telegram_id, theme_id, cache=cache, lang=req_lang)

    status_code = int(res.pop("status_code", 200 if res.get("ok") else 400))
    return web.json_response(res, status=status_code)


async def post_user_wallet_transfer(request: web.Request) -> web.Response:
    """Atomic Direct Peer-to-Peer wallet balance transfer."""
    user_auth, err = require_user(request)
    if err or not user_auth:
        return err
    req_lang = resolve_tma_lang(request)
    if user_auth.get("is_preview"):
        return web.json_response(
            {"ok": False, "message": "Unavailable in preview mode." if req_lang == "en" else "در حالت پیش‌نمایش مجاز نیست."},
            status=400,
        )

    body = await _parse_json_dict(request)
    recipient = str(body.get("recipient") or "")
    amount = body.get("amount")
    note = body.get("note")
    telegram_id = int(user_auth["id"])
    cache: FastCache | None = request.app.get("cache")
    bot = request.app.get("bot")

    async with user_action_lock(cache, telegram_id, "p2p_transfer", ttl_seconds=20) as acquired:
        if not acquired:
            return web.json_response({"ok": False, "message": t(req_lang, "spin_rate_limited")}, status=429)

        async with db_session(request) as session:
            inv_err = await enforce_invite_only(session, telegram_id, user_auth, remnawave=request.app.get("remnawave"))
            if inv_err:
                return inv_err
            res = await transfer_wallet_balance(
                session,
                sender_telegram_id=telegram_id,
                recipient_target=recipient,
                amount=amount,
                note=str(note) if note is not None else None,
                bot=bot,
                cache=cache,
                lang=req_lang,
            )

    status_code = int(res.pop("status_code", 200 if res.get("ok") else 400))
    return web.json_response(res, status=status_code)


async def post_user_red_packet_create(request: web.Request) -> web.Response:
    """Create a multi-claimer group Red Packet funded atomically by user's wallet."""
    user_auth, err = require_user(request)
    if err or not user_auth:
        return err
    req_lang = resolve_tma_lang(request)
    if user_auth.get("is_preview"):
        return web.json_response(
            {"ok": False, "message": "Unavailable in preview mode." if req_lang == "en" else "در حالت پیش‌نمایش مجاز نیست."},
            status=400,
        )

    body = await _parse_json_dict(request)
    telegram_id = int(user_auth["id"])
    cache: FastCache | None = request.app.get("cache")
    bot = request.app.get("bot")
    bot_username = getattr(getattr(bot, "_me", None), "username", "") if bot else ""
    sender_name = str(user_auth.get("first_name") or user_auth.get("username") or "").strip() or None

    async with user_action_lock(cache, telegram_id, "red_packet_create", ttl_seconds=20) as acquired:
        if not acquired:
            return web.json_response({"ok": False, "message": t(req_lang, "spin_rate_limited")}, status=429)

        async with db_session(request) as session:
            inv_err = await enforce_invite_only(session, telegram_id, user_auth, remnawave=request.app.get("remnawave"))
            if inv_err:
                return inv_err
            res = await create_red_packet(
                session,
                sender_telegram_id=telegram_id,
                sender_name=sender_name,
                total_amount=body.get("total_amount"),
                max_claims=body.get("max_claims"),
                split_mode=str(body.get("split_mode") or "RANDOM"),
                message=str(body.get("message") or "") or None,
                bot_username=bot_username,
                cache=cache,
                lang=req_lang,
            )

    status_code = int(res.pop("status_code", 200 if res.get("ok") else 400))
    return web.json_response(res, status=status_code)


async def post_user_red_packet_claim(request: web.Request) -> web.Response:
    """Claim one share from a Red Packet by code."""
    user_auth, err = require_user(request)
    if err or not user_auth:
        return err
    req_lang = resolve_tma_lang(request)
    if user_auth.get("is_preview"):
        return web.json_response(
            {"ok": False, "message": "Unavailable in preview mode." if req_lang == "en" else "در حالت پیش‌نمایش مجاز نیست."},
            status=400,
        )

    body = await _parse_json_dict(request)
    code = str(body.get("code") or "")
    telegram_id = int(user_auth["id"])
    cache: FastCache | None = request.app.get("cache")
    bot = request.app.get("bot")
    claimer_name = str(user_auth.get("first_name") or user_auth.get("username") or "").strip() or None

    async with db_session(request) as session:
        inv_err = await enforce_invite_only(session, telegram_id, user_auth, remnawave=request.app.get("remnawave"))
        if inv_err:
            return inv_err
        res = await claim_red_packet(
            session,
            code=code,
            claimer_telegram_id=telegram_id,
            claimer_name=claimer_name,
            bot=bot,
            cache=cache,
            lang=req_lang,
        )

    status_code = int(res.pop("status_code", 200 if res.get("ok") else 400))
    return web.json_response(res, status=status_code)


async def post_user_red_packet_refund(request: web.Request) -> web.Response:
    """Refund leftover balance from an expired Red Packet back to creator wallet."""
    user_auth, err = require_user(request)
    if err or not user_auth:
        return err
    req_lang = resolve_tma_lang(request)
    body = await _parse_json_dict(request)
    packet_id = body.get("packet_id")
    if isinstance(packet_id, bool) or not str(packet_id or "").isdigit():
        return web.json_response({"ok": False, "message": "Invalid packet ID."}, status=400)

    telegram_id = int(user_auth["id"])
    cache: FastCache | None = request.app.get("cache")

    async with db_session(request) as session:
        res = await refund_red_packet(
            session,
            packet_id=int(packet_id),
            sender_telegram_id=telegram_id,
            cache=cache,
            lang=req_lang,
        )

    status_code = int(res.pop("status_code", 200 if res.get("ok") else 400))
    return web.json_response(res, status=status_code)


async def get_user_red_packets_history(request: web.Request) -> web.Response:
    """List Red Packets created and claimed by authenticated user."""
    user_auth, err = require_user(request)
    if err or not user_auth:
        return err
    telegram_id = int(user_auth["id"])
    bot = request.app.get("bot")
    bot_username = getattr(getattr(bot, "_me", None), "username", "") if bot else ""

    async with db_session(request) as session:
        data = await get_user_red_packets(session, telegram_id, bot_username=bot_username)

    return web.json_response({"ok": True, "red_packets": data})
