"""Subscription configuration endpoints for Telegram Mini App."""
import logging
import urllib.parse

from aiohttp import web
from sqlalchemy import select

from bot.db.models import Order
from bot.services.configs import fetch_subscription_configs, parse_subscription_text
from bot.web.cache import FastCache
from bot.web.user_common import db_session, require_user

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
    """Fetch parsed individual configs from the user's active subscription."""
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
    session_factory = request.app.get("session_factory")
    if not session_factory or not remnawave:
        return web.json_response({"ok": False, "error": "سرویس سرور در دسترس نیست."}, status=503)

    sub_url = ""
    settings = request.app.get("settings")
    base_remna = (getattr(settings, "REMNAWAVE_BASE_URL", "") or getattr(settings, "REMNAWAVE_URL", "")).strip() if settings else ""

    async with db_session(request) as session:
        # 1. Fetch user accounts from Remnawave
        try:
            panel_users = await remnawave.get_users_by_telegram_id(telegram_id) or []
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

            if target:
                sub_url = target.get("subscriptionUrl") or target.get("subscription_url") or ""
                target_sub_id = target.get("shortUuid") or target.get("vlessUuid") or target.get("uuid") or target.get("shortId")
                if not sub_url and target_sub_id and base_remna:
                    sub_url = f"{base_remna.rstrip('/')}/api/sub/{target_sub_id}"
                elif sub_url and sub_url.startswith("/") and base_remna:
                    sub_url = urllib.parse.urljoin(base_remna, sub_url)
        except Exception as exc:
            logger.warning("Error fetching panel users for configs %s: %s", telegram_id, exc)

        # Fallback to Order table if not in panel response
        if not sub_url:
            order_res = await session.execute(
                select(Order.subscription_url).where(
                    Order.telegram_id == telegram_id,
                    Order.subscription_url.isnot(None),
                ).order_by(Order.id.desc()).limit(1)
            )
            sub_url = order_res.scalar_one_or_none() or ""

    if not sub_url:
        return web.json_response({
            "ok": True,
            "configs": [],
            "message": "اشتراک فعالی برای این حساب یافت نشد.",
        })

    # Download and parse configs: Try direct Remnawave internal fetch first
    raw_configs = []
    sub_token = ""
    if target:
        sub_token = str(target.get("shortUuid") or target.get("uuid") or target.get("shortId") or target.get("vlessUuid") or "").strip()
    if not sub_token and sub_url:
        parsed_sub = urllib.parse.urlparse(sub_url)
        path_segments = [p for p in parsed_sub.path.split("/") if p]
        if path_segments:
            sub_token = path_segments[-1]

    if sub_token and hasattr(remnawave, "_client"):
        for sub_ep in (f"/api/sub/{sub_token}", f"/sub/{sub_token}"):
            try:
                resp = await remnawave._client.get(
                    sub_ep,
                    headers={"User-Agent": "v2rayNG/1.8.5", "Accept": "*/*"},
                    timeout=4.0,
                )
                if resp.status_code == 200 and resp.text.strip():
                    body = resp.text.strip()
                    if not body.lower().startswith(("<!doctype", "<html")):
                        raw_configs = parse_subscription_text(body)
                        if raw_configs:
                            logger.info("Successfully fetched %d configs directly from Remnawave internal %s", len(raw_configs), sub_ep)
                            break
            except Exception as direct_exc:
                logger.debug("Direct internal subscription fetch failed on %s: %s", sub_ep, direct_exc)

    # Fallback to general fetcher if direct fetch was empty
    if not raw_configs and sub_url:
        raw_configs = await fetch_subscription_configs(sub_url)

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

    # Cache for 60 seconds
    if configs:
        await cache.set(cache_key, configs, ttl_seconds=60)

    return web.json_response({"ok": True, "configs": configs})
