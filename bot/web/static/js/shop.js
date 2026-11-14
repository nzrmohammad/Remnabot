/**
 * RemnaStore Pro - Shop Plans & Checkout Logic
 * Native TMA checkout modal without browser confirm alerts.
 */

window.activeCoupon = null;
let currentPendingPlan = null;

function setupCouponInput() {
  const applyCouponBtn = document.getElementById('applyCouponBtn');
  const couponInput = document.getElementById('couponInput');
  if (!applyCouponBtn || !couponInput) return;

  const resetCouponState = (showFeedback = true) => {
    window.activeCoupon = null;
    couponInput.value = '';
    couponInput.disabled = false;
    applyCouponBtn.disabled = false;
    applyCouponBtn.innerText = '⚡️ اعمال';
    applyCouponBtn.className = 'btn btn-primary text-xs font-semibold px-4 py-2 rounded-lg shadow shrink-0';
    if (showFeedback) {
      showToast('ℹ️ کد تخفیف حذف گردید.');
      hapticFeedback('selection');
    }
    if (window.lastUserData) {
      renderShopPlans(window.lastUserData);
      renderWonCoupons(window.lastUserData);
    }
  };

  applyCouponBtn.addEventListener('click', async () => {
    // If coupon is already applied, button acts as "✕ حذف"
    if (window.activeCoupon) {
      resetCouponState(true);
      return;
    }

    const code = couponInput.value.trim().toUpperCase();
    if (!code) {
      showToast('⚠️ لطفاً کد تخفیف را وارد فرمایید.');
      return;
    }
    applyCouponBtn.disabled = true;
    applyCouponBtn.innerText = 'بررسی...';

    try {
      const res = await window.api.validateCoupon(code);
      if (res.ok && res.data) {
        window.activeCoupon = res.data;
        let discMsg = '';
        if (res.data.discount_percent > 0) discMsg = `${toEnglishDigits(res.data.discount_percent)}%`;
        else if (res.data.discount_amount > 0) discMsg = `${Number(res.data.discount_amount).toLocaleString('en-US')} تومان`;
        showToast(`🎉 کد تخفیف اعمال شد!\n(${discMsg} تخفیف)`);
        hapticFeedback('success');
        applyCouponBtn.innerText = '✕ حذف';
        applyCouponBtn.className = 'bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold px-4 py-2 rounded-lg transition active:scale-95 shadow shrink-0';
        couponInput.disabled = true;
        if (window.lastUserData) {
          renderShopPlans(window.lastUserData);
          renderWonCoupons(window.lastUserData);
        }
      } else {
        window.activeCoupon = null;
        showToast(`❌ ${res.message || 'کد تخفیف نامعتبر است.'}`);
        hapticFeedback('error');
        applyCouponBtn.innerText = '⚡️ اعمال';
        applyCouponBtn.className = 'btn btn-primary text-xs font-semibold px-4 py-2 rounded-lg shadow shrink-0';
        couponInput.disabled = false;
        if (window.lastUserData) renderShopPlans(window.lastUserData);
      }
    } catch (err) {
      showToast('❌ خطا در بررسی کد تخفیف.');
      applyCouponBtn.innerText = 'اعمال';
      applyCouponBtn.className = 'bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold px-4 py-2 rounded-lg transition active:scale-95 shadow shrink-0';
      couponInput.disabled = false;
    } finally {
      applyCouponBtn.disabled = false;
    }
  });

  window.applyCouponCodeDirectly = (code) => {
    if (window.activeCoupon) resetCouponState(false);
    couponInput.value = code;
    applyCouponBtn.click();
  };
}

function renderWonCoupons(data) {
  const container = document.getElementById('userCouponsContainer');
  const list = document.getElementById('userCouponsList');
  if (!container || !list) return;

  const now = Date.now();
  const isValidCoupon = (c) => {
    if (!c || !c.code) return false;
    if (c.is_expired) return false;
    if (!c.expires_at) return false;
    const exp = new Date(c.expires_at).getTime();
    if (isNaN(exp) || exp <= now) return false;
    return true;
  };

  let coupons = (data?.won_coupons || []).filter(isValidCoupon);
  if (coupons.length === 0) {
    try {
      const local = JSON.parse(localStorage.getItem('user_won_coupons') || '[]');
      if (Array.isArray(local)) {
        const validLocal = local.filter(isValidCoupon);
        localStorage.setItem('user_won_coupons', JSON.stringify(validLocal));
        coupons = validLocal;
      }
    } catch(e) {}
  }

  if (!coupons || coupons.length === 0) {
    container.classList.add('hidden');
    list.innerHTML = '';
    return;
  }

  container.classList.remove('hidden');

  const activeCode = (window.activeCoupon?.code || '').toUpperCase();
  list.innerHTML = coupons.map(c => {
    const isApplied = Boolean(activeCode && c.code && activeCode === String(c.code).toUpperCase());
    const btnText = isApplied ? '✓ اعمال شد' : '⚡️ اعمال';
    const btnClass = isApplied
      ? 'won-coupon-apply-btn bg-emerald-600 text-white font-semibold px-3 py-1.5 rounded-lg text-xs transition active:scale-95 shrink-0 shadow-sm'
      : 'won-coupon-apply-btn btn btn-primary text-xs font-semibold px-3 py-1.5 rounded-lg shadow shrink-0';
    return `
      <div class="won-coupon-card flex-1 min-w-[140px] flex items-center justify-between gap-2 p-2.5 rounded-xl card-inset border border-slate-200 dark:border-slate-800 transition shadow-none" dir="ltr">
        <div class="text-left">
          <div class="flex items-center gap-1.5">
            <span class="text-xs">🎟</span>
            <span class="font-bold font-sans tracking-wider t-main text-xs select-all">${escapeHtml(c.code)}</span>
          </div>
          <span class="text-[11px] t-success font-sans block mt-0.5"><span class="font-sans font-bold inline-block">${toEnglishDigits(c.discount_percent || 10)}%</span> تخفیف</span>
        </div>
        <button type="button" class="${btnClass}" data-code="${escapeHtml(c.code)}">
          ${btnText}
        </button>
      </div>
    `;
  }).join('');

  list.querySelectorAll('.won-coupon-apply-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const code = btn.getAttribute('data-code');
      if (code && typeof window.applyCouponCodeDirectly === 'function') {
        window.applyCouponCodeDirectly(code);
      }
    });
  });
}
// Note: formatPlanTitle is centralized in utils.js (SSOT)

let currentShopCategory = 'full';
let cachedPlansData = null;

function switchShopCategory(cat, shouldRender = true) {
  if (cat) {
    if (shouldRender) window._shopCategoryManuallyChanged = true;
    currentShopCategory = cat;
  }
  const activeClass = 'flex-1 py-1.5 px-2 rounded-xl font-bold transition flex items-center justify-center gap-1 bg-blue-600 text-white shadow';
  const inactiveClass = 'flex-1 py-1.5 px-2 rounded-xl font-medium transition flex items-center justify-center gap-1 t-muted hover:t-main';
  ['full', 'traffic', 'time', 'custom'].forEach(c => {
    const btn = document.getElementById(`shopCategoryBtn-${c}`);
    if (btn) {
      btn.className = (c === currentShopCategory) ? activeClass : inactiveClass;
    }
  });

  const noticeEl = document.getElementById('shopSmartNotice');
  if (noticeEl) {
    if (currentShopCategory !== 'full') {
      noticeEl.classList.add('hidden');
    } else if (noticeEl.dataset.shouldShow === 'true') {
      noticeEl.classList.remove('hidden');
    }
  }

  // Tunnel Stability Banner permanently hidden per UX simplification
  const tunnelBanner = document.getElementById('shopTunnelStabilityBanner');
  if (tunnelBanner) {
    tunnelBanner.classList.add('hidden');
  }

  const customContainer = document.getElementById('customPlanBuilderContainer');
  const shopContainer = document.getElementById('shopPlansContainer');
  const couponSection = document.getElementById('shopCouponSection');

  if (currentShopCategory === 'custom') {
    if (customContainer) customContainer.classList.remove('hidden');
    if (shopContainer) shopContainer.classList.add('hidden');
    if (couponSection) couponSection.classList.add('hidden');
    const customSettings = cachedPlansData?.custom_plan_settings || window.storeSettings?.custom_plan_settings || {};
    const disabledNotice = document.getElementById('customPlanDisabledNotice');
    const builderContent = document.getElementById('customPlanBuilderContent');
    if (customSettings.enabled === false) {
      if (disabledNotice) disabledNotice.classList.remove('hidden');
      if (builderContent) builderContent.classList.add('hidden');
    } else {
      if (disabledNotice) disabledNotice.classList.add('hidden');
      if (builderContent) builderContent.classList.remove('hidden');
      initCustomPlanBuilder();
    }
    return;
  } else {
    if (customContainer) customContainer.classList.add('hidden');
    if (shopContainer) shopContainer.classList.remove('hidden');
  }

  if (shouldRender && cachedPlansData) {
    renderFilteredShopPlans();
  }
}
window.switchShopCategory = switchShopCategory;

