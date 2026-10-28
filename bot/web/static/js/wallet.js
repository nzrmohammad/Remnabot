/**
 * RemnaStore Pro - Wallet & Topup Logic
 */

let currentTopupInvoice = null;
let allWalletTransactions = [];
let currentWalletPage = 1;
const TX_PER_PAGE = 10;

function formatTxTitle(tx) {
  if (!tx) return 'تراکنش';
  if (tx.type === 'order' || (tx.title && tx.title.startsWith('خرید '))) {
    const rawPlan = (tx.service_name || tx.title.replace(/^خرید\s+/, '')).trim();
    const formattedPlan = typeof formatPlanTitle === 'function' ? formatPlanTitle(rawPlan) : escapeHtml(rawPlan);
    return `<span class="inline-flex items-center gap-1"><span class="text-slate-400 font-normal">خرید</span> ${formattedPlan}</span>`;
  }
  return escapeHtml(tx.title || 'تراکنش');
}

function renderWalletTransactions(transactions) {
  const txContainer = document.getElementById('walletTransactionsList');
  if (!txContainer) return;

  if (transactions !== undefined && transactions !== null) {
    allWalletTransactions = transactions;
    currentWalletPage = 1;
  }

  const txList = allWalletTransactions || [];
  if (txList.length === 0) {
    txContainer.innerHTML = `
      <div class="p-4 rounded-xl bg-transparent border border-[var(--card-border)] text-center text-xs text-slate-400">
        <span>🧾 هنوز تراکنش یا سفارشی برای این حساب ثبت نشده است.</span>
      </div>
    `;
    const oldPag = document.getElementById('walletTxPagination');
    if (oldPag) oldPag.classList.add('hidden');
    return;
  }

  const totalPages = Math.ceil(txList.length / TX_PER_PAGE);
  if (currentWalletPage > totalPages) currentWalletPage = totalPages;
  if (currentWalletPage < 1) currentWalletPage = 1;

  const startIdx = (currentWalletPage - 1) * TX_PER_PAGE;
  const pageItems = txList.slice(startIdx, startIdx + TX_PER_PAGE);

  txContainer.innerHTML = pageItems.map(tx => {
    const statusColor = (tx.status_color === 'amber' || tx.status_color === 'yellow')
      ? 't-warn'
      : ((tx.status_color === 'rose' || tx.status_color === 'red')
        ? 't-danger'
        : (tx.status_color === 'slate' ? 't-muted' : 't-success'));
    return `
    <div class="card-inset rounded-xl p-3 flex items-center justify-between text-xs">
      <div class="flex items-center gap-2.5">
        <span class="text-xl">${tx.type === 'topup' ? '💳' : (tx.type === 'admin_adjust' ? '⚡️' : '🛒')}</span>
        <div>
          <span class="font-bold t-main block">${formatTxTitle(tx)}</span>
          <span class="text-[10px] t-muted font-mono mt-0.5" dir="ltr">${toEnglishDigits(tx.date_jalali || '')}</span>
        </div>
      </div>
      <div class="text-left space-y-0.5">
        <div class="inline-flex items-center gap-1 font-bold ${tx.is_positive ? 't-success' : 't-main'}" dir="rtl">
          <span class="font-mono text-xs" dir="ltr">${Number(tx.amount != null ? tx.amount : 0).toLocaleString('en-US')}</span>
          <span class="font-mono text-sm leading-none font-bold">${tx.is_positive ? '+' : '-'}</span>
          <span class="font-sans text-[10px] t-muted font-normal">تومان</span>
        </div>
        <span class="text-[10px] ${statusColor} font-sans block">
          ${escapeHtml(tx.status || 'موفق')}
        </span>
      </div>
    </div>
  `;
  }).join('');

  // Pagination Controls
  let pagEl = document.getElementById('walletTxPagination');
  if (!pagEl) {
    pagEl = document.createElement('div');
    pagEl.id = 'walletTxPagination';
    pagEl.className = 'flex items-center justify-between pt-2 border-t border-[var(--card-border)] text-xs';
    txContainer.parentNode.appendChild(pagEl);
  }

  if (totalPages <= 1) {
    pagEl.classList.add('hidden');
  } else {
    pagEl.classList.remove('hidden');
    pagEl.innerHTML = `
      <button type="button" id="walletPrevPageBtn" class="p-1.5 rounded-lg border border-[var(--card-border)] bg-transparent t-muted hover:t-main transition active:scale-95 flex items-center justify-center ${currentWalletPage === 1 ? 'opacity-30 cursor-not-allowed pointer-events-none' : ''}" title="صفحه قبل">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
      </button>
      <span class="text-[11px] text-slate-400 font-mono">
        صفحه <b class="t-main">${currentWalletPage}</b> از <b class="t-main">${totalPages}</b>
      </span>
      <button type="button" id="walletNextPageBtn" class="p-1.5 rounded-lg border border-[var(--card-border)] bg-transparent t-muted hover:t-main transition active:scale-95 flex items-center justify-center ${currentWalletPage === totalPages ? 'opacity-30 cursor-not-allowed pointer-events-none' : ''}" title="صفحه بعد">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
      </button>
    `;

    pagEl.querySelector('#walletNextPageBtn')?.addEventListener('click', () => {
      if (currentWalletPage < totalPages) {
        currentWalletPage++;
        renderWalletTransactions();
      }
    });

    pagEl.querySelector('#walletPrevPageBtn')?.addEventListener('click', () => {
      if (currentWalletPage > 1) {
        currentWalletPage--;
        renderWalletTransactions();
      }
    });
  }
}

