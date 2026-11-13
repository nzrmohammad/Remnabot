/**
 * RemnaStore Pro - Wallet & Topup Logic
 */

function formatCardNumberDisplay(num) {
  if (!num) return '---- ---- ---- ----';
  const clean = String(num).replace(/\D/g, '');
  if (!clean || clean.length < 4) return String(num);
  return clean.replace(/(\d{4})(?=\d)/g, '$1 ');
}

function renderBluCardNumber(el, num) {
  if (!el) return;
  const clean = String(num || '').replace(/\D/g, '');
  const isGraphic = el.id === 'graphicCardNumberDisplay' || Boolean(el.closest && el.closest('.blu-card-perspective-box'));
  if (clean.length === 16) {
    if (isGraphic) {
      el.innerHTML = `<span class="tracking-wide font-black text-white" style="color: #ffffff;">${clean.slice(0, 4)}</span>&nbsp;<span class="tracking-wide font-black text-white" style="color: #ffffff;">${clean.slice(4, 8)}</span>&nbsp;<span class="tracking-wide font-black text-white" style="color: #ffffff;">${clean.slice(8, 12)}</span>&nbsp;<span class="tracking-wide font-black text-white" style="color: #ffffff;">${clean.slice(12, 16)}</span>`;
    } else {
      el.innerHTML = `<span class="tracking-wide font-black">${clean.slice(0, 4)}</span>&nbsp;<span class="tracking-wide font-black">${clean.slice(4, 8)}</span>&nbsp;<span class="tracking-wide font-black">${clean.slice(8, 12)}</span>&nbsp;<span class="tracking-wide font-black">${clean.slice(12, 16)}</span>`;
    }
  } else {
    el.innerText = formatCardNumberDisplay(num);
  }
}

window.flipBluCard = function(el) {
  if (!el) return;
  const flipper = el.classList.contains('blu-card-flipper') ? el : (el.querySelector('.blu-card-flipper') || el);
  flipper.classList.toggle('is-flipped');
  if (window.hapticFeedback) window.hapticFeedback('impact');
};

const BLUBANK_PALETTES = {
  red: {
    grad: 'linear-gradient(135deg, #991b1b 0%, #b91c1c 50%, #dc2626 100%)',
    text: '#ffffff',
    accent: '#fecaca',
  },
  blue: {
    grad: 'linear-gradient(135deg, #0d47a1 0%, #1976d2 50%, #0288d1 100%)',
    text: '#ffffff',
    accent: '#bfdbfe',
  },
  green: {
    grad: 'linear-gradient(135deg, #004d40 0%, #00796b 50%, #00bfa5 100%)',
    text: '#ffffff',
    accent: '#a7f3d0',
  },
  rose: {
    grad: 'linear-gradient(135deg, #880e4f 0%, #c2185b 50%, #e91e63 100%)',
    text: '#ffffff',
    accent: '#fbcfe8',
  },
  magenta: {
    grad: 'linear-gradient(135deg, #831843 0%, #be185d 45%, #db2777 80%, #9d174d 100%)',
    text: '#ffffff',
    accent: '#fbcfe8',
  },
  yellow: {
    grad: 'linear-gradient(135deg, #e65100 0%, #f57f17 50%, #fbc02d 100%)',
    text: '#ffffff',
    accent: '#fef08a',
  },
  black: {
    grad: 'linear-gradient(135deg, #18181b 0%, #27272a 50%, #09090b 100%)',
    text: '#ffffff',
    accent: '#cbd5e1',
  },
  purple: {
    grad: 'linear-gradient(135deg, #4a148c 0%, #7b1fa2 50%, #ab47bc 100%)',
    text: '#ffffff',
    accent: '#e9d5ff',
  },
};

function applyBluBankCardTheme(color, bankTmpl) {
  const selectedKey = String(color || 'rose').toLowerCase();
  const palette = BLUBANK_PALETTES[selectedKey] || BLUBANK_PALETTES.rose;
  const grad = palette.grad;

  document.querySelectorAll('.blu-card-face').forEach(face => {
    face.style.background = grad;
    face.style.color = palette.text;
  });

  const isMinimal = String(bankTmpl || '').toLowerCase() === 'minimal';

  const isGraphic = !['none', 'classic'].includes(String(bankTmpl || '').toLowerCase());
  const manualGraphicBox = document.getElementById('manualCardGraphicBox');
  if (manualGraphicBox) {
    manualGraphicBox.classList.toggle('hidden', !isGraphic);
  }

  document.querySelectorAll('#graphicBankTitle, .graphicBankTitle').forEach(titleEl => {
    titleEl.innerText = isMinimal ? '' : 'SamanBank';
    titleEl.style.display = isMinimal ? 'none' : '';
    titleEl.style.color = palette.text;
  });

  document.querySelectorAll('#graphicBankIcon, .graphicBankIcon').forEach(iconEl => {
    iconEl.style.display = isMinimal ? 'none' : '';
    iconEl.style.color = palette.text;
    iconEl.style.borderColor = palette.accent;
  });

  document.querySelectorAll('#graphicCardHolderDisplay, .graphicCardHolderDisplay').forEach(holderEl => {
    holderEl.style.color = palette.text;
  });

  document.querySelectorAll('#graphicCardNumberDisplay, .graphicCardNumberDisplay').forEach(numberEl => {
    numberEl.style.color = palette.text;
    numberEl.querySelectorAll('span').forEach(s => { s.style.color = palette.text; });
  });

  document.querySelectorAll('#graphicCardBackText, .graphicCardBackText').forEach(backTextEl => {
    backTextEl.innerText = isMinimal ? '' : 'Blu, But Lovely';
    backTextEl.style.display = isMinimal ? 'none' : '';
    backTextEl.style.color = palette.text;
  });
}

let currentTopupInvoice = null;
let allWalletTransactions = [];
let currentWalletPage = 1;
function getTxPerPage() {
  return Number(window.storeSettings?.history_page_size) || 15;
}