let _customPlanBuilderInitialized = false;
let _calcDebounce = null;

function initCustomPlanBuilder() {
  const gbSlider = document.getElementById('customPlanGbSlider');
  const daysSlider = document.getElementById('customPlanDaysSlider');
  const hwidSlider = document.getElementById('customPlanHwidSlider');
  if (!gbSlider || !daysSlider) return;

  const settings = cachedPlansData?.custom_plan_settings || window.storeSettings?.custom_plan_settings || {};
  if (settings.min_gb) {
    gbSlider.min = settings.min_gb;
  }
  if (settings.max_gb) {
    gbSlider.max = settings.max_gb;
  }
  if (settings.min_days) {
    daysSlider.min = settings.min_days;
  }
  if (settings.max_days) {
    daysSlider.max = settings.max_days;
  }

  if (!_customPlanBuilderInitialized) {
    _customPlanBuilderInitialized = true;
    ['input', 'change'].forEach(evt => {
      gbSlider.addEventListener(evt, () => updateCustomPlanCalculation());
      daysSlider.addEventListener(evt, () => updateCustomPlanCalculation());
      if (hwidSlider) hwidSlider.addEventListener(evt, () => updateCustomPlanCalculation());
    });
  }

  updateCustomPlanCalculation();
}

async function updateCustomPlanCalculation() {
  const gbSlider = document.getElementById('customPlanGbSlider');
  const daysSlider = document.getElementById('customPlanDaysSlider');
  const hwidSlider = document.getElementById('customPlanHwidSlider');
  if (!gbSlider || !daysSlider) return;

  const gb = Number(gbSlider.value || 30);
  const days = Number(daysSlider.value || 30);
  const hwid = Number(hwidSlider?.value || 2);

  const valGbEl = document.getElementById('customPlanGbVal');
  const valDaysEl = document.getElementById('customPlanDaysVal');
  const valHwidEl = document.getElementById('customPlanHwidVal');
  if (valGbEl) valGbEl.innerText = gb;
  if (valDaysEl) valDaysEl.innerText = days;
  if (valHwidEl) valHwidEl.innerText = hwid;

  // Instantaneous 60fps client-side calculation
  const settings = cachedPlansData?.custom_plan_settings || window.storeSettings?.custom_plan_settings || {};
  const pricePerGb = Number(settings.price_per_gb || 0);
  const pricePerDay = Number(settings.price_per_day || 0);
  const baseFixed = Number(settings.base_price || 0);
  const isConfigured = Boolean(pricePerGb > 0 || pricePerDay > 0 || baseFixed > 0);
  const loyalty = cachedPlansData?.loyalty || window.lastUserData?.loyalty || {};
  const loyaltyPct = Number(loyalty.discount_percent || 0);

  const baseEl = document.getElementById('customPlanBasePriceDisplay');
  const discRow = document.getElementById('customPlanDiscountRow');
  const discEl = document.getElementById('customPlanDiscountDisplay');
  const finalEl = document.getElementById('customPlanFinalPrice');
  const pill = document.getElementById('customPlanLoyaltyDiscountPill');
  const pctEl = document.getElementById('customPlanLoyaltyPct');
  const submitBtn = document.getElementById('submitCustomPlanBtn');

  if (isConfigured) {
    let volPct = 0;
    let vTiers = null;
    try {
      if (settings.volume_tiers_json) vTiers = JSON.parse(settings.volume_tiers_json);
      else if (Array.isArray(settings.volume_tiers)) vTiers = settings.volume_tiers;
    } catch (_) {}

    if (Array.isArray(vTiers) && vTiers.length > 0) {
      for (const t of vTiers) {
        const minG = Number(t.min_gb || 0);
        const maxG = Number(t.max_gb || 999999);
        if (gb >= minG && gb <= maxG) {
          volPct = Math.max(0, Math.min(100, Number(t.discount_percent || 0)));
          break;
        }
      }
    } else {
      if (gb >= 51 && gb <= 100) volPct = 10;
      else if (gb >= 101 && gb <= 200) volPct = 20;
      else if (gb > 200) volPct = 30;
    }

    const extraDevicePercent = Number(settings.extra_device_percent || 15);
    const extraUserPct = Math.max(0, hwid - 1) * extraDevicePercent;
    const rawTraffic = gb * pricePerGb;
    const rawSubtotal = rawTraffic + (days * pricePerDay) + baseFixed;
    const discountedTraffic = Math.floor(rawTraffic * (100 - volPct) / 100);
    const discountedSubtotal = discountedTraffic + (days * pricePerDay) + baseFixed;
    const localVolDiscAmt = Math.max(0, rawTraffic - discountedTraffic);
    const localHwidCost = Math.floor(discountedSubtotal * extraUserPct / 100);
    const localBase = discountedSubtotal + localHwidCost;
    const localDisc = Math.floor((localBase * loyaltyPct) / 100);
    const localFinal = Math.max(0, localBase - localDisc);

    if (baseEl) baseEl.innerHTML = `<span dir="ltr" class="font-sans num-bidi">${Number(rawSubtotal).toLocaleString('en-US')}</span> تومان`;

    const hwidRow = document.getElementById('customPlanHwidCostRow');
    const hwidCostDisplay = document.getElementById('customPlanHwidCostDisplay');
    const hwidCountDisplay = document.getElementById('customPlanHwidCountDisplay');
    if (hwid > 1 && localHwidCost > 0) {
      if (hwidRow) hwidRow.classList.remove('hidden');
      if (hwidCountDisplay) hwidCountDisplay.innerText = hwid;
      if (hwidCostDisplay) hwidCostDisplay.innerHTML = `<span dir="ltr" class="font-sans num-bidi">+${Number(localHwidCost).toLocaleString('en-US')}</span> تومان`;
    } else {
      if (hwidRow) hwidRow.classList.add('hidden');
    }

    const volRow = document.getElementById('customPlanVolumeDiscountRow');
    const volEl = document.getElementById('customPlanVolumeDiscountDisplay');
    const volTierPct = document.getElementById('customPlanVolumeTierPct');
    const volBadge = document.getElementById('customPlanVolumeBadge');
    const volPctVal = document.getElementById('customPlanVolumePct');

    if (volPct > 0) {
      if (volRow) volRow.classList.remove('hidden');
      if (volTierPct) volTierPct.innerText = volPct;
      if (volEl) volEl.innerHTML = `<span dir="ltr" class="font-sans num-bidi">-${Number(localVolDiscAmt).toLocaleString('en-US')}</span> تومان`;
      if (volBadge) volBadge.classList.remove('hidden');
      if (volPctVal) volPctVal.innerText = volPct;
    } else {
      if (volRow) volRow.classList.add('hidden');
      if (volBadge) volBadge.classList.add('hidden');
    }

    if (localDisc > 0) {
      if (discRow) discRow.classList.remove('hidden');
      const discPctEl = document.getElementById('customPlanDiscountPct');
      if (discPctEl) discPctEl.innerText = loyaltyPct;
      if (discEl) discEl.innerHTML = `<span dir="ltr" class="font-sans num-bidi">-${Number(localDisc).toLocaleString('en-US')}</span> تومان`;
    } else {
      if (discRow) discRow.classList.add('hidden');
    }
    if (finalEl) finalEl.innerText = Number(localFinal).toLocaleString('en-US');
    if (loyaltyPct > 0) {
      if (pill) pill.classList.remove('hidden');
      if (pctEl) pctEl.innerText = loyaltyPct;
    } else {
      if (pill) pill.classList.add('hidden');
    }
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.classList.remove('opacity-50', 'cursor-not-allowed');
      submitBtn.innerText = `خرید بسته دلخواه (${Number(localFinal).toLocaleString('en-US')} تومان)`;
    }
  } else {
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.classList.add('opacity-50', 'cursor-not-allowed');
      submitBtn.innerText = 'تعرفه بسته دلخواه هنوز تعریف نشده است';
    }
  }

  // Debounced server confirmation
  if (_calcDebounce) clearTimeout(_calcDebounce);
  _calcDebounce = setTimeout(async () => {
    try {
      const res = await window.api.calculateCustomPlan(gb, days, hwid);
      if (res && res.ok && res.data) {
        const d = res.data;
        if (baseEl) baseEl.innerHTML = `<span dir="ltr" class="font-sans num-bidi">${Number(d.base_subtotal != null ? (d.base_subtotal + (d.volume_discount_amount || 0)) : (d.raw_base_price || d.base_price)).toLocaleString('en-US')}</span> تومان`;

        const hwidRow = document.getElementById('customPlanHwidCostRow');
        const hwidCostDisplay = document.getElementById('customPlanHwidCostDisplay');
        const hwidCountDisplay = document.getElementById('customPlanHwidCountDisplay');
        const hwidCost = Number(d.hwid_cost || 0);
        if (d.hwid_limit > 1 && hwidCost > 0) {
          if (hwidRow) hwidRow.classList.remove('hidden');
          if (hwidCountDisplay) hwidCountDisplay.innerText = d.hwid_limit;
          if (hwidCostDisplay) hwidCostDisplay.innerHTML = `<span dir="ltr" class="font-sans num-bidi">+${Number(hwidCost).toLocaleString('en-US')}</span> تومان`;
        } else {
          if (hwidRow) hwidRow.classList.add('hidden');
        }

        const volRow = document.getElementById('customPlanVolumeDiscountRow');
        const volEl = document.getElementById('customPlanVolumeDiscountDisplay');
        const volTierPct = document.getElementById('customPlanVolumeTierPct');
        const volBadge = document.getElementById('customPlanVolumeBadge');
        const volPctVal = document.getElementById('customPlanVolumePct');

        if (d.volume_discount_percent > 0) {
          if (volRow) volRow.classList.remove('hidden');
          if (volTierPct) volTierPct.innerText = d.volume_discount_percent;
          if (volEl) volEl.innerHTML = `<span dir="ltr" class="font-sans num-bidi">-${Number(d.volume_discount_amount).toLocaleString('en-US')}</span> تومان`;
          if (volBadge) volBadge.classList.remove('hidden');
          if (volPctVal) volPctVal.innerText = d.volume_discount_percent;
        } else {
          if (volRow) volRow.classList.add('hidden');
          if (volBadge) volBadge.classList.add('hidden');
        }

        if (d.loyalty_discount_amount > 0) {
          if (discRow) discRow.classList.remove('hidden');
          if (discEl) discEl.innerHTML = `<span dir="ltr" class="font-sans num-bidi">-${Number(d.loyalty_discount_amount).toLocaleString('en-US')}</span> تومان <span dir="ltr" class="font-sans font-bold num-bidi">(${d.loyalty_discount_percent}%)</span>`;
        } else {
          if (discRow) discRow.classList.add('hidden');
        }
        if (finalEl) finalEl.innerText = Number(d.final_price).toLocaleString('en-US');
        if (d.loyalty_discount_percent > 0) {
          if (pill) pill.classList.remove('hidden');
          if (pctEl) pctEl.innerText = d.loyalty_discount_percent;
        } else {
          if (pill) pill.classList.add('hidden');
        }

        const isPricingValid = Boolean(d.is_configured !== false && d.final_price > 0);
        if (submitBtn) {
          submitBtn.disabled = !isPricingValid;
          submitBtn.classList.toggle('opacity-50', !isPricingValid);
          submitBtn.classList.toggle('cursor-not-allowed', !isPricingValid);
          if (!isPricingValid) {
            submitBtn.innerText = 'تعرفه بسته دلخواه هنوز تعریف نشده است';
          } else {
            submitBtn.innerText = `خرید بسته دلخواه (${Number(d.final_price).toLocaleString('en-US')} تومان)`;
          }
        }
      }
    } catch (e) {
      console.warn('Error calculating custom plan:', e);
    }
  }, 120);
}

