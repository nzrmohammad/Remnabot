"""Subscription configuration endpoints for Telegram Mini App."""
import asyncio
import logging
import urllib.parse

from aiohttp import web

from bot.services.configs import parse_subscription_text
from bot.services.formatting import country_name as fmt_country_name
from bot.web.cache import FastCache
from bot.web.user_common import require_user, resolve_tma_lang

logger = logging.getLogger(__name__)

COUNTRY_MAP = [
    ("🇩🇪", "آلمان", "Germany", ["de", "germany", "frankfurt", "berlin"]),
    ("🇳🇱", "هلند", "Netherlands", ["nl", "netherlands", "amsterdam"]),
    ("🇫🇮", "فنلاند", "Finland", ["fi", "finland", "helsinki"]),
    ("🇫🇷", "فرانسه", "France", ["fr", "france", "paris"]),
    ("🇺🇸", "آمریکا", "United States", ["us", "usa", "america", "united states", "los angeles", "new york"]),
    ("🇬🇧", "انگلیس", "United Kingdom", ["gb", "uk", "england", "london", "britain"]),
    ("🇹🇷", "ترکیه", "Turkey", ["tr", "turkey", "istanbul"]),
    ("🇨🇦", "کانادا", "Canada", ["ca", "canada", "toronto"]),
    ("🇸🇪", "سوئد", "Sweden", ["se", "sweden", "stockholm"]),
    ("🇵🇱", "لهستان", "Poland", ["pl", "poland", "warsaw"]),
    ("🇨🇭", "سوئیس", "Switzerland", ["ch", "switzerland", "zurich"]),
    ("🇦🇪", "امارات", "UAE", ["ae", "uae", "dubai"]),
    ("🇸🇬", "سنگاپور", "Singapore", ["sg", "singapore"]),
    ("🇮🇷", "ایران", "Iran", ["ir", "iran", "tehran"]),
]


async def get_user_subscription_configs(request: web.Request) -> web.Response:
    """Fetch parsed individual configs directly via Remnawave API."""
    user_auth, err = require_user(request)
    if err:
        return err

    req_lang = resolve_tma_lang(request)
    is_en = req_lang == "en"
    telegram_id = user_auth.get("id")
    account_id_param = request.query.get("account_id")
    if account_id_param and str(account_id_param).strip().lower() in ("null", "undefined", "none", ""):
        account_id_param = None

    cache: FastCache = request.app["cache"]
    cache_key = f"tma:user:{telegram_id}:configs:{account_id_param or 'def'}"
    lang_cache_key = cache_key if req_lang == "fa" else f"{cache_key}:{req_lang}"
    cached = await cache.get(lang_cache_key)
    if cached is not None:
        return web.json_response({"ok": True, "configs": cached, "cached": True})

    remnawave = request.app.get("remnawave")
    if not remnawave:
        return web.json_response(
            {"ok": False, "error": "Server service unavailable." if is_en else "سرویس سرور در دسترس نیست."},
            status=503,
        )

    # 1. Fetch user accounts directly from Remnawave API with bounded timeout
    panel_fetch_failed = False
    panel_users = []
    try:
        panel_users_raw = await asyncio.wait_for(
            remnawave.get_users_by_telegram_id(telegram_id),
            timeout=6.0,
        )
        if panel_users_raw is None:
            panel_fetch_failed = True
        else:
            # Strictly filter by telegramId to prevent cross-account leakage
            panel_users = [
                u for u in panel_users_raw
                if str(u.get("telegramId") or u.get("telegram_id") or "") == str(telegram_id)
            ]
    except TimeoutError:
        logger.warning("Timeout fetching panel users for configs (telegram_id=%s)", telegram_id)
        panel_fetch_failed = True
    except Exception as exc:
        logger.warning("Error fetching panel users for configs %s: %s", telegram_id, exc)
        panel_fetch_failed = True

    if panel_fetch_failed:
        return web.json_response({
            "ok": False,
            "error": (
                "Could not reach panel server temporarily. Please try again shortly."
                if is_en
                else "ارتباط با پنل سرور موقتاً برقرار نشد. لطفاً چند لحظه دیگر تلاش فرمایید."
            ),
        }, status=503)

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
            "message": "No active subscription found for this account." if is_en else "اشتراک فعالی برای این حساب در پنل یافت نشد.",
        })

    # Strict check: ensure target matches telegram_id
    target_tid = target.get("telegramId") or target.get("telegram_id")
    if str(target_tid or "") != str(telegram_id):
        return web.json_response({
            "ok": True,
            "configs": [],
            "message": "No active subscription found for this account." if is_en else "اشتراک فعالی برای این حساب در پنل یافت نشد.",
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

    # 3. Direct Remnawave API call ONLY (bounded timeout, no external scraping)
    raw_configs = []
    candidate_ids = [cid for cid in (user_id, user_uuid) if cid is not None and str(cid).strip()]
    for cid in candidate_ids:
        try:
            conn_keys = await asyncio.wait_for(
                remnawave.get_user_connection_keys(
                    user_id=cid,
                    short_uuid=short_uuid or None,
                    user_uuid=user_uuid or None,
                ),
                timeout=4.0,
            )
            if conn_keys:
                for k in conn_keys:
                    raw_configs.extend(parse_subscription_text(k))
                if raw_configs:
                    logger.info("Direct Remnawave API returned %d configs for user %s", len(raw_configs), cid)
                    break
        except TimeoutError:
            logger.warning("Timeout calling Remnawave connection keys (user_id=%s)", cid)
        except Exception as ck_err:
            logger.warning("Direct Remnawave API connection keys failed (user_id=%s): %s", cid, ck_err)

    configs = []
    for idx, cfg in enumerate(raw_configs, start=1):
        name = cfg.get("name", "").strip()
        proto = cfg.get("protocol", "").lower()
        uri = cfg.get("uri", "")

        flag = "🌐"
        c_label = "Server" if is_en else "سرور"
        name_lower = name.lower()

        # Check existing emoji in name
        for f, c_fa, c_en, _keywords in COUNTRY_MAP:
            if f in name:
                flag = f
                c_label = c_en if is_en else c_fa
                break
        if flag == "🌐":
            for f, c_fa, c_en, keywords in COUNTRY_MAP:
                if any(kw in name_lower for kw in keywords):
                    flag = f
                    c_label = c_en if is_en else c_fa
                    break
        if flag != "🌐" and c_label in ("Server", "سرور"):
            c_label = fmt_country_name(name, default=c_label, lang=req_lang)

        configs.append({
            "id": idx,
            "name": name or f"Config #{idx}",
            "protocol": proto,
            "flag": flag,
            "country_name": c_label,
            "uri": uri,
        })

    # Cache for 120 seconds
    if configs:
        await cache.set(lang_cache_key, configs, ttl_seconds=120)
        return web.json_response({"ok": True, "configs": configs})

    return web.json_response({
        "ok": True,
        "configs": [],
        "message": "No configs found in Remnawave panel." if is_en else "کانفیگی در پنل رمنانو یافت نشد.",
    })