function getTxPurchaseInfo(tx) {
  if (!tx) return { typeRowText: 'خرید بسته', planHtml: '' };
  const rawPlan = (tx.service_name || tx.title?.replace(/^خرید\s+/, '') || '').trim();
  const isCustom = Boolean(tx.is_custom || tx.badge === 'custom' || rawPlan.includes('دلخواه') || tx.title?.includes('دلخواه'));

  let typeRowText = 'خرید بسته';
  let planHtml = '';

  if (isCustom) {
    typeRowText = 'خرید بسته دلخواه';
    const traf = Number(tx.traffic_gb || 0);
    const days = Number(tx.duration_days || 0);
    const trafStr = traf > 0 ? (typeof fmtTraffic === 'function' ? fmtTraffic(traf, { html: false }) : `${traf} گیگابایت`) : '';
    const specsStr = (traf > 0 && days > 0) ? `${trafStr} - ${days} روز` : (traf > 0 ? trafStr : (days > 0 ? `${days} روز` : 'بسته اختصاصی'));
    planHtml = `<bdi class="font-bold select-all font-sans">${escapeHtml(specsStr)}</bdi>`;
  } else {
    const traf = Number(tx.traffic_gb || 0);
    const days = Number(tx.duration_days || 0);
    if (traf > 0 && days > 0) {
      typeRowText = 'خرید بسته کامل';
    } else if (traf > 0 && days === 0) {
      typeRowText = 'خرید بسته حجم';
    } else if (traf === 0 && days > 0) {
      typeRowText = 'خرید بسته زمان';
    } else {
      if (rawPlan.includes('حجم')) typeRowText = 'خرید بسته حجم';
      else if (rawPlan.includes('زمان') || rawPlan.includes('روز')) typeRowText = 'خرید بسته زمان';
      else typeRowText = 'خرید بسته کامل';
    }

    const emojiRegex = /[\p{Extended_Pictographic}\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu;
    const emojis = rawPlan.match(emojiRegex);
    let cleanOnly = rawPlan.replace(emojiRegex, '').trim();

    // Strip duplicate 'بسته' prefix since row 1 already shows 'خرید بسته ...'
    cleanOnly = cleanOnly.replace(/^بسته\s+/, '').trim();
    if (!cleanOnly || cleanOnly === 'بسته') {
      cleanOnly = 'سرویس اشتراکی';
    }

    let emojiStr = (emojis && emojis.length > 0) ? emojis.join('') : '';
    if (!emojiStr) {
      const lowerName = cleanOnly.toLowerCase();
      if (lowerName.includes('طلایی') || lowerName.includes('gold')) emojiStr = '🥇';
      else if (lowerName.includes('نقره') || lowerName.includes('silver')) emojiStr = '🥈';
      else if (lowerName.includes('برنز') || lowerName.includes('bronze')) emojiStr = '🥉';
      else if (lowerName.includes('الماس') || lowerName.includes('diamond')) emojiStr = '💎';
      else if (lowerName.includes('ویژه') || lowerName.includes('vip')) emojiStr = '👑';
      else if (lowerName.includes('گیم') || lowerName.includes('game')) emojiStr = '🎮';
      else if (lowerName.includes('خانواده') || lowerName.includes('family')) emojiStr = '👥';
      else if (typeRowText === 'خرید بسته حجم') emojiStr = '⚡️';
      else if (typeRowText === 'خرید بسته زمان') emojiStr = '⏳';
      else emojiStr = '📦';
    }

    const iconHtml = `<span class="shrink-0 flex items-center justify-center">${uiEmojiIcon(emojiStr || '📦', 'w-4 h-4')}</span>`;
    planHtml = `<span class="inline-flex items-center gap-1.5"><bdi class="font-bold select-all">${escapeHtml(cleanOnly)}</bdi>${iconHtml}</span>`;
  }

  return { typeRowText, planHtml };
}

function formatTxPlan(tx) {
  return getTxPurchaseInfo(tx).planHtml;
}

function formatTxTitle(tx) {
  if (!tx) return 'تراکنش';
  if (tx.type === 'order' || (tx.title && tx.title.startsWith('خرید '))) {
    const { typeRowText } = getTxPurchaseInfo(tx);
    return typeRowText;
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
        <span>${uiIcon('receipt', 'w-4 h-4 inline-block ml-1')} هنوز تراکنش یا سفارشی برای این حساب ثبت نشده است.</span>
      </div>
    `;
    const oldPag = document.getElementById('walletTxPagination');
    if (oldPag) oldPag.classList.add('hidden');
    return;
  }

  const pageSize = getTxPerPage();
  const totalPages = Math.ceil(txList.length / pageSize);
  if (currentWalletPage > totalPages) currentWalletPage = totalPages;
  if (currentWalletPage < 1) currentWalletPage = 1;

  const startIdx = (currentWalletPage - 1) * pageSize;
  const pageItems = txList.slice(startIdx, startIdx + pageSize);

  txContainer.innerHTML = pageItems.map(tx => {
    const statusColor = (tx.status_color === 'amber' || tx.status_color === 'yellow')
      ? 't-warn'
      : ((tx.status_color === 'rose' || tx.status_color === 'red')
        ? 't-danger'
        : (tx.status_color === 'purple'
          ? 'text-purple-400'
          : (tx.status_color === 'slate' ? 't-muted' : 't-success')));

    const isOrder = tx.type === 'order' && tx.id;
    const isPurchase = tx.type === 'order' || (tx.title && tx.title.startsWith('خرید '));

    let titleBlock = '';
    if (isPurchase) {
      const { typeRowText, planHtml } = getTxPurchaseInfo(tx);
      titleBlock = `
        <span class="text-[11px] t-muted font-medium block leading-tight">${typeRowText}</span>
        <div class="font-bold t-main text-xs sm:text-sm leading-snug break-words">${planHtml}</div>
      `;
    } else {
      titleBlock = `<div class="font-bold t-main text-xs sm:text-sm leading-snug break-words">${escapeHtml(tx.title || 'تراکنش')}</div>`;
    }

    const invoiceBtn = isOrder ? `
      <button type="button" onclick="event.stopPropagation(); window.openInvoiceModal && window.openInvoiceModal(${tx.id});" class="text-[10px] text-cyan-600 dark:text-cyan-400 hover:underline flex items-center gap-1 font-bold" title="مشاهده و دانلود فاکتور رسمی">
        ${uiIcon('receipt', 'w-3.5 h-3.5')} <span>فاکتور</span>
      </button>
    ` : '';

    const txIcon = ({ topup: '💳', card_auto: '💳', crypto: '💎', admin_adjust: '⚡️' })[tx.type] || '🛒';
    return `
    <div class="card-inset rounded-2xl p-4 sm:p-4.5 flex items-center justify-between text-xs sm:text-[13px] gap-3 min-h-[72px] ${isOrder ? 'cursor-pointer hover:border-cyan-500/40 transition active:scale-[0.99]' : ''}" ${isOrder ? `onclick="window.openInvoiceModal && window.openInvoiceModal(${tx.id});"` : ''}>
      <div class="flex items-center gap-2.5 min-w-0 flex-1">
        <span class="shrink-0 flex items-center justify-center">${uiEmojiIcon(txIcon, 'w-5 h-5')}</span>
        <div class="min-w-0 flex-1 space-y-1">
          ${titleBlock}
          <span class="text-[10px] t-muted font-sans num-bidi block" dir="ltr">${toEnglishDigits(tx.date_jalali || '')}</span>
        </div>
      </div>
      <div class="text-left shrink-0 space-y-0.5">
        <div class="inline-flex items-center gap-1 font-bold ${tx.is_positive ? 't-success' : 't-main'}" dir="rtl">
          <span class="font-sans num-bidi text-xs sm:text-sm" dir="ltr">${tx.is_positive ? "+" : "-"}${Number(tx.amount != null ? tx.amount : 0).toLocaleString("en-US")}</span>
          <span class="font-sans text-[10px] t-muted font-normal">تومان</span>
        </div>
        <div class="flex items-center justify-end gap-1.5">
          <span class="text-[10px] ${statusColor} font-sans block">
            ${escapeHtml(tx.status || 'موفق')}
          </span>
          ${invoiceBtn}
        </div>
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
      <span class="text-[11px] text-slate-400 font-sans num-bidi">
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

function getTopupLimits() {
  const minAmt = Number(window.storeSettings?.topup_min_amount || window.storeSettings?.min_amount || 10000);
  const maxAmt = Number(window.storeSettings?.topup_max_amount || window.storeSettings?.max_amount || 50000000);
  return { minAmt, maxAmt };
}
window.getTopupLimits = getTopupLimits;

function validateTopupAmount(amt) {
  const { minAmt, maxAmt } = getTopupLimits();
  if (!amt || isNaN(amt) || amt <= 0) {
    if (window.showToast) {
      window.showToast('لطفاً ابتدا مبلغ شارژ مورد نظر خود را وارد یا انتخاب نمایید.', 'warning');
    }
    return false;
  }
  if (amt < minAmt) {
    if (window.showToast) {
      window.showToast(`حداقل مبلغ شارژ ${minAmt.toLocaleString('en-US')} تومان است.`, 'warning');
    }
    return false;
  }
  if (maxAmt > 0 && amt > maxAmt) {
    if (window.showToast) {
      window.showToast(`حداکثر مبلغ شارژ ${maxAmt.toLocaleString('en-US')} تومان است.`, 'warning');
    }
    return false;
  }
  return true;
}
window.validateTopupAmount = validateTopupAmount;

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
  if (window.storeSettings?.pol_rate_toman && window.storeSettings.pol_rate_toman > 0) {
    const polAmt = ((amt || 0) / window.storeSettings.pol_rate_toman).toFixed(4);
    const polDisplay = document.getElementById('polAmountDisplay');
    if (polDisplay) polDisplay.innerText = `${polAmt} POL`;
  }
  const starsRate = window.storeSettings?.stars_rate_toman || 1500;
  const starsCount = Math.max(1, Math.ceil((amt || 0) / starsRate));
  const starsReqEl = document.getElementById('starsRequiredCount');
  if (starsReqEl) starsReqEl.innerText = `${starsCount} ⭐️`;
  const starsRateEl = document.getElementById('starsRateDisplay');
  if (starsRateEl) starsRateEl.innerText = `${Number(starsRate).toLocaleString('en-US')} تومان`;
  if (typeof window.updateCardTopupSubmitState === 'function') {
    window.updateCardTopupSubmitState();
  }
}

const _cardTopupGuardState = {
  phoneLocked: false,
  manualBlockUntilMs: 0,
  selectedImageBase64: null,
  selectedImageHash: null,
  selectedFileKey: null,
  selectedTextHash: null,
  knownDuplicateHashes: new Set(),
  recentPaidAutoAmounts: new Set(),
  serverRejectedKey: null,
  serverRejectedMsg: '',
};

const MANUAL_CARD_LOCK_HOURS = 1;
const MANUAL_CARD_LOCK_SECONDS = MANUAL_CARD_LOCK_HOURS * 3600;
let _manualCardLockTimerInterval = null;

function formatLockCountdownHHMMSS(totalSeconds) {
  const sec = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function applyManualCardLockState(blockedUntilIso, remainingSeconds = 0) {
  let targetMs = 0;
  if (blockedUntilIso) {
    const parsed = Date.parse(blockedUntilIso);
    if (!Number.isNaN(parsed)) targetMs = parsed;
  }
  if (!targetMs && Number(remainingSeconds) > 0) {
    targetMs = Date.now() + Number(remainingSeconds) * 1000;
  }

  if (_manualCardLockTimerInterval) {
    clearInterval(_manualCardLockTimerInterval);
    _manualCardLockTimerInterval = null;
  }

  const toggleWrap = document.getElementById('manualReceiptToggleWrapper');
  const lockBanner = document.getElementById('manualReceiptLockBanner');
  const countdownEl = document.getElementById('manualReceiptLockCountdown');
  const manualSection = document.getElementById('manualCardTopupSection');

  const now = Date.now();
  if (targetMs > now) {
    _cardTopupGuardState.manualBlockUntilMs = targetMs;
    if (window.storeSettings) {
      window.storeSettings.manual_card_blocked = true;
      window.storeSettings.manual_card_blocked_until = new Date(targetMs).toISOString();
    }
    toggleWrap?.classList.add('hidden');
    manualSection?.classList.add('hidden');
    lockBanner?.classList.remove('hidden');

    const updateTimer = () => {
      const remSecs = Math.max(0, Math.ceil((_cardTopupGuardState.manualBlockUntilMs - Date.now()) / 1000));
      if (countdownEl) countdownEl.innerText = formatLockCountdownHHMMSS(remSecs);
      if (remSecs <= 0) {
        applyManualCardLockState(null, 0);
      }
    };
    updateTimer();
    _manualCardLockTimerInterval = setInterval(updateTimer, 1000);
  } else {
    _cardTopupGuardState.manualBlockUntilMs = 0;
    if (window.storeSettings) {
      window.storeSettings.manual_card_blocked = false;
      window.storeSettings.manual_card_blocked_until = null;
      window.storeSettings.manual_card_block_remaining_seconds = 0;
    }
    if (countdownEl) countdownEl.innerText = formatLockCountdownHHMMSS(MANUAL_CARD_LOCK_SECONDS);
    lockBanner?.classList.add('hidden');
    toggleWrap?.classList.remove('hidden');
    if (window.storeSettings && !window.storeSettings.card_auto_enabled && window.storeSettings.card_enabled) {
      manualSection?.classList.remove('hidden');
    }
  }

  if (typeof window.updateCardTopupSubmitState === 'function') {
    window.updateCardTopupSubmitState();
  }
}

async function _computeSha256Hex(bytes) {
  try {
    if (window.crypto?.subtle && bytes) {
      const digest = await window.crypto.subtle.digest('SHA-256', bytes);
      return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
    }
  } catch (e) {}
  return '';
}

async function computeReceiptImageFingerprint(dataUrl) {
  if (!dataUrl || typeof dataUrl !== 'string') return '';
  const b64 = dataUrl.includes('base64,') ? dataUrl.split('base64,')[1] : dataUrl;
  if (!b64 || b64.length < 32) return '';
  try {
    const raw = atob(b64);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    const hex = await _computeSha256Hex(bytes);
    if (hex) return `img:${hex.slice(0, 48)}`;
  } catch (e) {}
  return `img_raw:${b64.length}:${b64.slice(0, 32)}`;
}

async function computeReceiptTextFingerprint(rawText) {
  const normalized = String(rawText || '').trim().replace(/\s+/g, ' ');
  if (!normalized) return '';
  try {
    if (typeof TextEncoder !== 'undefined') {
      const bytes = new TextEncoder().encode(normalized);
      const hex = await _computeSha256Hex(bytes);
      if (hex) return `text:${hex.slice(0, 48)}`;
    }
  } catch (e) {}
  return `text_raw:${normalized}`;
}

window.updateCardTopupSubmitState = function () {
  const submitCardBtn = document.getElementById('submitCardTopupBtn');
  const warningEl = document.getElementById('cardReceiptWarningBanner');
  if (!submitCardBtn) return;

  const setDisabled = (disabled, warnMsg = '') => {
    submitCardBtn.disabled = Boolean(disabled);
    submitCardBtn.classList.toggle('opacity-40', Boolean(disabled));
    submitCardBtn.classList.toggle('cursor-not-allowed', Boolean(disabled));
    if (warningEl) {
      if (warnMsg) {
        warningEl.textContent = warnMsg;
        warningEl.classList.remove('hidden');
      } else {
        warningEl.textContent = '';
        warningEl.classList.add('hidden');
      }
    }
  };

  if (_cardTopupGuardState.phoneLocked) {
    submitCardBtn.innerText = '🔒 نیاز به تأیید شماره تماس';
    setDisabled(true, '');
    return;
  }

  if (_cardTopupGuardState.manualBlockUntilMs > Date.now()) {
    submitCardBtn.innerText = `🔒 ارسال دستی تا ${MANUAL_CARD_LOCK_HOURS} ساعت مسدود است`;
    setDisabled(true, `🔒 به دلیل وجود فاکتور کارت‌به‌کارت خودکار، تا ${MANUAL_CARD_LOCK_HOURS} ساعت امکان ثبت دستی فیش وجود ندارد.`);
    return;
  }

  submitCardBtn.innerText = '📤 ثبت و ارسال رسید پرداخت';

  const amt = parseInt(document.getElementById('topupAmountInput')?.value || '0', 10) || 0;
  const minAmt = window.storeSettings?.topup_min_amount || 10000;
  const maxAmt = window.storeSettings?.topup_max_amount || 50000000;

  if (amt > 0 && _cardTopupGuardState.recentPaidAutoAmounts.has(amt)) {
    setDisabled(true, '⚠️ این مبلغ پیش‌تر به‌صورت خودکار تأیید و شارژ شده است؛ نیازی به ارسال فیش نیست.');
    return;
  }

  const dupImg = (
    (_cardTopupGuardState.selectedImageHash && _cardTopupGuardState.knownDuplicateHashes.has(_cardTopupGuardState.selectedImageHash))
    || (_cardTopupGuardState.selectedFileKey && _cardTopupGuardState.knownDuplicateHashes.has(_cardTopupGuardState.selectedFileKey))
  );
  if (dupImg) {
    setDisabled(true, '⚠️ این تصویر فیش قبلاً ثبت شده و تکراری است؛ لطفاً تصویر فیش جدید بارگذاری کنید.');
    return;
  }

  if (_cardTopupGuardState.selectedTextHash && _cardTopupGuardState.knownDuplicateHashes.has(_cardTopupGuardState.selectedTextHash)) {
    setDisabled(true, '⚠️ این کد پیگیری قبلاً ثبت شده و تکراری است؛ لطفاً کد جدید یا متن متفاوتی وارد کنید.');
    return;
  }

  const currentKey = `${amt}|${_cardTopupGuardState.selectedImageHash || ''}|${_cardTopupGuardState.selectedTextHash || ''}`;
  if (_cardTopupGuardState.serverRejectedKey && _cardTopupGuardState.serverRejectedKey === currentKey) {
    setDisabled(true, _cardTopupGuardState.serverRejectedMsg || '⚠️ این درخواست قبلاً ثبت شده است.');
    return;
  }

  const hasValidAmount = amt >= minAmt && amt <= maxAmt;
  const hasImage = Boolean(_cardTopupGuardState.selectedImageBase64);
  setDisabled(!(hasImage && hasValidAmount), '');
};

async function loadTopupInfo() {
  try {
    const res = await window.api.getTopupInfo();
    if (res.ok) {
      window.storeSettings = res;
      if (Array.isArray(res.recent_paid_auto_amounts)) {
        _cardTopupGuardState.recentPaidAutoAmounts = new Set(res.recent_paid_auto_amounts.map(Number));
      }
      if (Array.isArray(res.recent_receipt_hashes)) {
        _cardTopupGuardState.knownDuplicateHashes = new Set(res.recent_receipt_hashes.filter(Boolean));
      }
      const isGraphic = res.card_graphical_view_enabled !== false;
      const graphicBox = document.getElementById('cardAutoGraphicBox');
      if (graphicBox) graphicBox.classList.toggle('hidden', !isGraphic);
      document.querySelectorAll('.card-graphic-box').forEach(el => el.classList.toggle('hidden', !isGraphic));
      document.querySelectorAll('.card-classic-box').forEach(el => el.classList.toggle('hidden', isGraphic));

      const cardNumEl = document.getElementById('topupCardNumber');
      const cardHolderEl = document.getElementById('topupCardHolder');
      const manualClassicNum = document.getElementById('manualClassicNumber');
      const manualClassicHolder = document.getElementById('manualClassicHolder');
      const graphicNum = document.getElementById('graphicCardNumberDisplay');
      const graphicHolder = document.getElementById('graphicCardHolderDisplay');
      const rawNum = res.card_number || '----';
      const rawHolder = res.card_holder || 'مدیریت سرور';

      if (cardNumEl) renderBluCardNumber(cardNumEl, rawNum);
      if (cardHolderEl) cardHolderEl.innerText = rawHolder;
      if (graphicNum) renderBluCardNumber(graphicNum, rawNum);
      if (graphicHolder) graphicHolder.innerText = rawHolder;
      const manualGraphicNum = document.getElementById('manualGraphicCardNumberDisplay');
      const manualGraphicHolder = document.getElementById('manualGraphicCardHolderDisplay');
      if (manualGraphicNum) renderBluCardNumber(manualGraphicNum, rawNum);
      if (manualGraphicHolder) manualGraphicHolder.innerText = rawHolder;
      if (manualClassicNum) manualClassicNum.innerText = formatCardNumberDisplay(rawNum);
      if (manualClassicHolder) manualClassicHolder.innerText = rawHolder;
      applyBluBankCardTheme(res.card_blubank_color || 'rose', res.card_template || 'blubank');

      const hasCard = res.card_enabled === true;
      const hasStars = res.stars_enabled === true;
      const hasCrypto = res.crypto_enabled === true;
      const hasTrx = res.trx_enabled === true;
      const hasPol = res.pol_enabled === true;
      const anyMethodEnabled = hasCard || hasStars || hasCrypto || hasTrx || hasPol;

      const tabsContainer = document.getElementById('topupMethodTabs');
      const amountSection = document.getElementById('topupAmountSection');
      const disabledState = document.getElementById('topupAllDisabledState');
      const viewCard = document.getElementById('topupCardView');
      const viewStars = document.getElementById('topupStarsView');
      const viewCrypto = document.getElementById('topupCryptoView');
      const viewTrx = document.getElementById('topupTrxView');
      const viewPol = document.getElementById('topupPolView');

      if (!anyMethodEnabled) {
        tabsContainer?.classList.add('hidden');
        amountSection?.classList.add('hidden');
        viewCard?.classList.add('hidden');
        viewStars?.classList.add('hidden');
        viewCrypto?.classList.add('hidden');
        viewTrx?.classList.add('hidden');
        viewPol?.classList.add('hidden');
        disabledState?.classList.remove('hidden');
      } else {
        disabledState?.classList.add('hidden');
        tabsContainer?.classList.remove('hidden');
        amountSection?.classList.remove('hidden');

        document.getElementById('topupMethodCardBtn')?.classList.toggle('hidden', !hasCard);
        document.getElementById('topupMethodCryptoBtn')?.classList.toggle('hidden', !hasCrypto);
        document.getElementById('topupMethodTrxBtn')?.classList.toggle('hidden', !hasTrx);
        document.getElementById('topupMethodPolBtn')?.classList.toggle('hidden', !hasPol);
        document.getElementById('topupMethodStarsBtn')?.classList.toggle('hidden', !hasStars);

        const activeMethod = window.currentTopupTab || 'card';
        const methodEnabledMap = {
          card: hasCard,
          crypto: hasCrypto,
          trx: hasTrx,
          pol: hasPol,
          stars: hasStars,
        };
        if (!methodEnabledMap[activeMethod]) {
          const fallback = ['card', 'crypto', 'trx', 'pol', 'stars'].find(k => methodEnabledMap[k]);
          if (fallback) switchTopupTab(fallback);
        }
      }

      const cardPhoneWarning = document.getElementById('cardPhoneVerificationWarning');
      const cardDetailsBox = document.getElementById('topupCardDetailsBox');
      const cardUploadBtn = document.getElementById('uploadCardReceiptImageBtn');
      if (res.card_require_phone_verification && !res.is_phone_verified) {
        _cardTopupGuardState.phoneLocked = true;
        if (cardPhoneWarning) cardPhoneWarning.classList.remove('hidden');
        if (cardDetailsBox) cardDetailsBox.classList.add('hidden');
        if (cardUploadBtn) {
          cardUploadBtn.disabled = true;
          cardUploadBtn.classList.add('opacity-40', 'cursor-not-allowed');
        }
      } else {
        _cardTopupGuardState.phoneLocked = false;
        if (cardPhoneWarning) cardPhoneWarning.classList.add('hidden');
        if (cardDetailsBox) cardDetailsBox.classList.remove('hidden');
        if (cardUploadBtn) {
          cardUploadBtn.disabled = false;
          cardUploadBtn.classList.remove('opacity-40', 'cursor-not-allowed');
        }
      }
      window.updateCardTopupSubmitState();

      const cardAutoContainer = document.getElementById('cardAutoTopupContainer');
      const manualCardSection = document.getElementById('manualCardTopupSection');
      if (res.card_auto_enabled) {
        if (cardAutoContainer) cardAutoContainer.classList.remove('hidden');
        if (manualCardSection) manualCardSection.classList.add('hidden');
        checkActiveCardAutoInvoice();
      } else {
        if (cardAutoContainer) cardAutoContainer.classList.add('hidden');
        if (manualCardSection) manualCardSection.classList.remove('hidden');
      }
      applyManualCardLockState(
        res.manual_card_blocked ? res.manual_card_blocked_until : null,
        res.manual_card_block_remaining_seconds || 0
      );
      syncActiveInvoicesWithServer();

      const inputEl = document.getElementById('topupAmountInput');
      updateTopupDisplays(parseInt(inputEl?.value || '50000'));
    }
  } catch (err) {}
}

let cryptoCountdownTimerInterval = null;

function getActiveInvoiceType() {
  if (activeCardAutoUuid) return 'CARD';
  if (currentTopupInvoice && currentTopupInvoice.id) return 'TON';
  if (currentTrxInvoice && currentTrxInvoice.id) return 'TRX';
  if (currentPolInvoice && currentPolInvoice.id) return 'POL';
  return null;
}

function updateTopupMutexUI() {
  const activeType = getActiveInvoiceType();
  const amountSection = document.getElementById('topupAmountSection');
  const btnCard = document.getElementById('topupMethodCardBtn');
  const btnStars = document.getElementById('topupMethodStarsBtn');
  const btnCrypto = document.getElementById('topupMethodCryptoBtn');
  const btnTrx = document.getElementById('topupMethodTrxBtn');
  const btnPol = document.getElementById('topupMethodPolBtn');
  const tabs = [
    { el: btnCard, type: 'CARD' },
    { el: btnCrypto, type: 'TON' },
    { el: btnTrx, type: 'TRX' },
    { el: btnPol, type: 'POL' },
    { el: btnStars, type: null }
  ];

  if (activeType) {
    if (amountSection) amountSection.classList.add('hidden');
    tabs.forEach(({ el, type }) => {
      if (!el) return;
      if (type === activeType) {
        el.classList.remove('opacity-40');
      } else {
        el.classList.add('opacity-40');
      }
    });
  } else {
    if (amountSection) amountSection.classList.remove('hidden');
    tabs.forEach(({ el }) => {
      if (el) el.classList.remove('opacity-40');
    });
  }
}

function switchTopupTab(tab) {
  const activeType = getActiveInvoiceType();
  if (activeType) {
    const requiredTab = activeType === 'CARD' ? 'card' : (activeType === 'TRX' ? 'trx' : (activeType === 'POL' ? 'pol' : 'crypto'));
    if (tab !== requiredTab) {
      if (window.showToast) {
        const typeName = activeType === 'CARD' ? 'کارت‌به‌کارت' : (activeType === 'TRX' ? 'ترون (TRX)' : (activeType === 'POL' ? 'پلیگان (POL)' : 'تون (TON)'));
        window.showToast(`شما یک فاکتور فعال در جریان (${typeName}) دارید. لطفاً ابتدا آن را پرداخت یا لغو نمایید.`, 'warning');
      }
      return;
    }
  }
  window.currentTopupTab = tab;
  const btnCard = document.getElementById('topupMethodCardBtn');
  const btnStars = document.getElementById('topupMethodStarsBtn');
  const btnCrypto = document.getElementById('topupMethodCryptoBtn');
  const btnTrx = document.getElementById('topupMethodTrxBtn');
  const btnPol = document.getElementById('topupMethodPolBtn');

  const viewCard = document.getElementById('topupCardView');
  const viewStars = document.getElementById('topupStarsView');
  const viewCrypto = document.getElementById('topupCryptoView');
  const viewTrx = document.getElementById('topupTrxView');
  const viewPol = document.getElementById('topupPolView');

  [btnCard, btnStars, btnCrypto, btnTrx, btnPol].forEach(b => {
    if (b) {
      b.classList.remove('bg-blue-600', 'text-white');
      b.classList.add('text-slate-400');
    }
  });
  [viewCard, viewStars, viewCrypto, viewTrx, viewPol].forEach(v => {
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
  } else if (tab === 'pol') {
    btnPol?.classList.add('bg-blue-600', 'text-white');
    btnPol?.classList.remove('text-slate-400');
    viewPol?.classList.remove('hidden');
  }
}

function switchToCryptoTab() { switchTopupTab('crypto'); }
function switchToCardTab() { switchTopupTab('card'); }

let cardAutoTimerInterval = null;
let cardAutoPollingInterval = null;
let activeCardAutoUuid = null;

async function checkActiveCardAutoInvoice() {
  try {
    const res = await window.api.getCardAutoStatus();
    if (res && res.ok) {
      if (res.manual_card_blocked) {
        applyManualCardLockState(res.manual_card_blocked_until, res.manual_card_block_remaining_seconds || 0);
      } else if (typeof res.manual_card_blocked === 'boolean') {
        applyManualCardLockState(null, 0);
      }
      if (res.status === 'pending' && res.invoice_uuid) {
        renderCardAutoInvoice(res);
      }
    }
  } catch (e) {}
}

function renderCardAutoInvoice(inv) {
  activeCardAutoUuid = inv.invoice_uuid;
  const initialBox = document.getElementById('cardAutoInitialBox');
  const detailsBox = document.getElementById('cardAutoInvoiceDetails');
  if (initialBox) initialBox.classList.add('hidden');
  if (detailsBox) detailsBox.classList.remove('hidden');

  const isGraphic = (inv.card_graphical_view_enabled ?? window.storeSettings?.card_graphical_view_enabled) !== false;
  const graphicBox = document.getElementById('cardAutoGraphicBox');
  if (graphicBox) graphicBox.classList.toggle('hidden', !isGraphic);
  document.querySelectorAll('.card-graphic-box').forEach(el => el.classList.toggle('hidden', !isGraphic));
  document.querySelectorAll('.card-classic-box').forEach(el => el.classList.toggle('hidden', isGraphic));

  const exactTomanEl = document.getElementById('cardAutoExactToman');
  const exactRialEl = document.getElementById('cardAutoExactRial');
  const cardNumEl = document.getElementById('cardAutoCardNumber');
  const cardHolderEl = document.getElementById('cardAutoCardHolder');
  const autoClassicNum = document.getElementById('cardAutoClassicNumber');
  const autoClassicHolder = document.getElementById('cardAutoClassicHolder');
  const graphicNum = document.getElementById('graphicCardNumberDisplay');
  const graphicHolder = document.getElementById('graphicCardHolderDisplay');
  const numToDisplay = inv.card_number || window.storeSettings?.card_number || '----';
  const holderToDisplay = inv.card_holder || window.storeSettings?.card_holder || 'مدیریت سرور';

  if (exactTomanEl) exactTomanEl.innerText = `${Number(inv.exact_amount || 0).toLocaleString('en-US')} تومان`;
  if (exactRialEl) exactRialEl.innerText = `${Number(inv.exact_rial || (inv.exact_amount * 10) || 0).toLocaleString('en-US')} ریال`;
  if (cardNumEl) renderBluCardNumber(cardNumEl, numToDisplay);
  if (cardHolderEl) cardHolderEl.innerText = holderToDisplay;
  if (graphicNum) renderBluCardNumber(graphicNum, numToDisplay);
  if (graphicHolder) graphicHolder.innerText = holderToDisplay;
  if (autoClassicNum) autoClassicNum.innerText = formatCardNumberDisplay(numToDisplay);
  if (autoClassicHolder) autoClassicHolder.innerText = holderToDisplay;
  applyBluBankCardTheme(inv.card_blubank_color || window.storeSettings?.card_blubank_color || 'rose', inv.card_template || window.storeSettings?.card_template || 'blubank');

  startCardAutoCountdownTimer(inv.remaining_seconds || 3600);
  startCardAutoPolling(inv.invoice_uuid);
  updatePendingCardUI(inv, inv.remaining_seconds || 3600, 'CARD');
  const lockUntil = inv.manual_card_blocked_until || window.storeSettings?.manual_card_blocked_until || new Date(Date.now() + MANUAL_CARD_LOCK_SECONDS * 1000).toISOString();
  applyManualCardLockState(lockUntil, inv.manual_card_block_remaining_seconds || MANUAL_CARD_LOCK_SECONDS);
  updateTopupMutexUI();
}

function startCardAutoCountdownTimer(seconds) {
  if (cardAutoTimerInterval) {
    clearInterval(cardAutoTimerInterval);
    cardAutoTimerInterval = null;
  }
  let remaining = seconds || 3600;
  const timerEl = document.getElementById('cardAutoCountdownTimer');

  const updateDisplay = () => {
    if (remaining <= 0) {
      clearInterval(cardAutoTimerInterval);
      cardAutoTimerInterval = null;
      if (timerEl) timerEl.innerText = '00:00 (منقضی شد)';
      if (window.activePendingInvoiceType === 'CARD') {
        const pendingTimer = document.getElementById('activeCryptoPendingTimer');
        if (pendingTimer) pendingTimer.innerText = '00:00 (منقضی شد)';
        updatePendingCardUI(null);
      }
      stopCardAutoPolling();
      return;
    }
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    const timeStr = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    if (timerEl) {
      timerEl.innerText = timeStr;
    }
    if (window.activePendingInvoiceType === 'CARD') {
      const pendingTimer = document.getElementById('activeCryptoPendingTimer');
      if (pendingTimer) pendingTimer.innerText = timeStr;
    }
    remaining--;
  };
  updateDisplay();
  cardAutoTimerInterval = setInterval(updateDisplay, 1000);
}

function startCardAutoPolling(uuid) {
  stopCardAutoPolling();
  cardAutoPollingInterval = setInterval(async () => {
    try {
      const res = await window.api.getCardAutoStatus(uuid);
      if (res && res.ok) {
        if (res.status === 'paid') {
          stopCardAutoPolling();
          if (cardAutoTimerInterval) {
            clearInterval(cardAutoTimerInterval);
            cardAutoTimerInterval = null;
          }
          if (window.showToast) {
            window.showToast('✅ پرداخت شما با موفقیت تأیید شد و کیف پول شارژ گردید!', 'success');
          }
          if (window.Telegram?.WebApp?.HapticFeedback) {
            window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
          }
          resetCardAutoUI();
          applyManualCardLockState(res.manual_card_blocked ? res.manual_card_blocked_until : null, res.manual_card_block_remaining_seconds || 0);
          if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
          if (typeof closeModal === 'function') closeModal('topupModal');
        } else if (res.status === 'expired' || res.status === 'cancelled') {
          stopCardAutoPolling();
          resetCardAutoUI();
          applyManualCardLockState(res.manual_card_blocked ? res.manual_card_blocked_until : null, res.manual_card_block_remaining_seconds || 0);
        }
      }
    } catch (e) {}
  }, 4000);
}

function stopCardAutoPolling() {
  if (cardAutoPollingInterval) {
    clearInterval(cardAutoPollingInterval);
    cardAutoPollingInterval = null;
  }
}

function resetCardAutoUI() {
  activeCardAutoUuid = null;
  const initialBox = document.getElementById('cardAutoInitialBox');
  const detailsBox = document.getElementById('cardAutoInvoiceDetails');
  if (initialBox) initialBox.classList.remove('hidden');
  if (detailsBox) detailsBox.classList.add('hidden');
  if (window.activePendingInvoiceType === 'CARD') {
    updatePendingCardUI(null);
  }
  updateTopupMutexUI();
}

window.createCardAutoInvoice = async function () {
  const inputEl = document.getElementById('topupAmountInput');
  const amount = parseInt(inputEl?.value || '0', 10);
  if (!validateTopupAmount(amount)) return;
  const btn = document.getElementById('createCardAutoInvoiceBtn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="inline-block animate-spin mr-1">⌛</span> در حال ایجاد فاکتور...';
  }
  try {
    const res = await window.api.createCardAutoInvoice(amount);
    if (res && res.ok) {
      if (window.storeSettings) {
        window.storeSettings.manual_card_blocked = true;
        window.storeSettings.manual_card_blocked_until = res.manual_card_blocked_until || new Date(Date.now() + MANUAL_CARD_LOCK_SECONDS * 1000).toISOString();
        window.storeSettings.manual_card_block_remaining_seconds = res.manual_card_block_remaining_seconds || MANUAL_CARD_LOCK_SECONDS;
      }
      renderCardAutoInvoice(res);
      if (window.showToast) window.showToast('فاکتور پرداخت هوشمند با موفقیت ایجاد شد.', 'success');
    } else {
      if (window.showToast) window.showToast(res?.message || 'خطا در ایجاد فاکتور', 'error');
    }
  } catch (err) {
    if (window.showToast) window.showToast('خطا در برقراری ارتباط با سرور', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<span>⚡️</span> ایجاد فاکتور پرداخت آنی کارت‌به‌کارت';
    }
  }
};

window.checkCardAutoStatus = async function (isManual = false) {
  if (!activeCardAutoUuid) return;
  try {
    const res = await window.api.getCardAutoStatus(activeCardAutoUuid);
    if (res && res.ok) {
      if (res.status === 'paid') {
        stopCardAutoPolling();
        if (window.showToast) window.showToast('✅ پرداخت تایید شد و حساب شما شارژ گردید!', 'success');
        resetCardAutoUI();
        applyManualCardLockState(res.manual_card_blocked ? res.manual_card_blocked_until : null, res.manual_card_block_remaining_seconds || 0);
        if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
        if (typeof closeModal === 'function') closeModal('topupModal');
      } else if (res.status === 'expired') {
        if (window.showToast) window.showToast('مهلت پرداخت این فاکتور به پایان رسیده است.', 'warning');
        resetCardAutoUI();
        applyManualCardLockState(res.manual_card_blocked ? res.manual_card_blocked_until : null, res.manual_card_block_remaining_seconds || 0);
      } else if (isManual) {
        if (window.showToast) window.showToast('هنوز پیامی مبنی بر واریز دریافت نشده است؛ لطفاً پس از واریز صبور باشید.', 'info');
      }
    }
  } catch (e) {}
};

window.cancelCardAutoInvoice = async function () {
  if (!activeCardAutoUuid) {
    resetCardAutoUI();
    applyManualCardLockState(null, 0);
    return;
  }
  try {
    const cancelRes = await window.api.cancelCardAutoInvoice(activeCardAutoUuid);
    if (cancelRes && cancelRes.ok === false) {
      if (window.showToast) window.showToast(cancelRes.message || 'امکان لغو این فاکتور وجود ندارد.', 'warning');
      await loadTopupInfo();
      return;
    }
    stopCardAutoPolling();
    if (cardAutoTimerInterval) {
      clearInterval(cardAutoTimerInterval);
      cardAutoTimerInterval = null;
    }
    resetCardAutoUI();
    applyManualCardLockState(
      cancelRes?.manual_card_blocked ? cancelRes.manual_card_blocked_until : null,
      cancelRes?.manual_card_block_remaining_seconds || 0
    );
    await loadTopupInfo();
    if (window.showToast) window.showToast('فاکتور پرداخت لغو گردید.', 'info');
  } catch (e) {}
};

window.copyCardNumber = function (btnEl) {
  const el = document.getElementById('cardAutoCardNumber') || document.getElementById('topupCardNumber');
  const card = el?.innerText?.trim();
  if (card && !card.includes('----') && !card.includes('ثبت نشده')) {
    const cleanDigits = card.replace(/[^\d]/g, '');
    const copyFn = typeof copyToClipboard === 'function' ? copyToClipboard : window.copyToClipboard;
    if (copyFn) copyFn(cleanDigits || card, '📋 شماره کارت در کلیپ‌بورد کپی شد.');
    if (typeof hapticFeedback === 'function') hapticFeedback('success');
    const targetBtn = btnEl || document.getElementById('copyCardAutoBtn') || document.getElementById('copyTopupCardBtn');
    if (targetBtn && targetBtn.tagName === 'BUTTON') {
      const orig = targetBtn.innerText;
      targetBtn.innerText = '✅';
      setTimeout(() => { targetBtn.innerText = orig; }, 1500);
    }
  } else {
    if (typeof showToast === 'function') showToast('⚠️ شماره کارتی برای کپی کردن یافت نشد.');
  }
};

window.copyCardAutoAmount = function (type) {
  const el = type === 'rial' ? document.getElementById('cardAutoExactRial') : document.getElementById('cardAutoExactToman');
  const text = el?.innerText?.trim() || '';
  const digits = text.replace(/[^\d]/g, '');
  if (digits) {
    copyToClipboard(digits, `📋 مبلغ (${type === 'rial' ? 'ریال' : 'تومان'}) در کلیپ‌بورد کپی شد.`);
  }
};

window.toggleManualReceiptUpload = function () {
  const section = document.getElementById('manualCardTopupSection');
  if (_cardTopupGuardState.manualBlockUntilMs > Date.now()) {
    if (section) section.classList.add('hidden');
    if (window.showToast) {
      const rem = formatLockCountdownHHMMSS(Math.ceil((_cardTopupGuardState.manualBlockUntilMs - Date.now()) / 1000));
      window.showToast(`🔒 تا ${MANUAL_CARD_LOCK_HOURS} ساعت پس از ایجاد یا استفاده از فاکتور کارت‌به‌کارت خودکار (${rem})، امکان ارسال دستی فیش وجود ندارد.`, 'warning');
    }
    return;
  }
  if (section) {
    section.classList.toggle('hidden');
    if (typeof window.updateCardTopupSubmitState === 'function') {
      window.updateCardTopupSubmitState();
    }
  }
};

window.activePendingInvoiceType = null;

function updatePendingCardUI(invoice, remainingSec, type = 'TON') {
  const card = document.getElementById('activeCryptoPendingCard');
  if (!card) return;
  if (!invoice) {
    window.activePendingInvoiceType = null;
    card.classList.add('hidden');
    return;
  }
  window.activePendingInvoiceType = type;
  card.classList.remove('hidden');

  const titleEl = document.getElementById('activePendingCardTitle');
  if (titleEl) {
    if (type === 'TRX') {
      titleEl.innerText = 'فاکتور ترون (TRX) در جریان';
    } else if (type === 'POL') {
      titleEl.innerText = 'فاکتور پلیگان (POL) در جریان';
    } else if (type === 'CARD') {
      titleEl.innerText = 'فاکتور کارت‌به‌کارت در جریان';
    } else {
      titleEl.innerText = 'فاکتور تون (TON) در جریان';
    }
  }

  const amtEl = document.getElementById('activeCryptoPendingAmount');
  if (amtEl) {
    if (type === 'TRX') {
      amtEl.innerText = `${invoice.amount_trx || invoice.amount_ton} TRX`;
    } else if (type === 'POL') {
      amtEl.innerText = `${invoice.amount_pol || invoice.amount_ton} POL`;
    } else if (type === 'CARD') {
      const rial = invoice.exact_rial || (Number(invoice.exact_amount || 0) * 10);
      amtEl.innerText = `${Number(rial).toLocaleString('en-US')} ریال`;
    } else {
      amtEl.innerText = `${invoice.amount_ton} TON`;
    }
  }

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

function startCryptoCountdownTimer(seconds = 3600) {
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
      if (pendingTimer && window.activePendingInvoiceType === 'TON') {
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
      if (window.activePendingInvoiceType === 'TON') {
        updatePendingCardUI(null);
      }
      return;
    }
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    const timeStr = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    if (timer) timer.innerText = timeStr;
    if (pendingTimer && window.activePendingInvoiceType === 'TON') pendingTimer.innerText = timeStr;
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

function saveActiveCryptoInvoice(inv, durationSec = 3600) {
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

  if (window.activePendingInvoiceType === 'TON') {
    updatePendingCardUI(null);
  }

  const genBtn = document.getElementById('generateTonInvoiceBtn');
  if (genBtn) {
    genBtn.disabled = false;
    genBtn.innerText = '💎 ایجاد فاکتور پرداخت TON';
  }

  const timerEl = document.getElementById('cryptoCountdownTimer');
  if (timerEl) {
    timerEl.innerText = '60:00';
    timerEl.classList.remove('t-danger', 'text-rose-400', 'bg-rose-500/10', 'border-rose-500/20', 'bg-amber-500/10', 'border-amber-500/20');
    timerEl.classList.add('t-warn');
  }

  const amtEl = document.getElementById('cryptoAmountTon');
  if (amtEl) amtEl.innerText = '-- TON';
  const addrEl = document.getElementById('cryptoPayAddress');
  if (addrEl) addrEl.innerText = '--';
  const commEl = document.getElementById('cryptoComment');
  if (commEl) commEl.innerText = '--';
  updateTopupMutexUI();
}

window.cancelCryptoInvoice = async function() {
  if (currentTopupInvoice?.id && window.api?.cancelCryptoInvoice) {
    try { await window.api.cancelCryptoInvoice(currentTopupInvoice.id); } catch (e) {}
  }
  clearActiveCryptoInvoice();
  updateTopupMutexUI();
  showToast('✅ فاکتور لغو شد. می‌توانید فاکتور جدید صادر فرمایید.');
};


async function syncActiveInvoicesWithServer() {
  try {
    if (!window.api || !window.api.getActiveCryptoInvoice) return;
    const res = await window.api.getActiveCryptoInvoice();
    if (res && res.ok && res.has_active && res.invoice) {
      const inv = res.invoice;
      const currency = inv.currency || 'TON';
      const remSec = inv.remaining_seconds || 3600;
      if (currency === 'TRX') {
        clearActiveCryptoInvoice();
        clearActivePolInvoice();
        saveActiveTrxInvoice(inv, remSec);
        restoreActiveTrxInvoice();
      } else if (currency === 'POL') {
        clearActiveCryptoInvoice();
        clearActiveTrxInvoice();
        saveActivePolInvoice(inv, remSec);
        restoreActivePolInvoice();
      } else {
        clearActiveTrxInvoice();
        clearActivePolInvoice();
        saveActiveCryptoInvoice(inv, remSec);
        restoreActiveCryptoInvoice();
      }
    } else if (res && res.ok && !res.has_active) {
      if (window.activePendingInvoiceType === 'TON') {
        clearActiveCryptoInvoice();
      } else if (window.activePendingInvoiceType === 'TRX') {
        clearActiveTrxInvoice();
      } else if (window.activePendingInvoiceType === 'POL') {
        clearActivePolInvoice();
      }
    }
  } catch (e) {}
}

function restoreActiveCryptoInvoice() {
  try {
    const raw = localStorage.getItem(getActiveCryptoStorageKey()) || localStorage.getItem('remna_active_crypto_invoice');
    if (!raw) {
      if (window.activePendingInvoiceType === 'TON') updatePendingCardUI(null);
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
    updatePendingCardUI(data.invoice, remainingSec, 'TON');
    updateTopupMutexUI();
    return true;
  } catch (e) {
    return false;
  }
}

let currentTrxInvoice = null;
let trxCountdownTimerInterval = null;

function updateTronLinkButton(inv) {
  const btn = document.getElementById('openTronLinkBtn');
  if (!btn || !inv || !inv.pay_address || !inv.amount_trx) return;
  const trxAmount = Number(inv.amount_trx);
  const tronUri = `tron:${inv.pay_address}?amount=${trxAmount}`;
  const redirectUrl = `${window.location.origin}/api/user/topup/trx/redirect?address=${encodeURIComponent(inv.pay_address)}&amount=${trxAmount}`;

  btn.href = redirectUrl;
  btn.onclick = (e) => {
    e.preventDefault();
    if (typeof copyToClipboard === 'function') {
      copyToClipboard(inv.pay_address, `📋 آدرس ترون کپی شد (${trxAmount} TRX)`);
    }

    if (window.Telegram?.WebApp?.openLink) {
      window.Telegram.WebApp.openLink(redirectUrl);
      return;
    }

    try {
      window.location.href = tronUri;
    } catch (_) {
      window.open(redirectUrl, '_blank');
    }
  };
}

function startTrxCountdownTimer(seconds = 3600) {
  if (trxCountdownTimerInterval) {
    clearInterval(trxCountdownTimerInterval);
    trxCountdownTimerInterval = null;
  }
  let targetEnd = Date.now() + (seconds * 1000);
  try {
    const raw = localStorage.getItem(getActiveTrxStorageKey());
    if (raw) {
      const data = JSON.parse(raw);
      if (data && data.expires_at) targetEnd = data.expires_at;
    }
  } catch (e) {}

  const updateDisplay = () => {
    const now = Date.now();
    const remaining = Math.max(0, Math.floor((targetEnd - now) / 1000));
    const timer = document.getElementById('trxCountdownTimer');
    const pendingTimer = document.getElementById('activeCryptoPendingTimer');

    if (remaining <= 0) {
      if (timer) timer.innerText = '00:00 (منقضی شد)';
      if (pendingTimer && window.activePendingInvoiceType === 'TRX') pendingTimer.innerText = '00:00 (منقضی شد)';
      if (trxCountdownTimerInterval) {
        clearInterval(trxCountdownTimerInterval);
        trxCountdownTimerInterval = null;
      }
      return;
    }
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    const timeStr = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    if (timer) timer.innerText = timeStr;
    if (pendingTimer && window.activePendingInvoiceType === 'TRX') pendingTimer.innerText = timeStr;
  };

  updateDisplay();
  trxCountdownTimerInterval = setInterval(updateDisplay, 1000);
}

function stopTrxCountdownTimer() {
  if (trxCountdownTimerInterval) {
    clearInterval(trxCountdownTimerInterval);
    trxCountdownTimerInterval = null;
  }
}

function getActiveTrxStorageKey() {
  const tgId = window.lastUserData?.user?.telegram_id || window.Telegram?.WebApp?.initDataUnsafe?.user?.id || 'default';
  return `remna_active_trx_invoice_${tgId}`;
}

function saveActiveTrxInvoice(inv, durationSec = 3600) {
  try {
    const expiresAt = Date.now() + (durationSec * 1000);
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
  stopTrxCountdownTimer();
  currentTrxInvoice = null;
  const detailsEl = document.getElementById('trxInvoiceDetails');
  const initialEl = document.getElementById('trxInvoiceInitial');
  if (detailsEl) detailsEl.classList.add('hidden');
  if (initialEl) initialEl.classList.remove('hidden');
  const input = document.getElementById('trxTxIdInput');
  if (input) input.value = '';
  if (window.activePendingInvoiceType === 'TRX') {
    updatePendingCardUI(null);
  }
  updateTopupMutexUI();
}

function restoreActiveTrxInvoice() {
  try {
    const raw = localStorage.getItem(getActiveTrxStorageKey());
    if (!raw) return false;
    const data = JSON.parse(raw);
    const now = Date.now();
    const remainingSec = Math.floor((data.expires_at - now) / 1000);
    if (remainingSec <= 0 || !data.invoice) {
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
    updateTronLinkButton(data.invoice);
    startTrxCountdownTimer(remainingSec);
    updatePendingCardUI(data.invoice, remainingSec, 'TRX');
    updateTopupMutexUI();
    return true;
  } catch (e) {
    return false;
  }
}

let currentPolInvoice = null;
let polCountdownTimerInterval = null;

function startPolCountdownTimer(seconds = 3600) {
  if (polCountdownTimerInterval) {
    clearInterval(polCountdownTimerInterval);
    polCountdownTimerInterval = null;
  }
  let targetEnd = Date.now() + (seconds * 1000);
  try {
    const raw = localStorage.getItem(getActivePolStorageKey());
    if (raw) {
      const data = JSON.parse(raw);
      if (data && data.expires_at) targetEnd = data.expires_at;
    }
  } catch (e) {}

  const updateDisplay = () => {
    const now = Date.now();
    const remaining = Math.max(0, Math.floor((targetEnd - now) / 1000));
    const timer = document.getElementById('polCountdownTimer');
    const pendingTimer = document.getElementById('activeCryptoPendingTimer');

    if (remaining <= 0) {
      if (timer) timer.innerText = '00:00 (منقضی شد)';
      if (pendingTimer && window.activePendingInvoiceType === 'POL') pendingTimer.innerText = '00:00 (منقضی شد)';
      if (polCountdownTimerInterval) {
        clearInterval(polCountdownTimerInterval);
        polCountdownTimerInterval = null;
      }
      return;
    }
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    const timeStr = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    if (timer) timer.innerText = timeStr;
    if (pendingTimer && window.activePendingInvoiceType === 'POL') pendingTimer.innerText = timeStr;
  };

  updateDisplay();
  polCountdownTimerInterval = setInterval(updateDisplay, 1000);
}

function stopPolCountdownTimer() {
  if (polCountdownTimerInterval) {
    clearInterval(polCountdownTimerInterval);
    polCountdownTimerInterval = null;
  }
}

function getActivePolStorageKey() {
  const tgId = window.lastUserData?.user?.telegram_id || window.Telegram?.WebApp?.initDataUnsafe?.user?.id || 'default';
  return `remna_active_pol_invoice_${tgId}`;
}

function saveActivePolInvoice(inv, durationSec = 3600) {
  try {
    const expiresAt = Date.now() + (durationSec * 1000);
    localStorage.setItem(getActivePolStorageKey(), JSON.stringify({
      invoice: inv,
      expires_at: expiresAt
    }));
  } catch (e) {}
}

function clearActivePolInvoice() {
  try {
    localStorage.removeItem(getActivePolStorageKey());
  } catch (e) {}
  stopPolCountdownTimer();
  currentPolInvoice = null;
  const detailsEl = document.getElementById('polInvoiceDetails');
  const initialEl = document.getElementById('polInvoiceInitial');
  if (detailsEl) detailsEl.classList.add('hidden');
  if (initialEl) initialEl.classList.remove('hidden');
  const input = document.getElementById('polTxIdInput');
  if (input) input.value = '';
  if (window.activePendingInvoiceType === 'POL') {
    updatePendingCardUI(null);
  }
  updateTopupMutexUI();
}

function restoreActivePolInvoice() {
  try {
    const raw = localStorage.getItem(getActivePolStorageKey());
    if (!raw) {
      if (window.activePendingInvoiceType === 'POL') updatePendingCardUI(null);
      return false;
    }
    const data = JSON.parse(raw);
    const now = Date.now();
    const remainingSec = Math.floor((data.expires_at - now) / 1000);
    if (remainingSec <= 0 || !data.invoice) {
      clearActivePolInvoice();
      return false;
    }
    currentPolInvoice = data.invoice;
    document.getElementById('polInvoiceInitial')?.classList.add('hidden');
    document.getElementById('polInvoiceDetails')?.classList.remove('hidden');
    const amtEl = document.getElementById('polAmountDisplay');
    if (amtEl) amtEl.innerText = `${data.invoice.amount_pol} POL`;
    const addrEl = document.getElementById('polPayAddress');
    if (addrEl) addrEl.innerText = data.invoice.pay_address;
    startPolCountdownTimer(remainingSec);
    updatePendingCardUI(data.invoice, remainingSec, 'POL');
    updateTopupMutexUI();
    return true;
  } catch (e) {
    return false;
  }
}

async function openTopupModal(defaultAmt, forceCrypto = false) {
  const { minAmt } = getTopupLimits();
  const amt = defaultAmt ? Math.max(Number(defaultAmt), minAmt) : null;
  const inputEl = document.getElementById('topupAmountInput');
  if (inputEl) {
    inputEl.value = amt !== null ? amt : '';
    inputEl.placeholder = 'مبلغ دلخواه را وارد کنید (تومان)';
  }
  updateTopupDisplays(amt || 0);

  // Initialize selected tab for new modal session
  window.currentTopupTab = forceCrypto ? 'crypto' : null;

  const applyMethodTabs = (s, isInitial = false) => {
    try {
      if (!s) return;
      const hasActiveCrypto = restoreActiveCryptoInvoice();
      const hasActiveTrx = restoreActiveTrxInvoice();
      const hasActivePol = restoreActivePolInvoice();
      const activeType = getActiveInvoiceType();
      const anyEnabled = s.card_enabled !== false || s.stars_enabled !== false || s.crypto_enabled !== false || s.trx_enabled !== false || s.pol_enabled !== false;
      if (!anyEnabled) {
        document.getElementById('topupMethodTabs')?.classList.add('hidden');
        document.getElementById('topupAmountSection')?.classList.add('hidden');
        document.getElementById('topupCardView')?.classList.add('hidden');
        document.getElementById('topupStarsView')?.classList.add('hidden');
        document.getElementById('topupCryptoView')?.classList.add('hidden');
        document.getElementById('topupTrxView')?.classList.add('hidden');
        document.getElementById('topupAllDisabledState')?.classList.remove('hidden');
      } else if (activeType === 'CARD') {
        switchToCardTab();
      } else if (activeType === 'TON') {
        switchToCryptoTab();
      } else if (activeType === 'TRX') {
        switchTopupTab('trx');
      } else if (activeType === 'POL') {
        switchTopupTab('pol');
      } else if ((hasActiveCrypto || forceCrypto) && s.crypto_enabled !== false) {
        switchToCryptoTab();
      } else if (hasActiveTrx && s.trx_enabled !== false) {
        switchTopupTab('trx');
      } else if (hasActivePol && s.pol_enabled !== false) {
        switchTopupTab('pol');
      } else if (!isInitial && window.currentTopupTab) {
        if (window.currentTopupTab === 'stars' && s.stars_enabled !== false) {
          switchTopupTab('stars');
        } else if (window.currentTopupTab === 'crypto' && s.crypto_enabled !== false) {
          switchToCryptoTab();
        } else if (window.currentTopupTab === 'trx' && s.trx_enabled !== false) {
          switchTopupTab('trx');
        } else if (window.currentTopupTab === 'card' && s.card_enabled !== false) {
          switchToCardTab();
        } else {
          if (s.card_enabled !== false) switchToCardTab();
          else if (s.crypto_enabled !== false) switchToCryptoTab();
          else if (s.trx_enabled !== false) switchTopupTab('trx');
          else if (s.stars_enabled !== false) switchTopupTab('stars');
        }
      } else if (s.card_enabled !== false) {
        switchToCardTab();
      } else if (s.crypto_enabled !== false) {
        switchToCryptoTab();
      } else if (s.trx_enabled !== false) {
        switchTopupTab('trx');
      } else if (s.stars_enabled !== false) {
        switchTopupTab('stars');
      }
      updateTopupMutexUI();
      if (s) {
        applyManualCardLockState(
          s.manual_card_blocked ? s.manual_card_blocked_until : null,
          s.manual_card_block_remaining_seconds || 0
        );
      }
    } catch (err) {
      console.warn('Error applying topup method tabs:', err);
    }
  };

  // Apply cached storeSettings immediately if available
  try {
    applyMethodTabs(window.storeSettings, true);
  } catch (e) {}

  // Open modal immediately with 0ms delay
  openModal('topupModal');

  // Load/refresh settings in background (SWR pattern)
  try {
    await loadTopupInfo();
    applyMethodTabs(window.storeSettings, false);
  } catch (e) {}
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

  const methodPolBtn = document.getElementById('topupMethodPolBtn');
  methodPolBtn?.addEventListener('click', () => {
    switchTopupTab('pol');
    restoreActivePolInvoice();
  });

  document.getElementById('closeTopupModalBtn')?.addEventListener('click', () => {
    closeModal('topupModal');
  });

  document.getElementById('chargeWalletBtn')?.addEventListener('click', () => {
    openTopupModal();
  });

  document.getElementById('openActiveCryptoBtn')?.addEventListener('click', () => {
    const pType = window.activePendingInvoiceType;
    if (pType === 'TRX') {
      openTopupModal(50000);
      switchTopupTab('trx');
    } else if (pType === 'POL') {
      openTopupModal(50000);
      switchTopupTab('pol');
    } else if (pType === 'CARD') {
      openTopupModal(50000);
      switchTopupTab('card');
    } else {
      openTopupModal(50000, true);
    }
  });

  document.getElementById('chargeWalletBtn')?.addEventListener('click', () => {
    openTopupModal();
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

  window.updateCardTopupSubmitState();
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
          if (!ctx || !width || !height) {
            resolve(rawData);
            return;
          }
          ctx.drawImage(img, 0, 0, width, height);
          const compressed = canvas.toDataURL('image/jpeg', quality);
          resolve(compressed && compressed.length > 100 ? compressed : rawData);
        };
        img.onerror = () => resolve(rawData);
        img.src = rawData;
      };
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(file);
    });
  }

  const receiptTextInput = document.getElementById('topupCardReceiptInput');
  receiptTextInput?.addEventListener('input', async (e) => {
    _cardTopupGuardState.selectedTextHash = await computeReceiptTextFingerprint(e.target.value);
    window.updateCardTopupSubmitState();
  });

  const resetSelectedReceiptImage = () => {
    _cardTopupGuardState.selectedImageBase64 = null;
    _cardTopupGuardState.selectedImageHash = null;
    _cardTopupGuardState.selectedFileKey = null;
    if (imageInput) imageInput.value = '';
    previewContainer?.classList.add('hidden');
    uploadImgBtn?.classList.remove('hidden');
    window.updateCardTopupSubmitState();
  };

  imageInput?.addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      showToast('⚠️ حداکثر حجم مجاز تصویر 10 مگابایت است.');
      return;
    }
    const compressedBase64 = await compressReceiptImage(file);
    if (!compressedBase64) {
      showToast('⚠️ خطا در پردازش تصویر فیش.');
      return;
    }
    _cardTopupGuardState.selectedImageBase64 = compressedBase64;
    _cardTopupGuardState.selectedFileKey = `file:${file.name}:${file.size}:${file.lastModified}`;
    _cardTopupGuardState.selectedImageHash = await computeReceiptImageFingerprint(compressedBase64);
    if (previewImg) previewImg.src = _cardTopupGuardState.selectedImageBase64;
    if (previewName) previewName.innerText = file.name || 'تصویر رسید انتخاب شد';
    previewContainer?.classList.remove('hidden');
    uploadImgBtn?.classList.add('hidden');
    window.updateCardTopupSubmitState();
  });

  removeImgBtn?.addEventListener('click', resetSelectedReceiptImage);

  document.getElementById('submitCardTopupBtn')?.addEventListener('click', async () => {
    const amt = parseInt(topupAmountInput?.value || '0', 10);
    const receipt = document.getElementById('topupCardReceiptInput')?.value?.trim();
    if (!validateTopupAmount(amt)) return;
    if (!_cardTopupGuardState.selectedImageBase64) {
      showToast('⚠️ لطفاً تصویر فیش واریزی را بارگذاری فرمایید.');
      window.updateCardTopupSubmitState();
      return;
    }

    const submitBtn = document.getElementById('submitCardTopupBtn');
    const submittedImgHash = _cardTopupGuardState.selectedImageHash;
    const submittedFileKey = _cardTopupGuardState.selectedFileKey;
    const submittedTextHash = await computeReceiptTextFingerprint(receipt || '');
    _cardTopupGuardState.selectedTextHash = submittedTextHash;

    submitBtn.disabled = true;
    submitBtn.classList.add('opacity-40', 'cursor-not-allowed');
    submitBtn.innerText = 'در حال ثبت...';
    try {
      const res = await window.api.submitCardTopup(
        amt,
        receipt || '',
        _cardTopupGuardState.selectedImageBase64,
      );
      if (res.ok) {
        if (submittedImgHash) _cardTopupGuardState.knownDuplicateHashes.add(submittedImgHash);
        if (submittedFileKey) _cardTopupGuardState.knownDuplicateHashes.add(submittedFileKey);
        if (submittedTextHash) _cardTopupGuardState.knownDuplicateHashes.add(submittedTextHash);
        _cardTopupGuardState.serverRejectedKey = null;
        _cardTopupGuardState.serverRejectedMsg = '';
        if (receiptTextInput) {
          receiptTextInput.value = '';
          _cardTopupGuardState.selectedTextHash = null;
        }
        showToast('✅ رسید با موفقیت ثبت شد و پس از بررسی ادمین حساب شارژ می‌گردد.');
        resetSelectedReceiptImage();
        closeModal('topupModal');
        if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
      } else {
        const msg = String(res.message || 'خطا در ثبت رسید');
        if (res.error === 'duplicate_receipt' || (msg.includes('تکراری') && !msg.includes('خودکار')) || msg.includes('قبلاً ثبت')) {
          if (msg.includes('پیگیری')) {
            if (submittedTextHash) _cardTopupGuardState.knownDuplicateHashes.add(submittedTextHash);
          } else {
            if (submittedImgHash) _cardTopupGuardState.knownDuplicateHashes.add(submittedImgHash);
            if (submittedFileKey) _cardTopupGuardState.knownDuplicateHashes.add(submittedFileKey);
          }
        } else if (msg.includes('خودکار')) {
          _cardTopupGuardState.recentPaidAutoAmounts.add(amt);
        } else {
          _cardTopupGuardState.serverRejectedKey = `${amt}|${submittedImgHash || ''}|${submittedTextHash || ''}`;
          _cardTopupGuardState.serverRejectedMsg = `⚠️ ${msg}`;
        }
        showToast(`❌ ${msg}`);
      }
    } catch (e) {
      showToast('❌ خطا در ارسال درخواست.');
    } finally {
      window.updateCardTopupSubmitState();
    }
  });

  document.getElementById('submitStarsTopupBtn')?.addEventListener('click', async () => {
    const amt = parseInt(topupAmountInput?.value || '0', 10);
    if (!validateTopupAmount(amt)) return;
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
    const amt = parseInt(topupAmountInput?.value || '0', 10);
    if (!validateTopupAmount(amt)) return;
    const genBtn = document.getElementById('generateTonInvoiceBtn');
    genBtn.disabled = true;
    genBtn.innerText = 'ایجاد فاکتور...';
    try {
      const res = await window.api.createCryptoInvoice(amt);
      if (res.ok && res.invoice) {
        currentTopupInvoice = res.invoice;
        const durationSec = res.invoice.remaining_seconds || (res.invoice.expires_minutes ? res.invoice.expires_minutes * 60 : 3600);
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
        updateTopupMutexUI();
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
    if (!validateTopupAmount(amt)) return;
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
        updateTronLinkButton(res.invoice);
        const trxDurationSec = res.invoice.remaining_seconds || (res.invoice.expires_minutes ? res.invoice.expires_minutes * 60 : 3600);
        startTrxCountdownTimer(trxDurationSec);
        updatePendingCardUI(res.invoice, trxDurationSec, 'TRX');
        updateTopupMutexUI();
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

  document.getElementById('cancelTrxInvoiceBtn')?.addEventListener('click', async () => {
    if (currentTrxInvoice?.id && window.api?.cancelCryptoInvoice) {
      try { await window.api.cancelCryptoInvoice(currentTrxInvoice.id); } catch (e) {}
    }
    clearActiveTrxInvoice();
    updateTopupMutexUI();
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

  // POL Gateway Listeners
  document.getElementById('generatePolInvoiceBtn')?.addEventListener('click', async () => {
    const amt = parseInt(topupAmountInput?.value || '0', 10);
    if (!validateTopupAmount(amt)) return;
    const btn = document.getElementById('generatePolInvoiceBtn');
    btn.disabled = true;
    btn.innerText = 'در حال ایجاد فاکتور پلیگان...';
    try {
      const res = await window.api.createPolInvoice(amt);
      if (res.ok && res.invoice) {
        currentPolInvoice = res.invoice;
        saveActivePolInvoice(res.invoice);
        document.getElementById('polInvoiceInitial')?.classList.add('hidden');
        document.getElementById('polInvoiceDetails')?.classList.remove('hidden');
        const amtEl = document.getElementById('polAmountDisplay');
        if (amtEl) amtEl.innerText = `${res.invoice.amount_pol} POL`;
        const addrEl = document.getElementById('polPayAddress');
        if (addrEl) addrEl.innerText = res.invoice.pay_address;
        const polDurationSec = res.invoice.remaining_seconds || (res.invoice.expires_minutes ? res.invoice.expires_minutes * 60 : 3600);
        startPolCountdownTimer(polDurationSec);
        updatePendingCardUI(res.invoice, polDurationSec, 'POL');
        updateTopupMutexUI();
      } else {
        showToast(`❌ ${res.message || 'خطا در ایجاد فاکتور پلیگان'}`);
      }
    } catch (e) {
      showToast('❌ خطا در برقراری ارتباط با سرور.');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>🟣</span> ایجاد فاکتور پلیگان (POL)';
    }
  });

  const handleCopyPolAddress = () => {
    const addr = document.getElementById('polPayAddress')?.innerText?.trim();
    if (addr && addr !== '--') {
      copyToClipboard(addr, '📋 آدرس ولت پلیگان کپی شد.');
      hapticFeedback('success');
    }
  };
  document.getElementById('copyPolAddressBtn')?.addEventListener('click', handleCopyPolAddress);
  document.getElementById('polPayAddress')?.addEventListener('click', handleCopyPolAddress);

  document.getElementById('copyPolAmountBtn')?.addEventListener('click', () => {
    const amt = currentPolInvoice?.amount_pol;
    if (amt) {
      copyToClipboard(String(amt), '📋 مقدار POL کپی شد.');
      hapticFeedback('success');
    }
  });

  document.getElementById('cancelPolInvoiceBtn')?.addEventListener('click', async () => {
    if (currentPolInvoice?.id && window.api?.cancelCryptoInvoice) {
      try { await window.api.cancelCryptoInvoice(currentPolInvoice.id); } catch (e) {}
    }
    clearActivePolInvoice();
    updateTopupMutexUI();
    showToast('فاکتور پلیگان لغو شد.');
  });

  document.getElementById('openMetaMaskBtn')?.addEventListener('click', async () => {
    if (!currentPolInvoice || !currentPolInvoice.pay_address) {
      showToast('⚠️ ابتدا فاکتور پلیگان را ایجاد فرمایید.');
      return;
    }

    const toAddress = currentPolInvoice.pay_address;
    const weiValStr = currentPolInvoice.wei || '0';
    let weiHex = '0x0';
    try {
      weiHex = '0x' + BigInt(weiValStr).toString(16);
    } catch (_) {
      weiHex = '0x0';
    }

    if (typeof copyToClipboard === 'function') {
      copyToClipboard(toAddress, `📋 آدرس ولت کپی شد (${currentPolInvoice.amount_pol} POL)`);
    }

    // Direct Web3 MetaMask
    if (window.ethereum) {
      try {
        const chainIdHex = '0x89'; // Polygon Mainnet (137)
        try {
          await window.ethereum.request({
            method: 'wallet_switchEthereumChain',
            params: [{ chainId: chainIdHex }],
          });
        } catch (switchError) {
          if (switchError.code === 4902) {
            await window.ethereum.request({
              method: 'wallet_addEthereumChain',
              params: [{
                chainId: chainIdHex,
                chainName: 'Polygon Mainnet',
                nativeCurrency: { name: 'POL', symbol: 'POL', decimals: 18 },
                rpcUrls: ['https://polygon-rpc.com/'],
                blockExplorerUrls: ['https://polygonscan.com/'],
              }],
            });
          }
        }

        const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
        if (accounts && accounts.length > 0) {
          const txParams = {
            from: accounts[0],
            to: toAddress,
            value: weiHex,
            chainId: chainIdHex,
          };
          const txHash = await window.ethereum.request({
            method: 'eth_sendTransaction',
            params: [txParams],
          });
          if (txHash) {
            const input = document.getElementById('polTxIdInput');
            if (input) input.value = txHash;
            showToast('✅ تراکنش در متامسک ثبت شد! در حال تأیید خودکار...');
            setTimeout(() => {
              document.getElementById('submitPolTxIdBtn')?.click();
            }, 1200);
            return;
          }
        }
      } catch (ethErr) {
        console.warn('MetaMask error:', ethErr);
        if (ethErr.code === 4001) {
          showToast('تراکنش در متامسک لغو شد.');
          return;
        }
      }
    }

    // Deep link fallback for mobile / TMA
    const deepLink = `https://metamask.app.link/send/${toAddress}?value=${weiHex}&chainId=137`;
    if (window.Telegram?.WebApp?.openLink) {
      window.Telegram.WebApp.openLink(deepLink);
    } else {
      window.open(deepLink, '_blank');
    }
  });

  document.getElementById('submitPolTxIdBtn')?.addEventListener('click', async () => {
    if (!currentPolInvoice?.id) {
      showToast('⚠️ ابتدا فاکتور پلیگان را ایجاد فرمایید.');
      return;
    }
    const txId = document.getElementById('polTxIdInput')?.value?.trim();
    if (!txId) {
      showToast('⚠️ لطفاً هش تراکنش (TxHash) را وارد فرمایید.');
      return;
    }
    const btn = document.getElementById('submitPolTxIdBtn');
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> در حال استعلام از شبکه پلیگان...';
    try {
      const res = await window.api.verifyPolInvoice(currentPolInvoice.id, txId);
      if (res.ok) {
        showToast('🎉 واریز POL در شبکه پلیگان تأیید شد و کیف پول شارژ گردید!');
        clearActivePolInvoice();
        closeModal('topupModal');
        hapticFeedback('success');
        if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
      } else {
        showToast(`❌ ${res.message || 'تراکنش در شبکه پلیگان تأیید نشد'}`);
      }
    } catch (e) {
      showToast('❌ خطا در بررسی تراکنش.');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>🔍</span> بررسی و تأیید واریز POL';
    }
  });

  restoreActiveCryptoInvoice();
  restoreActiveTrxInvoice();
  restoreActivePolInvoice();
  // Pre-fetch topup settings in background for instant modal responsiveness
  loadTopupInfo().catch(() => {});
}

window.renderWalletTransactions = renderWalletTransactions;
window.openTopupModal = openTopupModal;
window.closeTopupModal = function () {
  if (typeof closeModal === 'function') closeModal('topupModal');
};
window.setupWalletListeners = setupWalletListeners;
