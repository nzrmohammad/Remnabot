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
    assert 'placeholder="@username &lrm;یا&lrm; 123456789"' in app_html

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

    # app.css has high-contrast warm amber-orange gradient (>= 5.0:1 with white text)
    assert ".btn-plan-bestseller {" in app_css
    assert "linear-gradient(135deg, #b45309 0%, #c2410c 100%)" in app_css

    # shop.js handles bestseller with Persian word
    assert "planBadgeKey.includes('پرفروش')" in shop_js


def test_custom_plan_price_breakdown_label():
    """Custom plan breakdown must display percent with % on right and minus amount in value."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")
    comp_css = Path("bot/web/static/css/components.css").read_text(encoding="utf-8")

    assert 'id="customPlanDiscountPct"' in app_html
    assert 'تخفیف باشگاه مشتریان (<span dir="ltr" class="inline-block num-bidi font-bold"><span id="customPlanDiscountPct">0</span>%</span>):' in app_html
    assert 'تخفیف حجم انتخابی (<span dir="ltr" class="inline-block num-bidi font-bold"><span id="customPlanVolumeTierPct">0</span>%</span>):' in app_html

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
    """TronLink DeepLink must specify valid parameters, Mainnet chainId, and prioritize native TRON URI."""
    user_topup = Path("bot/web/user_topup.py").read_text(encoding="utf-8")
    wallet_js = Path("bot/web/static/js/wallet.js").read_text(encoding="utf-8")

    # In user_topup.py
    assert '"chainId": "0x2b6653de"' in user_topup
    assert '"dappName": "Remnabot Cloud"' in user_topup
    assert '"actionId": action_id' in user_topup
    assert "safe_tron_uri" in user_topup

    # In wallet.js
    assert "const tronUri = `tron:${inv.pay_address}?amount=${trxAmount}`;" in wallet_js
    assert "window.location.href = tronUri;" in wallet_js


def test_gift_modal_clarity_and_nowrap():
    """Gift modal options must have high-contrast active gradient and nowrap labels."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")

    assert 'id="giftDeliveryBtn-direct"' in app_html
    assert "whitespace-nowrap" in app_html
    assert "bg-pink-600 text-white font-bold" in app_js
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
    """Client import buttons must use icon-only borderless grid filling the card."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")

    assert "grid grid-cols-6 gap-1.5 sm:gap-2 text-center" in app_html
    assert 'id="appImportStreisand"' in app_html
    assert 'w-11 h-11 sm:w-13 sm:h-13 rounded-2xl object-cover' in app_html



def test_admin_marketing_badges_and_plan_limit_label():
    """Marketing badges must be streamlined and plan limit must have stylish optional tag."""
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    admin_plans = Path("bot/web/static/js/admin_plans.js").read_text(encoding="utf-8")

    # Marketing badges
    assert "': 'انتخاب کنید'" in admin_plans
    assert "'gaming': '🎮 ویژه گیمینگ'" in admin_plans
    assert "پینگ پایین" not in admin_plans
    assert "'antifilter':" not in admin_plans
    assert "'speed':" not in admin_plans

    # Plan limit label & optional badge
    assert "سقف تعداد فروش (خالی = نامحدود):" in admin_html
    assert ">اختیاری</span>" in admin_html

    # Badge modal list padding
    assert "pl-1 pr-2 py-1" in admin_html


def test_top_consumers_period_sync():
    """Top consumers period must start on daily to match active UI button."""
    admin_charts = Path("bot/web/static/js/admin_charts.js").read_text(encoding="utf-8")

    assert "let currentTopConsumersPeriod = 'daily';" in admin_charts
    assert "renderAdminTopConsumersChart(c.top_consumers, 'daily')" in admin_charts



def test_user_profile_modal_high_contrast_in_dark_theme():
    """User profile modal Telegram ID must use t-main to stay high-contrast in dark mode."""
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    assert 'id="userProfModalId" class="font-sans t-main font-black text-xs select-all"' in admin_html
    assert 'text-slate-800 dark:text-slate-100' not in admin_html


def test_check_host_custom_modals_and_ltr_result_cards():
    """Check-Host must have custom modals and dir=ltr cards placing flag/country on the left."""
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    admin_nodes_js = Path("bot/web/static/js/admin_nodes.js").read_text(encoding="utf-8")
    admin_infra = Path("bot/web/admin_infra_api.py").read_text(encoding="utf-8")

    # Modals in admin.html
    assert 'id="checkHostTypeModal"' in admin_html
    assert 'id="checkHostNodesModal"' in admin_html
    assert 'id="checkHostTypeBtn"' in admin_html
    assert 'id="checkHostNodesBtn"' in admin_html

    # Modal methods in admin_nodes.js
    assert "window.openCheckHostTypeModal" in admin_nodes_js
    assert "window.openCheckHostNodesModal" in admin_nodes_js
    assert "window.selectCheckHostType" in admin_nodes_js
    assert "window.selectCheckHostNodes" in admin_nodes_js

    # Result card orientation in admin_nodes.js (dir="ltr")
    assert 'class="card-inset p-2 rounded-xl border flex items-center justify-between ${statusClass}" dir="ltr"' in admin_nodes_js

    # admin_infra_api handles HTTPS and port properly
    assert 'is_https = original_host.startswith("https://")' in admin_infra
    assert 'query_host = f"https://{clean_host}"' in admin_infra


def test_asn_lookup_ui_layout_and_copy_button():
    """ASN lookup copy button must be grouped on the left with the filter and list stretched full width."""
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    admin_nodes_js = Path("bot/web/static/js/admin_nodes.js").read_text(encoding="utf-8")

    # ASN results box has full width
    assert 'id="asnResultsBox" class="hidden space-y-2 pt-2 w-full"' in admin_html
    # Copy button is after filter input (on the left side of the flex row)
    assert 'id="asnFilterInput"' in admin_html
    assert 'button type="button" onclick="window.copyAllAsnPrefixes()"' in admin_html
    # Prefixes list has w-full
    assert 'id="asnPrefixesList" class="w-full' in admin_html
    # Prefix chips use tokenized t-purple
    assert "t-purple font-bold text-[11px]" in admin_nodes_js


def test_ui_polish_round4():
    """Verify invoice icon placement, gift borders, card minimal mode, and admin layout."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    wallet_js = Path("bot/web/static/js/wallet.js").read_text(encoding="utf-8")
    comp_css = Path("bot/web/static/css/components.css").read_text(encoding="utf-8")

    # 1. Invoice item title precedes item icon in RTL flex row (icon is on visual left)
    assert '<b id="invItemTitle" class="t-main text-xs">بسته اشتراک</b>' in app_html
    assert '<span id="invItemIcon" class="text-xs shrink-0">📦</span>' in app_html

    # 2. Gift modal active buttons have high-visibility border, components has .border-card-border
    assert ".border-card-border" in comp_css
    assert "border-color: var(--card-border);" in comp_css
    assert "border border-pink-500/40" in app_js
    assert 'id="giftTypeBtn-balance"' in app_html
    assert 'id="giftDeliveryBtn-direct"' in app_html

    # 3. History page size description text removed
    assert "تعداد فاکتورها و تراکنش‌های نمایش‌داده‌شده در هر صفحه کیف پول" not in admin_html
    assert 'id="settingHistoryPageSize"' in admin_html

    # 3.1 English +98 in Iran phone limit note and Internal Squad removed from label
    assert ('محدودیت احراز فقط برای شماره ایران (<span class="num-bidi font-sans" dir="ltr">+98</span>)' in admin_html or 'محدودیت احراز فقط برای شماره ایران (<span class="num-bidi font-mono" dir="ltr">+98</span>)' in admin_html)
    assert 'اسکواد متصل:</label>' in admin_html
    assert 'اسکواد متصل (Internal Squad):' not in admin_html

    # 4. Bank card minimal mode hides bank title and logo
    assert "const isMinimal = String(bankTmpl || '').toLowerCase() === 'minimal';" in wallet_js
    assert "titleEl.innerText = isMinimal ? '' : 'SamanBank';" in wallet_js
    assert "iconEl.style.display = isMinimal ? 'none' : '';" in wallet_js
    assert "backTextEl.innerText = isMinimal ? '' : 'Blu, But Lovely';" in wallet_js

    # 5. Plan modal removes squad auto-split description & offsets active checkbox
    assert "تخصیص سرورهای این بسته به کاربر و تفکیک خودکار قیمت حجم/زمان" not in admin_html
    assert 'id="planModalActive" checked class="w-4 h-4 rounded text-blue-600 bg-slate-900 border-slate-700 ml-1.5"' in admin_html

    # 6. Announced prefixes copy button is icon-only and in title group on the right; badge uses font-sans
    assert 'button type="button" onclick="window.copyAllAsnPrefixes()" class="btn btn-secondary w-7 h-7 p-0 rounded-xl flex items-center justify-center transition active:scale-95 shadow-xs"' in admin_html
    assert "<span>کپی همه</span>" not in admin_html
    assert 'id="asnCountBadge" class="badge badge-info font-sans">0 رنج</span>' in admin_html
    assert 'id="asnFilterInput" type="text" oninput="window.filterAsnPrefixes(this.value)" placeholder="فیلتر رنج..." dir="ltr" class="input-base px-2.5 py-1 text-xs font-sans rounded-xl w-full flex-1 outline-none"' in admin_html


