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
    """Ensure !important count across design system CSS files is strictly within budget (<= 5)."""
    total_important = 0
    for css_path in [APP_CSS_PATH, COMPONENTS_CSS_PATH, BASE_CSS_PATH, TOKENS_CSS_PATH]:
        count = len(re.findall(r"!important\b", css_path.read_text(encoding="utf-8")))
        total_important += count
    assert total_important <= MAX_IMPORTANT_ALLOWANCE, (
        f"Total !important count across design system CSS is {total_important}, "
        f"exceeding tightened budget of {MAX_IMPORTANT_ALLOWANCE}. "
        "Avoid using !important; prefer proper cascade specificity or CSS tokens."
    )


def test_templates_use_modal_card_class():
    """Ensure all modal containers in HTML templates have the exact .modal-card class and no raw dark background."""
    for html_path in [APP_HTML_PATH, ADMIN_HTML_PATH]:
        content = html_path.read_text(encoding="utf-8")
        pattern = re.compile(r'id=["\'](\w+Modal)["\'][^>]*>\s*<div\s+class=["\']([^"\']+)["\']')
        missing = []
        raw_dark_violations = []
        for modal_id, class_list in pattern.findall(content):
            if "storyCardModal" in modal_id:
                continue
            classes = class_list.split()
            if "modal-card" not in classes:
                missing.append(f"{html_path.name}: #{modal_id} inner div lacks exact 'modal-card' token")
            raw_darks = [c for c in classes if c.startswith("bg-[#") or (c.startswith("bg-slate-") and "hover:" not in c)]
            if raw_darks:
                raw_dark_violations.append(f"{html_path.name}: #{modal_id} inner div has raw dark bg: {raw_darks}")
        assert not missing, "Found modal cards without exact .modal-card class:\n" + "\n".join(missing)
        assert not raw_dark_violations, "Found modal cards with raw dark background:\n" + "\n".join(raw_dark_violations)


def test_top_nav_bar_contrast():
    """Ensure top-nav-bar elements in templates do not use raw low-contrast text classes on white."""
    for html_path in [APP_HTML_PATH, ADMIN_HTML_PATH]:
        content = html_path.read_text(encoding="utf-8")
        m = re.search(r'<div[^>]*class=["\'][^"\']*top-nav-bar[^"\']*["\'][\s\S]*?(?=<div[^>]*id=["\'](?:contentArea|adminContentArea)["\'])', content)
        assert m is not None, f"Could not find top-nav-bar section in {html_path.name}!"
        header_html = m.group(0)
        for low_contrast in ["text-blue-300", "text-amber-400", "text-slate-300", "text-indigo-300"]:
            assert low_contrast not in header_html, (
                f"Found low-contrast '{low_contrast}' in header of {html_path.name}; "
                "use semantic tokens (t-accent, t-warn, t-muted, t-success) instead."
            )


def test_safety_umbrella_and_no_broad_cta_overreach():
    """Ensure safety umbrella does not use broad wildcards that force white text on translucent tints."""
    app_css = APP_CSS_PATH.read_text(encoding="utf-8")
    # Banned broad wildcard rules that cause white-on-white on translucent badge tints
    for banned_rule in [
        'html.theme-light [class*="bg-emerald-"]',
        'html.theme-light [class*="bg-blue-"]',
        'html.theme-light [class*="bg-rose-"]',
        'html.theme-light button[class*="bg-"]',
    ]:
        assert banned_rule not in app_css, (
            f"Found banned broad CTA rule '{banned_rule}' in app.css! "
            "This forces white text on translucent tints (e.g. bg-emerald-500/20 text-emerald-400)."
        )

    # Buttons must be explicitly excluded from the umbrella so solid CTAs naturally retain text-white
    assert ':not(button)' in app_css, "Buttons must be excluded from the transitional safety umbrella!"
    # Dark avatar initial must retain white text
    assert 'html.theme-light #profileAvatarInitial' in app_css, "Missing #profileAvatarInitial rule in app.css"


def test_soft_tint_badges_retain_color():
    """Ensure badges with soft tints (e.g. bg-emerald-500/20 text-emerald-400) exist and are untainted."""
    app_html = APP_HTML_PATH.read_text(encoding="utf-8")
    assert 'bg-emerald-500/20 text-emerald-400' in app_html, "Missing expected status badge in app.html"
    assert 'bg-blue-500/15' in app_html, "Missing expected icon container in app.html"
    admin_html = ADMIN_HTML_PATH.read_text(encoding="utf-8")
    assert 'bg-blue-600/20 text-blue-400' in admin_html, "Missing expected filter badge in admin.html"


