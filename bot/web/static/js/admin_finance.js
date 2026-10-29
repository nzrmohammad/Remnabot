/**
 * RemnaAdmin Pro - Finance & Topups Module (admin_finance.js)
 * Card-to-card payments, transaction review, crypto gateway rates and wallet balances.
 */
(function (window) {
  'use strict';

  const $ = id => document.getElementById(id);
  const api = window.api;
  const tg = window.Telegram?.WebApp;
  const formatNumber = window.formatNumber || (n => String(n));
  const showConfirmModal = window.showConfirmModal || window.adminActions?.showConfirmModal;
  const showOperationReportModal = window.showOperationReportModal || window.adminActions?.showOperationReportModal;
  window.adminActions = window.adminActions || {};

  let currentWalletTarget = null;

  window.switchFinanceSubtab = function(subtab) {
    const btnTopups = $('subtabBtnTopups');
    const btnCampaigns = $('subtabBtnCampaigns');
    const contentTopups = $('subtabContentTopups');
    const contentCampaigns = $('subtabContentCampaigns');

    if (window.hapticFeedback) window.hapticFeedback('selection');

    const isTopups = subtab === 'topups';
    btnTopups?.classList.toggle('is-active', isTopups);
    btnTopups?.setAttribute('aria-selected', isTopups ? 'true' : 'false');
    btnCampaigns?.classList.toggle('is-active', !isTopups);
    btnCampaigns?.setAttribute('aria-selected', !isTopups ? 'true' : 'false');

    contentTopups?.classList.toggle('hidden', !isTopups);
    contentCampaigns?.classList.toggle('hidden', isTopups);

    if (isTopups) {
      if (typeof fetchAdminTopups === 'function') fetchAdminTopups();
    } else {
      if (window.adminActions && typeof window.adminActions.fetchAdminCampaigns === 'function') {
        window.adminActions.fetchAdminCampaigns();
      }
    }
  };


  // Finance, Topups & Crypto Actions
  Object.assign(window.adminActions, {
async handleTopup(topup_id, approved) {
      const ok = await showConfirmModal({
        title: approved ? 'تایید و شارژ فیش' : 'رد کردن فیش واریزی',
        message: `آیا از ${approved ? 'تایید و شارژ' : 'رد کردن'} این فیش مطمئن هستید؟`,
        confirmText: approved ? 'تایید و شارژ' : 'رد فیش',
        isDanger: !approved,
      });
      if (!ok) return;

      try {
        const res = await window.api.handleTopupAction(topup_id, approved);
        if (res && res.ok) {
          if (window.showToast) window.showToast(`✅ ${res.message}`);
          if (window.hapticFeedback) window.hapticFeedback('success');
          fetchAdminTopups();
          if (window.syncAdminOverview) window.syncAdminOverview();
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در تعیین تکلیف فیش'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (err) {
        if (window.showToast) window.showToast('خطا در برقراری ارتباط');
      }
    },

// --- Wallet Actions ---
    openWalletModal(telegram_id, name) {
      currentWalletTarget = { telegram_id, name };
      const modal = $('walletModal');
      const title = $('walletModalTitle');
      const amtInput = $('walletModalAmount');
      const reasonInput = $('walletModalReason');
      if (modal) modal.classList.remove('hidden');
      if (title) title.innerText = `💰 کیف پول: ${name}`;
      if (amtInput) amtInput.value = '50000';
      if (reasonInput) reasonInput.value = 'شارژ دستی توسط مدیریت';
      amtInput?.focus();
    },

    closeWalletModal() {
      $('walletModal')?.classList.add('hidden');
      currentWalletTarget = null;
    },

    async applyWalletModification() {
      if (!currentWalletTarget) return;
      const rawAmount = parseInt($('walletModalAmount')?.value || '0', 10);
      if (isNaN(rawAmount) || rawAmount <= 0) {
        if (window.showToast) window.showToast('لطفاً مبلغ معتبری وارد کنید.');
        return;
      }
      const finalAmount = walletActionType === 'add' ? rawAmount : -rawAmount;
      const reason = $('walletModalReason')?.value?.trim() || 'شارژ توسط مدیریت';
      const submitBtn = $('walletModalSubmitBtn');
      if (submitBtn) { submitBtn.disabled = true; submitBtn.innerText = 'در حال ثبت...'; }

      try {
        const res = await window.api.modifyUserWallet(currentWalletTarget.telegram_id, finalAmount, reason);
        if (res && res.ok) {
          const oldBal = Number(res.old_balance !== undefined ? res.old_balance : 0);
          const newBal = Number(res.new_balance !== undefined ? res.new_balance : 0);
          const delta = Number(res.delta !== undefined ? res.delta : finalAmount);
          const isAdd = delta > 0;
          const targetName = currentWalletTarget.name;
          const targetId = currentWalletTarget.telegram_id;

          this.closeWalletModal();
          if (window.fetchAdminUsers) window.fetchAdminUsers();
          if (window.syncAdminOverview) window.syncAdminOverview();

          showOperationReportModal({
            title: 'گزارش تراکنش کیف پول',
            subtitle: isAdd ? 'افزایش موجودی با موفقیت ثبت شد' : 'کسر موجودی با موفقیت ثبت شد',
            iconType: 'success',
            items: [
              { label: 'کاربر منتخب', value: targetName },
              { label: 'شناسه تلگرام', value: `#${targetId}`, dir: 'ltr' },
              { label: 'نوع عملیات', value: isAdd ? 'افزایش اعتبار (شارژ دستی)' : 'کسر موجودی دستی', color: isAdd ? 'text-emerald-400' : 'text-rose-400' },
              { label: 'موجودی قبلی', value: `${formatNumber(oldBal)} تومان`, dir: 'rtl' },
              { label: 'مبلغ تغییر یافته', value: `${isAdd ? '+' : ''}${formatNumber(delta)} تومان`, color: isAdd ? 'text-emerald-400' : 'text-rose-400', dir: 'rtl' },
              { label: 'موجودی جدید کیف پول', value: `${formatNumber(newBal)} تومان`, highlight: true },
              { label: 'توضیحات / بابت', value: reason || 'ثبت توسط مدیریت' },
            ]
          });
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در تغییر موجودی'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطای شبکه در ثبت موجودی');
      } finally {
        if (submitBtn) { submitBtn.disabled = false; submitBtn.innerText = 'ثبت تغییر موجودی'; }
      }
    },

async openReceiptImageModal(photoUrl, topupId) {
      const modal = $('receiptPhotoModal');
      const img = $('receiptModalImage');
      const spinner = $('receiptModalSpinner');
      const errBox = $('receiptModalError');
      const textBox = $('receiptModalTextInfo');
      const titleEl = $('receiptModalTitle');

      if (titleEl) titleEl.textContent = topupId ? `تصویر رسید فیش ${topupId}` : 'تصویر رسید واریزی';
      if (modal) modal.classList.remove('hidden');
      if (img) {
        img.src = '';
        img.classList.add('hidden');
      }
      if (textBox) textBox.classList.add('hidden');
      if (errBox) errBox.classList.add('hidden');
      if (spinner) spinner.classList.remove('hidden');

      try {
        const fetchUrl = photoUrl || `/api/admin/topup/photo?id=${encodeURIComponent(topupId || '')}`;
        let blob;
        try {
          blob = await window.api.getBlob(fetchUrl);
        } catch (fetchErr) {
          throw new Error(fetchErr.status === 404 ? 'تصویری برای این فیش یافت نشد یا ثبت نشده است.' : 'خطا در دریافت تصویر رسید از تلگرام');
        }

        if (!blob || blob.size === 0) {
          throw new Error('فایل تصویر دریافت نشد.');
        }

        const objectUrl = URL.createObjectURL(blob);
        if (img) {
          img.onload = () => {
            if (spinner) spinner.classList.add('hidden');
            img.classList.remove('hidden');
          };
          img.onerror = () => {
            if (spinner) spinner.classList.add('hidden');
            if (errBox) {
              errBox.textContent = 'خطا در نمایش تصویر رسید';
              errBox.classList.remove('hidden');
            }
          };
          img.src = objectUrl;
        }
      } catch (err) {
        if (spinner) spinner.classList.add('hidden');
        if (errBox) {
          errBox.textContent = err.message || 'خطا در بارگذاری تصویر فیش';
          errBox.classList.remove('hidden');
        }
      }

      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    showReceiptInfoModal(topupId, receiptHash, amount) {
      const modal = $('receiptPhotoModal');
      const img = $('receiptModalImage');
      const spinner = $('receiptModalSpinner');
      const errBox = $('receiptModalError');
      const textBox = $('receiptModalTextInfo');
      const textContent = $('receiptModalTextContent');
      const titleEl = $('receiptModalTitle');

      if (titleEl) titleEl.textContent = `مشخصات فیش واریزی ${topupId}`;
      if (modal) modal.classList.remove('hidden');
      if (spinner) spinner.classList.add('hidden');
      if (errBox) errBox.classList.add('hidden');
      if (img) img.classList.add('hidden');

      let cleanText = receiptHash || 'بدون اطلاعات پیگیری';
      if (cleanText.startsWith('text:')) {
        cleanText = cleanText.substring(5);
      }

      if (textContent) {
        textContent.textContent = `${cleanText}\nمبلغ: ${amount} تومان`;
      }
      if (textBox) textBox.classList.remove('hidden');

      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    closeReceiptPhotoModal() {
      const modal = $('receiptPhotoModal');
      if (modal) modal.classList.add('hidden');
    },

openCryptoRatesModal() {
      const modal = $('cryptoRatesModal');
      if (modal) modal.classList.remove('hidden');
      this.refreshLiveCryptoRates();
      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    closeCryptoRatesModal() {
      $('cryptoRatesModal')?.classList.add('hidden');
    },

    async refreshLiveCryptoRates(force = true) {
      const container = $('cryptoRatesContent');
      if (!container) return;
      container.innerHTML = '<div class="p-6 text-center text-xs text-slate-400">در حال استعلام جدیدترین نرخ‌ها از صرافی‌های معتبر...</div>';
      try {
        const res = await window.api.getAdminCryptoRates(force);
        if (!res || !res.ok) {
          container.innerHTML = `<div class="p-6 text-center text-xs text-rose-400">${escapeHtml(res?.error || 'خطا در دریافت نرخ‌ها')}</div>`;
          return;
        }

        const bestTon = res.best_ton || {};
        const bestUsdt = res.best_usdt || {};
        const bestEur = res.best_eur || {};
        const bestTrx = res.best_trx || {};
        window.lastLiveCryptoRates = { ton: bestTon.price, usdt: bestUsdt.price, eur: bestEur.price, trx: bestTrx.price };
        if (bestEur.price) window.currentEurRate = bestEur.price;
        if (bestUsdt.price) window.currentUsdRate = bestUsdt.price;

        const usdtList = Object.entries(res.usdt_prices || {});
        const eurList = Object.entries(res.eur_prices || {});
        const tonList = Object.entries(res.ton_prices || {});
        const trxList = Object.entries(res.trx_prices || {});
        const binanceUsd = res.binance_usd;
        const binanceEurUsd = res.binance_eur_usd;
        const binanceTrxUsd = res.binance_trx_usd;

        let usdtRowsHtml = '';
        if (usdtList.length > 0) {
          usdtRowsHtml = usdtList.map(([src, p]) => `
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-xl card-inset border border-slate-700/50 hover:border-slate-500/50 transition">
              <span class="t-main font-medium text-[11px]">${src}</span>
              <div class="flex items-center gap-2">
                <span class="font-mono font-bold t-main text-[11px] num-bidi">${formatNumber(p)} <span class="text-[10px] t-muted font-sans">تومان</span></span>
                <button onclick="window.adminActions.applySpecificRate('usdt', ${p}, this)" class="bg-transparent hover:bg-emerald-500/10 text-emerald-400 hover:text-emerald-300 border border-emerald-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
                  اعمال
                </button>
              </div>
            </div>
          `).join('');
        }

        let eurRowsHtml = '';
        if (eurList.length > 0) {
          eurRowsHtml = eurList.map(([src, p]) => `
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-xl card-inset border border-slate-700/50 hover:border-slate-500/50 transition">
              <span class="t-main font-medium text-[11px]">${src}</span>
              <div class="flex items-center gap-2">
                <span class="font-mono font-bold t-main text-[11px] num-bidi">${formatNumber(p)} <span class="text-[10px] t-muted font-sans">تومان</span></span>
                <button onclick="window.adminActions.applySpecificRate('eur', ${p}, this)" class="bg-transparent hover:bg-indigo-500/10 text-indigo-400 hover:text-indigo-300 border border-indigo-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
                  اعمال
                </button>
              </div>
            </div>
          `).join('');
        }

        let tonRowsHtml = '';
        if (tonList.length > 0) {
          tonRowsHtml = tonList.map(([src, p]) => `
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-xl card-inset border border-slate-700/50 hover:border-slate-500/50 transition">
              <span class="t-main font-medium text-[11px]">${src}</span>
              <div class="flex items-center gap-2">
                <span class="font-mono font-bold t-main text-[11px] num-bidi">${formatNumber(p)} <span class="text-[10px] t-muted font-sans">تومان</span></span>
                <button onclick="window.adminActions.applySpecificRate('ton', ${p}, this)" class="bg-transparent hover:bg-cyan-500/10 text-cyan-400 hover:text-cyan-300 border border-cyan-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
                  اعمال
                </button>
              </div>
            </div>
          `).join('');
        }

        if (binanceUsd) {
          const tonTomanBinance = bestTon.price;
          const globalSrc = res.global_ton_source ? `${res.global_ton_source} (جهانی)` : 'بایننس (جهانی)';
          tonRowsHtml += `
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-xl card-inset border border-slate-700/50 hover:border-slate-500/50 transition">
              <span class="t-main font-medium text-[11px]">${escapeHtml(globalSrc)}</span>
              <div class="flex items-center gap-2">
                <span class="font-mono font-bold text-cyan-500 dark:text-cyan-300 text-[11px] num-bidi">${Number(binanceUsd).toFixed(2)}</span>
                ${tonTomanBinance ? `
                <button onclick="window.adminActions.applySpecificRate('ton', ${tonTomanBinance}, this)" class="bg-transparent hover:bg-cyan-500/10 text-cyan-400 hover:text-cyan-300 border border-cyan-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
                  اعمال
                </button>` : ''}
              </div>
            </div>
          `;
        }

        let trxRowsHtml = '';
        if (trxList.length > 0) {
          trxRowsHtml = trxList.map(([src, p]) => `
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-xl card-inset border border-slate-700/50 hover:border-slate-500/50 transition">
              <span class="t-main font-medium text-[11px]">${src}</span>
              <div class="flex items-center gap-2">
                <span class="font-mono font-bold t-main text-[11px] num-bidi">${formatNumber(p)} <span class="text-[10px] t-muted font-sans">تومان</span></span>
                <button onclick="window.adminActions.applySpecificRate('trx', ${p}, this)" class="bg-transparent hover:bg-rose-500/10 text-rose-500 dark:text-rose-400 border border-rose-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
                  اعمال
                </button>
              </div>
            </div>
          `).join('');
        }

        if (binanceTrxUsd) {
          const trxTomanBinance = bestTrx.price;
          trxRowsHtml += `
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-xl card-inset border border-slate-700/50 hover:border-slate-500/50 transition">
              <span class="t-main font-medium text-[11px]">بایننس (جهانی)</span>
              <div class="flex items-center gap-2">
                <span class="font-mono font-bold text-rose-500 dark:text-rose-300 text-[11px] num-bidi">${Number(binanceTrxUsd).toFixed(4)}</span>
                ${trxTomanBinance ? `
                <button onclick="window.adminActions.applySpecificRate('trx', ${trxTomanBinance}, this)" class="bg-transparent hover:bg-rose-500/10 text-rose-500 dark:text-rose-400 border border-rose-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
                  اعمال
                </button>` : ''}
              </div>
            </div>
          `;
        }

        container.innerHTML = `
          <!-- All USDT Exchanges List -->
          <div class="space-y-1.5">
            <span class="text-[10px] font-bold t-muted block px-1">استعلام صرافی‌های داخلی (USDT تتر):</span>
            <div class="space-y-1">
              ${usdtRowsHtml || '<div class="text-[10px] t-muted text-center py-1">اطلاعاتی دریافت نشد</div>'}
            </div>
          </div>

          <!-- All EUR Rates List -->
          <div class="space-y-1.5 mt-3">
            <span class="text-[10px] font-bold t-muted block px-1">استعلام نرخ ارز یورو (EUR):</span>
            <div class="space-y-1">
              ${eurRowsHtml || '<div class="text-[10px] t-muted text-center py-1">اطلاعاتی دریافت نشد</div>'}
            </div>
          </div>

          <!-- All TON Exchanges List -->
          <div class="space-y-1.5 mt-3">
            <span class="text-[10px] font-bold t-muted block px-1">استعلام صرافی‌ها (TON تون):</span>
            <div class="space-y-1">
              ${tonRowsHtml || '<div class="text-[10px] t-muted text-center py-1">اطلاعاتی دریافت نشد</div>'}
            </div>
          </div>

          <!-- All TRX Exchanges List -->
          <div class="space-y-1.5 mt-3">
            <span class="text-[10px] font-bold t-muted block px-1">استعلام صرافی‌ها (TRX ترون):</span>
            <div class="space-y-1">
              ${trxRowsHtml || '<div class="text-[10px] t-muted text-center py-1">اطلاعاتی دریافت نشد</div>'}
            </div>
          </div>`;

          <!-- Stars Auto-Calculation from Live USDT Benchmark -->
          <div class="space-y-1.5 mt-3 pt-2.5 border-t border-slate-700/60">
            <div class="flex items-center justify-between px-1">
              <span id="modalStarsBenchmarkTitle" class="text-[10px] font-bold text-amber-400">⭐️ نرخ پیشنهادی استارز تلگرام:</span>
            </div>
            <div class="space-y-1.5">
              <div class="flex items-center justify-between py-1.5 px-2.5 rounded-xl bg-slate-800/60 border border-slate-700/50 hover:border-slate-600 transition">
                <div>
                  <span class="text-slate-200 font-bold text-[11px] block">🛡️ فرمول بدون ضرر</span>
                  <span class="text-[11px] text-slate-400">نقد کردن با کسر کارمزد تلگرام</span>
                </div>
                <div class="flex items-center gap-2">
                  <span id="modalStarsLosslessPrice" class="font-mono font-bold text-amber-300 text-[11px]"></span>
                  <button id="modalStarsLosslessBtn" class="bg-transparent hover:bg-amber-500/10 text-amber-400 hover:text-amber-300 border border-amber-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
                    اعمال
                  </button>
                </div>
              </div>
              <div class="flex items-center justify-between py-1.5 px-2.5 rounded-xl bg-slate-800/60 border border-slate-700/50 hover:border-slate-600 transition">
                <div>
                  <span class="text-slate-200 font-bold text-[11px] block">🏷️ نرخ خرید فرگمنت</span>
                  <span class="text-[11px] text-slate-400">بر اساس قیمت خرید استارز در فرگمنت</span>
                </div>
                <div class="flex items-center gap-2">
                  <span id="modalStarsFragmentPrice" class="font-mono font-bold text-blue-300 text-[11px]"></span>
                  <button id="modalStarsFragmentBtn" class="bg-transparent hover:bg-blue-500/10 text-blue-400 hover:text-blue-300 border border-blue-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
                    اعمال
                  </button>
                </div>
              </div>
            </div>
          </div>
        `;

        const initialUsdt = bestUsdt.price || window.lastLiveCryptoRates?.usdt || window.currentUsdRate || 95000;
        this.updateModalStarsRates(initialUsdt);
      } catch (e) {
        container.innerHTML = '<div class="p-6 text-center text-xs text-rose-400">خطای ارتباط با سرور در استعلام نرخ‌ها</div>';
      }
    },

    updateModalStarsRates(usdtPrice) {
      const p = parseInt(usdtPrice || '0', 10) || window.currentUsdRate || 95000;
      const lossless = Math.round(p * 0.013);
      const fragment = Math.round(p * 0.015);

      const titleEl = $('modalStarsBenchmarkTitle');
      if (titleEl) titleEl.textContent = `⭐️ نرخ پیشنهادی استارز تلگرام (بر اساس دلار ${formatNumber(p)} ت):`;

      const losslessPriceEl = $('modalStarsLosslessPrice');
      if (losslessPriceEl) losslessPriceEl.innerHTML = `${formatNumber(lossless)} <span class="text-[10px] text-slate-400 font-sans">تومان</span>`;

      const fragmentPriceEl = $('modalStarsFragmentPrice');
      if (fragmentPriceEl) fragmentPriceEl.innerHTML = `${formatNumber(fragment)} <span class="text-[10px] text-slate-400 font-sans">تومان</span>`;

      const losslessBtn = $('modalStarsLosslessBtn');
      if (losslessBtn) {
        losslessBtn.onclick = () => window.adminActions.applySpecificRate('stars', lossless, losslessBtn);
        losslessBtn.textContent = 'اعمال';
        losslessBtn.classList.remove('bg-emerald-500/20', 'text-emerald-300', 'border-emerald-500');
      }

      const fragmentBtn = $('modalStarsFragmentBtn');
      if (fragmentBtn) {
        fragmentBtn.onclick = () => window.adminActions.applySpecificRate('stars', fragment, fragmentBtn);
        fragmentBtn.textContent = 'اعمال';
        fragmentBtn.classList.remove('bg-emerald-500/20', 'text-emerald-300', 'border-emerald-500');
      }
    },

    async applySpecificRate(type, val, btnEl) {
      if (!val) return;
      const numVal = parseInt(val, 10);
      if (isNaN(numVal) || numVal <= 0) return;

      if (!window.lastLiveCryptoRates) window.lastLiveCryptoRates = {};
      window.lastLiveCryptoRates[type] = numVal;

      const payload = {};
      if (type === 'usdt') {
        const inp = $('settingUsdtRate');
        if (inp) inp.value = numVal;
        payload.usdt_rate_toman = numVal;
        window.currentUsdRate = numVal;
        this.updateStarsHint();
        this.updateModalStarsRates(numVal);
      } else if (type === 'eur') {
        const inp = $('settingEurRate');
        if (inp) inp.value = numVal;
        payload.eur_rate_toman = numVal;
        window.currentEurRate = numVal;
      } else if (type === 'ton') {
        const inp = $('settingTonRate');
        if (inp) inp.value = numVal;
        payload.ton_rate_toman = numVal;
      } else if (type === 'trx') {
        const inp = $('settingTrxRate');
        if (inp) inp.value = numVal;
        payload.trx_rate_toman = numVal;
      } else if (type === 'stars') {
        const inp = $('settingStarsRate');
        if (inp) inp.value = numVal;
        payload.stars_rate_toman = numVal;
      }

      if (btnEl) {
        const parent = btnEl.closest('.space-y-1') || btnEl.closest('.space-y-1\\.5');
        if (parent) {
          parent.querySelectorAll('button').forEach(b => {
            b.textContent = 'اعمال';
            b.classList.remove('bg-emerald-500/20', 'text-emerald-300', 'border-emerald-500');
          });
        }
        btnEl.textContent = '✓ اعمال شد';
        btnEl.classList.add('bg-emerald-500/20', 'text-emerald-300', 'border-emerald-500');
      }

      try {
        const res = await window.api.saveAdminSettings(payload);
        if (res && res.ok) {
          const typeName = type === 'usdt' ? 'تتر' : (type === 'eur' ? 'یورو' : (type === 'ton' ? 'تون' : (type === 'trx' ? 'ترون' : 'استارز')));
          if (window.showToast) window.showToast(`✅ نرخ ${typeName} به ${formatNumber(numVal)} تومان ذخیره شد`);
          if (window.hapticFeedback) window.hapticFeedback('success');
        } else {
          if (window.showToast) window.showToast(`⚠️ نرخ تنظیم شد اما در سرور ذخیره نشد: ${res?.error || ''}`);
        }
      } catch (err) {
        if (window.showToast) window.showToast('خطا در ذخیره نرخ در سرور');
      }
    },

    async applyLiveCryptoRates() {
      const usdtInp = $('settingUsdtRate');
      const eurInp = $('settingEurRate');
      const tonInp = $('settingTonRate');
      const trxInp = $('settingTrxRate');
      const starsInp = $('settingStarsRate');

      const usdtVal = window.lastLiveCryptoRates?.usdt || parseInt(usdtInp?.value || '95000', 10);
      const tonVal = window.lastLiveCryptoRates?.ton || parseInt(tonInp?.value || '0', 10);
      const eurVal = window.lastLiveCryptoRates?.eur || parseInt(eurInp?.value || '105000', 10);
      const trxVal = window.lastLiveCryptoRates?.trx || parseInt(trxInp?.value || '0', 10);
      const starsVal = window.lastLiveCryptoRates?.stars || parseInt(starsInp?.value || '0', 10) || Math.round(usdtVal * 0.013);

      if (usdtInp && usdtVal) {
        usdtInp.value = usdtVal;
        window.currentUsdRate = usdtVal;
      }
      if (tonInp && tonVal) tonInp.value = tonVal;
      if (trxInp && trxVal) trxInp.value = trxVal;
      if (eurInp && eurVal) {
        eurInp.value = eurVal;
        window.currentEurRate = eurVal;
      }
      if (starsInp && starsVal) starsInp.value = starsVal;

      try {
        const payload = {
          usdt_rate_toman: usdtVal,
          ton_rate_toman: tonVal,
          trx_rate_toman: trxVal,
          eur_rate_toman: eurVal,
          stars_rate_toman: starsVal,
        };
        const res = await window.api.saveAdminSettings(payload);
        if (res && res.ok) {
          if (window.showToast) window.showToast('✅ تمامی نرخ‌ها با موفقیت ذخیره شدند');
          this.closeCryptoRatesModal();
          this.updateStarsHint();
          if (window.hapticFeedback) window.hapticFeedback('success');
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ثبت نرخ‌ها'}`);
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطا در ذخیره نرخ‌ها');
      }
    }
  });

  let walletActionType = 'add';
  const walletActionAddBtn = $('walletActionAddBtn');
  const walletActionDeductBtn = $('walletActionDeductBtn');

  walletActionAddBtn?.addEventListener('click', () => {
    walletActionType = 'add';
    walletActionAddBtn.className = 'py-2 rounded-xl bg-emerald-600 text-white font-bold transition flex items-center justify-center gap-1 shadow-sm';
    walletActionDeductBtn.className = 'py-2 rounded-xl t-muted hover:t-main font-medium transition flex items-center justify-center gap-1';
  });

  walletActionDeductBtn?.addEventListener('click', () => {
    walletActionType = 'deduct';
    walletActionDeductBtn.className = 'py-2 rounded-xl bg-rose-600 text-white font-bold transition flex items-center justify-center gap-1 shadow-sm';
    walletActionAddBtn.className = 'py-2 rounded-xl t-muted hover:t-main font-medium transition flex items-center justify-center gap-1';
  });

  // --- 7. Pending Topups Fetcher ---
  async function fetchAdminTopups() {
    const container = $('adminPendingTopupsList');
    if (!container) return;
    if (!container.children || container.children.length === 0) {
      container.innerHTML = '<div class="p-4 text-center text-xs text-slate-400">در حال دریافت فیش‌ها...</div>';
    }

    try {
      const res = await window.api.getAdminTopups();
      if (!res || !res.ok) {
        container.innerHTML = `<div class="p-6 text-center text-rose-400 text-xs">${escapeHtml(res?.error || 'خطا در دریافت فیش‌ها')}</div>`;
        return;
      }
      const topups = res.topups || [];
      if (topups.length === 0) {
        container.innerHTML = `
          <div class="bg-slate-900/40 rounded-2xl p-6 text-center text-slate-400 text-xs border border-slate-800 space-y-2">
            <div class="w-10 h-10 rounded-2xl bg-emerald-500/15 text-emerald-400 flex items-center justify-center mx-auto">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
            </div>
            <p class="font-medium text-slate-300">هیچ فیش واریزی در انتظاری وجود ندارد</p>
            <span class="text-[10px] text-slate-500">تمامی پرداخت‌های کارت به کارت بررسی شده‌اند.</span>
          </div>
        `;
        return;
      }

      container.innerHTML = topups.map(t => {
        const uLabel = t.full_name || (t.username ? '@' + t.username : `کاربر ${t.telegram_id}`);
        const initial = (uLabel[0] || 'U').toUpperCase();
        const dateStr = t.created_at ? new Date(t.created_at).toLocaleDateString('fa-IR', { numberingSystem: 'latn', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }) : '—';
        const avatarSrc = t.avatar_url || `/api/user/avatar?user_id=${t.telegram_id}`;
        const hasPhoto = Boolean(t.has_photo || t.receipt_photo_id || (t.receipt_hash && (t.receipt_hash.startsWith('img:') || t.receipt_hash.startsWith('photo:'))));
        const photoUrl = hasPhoto ? `/api/admin/topup/photo?id=${t.id}` : null;
        const usernameTag = t.username ? `@${t.username}` : '';

        return `
          <div class="topup-card bg-slate-800/90 rounded-2xl p-3.5 border border-slate-700/80 space-y-3 shadow-md relative overflow-hidden transition hover:border-slate-600">
            <!-- Top Status Row: Receipt & Status on right (بدون علامت #), Date on left -->
            <div class="flex items-center justify-between border-b border-slate-700/60 pb-2">
              <div class="flex items-center gap-1.5">
                <span class="font-mono text-xs font-bold text-amber-500 dark:text-amber-400">فیش ${t.id}</span>
                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-bold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30">
                  <span class="w-1.5 h-1.5 rounded-full bg-amber-500 dark:bg-amber-400 animate-pulse"></span>
                  در انتظار بررسی
                </span>
              </div>
              <span class="font-mono text-[10px] text-slate-500" dir="ltr">${dateStr}</span>
            </div>

            <!-- Middle Row: Photo + Name & Price on right, Username + ID on left (بدون فاصله، کاملاً چسبیده به چپ) -->
            <div class="flex items-center justify-between gap-2.5">
              <div class="flex items-center gap-2.5 min-w-0">
                <div class="w-10 h-10 rounded-full bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-white text-xs shadow flex-shrink-0 overflow-hidden relative">
                  <img src="${avatarSrc}" alt="Avatar" class="w-full h-full object-cover" onerror="this.classList.add('hidden'); if(this.nextElementSibling) this.nextElementSibling.classList.remove('hidden');" />
                  <span class="font-bold">${escapeHtml(initial)}</span>
                </div>
                <div class="min-w-0 space-y-0.5">
                  <b class="t-main text-xs font-bold block truncate max-w-[140px] cursor-pointer hover:text-cyan-500 dark:hover:text-cyan-300" data-copy="${escapeHtml(uLabel)}" onclick="window.adminActions.quickCopy(this.dataset.copy, 'نام')" title="${escapeHtml(uLabel)}">${escapeHtml(uLabel)}</b>
                  <div class="flex items-baseline gap-1 text-emerald-400 font-bold" dir="rtl">
                    <span class="text-sm font-black font-mono leading-none">${formatNumber(t.amount || 0)}</span>
                    <span class="text-[10px] text-emerald-500/90 font-sans">تومان</span>
                  </div>
                </div>
              </div>

              <!-- Left column: Username on line 1, Numeric ID on line 2 (بدون ID: و کاملاً چسبیده به چپ بدون فاصله) -->
              <div class="flex flex-col items-start justify-center gap-0.5 font-mono text-[11px] text-slate-400 flex-shrink-0 text-left" dir="ltr">
                ${t.username ? `<span onclick="window.adminActions.quickCopy('@${escapeHtml(t.username)}', 'نام کاربری')" class="cursor-pointer hover:text-cyan-300 text-slate-300 font-mono truncate max-w-[130px] block leading-tight" title="@${escapeHtml(t.username)}">@${escapeHtml(t.username)}</span>` : ''}
                <span class="cursor-pointer hover:text-cyan-300 text-slate-400 font-mono block leading-tight" onclick="window.adminActions.quickCopy('${t.telegram_id}', 'شناسه عددی')" title="شناسه عددی">${t.telegram_id}</span>
              </div>
            </div>

            <!-- Action Buttons: Chat on right, Photo icon & Action buttons on left (همه بدون پس‌زمینه) -->
            <div class="flex items-center justify-between gap-2 pt-1 border-t border-slate-700/50">
              <button data-action="chat" data-tgid="${t.telegram_id}" data-name="${escapeHtml(uLabel)}" data-tag="${escapeHtml(usernameTag || ('#' + t.telegram_id))}" data-topupid="${t.id}" onclick="window.adminActions.openUserChat(this.dataset.tgid, this.dataset.name, this.dataset.tag, this.dataset.topupid)" class="btn btn-secondary px-3 py-1.5 rounded-xl text-xs font-medium transition flex items-center gap-1.5 active:scale-95" title="گفتگوی مستقیم با کاربر">
                <svg class="w-3.5 h-3.5 text-cyan-500 dark:text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
                <span>چت با کاربر</span>
              </button>

              <div class="flex items-center gap-1.5">
                ${hasPhoto ? `
                  <button type="button" onclick="window.adminActions.openReceiptImageModal('${photoUrl}', ${t.id})" class="w-8 h-8 rounded-xl bg-transparent hover:bg-cyan-500/10 text-cyan-400 border border-cyan-500/40 flex items-center justify-center transition active:scale-95 shadow-sm" title="مشاهده تصویر فیش">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                  </button>
                ` : `
                  <button type="button" data-action="receipt-info" data-topupid="${t.id}" data-hash="${escapeHtml(t.receipt_hash || '')}" data-amount="${formatNumber(t.amount || 0)}" onclick="window.adminActions.showReceiptInfoModal(this.dataset.topupid, this.dataset.hash, this.dataset.amount)" class="w-8 h-8 rounded-xl bg-transparent hover:bg-cyan-500/10 text-cyan-400 border border-cyan-500/40 flex items-center justify-center transition active:scale-95 shadow-sm" title="مشاهده مشخصات رسید / کد پیگیری">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                  </button>
                `}
                <button type="button" onclick="window.adminActions.handleTopup(${t.id}, false)" class="w-8 h-8 rounded-xl bg-transparent hover:bg-rose-500/10 text-rose-500 hover:text-rose-400 border border-rose-500/40 flex items-center justify-center transition active:scale-95 font-bold text-sm shadow-sm" title="رد فیش">
                  ✕
                </button>
                <button type="button" onclick="window.adminActions.handleTopup(${t.id}, true)" class="w-8 h-8 rounded-xl bg-transparent hover:bg-emerald-500/10 text-emerald-400 hover:text-emerald-300 border border-emerald-500/40 flex items-center justify-center transition active:scale-95 font-bold text-sm shadow-sm" title="تایید و شارژ موجودی">
                  ✓
                </button>
              </div>
            </div>
          </div>
        `;
      }).join('');
    } catch (err) {
      container.innerHTML = '<div class="p-4 text-center text-rose-400 text-xs">خطای شبکه در دریافت فیش‌ها</div>';
    }
  }



  $('settingEurRate')?.addEventListener('input', (e) => {
    const val = parseInt(e.target.value, 10);
    if (!isNaN(val) && val > 0) {
      window.currentEurRate = val;
    }
  });

  $('settingUsdtRate')?.addEventListener('input', (e) => {
    const val = parseInt(e.target.value, 10);
    if (!isNaN(val) && val > 0) {
      window.currentUsdRate = val;
    }
  });

  $('refreshTopupsBtn')?.addEventListener('click', () => {
    fetchAdminTopups();
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  $('viewPendingBtn')?.addEventListener('click', () => {
    if (typeof window.switchFinanceSubtab === 'function') {
      window.switchFinanceSubtab('topups');
    }
    const ticketsNav = document.querySelector('.admin-nav-btn[data-admin-tab="tab-admin-tickets"]');
    ticketsNav?.click();
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  // Global modal triggers for inline onclick backwards-compatibility

  // Global exports
  window.fetchAdminTopups = fetchAdminTopups;
})(window);
