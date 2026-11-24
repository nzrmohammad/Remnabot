"""Test suite for the 3D Holographic User Wallet Card and Currency Switcher."""
from pathlib import Path

COMPONENTS_CSS_PATH = Path("bot/web/static/css/components.css")
APP_HTML_PATH = Path("bot/web/templates/app.html")
WALLET_JS_PATH = Path("bot/web/static/js/wallet.js")
APP_JS_PATH = Path("bot/web/static/js/app.js")


def test_wallet_graphic_card_css_components():
    """Verify that required 3D perspective and card component rules exist in components.css."""
    content = COMPONENTS_CSS_PATH.read_text(encoding="utf-8")
    assert ".user-wallet-card-container" in content
    assert ".user-wallet-card-flipper" in content
    assert ".user-wallet-card-flipper.is-flipped" in content
    assert ".user-wallet-card-face" in content
    assert ".user-wallet-card-front" in content
    assert ".user-wallet-card-back" in content
    assert ".user-wallet-card-sheen" in content
    assert ".user-wallet-chip" in content
    assert ".user-wallet-vertical-code" in content
    assert ".user-wallet-sparkle" in content
    assert ".user-wallet-currency-btn" in content
    # Currency button background must be transparent per user request
    btn_start = content.find(".user-wallet-currency-btn")
    btn_end = content.find("}", btn_start)
    assert btn_start != -1 and btn_end != -1
    btn_block = content[btn_start:btn_end]
    assert "background: transparent" in btn_block or "background-color: transparent" in btn_block
    assert "writing-mode: vertical-rl;" in content
    assert "preserve-3d" in content


def test_wallet_graphic_card_html_structure():
    """Verify that the 3D card markup, classic box, and currency switcher exist in app.html."""
    content = APP_HTML_PATH.read_text(encoding="utf-8")
    assert 'class="user-wallet-card-container' in content
    assert 'id="userWalletGraphicBox"' in content
    assert 'id="userWalletClassicBox"' in content
    assert 'id="userBoxWalletSettings"' in content
    assert 'id="settingToggleWalletCardView"' in content
    assert 'id="classicWalletBalance"' in content
    assert 'id="userWalletCardBalance"' in content
    assert 'id="userWalletCardName"' in content
    assert 'user-wallet-currency-btn' in content  # Dedicated top-right currency switcher button
    assert 'CARD HOLDER' not in content
    assert 'userWalletCardVerticalCode' not in content
    assert 'Remna but lovely' in content
    assert 'classicWalletCurrencyDisplay' in content
    assert 'userWalletColorRow' in content
    assert 'wallet-card-color-swatch' in content
    assert 'id="walletCurrencyModal"' in content
    assert 'id="userCurrencyTriggerBtn"' in content
    assert 'id="userCurrencyInput"' in content
    # Card is strictly LTR front face
    assert 'user-wallet-card-front' in content
    assert 'dir="ltr"' in content
    # Legacy compatibility element preserved
    assert 'id="walletTabBalance"' in content
    # Charge & gift buttons preserved without duplication
    assert content.count('id="chargeWalletBtn"') == 1
    assert 'openGiftModal' in content

    # Profile tab is cleanly nested before navBottom inside contentArea
    tab_profile_pos = content.find('id="tab-profile"')
    nav_bottom_pos = content.find('id="navBottom"')
    content_area_pos = content.find('id="contentArea"')
    assert content_area_pos != -1
    assert tab_profile_pos != -1
    assert nav_bottom_pos != -1
    assert content_area_pos < tab_profile_pos < nav_bottom_pos


def test_wallet_graphic_card_js_logic():
    """Verify that interactive flipper, code generator, view toggle, and currency functions exist in wallet.js."""
    content = WALLET_JS_PATH.read_text(encoding="utf-8")
    assert "window.flipUserWalletCard" in content
    assert "window.toggleWalletCardView" in content
    assert "user_wallet_card_view" in content
    assert "classicWalletBalance" in content
    assert "window.cycleWalletCurrency" in content
    assert "window.setWalletCurrency" in content
    assert "window.openWalletCurrencyModal" in content
    assert "window.closeWalletCurrencyModal" in content
    assert "window.selectWalletCurrency" in content
    assert "window.renderUserWalletCard" in content
    assert "generateUserCardVerticalCode" in content
    assert "user_wallet_currency" in content
    assert "WALLET_CURRENCY_OPTIONS" in content
    assert "'pol'" in content
    assert "'stars'" in content
    assert "USER_WALLET_PALETTES" in content
    assert "window.setUserWalletCardColor" in content
    assert "window.applyUserWalletCardColor" in content
    assert "classicWalletCurrencyDisplay" in content


def test_app_js_wallet_card_integration():
    """Verify that app.js triggers wallet card rendering and syncs preferences."""
    content = APP_JS_PATH.read_text(encoding="utf-8")
    assert "window.renderUserWalletCard" in content
    assert "userCurrencyInput" in content
    assert "userCurrencyDisplay" in content
    assert "settingToggleWalletCardView" in content
    assert "user_wallet_card_view" in content