def test_speedtest_modal_theme_styles():
    """Ensure speedtest modal has active theme rules for #speedTestModal .modal-card."""
    app_css = APP_CSS_PATH.read_text(encoding="utf-8")
    assert 'html.theme-light #speedTestModal .modal-card' in app_css, "Missing #speedTestModal .modal-card in app.css"
    assert '.speedtest-modal-card' not in app_css, "Found dead .speedtest-modal-card selector in app.css"


def test_support_chat_modal_uses_tokenized_surfaces():
    """Ensure supportChatModal does not use hardcoded dark surfaces (bg-[#1a263e]) that break in light theme."""
    content = APP_HTML_PATH.read_text(encoding="utf-8")
    assert 'bg-[#1a263e]' not in content, "Found hardcoded bg-[#1a263e] in app.html; use .card-inset or tokens instead."


def test_semantic_typography_hover_variants():
    """Ensure hover variants for semantic tokens (.hover:t-main, .hover:t-muted) are defined in components.css."""
    components_css = COMPONENTS_CSS_PATH.read_text(encoding="utf-8")
    assert r".hover\:t-main:hover" in components_css, "Missing .hover:t-main:hover in components.css"
    assert r".hover\:t-muted:hover" in components_css, "Missing .hover:t-muted:hover in components.css"


def test_settings_box_text_theme_support():
    """Ensure settings-box headers and bodies support themed text."""
    components_css = COMPONENTS_CSS_PATH.read_text(encoding="utf-8")
    assert ".settings-box-header," in components_css, "Missing settings-box-header rule in components.css"
    app_css = APP_CSS_PATH.read_text(encoding="utf-8")
    assert "html.theme-light .settings-box" in app_css, "Missing settings-box umbrella rule in app.css"


def test_modal_backdrops_use_tokenized_overlay():
    """Ensure modal backdrops in HTML templates use .modal-backdrop instead of hardcoded bg-black/80."""
    for html_path in [APP_HTML_PATH, ADMIN_HTML_PATH]:
        content = html_path.read_text(encoding="utf-8")
        assert "bg-black/80" not in content, f"Found hardcoded bg-black/80 in {html_path.name}; use .modal-backdrop instead."
        assert "bg-black/85" not in content, f"Found hardcoded bg-black/85 in {html_path.name}; use .modal-backdrop instead."


def test_surface_dark_contract():
    """Ensure media cards adhere to the .surface-dark & .on-dark immersive canvas contract."""
    content = APP_HTML_PATH.read_text(encoding="utf-8")
    assert 'id="exportableStoryCard"' in content
    assert 'surface-dark on-dark' in content, "Missing surface-dark on-dark contract in app.html"
    components_css = COMPONENTS_CSS_PATH.read_text(encoding="utf-8")
    assert ".surface-dark," in components_css, "Missing .surface-dark in components.css"
    assert ".on-dark" in components_css, "Missing .on-dark in components.css"


def test_report_card_values_semantic_tokens():
    """Ensure report card values in app.html use high-contrast semantic tokens instead of raw low-contrast classes."""
    content = APP_HTML_PATH.read_text(encoding="utf-8")
    for bad_class in ['id="repNightlyUsed" class="font-mono text-amber-400', 'id="repNightlyRemain" class="font-mono text-emerald-400']:
        assert bad_class not in content, f"Found raw low-contrast class in report cards: {bad_class}"
    for expected_token in ['id="repNightlyUsed" class="font-mono t-warn', 'id="repNightlyRemain" class="font-mono t-success', 'id="repNightlyYesterday" class="font-mono t-accent']:
        assert expected_token in content, f"Missing semantic token in report cards: {expected_token}"


def test_settings_box_no_raw_background_duality():
    """Ensure settings-box elements in templates rely purely on .settings-box without raw bg-slate-800 overrides."""
    for html_path in [APP_HTML_PATH, ADMIN_HTML_PATH]:
        content = html_path.read_text(encoding="utf-8")
        assert 'settings-box bg-slate-800' not in content, (
            f"Found dual system 'settings-box bg-slate-800' in {html_path.name}; "
            "remove raw bg-slate-800 and rely purely on .settings-box component."
        )


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