function purchaseCustomPlan() {
  const gb = Number(document.getElementById('customPlanGbSlider')?.value || 30);
  const days = Number(document.getElementById('customPlanDaysSlider')?.value || 30);
  const hwid = Number(document.getElementById('customPlanHwidSlider')?.value || 2);
  const finalPriceEl = document.getElementById('customPlanFinalPrice');
  const finalPriceText = finalPriceEl ? finalPriceEl.innerText.replace(/[^0-9]/g, '') : '';
  const finalPrice = Number(finalPriceText) || 0;

  const customPlanObj = {
    id: 'custom',
    isCustom: true,
    name: 'بسته دلخواه',
    price: finalPrice,
    traffic: gb,
    days: days,
    hwid_limit: hwid,
    badge: 'custom',
    gb: gb,
  };

  openCheckoutConfirmModal(customPlanObj);
}
window.purchaseCustomPlan = purchaseCustomPlan;

function renderShopPlans(data) {
  cachedPlansData = data;
  renderWonCoupons(data);
  const shopBalAmt = document.getElementById('shopWalletBalanceAmount');
  if (shopBalAmt && data?.user?.wallet_balance !== undefined) {
    shopBalAmt.innerText = Number(data.user.wallet_balance || 0).toLocaleString('en-US');
  }

  const customSettings = data?.custom_plan_settings || window.storeSettings?.custom_plan_settings;
  const customBtn = document.getElementById('shopCategoryBtn-custom');
  if (customBtn) {
    customBtn.classList.remove('hidden');
  }

  // Smart User Routing & Recommendation Banner
  const sub = window.lastUserData?.active_subscription;
  const hasActiveSub = Boolean(window.lastUserData?.has_active_sub && sub && (sub.status === 'ACTIVE' || !sub.status));
  const daysLeft = Number(sub?.days_left ?? 0);
  const pctRemaining = Number(sub?.percent_remaining ?? 100);

  const noticeEl = document.getElementById('shopSmartNotice');
  if (noticeEl) {
    if (!hasActiveSub) {
      noticeEl.className = 'p-2.5 rounded-2xl text-[11px] leading-relaxed mb-1 transition flex items-center gap-2 s-accent-soft';
      noticeEl.innerHTML = '<div class="flex items-start gap-2"><div class="flex flex-col gap-0.5"><span class="font-bold">جهت شروع، یکی از <b>سرویس‌های کامل</b> را انتخاب فرمایید.</span><span class="text-[10px] sm:text-[10.5px] opacity-85 whitespace-nowrap overflow-hidden text-ellipsis block">در صورت کندی اینترنت، بسته‌های تانل اختصاصی پیشنهاد می‌شود.</span></div></div>';
      noticeEl.dataset.shouldShow = 'true';
      if (currentShopCategory === 'full') noticeEl.classList.remove('hidden');
      else noticeEl.classList.add('hidden');
      if (!window._shopCategoryManuallyChanged) currentShopCategory = 'full';
    } else if (daysLeft > 3 && pctRemaining <= 25) {
      noticeEl.className = 'p-2.5 rounded-2xl text-[11px] leading-relaxed mb-1 transition flex items-center gap-2 s-accent-soft border';
      noticeEl.innerHTML = `<span>⚡️</span><span>شما هنوز <b>${daysLeft} روز</b> اشتراک فعال دارید؛ خرید <b>بسته افزایش حجم</b> مانع از سوختن روزهای باقیمانده شما می‌شود.</span>`;
      noticeEl.dataset.shouldShow = 'true';
      if (currentShopCategory === 'traffic') noticeEl.classList.remove('hidden');
      else noticeEl.classList.add('hidden');
      if (!window._shopCategoryManuallyChanged) currentShopCategory = 'traffic';
    } else if (daysLeft <= 3) {
      noticeEl.className = 'p-2.5 rounded-2xl text-[11px] leading-relaxed mb-1 transition flex items-center gap-2 s-warn-soft border';
      noticeEl.innerHTML = `<span>⏳</span><span>تنها <b>${daysLeft} روز</b> از اشتراک شما باقیمانده است؛ جهت جلوگیری از قطعی، <b>خرید یا تمدید دوره کامل</b> پیشنهاد می‌شود.</span>`;
      noticeEl.dataset.shouldShow = 'true';
      if (currentShopCategory === 'full') noticeEl.classList.remove('hidden');
      else noticeEl.classList.add('hidden');
      if (!window._shopCategoryManuallyChanged) currentShopCategory = 'full';
    } else {
      noticeEl.dataset.shouldShow = 'false';
      noticeEl.classList.add('hidden');
    }
  }

  switchShopCategory(currentShopCategory, false);
  renderFilteredShopPlans();
}