function updateTopupDisplays(amt) {
  const cardAmountDisplay = document.getElementById('topupCardAmountDisplay');
  if (cardAmountDisplay) {
    cardAmountDisplay.innerText = `${Number(amt || 0).toLocaleString('en-US')} تومان`;
  }
  if (window.storeSettings?.ton_rate_toman && window.storeSettings.ton_rate_toman > 0) {
    const tonAmt = ((amt || 0) / window.storeSettings.ton_rate_toman).toFixed(4);
    const cryptoTonEl = document.getElementById('cryptoAmountTon');
    if (cryptoTonEl) cryptoTonEl.innerText = `${tonAmt} TON`;
  }
  if (window.storeSettings?.trx_rate_toman && window.storeSettings.trx_rate_toman > 0) {
    const trxAmt = ((amt || 0) / window.storeSettings.trx_rate_toman).toFixed(2);
    const trxDisplay = document.getElementById('trxAmountDisplay');
    if (trxDisplay) trxDisplay.innerText = `${trxAmt} TRX`;
  }
  const usdtRate = window.storeSettings?.usdt_rate_toman || 100000;
  const usdtAmt = ((amt || 0) / usdtRate).toFixed(2);
  const xrocketAmtEl = document.getElementById('xrocketAmountUsd');
  if (xrocketAmtEl) xrocketAmtEl.innerText = `${usdtAmt} USDT`;

  const starsRate = window.storeSettings?.stars_rate_toman || 1600;
  const starsCount = Math.max(1, Math.ceil((amt || 0) / starsRate));
  const starsReqEl = document.getElementById('starsRequiredCount');
  if (starsReqEl) starsReqEl.innerText = `${starsCount} ⭐️`;
  const starsRateEl = document.getElementById('starsRateDisplay');
  if (starsRateEl) starsRateEl.innerText = `${Number(starsRate).toLocaleString('en-US')} تومان`;
}

async function loadTopupInfo() {
  try {
    const res = await window.api.getTopupInfo();
    if (res.ok) {
      window.storeSettings = res;
      const cardNumEl = document.getElementById('topupCardNumber');
      const cardHolderEl = document.getElementById('topupCardHolder');
      if (cardNumEl) cardNumEl.innerText = res.card_number || 'هنوز ثبت نشده';
      if (cardHolderEl) cardHolderEl.innerText = res.card_holder || 'مدیریت سرور';

      const hasCard = res.card_enabled !== false;
      const hasStars = res.stars_enabled !== false;
      const hasCrypto = res.crypto_enabled !== false;
      const anyMethodEnabled = hasCard || hasStars || hasCrypto;

      const tabsContainer = document.getElementById('topupMethodTabs');
      const amountSection = document.getElementById('topupAmountSection');
      const disabledState = document.getElementById('topupAllDisabledState');
      const viewCard = document.getElementById('topupCardView');
      const viewStars = document.getElementById('topupStarsView');
      const viewCrypto = document.getElementById('topupCryptoView');

      if (!anyMethodEnabled) {
        tabsContainer?.classList.add('hidden');
        amountSection?.classList.add('hidden');
        viewCard?.classList.add('hidden');
        viewStars?.classList.add('hidden');
        viewCrypto?.classList.add('hidden');
        disabledState?.classList.remove('hidden');
      } else {
        disabledState?.classList.add('hidden');
        tabsContainer?.classList.remove('hidden');
        amountSection?.classList.remove('hidden');

        if (!hasStars) {
          document.getElementById('topupMethodStarsBtn')?.classList.add('hidden');
        } else {
          document.getElementById('topupMethodStarsBtn')?.classList.remove('hidden');
        }

        if (!hasCard) {
          document.getElementById('topupMethodCardBtn')?.classList.add('hidden');
        } else {
          document.getElementById('topupMethodCardBtn')?.classList.remove('hidden');
        }

        if (!hasCrypto) {
          document.getElementById('topupMethodCryptoBtn')?.classList.add('hidden');
        } else {
          document.getElementById('topupMethodCryptoBtn')?.classList.remove('hidden');
        }
      }

      const cardPhoneWarning = document.getElementById('cardPhoneVerificationWarning');
      const cardDetailsBox = document.getElementById('topupCardDetailsBox');
      const submitCardBtn = document.getElementById('submitCardTopupBtn');
      const cardUploadBtn = document.getElementById('uploadCardReceiptImageBtn');
      if (res.card_require_phone_verification && !res.is_phone_verified) {
        if (cardPhoneWarning) cardPhoneWarning.classList.remove('hidden');
        if (cardDetailsBox) cardDetailsBox.classList.add('hidden');
        if (submitCardBtn) {
          submitCardBtn.disabled = true;
          submitCardBtn.classList.add('opacity-40', 'cursor-not-allowed');
          submitCardBtn.innerText = '🔒 نیاز به تأیید شماره تماس';
        }
        if (cardUploadBtn) {
          cardUploadBtn.disabled = true;
          cardUploadBtn.classList.add('opacity-40', 'cursor-not-allowed');
        }
      } else {
        if (cardPhoneWarning) cardPhoneWarning.classList.add('hidden');
        if (cardDetailsBox) cardDetailsBox.classList.remove('hidden');
        if (submitCardBtn) {
          submitCardBtn.disabled = false;
          submitCardBtn.classList.remove('opacity-40', 'cursor-not-allowed');
          submitCardBtn.innerText = '📤 ثبت و ارسال رسید پرداخت';
        }
        if (cardUploadBtn) {
          cardUploadBtn.disabled = false;
          cardUploadBtn.classList.remove('opacity-40', 'cursor-not-allowed');
        }
      }

      const inputEl = document.getElementById('topupAmountInput');
      updateTopupDisplays(parseInt(inputEl?.value || '50000'));
    }
  } catch (err) {}
}

let cryptoCountdownTimerInterval = null;