def test_vazirmatn_typography_guard():
    """Verify improper font-mono classes are replaced by Vazirmatn font-sans and num-bidi."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")

    # 1. Header username and inputs use font-sans
    assert 'id="headerUsername" class="font-bold t-accent text-xs max-w-[100px] truncate font-sans"' in app_html
    assert 'id="giftReceiverInput" placeholder="@username &lrm;یا&lrm; 123456789" class="input-base w-full p-2.5 rounded-xl text-xs outline-none text-left font-sans"' in app_html
    assert 'id="giftBalanceAmount" min="10000" step="5000" placeholder="مثال: 50,000" class="input-base w-full p-2.5 rounded-xl text-xs outline-none num-bidi font-sans"' in app_html
    assert 'id="topupAmountInput" placeholder="مبلغ دلخواه را وارد کنید (تومان)" class="input-base w-full px-3 py-2 rounded-xl outline-none text-xs mt-1 num-bidi font-sans"' in app_html

    # 2. Loyalty and countdown elements use font-sans / num-bidi
    assert 'id="loyaltyModalTotalSpent" class="text-xs t-main font-sans num-bidi"' in app_html
    assert 'id="countdownDays" class="text-xl font-black font-sans num-bidi t-warn block leading-tight"' in app_html
    assert 'id="bdayCountdownDays" class="text-xl font-black font-sans num-bidi t-pink block leading-tight"' in app_html

    # 3. Admin user page info uses font-sans num-bidi and semantic t-muted
    assert 'id="adminUsersPageInfo" class="font-sans num-bidi text-[11px] t-muted"' in admin_html


def test_topup_empty_default_and_manual_graphic_card():
    """Verify topup modal opens with empty input and manual card includes 3D graphic view."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    wallet_js = Path("bot/web/static/js/wallet.js").read_text(encoding="utf-8")

    # In app.html and wallet.js, chargeWalletBtn opens topup modal without hardcoded amount
    assert 'id="chargeWalletBtn" onclick="window.openTopupModal && window.openTopupModal()"' in app_html
    assert "document.getElementById('chargeWalletBtn')?.addEventListener('click', () => {\n    openTopupModal();\n  });" in wallet_js

    # In app.html, manual card mode has manualCardGraphicBox
    assert 'id="manualCardGraphicBox" class="card-graphic-box blu-card-perspective-box hidden my-2 select-none"' in app_html
    assert 'id="manualGraphicCardNumberDisplay"' in app_html
    assert 'id="manualGraphicCardHolderDisplay"' in app_html

    # In wallet.js, manual graphic elements are synced
    assert "const manualGraphicNum = document.getElementById('manualGraphicCardNumberDisplay');" in wallet_js
    assert "const manualGraphicHolder = document.getElementById('manualGraphicCardHolderDisplay');" in wallet_js


