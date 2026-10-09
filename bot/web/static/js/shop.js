/**
 * RemnaStore Pro - Shop Plans & Checkout Logic
 * Native TMA checkout modal without browser confirm alerts.
 */

window.activeCoupon = null;
let currentPendingPlan = null;

function setupCouponInput() {
  const applyCouponBtn = document.getElementById('applyCouponBtn');
  const removeCouponBtn = document.getElementById('removeCouponBtn');
  const couponInput = document.getElementById('couponInput');
  if (!applyCouponBtn || !couponInput) return;

  const resetCouponState = () => {
    window.activeCoupon = null;
    couponInput.value = '';
    couponInput.disabled = false;
    applyCouponBtn.disabled = false;
    applyCouponBtn.innerText = 'اعمال';
    applyCouponBtn.classList.replace('bg-emerald-600', 'bg-blue-600');
    removeCouponBtn?.classList.add('hidden');
    if (window.lastUserData) renderShopPlans(window.lastUserData);
  };

  removeCouponBtn?.addEventListener('click', () => {
    resetCouponState();
    showToast('کد تخفیف حذف گردید.');
  });

  applyCouponBtn.addEventListener('click', async () => {
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
        if (res.data.discount_percent > 0) discMsg = `${res.data.discount_percent}٪`;
        else if (res.data.discount_amount > 0) discMsg = `${Number(res.data.discount_amount).toLocaleString('en-US')} تومان`;
        showToast(`🎉 کد تخفیف با موفقیت اعمال شد! (${discMsg} تخفیف)`);
        applyCouponBtn.innerText = '✓ اعمال شد';
        applyCouponBtn.classList.replace('bg-blue-600', 'bg-emerald-600');
        couponInput.disabled = true;
        removeCouponBtn?.classList.remove('hidden');
        if (window.lastUserData) renderShopPlans(window.lastUserData);
      } else {
        window.activeCoupon = null;
        showToast(`❌ ${res.message || 'کد تخفیف نامعتبر است.'}`);
        applyCouponBtn.innerText = 'اعمال';
        applyCouponBtn.classList.replace('bg-emerald-600', 'bg-blue-600');
        removeCouponBtn?.classList.add('hidden');
        if (window.lastUserData) renderShopPlans(window.lastUserData);
      }
    } catch (err) {
      showToast('❌ خطا در بررسی کد تخفیف.');
      applyCouponBtn.innerText = 'اعمال';
    } finally {
      applyCouponBtn.disabled = false;
    }
  });
}