function switchTopupTab(tab) {
  const btnCard = document.getElementById('topupMethodCardBtn');
  const btnStars = document.getElementById('topupMethodStarsBtn');
  const btnCrypto = document.getElementById('topupMethodCryptoBtn');
  const btnTrx = document.getElementById('topupMethodTrxBtn');
  const btnXRocket = document.getElementById('topupMethodXRocketBtn');

  const viewCard = document.getElementById('topupCardView');
  const viewStars = document.getElementById('topupStarsView');
  const viewCrypto = document.getElementById('topupCryptoView');
  const viewTrx = document.getElementById('topupTrxView');
  const viewXRocket = document.getElementById('topupXRocketView');

  [btnCard, btnStars, btnCrypto, btnTrx, btnXRocket].forEach(b => {
    if (b) {
      b.classList.remove('bg-blue-600', 'text-white');
      b.classList.add('text-slate-400');
    }
  });
  [viewCard, viewStars, viewCrypto, viewTrx, viewXRocket].forEach(v => {
    if (v) v.classList.add('hidden');
  });

  if (tab === 'card') {
    btnCard?.classList.add('bg-blue-600', 'text-white');
    btnCard?.classList.remove('text-slate-400');
    viewCard?.classList.remove('hidden');
  } else if (tab === 'stars') {
    btnStars?.classList.add('bg-blue-600', 'text-white');
    btnStars?.classList.remove('text-slate-400');
    viewStars?.classList.remove('hidden');
  } else if (tab === 'crypto') {
    btnCrypto?.classList.add('bg-blue-600', 'text-white');
    btnCrypto?.classList.remove('text-slate-400');
    viewCrypto?.classList.remove('hidden');
  } else if (tab === 'trx') {
    btnTrx?.classList.add('bg-blue-600', 'text-white');
    btnTrx?.classList.remove('text-slate-400');
    viewTrx?.classList.remove('hidden');
  } else if (tab === 'xrocket') {
    btnXRocket?.classList.add('bg-blue-600', 'text-white');
    btnXRocket?.classList.remove('text-slate-400');
    viewXRocket?.classList.remove('hidden');
  }
}

function switchToCryptoTab() { switchTopupTab('crypto'); }
function switchToCardTab() { switchTopupTab('card'); }
function switchToStarsTab() { switchTopupTab('stars'); }

function updatePendingCardUI(invoice, remainingSec) {
  const card = document.getElementById('activeCryptoPendingCard');
  if (!card) return;
  if (!invoice) {
    card.classList.add('hidden');
    return;
  }
  card.classList.remove('hidden');
  const amtEl = document.getElementById('activeCryptoPendingAmount');
  if (amtEl) amtEl.innerText = `${invoice.amount_ton} TON`;
  const timerEl = document.getElementById('activeCryptoPendingTimer');
  if (timerEl && remainingSec !== undefined) {
    const mins = Math.max(0, Math.floor(remainingSec / 60));
    const secs = Math.max(0, remainingSec % 60);
    timerEl.innerText = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }
}

function getActiveCryptoStorageKey() {
  const tgId = window.lastUserData?.user?.telegram_id || window.Telegram?.WebApp?.initDataUnsafe?.user?.id || 'default';
  return `remna_active_crypto_invoice_${tgId}`;
}

function startCryptoCountdownTimer(seconds = 2700) {
  if (cryptoCountdownTimerInterval) {
    clearInterval(cryptoCountdownTimerInterval);
    cryptoCountdownTimerInterval = null;
  }
  let targetEnd = Date.now() + (seconds * 1000);
  try {
    const raw = localStorage.getItem(getActiveCryptoStorageKey()) || localStorage.getItem('remna_active_crypto_invoice');
    if (raw) {
      const data = JSON.parse(raw);
      if (data && data.expires_at) targetEnd = data.expires_at;
    }
  } catch (e) {}

  const timerEl = document.getElementById('cryptoCountdownTimer');
  if (timerEl) {
    timerEl.classList.remove('t-danger', 'text-rose-400', 'bg-rose-500/10', 'border-rose-500/20', 'bg-amber-500/10', 'border-amber-500/20');
    timerEl.classList.add('t-warn');
  }

  const updateDisplay = () => {
    const now = Date.now();
    const remaining = Math.max(0, Math.floor((targetEnd - now) / 1000));
    const timer = document.getElementById('cryptoCountdownTimer');
    const pendingTimer = document.getElementById('activeCryptoPendingTimer');

    if (remaining <= 0) {
      if (timer) {
        timer.innerText = '00:00 (منقضی شد)';
        timer.classList.remove('t-warn', 'text-amber-400', 'bg-amber-500/10', 'border-amber-500/20');
        timer.classList.add('t-danger');
      }
      if (pendingTimer) {
        pendingTimer.innerText = '00:00 (منقضی شد)';
      }
      if (cryptoCountdownTimerInterval) {
        clearInterval(cryptoCountdownTimerInterval);
        cryptoCountdownTimerInterval = null;
      }
      try {
        localStorage.removeItem(getActiveCryptoStorageKey());
        try { localStorage.removeItem('remna_active_crypto_invoice'); } catch (e) {}
      } catch (e) {}
      updatePendingCardUI(null);
      return;
    }
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    const timeStr = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    if (timer) timer.innerText = timeStr;
    if (pendingTimer) pendingTimer.innerText = timeStr;
  };

  updateDisplay();
  cryptoCountdownTimerInterval = setInterval(updateDisplay, 1000);
}

function stopCryptoCountdownTimer() {
  if (cryptoCountdownTimerInterval) {
    clearInterval(cryptoCountdownTimerInterval);
    cryptoCountdownTimerInterval = null;
  }
}