function renderFilteredShopPlans() {
  const shopContainer = document.getElementById('shopPlansContainer');
  const couponSection = document.getElementById('shopCouponSection');
  const allPlans = cachedPlansData?.plans || [];
  if (!shopContainer) return;

  if (allPlans.length === 0) {
    shopContainer.innerHTML = `
      <div class="py-8 px-4 rounded-2xl card-inset text-center space-y-2">
        <span class="text-3xl block">📦</span>
        <b class="text-xs t-main block">در حال حاضر بسته‌ای برای خرید موجود نیست</b>
        <p class="text-[11px] t-muted">لطفاً بعداً مراجعه فرمایید یا با پشتیبانی در ارتباط باشید.</p>
      </div>
    `;
    if (couponSection) couponSection.classList.add('hidden');
    return;
  }

  if (couponSection) couponSection.classList.remove('hidden');

  const plans = allPlans.filter(p => {
    const b = (p.badge || '').toLowerCase();
    const isTraffic = (b === 'traffic' || (Number(p.duration_days) === 0 && Number(p.traffic_gb) > 0)) && b !== 'time';
    const isTime = !isTraffic && (b === 'time' || (Number(p.traffic_gb) === 0 && Number(p.duration_days) > 0 && b !== 'traffic'));
    if (currentShopCategory === 'traffic') return isTraffic;
    if (currentShopCategory === 'time') return isTime;
    return !isTraffic && !isTime; // 'full'
  });

  if (plans.length === 0) {
    const catLabels = { traffic: 'افزایش حجم', time: 'افزایش زمان', full: 'سرویس‌های کامل' };
    const curLabel = catLabels[currentShopCategory] || 'این دسته‌بندی';
    shopContainer.innerHTML = `
      <div class="py-8 px-4 rounded-2xl card-inset text-center space-y-3">
        <span class="text-3xl block">🔍</span>
        <b class="text-xs t-main block">بسته‌ای در بخش «${curLabel}» یافت نشد</b>
        <p class="text-[11px] t-muted">می‌توانید سایر سرویس‌های فعال را بررسی نمایید.</p>
        <button type="button" onclick="window.switchShopCategory('full')" class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs transition shadow active:scale-95 mx-auto">
          مشاهده سرویس‌های کامل
        </button>
      </div>
    `;
    return;
  }

  shopContainer.innerHTML = plans.map(p => {
    const planText = `${p.name || ''} ${p.description || ''}`.toLowerCase();
    const planBadgeKey = (p.badge || '').toLowerCase().trim();
    const isTimeOnly = (Number(p.traffic_gb) === 0 && Number(p.duration_days) > 0) || (planBadgeKey === 'time' && Number(p.traffic_gb) === 0);
    const isExtraTraffic = ((Number(p.duration_days) === 0 && Number(p.traffic_gb) > 0) || planBadgeKey === 'traffic') && !isTimeOnly;

    let planBadge = '';
    let badgeBorderClass = 'border-slate-700/80';
    let btnClass = 'btn-plan-default';

    const badgeIcon = (name) => (typeof uiIcon === 'function' ? uiIcon(name, 'w-3.5 h-3.5') : '');
    const iranFlagBadge = typeof renderFlagHtml === 'function'
      ? renderFlagHtml('IR', 'w-3.5 h-2.5 inline-block rounded-[2px] object-cover shrink-0')
      : '🇮🇷';

    if (isExtraTraffic) {
      planBadge = `<div class="shop-plan-badge badge-traffic absolute top-0 left-0 bg-gradient-to-r from-cyan-600 to-blue-600 text-white text-[11px] font-semibold px-3 py-0.5 rounded-br-xl shadow flex items-center gap-1">${badgeIcon('zap')}<span>بسته افزایش حجم</span></div>`;
      badgeBorderClass = 'border-cyan-500/50 shadow-lg shadow-cyan-500/10';
      btnClass = 'btn-plan-traffic';
    } else if (isTimeOnly) {
      planBadge = `<div class="shop-plan-badge badge-traffic absolute top-0 left-0 bg-gradient-to-r from-cyan-600 to-blue-600 text-white text-[11px] font-semibold px-3 py-0.5 rounded-br-xl shadow flex items-center gap-1">${badgeIcon('clock')}<span>بسته افزایش زمان</span></div>`;
      badgeBorderClass = 'border-cyan-500/50 shadow-lg shadow-cyan-500/10';
      btnClass = 'btn-plan-traffic';
    } else if (planBadgeKey === 'vip' || (!planBadgeKey && (planText.includes('پیشنهاد ویژه') || planText.includes('vip')))) {
      planBadge = `<div class="shop-plan-badge badge-vip absolute top-0 left-0 bg-gradient-to-r from-rose-500 via-pink-500 to-purple-500 text-white text-[11px] font-semibold px-3 py-0.5 rounded-br-xl border-b border-r border-rose-300/70 shadow-lg shadow-rose-500/30 flex items-center gap-1">${badgeIcon('crown')}<span>پیشنهاد ویژه</span></div>`;
      badgeBorderClass = 'border-rose-500/70 shadow-lg shadow-rose-500/20';
      btnClass = 'btn-plan-vip';
    } else if (planBadgeKey === 'bestseller' || planBadgeKey.includes('پرفروش') || (!planBadgeKey && (planText.includes('پرفروش') || planText.includes('bestseller')))) {
      planBadge = `<div class="shop-plan-badge badge-bestseller absolute top-0 left-0 bg-gradient-to-r from-amber-500 via-orange-500 to-amber-600 text-white text-[11px] font-semibold px-3 py-0.5 rounded-br-xl border-b border-r border-amber-300/80 shadow-lg shadow-amber-500/30 flex items-center gap-1">${badgeIcon('flame')}<span>پرفروش‌ترین</span></div>`;
      badgeBorderClass = 'border-amber-400/80 shadow-lg shadow-amber-500/25';
      btnClass = 'btn-plan-bestseller';
    } else if (planBadgeKey === 'popular' || (!planBadgeKey && (planText.includes('محبوب') || planText.includes('popular')))) {
      planBadge = `<div class="shop-plan-badge badge-popular absolute top-0 left-0 bg-gradient-to-r from-purple-600 via-indigo-600 to-blue-600 text-white text-[11px] font-semibold px-3 py-0.5 rounded-br-xl border-b border-r border-indigo-400/40 shadow-md flex items-center gap-1">${badgeIcon('star')}<span>محبوب‌ترین</span></div>`;
      badgeBorderClass = 'border-purple-500/70 shadow-lg shadow-purple-500/15';
      btnClass = 'btn-plan-popular';
    } else if (planBadgeKey === 'economic' || (!planBadgeKey && (planText.includes('اقتصادی') || planText.includes('economic') || planText.includes('به‌صرفه') || planText.includes('بصرفه') || planText.includes('ارزان')))) {
      planBadge = `<div class="shop-plan-badge badge-economic absolute top-0 left-0 bg-gradient-to-r from-emerald-600 to-teal-600 text-white text-[11px] font-semibold px-3 py-0.5 rounded-br-xl border-b border-r border-emerald-400/40 shadow-md flex items-center gap-1">${badgeIcon('coins')}<span>اقتصادی‌ترین</span></div>`;
      badgeBorderClass = 'border-emerald-500/70 shadow-lg shadow-emerald-500/15';
      btnClass = 'btn-plan-economic';
    } else if (planBadgeKey === 'tunnel' || (!planBadgeKey && (planText.includes('تانل') || planText.includes('tunnel')))) {
      planBadge = `<div class="shop-plan-badge badge-tunnel absolute top-0 left-0 bg-gradient-to-r from-teal-600 via-cyan-600 to-sky-600 text-white text-[11px] font-semibold px-3 py-0.5 rounded-br-xl border-b border-r border-cyan-400/50 shadow-md flex items-center gap-1">${badgeIcon('route')}<span>تانل اختصاصی</span></div>`;
      badgeBorderClass = 'border-cyan-500/70 shadow-lg shadow-cyan-500/20';
      btnClass = 'bg-gradient-to-r from-teal-600 via-cyan-600 to-sky-600 hover:from-teal-500 hover:to-sky-500 text-white font-bold shadow-md shadow-cyan-600/25';
    } else if (planBadgeKey === 'gaming' || (!planBadgeKey && (planText.includes('گیم') || planText.includes('gaming')))) {
      planBadge = `<div class="shop-plan-badge badge-gaming absolute top-0 left-0 bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 text-white text-[11px] font-semibold px-3 py-0.5 rounded-br-xl border-b border-r border-indigo-400/50 shadow-md flex items-center gap-1">${badgeIcon('gamepad')}<span>ویژه گیمینگ</span></div>`;
      badgeBorderClass = 'border-indigo-500/70 shadow-lg shadow-indigo-500/20';
      btnClass = 'btn-plan-gaming';
    } else if (planBadgeKey === 'antifilter' || (!planBadgeKey && (planText.includes('ضد فیلتر') || planText.includes('ضدفیلتر')))) {
      planBadge = `<div class="shop-plan-badge badge-antifilter absolute top-0 left-0 bg-gradient-to-r from-teal-600 to-emerald-600 text-white text-[11px] font-semibold px-3 py-0.5 rounded-br-xl border-b border-r border-teal-400/50 shadow-md flex items-center gap-1">${badgeIcon('shield')}<span>ضد فیلتر</span></div>`;
      badgeBorderClass = 'border-teal-500/70 shadow-lg shadow-teal-500/20';
      btnClass = 'bg-gradient-to-r from-teal-600 to-emerald-600 hover:from-teal-500 hover:to-emerald-500 text-white font-bold shadow-md shadow-teal-600/20';
    } else if (planBadgeKey === 'speed' || (!planBadgeKey && (planText.includes('فوق سریع') || planText.includes('گیگابیت')))) {
      planBadge = `<div class="shop-plan-badge badge-speed absolute top-0 left-0 bg-gradient-to-r from-amber-500 via-yellow-500 to-orange-500 text-white text-[11px] font-semibold px-3 py-0.5 rounded-br-xl border-b border-r border-amber-300/60 shadow-md flex items-center gap-1">${badgeIcon('zap')}<span>فوق سریع</span></div>`;
      badgeBorderClass = 'border-amber-500/70 shadow-lg shadow-amber-500/20';
      btnClass = 'bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-white font-bold shadow-md shadow-amber-600/20';
    } else if (planBadgeKey === 'stream' || (!planBadgeKey && (planText.includes('استریم') || planText.includes('یوتیوب')))) {
      planBadge = `<div class="shop-plan-badge badge-stream absolute top-0 left-0 bg-gradient-to-r from-red-600 to-rose-600 text-white text-[11px] font-semibold px-3 py-0.5 rounded-br-xl border-b border-r border-red-400/50 shadow-md flex items-center gap-1">${badgeIcon('play')}<span>ویژه استریم</span></div>`;
      badgeBorderClass = 'border-red-500/70 shadow-lg shadow-red-500/20';
      btnClass = 'bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 text-white font-bold shadow-md shadow-red-600/20';
    } else if (planBadgeKey === 'family' || (!planBadgeKey && (planText.includes('خانوادگی') || planText.includes('چند کاربر')))) {
      planBadge = `<div class="shop-plan-badge badge-family absolute top-0 left-0 bg-gradient-to-r from-sky-600 to-blue-600 text-white text-[11px] font-semibold px-3 py-0.5 rounded-br-xl border-b border-r border-sky-400/50 shadow-md flex items-center gap-1">${badgeIcon('users')}<span>چند کاربره</span></div>`;
      badgeBorderClass = 'border-sky-500/70 shadow-lg shadow-sky-500/20';
      btnClass = 'btn-plan-family';
    } else if (planBadgeKey === 'iran' || (!planBadgeKey && planText.includes('سرور ایران'))) {
      planBadge = `<div class="shop-plan-badge badge-iran absolute top-0 left-0 text-white text-[11px] font-semibold px-3 py-0.5 rounded-br-xl flex items-center gap-1">${iranFlagBadge}<span>سرور ایران</span></div>`;
      badgeBorderClass = 'border-emerald-500/70 shadow-lg shadow-red-500/15';
      btnClass = 'btn-plan-iran';
    }

    const hasLoyaltyDiscount = Boolean(p.loyalty_discount_percent && p.loyalty_discount_percent > 0 && p.original_price && p.original_price > p.price);
    const originalPriceToDisplay = hasLoyaltyDiscount ? p.original_price : p.price;

    let discountVal = 0;
    if (window.activeCoupon) {
      if (window.activeCoupon.discount_percent > 0) {
        discountVal = Math.round(p.price * window.activeCoupon.discount_percent / 100);
      } else if (window.activeCoupon.discount_amount > 0) {
        discountVal = window.activeCoupon.discount_amount;
      }
    }
    const finalPrice = Math.max(0, p.price - discountVal);
    const hasAnyDiscount = hasLoyaltyDiscount || (discountVal > 0);
    const formattedFinal = Number(finalPrice).toLocaleString('en-US');
    const formattedOriginal = Number(originalPriceToDisplay || 0).toLocaleString('en-US');
    const devLimitText = (p.hwid_limit && p.hwid_limit > 0) ? `${p.hwid_limit} کاربر` : 'کاربر نامحدود';

    const durationText = isExtraTraffic
      ? '<span class="flex items-center gap-1">📅 <b class="text-emerald-700 dark:text-emerald-400 font-bold">بدون تغییر زمان انقضا</b></span>'
      : (isTimeOnly
          ? `<span class="flex items-center gap-1">📅 <b class="t-accent font-bold">${p.duration_days} روز اضافه</b></span>`
          : (Number(p.duration_days) > 0
              ? `<span class="flex items-center gap-1">📅 <b class="t-main">${p.duration_days} روز</b></span>`
              : '<span class="flex items-center gap-1">📅 <b class="t-main">نامحدود روز</b></span>'));
    const trafficText = isTimeOnly
      ? '<span class="t-accent font-bold">بدون تغییر حجم</span>'
      : (Number(p.traffic_gb) > 0 ? fmtTraffic(p.traffic_gb, { html: false }) : 'نامحدود');

    let buttonLabel = 'خرید / تمدید آنی';
    if (isExtraTraffic) buttonLabel = 'خرید بسته ترافیک';
    else if (isTimeOnly) buttonLabel = 'تمدید مدت زمان';

    const isTunnel = planBadgeKey === 'tunnel' || (!planBadgeKey && (planText.includes('تانل') || planText.includes('tunnel')));
    const rawDesc = p.description || (isExtraTraffic ? 'افزایش حجم بدون تغییر در تاریخ انقضای سرویس فعلی' : (isTimeOnly ? 'افزایش مدت زمان اعتبار بدون تغییر در میزان ترافیک' : (isTunnel ? 'ترافیک پایدار روی سرورها + تانل اختصاصی' : 'ترافیک پایدار روی سرورها')));
    const safeDesc = escapeHtml(rawDesc)
      .replace(/تانل\s+اختصاصی/g, 'تانل&nbsp;اختصاصی')
      .replace(/\+\s*تانل/g, '+&nbsp;تانل');

    const cleanFlags = (p.flags && Array.isArray(p.flags)) ? p.flags.filter(f => f && (p.flags.length === 1 || f !== '🌐')) : [];
    const clusterFlags = (cachedPlansData?.cluster_flags || window.lastUserData?.cluster_flags || []).filter(f => f && f !== '🌐');
    const isExplicitIranPlan = planBadgeKey === 'iran' || (!planBadgeKey && planText.includes('سرور ایران'));
    const activeFlags = cleanFlags.length > 0
      ? cleanFlags
      : (p.squad_uuid
          ? (isExplicitIranPlan ? ['🇮🇷'] : [])
          : clusterFlags);
    const flagsList = activeFlags.length > 0
      ? activeFlags.map(f => (typeof renderFlagHtml === 'function' ? renderFlagHtml(f, 'w-4 h-3 inline-block rounded-xs shadow-xs object-cover align-middle') : `<span class="text-xs inline-block" title="${f}">${f}</span>`)).join(' ')
      : '<span class="text-xs inline-block" title="سرور اختصاصی">🌐</span>';

    const userLoyalty = cachedPlansData?.loyalty || window.lastUserData?.loyalty;
    const userTierIcon = userLoyalty?.icon || '🥈';
    const loyaltyPctEnglish = toEnglishDigits(p.loyalty_discount_percent || userLoyalty?.discount_percent || 0);

    let tagThemeClass = 'badge-info';
    if (isExtraTraffic || isTimeOnly) {
      tagThemeClass = 'badge-accent';
    } else if (planBadgeKey === 'vip' || (!planBadgeKey && (planText.includes('پیشنهاد ویژه') || planText.includes('vip')))) {
      tagThemeClass = 'badge-danger';
    } else if (planBadgeKey === 'bestseller' || (!planBadgeKey && (planText.includes('پرفروش') || planText.includes('bestseller')))) {
      tagThemeClass = 'badge-warn';
    } else if (planBadgeKey === 'popular' || (!planBadgeKey && (planText.includes('محبوب') || planText.includes('popular')))) {
      tagThemeClass = 'badge-purple';
    } else if (planBadgeKey === 'economic' || (!planBadgeKey && (planText.includes('اقتصادی') || planText.includes('economic') || planText.includes('به‌صرفه') || planText.includes('بصرفه') || planText.includes('ارزان')))) {
      tagThemeClass = 'badge-success';
    } else if (planBadgeKey === 'tunnel' || (!planBadgeKey && (planText.includes('تانل') || planText.includes('tunnel')))) {
      tagThemeClass = 'badge-accent';
    } else if (planBadgeKey === 'gaming') {
      tagThemeClass = 'badge-purple';
    } else if (planBadgeKey === 'antifilter') {
      tagThemeClass = 'badge-success';
    } else if (planBadgeKey === 'speed') {
      tagThemeClass = 'badge-warn';
    } else if (planBadgeKey === 'stream') {
      tagThemeClass = 'badge-danger';
    } else if (planBadgeKey === 'family') {
      tagThemeClass = 'badge-info';
    } else if (planBadgeKey === 'iran' || (!planBadgeKey && planText.includes('سرور ایران'))) {
      tagThemeClass = 'badge-success';
    }

    const hasDiscountBadges = Boolean(discountVal > 0 || hasLoyaltyDiscount);
    return `
      <div class="shop-plan-card card p-3 border ${badgeBorderClass} relative overflow-hidden group">
        ${planBadge}
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0 flex-1 text-right">
            <div class="flex items-baseline justify-start gap-1.5 flex-wrap font-sans" dir="rtl">
              ${hasAnyDiscount ? `<span class="line-through t-muted text-[11px] font-semibold leading-none num-bidi" dir="ltr">${formattedOriginal}</span>` : ''}
              <span class="text-base font-black t-success leading-tight num-bidi" dir="ltr">${formattedFinal}</span>
              <span class="text-[11px] t-muted font-sans leading-none">تومان</span>
            </div>
            <p class="text-[10.5px] leading-snug t-muted text-right line-clamp-2 tracking-tight mt-1">${safeDesc}</p>
          </div>
          <div class="flex flex-col items-start min-w-0 shrink-0 max-w-[46%] ${planBadge ? 'mt-4' : ''}" dir="ltr">
            <div class="card-inset px-2.5 py-1 rounded-xl border border-card-border shadow-xs max-w-full">
              <h4 class="font-bold text-xs sm:text-sm t-main truncate text-left">${formatPlanTitle(p.name)}</h4>
            </div>
          </div>
        </div>
        ${hasDiscountBadges ? `
          <div class="flex items-center justify-start gap-1.5 flex-wrap mt-2.5 mb-2.5" dir="ltr">
            ${hasLoyaltyDiscount ? `<span class="badge ${tagThemeClass} text-[11px] font-sans num-bidi" title="تخفیف وفاداری"><span>${userTierIcon}</span><span>Loyality (-${loyaltyPctEnglish}%)</span></span>` : ''}
            ${discountVal > 0 ? `<span class="badge ${tagThemeClass} text-[11px] font-sans num-bidi"><span>🏷</span><span>${window.activeCoupon?.code ? escapeHtml(window.activeCoupon.code) : 'کوپن'} (-${toEnglishDigits(window.activeCoupon?.discount_percent || 0)}%)</span></span>` : ''}
          </div>
        ` : ''}
        <div class="flex items-center justify-between my-1.5 text-[11px] card-inset px-2.5 py-1.5 whitespace-nowrap overflow-hidden">
          <span class="flex items-center gap-1">📊 <b dir="ltr" class="font-sans t-main num-bidi">${trafficText}</b></span>
          ${durationText}
          <span class="flex items-center gap-1">📱 <b class="t-main">${devLimitText}</b></span>
        </div>
        <div class="flex items-center justify-between mb-1.5 px-1 text-[11px] t-muted">
          <span class="flex items-center gap-1">
            <span>🌍</span>
            <span>کشورها:</span>
          </span>
          <span class="inline-flex items-center gap-1 text-xs tracking-wider" dir="ltr">${flagsList}</span>
        </div>
        <button class="buy-plan-btn w-full ${btnClass} text-xs py-2 rounded-xl transition shadow active:scale-[0.98]" data-id="${p.id}" data-price="${finalPrice}" data-name="${p.name}" data-traffic="${p.traffic_gb}" data-days="${p.duration_days}" data-badge="${p.badge || ''}" data-squad="${p.squad_uuid || ''}">
          🛒 ${buttonLabel} (${formattedFinal} تومان)
        </button>
      </div>
    `;
  }).join('');

  setupBuyButtons();
}

