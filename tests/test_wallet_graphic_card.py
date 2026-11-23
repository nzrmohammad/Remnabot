"""Test suite for the 3D Holographic User Wallet Card and Currency Switcher."""
import re
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
    assert "writing-mode: vertical-rl;" in content
    assert "preserve-3d" in content


def test_wallet_graphic_card_html_structure():
    """Verify that the 3D card markup and currency switcher exist in app.html."""
    content = APP_HTML_PATH.read_text(encoding="utf-8")
    assert 'class="user-wallet-card-container' in content
    assert 'id="userWalletCardBalance"' in content
    assert 'id="userWalletCardSecondaryBalance"' in content
    assert 'id="userWalletCurrencyBadge"' in content
    assert 'id="userWalletCardVerticalCode"' in content
    assert 'id="userWalletCardName"' in content
    assert 'id="userWalletCardUid"' in content
    assert 'id="userWalletCardCvv"' in content
    assert 'id="userWalletCardTier"' in content
    assert 'id="userCurrencySelector"' in content
    # Legacy compatibility element preserved
    assert 'id="walletTabBalance"' in content
    # Charge & gift buttons preserved
    assert 'id="chargeWalletBtn"' in content
    assert 'openGiftModal' in content


def test_wallet_graphic_card_js_logic():
    """Verify that interactive flipper, code generator, and currency functions exist in wallet.js."""
    content = WALLET_JS_PATH.read_text(encoding="utf-8")
    assert "window.flipUserWalletCard" in content
    assert "window.cycleWalletCurrency" in content
    assert "window.setWalletCurrency" in content
    assert "window.renderUserWalletCard" in content
    assert "generateUserCardVerticalCode" in content
    assert "user_wallet_currency" in content


def test_app_js_wallet_card_integration():
    """Verify that app.js triggers wallet card rendering and syncs preferences."""
    content = APP_JS_PATH.read_text(encoding="utf-8")
    assert "window.renderUserWalletCard" in content
    assert "userCurrencySelector" in content
