from pathlib import Path


def test_invoice_service_logo_multiple_candidate_paths():
    """Invoice service should search multiple candidate paths to find local store logo."""
    content = Path("bot/services/invoice_service.py").read_text(encoding="utf-8")
    assert "candidate_paths = [" in content
    assert "base_dir / clean_path" in content


def test_invoice_logo_and_icon_wiring():
    """Invoice in TMA should support graceful logo onerror fallback and RTL left-positioned icon."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")

    # In app.html, invItemTitle is followed by invItemIcon in RTL flex row (so icon is visually on the left)
    assert '<b id="invItemTitle" class="t-main text-xs">بسته اشتراک</b>' in app_html
    assert '<span id="invItemIcon" class="text-xs shrink-0">📦</span>' in app_html

    # In app.js, onerror fallback and icon mapping exist
    assert "logoImg.onerror = () => {" in app_js
    assert "$('invItemIcon')" in app_js
    assert "icon = '🥇'" in app_js
    assert "icon = '🥉'" in app_js


def test_card_number_light_theme_visibility():
    """Card numbers must not have hardcoded white text overriding light theme."""
    wallet_js = Path("bot/web/static/js/wallet.js").read_text(encoding="utf-8")
    comp_css = Path("bot/web/static/css/components.css").read_text(encoding="utf-8")

    # wallet.js renderBluCardNumber checks isGraphic
    assert "const isGraphic = el.id === 'graphicCardNumberDisplay'" in wallet_js
    # regular DOM elements get pure spans without hardcoded white
    assert 'el.innerHTML = `<span class="tracking-wide font-black">${clean.slice(0, 4)}</span>' in wallet_js

    # components.css styles light mode card number with bold dark color
    assert "html.theme-light #topupCardNumber" in comp_css
    assert "html.theme-light #cardAutoCardNumber" in comp_css


def test_gift_modal_bidi_and_palette():
    """Gift modal must have clean BiDi placeholder with LRM and no broken hover:text-white."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")

    # Placeholder uses LRM to keep 'یا' strictly between username and number
    assert 'placeholder="username &lrm;یا&lrm; 123456789"' in app_html

    # Inactive buttons do not have hover:text-white
    assert 't-muted hover:t-main' in app_html

    # app.js also uses tokenized classes
    assert "t-muted hover:t-main" in app_js


def test_loyalty_modal_typography():
    """Loyalty discount numbers should use Vazirmatn (font-sans) instead of system font-mono."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")

    # In app.html, tier percentages use font-sans num-bidi
    assert 'id="loyaltyTierCard_silver_pct" class="text-emerald-500 font-bold font-sans num-bidi"' in app_html
    assert 'id="loyaltyTierCard_gold_pct" class="text-emerald-500 font-bold font-sans num-bidi"' in app_html

    # In app.js, current discount and all_tiers use font-sans
    assert '<span class="font-sans font-bold num-bidi"' in app_js


def test_kill_all_sessions_dedicated_modal():
    """Active sessions kill all action must have a dedicated confirmation modal."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")

    assert 'id="killAllSessionsModal"' in app_html
    assert 'id="confirmKillAllSessionsBtn"' in app_html
    assert 'window.openKillAllSessionsModal' in app_html
    assert "'killAllSessionsModal'" in app_js
    assert "function openKillAllSessionsModal()" in app_js
    assert "function confirmKillAllSessions()" in app_js


def test_bestseller_badge_and_button_gradient():
    """Bestseller button must have matching warm amber-orange gradient and detect Persian badge."""
    app_css = Path("bot/web/static/css/app.css").read_text(encoding="utf-8")
    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")

    # app.css has amber-orange gradient
    assert ".btn-plan-bestseller {" in app_css
    assert "linear-gradient(135deg, #f59e0b 0%, #ea580c 100%)" in app_css

    # shop.js handles bestseller with Persian word
    assert "planBadgeKey.includes('پرفروش')" in shop_js


def test_custom_plan_price_breakdown_label():
    """Custom plan breakdown must display percent in the label and value strictly as minus amount."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")

    assert 'id="customPlanDiscountPct"' in app_html
    assert 'تخفیف باشگاه مشتریان شما (<span id="customPlanDiscountPct">0</span>%):' in app_html
    assert 'تخفیف پلکانی حجم انتخابی (<span id="customPlanVolumeTierPct">0</span>%):' in app_html

    # In shop.js, loyalty percentage is set to label element and not suffixed onto value
    assert "const discPctEl = document.getElementById('customPlanDiscountPct');" in shop_js
    assert "if (discPctEl) discPctEl.innerText = loyaltyPct;" in shop_js


def test_delete_plan_modal_icon_placement():
    """In admin plan delete confirmation modal, the icon is placed to the left of the name."""
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    admin_plans = Path("bot/web/static/js/admin_plans.js").read_text(encoding="utf-8")

    assert '<span id="deletePlanModalName" class="text-sm font-bold t-main truncate">نام تعرفه</span>' in admin_html
    assert '<span id="deletePlanModalIcon" class="text-base shrink-0">📦</span>' in admin_html
    assert "$('deletePlanModalIcon')" in admin_plans