function openCheckoutConfirmModal(plan) {
  currentPendingPlan = plan;
  const userBalance = window.lastUserData?.user?.wallet_balance || 0;
  const planPrice = plan.price;
  const isShortage = userBalance < planPrice;
  const shortageAmount = planPrice - userBalance;

  const modal = document.getElementById('checkoutConfirmModal');
  if (!modal) return;

  const nameEl = document.getElementById('checkoutPlanName');
  const trafEl = document.getElementById('checkoutPlanTraffic');
  const daysEl = document.getElementById('checkoutPlanDays');
  const priceEl = document.getElementById('checkoutPlanPrice');
  const balEl = document.getElementById('checkoutWalletBalance');
  const remRow = document.getElementById('checkoutRemainRow');
  const remBalEl = document.getElementById('checkoutRemainingBalance');
  const shortageBox = document.getElementById('checkoutShortageBox');
  const shortageAmtEl = document.getElementById('checkoutShortageAmount');
  const topupBtn = document.getElementById('checkoutTopupBtn');
  const confirmBtn = document.getElementById('confirmPurchaseBtn');

  const isExtraTraffic = (Number(plan.days) === 0 && Number(plan.traffic) > 0) || (plan.badge || '').toLowerCase() === 'traffic';
  const isTimeOnly = (Number(plan.traffic) === 0 && Number(plan.days) > 0) || (plan.badge || '').toLowerCase() === 'time';

  if (nameEl) nameEl.innerHTML = formatPlanTitle(plan.name);
  if (trafEl) {
    if (isTimeOnly) {
      trafEl.innerText = 'بدون تغییر حجم فعلی';
    } else {
      trafEl.innerText = fmtTraffic(plan.traffic, { html: false });
    }
  }
  if (daysEl) {
    if (isExtraTraffic) {
      const activeSub = window.lastUserData?.active_sub || window.lastUserData?.active_subscription;
      const daysLeft = Number(activeSub?.days_left ?? 0);
      if (daysLeft > 0) {
        daysEl.innerText = `هم‌گام با سرویس فعلی (${daysLeft} روز مانده)`;
      } else {
        daysEl.innerText = 'بدون تغییر زمان انقضا';
      }
    } else if (isTimeOnly) {
      daysEl.innerText = `${plan.days} روز اضافه به سرویس`;
    } else if (Number(plan.days) > 0) {
      daysEl.innerText = `${plan.days} روز`;
    } else {
      daysEl.innerText = 'نامحدود روز';
    }
  }
  if (priceEl) priceEl.innerText = `${Number(planPrice).toLocaleString('en-US')} تومان`;
  if (balEl) balEl.innerText = `${Number(userBalance).toLocaleString('en-US')} تومان`;

  const hwidEl = document.getElementById('checkoutPlanHwid');
  const hwidRow = document.getElementById('checkoutPlanHwidRow');
  if (hwidEl && hwidRow) {
    if (plan.hwid_limit || plan.isCustom) {
      hwidRow.classList.remove('hidden');
      hwidEl.innerText = `${plan.hwid_limit || 2} کاربر`;
    } else {
      hwidRow.classList.add('hidden');
    }
  }

  const switchBox = document.getElementById('checkoutSwitchWarningBox');
  const activeSub = window.lastUserData?.active_sub || window.lastUserData?.active_subscription;
  const activeSquad = (activeSub?.squad_uuid || '').trim().toLowerCase();
  const planSquadNorm = (plan.squad_uuid || '').trim().toLowerCase();
  const isSwitch = Boolean(
    activeSub &&
    !isExtraTraffic &&
    !isTimeOnly &&
    planSquadNorm &&
    (!activeSquad || planSquadNorm !== activeSquad)
  );

  if (switchBox) {
    if (isSwitch) {
      switchBox.classList.remove('hidden');
    } else {
      switchBox.classList.add('hidden');
    }
  }

  if (isShortage) {
    if (remRow) remRow.classList.add('hidden');
    if (shortageBox) shortageBox.classList.remove('hidden');
    if (shortageAmtEl) shortageAmtEl.innerText = `${Number(shortageAmount).toLocaleString('en-US')} تومان`;
    if (topupBtn) {
      topupBtn.classList.remove('hidden');
      topupBtn.onclick = () => {
        closeModal('checkoutConfirmModal');
        if (typeof openTopupModal === 'function') openTopupModal(shortageAmount);
      };
    }
    if (confirmBtn) confirmBtn.classList.add('hidden');
  } else {
    if (shortageBox) shortageBox.classList.add('hidden');
    if (topupBtn) topupBtn.classList.add('hidden');
    if (remRow) remRow.classList.remove('hidden');
    if (remBalEl) remBalEl.innerText = `${Number(userBalance - planPrice).toLocaleString('en-US')} تومان`;
    if (confirmBtn) {
      confirmBtn.classList.remove('hidden');
      confirmBtn.disabled = false;
      confirmBtn.innerText = isSwitch ? '✅ تایید و ارتقای سرور' : '✅ تایید و خرید آنی';
      confirmBtn.onclick = executePurchase;
    }
  }

  openModal('checkoutConfirmModal');
}

