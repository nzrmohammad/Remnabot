"""Regression and architectural tests for Section 4 i18n infrastructure."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import make_mocked_request

from bot.db.models import Order, OrderStatus, User, Wallet
from bot.locales.en import EN_TEXTS
from bot.locales.fa import FA_TEXTS
from bot.locales.texts import (
    CHOOSE_LANGUAGE,
    INVITE_ONLY_NOTICE,
    MAINTENANCE_NOTICE,
    normalize_lang,
    t,
)
from bot.services.formatting import country_name, format_date
from bot.services.wallet_history import fetch_user_transactions
from bot.web.cache import FastCache


def test_locales_parity_normalization_and_safe_formatting():
    """Verify 100% key and placeholder parity, BCP-47 normalization, and safe format fallback."""
    fa_keys = set(FA_TEXTS.keys())
    en_keys = set(EN_TEXTS.keys())
    assert fa_keys == en_keys, f"Key mismatch: fa-en={fa_keys - en_keys}, en-fa={en_keys - fa_keys}"

    ph_re = re.compile(r"\{([a-zA-Z0-9_]+)\}")
    for key in sorted(fa_keys):
        assert set(ph_re.findall(FA_TEXTS[key])) == set(ph_re.findall(EN_TEXTS[key])), key

    assert normalize_lang(None) == "fa"
    assert normalize_lang("") == "fa"
    assert normalize_lang("fa-IR") == "fa"
    assert normalize_lang("FA") == "fa"
    assert normalize_lang("en") == "en"
    assert normalize_lang("en-US") == "en"
    assert normalize_lang("en_GB") == "en"
    assert normalize_lang("de") == "fa"

    # Normalized BCP-47 lookup & safe formatting without KeyError
    assert t("en-US", "not_authorized") == EN_TEXTS["not_authorized"]
    assert isinstance(t("en", "stats_days_left"), str)  # Missing kwargs must not raise KeyError

    # Pre-onboarding/system notices are bilingual
    for notice in (CHOOSE_LANGUAGE, MAINTENANCE_NOTICE, INVITE_ONLY_NOTICE):
        assert re.search(r"[A-Za-z]{4,}", notice)
        assert re.search(r"[\u0600-\u06FF]{4,}", notice)


def test_localized_country_names_and_dates():
    """Country names and date formatting adapt cleanly between Persian and English."""
    assert country_name("DE", lang="fa") == "آلمان"
    assert country_name("DE", lang="en-US") == "Germany"
    assert country_name("germany", lang="en") == "Germany"

    sample_dt = datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc)
    assert format_date(sample_dt, "en-US") == "2026-03-21"
    assert format_date(sample_dt, "fa-IR").startswith("1405/01/01")


@pytest.mark.anyio
async def test_wallet_history_and_miniapp_language_api_localization(session_factory):
    """Language updates persist normalized locale and localize /api/me transactions."""
    from bot.web.routes_user import get_user_me
    from bot.web.user_nodes import post_user_settings

    async with session_factory() as session:
        session.add(User(telegram_id=91919, username="en_user", full_name="English User", language="fa"))
        await session.flush()
        session.add(Wallet(telegram_id=91919, balance=150_000))
        session.add(
            Order(
                telegram_id=91919,
                service_name="Pro Plan",
                traffic_gb=50,
                duration_days=30,
                amount=120_000,
                status=OrderStatus.PAID,
            )
        )
        await session.commit()

        en_tx = await fetch_user_transactions(session, 91919, "Asia/Tehran", lang="en-US")
        fa_tx = await fetch_user_transactions(session, 91919, "Asia/Tehran", lang="fa")
        assert en_tx[0]["status"] == "Paid"
        assert en_tx[0]["title"] == "Purchase Pro Plan"
        assert "Toman" in en_tx[0]["amount_formatted"]
        assert re.match(r"^\d{4}-\d{2}-\d{2} - \d{2}:\d{2}$", en_tx[0]["date_formatted"])
        assert fa_tx[0]["status"] == "موفق"
        assert "تومان" in fa_tx[0]["amount_formatted"]

    app = {
        "bot_token": "123:abc",
        "admin_ids": [55555],
        "is_dev": True,
        "session_factory": session_factory,
        "cache": FastCache(redis_client=None),
        "remnawave": AsyncMock(get_users_by_telegram_id=AsyncMock(return_value=[])),
        "settings": MagicMock(TIMEZONE="Asia/Tehran"),
    }

    req_set = make_mocked_request("POST", "/api/user/settings?user_id=91919", app=app)
    req_set.json = AsyncMock(return_value={"language": "en-US"})
    resp_set = await post_user_settings(req_set)
    assert resp_set.status == 200
    assert json.loads(resp_set.text)["language"] == "en"

    req_me = make_mocked_request("GET", "/api/me?user_id=91919", headers={"X-App-Language": "fa"}, app=app)
    resp_me = await get_user_me(req_me)
    assert resp_me.status == 200
    me_data = json.loads(resp_me.text)["data"]
    assert me_data["user"]["language"] == "en"
    assert me_data["transactions"][0]["status"] == "Paid"


def test_frontend_i18n_runtime_and_bundle_integration():
    """Verify frontend i18n module, HTML hooks, wallet renderer, and build order stay wired."""
    i18n_js = Path("bot/web/static/js/i18n.js").read_text(encoding="utf-8")
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")
    wallet_js = Path("bot/web/static/js/wallet.js").read_text(encoding="utf-8")
    build_mjs = Path("scripts/build_assets.mjs").read_text(encoding="utf-8")
    bundle_path = Path("bot/web/static/js/dist/user.bundle.min.js")

    assert "function applyAppLocale" in i18n_js
    assert "remna_user_lang" in app_html
    assert '<script src="/static/js/i18n.js" defer></script>' in app_html
    assert "'i18n.js'" in build_mjs
    assert "window.applyAppLocale" in app_js
    assert "window.lastUserData.user.language = appliedLang" in app_js
    assert "syncUserDataWithApi(window.currentAccountId, { refresh: true })" in app_js
    assert "txDateDisplay" in wallet_js and "txUnitLabel" in wallet_js
    lang_en_btn = re.search(r'<button[^>]*id="langEnBtn"[^>]*>', app_html)
    assert lang_en_btn and "t-muted hover:t-main" in lang_en_btn.group(0)
    assert bundle_path.is_file() and "applyAppLocale" in bundle_path.read_text(encoding="utf-8")


def test_app_html_i18n_attributes_and_boot_locale():
    """Every app.html data-i18n* attribute must have an I18N_EN key and boot must not auto-switch via language_code."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    i18n_js = Path("bot/web/static/js/i18n.js").read_text(encoding="utf-8")

    html_keys = set(
        re.findall(r'data-i18n(?:-(?:html|placeholder|title|aria))?="([^"]+)"', app_html)
    )
    assert len(html_keys) >= 500

    # Extract declared keys in I18N_EN block
    en_match = re.search(r"const I18N_EN = \{(.*?)\n  \};", i18n_js, re.S)
    assert en_match, "I18N_EN dictionary not found in i18n.js"
    en_keys = set(re.findall(r"^\s*([A-Za-z0-9_]+)\s*:", en_match.group(1), re.M))

    missing = sorted(html_keys - en_keys)
    assert not missing, f"app.html references missing I18N_EN keys: {missing[:20]}"

    # Selector map keys must also resolve in I18N_EN
    sel_match = re.search(r"const SELECTOR_I18N_MAP = \[(.*?)\n  \];", i18n_js, re.S)
    assert sel_match
    sel_keys = set(re.findall(r",\s*'([^']+)'\]", sel_match.group(1)))
    assert not (sel_keys - en_keys)

    # Boot <head> inline script must preserve default 'fa' / explicit remna_user_lang without reading language_code
    head_boot = app_html.split("</head>", 1)[0]
    assert "language_code" not in head_boot


