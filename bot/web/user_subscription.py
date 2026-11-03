"""Subscription configuration endpoints for Telegram Mini App."""
import logging
import urllib.parse

from aiohttp import web

from bot.services.configs import parse_subscription_text
from bot.web.cache import FastCache
from bot.web.user_common import require_user

logger = logging.getLogger(__name__)

COUNTRY_MAP = [
    ("🇩🇪", "آلمان", ["de", "germany", "frankfurt", "berlin"]),
    ("🇳🇱", "هلند", ["nl", "netherlands", "amsterdam"]),
    ("🇫🇮", "فنلاند", ["fi", "finland", "helsinki"]),
    ("🇫🇷", "فرانسه", ["fr", "france", "paris"]),
    ("🇺🇸", "آمریکا", ["us", "usa", "america", "united states", "los angeles", "new york"]),
    ("🇬🇧", "انگلیس", ["gb", "uk", "england", "london", "britain"]),
    ("🇹🇷", "ترکیه", ["tr", "turkey", "istanbul"]),
    ("🇨🇦", "کانادا", ["ca", "canada", "toronto"]),
    ("🇸🇪", "سوئد", ["se", "sweden", "stockholm"]),
    ("🇵🇱", "لهستان", ["pl", "poland", "warsaw"]),
    ("🇨🇭", "سوئیس", ["ch", "switzerland", "zurich"]),
    ("🇦🇪", "امارات", ["ae", "uae", "dubai"]),
    ("🇸🇬", "سنگاپور", ["sg", "singapore"]),
    ("🇮🇷", "ایران", ["ir", "iran", "tehran"]),
]


async def get_user_subscription_configs(request: web.Request) -> web.Response:
    """Fetch parsed individual configs directly via Remnawave API."""
    user_auth, err = require_user(request)
    if err:
        return err

    telegram_id = user_auth.get("id")
    account_id_param = request.query.get("account_id")
    if account_id_param and str(account_id_param).strip().lower() in ("null", "undefined", "none", ""):
        account_id_param = None

    cache: FastCache = request.app["cache"]
    cache_key = f"tma:user:{telegram_id}:configs:{account_id_param or 'def'}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return web.json_response({"ok": True, "configs": cached, "cached": True})

    remnawave = request.app.get("remnawave")
    if not remnawave:
        return web.json_response({"ok": False, "error": "سرویس سرور در دسترس نیست."}, status=503)

    # 1. Fetch user accounts directly from Remnawave API
    try:
        panel_users = await remnawave.get_users_by_telegram_id(telegram_id) or []
    except Exception as exc:
        logger.warning("Error fetching panel users for configs %s: %s", telegram_id, exc)
        panel_users = []

    target = None
    if account_id_param:
        for pu in panel_users:
            pu_short = pu.get("shortUuid") or pu.get("shortId")
            pu_vless = pu.get("vlessUuid") or pu.get("uuid")
            if (
                str(pu.get("id")) == str(account_id_param)
                or (pu_short and str(pu_short) == str(account_id_param))
                or (pu_vless and str(pu_vless) == str(account_id_param))
            ):
                target = pu
                break

    if not target and panel_users:
        target = panel_users[0]

    if not target:
        return web.json_response({
            "ok": True,
            "configs": [],
            "message": "اشتراک فعالی برای این حساب در پنل یافت نشد.",
        })

    # 2. Extract user identifiers for direct Remnawave API
    user_id = target.get("id")
    short_uuid = str(target.get("shortUuid") or target.get("shortId") or target.get("vlessUuid") or "").strip()
    user_uuid = str(target.get("uuid") or "").strip()

    if not short_uuid:
        sub_url = target.get("subscriptionUrl") or target.get("subscription_url") or ""
        if sub_url and "/api/sub/" in sub_url:
            short_uuid = sub_url.split("/api/sub/")[-1].split("?")[0].strip("/")
        elif sub_url and "/" in sub_url:
            path_segments = [p for p in urllib.parse.urlparse(sub_url).path.split("/") if p]
            if path_segments:
                short_uuid = path_segments[-1]

    # 3. Direct Remnawave API call ONLY (no external scraping or fallbacks)
    raw_configs = []
    candidate_ids = [cid for cid in (user_id, user_uuid) if cid is not None and str(cid).strip()]
    for cid in candidate_ids:
        try:
            conn_keys = await remnawave.get_user_connection_keys(
                user_id=cid,
                short_uuid=short_uuid or None,
                user_uuid=user_uuid or None,
            )
            if conn_keys:
                for k in conn_keys:
                    raw_configs.extend(parse_subscription_text(k))
                if raw_configs:
                    logger.info("Direct Remnawave API returned %d configs for user %s", len(raw_configs), cid)
                    break
        except Exception as ck_err:
            logger.warning("Direct Remnawave API connection keys failed (user_id=%s): %s", cid, ck_err)

    configs = []
    for idx, cfg in enumerate(raw_configs, start=1):
        name = cfg.get("name", "").strip()
        proto = cfg.get("protocol", "").lower()
        uri = cfg.get("uri", "")

        flag = "🌐"
        country_name = "سرور"
        name_lower = name.lower()

        # Check existing emoji in name
        for f, c_name, _keywords in COUNTRY_MAP:
            if f in name:
                flag = f
                country_name = c_name
                break
        if flag == "🌐":
            for f, c_name, keywords in COUNTRY_MAP:
                if any(kw in name_lower for kw in keywords):
                    flag = f
                    country_name = c_name
                    break

        configs.append({
            "id": idx,
            "name": name or f"Config #{idx}",
            "protocol": proto,
            "flag": flag,
            "country_name": country_name,
            "uri": uri,
        })

    # Cache for 120 seconds
    if configs:
        await cache.set(cache_key, configs, ttl_seconds=120)
        return web.json_response({"ok": True, "configs": configs})

    return web.json_response({
        "ok": True,
        "configs": [],
        "message": "کانفیگی در پنل رمنانو یافت نشد.",
    })
