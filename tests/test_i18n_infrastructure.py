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

    req_me = make_mocked_request("GET", "/api/me?user_id=91919", app=app)
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
    assert "txDateDisplay" in wallet_js and "txUnitLabel" in wallet_js
    lang_en_btn = re.search(r'<button[^>]*id="langEnBtn"[^>]*>', app_html)
    assert lang_en_btn and "t-muted hover:t-main" in lang_en_btn.group(0)
    assert bundle_path.is_file() and "applyAppLocale" in bundle_path.read_text(encoding="utf-8")