def test_revoke_sub_account_selection_and_modal():
    """Revoke sub should accept account_id and display target account name in confirmation modal."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")
    api_js = Path("bot/web/static/js/api.js").read_text(encoding="utf-8")
    user_shop_py = Path("bot/web/user_shop.py").read_text(encoding="utf-8")

    # Target account label in modal
    assert 'id="revokeTargetAccountName"' in app_html
    assert "prepareAndOpenRevokeModal" in app_js
    assert "targetEl.innerText = `اکانت هدف: ${accObj.username || accObj.id}`;" in app_js

    # api.js passes account_id
    assert "async revokeSub(accountId = null)" in api_js
    assert "window.api.revokeSub(window.currentAccountId)" in app_js

    # user_shop.py matches account_id
    assert 'account_id = data.get("account_id")' in user_shop_py
    assert 'str(u.get("id")) == str(account_id) or str(u.get("uuid")) == str(account_id)' in user_shop_py


def test_client_importers_icon_only_grid():
    """Verify 1-click importers display clean icon-only grid without redundant text labels."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")

    # Importers are icon-only with larger images filling the button
    assert '<!-- 1-Click App Importers (Icon-Only Borderless Grid) -->' in app_html
    assert '<img src="/static/img/apps/incy.webp" alt="Incy" class="w-11 h-11 sm:w-13 sm:h-13 rounded-2xl object-cover' in app_html
    assert '<img src="/static/img/apps/happ.webp" alt="Happ" class="w-11 h-11 sm:w-13 sm:h-13 rounded-2xl object-cover' in app_html
    assert '<span class="text-[9.5px] sm:text-[11px] font-medium t-muted truncate block max-w-full tracking-tighter sm:tracking-normal">Incy</span>' not in app_html