def test_backend_en_localization_helpers():
    """Loyalty and Smart Renewal Advisor helpers must localize cleanly when lang='en'."""
    from bot.services.engagement_service import compute_renewal_advisor
    from bot.services.loyalty import localize_loyalty_data

    fa_loyalty = {
        "enabled": True,
        "tier_id": "gold",
        "name": "طلایی",
        "discount_percent": 10,
        "next_tier": {"id": "platinum", "name": "پلاتینیوم", "discount_percent": 15},
        "all_tiers": [
            {"id": "bronze", "name": "برنزی", "discount_percent": 0},
            {"id": "diamond", "name": "الماس", "discount_percent": 25},
        ],
    }
    en_loyalty = localize_loyalty_data(fa_loyalty, lang="en-US")
    assert en_loyalty["name"] == "Gold"
    assert en_loyalty["description"] == "10% discount"
    assert en_loyalty["next_tier"]["name"] == "Platinum"
    assert en_loyalty["all_tiers"][1]["description"] == "25% discount + Priority Support"
    assert localize_loyalty_data(fa_loyalty, lang="fa")["name"] == "طلایی"

    en_advisor = compute_renewal_advisor(
        {"avg_daily_gb": 2.0, "status": "fast", "days_left_plan": 5},
        {"traffic_remaining_gb": 4.0},
        lang="en",
    )
    assert "Prevent Early Depletion" in en_advisor["title"]
    assert "GB" in en_advisor["summary"]
    assert not re.search(r"[\u0600-\u06FF]", en_advisor["summary"])

    fa_advisor = compute_renewal_advisor(
        {"avg_daily_gb": 2.0, "status": "fast", "days_left_plan": 5},
        {"traffic_remaining_gb": 4.0},
        lang="fa",
    )
    assert re.search(r"[\u0600-\u06FF]", fa_advisor["summary"])


