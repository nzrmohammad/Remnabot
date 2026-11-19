"""Automated tests verifying fixes for Critical, High and DRY audit findings:
1. Stars payment nonce is safely deleted from cache on database exception so Telegram retry succeeds.
2. Runtime ALTER TABLE is banned in user_shop.py.
3. Squad validation in user_shop.py is Fail-Closed.
4. Admin settings API purges tma:user cache.
5. Ban badge in admin_user_bans.py correctly outputs '⛔️ Banned' when lang=='en'.
6. Speedtest.js has monotonic runId and null-safe signal checks.
7. Admin_users.js calls fetchAdminUsers(1) instead of undefined this.loadUsers.
8. Wallet.js cancels crypto invoice via window.api.cancelCryptoInvoice.
9. App.js gift history copy links/codes are safe against quote injection.
10. Admin_charts.js top consumers list escapes username against Stored XSS.
11. Utils.js renderFlagHtml onerror has valid JavaScript syntax without inner quote breakage.
12. Admin.js tab switcher supports tab-admin-tickets for finance data loading.
13. Admin_settings.js cleans up broadcast polling timer.
14. Tokens.css provides --c-border, --font-sans, and --font-mono design tokens.
15. App_settings.py pricing SSOT alignment.
16. App.js and admin_settings.js version synchronization for Karing and Zedsecure.
"""
from pathlib import Path
import pytest
from bot.services.app_settings import StoreSettings


def test_stars_nonce_released_on_error():
    """Verify stars:nonce:{nonce} is deleted from cache on crediting failure."""
    code = Path("bot/handlers/payment_stars.py").read_text(encoding="utf-8")
    assert 'await cache.delete(f"stars:nonce:{nonce}")' in code


def test_user_shop_no_runtime_ddl():
    """Verify no inline ALTER TABLE DDL exists in user_shop.py."""
    code = Path("bot/web/user_shop.py").read_text(encoding="utf-8")
    assert "ALTER TABLE" not in code


def test_user_shop_squad_fail_closed():
    """Verify target squad is validated Fail-Closed."""
    code = Path("bot/web/user_shop.py").read_text(encoding="utf-8")
    assert "valid_squad = False" in code
    assert "if str(target_squad) in squad_uuids:" in code
    assert "if not valid_squad:" in code


def test_admin_settings_cache_purging():
    """Verify admin settings API purges tma:user cache."""
    code = Path("bot/web/admin_settings_api.py").read_text(encoding="utf-8")
    assert 'await cache.delete("tma:user")' in code


def test_admin_user_ban_badge_english():
    """Verify ban_badge respects English language when user is banned."""
    code = Path("bot/handlers/admin_user_bans.py").read_text(encoding="utf-8")
    assert 'ban_badge = "⛔️ مسدود" if lang == "fa" else "⛔️ Banned"' in code


def test_speedtest_safe_controller_and_monotonic_run():
    """Verify speedtest has currentSpeedRunId and safe signal checks."""
    code = Path("bot/web/static/js/speedtest.js").read_text(encoding="utf-8")
    assert "currentSpeedRunId" in code
    assert "!ctrl.signal.aborted" in code


def test_admin_users_reload_fix():
    """Verify admin_users.js invokes fetchAdminUsers(1)."""
    code = Path("bot/web/static/js/admin_users.js").read_text(encoding="utf-8")
    assert "if (typeof fetchAdminUsers === 'function') {" in code
    assert "this.loadUsers(1)" not in code


def test_wallet_crypto_cancel_api():
    """Verify wallet.js calls window.api.cancelCryptoInvoice."""
    code = Path("bot/web/static/js/wallet.js").read_text(encoding="utf-8")
    assert "window.api.cancelCryptoInvoice(invId)" in code


def test_app_gift_copy_safe_attributes():
    """Verify app.js uses data attributes instead of unescaped onclick string interpolation."""
    code = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")
    assert "btn-copy-gift-link" in code
    assert "btn-copy-gift-code" in code
    assert 'onclick="copyToClipboard(\'${shareUrl}\')' not in code


def test_admin_charts_xss_prevention():
    """Verify admin_charts.js escapes usernames in top consumers."""
    code = Path("bot/web/static/js/admin_charts.js").read_text(encoding="utf-8")
    assert "escapeHtml(u.username || '—')" in code