function openShopGuidanceModal({ title, badgeText, badgeClass, message, actionText, onAction, secondaryText = 'انصراف', onSecondary = null }) {
  const modal = document.getElementById('shopGuidanceModal');
  if (!modal) return;

  const tEl = document.getElementById('shopGuidanceTitle');
  const bEl = document.getElementById('shopGuidanceBadge');
  const txtEl = document.getElementById('shopGuidanceText');
  const actBtn = document.getElementById('shopGuidanceActionBtn');
  const secBtn = document.getElementById('shopGuidanceSecondaryBtn');

  if (tEl) tEl.innerText = title || 'راهنمای انتخاب بسته';
  if (bEl) {
    bEl.innerText = badgeText || '⚡️ پیشنهاد هوشمند';
    bEl.className = badgeClass || 'px-2.5 py-0.5 rounded-full text-[11px] font-bold s-accent-soft border border-cyan-500/30';
  }
  if (txtEl) txtEl.innerHTML = message || '';

  if (actBtn) {
    actBtn.innerText = actionText || 'تایید و ادامه';
    actBtn.onclick = () => {
      closeModal('shopGuidanceModal');
      if (typeof onAction === 'function') onAction();
    };
  }

  if (secBtn) {
    secBtn.innerText = secondaryText;
    secBtn.onclick = () => {
      closeModal('shopGuidanceModal');
      if (typeof onSecondary === 'function') onSecondary();
    };
  }

  openModal('shopGuidanceModal');
}
window.openShopGuidanceModal = openShopGuidanceModal;

