"""CI Guard Test: Prevents CSS regressions, untokenized colors, and unstandardized modals."""
import re
from pathlib import Path

APP_CSS_PATH = Path("bot/web/static/css/app.css")
TOKENS_CSS_PATH = Path("bot/web/static/css/tokens.css")
BASE_CSS_PATH = Path("bot/web/static/css/base.css")
COMPONENTS_CSS_PATH = Path("bot/web/static/css/components.css")
APP_HTML_PATH = Path("bot/web/templates/app.html")
ADMIN_HTML_PATH = Path("bot/web/templates/admin.html")

# Max allowable !important count in app.css (tightened from 45 -> 25 -> 15 -> 5; current is 0)
MAX_IMPORTANT_ALLOWANCE = 5

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


def test_css_loading_cascade_order():
    """Ensure stylesheet cascade order in HTML templates is strictly:
    tokens -> base -> tailwind -> components -> app
    This prevents Tailwind utilities from accidentally overriding tokenized components."""
    for html_path in [APP_HTML_PATH, ADMIN_HTML_PATH]:
        content = html_path.read_text(encoding="utf-8")
        tokens_idx = content.find("tokens.css")
        base_idx = content.find("base.css")
        tailwind_idx = content.find("tailwind.min.css")
        components_idx = content.find("components.css")
        app_idx = content.find("app.css")

        assert tokens_idx != -1 and base_idx != -1 and tailwind_idx != -1 and components_idx != -1 and app_idx != -1, (
            f"Missing stylesheet link in {html_path.name}"
        )
        assert tokens_idx < base_idx < tailwind_idx < components_idx < app_idx, (
            f"Incorrect CSS cascade order in {html_path.name}! "
            "Must be tokens.css -> base.css -> tailwind.min.css -> components.css -> app.css"
        )


def _relative_luminance(hex_color: str) -> float:
    """Calculate relative luminance per W3C WCAG 2.1 specification."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    def _gamma(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * _gamma(r) + 0.7152 * _gamma(g) + 0.0722 * _gamma(b)


def test_light_mode_accent_wcag_aa_contrast():
    """Ensure light-theme --c-accent satisfies WCAG AA contrast ratio (>= 4.5:1 against #ffffff)."""
    tokens_content = TOKENS_CSS_PATH.read_text(encoding="utf-8")
    m = re.search(r"html\.theme-light\s*\{[^}]*--c-accent:\s*(#[a-fA-F0-9]{6})", tokens_content)
    assert m, "Could not find html.theme-light --c-accent hex in tokens.css!"
    accent_hex = m.group(1)

    lum_white = 1.0  # #ffffff relative luminance
    lum_accent = _relative_luminance(accent_hex)
    contrast = (lum_white + 0.05) / (lum_accent + 0.05)

    assert contrast >= 4.5, (
        f"Light theme --c-accent ({accent_hex}) contrast ratio against white is {contrast:.2f}:1, "
        "failing WCAG AA minimum of 4.5:1!"
    )