def test_utils_flag_onerror_syntax():
    """Verify renderFlagHtml does not have broken inner single quotes in onerror."""
    code = Path("bot/web/static/js/utils.js").read_text(encoding="utf-8")
    assert "onerror=\"this.outerHTML='<span>${fallback}</span>'\"" in code


def test_admin_tickets_finance_tab_navigation():
    """Verify admin.js tab switcher supports tab-admin-tickets for topups."""
    code = Path("bot/web/static/js/admin.js").read_text(encoding="utf-8")
    assert "targetId === 'tab-admin-finance' || targetId === 'tab-admin-tickets'" in code


def test_admin_settings_broadcast_timer_cleanup():
    """Verify admin_settings.js cleans up broadcastPollTimer."""
    code = Path("bot/web/static/js/admin_settings.js").read_text(encoding="utf-8")
    assert "clearBroadcastPoll()" in code
    assert "broadcastPollTimer = setInterval" in code


def test_tokens_css_defines_required_tokens():
    """Verify tokens.css provides --c-border, --font-sans, and --font-mono."""
    code = Path("bot/web/static/css/tokens.css").read_text(encoding="utf-8")
    assert "--c-border: var(--card-border);" in code
    assert "--font-sans:" in code
    assert "--font-mono:" in code


def test_store_settings_pricing_ssot():
    """Verify StoreSettings default prices match between dataclass and get_store_settings."""
    from bot.services.app_settings import get_store_settings
    code = Path("bot/services/app_settings.py").read_text(encoding="utf-8")
    assert "StoreSettings.custom_plan_price_per_gb" in code
    assert "StoreSettings.custom_plan_price_per_day" in code
    assert "StoreSettings.custom_plan_base_price" in code


def test_app_catalog_versions_synchronized():
    """Verify Karing and Zedsecure versions match between app.js and admin_settings.js."""
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")
    admin_js = Path("bot/web/static/js/admin_settings.js").read_text(encoding="utf-8")

    assert "version: '1.2.26'" in app_js
    assert "version: '1.2.26'" in admin_js
    assert "version: '3.1.8'" in app_js
    assert "version: '3.1.8'" in admin_js
    assert "version: '1.0.38'" not in app_js
    assert "version: '1.0.0'" not in app_js


def test_serve_open_client_schemes():
    """Verify safe_schemes includes modern clients (Karing, v2RayTun, Clash, Shadowrocket, Sub, FlClash)."""
    server_py = Path("bot/web/server.py").read_text(encoding="utf-8")
    for s in ("karing://", "v2raytun://", "clash://", "shadowrocket://", "sub://", "flclash://"):
        assert f'"{s}"' in server_py


def test_bulk_action_rate_limit_path():
    """Verify admin sensitive rate limiting uses hyphenated bulk-action route."""
    server_py = Path("bot/web/server.py").read_text(encoding="utf-8")
    assert '"/api/admin/users/bulk-action"' in server_py
    assert '"/api/admin/users/bulk_action"' not in server_py


def test_admin_topup_fail_closed():
    """Verify post_admin_topup_action requires approved flag."""
    topup_py = Path("bot/web/admin_topups.py").read_text(encoding="utf-8")
    assert 'raw_approved = body.get("approved")' in topup_py
    assert 'if raw_approved is None:' in topup_py


def test_invoice_service_status_icon():
    """Verify invoice service only shows checkmark when is_paid is True."""
    inv_py = Path("bot/services/invoice_service.py").read_text(encoding="utf-8")
    assert "{'✅' if pay.get('is_paid') else '❌'}" in inv_py


def test_wallet_card_admin_fallback():
    """Verify wallet_card.py fallback to ADMIN_IDS executes even if ADMIN_CHAT_ID is set."""
    wc_py = Path("bot/handlers/wallet_card.py").read_text(encoding="utf-8")
    assert "if not delivered and settings.ADMIN_IDS:" in wc_py
    assert "not settings.ADMIN_CHAT_ID and settings.ADMIN_IDS" not in wc_py


def test_icons_js_trim_syntax():
    """Verify icons.js uses trimmed class attribute without syntax leakage."""
    icons_js = Path("bot/web/static/js/icons.js").read_text(encoding="utf-8")
    assert 'class="${classes}"' in icons_js
    assert '".trim()' not in icons_js


def test_admin_html_warning_icon():
    """Verify admin.html references existing warning.svg rather than broken alert.svg."""
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    assert "alert.svg" not in admin_html
    assert "warning.svg" in admin_html

