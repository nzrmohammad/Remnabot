import pytest
from aiohttp import web
from bot.services.app_settings import StoreSettings, get_store_settings
from bot.services.loyalty import DEFAULT_LOYALTY_TIERS
from bot.web.user_shop import compute_custom_plan_price
from bot.web.admin_infra_api import get_admin_tools_check_host


def test_app_html_profile_card_order_and_arrow():
    with open("bot/web/templates/app.html", "r", encoding="utf-8") as f:
        html = f.read()

    # 1. Identity box comes before profileLoyaltyCard
    idx_identity = html.find("userBoxIdentity")
    idx_loyalty = html.find("profileLoyaltyCard")
    assert idx_identity != -1, "userBoxIdentity not found"
    assert idx_loyalty != -1, "profileLoyaltyCard not found"
    assert idx_identity < idx_loyalty, "userBoxIdentity should be positioned before profileLoyaltyCard"

    # 2. Inward arrow ▶ in loyalty card CTA
    assert "▶</span>" in html

    # 3. Loyalty tiers list container padding
    assert 'id="loyaltyModalTiersList" class="space-y-2 max-h-72 overflow-y-auto px-1.5 py-1"' in html

    # 4. Diamond tier light theme contrast
    assert 'id="loyaltyTierCard_diamond"' in html
    assert 'text-amber-600 dark:text-amber-300' in html

    # 5. Graphical bank card component in app.html
    assert 'id="cardAutoGraphicBox"' in html
    assert 'class="card-graphic-box blu-card-perspective-box' in html


def test_loyalty_service_copy_and_english_pct():
    for tier in DEFAULT_LOYALTY_TIERS:
        if tier["id"] == "silver":
            assert tier["description"] == "3% تخفیف"
        elif tier["id"] == "gold":
            assert tier["description"] == "5% تخفیف"
        elif tier["id"] == "diamond":
            assert "15% تخفیف" in tier["description"]


def test_custom_plan_volume_discount_tiered_calculation():
    # Test tiered discounts with JSON configuration
    st = StoreSettings(
        card_number="",
        card_holder="",
        topup_min_amount=10000,
        default_squad_uuid="",
        expiry_grace_days=3,
        expiry_remind_days="3",
        topic_topups=None,
        topic_orders=None,
        topic_support=None,
        topic_alerts=None,
        support_contact="",
        custom_plan_price_per_gb=2000,
        custom_plan_price_per_day=500,
        custom_plan_base_price=10000,
        custom_plan_volume_tiers_json='[{"min_gb": 50, "max_gb": 99, "discount_percent": 15}, {"min_gb": 100, "max_gb": 999999, "discount_percent": 25}]',
    )

    # 40 GB: 0% discount
    raw, vol_pct, discounted = compute_custom_plan_price(40, 30, st)
    assert vol_pct == 0
    assert raw == discounted == (40 * 2000) + (30 * 500) + 10000

    # 60 GB: 15% discount on traffic
    raw, vol_pct, discounted = compute_custom_plan_price(60, 30, st)
    assert vol_pct == 15
    expected_traffic = int((60 * 2000) * 0.85)
    assert discounted == expected_traffic + (30 * 500) + 10000


@pytest.mark.anyio
async def test_admin_check_host_guarantees_iran_node():
    from unittest.mock import AsyncMock, MagicMock
    from bot.web.admin_infra_api import get_admin_tools_check_host

    app = web.Application()
    app["admin_id"] = 12345
    app["settings"] = None

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("bot.web.routes_admin._check_admin", lambda r: {"id": 12345, "is_admin": True})
        mp.setattr("bot.web.admin_common._check_admin", lambda r: {"id": 12345, "is_admin": True})

        req = MagicMock()
        req.method = "POST"
        req.app = app
        req.json = AsyncMock(return_value={"host": "1.1.1.1", "check_type": "ping", "max_nodes": 6})
        req.query = {}

        resp = await get_admin_tools_check_host(req)
        import json
        data = json.loads(resp.text)
        assert data["ok"] is True
        results = data.get("results", [])
        assert len(results) > 0
        assert any(r.get("flag") == "🇮🇷" or "ایران" in r.get("node_name", "") for r in results)