function saveActiveCryptoInvoice(inv, durationSec = 2700) {
  try {
    const expiresAt = Date.now() + (durationSec * 1000);
    localStorage.setItem(getActiveCryptoStorageKey(), JSON.stringify({
      invoice: inv,
      expires_at: expiresAt
    }));
  } catch (e) {}
}

function clearActiveCryptoInvoice() {
  try {
    localStorage.removeItem(getActiveCryptoStorageKey());
    try { localStorage.removeItem('remna_active_crypto_invoice'); } catch (e) {}
  } catch (e) {}
  currentTopupInvoice = null;
  stopCryptoCountdownTimer();

  const detailsEl = document.getElementById('cryptoInvoiceDetails');
  const initialEl = document.getElementById('cryptoInvoiceInitial');
  if (detailsEl) detailsEl.classList.add('hidden');
  if (initialEl) initialEl.classList.remove('hidden');

  updatePendingCardUI(null);

  const genBtn = document.getElementById('generateTonInvoiceBtn');
  if (genBtn) {
    genBtn.disabled = false;
    genBtn.innerText = '💎 ایجاد فاکتور پرداخت TON';
  }

  const timerEl = document.getElementById('cryptoCountdownTimer');
  if (timerEl) {
    timerEl.innerText = '45:00';
    timerEl.classList.remove('t-danger', 'text-rose-400', 'bg-rose-500/10', 'border-rose-500/20', 'bg-amber-500/10', 'border-amber-500/20');
    timerEl.classList.add('t-warn');
  }

  const amtEl = document.getElementById('cryptoAmountTon');
  if (amtEl) amtEl.innerText = '-- TON';
  const addrEl = document.getElementById('cryptoPayAddress');
  if (addrEl) addrEl.innerText = '--';
  const commEl = document.getElementById('cryptoComment');
  if (commEl) commEl.innerText = '--';
}

window.cancelCryptoInvoice = function() {
  clearActiveCryptoInvoice();
  showToast('✅ فاکتور لغو شد. می‌توانید فاکتور جدید صادر فرمایید.');
};

function restoreActiveCryptoInvoice() {
  try {
    const raw = localStorage.getItem(getActiveCryptoStorageKey()) || localStorage.getItem('remna_active_crypto_invoice');
    if (!raw) {
      updatePendingCardUI(null);
      return false;
    }
    const data = JSON.parse(raw);
    const now = Date.now();
    const remainingSec = Math.floor((data.expires_at - now) / 1000);
    if (remainingSec <= 0 || !data.invoice) {
      clearActiveCryptoInvoice();
      return false;
    }
    currentTopupInvoice = data.invoice;
    document.getElementById('cryptoInvoiceInitial')?.classList.add('hidden');
    document.getElementById('cryptoInvoiceDetails')?.classList.remove('hidden');
    const amtEl = document.getElementById('cryptoAmountTon');
    if (amtEl) amtEl.innerText = `${data.invoice.amount_ton} TON`;
    const addrEl = document.getElementById('cryptoPayAddress');
    if (addrEl) addrEl.innerText = data.invoice.pay_address;
    const commEl = document.getElementById('cryptoComment');
    if (commEl) commEl.innerText = data.invoice.comment;
    const targetLink = data.invoice.universal_link || data.invoice.deep_link || '#';
    const tonBtn = document.getElementById('cryptoTonkeeperLink');
    if (tonBtn) tonBtn.href = targetLink;
    startCryptoCountdownTimer(remainingSec);
    updatePendingCardUI(data.invoice, remainingSec);
    return true;
  } catch (e) {
    return false;
  }
}

let currentTrxInvoice = null;

function getActiveTrxStorageKey() {
  const tgId = window.lastUserData?.user?.telegram_id || window.Telegram?.WebApp?.initDataUnsafe?.user?.id || 'default';
  return `remna_active_trx_invoice_${tgId}`;
}

function saveActiveTrxInvoice(inv) {
  try {
    const expiresAt = Date.now() + (60 * 60 * 1000);
    localStorage.setItem(getActiveTrxStorageKey(), JSON.stringify({
      invoice: inv,
      expires_at: expiresAt
    }));
  } catch (e) {}
}

function clearActiveTrxInvoice() {
  try {
    localStorage.removeItem(getActiveTrxStorageKey());
  } catch (e) {}
  currentTrxInvoice = null;
  const detailsEl = document.getElementById('trxInvoiceDetails');
  const initialEl = document.getElementById('trxInvoiceInitial');
  if (detailsEl) detailsEl.classList.add('hidden');
  if (initialEl) initialEl.classList.remove('hidden');
  const input = document.getElementById('trxTxIdInput');
  if (input) input.value = '';
}

function restoreActiveTrxInvoice() {
  try {
    const raw = localStorage.getItem(getActiveTrxStorageKey());
    if (!raw) return false;
    const data = JSON.parse(raw);
    const now = Date.now();
    if (now >= data.expires_at || !data.invoice) {
      clearActiveTrxInvoice();
      return false;
    }
    currentTrxInvoice = data.invoice;
    document.getElementById('trxInvoiceInitial')?.classList.add('hidden');
    document.getElementById('trxInvoiceDetails')?.classList.remove('hidden');
    const amtEl = document.getElementById('trxAmountDisplay');
    if (amtEl) amtEl.innerText = `${data.invoice.amount_trx} TRX`;
    const addrEl = document.getElementById('trxPayAddress');
    if (addrEl) addrEl.innerText = data.invoice.pay_address;
    return true;
  } catch (e) {
    return false;
  }
}

