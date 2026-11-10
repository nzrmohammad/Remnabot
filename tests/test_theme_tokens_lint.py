"""Phase 3 CI Guard: Automated Token Linter & WCAG AA Contrast Compliance Test.

Enforces zero-regression rules:
1. No raw utility anti-patterns in HTML templates (banned dark hexes, modal bg-black, duality).
2. All headings use semantic .t-main.
3. Mathematical W3C WCAG 2.1 AA contrast verification (>= 4.5:1) for all light theme tokens.
4. CSS line budget (app.css <= 550) and specificity (!important budget <= 5).
"""
import re
from pathlib import Path

TOKENS_CSS_PATH = Path("bot/web/static/css/tokens.css")
BASE_CSS_PATH = Path("bot/web/static/css/base.css")
COMPONENTS_CSS_PATH = Path("bot/web/static/css/components.css")
APP_CSS_PATH = Path("bot/web/static/css/app.css")
APP_HTML_PATH = Path("bot/web/templates/app.html")
ADMIN_HTML_PATH = Path("bot/web/templates/admin.html")

MAX_APP_CSS_LINES = 550
MAX_IMPORTANT_BUDGET = 5


def _relative_luminance(hex_color: str) -> float:
    """Calculate relative luminance per W3C WCAG 2.1 specification."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    def _gamma(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * _gamma(r) + 0.7152 * _gamma(g) + 0.0722 * _gamma(b)


def _contrast_ratio(hex1: str, hex2: str) -> float:
    """Calculate WCAG contrast ratio between two hex colors."""
    l1, l2 = _relative_luminance(hex1), _relative_luminance(hex2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def test_no_banned_raw_utility_anti_patterns_in_templates():
    """Ensure templates do not reintroduce banned raw utilities (bg-black overlays, raw hexes, settings duality)."""
    banned_patterns = [
        (r"\bbg-black/8[05]\b", "Hardcoded dark overlay; use .modal-backdrop instead"),
        (r"\bbg-\[#131d31\]\b", "Raw hex bg; use .top-nav-bar or .bottom-nav-bar instead"),
        (r"\bbg-\[#1a263e\]\b", "Raw hex bg; use .card-inset or tokens instead"),
        (r"settings-box\s+bg-slate-800", "Component duality; settings-box must rely purely on .settings-box component"),
        (r'class="gauge-bg-circle"\s+stroke="#1e293b"', "Hardcoded dark SVG stroke; use var(--gauge-track)"),
        (r'client-import-btn[^"]*\bbg-slate', "Hardcoded dark button; use .card-inset or .btn-secondary"),
        (r'topup-preset-btn[^"]*\bbg-slate', "Hardcoded dark preset button; use .card-inset"),
    ]

    violations = []
    for html_path in [APP_HTML_PATH, ADMIN_HTML_PATH]:
        content = html_path.read_text(encoding="utf-8")
        for pattern, explanation in banned_patterns:
            matches = re.findall(pattern, content)
            if matches:
                violations.append(f"{html_path.name}: Found '{matches[0]}' ({explanation})")

    assert not violations, "Found banned raw utility anti-patterns in HTML templates:\n" + "\n".join(violations)


def test_headings_do_not_hardcode_raw_text_white():
    """Ensure headings (h1-h6) do not use raw text-white; must use semantic .t-main."""
    heading_pattern = re.compile(r"<h[1-6][^>]*class=[\"'][^\"']*\btext-white\b[^\"']*[\"'][^>]*>")
    violations = []
    for html_path in [APP_HTML_PATH, ADMIN_HTML_PATH]:
        content = html_path.read_text(encoding="utf-8")
        for match in heading_pattern.findall(content):
            violations.append(f"{html_path.name}: {match[:80]}")

    assert not violations, (
        f"Found {len(violations)} headings with raw text-white! "
        "Headings must use semantic '.t-main' so they automatically adapt in light mode:\n"
        + "\n".join(violations[:10])
    )


def test_app_css_line_and_specificity_budget():
    """Ensure app.css line count is strictly <= 550 and !important count <= 5 across all CSS files."""
    assert APP_CSS_PATH.exists()
    content = APP_CSS_PATH.read_text(encoding="utf-8")
    line_count = len(content.splitlines())
    assert line_count <= MAX_APP_CSS_LINES, (
        f"app.css has {line_count} lines, exceeding strict budget of {MAX_APP_CSS_LINES} lines! "
        "Keep app.css minimal and DRY."
    )

    total_important = 0
    for css_path in [APP_CSS_PATH, COMPONENTS_CSS_PATH, BASE_CSS_PATH, TOKENS_CSS_PATH]:
        total_important += len(re.findall(r"!important\b", css_path.read_text(encoding="utf-8")))

    assert total_important <= MAX_IMPORTANT_BUDGET, (
        f"Total !important count across design system CSS files is {total_important}, "
        f"exceeding budget of {MAX_IMPORTANT_BUDGET}."
    )


def test_all_semantic_tokens_satisfy_wcag_aa_contrast():
    """Verify that ALL light-mode semantic text & status tokens satisfy WCAG 2.1 AA (>= 4.5:1 against #ffffff)."""
    tokens_content = TOKENS_CSS_PATH.read_text(encoding="utf-8")
    m = re.search(r"html\.theme-light\s*\{([^}]+)\}", tokens_content)
    assert m, "Could not find html.theme-light block in tokens.css!"

    light_block = m.group(1)
    hex_vars = dict(re.findall(r"(--[a-zA-Z0-9_-]+):\s*(#[0-9a-fA-F]{6})", light_block))

    card_bg = hex_vars.get("--card-bg", "#ffffff")
    page_bg = hex_vars.get("--page-bg", "#f1f5f9")
    inset_bg = hex_vars.get("--inset-bg", page_bg)
    required_aa_tokens = [
        "--text-main",
        "--text-muted",
        "--text-subtle",
        "--c-accent",
        "--c-accent-solid",
        "--c-success",
        "--c-warn",
        "--c-danger",
        "--c-info",
        "--c-purple",
        "--c-pink",
    ]

    failed_tokens = []
    for token in required_aa_tokens:
        assert token in hex_vars, f"Missing token {token} in html.theme-light tokens.css!"
        hex_val = hex_vars[token]
        for bg_name, bg_hex in (("card-bg", card_bg), ("page-bg", page_bg), ("inset-bg", inset_bg)):
            ratio = _contrast_ratio(hex_val, bg_hex)
            if ratio < 4.5:
                failed_tokens.append(f"{token} ({hex_val}) on {bg_name} ({bg_hex}): {ratio:.2f}:1 (requires >= 4.5:1)")

    assert not failed_tokens, "The following light mode tokens fail WCAG AA contrast:\n" + "\n".join(failed_tokens)


def test_dark_mode_tokens_wcag_and_halation_protection():
    """Verify Dark Mode semantic tokens meet WCAG AA, include chart tokens, and avoid OLED halation."""
    tokens_content = TOKENS_CSS_PATH.read_text(encoding="utf-8")
    m = re.search(r":root\s*\{([^}]+)\}", tokens_content)
    assert m, "Could not find :root block in tokens.css!"
    dark_block = m.group(1)
    hex_vars = dict(re.findall(r"(--[a-zA-Z0-9_-]+):\s*(#[0-9a-fA-F]{6})", dark_block))

    page_bg = hex_vars["--page-bg"]
    modal_bg = hex_vars["--modal-bg"]
    text_main = hex_vars["--text-main"]

    halation_ratio = _contrast_ratio(text_main, page_bg)
    assert 7.0 <= halation_ratio <= 16.5, (
        f"Dark mode --text-main ({text_main}) on --page-bg ({page_bg}) has contrast {halation_ratio:.2f}:1; "
        "expected calibrated comfort range [7.0, 16.5] to avoid OLED halation."
    )

    for token in ("--text-muted", "--text-subtle", "--c-accent", "--c-success", "--c-warn", "--c-danger", "--c-info", "--c-purple", "--c-pink"):
        assert token in hex_vars, f"Missing {token} in :root tokens.css!"
        for bg_name, bg_hex in (("page-bg", page_bg), ("modal-bg", modal_bg)):
            ratio = _contrast_ratio(hex_vars[token], bg_hex)
            assert ratio >= 4.5, f"Dark {token} ({hex_vars[token]}) on {bg_name} ({bg_hex}): {ratio:.2f}:1 (< 4.5:1)"

    for chart_var in ("--chart-grid", "--chart-tick", "--chart-tooltip-bg", "--chart-tooltip-border", "--chart-tooltip-text"):
        assert tokens_content.count(chart_var) >= 2, f"{chart_var} must be defined for both dark and light themes"


def test_no_dead_dark_prefix_on_custom_tokens_and_calm_cta():
    """Prevent dead dark:t-* utilities in templates/JS and ensure calm accessible CTA contrast."""
    for file_path in [APP_HTML_PATH, ADMIN_HTML_PATH, *Path("bot/web/static/js").glob("*.js")]:
        if file_path.name == "chart.umd.min.js":
            continue
        content = file_path.read_text(encoding="utf-8")
        dead_matches = re.findall(r"dark:t-[\w-]+", content)
        assert not dead_matches, f"Found dead Tailwind dark variant on custom CSS token in {file_path}: {dead_matches}"

    app_css = APP_CSS_PATH.read_text(encoding="utf-8")
    assert "#f59e0b" not in app_css[app_css.find(".btn-plan-bestseller"):app_css.find(".btn-plan-bestseller") + 300], (
        ".btn-plan-bestseller should use high-contrast amber-700/orange-700 gradient instead of low-contrast #f59e0b"
    )
    components_css = COMPONENTS_CSS_PATH.read_text(encoding="utf-8")
    assert "background-color: var(--c-accent-solid);" in components_css, (
        "Primary CTA / active subtabs must use --c-accent-solid instead of glaring neon --c-accent"
    )


def test_surface_dark_rescoping_contract():
    """Ensure .surface-dark and .on-dark components rescop custom properties to light values."""
    components_css = COMPONENTS_CSS_PATH.read_text(encoding="utf-8")
    assert ".surface-dark," in components_css, "Missing .surface-dark in components.css"
    assert ".on-dark" in components_css, "Missing .on-dark in components.css"
    assert "--text-main: #f8fafc" in components_css, "Missing --text-main dark re-scoping in components.css"


def test_bottom_navigation_bars_tokenized():
    """Ensure both user and admin bottom navigation bars are strictly tokenized."""
    components_css = COMPONENTS_CSS_PATH.read_text(encoding="utf-8")
    assert "#navBottom," in components_css and "#adminNavBottom," in components_css, (
        "Missing #navBottom and #adminNavBottom in components.css"
    )
    admin_html = ADMIN_HTML_PATH.read_text(encoding="utf-8")
    assert 'id="adminNavBottom"' in admin_html, "Missing id='adminNavBottom' in admin.html"