def test_bilingual_ui_regression_fixes():
    """Verify EN/FA visual layout, dynamic field preservation, TON default, and modal LTR contracts."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    i18n_js = Path("bot/web/static/js/i18n.js").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")
    wallet_js = Path("bot/web/static/js/wallet.js").read_text(encoding="utf-8")
    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")
    admin_panel_js = Path("bot/web/static/js/admin_panel.js").read_text(encoding="utf-8")

    # 1. Dynamic fields never wiped by static i18n selectors/attributes
    assert "#headerUsername" not in i18n_js
    for dyn_id in ('id="profilePhone"', 'id="profileBirthDate"', 'id="profileSubStatus"', 'id="loyaltyTierName"'):
        idx = app_html.find(dyn_id)
        assert idx != -1
        tag = app_html[app_html.rfind("<", 0, idx):app_html.find(">", idx)]
        assert "data-i18n=" not in tag, f"Dynamic element {dyn_id} must not declare data-i18n="
    assert app_js.find("window.applyAppLocale") < app_js.find("// --- PHASE 1:")

    # 2. Removed Customize alerts subtitle
    assert "settings_section_sub" not in app_html
    assert "settings_section_sub" not in i18n_js

    # 3. Settings rows use logical flex gap instead of directional ml-1.5
    settings_slice = app_html[app_html.find("<!-- 2. Box: هشدارهای تلگرام"):app_html.find('id="userWalletColorRow"')]
    assert "ml-1.5" not in settings_slice

    # 4. Support chat Send and Shop Coupon Apply stay anchored on right side
    chat_bar_idx = app_html.find('id="sendMessageBtn"')
    assert 'dir="rtl"' in app_html[chat_bar_idx - 160:chat_bar_idx]
    coupon_bar_idx = app_html.find('id="applyCouponBtn"')
    assert 'dir="rtl"' in app_html[coupon_bar_idx - 160:coupon_bar_idx]

    # 5. Default wallet display currency is Ton in EN and Toman in FA
    assert "window.getDefaultWalletCurrency" in wallet_js and "_wIsEn() ? 'ton' : 'toman'" in wallet_js
    assert "window.getEffectiveWalletCurrency" in wallet_js and "window.getEffectiveWalletCurrency()" in app_js

    # 6. Monthly report localizes Persian month names; sessions keep number before devices; country breakdown places country left / volume right
    assert "toLocalizedMonthName(mNameRaw)" in app_js
    assert "repSessionsBadge.dir = isEn ? 'ltr' : 'rtl'" in app_js
    assert '<div class="flex justify-between items-center text-xs" dir="ltr">' in app_js

    # 7. Modals use logical end-* close buttons and #walletCurrencyModal / #configsModal are not text-right/pl-10
    assert "modal-close-btn absolute top-3.5 left-3.5" not in app_html
    assert "modal-close-btn absolute top-3 left-3" not in app_html
    cur_modal = app_html[app_html.find('id="walletCurrencyModal"'):app_html.find('id="expiryCountdownModal"')]
    assert "text-right" not in cur_modal and "pl-10" not in cur_modal

    # 8. Shop custom badges & EN card header, Wallet TX left icon, Hosts pagination LTR prev/next
    assert 'data-i18n="custom_vol_badge_lbl"' in app_html
    assert 'data-i18n="custom_loyalty_badge_lbl"' in app_html
    assert "const cardHeaderHtml = isEn ?" in shop_js
    assert "${iconHtml}<bdi class=\"font-bold select-all\">" in wallet_js
    assert "paginationEl.setAttribute('dir', 'ltr')" in admin_panel_js
    assert 'aria-label="قبلی"' in admin_panel_js and admin_panel_js.find("M15 19l-7-7 7-7") < admin_panel_js.find("M9 5l7 7-7 7")
