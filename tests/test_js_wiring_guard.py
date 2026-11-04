"""CI Guard Test: Prevents JavaScript wiring regressions, dangling function calls,

missing modal IDs, and unguarded settings payload evaluations in the Telegram Mini App.
"""
import re
from pathlib import Path

WEB_DIR = Path("bot/web")
JS_DIR = WEB_DIR / "static" / "js"
TEMPLATES_DIR = WEB_DIR / "templates"
APP_HTML = TEMPLATES_DIR / "app.html"
ADMIN_HTML = TEMPLATES_DIR / "admin.html"


def _get_all_html_ids() -> set[str]:
    ids = set()
    for html_path in [APP_HTML, ADMIN_HTML]:
        if html_path.exists():
            text = html_path.read_text(encoding="utf-8")
            ids.update(re.findall(r'id=["\']([^"\']+)["\']', text))
    return ids


def test_no_dangling_wallet_legacy_functions():
    """Ensure obsolete non-existent functions are not reintroduced in JS code."""
    banned_call_patterns = [
        (r"\bcloseTopupModal\(\)", "Use closeModal('topupModal') instead"),
        (r"\bloadProfileData\(\)", "Use syncUserDataWithApi(window.currentAccountId) instead"),
        (r"\bloadWalletHistory\(\)", "Use renderWalletTransactions() or syncUserDataWithApi() instead"),
    ]

    violations = []
    for js_file in JS_DIR.glob("*.js"):
        content = js_file.read_text(encoding="utf-8")
        for pattern, recommendation in banned_call_patterns:
            matches = list(re.finditer(pattern, content))
            # Exclude fallback definition itself: e.g. function closeTopupModal() or window.closeTopupModal =
            call_matches = [
                m for m in matches
                if not content[max(0, m.start() - 20):m.start()].strip().endswith("function")
                and not content[max(0, m.start() - 20):m.start()].strip().endswith("window.")
            ]
            if call_matches:
                violations.append(
                    f"{js_file.name}: found {len(call_matches)} call(s) matching '{pattern}'. {recommendation}"
                )

    assert not violations, (
        f"Found {len(violations)} dangling legacy function call(s) in JS:\n" + "\n".join(violations)
    )


def test_modals_targeted_exist_in_templates():
    """Ensure every modal opened or closed via openModal/closeModal exists in HTML templates."""
    html_ids = _get_all_html_ids()
    assert html_ids, "HTML templates must contain elements with IDs."

    # Pattern for openModal('xyz') or closeModal('xyz')
    modal_call_pattern = re.compile(r"""(?:openModal|closeModal)\s*\(\s*['"]([a-zA-Z0-9_-]+)['"]\s*\)""")

    missing_modals = []
    for js_file in JS_DIR.glob("*.js"):
        content = js_file.read_text(encoding="utf-8")
        targets = modal_call_pattern.findall(content)
        for target in targets:
            if target not in html_ids:
                missing_modals.append(f"{js_file.name} targets missing modal id='{target}'")

    assert not missing_modals, (
        f"Found {len(missing_modals)} references to nonexistent modal IDs:\n" + "\n".join(missing_modals)
    )


def test_app_modal_ids_exist_in_templates():
    """Ensure every modal listed in APP_MODAL_IDS in app.js exists in the HTML templates."""
    html_ids = _get_all_html_ids()
    app_js_text = (JS_DIR / "app.js").read_text(encoding="utf-8")

    match = re.search(r"const APP_MODAL_IDS\s*=\s*\[(.*?)\];", app_js_text, re.DOTALL)
    assert match, "Could not find APP_MODAL_IDS array in app.js"

    modal_ids = re.findall(r"""['"]([a-zA-Z0-9_-]+)['"]""", match.group(1))
    assert modal_ids, "APP_MODAL_IDS must contain at least one modal ID"

    missing = [m_id for m_id in modal_ids if m_id not in html_ids]
    assert not missing, f"Nonexistent modal IDs in APP_MODAL_IDS: {missing}"


def test_admin_settings_payload_keys_guarded():
    """Ensure settings in admin_settings.js don't unconditionally read missing DOM inputs, preventing DB wipe."""
    admin_settings_js = JS_DIR / "admin_settings.js"
    assert admin_settings_js.exists()
    content = admin_settings_js.read_text(encoding="utf-8")

    admin_html_text = ADMIN_HTML.read_text(encoding="utf-8")
    admin_ids = set(re.findall(r'id=["\']([^"\']+)["\']', admin_html_text))

    # Extract the payload object literal in handleSaveAllSettings (from "const payload = {" to "};")
    start = content.find("const payload = {")
    end = content.find("};", start)
    assert start != -1 and end != -1, "Could not locate payload object literal in handleSaveAllSettings"
    payload_code = content[start:end]

    # Find any unconditionally read input IDs via $('someId')?.value or $('someId').value
    referenced_ids = re.findall(r"\$\(['\"]([^'\"]+)['\"]\)", payload_code)
    unguarded_missing_ids = [el_id for el_id in referenced_ids if el_id not in admin_ids]

    assert not unguarded_missing_ids, (
        f"Found {len(unguarded_missing_ids)} unguarded missing input ID(s) in admin settings payload:\n"
        + "\n".join(unguarded_missing_ids)
        + "\nThese would evaluate to empty string and erase DB settings upon save! Make them conditional."
    )


def test_support_modal_has_fallback_in_app_js():
    """Ensure openSupportContact in app.js has a concrete fallback when support_link is empty."""
    app_js = JS_DIR / "app.js"
    assert app_js.exists()
    content = app_js.read_text(encoding="utf-8")

    assert "window.openSupportModal" in content, "app.js must define window.openSupportModal for support fallback"
    assert "openSupportBtn" in content, "openSupportModal must hook into openSupportBtn"
