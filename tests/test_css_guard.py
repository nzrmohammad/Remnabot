"""CI Guard Test: Prevents CSS regressions, untokenized colors, and unstandardized modals."""
import re
from pathlib import Path

APP_CSS_PATH = Path("bot/web/static/css/app.css")
TOKENS_CSS_PATH = Path("bot/web/static/css/tokens.css")
BASE_CSS_PATH = Path("bot/web/static/css/base.css")
COMPONENTS_CSS_PATH = Path("bot/web/static/css/components.css")
APP_HTML_PATH = Path("bot/web/templates/app.html")
ADMIN_HTML_PATH = Path("bot/web/templates/admin.html")

# Max allowable !important count in app.css (tightened from 45 -> 25 -> 15)
MAX_IMPORTANT_ALLOWANCE = 15

# Modal ID inner-div selectors that are banned in app.css (should use .modal-card instead)
MODAL_ID_DESCENDANT = re.compile(r"html\.theme-light\s+#[a-zA-Z0-9_-]*Modal\s*>\s*div")

# Obsolete ID overrides that were replaced by standardized components (.modal-close-btn, .btn, etc.)
BANNED_ID_OVERRIDES = [
    r"html\.theme-light\s+#closeTopupModalBtn",
    r"html\.theme-light\s+#closeQrModalBtn",
    r"html\.theme-light\s+#closeCheckoutModalBtn",
    r"html\.theme-light\s+#cancelRevokeBtn",
    r"html\.theme-light\s+#cancelCheckoutBtn",
    r"html\.theme-light\s+#gotoShopFromWallet",
    r"html\.theme-light\s+#applyCouponBtn",
    r"html\.theme-light\s+#copyTonCommentBtn",
    r"html\.theme-light\s+#copyTopupCardBtn",
]


def test_app_css_modal_consolidation():
    """Ensure no modal ID descendant hacks are reintroduced in app.css (use .modal-card)."""
    assert APP_CSS_PATH.exists()
    content = APP_CSS_PATH.read_text(encoding="utf-8")
    matches = MODAL_ID_DESCENDANT.findall(content)
    assert not matches, (
        f"Found {len(matches)} individual modal ID descendant rules in app.css!\n"
        f"Use the unified '.modal-card' class instead:\n" + "\n".join(matches)
    )


def test_app_css_banned_id_overrides():
    """Ensure obsolete ID overrides replaced by components are not reintroduced."""
    content = APP_CSS_PATH.read_text(encoding="utf-8")
    violations = []
    for pattern in BANNED_ID_OVERRIDES:
        m = re.findall(pattern, content)
        if m:
            violations.extend(m)
    assert not violations, (
        f"Found banned ID overrides in app.css! Use component classes (.modal-close-btn, .btn, etc.):\n"
        + "\n".join(violations)
    )


def test_app_css_important_count_budget():
    """Ensure !important count does not balloon in app.css (budget tightened to <= 25)."""
    content = APP_CSS_PATH.read_text(encoding="utf-8")
    count = len(re.findall(r"!important\b", content))
    assert count <= MAX_IMPORTANT_ALLOWANCE, (
        f"!important count in app.css is {count}, exceeding tightened budget of {MAX_IMPORTANT_ALLOWANCE}. "
        "Avoid using !important; prefer proper cascade specificity or CSS tokens."
    )


def test_templates_use_modal_card_class():
    """Ensure all modal containers in HTML templates have the .modal-card class."""
    for html_path in [APP_HTML_PATH, ADMIN_HTML_PATH]:
        content = html_path.read_text(encoding="utf-8")
        pattern = re.compile(r'id=["\'](\w+Modal)["\'][^>]*>\s*<div\s+class=["\']([^"\']+)["\']')
        missing = []
        for modal_id, class_list in pattern.findall(content):
            if "storyCardModal" in modal_id:
                continue
            if "modal-card" not in class_list:
                missing.append(f"{html_path.name}: #{modal_id} inner div lacks 'modal-card'")
        assert not missing, "Found modal cards without .modal-card class:\n" + "\n".join(missing)


def test_design_system_core_tokens_and_fonts():
    """Ensure tokens.css and font unicode ranges are properly configured."""
    assert TOKENS_CSS_PATH.exists()
    assert BASE_CSS_PATH.exists()
    assert COMPONENTS_CSS_PATH.exists()

    tokens_content = TOKENS_CSS_PATH.read_text(encoding="utf-8")
    for var in ["--page-bg", "--card-bg", "--card-inner-bg", "--text-main", "--c-accent"]:
        assert var in tokens_content, f"Missing token {var} in tokens.css!"

    base_content = BASE_CSS_PATH.read_text(encoding="utf-8")
    assert "unicode-range" in base_content, "Missing unicode-range splitting in base.css font-face!"