async function openTopupModal(defaultAmt, forceCrypto = false) {
  const amt = defaultAmt && defaultAmt >= 50000 ? defaultAmt : 50000;
  const inputEl = document.getElementById('topupAmountInput');
  if (inputEl) inputEl.value = amt;
  updateTopupDisplays(amt);

  const applyMethodTabs = (s) => {
    if (!s) return;
    const hasActiveCrypto = restoreActiveCryptoInvoice();
    const hasActiveTrx = restoreActiveTrxInvoice();
    const anyEnabled = s.card_enabled !== false || s.stars_enabled !== false || s.crypto_enabled !== false || s.trx_enabled !== false || s.xrocket_enabled !== false;
    if (!anyEnabled) {
      document.getElementById('topupMethodTabs')?.classList.add('hidden');
      document.getElementById('topupAmountSection')?.classList.add('hidden');
      document.getElementById('topupCardView')?.classList.add('hidden');
      document.getElementById('topupStarsView')?.classList.add('hidden');
      document.getElementById('topupCryptoView')?.classList.add('hidden');
      document.getElementById('topupTrxView')?.classList.add('hidden');
      document.getElementById('topupXRocketView')?.classList.add('hidden');
      document.getElementById('topupAllDisabledState')?.classList.remove('hidden');
    } else if ((hasActiveCrypto || forceCrypto) && s.crypto_enabled !== false) {
      switchToCryptoTab();
    } else if (hasActiveTrx && s.trx_enabled !== false) {
      switchTopupTab('trx');
    } else if (s.card_enabled !== false) {
      switchToCardTab();
    } else if (s.crypto_enabled !== false) {
      switchToCryptoTab();
    } else if (s.trx_enabled !== false) {
      switchTopupTab('trx');
    } else if (s.xrocket_enabled !== false) {
      switchTopupTab('xrocket');
    } else if (s.stars_enabled !== false) {
      switchTopupTab('stars');
    }
  };

  // Apply cached storeSettings immediately if available
  applyMethodTabs(window.storeSettings);

  // Open modal immediately with 0ms delay
  openModal('topupModal');

  // Load/refresh settings in background (SWR pattern)
  await loadTopupInfo();
  applyMethodTabs(window.storeSettings);
}

