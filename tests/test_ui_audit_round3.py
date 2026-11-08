from pathlib import Path


def test_invoice_service_logo_multiple_candidate_paths():
    """Invoice service should search multiple candidate paths to find local store logo."""
    content = Path("bot/services/invoice_service.py").read_text(encoding="utf-8")
    assert "candidate_paths = [" in content
    assert "base_dir / clean_path" in content


def test_invoice_logo_and_icon_wiring():
    """Invoice in TMA should always display the clean default icon 🧾 and RTL left-positioned plan icon."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")

    # In app.html, invItemTitle is followed by invItemIcon in RTL flex row (so icon is visually on the left)
    assert '<b id="invItemTitle" class="t-main text-xs">بسته اشتراک</b>' in app_html
    assert '<span id="invItemIcon" class="text-xs shrink-0">📦</span>' in app_html

    # Invoice header displays defaultIcon 🧾
    assert '<span id="invItemIcon" class="text-xs shrink-0">📦</span>' in app_html
    assert '<span id="invSellerDefaultIcon" class="text-2xl">🧾</span>' in app_html
    assert "$('invSellerDefaultIcon')" in app_js


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
    assert "t-muted hover:t-main" in app_html
    assert "t-muted hover:t-main" in app_js


def test_loyalty_modal_typography_and_dots_removed():
    """Loyalty discount numbers should use Vazirmatn and have no trailing dots."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")

    # In app.html, tier percentages use font-sans num-bidi
    assert 'id="loyaltyTierCard_silver_pct" class="text-emerald-500 font-bold font-sans num-bidi"' in app_html
    assert 'id="loyaltyTierCard_gold_pct" class="text-emerald-500 font-bold font-sans num-bidi"' in app_html

    # In app.js, current discount and all_tiers use font-sans
    assert '<span class="font-sans font-bold num-bidi"' in app_js

    # Trailing dots are removed from tier descriptions
    assert '<b class="text-emerald-500 font-bold">تخفیف</b>.' not in app_html
    assert 'سطح پیش‌فرض هنگام عضویت (بدون تخفیف)' in app_html


def test_kill_sessions_modals():
    """Both kill all sessions and kill single device must have dedicated modals."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")
    comp_css = Path("bot/web/static/css/components.css").read_text(encoding="utf-8")

    # Modals in HTML
    assert 'id="killAllSessionsModal"' in app_html
    assert 'id="killSingleDeviceModal"' in app_html
    assert 'id="confirmKillSingleDeviceBtn"' in app_html

    # Modals in JS list and handlers
    assert "'killAllSessionsModal'" in app_js
    assert "'killSingleDeviceModal'" in app_js
    assert "function openKillSingleDeviceModal" in app_js
    assert "function confirmKillSingleDevice" in app_js

    # .btn-danger component defined in components.css
    assert ".btn-danger {" in comp_css
    assert "html.theme-light .btn-danger" in comp_css


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
    """Custom plan breakdown must display percent with % on right and minus amount in value."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")
    comp_css = Path("bot/web/static/css/components.css").read_text(encoding="utf-8")

    assert 'id="customPlanDiscountPct"' in app_html
    assert 'تخفیف باشگاه مشتریان شما (<span dir="ltr" class="inline-block num-bidi font-bold"><span id="customPlanDiscountPct">0</span>%</span>):' in app_html
    assert 'تخفیف پلکانی حجم انتخابی (<span dir="ltr" class="inline-block num-bidi font-bold"><span id="customPlanVolumeTierPct">0</span>%</span>):' in app_html

    # High contrast in light mode
    assert "html.theme-light #customPlanVolumeDiscountRow" in comp_css
    assert "html.theme-light #customPlanDiscountRow" in comp_css

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


def test_guidance_text_not_italic():
    """Guidance text for squad switch must not be italic."""
    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")
    shop_renew = Path("bot/handlers/shop_renew.py").read_text(encoding="utf-8")

    assert "<i>راهنما: چنانچه قصد تغییر دسته سرور" not in shop_js
    assert "<i>راهنما: چنانچه قصد تغییر دسته سرور" not in shop_renew


def test_tronlink_deeplink_sun_amount_and_parameters():
    """TronLink DeepLink must specify amount in SUN and include all required parameters."""
    user_topup = Path("bot/web/user_topup.py").read_text(encoding="utf-8")
    wallet_js = Path("bot/web/static/js/wallet.js").read_text(encoding="utf-8")

    # In user_topup.py
    assert "amount_sun = int(round(amt_float * 1_000_000))" in user_topup
    assert '"chainId": "0x2b6653dc"' in user_topup
    assert '"dappName": "Remnabot Cloud"' in user_topup
    assert '"actionId": action_id' in user_topup

    # In wallet.js
    assert "const amountSun = Math.round(trxAmount * 1000000);" in wallet_js
    assert "actionId: String(Date.now())" in wallet_js
    assert "chainId: '0x2b6653dc'" in wallet_js


def test_gift_modal_clarity_and_nowrap():
    """Gift modal options must have high-contrast active gradient and nowrap labels."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")

    assert 'id="giftDeliveryBtn-direct"' in app_html
    assert "whitespace-nowrap" in app_html
    assert "bg-gradient-to-r from-pink-500 to-rose-500 text-white font-bold" in app_js
    assert "card-inset border border-card-border t-muted" in app_js


def test_invoice_caching_and_instant_load():
    """Invoices must be cached in memory (client) and FastCache (server) for instant render."""
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")
    user_shop = Path("bot/web/user_shop.py").read_text(encoding="utf-8")

    assert "const invoiceClientCache = new Map();" in app_js
    assert "renderInvoiceModalFields(invoiceClientCache.get(orderId), orderId);" in app_js
    assert 'cache_key = f"inv:ord:{telegram_id}:{order_id}"' in user_shop
    assert "await cache.set(cache_key, inv_data, ttl_seconds=600)" in user_shop


def test_history_page_size_setting():
    """History page size must be customizable in settings (default 15) and reflected in UI."""
    from bot.services.app_settings import StoreSettings
    assert StoreSettings.__dataclass_fields__["history_page_size"].default == 15

    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    admin_settings_js = Path("bot/web/static/js/admin_settings.js").read_text(encoding="utf-8")
    admin_settings_api = Path("bot/web/admin_settings_api.py").read_text(encoding="utf-8")
    wallet_js = Path("bot/web/static/js/wallet.js").read_text(encoding="utf-8")
    user_topup = Path("bot/web/user_topup.py").read_text(encoding="utf-8")

    assert 'id="settingHistoryPageSize"' in admin_html
    assert "$('settingHistoryPageSize')" in admin_settings_js
    assert '"history_page_size":' in admin_settings_api
    assert '"history_page_size"' in admin_settings_api
    assert '"history_page_size": hist_page_val' in user_topup
    assert "function getTxPerPage()" in wallet_js
    assert "window.storeSettings?.history_page_size" in wallet_js


def test_client_autoconnect_app_names_and_compact_grid():
    """Client import buttons must use compact typography and padding so app names do not truncate."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")

    assert "grid grid-cols-6 gap-1 sm:gap-1.5" in app_html
    assert 'id="appImportStreisand"' in app_html
    assert "text-[9.5px] sm:text-[11px]" in app_html
    assert "tracking-tighter" in app_html