def test_shop_guidance_toast_and_dns_presets():
    """Verify that shop guidance banner is converted to wide toast and DNS presets are configured."""
    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")
    utils_js = Path("bot/web/static/js/utils.js").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")
    admin_settings_js = Path("bot/web/static/js/admin_settings.js").read_text(encoding="utf-8")

    # 1. Shop banner converted to toast without artificial vertical newline break
    assert "window.showShopGuidanceToast" in shop_js
    assert "showShopGuidanceToast" in app_js
    assert "noticeEl.innerHTML = '<div" not in shop_js
    assert "\\n" not in shop_js.split("showShopGuidanceToast")[1].split("}")[0]
    # utils.js toast allows horizontal width expansion
    assert "w-max max-w-[95%] sm:max-w-xl" in utils_js

    # DNS Categorization and Badges in app.js
    assert "window.setDnsCategory" in app_js
    assert "_currentDnsCategory" in app_js
    assert "DoH" in app_js
    assert "DoT" in app_js

    # 2. Quad9 & Major DNS presets (DoH, DoT, IPv6) in app.js and admin_settings.js
    for js_code in (app_js, admin_settings_js):
        # Quad9
        assert "Quad9" in js_code
        assert "9.9.9.9" in js_code
        assert "https://9.9.9.9/dns-query" in js_code
        assert "dns.quad9.net" in js_code
        assert "2620:fe::fe" in js_code

        # Cloudflare
        assert "Cloudflare (DoH)" in js_code
        assert "https://1.1.1.1/dns-query" in js_code
        assert "Cloudflare (DoT)" in js_code
        assert "one.one.one.one" in js_code
        assert "2606:4700:4700::1111" in js_code

        # Google
        assert "Google (DoH)" in js_code
        assert "https://dns.google/dns-query" in js_code
        assert "Google (DoT)" in js_code
        assert "dns.google" in js_code
        assert "2001:4860:4860::8888" in js_code

        # AdGuard
        assert "AdGuard (DoH)" in js_code
        assert "https://dns.adguard-dns.com/dns-query" in js_code
        assert "AdGuard (DoT)" in js_code

        # Shecan, Electro, Radar Plus
        assert "Shecan (DoH)" in js_code
        assert "https://free.shecan.ir/dns-query" in js_code
        assert "Electro (DoH)" in js_code
        assert "https://elc.elcdn.ir/dns-query" in js_code
        assert "Radar Plus (DoH)" in js_code
        assert "https://dns.radar.game/dns-query" in js_code


def test_periodic_bandwidth_midnight_cache_rollover():
    """Verify that get_periodic_bandwidth_cache_key isolates cache by Tehran date and get_periodic_users_bandwidth avoids serving yesterday's data."""
    import asyncio
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    from bot.web.admin_overview_charts import (
        get_periodic_bandwidth_cache_key,
        get_periodic_users_bandwidth,
    )

    tehran_tz = ZoneInfo("Asia/Tehran")

    # Datetime at 23:59:00 Tehran on Nov 23
    dt_day1 = datetime(2026, 11, 23, 23, 59, 0, tzinfo=tehran_tz)
    # Datetime at 00:01:00 Tehran on Nov 24 (2 minutes later)
    dt_day2 = datetime(2026, 11, 24, 0, 1, 0, tzinfo=tehran_tz)

    key1 = get_periodic_bandwidth_cache_key(dt_day1)
    key2 = get_periodic_bandwidth_cache_key(dt_day2)

    assert "20261123" in key1
    assert "20261124" in key2
    assert key1 != key2

    # Mock cache
    class MockCache:
        def __init__(self):
            self.store = {}
            self.ttls = {}

        async def get(self, key):
            return self.store.get(key)

        async def set(self, key, val, ttl_seconds=300):
            self.store[key] = val
            self.ttls[key] = ttl_seconds

    mock_cache = MockCache()

    async def _runner():
        # Pre-populate day 1 cache
        day1_payload = {
            "tehran_date": "2026-11-23",
            "daily": {"label": "day1"},
            "nightly": {"label": "day0"},
            "weekly": {"label": "w"},
        }
        await mock_cache.set(key1, day1_payload)

        # When querying at day 2 (midnight rollover), key2 misses and cannot return day 1 payload
        res = await get_periodic_users_bandwidth(
            remnawave=None,
            cache=mock_cache,
            panel_users=[],
            now_utc=dt_day2.astimezone(timezone.utc),
        )
        assert res.get("tehran_date") == "2026-11-24"
        assert res != day1_payload
        # Ensure key2 is now cached
        assert key2 in mock_cache.store
        # Check TTL is capped before next midnight
        assert mock_cache.ttls[key2] <= 300

    asyncio.run(_runner())