function renderShopPlans(data) {
  const shopContainer = document.getElementById('shopPlansContainer');
  const plans = data?.plans || [];
  if (!shopContainer || plans.length === 0) return;

  shopContainer.innerHTML = plans.map(p => {
    const planNameLower = (p.name || '').toLowerCase();
    const isPopular = planNameLower.includes('gold') || (p.name || '').includes('گلد');
    let discountVal = 0;
    if (window.activeCoupon) {
      if (window.activeCoupon.discount_percent > 0) {
        discountVal = Math.round(p.price * window.activeCoupon.discount_percent / 100);
      } else if (window.activeCoupon.discount_amount > 0) {
        discountVal = window.activeCoupon.discount_amount;
      }
    }
    const finalPrice = Math.max(0, p.price - discountVal);
    const formattedFinal = Number(finalPrice).toLocaleString('en-US');
    const formattedOriginal = Number(p.price || 0).toLocaleString('en-US');
    const devLimitText = (p.hwid_limit && p.hwid_limit > 0) ? `${p.hwid_limit} کاربر` : 'بدون محدودیت کاربر';

    return `
      <div class="shop-plan-card bg-slate-800/90 rounded-2xl p-4 border ${isPopular ? 'border-amber-500/60 shadow-lg shadow-amber-500/10' : 'border-slate-700/80'} relative overflow-hidden group">
        ${isPopular ? '<div class="absolute top-0 left-0 bg-gradient-to-r from-amber-500 to-yellow-500 text-slate-950 text-[10px] font-black px-3 py-0.5 rounded-br-xl shadow flex items-center gap-1">🔥 پرفروش‌ترین</div>' : ''}
        <div class="flex justify-between items-start ${isPopular ? 'mt-1' : ''}">
          <div>
            <div class="flex items-center gap-2">
              <h4 class="font-bold text-sm text-white">${p.name}</h4>
              ${discountVal > 0 ? '<span class="text-[10px] text-emerald-400 font-bold bg-transparent border-0 px-0 py-0">🏷 تخفیف ویژه</span>' : ''}
            </div>
            <p class="text-xs text-slate-400 mt-1">${p.description || 'ترافیک پایدار و بدون محدودیت روی تمام سرورها'}</p>
          </div>
          <div class="text-left font-mono">
            ${discountVal > 0 ? `<span class="line-through text-slate-400 text-xs block -mb-0.5">${formattedOriginal}</span>` : ''}
            <span class="text-base font-black text-emerald-400">${formattedFinal}</span>
            <span class="text-[10px] text-slate-400 block -mt-1 font-sans">تومان</span>
          </div>
        </div>
        <div class="flex items-center justify-between my-2.5 text-[10px] text-slate-300 bg-slate-900/60 px-3 py-2 rounded-xl whitespace-nowrap overflow-hidden">
          <span class="flex items-center gap-1">📊 <b dir="ltr" class="font-mono text-cyan-300">${p.traffic_gb} GB</b></span>
          <span class="flex items-center gap-1">📅 <b class="text-slate-200">${p.duration_days} روز</b></span>
          <span class="flex items-center gap-1">📱 <b class="text-slate-200">${devLimitText}</b></span>
        </div>
        <button class="buy-plan-btn w-full ${isPopular ? 'bg-gradient-to-r from-amber-500 via-orange-500 to-amber-600 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-black' : 'bg-blue-600 hover:bg-blue-500 text-white font-semibold'} text-xs py-2.5 rounded-xl transition shadow active:scale-[0.98]" data-id="${p.id}" data-price="${finalPrice}" data-name="${p.name}" data-traffic="${p.traffic_gb}" data-days="${p.duration_days}">
          🛒 خرید / تمدید آنی (${formattedFinal} تومان)
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

  if (nameEl) nameEl.innerText = plan.name;
  if (trafEl) trafEl.innerText = `${plan.traffic} GB`;
  if (daysEl) daysEl.innerText = `${plan.days} روز`;
  if (priceEl) priceEl.innerText = `${Number(planPrice).toLocaleString('en-US')} تومان`;
  if (balEl) balEl.innerText = `${Number(userBalance).toLocaleString('en-US')} تومان`;

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
      confirmBtn.innerText = '✅ تایید و خرید آنی';
      confirmBtn.onclick = executePurchase;
    }
  }

  openModal('checkoutConfirmModal');
}

async function executePurchase() {
  if (!currentPendingPlan) return;
  const { id: planId, price: planPrice, name: planName } = currentPendingPlan;
  const confirmBtn = document.getElementById('confirmPurchaseBtn');

  if (confirmBtn) {
    confirmBtn.disabled = true;
    confirmBtn.innerText = 'در حال ثبت خرید...';
  }

  try {
    const res = await window.api.purchase(
      planId,
      window.activeCoupon?.code || null,
      window.currentAccountId || null
    );

    if (res.ok) {
      closeModal('checkoutConfirmModal');
      showPurchaseModal(res, planName, planPrice);
      hapticFeedback('success');
      if (typeof syncUserDataWithApi === 'function') {
        syncUserDataWithApi(window.currentAccountId);
      }
    } else {
      showToast(`❌ ${res.message || 'خطا در ثبت خرید'}`);
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
      const planPrice = parseInt(btn.getAttribute('data-price') || '0');
      const planName = btn.getAttribute('data-name');
      const planTraffic = btn.getAttribute('data-traffic') || '--';
      const planDays = btn.getAttribute('data-days') || '--';

      openCheckoutConfirmModal({
        id: planId,
        price: planPrice,
        name: planName,
        traffic: planTraffic,
        days: planDays
      });
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

  const rawName = (res.service_name || fallbackPlanName || '').trim();
  const emojiMatch = rawName.match(/^([\uD800-\uDBFF][\uDC00-\uDFFF]|[\u2600-\u27BF]|\p{Emoji_Presentation}|\p{Extended_Pictographic})/u);
  if (emojiMatch) {
    const emoji = emojiMatch[0];
    const cleanName = rawName.replace(emoji, '').trim();
    if (sNameEl) sNameEl.innerText = cleanName;
    if (sIconEl) sIconEl.innerText = emoji;
  } else {
    if (sNameEl) sNameEl.innerText = rawName;
    if (sIconEl) sIconEl.innerText = '📦';
  }

  if (sTrafEl) sTrafEl.innerText = `${res.traffic_gb ?? ''} GB`;
  if (sDaysEl) sDaysEl.innerText = `${res.duration_days ?? ''} روز`;
  if (sUserEl) sUserEl.innerText = res.panel_username || (window.lastUserData?.active_sub?.username || 'کاربر');
  if (sPriceEl) sPriceEl.innerText = `${Number(res.effective_price ?? fallbackPlanPrice).toLocaleString('en-US')} تومان`;
  if (sBalEl) sBalEl.innerText = `${Number(res.new_balance || 0).toLocaleString('en-US')} تومان`;

  const subUrl = res.subscription_url || window.lastUserData?.active_sub?.subscription_url || '';
  if (sSubEl) sSubEl.innerText = subUrl || 'لینک اشتراک در داشبورد ثبت گردید.';

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

  openModal('purchaseSuccessModal');
}

window.renderShopPlans = renderShopPlans;
window.setupCouponInput = setupCouponInput;
window.openCheckoutConfirmModal = openCheckoutConfirmModal;
