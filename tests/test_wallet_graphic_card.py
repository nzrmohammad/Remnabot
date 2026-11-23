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


def test_app_js_wallet_card_integration():
    """Verify that app.js triggers wallet card rendering and syncs preferences."""
    content = APP_JS_PATH.read_text(encoding="utf-8")
    assert "window.renderUserWalletCard" in content
    assert "userCurrencyInput" in content
    assert "userCurrencyDisplay" in content
    assert "settingToggleWalletCardView" in content
    assert "user_wallet_card_view" in content


def test_shop_guidance_toast_and_dns_presets():
    """Verify that shop guidance banner is converted to toast and Quad9 DNS variants are configured."""
    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")
    admin_settings_js = Path("bot/web/static/js/admin_settings.js").read_text(encoding="utf-8")

    # 1. Shop banner converted to toast
    assert "window.showShopGuidanceToast" in shop_js
    assert "showShopGuidanceToast" in app_js
    assert "noticeEl.innerHTML = '<div" not in shop_js

    # 2. Quad9 DNS presets in app.js and admin_settings.js
    for js_code in (app_js, admin_settings_js):
        assert "Quad9" in js_code
        assert "9.9.9.9" in js_code
        assert "https://9.9.9.9/dns-query" in js_code
        assert "dns.quad9.net" in js_code
        assert "2620:fe::fe" in js_code
