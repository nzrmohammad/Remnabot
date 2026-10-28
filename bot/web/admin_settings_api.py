"""Admin Settings and Exchange Rates API handlers for Telegram Mini App."""
import json
import logging

from aiohttp import web

from bot.db.models import AdminLog
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.services.app_settings import get_store_settings
from bot.web.admin_common import _check_admin as _default_check_admin
from bot.web.admin_common import db_session

logger = logging.getLogger(__name__)


def _check_admin(request):
    import bot.web.routes_admin as routes_admin
    check_fn = getattr(routes_admin, "_check_admin", _default_check_admin)
    return check_fn(request)


async def get_admin_settings(request: web.Request) -> web.Response:
    """Return runtime editable app settings."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    async with db_session(request) as session:
        store_settings = await get_store_settings(session)
        app_repo = AppSettingRepository(session)
        maint_val = await app_repo.get("maintenance")
        is_maintenance = maint_val == "1"

        data = {
            "maintenance": is_maintenance,
            "card_enabled": store_settings.card_enabled,
            "crypto_enabled": store_settings.crypto_enabled,
            "card_number": store_settings.card_number,
            "card_holder": store_settings.card_holder,
            "topup_min_amount": store_settings.topup_min_amount,
            "topup_max_amount": store_settings.topup_max_amount,
            "usdt_rate_toman": store_settings.usdt_rate_toman,
            "eur_rate_toman": store_settings.eur_rate_toman,
            "ton_rate_toman": store_settings.ton_rate_toman,
            "ton_wallet_address": store_settings.ton_wallet_address,
            "trx_enabled": store_settings.trx_enabled,
            "trx_wallet_address": store_settings.trx_wallet_address,
            "trx_rate_toman": store_settings.trx_rate_toman,
            "xrocket_enabled": store_settings.xrocket_enabled,
            "xrocket_api_key": store_settings.xrocket_api_key,
            "trial_enabled": store_settings.trial_enabled,
            "trial_traffic_gb": store_settings.trial_traffic_gb,
            "trial_duration_days": store_settings.trial_duration_days,
            "referral_enabled": store_settings.referral_enabled,
            "referral_reward_gb": store_settings.referral_reward_gb,
            "support_contact": store_settings.support_contact,
            "support_direct_enabled": store_settings.support_direct_enabled,
            "topic_topups": store_settings.topic_topups,
            "topic_orders": store_settings.topic_orders,
            "topic_support": store_settings.topic_support,
            "topic_alerts": store_settings.topic_alerts,
            "topic_backups": store_settings.topic_backups,
            "topic_reports": store_settings.topic_reports,
            "topic_nodes": store_settings.topic_nodes,
            "topic_crypto": store_settings.topic_crypto,
            "topic_errors": store_settings.topic_errors,
            "auto_clean_reports": store_settings.auto_clean_reports,
            "access_mode": store_settings.access_mode,
            "stars_enabled": store_settings.stars_enabled,
            "stars_rate_toman": store_settings.stars_rate_toman,
            "tutorial_channel_url": store_settings.tutorial_channel_url,
            "routing_tutorial_url": store_settings.routing_tutorial_url,
            "client_apps_json": store_settings.client_apps_json,
            "card_require_phone_verification": store_settings.card_require_phone_verification,
            "card_phone_iran_only": store_settings.card_phone_iran_only,
            "birthday_reward_enabled": store_settings.birthday_reward_enabled,
            "birthday_reward_traffic_gb": store_settings.birthday_reward_traffic_gb,
            "birthday_reward_discount_percent": store_settings.birthday_reward_discount_percent,
            "join_gate_enabled": store_settings.join_gate_enabled,
            "join_gate_channel": store_settings.join_gate_channel,
        }
        bot = request.app.get("bot")
        settings_cfg = request.app.get("settings")
        bot_username = getattr(settings_cfg, "BOT_USERNAME", "") or ""
        if not bot_username and bot:
            me_obj = getattr(bot, "_me", None)
            if me_obj and getattr(me_obj, "username", None):
                bot_username = me_obj.username
            elif hasattr(bot, "get_me"):
                try:
                    bot_info = await bot.get_me()
                    bot_username = bot_info.username or ""
                except Exception:
                    pass
        data["bot_username"] = bot_username
        return web.json_response({"ok": True, "settings": data})


async def post_admin_settings(request: web.Request) -> web.Response:
    """Update runtime editable app settings."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    async with db_session(request) as session:
        app_repo = AppSettingRepository(session)

        # Boolean flags
        bool_keys = (
            "card_enabled", "crypto_enabled", "trial_enabled",
            "referral_enabled", "support_direct_enabled", "maintenance",
            "stars_enabled", "trx_enabled", "xrocket_enabled",
            "card_require_phone_verification", "card_phone_iran_only", "birthday_reward_enabled",
            "join_gate_enabled", "auto_clean_reports",
        )
        for bk in bool_keys:
            if bk in body:
                val = "1" if bool(body[bk]) else "0"
                await app_repo.set(bk, val)

        # Numeric / string settings
        raw_keys = (
            "card_number", "card_holder", "topup_min_amount", "topup_max_amount",
            "usdt_rate_toman", "eur_rate_toman", "ton_rate_toman", "ton_wallet_address",
            "trx_rate_toman", "trx_wallet_address", "xrocket_api_key",
            "stars_rate_toman",
            "trial_traffic_gb", "trial_duration_days",
            "referral_reward_gb", "support_contact",
            "topic_topups", "topic_orders", "topic_support", "topic_alerts", "topic_backups", "topic_reports", "topic_nodes", "topic_crypto", "topic_errors",
            "access_mode",
            "tutorial_channel_url", "routing_tutorial_url", "client_apps_json",
            "birthday_reward_traffic_gb", "birthday_reward_discount_percent",
            "join_gate_channel",
        )
        for rk in raw_keys:
            if rk in body:
                v = body[rk]
                if v is None:
                    continue
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)
                await app_repo.set(rk, str(v).strip())

        # Invalidate cached settings
        cache = request.app.get("cache")
        if cache:
            await cache.delete("store_settings")
            await cache.delete("tma:admin:overview")

        session.add(
            AdminLog(
                admin_id=admin["id"],
                action="update_settings",
                detail=f"بروزرسانی تنظیمات سیستم: {list(body.keys())}",
            )
        )
        await session.commit()

    return web.json_response({"ok": True, "message": "تنظیمات با موفقیت ذخیره شدند."})


async def get_admin_crypto_rates(request: web.Request) -> web.Response:
    """Return realtime crypto rates from external source or fallback."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    force = request.query.get("force") in ("1", "true", "yes")
    from bot.services.crypto.nobitex import get_crypto_rates_summary
    rates = await get_crypto_rates_summary(force_refresh=force)
    return web.json_response({**rates, "rates": rates})