def test_orders_service_id_nullable_migration():
    """Verify orders.service_id NOT NULL is dropped in base.py and self-heals in user_shop.py."""
    base_py = Path("bot/db/base.py").read_text(encoding="utf-8")
    user_shop_py = Path("bot/web/user_shop.py").read_text(encoding="utf-8")

    assert "ALTER TABLE orders ALTER COLUMN service_id DROP NOT NULL;" in base_py
    assert "ALTER TABLE orders ALTER COLUMN service_id DROP NOT NULL;" in user_shop_py
    assert "Detected legacy NOT NULL on orders.service_id, executing inline self-healing migration..." in user_shop_py


def test_coupon_card_ltr_code_copy_status_order():
    """Coupon cards should lay out code -> copy icon -> status badge left-to-right."""
    admin_plans = Path("bot/web/static/js/admin_plans.js").read_text(encoding="utf-8")

    ltr_idx = admin_plans.find('<div class="flex items-center gap-2" dir="ltr">')
    copy_idx = admin_plans.find('class="btn-quick-copy-coupon', ltr_idx)
    badge_idx = admin_plans.find('${statusBadge}', copy_idx)
    assert ltr_idx != -1 and copy_idx != -1 and badge_idx != -1
    assert ltr_idx < copy_idx < badge_idx


def test_birthday_edit_hidden_after_registration():
    """Once birthday is registered, edit UI must not be shown in app frontend."""
    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")

    assert "✏️ ویرایش تاریخ تولد" not in app_html
    assert "ویرایش تاریخ" not in app_js
    assert "ویرایش ✏️" not in app_js
    assert "if (hasBirthDate) {\n        bdayBtn.classList.add('hidden');" in app_js
    assert "if (existingDate && String(existingDate).trim()) {" in app_js


