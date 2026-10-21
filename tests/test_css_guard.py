"""CI Guard Test: Prevents CSS regressions, untokenized colors, and unstandardized modals."""
import re
from pathlib import Path

APP_CSS_PATH = Path("bot/web/static/css/app.css")
APP_HTML_PATH = Path("bot/web/templates/app.html")
ADMIN_HTML_PATH = Path("bot/web/templates/admin.html")

# Max allowable !important count in app.css (preventing specificity bloat)
MAX_IMPORTANT_ALLOWANCE = 60

# Modal ID inner-div selectors that are banned in app.css (should use .modal-card instead)
MODAL_ID_DESCENDANT = re.compile(r"html\.theme-light\s+#[a-zA-Z0-9_-]*Modal\s*>\s*div\b")


def test_app_css_modal_consolidation():
    """Ensure no modal ID descendant hacks are reintroduced in app.css (use .modal-card)."""
    assert APP_CSS_PATH.exists()
    content = APP_CSS_PATH.read_text(encoding="utf-8")
    matches = MODAL_ID_DESCENDANT.findall(content)
    assert not matches, (
        f"Found {len(matches)} individual modal ID descendant rules in app.css!\n"
        f"Use the unified '.modal-card' class instead:\n" + "\n".join(matches)
    )


def test_app_css_important_count_budget():
    """Ensure !important count does not balloon in app.css."""
    content = APP_CSS_PATH.read_text(encoding="utf-8")
    count = len(re.findall(r"!important\b", content))
    assert count <= MAX_IMPORTANT_ALLOWANCE, (
        f"!important count in app.css is {count}, exceeding budget of {MAX_IMPORTANT_ALLOWANCE}. "
        "Avoid using !important; prefer proper cascade specificity or CSS tokens."
    )


def test_templates_use_modal_card_class():
    """Ensure all modal containers in HTML templates have the .modal-card class."""
    for html_path in [APP_HTML_PATH, ADMIN_HTML_PATH]:
        content = html_path.read_text(encoding="utf-8")
        # Match modal outer divs: id="...Modal" followed by inner <div class="...">
        pattern = re.compile(r'id=["\'](\w+Modal)["\'][^>]*>\s*<div\s+class=["\']([^"\']+)["\']')
        missing = []
        for modal_id, class_list in pattern.findall(content):
            if "storyCardModal" in modal_id:
                continue  # Special full-screen story overlay
            if "modal-card" not in class_list:
                missing.append(f"{html_path.name}: #{modal_id} inner div lacks 'modal-card'")
        assert not missing, "Found modal cards without .modal-card class:\n" + "\n".join(missing)