async function executePurchase() {
  if (!currentPendingPlan) return;
  const { id: planId, price: planPrice, name: planName, isCustom, gb, days } = currentPendingPlan;
  const confirmBtn = document.getElementById('confirmPurchaseBtn');

  if (confirmBtn) {
    confirmBtn.disabled = true;
    confirmBtn.innerText = 'در حال ثبت خرید...';
  }

  try {
    let res;
    if (isCustom) {
      res = await window.api.purchaseCustomPlan(gb, days, window.currentAccountId || null, currentPendingPlan.hwid_limit || 2);
    } else {
      res = await window.api.purchase(
        planId,
        window.activeCoupon?.code || null,
        window.currentAccountId || null
      );
    }

    if (res && res.ok) {
      closeModal('checkoutConfirmModal');
      showPurchaseModal(res, planName, planPrice);
      hapticFeedback('success');
      if (typeof syncUserDataWithApi === 'function') {
        syncUserDataWithApi(window.currentAccountId);
      }
    } else {
      const errMsg = res?.data?.message || res?.message || 'خطا در ثبت خرید';
      showToast(`❌ ${errMsg}`);
      hapticFeedback('error');
      if (res?.data?.error === 'insufficient_balance' || res?.error === 'insufficient_balance') {
        closeModal('checkoutConfirmModal');
        const shortage = planPrice - (window.lastUserData?.user?.wallet_balance || 0);
        setTimeout(() => {
          if (typeof window.openTopupModal === 'function') window.openTopupModal(shortage > 0 ? shortage : null);
        }, 300);
      } else if (res?.data?.error === 'needs_account' || res?.error === 'needs_account') {
        closeModal('checkoutConfirmModal');
        const switchBtn = document.getElementById('switchAccountBtn');
        if (switchBtn) {
          setTimeout(() => switchBtn.click(), 500);
        }
      }
    }
  } catch (err) {
    showToast('❌ خطا در برقراری ارتباط با سرور.');
  } finally {
    if (confirmBtn) {
      confirmBtn.disabled = false;
      confirmBtn.innerText = '✅ تایید و خرید آنی';
    }
  }
}

function setupBuyButtons() {
  document.querySelectorAll('.buy-plan-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const planId = btn.getAttribute('data-id');
      const planPrice = parseInt(btn.getAttribute('data-price') || '0', 10);
      const planName = btn.getAttribute('data-name');
      const planTraffic = parseInt(btn.getAttribute('data-traffic') || '0', 10);
      const planDays = parseInt(btn.getAttribute('data-days') || '0', 10);
      const planBadge = (btn.getAttribute('data-badge') || '').toLowerCase().trim();
      const planSquad = (btn.getAttribute('data-squad') || '').trim();

      const planObj = {
        id: planId,
        price: planPrice,
        name: planName,
        traffic: planTraffic,
        days: planDays,
        badge: planBadge,
        squad_uuid: planSquad,
      };

      const cachedService = (window.lastUserData?.services || []).find(s => String(s.id) === String(planId));
      if (cachedService && cachedService.squad_uuid && !planObj.squad_uuid) {
        planObj.squad_uuid = cachedService.squad_uuid;
      }

      const isExtraTraffic = (planDays === 0 && planTraffic > 0) || planBadge === 'traffic';
      const isTimeOnly = (planTraffic === 0 && planDays > 0) || planBadge === 'time';
      const isFullPlan = !isExtraTraffic && !isTimeOnly;

      const sub = window.lastUserData?.active_sub || window.lastUserData?.active_subscription;
      const hasActiveSub = Boolean(window.lastUserData?.has_active_sub && sub && (sub.status === 'ACTIVE' || !sub.status));
      const daysLeft = Number(sub?.days_left ?? 0);
      const pctRemaining = Number(sub?.percent_remaining ?? 100);

      // Rule 1: User has NO active subscription, but tries to buy traffic addon or time extension
      if (!hasActiveSub && (isExtraTraffic || isTimeOnly)) {
        openShopGuidanceModal({
          title: 'اشتراک فعالی یافت نشد',
          badgeText: '❌ نیازمند سرویس فعال',
          badgeClass: 'px-2.5 py-0.5 rounded-full text-[11px] font-bold s-danger-soft border border-rose-500/30',
          message: 'بسته‌های افزایش حجم و افزایش زمان صرفاً به سرویس‌های فعال اضافه می‌شوند. لطفاً ابتدا از تب «سرویس‌های کامل» یک اشتراک جدید تهیه فرمایید.',
          actionText: 'مشاهده سرویس‌های کامل',
          onAction: () => switchShopCategory('full'),
        });
        return;
      }

      // Squad Switch & Category guidance step (triggered after any Iran-only notice)
      const proceedPurchaseFlow = () => {
        const activeSub = window.lastUserData?.active_sub || window.lastUserData?.active_subscription;
        const activeSquad = (activeSub?.squad_uuid || '').trim().toLowerCase();
        const planSquadNorm = (planObj.squad_uuid || '').trim().toLowerCase();
        const isSwitch = Boolean(
          hasActiveSub &&
          activeSub &&
          !isExtraTraffic &&
          !isTimeOnly &&
          planSquadNorm &&
          (!activeSquad || planSquadNorm !== activeSquad)
        );

        if (isSwitch) {
          openShopGuidanceModal({
            title: '⚠️ هشدار مهم تغییر دسته سرور',
            badgeText: '🔄 تغییر دسته سرور',
            badgeClass: 'px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/20 text-amber-600 dark:text-amber-300 border border-amber-500/40',
            message: `شما در حال تغییر سرویس اشتراک فعلی خود به «<b>${formatPlanTitle(planObj.name, { plainText: true, iconPosition: 'left' })}</b>» هستید.<br><br>
<b>نکات بسیار مهم پیش از مشاهده پیش‌فاکتور:</b><br>
1. با تغییر سرویس، <b>حجم و روزهای باقیمانده بسته قبلی شما جایگزین می‌شوند</b> (سقف حجم و روزها از نو برای این بسته آغاز می‌گردند).<br>
2. <b>لینک اتصال اشتراک شما تغییری نمی‌کند</b> و تنها کافیست پس از پرداخت، گزینه <b>Update Subscription (بروزرسانی اشتراک)</b> را در برنامه بزنید.<br>
3. هزینه کامل بسته جدید دریافت خواهد شد.<br><br>
راهنما: چنانچه قصد تغییر دسته سرور اشتراک خود را ندارید، می‌توانید از بسته‌های مربوط به دسته سرور فعلی جهت تمدید استفاده کرده و یا «بسته افزایش حجم» تهیه فرمایید.<br><br>
آیا برای مشاهده پیش‌فاکتور و خرید این بسته موافقید؟`,
            actionText: '✅ متوجه شدم، مشاهده پیش‌فاکتور',
            onAction: () => openCheckoutConfirmModal(planObj),
            secondaryText: '❌ انصراف',
            onSecondary: () => closeModal('shopGuidanceModal'),
          });
          return;
        }

        // Rule 2: User has active subscription with plenty of days (> 3 days), and clicked on a Full Plan
        if (hasActiveSub && daysLeft > 3 && isFullPlan) {
          if (pctRemaining <= 25) {
            openShopGuidanceModal({
              title: 'پیشنهاد هوشمند خرید حجم',
              badgeText: '⚡️ صرفه‌جویی در هزینه',
              badgeClass: 'px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-cyan-500/20 text-cyan-600 dark:text-cyan-300 border border-cyan-500/40',
              message: `شما هنوز <b>${daysLeft} روز</b> از اشتراک فعلی‌تان اعتبار دارید! با خرید «بسته افزایش حجم»، نیازی به پرداخت هزینه سرویس کامل نیست و روزهای باقیمانده شما حفظ می‌شود.`,
              actionText: '⚡️ رفتن به بسته‌های افزایش حجم',
              onAction: () => switchShopCategory('traffic'),
              secondaryText: 'انصراف',
              onSecondary: () => closeModal('shopGuidanceModal'),
            });
          } else {
            openShopGuidanceModal({
              title: 'اشتراک شما فعال است',
              badgeText: 'ℹ️ سرویس فعال دارید',
              badgeClass: 'px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-500/20 text-blue-600 dark:text-blue-300 border border-blue-500/40',
              message: `شما در حال حاضر دارای اشتراک فعال با <b>${daysLeft} روز</b> اعتبار باقیمانده هستید. خرید سرویس کامل جدید صرفاً در 3 روز پایانی اعتبار امکان‌پذیر است. در صورت نیاز به حجم یا زمان بیشتر، لطفاً از بسته‌های افزایش حجم یا افزایش زمان استفاده فرمایید.`,
              actionText: '⚡️ بسته‌های افزایش حجم',
              onAction: () => switchShopCategory('traffic'),
              secondaryText: '⏳ بسته‌های افزایش زمان',
              onSecondary: () => switchShopCategory('time'),
            });
          }
          return;
        }

        // Rule 3: User has active subscription with low time (<= 3 days), but they clicked on a Traffic Addon
        if (hasActiveSub && daysLeft <= 3 && isExtraTraffic) {
          openShopGuidanceModal({
            title: 'هشدار پایان اعتبار زمانی',
            badgeText: '⏳ تمدید سرویس کامل',
            badgeClass: 'px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/20 text-amber-600 dark:text-amber-300 border border-amber-500/40',
            message: `تنها <b>${daysLeft} روز</b> از اعتبار زمانی اشتراک شما باقی مانده است! خرید بسته افزایش حجم، زمان سرویس شما را تمدید نمی‌کند و پس از پایان زمان، حجم باقی‌مانده غیرقابل استفاده می‌شود. پیشنهاد ما <b>تمدید دوره کامل</b> است.`,
            actionText: '💎 تمدید دوره کامل',
            onAction: () => switchShopCategory('full'),
            secondaryText: 'ادامه خرید بسته حجم',
            onSecondary: () => openCheckoutConfirmModal(planObj),
          });
          return;
        }

        // Default: proceed to checkout
        openCheckoutConfirmModal(planObj);
      };

      // Special pre-warning for Iran-only server badge BEFORE any server switch warning
      const isIranServerPlan = planBadge === 'iran' || (planName || '').includes('سرور ایران');
      if (isIranServerPlan) {
        openShopGuidanceModal({
          title: '🇮🇷 راهنمای سرویس سرور ایران',
          badgeText: '🌍 ویژه هم‌وطنان خارج از کشور',
          badgeClass: 'px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/20 text-emerald-600 dark:text-emerald-300 border border-emerald-500/40',
          message: `<div class="text-justify leading-relaxed space-y-2 text-xs">
<p>این بسته <b>منحصراً متصل به سرورهای داخل ایران (🇮🇷)</b> بوده و تنها آی‌پی کشور ایران را در اختیار شما قرار می‌دهد.</p>
<p class="font-bold">📌 نکات مهم پیش از خرید:</p>
<ul class="list-disc pr-4 space-y-1.5 leading-relaxed">
  <li>ویژه <b>ایرانیان مقیم خارج از کشور</b> جهت دسترسی به سامانه‌های بانکی، درگاه‌های پرداخت اینترنتی، سایت‌های دولتی (ثنا، سخا و...) و سرویس‌های داخلی ایران.</li>
  <li>در این اشتراک <b>فقط به کشور ایران</b> دسترسی خواهید داشت و برای کاربران داخل ایران (جهت عبور از محدودیت‌های اینترنتی) مناسب <u>نیست</u>.</li>
</ul>
<p class="pt-1 font-semibold">آیا شرایط این سرویس را مطالعه کرده و مایل به ادامه هستید؟</p>
</div>`,
          actionText: '✅ متوجه شدم، ادامه',
          onAction: proceedPurchaseFlow,
          secondaryText: '❌ انصراف',
          onSecondary: () => closeModal('shopGuidanceModal'),
        });
        return;
      }

      proceedPurchaseFlow();
    });
  });
}