def test_campaign_delete_confirmation_modal():
    """Campaign deletion must use a dedicated custom modal rather than window.confirm."""
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    admin_settings = Path("bot/web/static/js/admin_settings.js").read_text(encoding="utf-8")
    admin_js = Path("bot/web/static/js/admin.js").read_text(encoding="utf-8")

    for html_id in [
        'id="deleteCampaignModal"',
        'id="deleteCampaignModalName"',
        'id="deleteCampaignModalCode"',
        'id="confirmDeleteCampaignBtn"',
    ]:
        assert html_id in admin_html

    assert "openDeleteCampaignModal(" in admin_settings
    assert "closeDeleteCampaignModal(" in admin_settings
    assert "executeDeleteCampaign(" in admin_settings
    assert "confirm(`آیا از حذف کمپین" not in admin_settings
    assert "window.openDeleteCampaignModal" in admin_js


def test_no_monospace_font_anywhere_in_web():
    """Ensure monospace font family is completely replaced by Vazirmatn across web assets."""
    for path_str in [
        "bot/web/static/css/base.css",
        "bot/web/static/css/components.css",
        "bot/web/static/css/tailwind.min.css",
        "bot/web/static/js/charts.js",
        "bot/web/static/js/story.js",
        "bot/web/static/js/app.js",
        "bot/web/templates/app.html",
        "bot/web/user_topup.py",
    ]:
        content = Path(path_str).read_text(encoding="utf-8")
        assert "monospace" not in content, f"Found residual monospace font in {path_str}"

    base_css = Path("bot/web/static/css/base.css").read_text(encoding="utf-8")
    assert ".font-mono, code, pre, kbd, samp" in base_css
    assert "Vazirmatn" in base_css
    tailwind_cfg = Path("tailwind.config.js").read_text(encoding="utf-8")
    assert "mono: ['Vazirmatn'" in tailwind_cfg


def test_latest_ui_and_font_polish_batch():
    """Verify receipt button guard, LTR plans, uniform borders, coupon layout, no italics, and no font-mono class in HTML/JS."""
    import re

    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    wallet_js = Path("bot/web/static/js/wallet.js").read_text(encoding="utf-8")
    admin_plans = Path("bot/web/static/js/admin_plans.js").read_text(encoding="utf-8")
    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")
    utils_js = Path("bot/web/static/js/utils.js").read_text(encoding="utf-8")
    comp_css = Path("bot/web/static/css/components.css").read_text(encoding="utf-8")
    card_auto = Path("bot/services/payment/card_auto_service.py").read_text(encoding="utf-8")

    # 1. Card manual receipt submit button starts disabled and tracks duplicate/auto-paid guards
    assert 'id="submitCardTopupBtn" type="button" disabled' in app_html
    assert 'id="cardReceiptWarningBanner"' in app_html
    assert "window.updateCardTopupSubmitState" in wallet_js
    assert "knownDuplicateHashes" in wallet_js
    assert "recentPaidAutoAmounts" in wallet_js

    # 2. Admin plans LTR titles, restored shop styles/borders, and uniform neutral admin tag badges
    assert '<bdi dir="ltr"' in utils_js
    assert '<b dir="ltr" class="t-main text-xs font-bold truncate">' in admin_plans
    assert "TAG_LABELS" in admin_plans
    assert "badge badge-plan-type" in admin_plans
    assert "border-slate-700/80" in admin_plans
    assert "badge-stream" in shop_js
    assert "badge-family" in shop_js
    assert "border: 1px solid var(--card-border);" in comp_css

    # 3. Discount codes tab polish: no copy svg icon, compact buttons without .btn, 'نامحدود' without '(دائمی)'
    assert "نامحدود (دائمی)" not in admin_plans
    copy_btn_start = admin_plans.find('class="btn-quick-copy-coupon')
    copy_btn_end = admin_plans.find('</button>', copy_btn_start)
    assert copy_btn_start != -1 and "<svg" not in admin_plans[copy_btn_start:copy_btn_end]
    assert 'class="btn-coupon-usages btn-secondary flex-1 py-2 px-2' in admin_plans

    # 4. Zero italics anywhere in web assets or card_auto notifications, and zero font-mono classes in templates/non-minified JS
    assert "<i>" not in card_auto
    assert "<i>" not in app_html
    assert "<i>" not in admin_html
    assert ' class="hidden items-center gap-2 text-[11px] text-slate-400 italic"' not in app_html
    for asset_text in (app_html, admin_html, wallet_js, admin_plans, shop_js):
        assert not re.search(r"\bfont-mono\b", asset_text)