function setupWalletListeners() {
  const topupAmountInput = document.getElementById('topupAmountInput');
  topupAmountInput?.addEventListener('input', (e) => {
    updateTopupDisplays(parseInt(e.target.value || '0'));
  });

  document.querySelectorAll('.topup-preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const amt = parseInt(btn.getAttribute('data-amt') || '50000');
      if (topupAmountInput) topupAmountInput.value = amt;
      updateTopupDisplays(amt);
    });
  });

  const methodCardBtn = document.getElementById('topupMethodCardBtn');
  const methodStarsBtn = document.getElementById('topupMethodStarsBtn');
  const methodCryptoBtn = document.getElementById('topupMethodCryptoBtn');
  const methodTrxBtn = document.getElementById('topupMethodTrxBtn');
  const methodXRocketBtn = document.getElementById('topupMethodXRocketBtn');

  methodCardBtn?.addEventListener('click', () => {
    switchTopupTab('card');
  });

  methodStarsBtn?.addEventListener('click', () => {
    switchTopupTab('stars');
  });

  methodCryptoBtn?.addEventListener('click', () => {
    switchTopupTab('crypto');
    restoreActiveCryptoInvoice();
  });

  methodTrxBtn?.addEventListener('click', () => {
    switchTopupTab('trx');
    restoreActiveTrxInvoice();
  });

  methodXRocketBtn?.addEventListener('click', () => {
    switchTopupTab('xrocket');
  });

  document.getElementById('closeTopupModalBtn')?.addEventListener('click', () => {
    closeModal('topupModal');
  });

  document.getElementById('chargeWalletBtn')?.addEventListener('click', () => {
    openTopupModal(50000);
  });

  document.getElementById('openActiveCryptoBtn')?.addEventListener('click', () => {
    openTopupModal(50000, true);
  });

  document.getElementById('chargeWalletBtn')?.addEventListener('click', () => {
    openTopupModal(50000);
  });

  const handleCopyCard = () => {
    const cardEl = document.getElementById('topupCardNumber');
    const card = cardEl?.innerText?.trim();
    if (card && !card.includes('----') && !card.includes('ثبت نشده')) {
      const cleanDigits = card.replace(/[^\d]/g, '');
      copyToClipboard(cleanDigits || card, '📋 شماره کارت در کلیپ‌بورد کپی شد.');
      hapticFeedback('success');
      const btn = document.getElementById('copyTopupCardBtn');
      if (btn) {
        btn.innerText = '✅';
        setTimeout(() => { btn.innerText = '📋'; }, 1500);
      }
    } else {
      showToast('⚠️ شماره کارتی برای کپی کردن یافت نشد.');
    }
  };

  document.getElementById('copyTopupCardBtn')?.addEventListener('click', handleCopyCard);
  document.getElementById('topupCardNumber')?.addEventListener('click', handleCopyCard);

  const handleCopyCardAmount = () => {
    const amtEl = document.getElementById('topupCardAmountDisplay');
    const amtText = amtEl?.innerText?.trim();
    if (amtText && !amtText.includes('--')) {
      const cleanDigits = amtText.replace(/[^\d]/g, '');
      copyToClipboard(cleanDigits || amtText, '📋 مبلغ در کلیپ‌بورد کپی شد.');
      hapticFeedback('success');
      const btn = document.getElementById('copyTopupCardAmountBtn');
      if (btn) {
        btn.innerText = '✅';
        setTimeout(() => { btn.innerText = '📋'; }, 1500);
      }
    }
  };

  document.getElementById('copyTopupCardAmountBtn')?.addEventListener('click', handleCopyCardAmount);
  document.getElementById('topupCardAmountDisplay')?.addEventListener('click', handleCopyCardAmount);

  let selectedReceiptImageBase64 = null;
  const imageInput = document.getElementById('topupCardImageInput');
  const uploadImgBtn = document.getElementById('uploadCardReceiptImageBtn');
  const previewContainer = document.getElementById('receiptImagePreviewContainer');
  const previewImg = document.getElementById('receiptImagePreview');
  const previewName = document.getElementById('receiptImageName');
  const removeImgBtn = document.getElementById('removeReceiptImageBtn');

  uploadImgBtn?.addEventListener('click', () => {
    imageInput?.click();
  });

  function compressReceiptImage(file, maxDimension = 1400, quality = 0.85) {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = (evt) => {
        const rawData = evt.target.result;
        const img = new Image();
        img.onload = () => {
          let { width, height } = img;
          if (width > maxDimension || height > maxDimension) {
            if (width > height) {
              height = Math.round((height * maxDimension) / width);
              width = maxDimension;
            } else {
              width = Math.round((width * maxDimension) / height);
              height = maxDimension;
            }
          }
          const canvas = document.createElement('canvas');
          canvas.width = width;
          canvas.height = height;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(img, 0, 0, width, height);
          resolve(canvas.toDataURL('image/jpeg', quality));
        };
        img.onerror = () => resolve(rawData);
        img.src = rawData;
      };
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(file);
    });
  }

  imageInput?.addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      showToast('⚠️ حداکثر حجم مجاز تصویر ۱۰ مگابایت است.');
      return;
    }
    const compressedBase64 = await compressReceiptImage(file);
    if (!compressedBase64) {
      showToast('⚠️ خطا در پردازش تصویر فیش.');
      return;
    }
    selectedReceiptImageBase64 = compressedBase64;
    if (previewImg) previewImg.src = selectedReceiptImageBase64;
    if (previewName) previewName.innerText = file.name || 'تصویر رسید انتخاب شد';
    previewContainer?.classList.remove('hidden');
    uploadImgBtn?.classList.add('hidden');
  });

  removeImgBtn?.addEventListener('click', () => {
    selectedReceiptImageBase64 = null;
    if (imageInput) imageInput.value = '';
    previewContainer?.classList.add('hidden');
    uploadImgBtn?.classList.remove('hidden');
  });

  document.getElementById('submitCardTopupBtn')?.addEventListener('click', async () => {
    const amt = parseInt(topupAmountInput?.value || '0');
    const receipt = document.getElementById('topupCardReceiptInput')?.value?.trim();
    if (!amt || amt < 10000) {
      showToast('⚠️ لطفاً مبلغ معتبر وارد فرمایید.');
      return;
    }
    if (!selectedReceiptImageBase64) {
      showToast('⚠️ لطفاً تصویر فیش واریزی را بارگذاری فرمایید.');
      return;
    }

    const submitBtn = document.getElementById('submitCardTopupBtn');
    submitBtn.disabled = true;
    submitBtn.innerText = 'در حال ثبت...';
    try {
      const res = await window.api.submitCardTopup(amt, receipt || 'تصویر فیش پیوست شد', selectedReceiptImageBase64);
      if (res.ok) {
        showToast('✅ رسید با موفقیت ثبت شد و پس از بررسی ادمین حساب شارژ می‌گردد.');
        selectedReceiptImageBase64 = null;
        if (imageInput) imageInput.value = '';
        previewContainer?.classList.add('hidden');
        uploadImgBtn?.classList.remove('hidden');
        closeModal('topupModal');
        if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
      } else {
        showToast(`❌ ${res.message || 'خطا در ثبت رسید'}`);
      }
    } catch (e) {
      showToast('❌ خطا در ارسال درخواست.');
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerText = '📤 ثبت و ارسال رسید پرداخت';
    }
  });

  document.getElementById('submitStarsTopupBtn')?.addEventListener('click', async () => {
    const amt = parseInt(topupAmountInput?.value || '0', 10);
    if (!amt || amt < 10000) {
      showToast('⚠️ لطفاً مبلغ معتبر وارد فرمایید.');
      return;
    }
    const btn = document.getElementById('submitStarsTopupBtn');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span>⏳</span> در حال ایجاد فاکتور استارز...';
    }
    try {
      const res = await window.api.createStarsInvoice(amt);
      if (res && res.ok && res.invoice_link) {
        if (window.Telegram?.WebApp?.openInvoice) {
          window.Telegram.WebApp.openInvoice(res.invoice_link, (status) => {
            if (status === 'paid') {
              showToast('🎉 پرداخت استارز با موفقیت تایید شد و کیف پول شارژ گردید!');
              closeModal('topupModal');
              const sync = () => {
                if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
              };
              sync();
              setTimeout(sync, 1500);
            } else if (status === 'cancelled') {
              showToast('پرداخت استارز لغو شد.');
            } else if (status === 'failed') {
              showToast('❌ پرداخت استارز انجام نشد.');
            }
          });
        } else {
          window.open(res.invoice_link, '_blank');
        }
      } else {
        showToast(`❌ ${res?.error || res?.message || 'خطا در ایجاد فاکتور استارز'}`);
      }
    } catch (e) {
      showToast('❌ خطا در ارتباط با سرور.');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<span>⭐</span> پرداخت با استارز تلگرام';
      }
    }
  });

  document.getElementById('generateTonInvoiceBtn')?.addEventListener('click', async () => {
    const amt = parseInt(topupAmountInput?.value || '0');
    if (!amt || amt < 10000) {
      showToast('⚠️ لطفاً مبلغ معتبر وارد فرمایید.');
      return;
    }
    const genBtn = document.getElementById('generateTonInvoiceBtn');
    genBtn.disabled = true;
    genBtn.innerText = 'ایجاد فاکتور...';
    try {
      const res = await window.api.createCryptoInvoice(amt);
      if (res.ok && res.invoice) {
        currentTopupInvoice = res.invoice;
        const durationSec = (res.invoice.expires_minutes ? res.invoice.expires_minutes * 60 : 2700);
        saveActiveCryptoInvoice(res.invoice, durationSec);
        document.getElementById('cryptoInvoiceInitial')?.classList.add('hidden');
        document.getElementById('cryptoInvoiceDetails')?.classList.remove('hidden');
        document.getElementById('cryptoAmountTon').innerText = `${res.invoice.amount_ton} TON`;
        document.getElementById('cryptoPayAddress').innerText = res.invoice.pay_address;
        document.getElementById('cryptoComment').innerText = res.invoice.comment;
        const targetLink = res.invoice.universal_link || res.invoice.deep_link || '#';
        const tonBtn = document.getElementById('cryptoTonkeeperLink');
        if (tonBtn) tonBtn.href = targetLink;
        startCryptoCountdownTimer(durationSec);
      } else {
        showToast(`❌ ${res.message || 'خطا در ایجاد فاکتور کریپتو'}`);
      }
    } catch (e) {
      showToast('❌ خطا در برقراری ارتباط.');
    } finally {
      genBtn.disabled = false;
      genBtn.innerText = '💎 ایجاد فاکتور پرداخت TON';
    }
  });

  document.getElementById('cryptoTonkeeperLink')?.addEventListener('click', (e) => {
    e.preventDefault();
    const targetLink = currentTopupInvoice?.universal_link || currentTopupInvoice?.deep_link;
    if (targetLink) {
      if (window.Telegram?.WebApp?.openLink) {
        try {
          window.Telegram.WebApp.openLink(targetLink);
        } catch(err) {
          window.open(targetLink, '_blank');
        }
      } else {
        window.open(targetLink, '_blank');
      }
    }
  });

  document.getElementById('copyTonAmountBtn')?.addEventListener('click', () => {
    if (currentTopupInvoice?.amount_ton) {
      copyToClipboard(String(currentTopupInvoice.amount_ton), '📋 مقدار TON کپی شد.');
    }
  });

  document.getElementById('copyTonAddressBtn')?.addEventListener('click', () => {
    if (currentTopupInvoice?.pay_address) {
      copyToClipboard(currentTopupInvoice.pay_address, '📋 آدرس ولت TON کپی شد.');
    }
  });

  document.getElementById('copyTonCommentBtn')?.addEventListener('click', () => {
    if (currentTopupInvoice?.comment) {
      copyToClipboard(currentTopupInvoice.comment, '📋 کامنت (Memo) کپی شد.');
    }
  });

  document.getElementById('cryptoCancelInvoiceBtn')?.addEventListener('click', () => {
    clearActiveCryptoInvoice();
    showToast('فاکتور قبلی لغو شد. می‌توانید فاکتور جدید صادر فرمایید.');
  });

  document.getElementById('cryptoCheckStatusBtn')?.addEventListener('click', async () => {
    if (!currentTopupInvoice?.id) return;
    const chkBtn = document.getElementById('cryptoCheckStatusBtn');
    chkBtn.disabled = true;
    chkBtn.innerText = 'در حال بررسی شبکه...';
    try {
      const res = await window.api.checkCryptoInvoice(currentTopupInvoice.id);
      if (res.ok && res.paid) {
        showToast('🎉 پرداخت تایید شد و کیف پول شارژ گردید!');
        clearActiveCryptoInvoice();
        closeModal('topupModal');
        if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
      } else {
        showToast(res.message || 'تراکنش هنوز تایید نشده است.');
      }
    } catch (e) {
      showToast('❌ خطا در استعلام پرداخت.');
    } finally {
      chkBtn.disabled = false;
      chkBtn.innerText = '🔄 بررسی وضعیت پرداخت';
    }
  });

  const redeemBtn = document.getElementById('redeemVoucherBtn');
  const voucherInput = document.getElementById('voucherCodeInput');
  if (redeemBtn && voucherInput) {
    redeemBtn.addEventListener('click', async () => {
      const code = voucherInput.value.trim();
      if (!code) {
        showToast('لطفاً کد شارژ را وارد نمایید.', 'warning');
        return;
      }
      redeemBtn.disabled = true;
      redeemBtn.innerText = 'در حال بررسی...';
      try {
        const res = await window.api.redeemVoucher(code);
        if (res.ok) {
          showToast(res.message || 'کیف پول با موفقیت شارژ گردید!', 'success');
          voucherInput.value = '';
          const haptic = window.api?.haptic || window.hapticFeedback;
          if (haptic) haptic('success');
          if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
        } else {
          showToast(res.message || 'کد شارژ نامعتبر است.', 'error');
        }
      } catch (err) {
        showToast('خطا در برقراری ارتباط با سرور.', 'error');
      } finally {
        redeemBtn.disabled = false;
        redeemBtn.innerText = 'اعمال';
      }
    });
  }

  document.getElementById('tonConnectPayBtn')?.addEventListener('click', () => {
    if (!currentTopupInvoice?.pay_address) {
      showToast('⚠️ ابتدا فاکتور پرداخت TON را ایجاد فرمایید.');
      return;
    }
    const address = currentTopupInvoice.pay_address;
    const amountNano = Math.round((Number(currentTopupInvoice.amount_ton) || 0) * 1e9);
    const text = encodeURIComponent(currentTopupInvoice.comment || '');
    const tonUrl = `ton://transfer/${address}?amount=${amountNano}&text=${text}`;
    if (window.Telegram?.WebApp?.openLink) {
      try {
        window.Telegram.WebApp.openLink(tonUrl);
      } catch (e) {
        window.open(tonUrl, '_blank');
      }
    } else {
      window.open(tonUrl, '_blank');
    }
  });

  // TRX Gateway Listeners
  document.getElementById('generateTrxInvoiceBtn')?.addEventListener('click', async () => {
    const amt = parseInt(topupAmountInput?.value || '0', 10);
    if (!amt || amt < 10000) {
      showToast('⚠️ لطفاً مبلغ معتبر وارد فرمایید (حداقل ۱۰,۰۰۰ تومان).');
      return;
    }
    const btn = document.getElementById('generateTrxInvoiceBtn');
    btn.disabled = true;
    btn.innerText = 'در حال ایجاد فاکتور ترون...';
    try {
      const res = await window.api.createTrxInvoice(amt);
      if (res.ok && res.invoice) {
        currentTrxInvoice = res.invoice;
        saveActiveTrxInvoice(res.invoice);
        document.getElementById('trxInvoiceInitial')?.classList.add('hidden');
        document.getElementById('trxInvoiceDetails')?.classList.remove('hidden');
        const amtEl = document.getElementById('trxAmountDisplay');
        if (amtEl) amtEl.innerText = `${res.invoice.amount_trx} TRX`;
        const addrEl = document.getElementById('trxPayAddress');
        if (addrEl) addrEl.innerText = res.invoice.pay_address;
      } else {
        showToast(`❌ ${res.message || 'خطا در ایجاد فاکتور ترون'}`);
      }
    } catch (e) {
      showToast('❌ خطا در برقراری ارتباط با سرور.');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>🔴</span> ایجاد فاکتور ترون (TRX)';
    }
  });

  const handleCopyTrxAddress = () => {
    const addr = document.getElementById('trxPayAddress')?.innerText?.trim();
    if (addr && addr !== '--') {
      copyToClipboard(addr, '📋 آدرس ولت ترون کپی شد.');
      hapticFeedback('success');
    }
  };
  document.getElementById('copyTrxAddressBtn')?.addEventListener('click', handleCopyTrxAddress);
  document.getElementById('trxPayAddress')?.addEventListener('click', handleCopyTrxAddress);

  document.getElementById('copyTrxAmountBtn')?.addEventListener('click', () => {
    const amt = currentTrxInvoice?.amount_trx;
    if (amt) {
      copyToClipboard(String(amt), '📋 مقدار TRX کپی شد.');
      hapticFeedback('success');
    }
  });

  document.getElementById('cancelTrxInvoiceBtn')?.addEventListener('click', () => {
    clearActiveTrxInvoice();
    showToast('فاکتور ترون لغو شد.');
  });

  document.getElementById('submitTrxTxIdBtn')?.addEventListener('click', async () => {
    if (!currentTrxInvoice?.id) {
      showToast('⚠️ ابتدا فاکتور ترون را ایجاد فرمایید.');
      return;
    }
    const txId = document.getElementById('trxTxIdInput')?.value?.trim();
    if (!txId) {
      showToast('⚠️ لطفاً شناسه تراکنش (TxID) را وارد فرمایید.');
      return;
    }
    const btn = document.getElementById('submitTrxTxIdBtn');
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> در حال استعلام از شبکه ترون...';
    try {
      const res = await window.api.verifyTrxInvoice(currentTrxInvoice.id, txId);
      if (res.ok) {
        showToast('🎉 واریز TRX در شبکه تأیید شد و کیف پول شارژ گردید!');
        clearActiveTrxInvoice();
        closeModal('topupModal');
        hapticFeedback('success');
        if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
      } else {
        showToast(`❌ ${res.message || 'تراکنش در شبکه ترون تأیید نشد'}`);
      }
    } catch (e) {
      showToast('❌ خطا در بررسی تراکنش.');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>🔍</span> بررسی و تأیید واریز TRX';
    }
  });

  // xRocket Gateway Listener
  document.getElementById('submitXRocketTopupBtn')?.addEventListener('click', async () => {
    const amt = parseInt(topupAmountInput?.value || '0', 10);
    if (!amt || amt < 10000) {
      showToast('⚠️ لطفاً مبلغ معتبر وارد فرمایید.');
      return;
    }
    const currency = document.getElementById('xrocketCurrencySelect')?.value || 'USDT';
    const btn = document.getElementById('submitXRocketTopupBtn');
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> در حال ایجاد فاکتور xRocket...';
    try {
      const res = await window.api.createXRocketInvoice(amt, currency);
      if (res.ok && res.pay_url) {
        if (window.Telegram?.WebApp?.openTelegramLink && res.pay_url.includes('t.me')) {
          window.Telegram.WebApp.openTelegramLink(res.pay_url);
        } else if (window.Telegram?.WebApp?.openLink) {
          window.Telegram.WebApp.openLink(res.pay_url);
        } else {
          window.open(res.pay_url, '_blank');
        }
        showToast('🚀 درگاه xRocket باز شد. پس از پرداخت، کیف پول به‌صورت آنی شارژ خواهد شد.');
        closeModal('topupModal');
      } else {
        showToast(`❌ ${res.message || res.error || 'خطا در ایجاد درگاه xRocket'}`);
      }
    } catch (e) {
      showToast('❌ خطا در ارتباط با سرور.');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>🚀</span> ایجاد و پرداخت با xRocket';
    }
  });

  restoreActiveCryptoInvoice();
  restoreActiveTrxInvoice();
  // Pre-fetch topup settings in background for instant modal responsiveness
  loadTopupInfo().catch(() => {});
}

window.renderWalletTransactions = renderWalletTransactions;
window.openTopupModal = openTopupModal;
window.setupWalletListeners = setupWalletListeners;