function showPurchaseModal(res, fallbackPlanName, fallbackPlanPrice) {
  const pModal = document.getElementById('purchaseSuccessModal');
  if (!pModal) {
    showToast('🎉 خرید شما با موفقیت انجام شد!');
    return;
  }

  const sNameEl = document.getElementById('psvcName');
  const sIconEl = document.getElementById('psvcIcon');
  const sTrafEl = document.getElementById('psvcTraffic');
  const sDaysEl = document.getElementById('psvcDays');
  const sUserEl = document.getElementById('psvcUser');
  const sPriceEl = document.getElementById('psvcPrice');
  const sBalEl = document.getElementById('psvcNewBalance');
  const sSubEl = document.getElementById('psvcSubDisplay');

  let rawName = (res.service_name || fallbackPlanName || '').trim();
  if (rawName.includes('بسته دلخواه')) {
    rawName = 'بسته دلخواه';
  }
  const emojiMatch = rawName.match(/^([\uD800-\uDBFF][\uDC00-\uDFFF]|[\u2600-\u27BF]|\p{Emoji_Presentation}|\p{Extended_Pictographic})/u);
  if (emojiMatch) {
    const emoji = emojiMatch[0];
    const cleanName = rawName.replace(emoji, '').trim();
    if (sNameEl) sNameEl.innerText = cleanName;
    if (sIconEl) sIconEl.innerText = emoji;
  } else {
    if (sNameEl) sNameEl.innerText = rawName;
    const isResExtraTraffic = (Number(res.duration_days) === 0 && Number(res.traffic_gb) > 0);
    const isResExtraTime = (Number(res.traffic_gb) === 0 && Number(res.duration_days) > 0);
    let fallbackIcon = '📦';
    if (isResExtraTraffic || rawName.includes('حجم')) fallbackIcon = '⚡️';
    else if (isResExtraTime || rawName.includes('زمان') || rawName.includes('روز')) fallbackIcon = '⏳';
    if (sIconEl) sIconEl.innerText = fallbackIcon;
  }

  const isResExtraTraffic = (Number(res.duration_days) === 0 && Number(res.traffic_gb) > 0);
  const isResExtraTime = (Number(res.traffic_gb) === 0 && Number(res.duration_days) > 0);

  if (sTrafEl) {
    if (isResExtraTime) {
      sTrafEl.innerText = 'بدون تغییر حجم فعلی';
    } else {
      sTrafEl.innerText = fmtTraffic(res.traffic_gb, { html: false });
    }
  }

  if (sDaysEl) {
    if (isResExtraTraffic) {
      sDaysEl.innerText = 'هم‌گام با انقضای فعلی';
    } else if (Number(res.duration_days) > 0) {
      sDaysEl.innerText = `${res.duration_days} روز`;
    } else {
      sDaysEl.innerText = 'نامحدود روز';
    }
  }
  if (sUserEl) sUserEl.innerText = res.panel_username || (window.lastUserData?.active_sub?.username || 'کاربر');
  if (sPriceEl) sPriceEl.innerText = `${Number(res.effective_price ?? fallbackPlanPrice).toLocaleString('en-US')} تومان`;
  if (sBalEl) sBalEl.innerText = `${Number(res.new_balance || 0).toLocaleString('en-US')} تومان`;

  const subUrl = res.subscription_url || window.lastUserData?.active_sub?.subscription_url || '';
  if (sSubEl) sSubEl.innerText = subUrl || 'لینک اشتراک در داشبورد ثبت گردید.';

  const squadNoticeBox = document.getElementById('psvcSquadNoticeBox');
  if (squadNoticeBox) {
    if (res.squad_changed) {
      squadNoticeBox.classList.remove('hidden');
    } else {
      squadNoticeBox.classList.add('hidden');
    }
  }

  const copyBtn = document.getElementById('psvcCopyBtn');
  if (copyBtn) {
    copyBtn.onclick = () => {
      if (subUrl) copyToClipboard(subUrl, '📋 لینک اشتراک در کلیپ‌بورد کپی شد.');
    };
  }

  const openBtn = document.getElementById('psvcOpenBtn');
  if (openBtn) {
    openBtn.onclick = () => {
      if (subUrl) {
        if (window.Telegram?.WebApp?.openLink) {
          try { window.Telegram.WebApp.openLink(subUrl); } catch(e) { window.open(subUrl, '_blank'); }
        } else {
          window.open(subUrl, '_blank');
        }
      }
    };
  }

  const handleClose = () => {
    closeModal('purchaseSuccessModal');
    window.activeCoupon = null;
    const cInput = document.getElementById('couponInput');
    if (cInput) cInput.value = '';
    const cBtn = document.getElementById('applyCouponBtn');
    if (cBtn) {
      cBtn.disabled = false;
      cBtn.innerText = 'اعمال';
      cBtn.className = 'bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold px-4 py-2 rounded-lg transition';
    }
    if (window.lastUserData) renderShopPlans(window.lastUserData);
    if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
    const dashNav = document.querySelector('.nav-btn[data-tab="tab-dashboard"]');
    dashNav?.click();
  };

  const closeSuccessBtn = document.getElementById('psvcCloseBtn');
  if (closeSuccessBtn) closeSuccessBtn.onclick = handleClose;
  const psvcTopCloseBtn = document.getElementById('psvcTopCloseBtn');
  if (psvcTopCloseBtn) psvcTopCloseBtn.onclick = handleClose;

  const invoiceBtn = document.getElementById('psvcInvoiceBtn');
  if (invoiceBtn) {
    invoiceBtn.onclick = () => {
      const orderId = res.order_id || (window.lastUserData?.transactions?.[0]?.id);
      if (orderId && window.openInvoiceModal) {
        window.openInvoiceModal(orderId);
      } else {
        showToast('فاکتور این سفارش در بخش کیف پول ثبت گردید.');
      }
    };
  }

  openModal('purchaseSuccessModal');
}

window.renderShopPlans = renderShopPlans;
window.setupCouponInput = setupCouponInput;
window.openCheckoutConfirmModal = openCheckoutConfirmModal;
