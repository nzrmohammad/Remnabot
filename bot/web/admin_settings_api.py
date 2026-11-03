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
            "card_auto_enabled": store_settings.card_auto_enabled,
            "sms_webhook_secret": store_settings.sms_webhook_secret,
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
            "topic_sms_manual": store_settings.topic_sms_manual,
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
            "birthday_custom_message": store_settings.birthday_custom_message,
            "card_blubank_color": store_settings.card_blubank_color,
            "card_graphical_view_enabled": store_settings.card_graphical_view_enabled,
            "card_template": store_settings.card_template,
            "default_squad_uuid": store_settings.default_squad_uuid,
            "join_gate_enabled": store_settings.join_gate_enabled,
            "join_gate_channel": store_settings.join_gate_channel,
            "custom_plan_enabled": store_settings.custom_plan_enabled,
            "custom_plan_price_per_gb": store_settings.custom_plan_price_per_gb,
            "custom_plan_price_per_day": store_settings.custom_plan_price_per_day,
            "custom_plan_base_price": store_settings.custom_plan_base_price,
            "custom_plan_min_gb": store_settings.custom_plan_min_gb,
            "custom_plan_max_gb": store_settings.custom_plan_max_gb,
            "custom_plan_min_days": store_settings.custom_plan_min_days,
            "custom_plan_max_days": store_settings.custom_plan_max_days,
            "custom_plan_volume_tiers_json": store_settings.custom_plan_volume_tiers_json,
            "store_logo_url": store_settings.store_logo_url,
            "loyalty_tiers_json": store_settings.loyalty_tiers_json,
            "invoice_company_name": store_settings.invoice_company_name,
            "timezone": store_settings.timezone,
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
            "card_enabled", "card_auto_enabled", "crypto_enabled", "trial_enabled",
            "referral_enabled", "support_direct_enabled", "maintenance",
            "stars_enabled", "trx_enabled", "xrocket_enabled",
            "card_require_phone_verification", "card_phone_iran_only", "birthday_reward_enabled",
            "card_graphical_view_enabled",
            "join_gate_enabled", "auto_clean_reports", "custom_plan_enabled",
        )
        for bk in bool_keys:
            if bk in body:
                val = "1" if bool(body[bk]) else "0"
                await app_repo.set(bk, val)

        # Numeric / string settings
        raw_keys = (
            "card_number", "card_holder", "sms_webhook_secret", "topup_min_amount", "topup_max_amount",
            "usdt_rate_toman", "eur_rate_toman", "ton_rate_toman", "ton_wallet_address",
            "trx_rate_toman", "trx_wallet_address", "xrocket_api_key",
            "stars_rate_toman",
            "trial_traffic_gb", "trial_duration_days",
            "referral_reward_gb", "support_contact",
            "topic_topups", "topic_orders", "topic_support", "topic_alerts", "topic_backups", "topic_reports", "topic_nodes", "topic_crypto", "topic_errors", "topic_sms_manual",
            "access_mode", "default_squad_uuid",
            "tutorial_channel_url", "routing_tutorial_url", "client_apps_json",
            "birthday_reward_traffic_gb", "birthday_reward_discount_percent",
            "birthday_custom_message", "card_blubank_color", "card_template",
            "join_gate_channel",
            "custom_plan_price_per_gb", "custom_plan_price_per_day", "custom_plan_base_price",
            "custom_plan_min_gb", "custom_plan_max_gb", "custom_plan_min_days", "custom_plan_max_days",
            "store_logo_url", "loyalty_tiers_json", "custom_plan_volume_tiers_json", "invoice_company_name",
            "timezone",
        )
        for rk in raw_keys:
            if rk in body:
                v = body[rk]
                if v is None:
                    continue
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)
                await app_repo.set(rk, str(v).strip())

        if "timezone" in body and body["timezone"]:
            try:
                from zoneinfo import ZoneInfo
                tz_cand = str(body["timezone"]).strip()
                ZoneInfo(tz_cand)
                settings_cfg = request.app.get("settings")
                if settings_cfg:
                    settings_cfg.TIMEZONE = tz_cand
            except Exception as tz_err:
                logger.warning("Invalid timezone submitted: %s", tz_err)

        if "topic_errors" in body:
            try:
                from bot.services.error_reporter import update_cached_topic_errors
                te_val = body.get("topic_errors")
                if te_val is not None and str(te_val).strip().isdigit():
                    update_cached_topic_errors(int(str(te_val).strip()))
            except Exception:
                pass

        # Invalidate cached settings
        cache = request.app.get("cache")
        if cache:
            await cache.delete("store_settings")
            await cache.delete("tma:admin:overview")

        sensitive_keys = {"sms_webhook_secret", "ton_wallet_address", "trx_wallet_address", "xrocket_api_key"}
        safe_keys = [k for k in body.keys() if k not in sensitive_keys]
        has_secret_change = any(k in body for k in sensitive_keys)
        logger.info(
            "Admin settings updated: admin_id=%s keys=%s sensitive_changed=%s",
            admin.get("id"), safe_keys, has_secret_change,
        )

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


async def post_admin_upload_store_logo(request: web.Request) -> web.Response:
    """Upload and set store logo image."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    img_bytes = None
    ext = "png"

    if request.content_type.startswith("application/json"):
        try:
            body = await request.json()
            logo_data = body.get("logo_image") or ""
            if "base64," in logo_data:
                header, b64_data = logo_data.split("base64,", 1)
                if "jpeg" in header or "jpg" in header:
                    ext = "jpg"
                elif "webp" in header:
                    ext = "webp"
                import base64
                img_bytes = base64.b64decode(b64_data)
        except Exception as e:
            return web.json_response({"ok": False, "error": f"Invalid image payload: {e}"}, status=400)
    elif request.content_type.startswith("multipart/form-data"):
        try:
            reader = await request.multipart()
            while True:
                part = await reader.next()
                if part is None:
                    break
                if part.name == "file":
                    fn = (part.filename or "").lower()
                    if fn.endswith(".jpg") or fn.endswith(".jpeg"):
                        ext = "jpg"
                    elif fn.endswith(".webp"):
                        ext = "webp"
                    img_bytes = await part.read()
                    break
        except Exception as e:
            return web.json_response({"ok": False, "error": f"Upload error: {e}"}, status=400)

    if not img_bytes:
        return web.json_response({"ok": False, "error": "هیچ تصویری دریافت نشد."}, status=400)

    if len(img_bytes) > 5 * 1024 * 1024:
        return web.json_response({"ok": False, "error": "حجم تصویر نباید بیشتر از ۵ مگابایت باشد."}, status=400)

    import asyncio
    from pathlib import Path
    dest_dir = Path("bot/web/static/img")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f"store_logo.{ext}"

    def _write_file():
        with open(dest_file, "wb") as f:
            f.write(img_bytes)

    await asyncio.to_thread(_write_file)

    import time
    logo_url = f"/static/img/store_logo.{ext}?v={int(time.time())}"

    async with db_session(request) as session:
        app_repo = AppSettingRepository(session)
        await app_repo.set("store_logo_url", logo_url)
        cache = request.app.get("cache")
        if cache:
            await cache.delete("store_settings")
        session.add(
            AdminLog(
                admin_id=admin["id"],
                action="upload_store_logo",
                detail=f"آپلود لوگوی جدید فروشگاه: {logo_url}",
            )
        )
        await session.commit()

    return web.json_response({"ok": True, "logo_url": logo_url, "message": "لوگو با موفقیت ذخیره شد."})