def test_latest_requested_ui_features_and_english_digits():
    """Verify gifts/achievements, no Persian digits anywhere in display strings, 3-mode hourly curve, no custom diamond, LTR invoice buyer, 4 new apps, and magenta BluBank card."""
    import re
    from bot.web.user_subscription_detail import calc_usage_curves
    from bot.handlers.guide import APP_DISPLAY_NAMES, PLATFORMS
    from bot.web.admin_infra_api import GITHUB_REPOS

    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    admin_html = Path("bot/web/templates/admin.html").read_text(encoding="utf-8")
    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")
    charts_js = Path("bot/web/static/js/charts.js").read_text(encoding="utf-8")
    wallet_js = Path("bot/web/static/js/wallet.js").read_text(encoding="utf-8")
    utils_js = Path("bot/web/static/js/utils.js").read_text(encoding="utf-8")
    admin_settings_js = Path("bot/web/static/js/admin_settings.js").read_text(encoding="utf-8")
    fa_py = Path("bot/locales/fa.py").read_text(encoding="utf-8")

    # 1. Gifts & Achievements: no countdown in card, no 'بدون کد فعال', English 0
    assert "بدون کد فعال" not in app_js
    assert '<b id="achieveWonCoupons" class="font-sans t-success text-xs font-bold" dir="rtl">0 کد</b>' in app_html
    ach_fn = app_js[app_js.find("function renderUserAchievements"):app_js.find("window.renderUserAchievements")]
    assert "openBirthdayCountdownModal" not in ach_fn
    assert "شمارش معکوس" not in ach_fn

    # 2. Zero Persian/Eastern-Arabic digits in UI templates, JS outputs, and Persian locale
    digit_re = re.compile(r"[\u0660-\u0669\u06F0-\u06F9]")
    for content in (app_html, admin_html, app_js, charts_js, wallet_js, admin_settings_js, fa_py):
        assert not digit_re.search(content)
    # Only the input-normalization lookup arrays in utils.js may contain Persian digits
    utils_without_norm = "\n".join(
        line for line in utils_js.splitlines()
        if "const fa = ['۰'" not in line and "const ar = ['٠'" not in line
    )
    assert not digit_re.search(utils_without_norm)

    # 3. Peak hours exact hour (no range), Today-Yesterday-Compare order, and rolling 24h curve
    t_pos = app_html.find('id="repPeakModeTodayBtn"')
    y_pos = app_html.find('id="repPeakModeYesterdayBtn"')
    c_pos = app_html.find('id="repPeakModeCompareBtn"')
    assert 0 < t_pos < y_pos < c_pos
    assert "window.switchUserPeakHoursMode" in app_js
    assert "splitTodayIndex" in app_js
    assert "splitTodayIndex" in charts_js
    curves = calc_usage_curves(
        primary={"usedTrafficBytes": 5 * 1024**3},
        devices=[],
        traffic={},
        used_bytes=5 * 1024**3,
        today_used_gb=2.0,
        week_used_gb=8.0,
        panel_user_id="u1",
        source_breakdown=[],
        yesterday_used_gb=3.0,
    )
    hu = curves["hourly_usage"]
    yhu = curves["yesterday_hourly_usage"]
    assert len(hu["hourly_labels_24"]) == 24
    assert len(hu["hourly_data_24"]) == 24
    assert len(yhu["hourly_data_24"]) == 24
    assert hu["peak_hour"] and "-" not in hu["peak_hour"]
    assert yhu["peak_hour"] and "-" not in yhu["peak_hour"]

    # 4. Custom plan in transaction history has no diamond icon
    custom_block_start = wallet_js.find("if (isCustom) {")
    custom_block_end = wallet_js.find("} else {", custom_block_start)
    assert "💎" not in wallet_js[custom_block_start:custom_block_end]

    # 5. Official invoice Buyer label stays RTL while inner values are LTR; status icon is left of label
    buyer_idx = app_html.find("👤 خریدار:")
    seller_idx = app_html.find("🏢 ارائه‌دهنده:")
    assert buyer_idx != -1 and seller_idx != -1
    buyer_outer = app_html[buyer_idx - 70:buyer_idx + 20]
    buyer_inner = app_html[buyer_idx:buyer_idx + 120]
    seller_box = app_html[seller_idx - 70:seller_idx + 20]
    assert 'dir="ltr"' not in buyer_outer
    assert 'dir="ltr"' in buyer_inner
    assert 'dir="ltr"' not in seller_box
    assert "<span>پرداخت شده</span> <span>✅</span>" in app_html
    assert "<span>${statusText}</span> <span>${icon}</span>" in app_js

    # 6. Karing, PattN, PattNG, Zedsecure added across app configs, logos & guide + alternative app + Portable label
    for app_id in ("karing", "pattn", "pattng", "zedsecure"):
        assert app_id in APP_DISPLAY_NAMES
        assert app_id in GITHUB_REPOS
        assert f"id: '{app_id}'" in app_js
        assert f"{app_id}:" in admin_settings_js
        assert Path(f"bot/web/static/img/apps/{app_id}.png").is_file()
        assert Path(f"bot/web/static/img/apps/{app_id}.webp").is_file()
    assert any("Karing" in n for n, _ in PLATFORMS["ios"][1])
    assert any("PattNG" in n for n, _ in PLATFORMS["android"][1])
    assert any("PattN" in n for n, _ in PLATFORMS["windows"][1])
    assert any("Zedsecure" in n for n, _ in PLATFORMS["linux"][1])
    assert "لینک دانلود نسخه Portable:" in admin_html
    assert "پرتابل (Portable" not in admin_html
    for os_k in ("ios", "android", "windows", "macos", "linux"):
        assert f'id="appAlternative_{os_k}"' in admin_html
    assert "isAlternative" in app_js

    # 7. New magenta BluBank card theme color present
    assert "magenta:" in wallet_js
    assert "id: 'magenta'" in admin_settings_js

    # 8. Follow-up UX & copy fixes: toast newline, receipt btn bg, card_auto icon, referral note, OS field, Polygon label, topic size, modal scroll
    admin_js = Path("bot/web/static/js/admin.js").read_text(encoding="utf-8")
    assert "کپی شد:\\n${safeText}" in admin_js
    assert "bg-rose-950/40" not in app_html[app_html.find('id="removeReceiptImageBtn"'):app_html.find('id="removeReceiptImageBtn"') + 250]
    assert "card_auto: '💳'" in wallet_js
    assert "اولین خرید" in app_html
    assert "اولین خرید" in fa_py
    assert "سیستم‌عامل:" in app_js
    assert "Polygon PoS" not in admin_html
    assert "Polygon PoS" not in app_html
    assert 'id="settingTopicTopups"' in admin_html and 'text-[10px]' in admin_html
    assert "space-y-2.5 flex-1 min-h-0 max-h-[60vh] overflow-y-auto" in admin_html
