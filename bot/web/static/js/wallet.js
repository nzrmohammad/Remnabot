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

function generateUserCardVerticalCode(tgId) {
  const seed = String(tgId || '987654321');
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) & 0xffffffff;
  }
  const parts = [];
  for (let block = 0; block < 12; block++) {
    let part = '';
    for (let c = 0; c < 4; c++) {
      hash = (hash * 1664525 + 1013904223) & 0xffffffff;
      part += alphabet[Math.abs(hash) % alphabet.length];
    }
    parts.push(part);
  }
  return parts.join(' ');
}

window.flipUserWalletCard = function(el) {
  if (!el) return;
  const flipper = el.classList.contains('user-wallet-card-flipper')
    ? el
    : (el.querySelector('.user-wallet-card-flipper') || el);
  flipper.style.transform = '';
  flipper.classList.toggle('is-flipped');
  if (window.hapticFeedback) window.hapticFeedback('impact');
  if (typeof window.playSubtleSound === 'function') window.playSubtleSound('flip');
  if (typeof window.recordWeeklyQuestEvent === 'function' && localStorage.getItem('user_wallet_card_view') !== 'classic') {
    window.recordWeeklyQuestEvent('wallet_card_check');
  }
};

function _wIsEn() {
  return typeof window !== 'undefined' && (Boolean(window.isAppEn?.()) || window.getAppLanguage?.() === 'en');
}
function _wTr(fa, en) {
  return (typeof window !== 'undefined' && typeof window.trText === 'function')
    ? window.trText(fa, en)
    : (_wIsEn() ? en : fa);
}

const WALLET_CURRENCY_OPTIONS = [
  { id: 'toman', name: 'تومان (IRT)', nameEn: 'Toman (IRT)', desc: 'واحد پایه پولی ایران (پیش‌فرض سامانه ⭐)', descEn: 'Iranian Toman base currency (System Default ⭐)', icon: '/static/img/icons/coins.svg?v=fl2' },
  { id: 'ton', name: 'تون (TON)', nameEn: 'Toncoin (TON)', desc: 'شبکه بلاکچین تلگرام The Open Network', descEn: 'Telegram The Open Network blockchain', icon: '/static/img/icons/ton.svg?v=fl2' },
  { id: 'usdt', name: 'تتر (USDT)', nameEn: 'Tether (USDT)', desc: 'استیبل‌کوین دلاری تتر معادل دلار آمریکا', descEn: 'USD-pegged Tether stablecoin equivalent', icon: '/static/img/icons/credit-card.svg?v=fl2' },
  { id: 'trx', name: 'ترون (TRX)', nameEn: 'TRON (TRX)', desc: 'ارز دیجیتال شبکه پرسرعت TRON', descEn: 'Fast & low-fee TRON network token', icon: '/static/img/icons/tron.svg?v=fl2' },
  { id: 'pol', name: 'پالیگان (POL / MATIC)', nameEn: 'Polygon (POL / MATIC)', desc: 'ارز دیجیتال اکوسیستم و شبکه Polygon', descEn: 'Polygon network ecosystem token', icon: '/static/img/icons/polygon.svg?v=fl2' },
  { id: 'stars', name: 'ستاره تلگرام (Stars ⭐️)', nameEn: 'Telegram Stars ⭐️', desc: 'اعتبار رسمی ستاره‌های درون‌برنامه‌ای تلگرام', descEn: 'Official Telegram in-app Stars balance', icon: '/static/img/icons/star.svg?v=fl2' },
];

window.openWalletCurrencyModal = function() {
  const modal = document.getElementById('walletCurrencyModal');
  const listEl = document.getElementById('walletCurrencyOptionsList');
  if (!modal || !listEl) return;

  const currentVal = localStorage.getItem('user_wallet_currency') || 'toman';
  const isEn = _wIsEn();

  listEl.innerHTML = WALLET_CURRENCY_OPTIONS.map(opt => {
    const isAct = opt.id === currentVal;
    const oName = isEn ? opt.nameEn : opt.name;
    const oDesc = isEn ? opt.descEn : opt.desc;
    return `
      <div onclick="window.selectWalletCurrency && window.selectWalletCurrency('${opt.id}')" class="alert-picker-option cursor-pointer p-2.5 rounded-2xl border transition flex items-center justify-between ${isAct ? 'active-alert-opt s-accent-soft' : 'card-inset t-main hover:border-slate-500'}">
        <div class="flex items-center gap-2.5">
          <div class="w-8 h-8 rounded-xl ${isAct ? 'bg-cyan-500/20 border-cyan-500/30' : 'bg-slate-500/10 border-card-border'} border flex items-center justify-center shrink-0">
            <img src="${opt.icon}" class="ui-icon-img w-4 h-4 shrink-0" width="16" height="16" alt="" />
          </div>
          <div>
            <b class="text-xs block ${isAct ? 't-accent' : 't-main'}">${oName}</b>
            <span class="text-[11px] t-muted block mt-0.5">${oDesc}</span>
          </div>
        </div>
        <div class="w-6 h-6 rounded-full flex items-center justify-center border transition-all ${isAct ? 'bg-cyan-500 border-cyan-500 text-white shadow-xs' : 'border-card-border bg-slate-500/5'}">
          ${isAct ? '<svg class="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>' : ''}
        </div>
      </div>
    `;
  }).join('');

  if (typeof openModal === 'function') openModal('walletCurrencyModal');
  if (window.hapticFeedback) window.hapticFeedback('selection');
};

window.closeWalletCurrencyModal = function() {
  if (typeof closeModal === 'function') closeModal('walletCurrencyModal');
};

window.selectWalletCurrency = function(curr) {
  window.setWalletCurrency(curr);
  window.closeWalletCurrencyModal();
  if (window.hapticFeedback) window.hapticFeedback('success');
  if (typeof window.playSubtleSound === 'function') window.playSubtleSound('color_switch');
};

window.cycleWalletCurrency = function() {
  const currencies = ['toman', 'ton', 'usdt', 'trx', 'pol', 'stars'];
  const cur = localStorage.getItem('user_wallet_currency') || 'toman';
  const nextIdx = (currencies.indexOf(cur) + 1) % currencies.length;
  window.setWalletCurrency(currencies[nextIdx]);
};

window.setWalletCurrency = function(curr) {
  const valid = ['toman', 'ton', 'usdt', 'trx', 'pol', 'stars'];
  const target = valid.includes(curr) ? curr : 'toman';
  localStorage.setItem('user_wallet_currency', target);

  // Sync settings display elements
  const inputEl = document.getElementById('userCurrencyInput');
  const dispEl = document.getElementById('userCurrencyDisplay');
  const subEl = document.getElementById('userCurrencySubtext');
  const matched = WALLET_CURRENCY_OPTIONS.find(o => o.id === target);

  if (inputEl) inputEl.value = target;
  const matchedName = matched ? (_wIsEn() ? matched.nameEn : matched.name) : '';
  if (dispEl && matched) dispEl.innerText = matchedName.split('—')[0].split('(')[0].trim();
  if (subEl && matched) subEl.innerText = _wIsEn() ? `Primary currency: ${matchedName}` : `واحد اصلی: ${matchedName}`;

  window.renderUserWalletCard();
};

window.toggleWalletCardView = function(isGraphic, showToastMsg = true) {
  const graphicBox = document.getElementById('userWalletGraphicBox');
  const classicBox = document.getElementById('userWalletClassicBox');
  const toggleEl = document.getElementById('settingToggleWalletCardView');

  const enable = Boolean(isGraphic);
  localStorage.setItem('user_wallet_card_view', enable ? 'graphic' : 'classic');

  if (toggleEl && toggleEl.checked !== enable) {
    toggleEl.checked = enable;
  }

  if (graphicBox && classicBox) {
    if (enable) {
      graphicBox.classList.remove('hidden');
      classicBox.classList.add('hidden');
    } else {
      graphicBox.classList.add('hidden');
      classicBox.classList.remove('hidden');
    }
  }

  if (showToastMsg && typeof showToast === 'function') {
    showToast(
      enable
        ? _wTr('✨ حالت نمایش کارت گرافیکی فعال شد.', '✨ Graphic wallet card enabled.')
        : _wTr('📋 حالت نمایش کادر ساده فعال شد.', '📋 Simple wallet card view enabled.'),
      'info'
    );
  }
  if (showToastMsg && window.hapticFeedback) {
    window.hapticFeedback('selection');
  }
  if (enable && showToastMsg && typeof window.recordWeeklyQuestEvent === 'function') {
    window.recordWeeklyQuestEvent('wallet_card_check');
  }
};

window.toggleSoundFx = function(enabled) {
  if (enabled) {
    localStorage.removeItem('user_sound_fx_disabled');
    if (typeof window.playSubtleSound === 'function') window.playSubtleSound('selection');
    if (typeof showToast === 'function') showToast(_wTr('🔊 افکت‌های صوتی لمسی فعال شد.', '🔊 Touch sound effects enabled.'), 'info');
  } else {
    localStorage.setItem('user_sound_fx_disabled', '1');
    if (typeof showToast === 'function') showToast(_wTr('🔇 افکت‌های صوتی لمسی غیرفعال شد.', '🔇 Touch sound effects disabled.'), 'info');
  }
  if (window.hapticFeedback) {
    window.hapticFeedback('selection');
  }
};

const USER_WALLET_PALETTES = {
  blue: {
    id: 'blue',
    name: 'آبی رویال',
    nameEn: 'Royal Blue',
    front: 'radial-gradient(circle at 45% 40%, #1e88e5 0%, #1565c0 45%, #0d47a1 80%, #0a256e 100%)',
    back: 'radial-gradient(circle at 50% 50%, #1565c0 0%, #0d47a1 50%, #081d52 100%)',
    accent: '#bfdbfe',
    shadow: '0 20px 42px -10px rgba(13, 71, 161, 0.52)'
  },
  black: {
    id: 'black',
    name: 'مشکی کربن',
    nameEn: 'Carbon Black',
    front: 'radial-gradient(circle at 45% 40%, #3f3f46 0%, #27272a 45%, #18181b 80%, #09090b 100%)',
    back: 'radial-gradient(circle at 50% 50%, #27272a 0%, #18181b 50%, #09090b 100%)',
    accent: '#cbd5e1',
    shadow: '0 20px 42px -10px rgba(24, 24, 27, 0.65)'
  },
  green: {
    id: 'green',
    name: 'سبز یشمی',
    nameEn: 'Emerald Green',
    front: 'radial-gradient(circle at 45% 40%, #00897b 0%, #00695c 45%, #004d40 80%, #00251a 100%)',
    back: 'radial-gradient(circle at 50% 50%, #00695c 0%, #004d40 50%, #00251a 100%)',
    accent: '#a7f3d0',
    shadow: '0 20px 42px -10px rgba(0, 77, 64, 0.55)'
  },
  red: {
    id: 'red',
    name: 'قرمز یاقوتی',
    nameEn: 'Ruby Red',
    front: 'radial-gradient(circle at 45% 40%, #e53935 0%, #c62828 45%, #b71c1c 80%, #5f0909 100%)',
    back: 'radial-gradient(circle at 50% 50%, #c62828 0%, #b71c1c 50%, #5f0909 100%)',
    accent: '#fecaca',
    shadow: '0 20px 42px -10px rgba(183, 28, 28, 0.55)'
  },
  purple: {
    id: 'purple',
    name: 'بنفش نئونی',
    nameEn: 'Neon Purple',
    front: 'radial-gradient(circle at 45% 40%, #8e24aa 0%, #6a1b9a 45%, #4a148c 80%, #26054f 100%)',
    back: 'radial-gradient(circle at 50% 50%, #6a1b9a 0%, #4a148c 50%, #26054f 100%)',
    accent: '#e9d5ff',
    shadow: '0 20px 42px -10px rgba(74, 20, 140, 0.55)'
  },
  yellow: {
    id: 'yellow',
    name: 'طلایی متالیک',
    nameEn: 'Metallic Gold',
    front: 'radial-gradient(circle at 45% 40%, #fb8c00 0%, #e65100 45%, #bf360c 80%, #5d1700 100%)',
    back: 'radial-gradient(circle at 50% 50%, #e65100 0%, #bf360c 50%, #5d1700 100%)',
    accent: '#fed7aa',
    shadow: '0 20px 42px -10px rgba(191, 54, 12, 0.55)'
  }
};

window.setUserWalletCardColor = function(colorKey) {
  const pal = USER_WALLET_PALETTES[colorKey] || USER_WALLET_PALETTES.blue;
  localStorage.setItem('user_wallet_card_color', pal.id);
  window.applyUserWalletCardColor(pal.id);
  const pName = _wIsEn() ? pal.nameEn : pal.name;
  if (typeof showToast === 'function') {
    showToast(_wIsEn() ? `🎨 Wallet card theme changed to ${pName}.` : `🎨 رنگ کارت به ${pal.name} تغییر یافت.`, 'info');
  }
  if (window.hapticFeedback) {
    window.hapticFeedback('selection');
  }
  if (typeof window.playSubtleSound === 'function') {
    window.playSubtleSound('color_switch');
  }
  if (typeof window.recordWeeklyQuestEvent === 'function') {
    window.recordWeeklyQuestEvent('wallet_card_check');
  }
};

window.applyUserWalletCardColor = function(colorKey) {
  const curKey = colorKey || localStorage.getItem('user_wallet_card_color') || 'blue';
  const pal = USER_WALLET_PALETTES[curKey] || USER_WALLET_PALETTES.blue;
  const front = document.querySelector('.user-wallet-card-front');
  const back = document.querySelector('.user-wallet-card-back');
  if (front) {
    front.style.background = pal.front;
    front.style.boxShadow = `${pal.shadow}, inset 0 1px 1px rgba(255, 255, 255, 0.35)`;
  }
  if (back) {
    back.style.background = pal.back;
    back.style.boxShadow = `${pal.shadow}, inset 0 1px 1px rgba(255, 255, 255, 0.35)`;
  }
  const subEl = document.getElementById('userWalletColorSubtext');
  if (subEl) {
    const pName = _wIsEn() ? pal.nameEn : pal.name;
    subEl.innerText = _wIsEn() ? `Active theme: ${pName}` : `طرح فعال: ${pal.name}`;
  }
  document.querySelectorAll('.wallet-card-color-swatch').forEach(btn => {
    const isAct = btn.getAttribute('data-color') === pal.id;
    btn.classList.toggle('ring-2', isAct);
    btn.classList.toggle('ring-offset-2', isAct);
    btn.classList.toggle('ring-cyan-500', isAct);
  });
};

window.renderUserWalletCard = function(userData) {
  const user = userData || window.lastUserData?.user;
  const rawBal = Number(user?.wallet_balance || 0);

  const moneyUnit = _wTr('تومان', 'Toman');

  // Sync legacy hidden element
  const walletTabBal = document.getElementById('walletTabBalance');
  if (walletTabBal) {
    walletTabBal.innerText = `${rawBal.toLocaleString('en-US')} ${moneyUnit}`;
  }

  const balEl = document.getElementById('userWalletCardBalance');
  const classicBal = document.getElementById('classicWalletBalance');
  const classicCurrDisp = document.getElementById('classicWalletCurrencyDisplay');

  // Rates from storeSettings or defaults
  const tonRate = Number(window.storeSettings?.ton_rate_toman) || 500000;
  const usdtRate = Number(window.storeSettings?.usdt_rate_toman) || 75000;
  const trxRate = Number(window.storeSettings?.trx_rate_toman) || 12000;
  const polRate = Number(window.storeSettings?.pol_rate_toman) || 35000;
  const starsRate = Number(window.storeSettings?.stars_rate_toman) || 1500;

  const currentCurrency = localStorage.getItem('user_wallet_currency') || 'toman';

  let formattedBalStr = `${rawBal.toLocaleString('en-US')} ${moneyUnit}`;
  let currencyShortName = moneyUnit;

  if (currentCurrency === 'ton') {
    const tonVal = tonRate > 0 ? (rawBal / tonRate).toFixed(3) : '0';
    formattedBalStr = `${tonVal} TON`;
    currencyShortName = 'TON';
  } else if (currentCurrency === 'usdt') {
    const usdtVal = usdtRate > 0 ? (rawBal / usdtRate).toFixed(2) : '0';
    formattedBalStr = `${usdtVal} USDT`;
    currencyShortName = 'USDT';
  } else if (currentCurrency === 'trx') {
    const trxVal = trxRate > 0 ? (rawBal / trxRate).toFixed(2) : '0';
    formattedBalStr = `${trxVal} TRX`;
    currencyShortName = 'TRX';
  } else if (currentCurrency === 'pol') {
    const polVal = polRate > 0 ? (rawBal / polRate).toFixed(3) : '0';
    formattedBalStr = `${polVal} POL`;
    currencyShortName = 'POL';
  } else if (currentCurrency === 'stars') {
    const starsVal = starsRate > 0 ? Math.floor(rawBal / starsRate).toLocaleString('en-US') : '0';
    formattedBalStr = `${starsVal} ⭐️`;
    currencyShortName = 'Stars ⭐️';
  }

  const prevVal = Number(balEl?.dataset?.prevRawBal || 0);
  if (balEl) balEl.dataset.prevRawBal = String(rawBal);
  if (prevVal !== rawBal && typeof window.animateNumber === 'function' && currentCurrency === 'toman') {
    window.animateNumber(balEl, prevVal, rawBal, 700, (n) => `${n.toLocaleString('en-US')} ${moneyUnit}`);
    if (classicBal) window.animateNumber(classicBal, prevVal, rawBal, 700, (n) => `${n.toLocaleString('en-US')} ${moneyUnit}`);
  } else {
    if (balEl) balEl.innerText = formattedBalStr;
    if (classicBal) classicBal.innerText = formattedBalStr;
  }
  if (classicCurrDisp) classicCurrDisp.innerText = currencyShortName;

  const cardNameEl = document.getElementById('userWalletCardName');
  const cardNumEl = document.getElementById('userWalletCardNumber');
  const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
  const tgId = String(user?.telegram_id || tgUser?.id || user?.id || '').trim();
  window.lastUserTgId = tgId;

  const rawName = (user?.first_name ? `${user.first_name} ${user.last_name || ''}` : (tgUser?.first_name ? `${tgUser.first_name} ${tgUser.last_name || ''}` : (user?.username || 'REMNA VIP'))).trim().toUpperCase();

  if (cardNameEl) {
    cardNameEl.innerText = rawName || 'REMNA VIP';
  }
  if (cardNumEl) {
    cardNumEl.innerText = tgId || '------';
  }

  window.copyUserCardId = function() {
    if (!tgId) {
      if (typeof showToast === 'function') showToast(_wTr('شناسه تلگرام یافت نشد.', 'Telegram ID not found.'));
      return;
    }
    if (typeof copyToClipboard === 'function') {
      copyToClipboard(tgId, _wTr(`📋 شناسه تلگرام جهت دریافت هدیه کپی شد:\n${tgId}`, `📋 Telegram ID copied for receiving gifts:\n${tgId}`));
    }
  };

  window.applyUserWalletCardColor();
  setupUserWalletCardTiltGlare();
};

function setupUserWalletCardTiltGlare() {
  const container = document.querySelector('.user-wallet-card-container');
  if (!container || container.dataset.tiltInit === '1') return;
  container.dataset.tiltInit = '1';

  const sheen = container.querySelector('.user-wallet-card-sheen');
  container.addEventListener('mousemove', (e) => {
    const rect = container.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const tiltX = ((y - centerY) / centerY) * -10;
    const tiltY = ((x - centerX) / centerX) * 12;
    const flipper = container.querySelector('.user-wallet-card-flipper');
    if (flipper && !flipper.classList.contains('is-flipped')) {
      flipper.style.transform = `rotateY(${tiltY}deg) rotateX(${tiltX}deg)`;
    }
    if (sheen) {
      sheen.style.setProperty('--sheen-x', `${Math.round((x / rect.width) * 100)}%`);
      sheen.style.setProperty('--sheen-y', `${Math.round((y / rect.height) * 100)}%`);
    }
  });

  container.addEventListener('mouseleave', () => {
    const flipper = container.querySelector('.user-wallet-card-flipper');
    if (flipper && !flipper.classList.contains('is-flipped')) {
      flipper.style.transform = '';
    }
  });

  if (typeof window !== 'undefined' && window.DeviceOrientationEvent) {
    window.addEventListener('deviceorientation', (e) => {
      const gamma = e.gamma;
      const beta = e.beta;
      if (gamma === null || beta === null) return;
      const flipper = container.querySelector('.user-wallet-card-flipper');
      if (flipper && !flipper.classList.contains('is-flipped')) {
        const tiltY = Math.max(-12, Math.min(12, gamma * 0.35));
        const tiltX = Math.max(-10, Math.min(10, (beta - 45) * 0.3));
        flipper.style.transform = `rotateY(${tiltY}deg) rotateX(${tiltX}deg)`;
      }
      if (sheen) {
        const pctX = Math.max(10, Math.min(90, 50 + gamma));
        const pctY = Math.max(10, Math.min(90, 50 + (beta - 45)));
        sheen.style.setProperty('--sheen-x', `${Math.round(pctX)}%`);
        sheen.style.setProperty('--sheen-y', `${Math.round(pctY)}%`);
      }
    }, { passive: true });
  }
}

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
  const isEn = _wIsEn();
  if (!tx) return { typeRowText: _wTr('خرید بسته', 'Plan Purchase'), planHtml: '' };
  const rawPlan = (tx.service_name || tx.title?.replace(/^خرید\s+/, '') || '').trim();
  const isCustom = Boolean(tx.is_custom || tx.badge === 'custom' || rawPlan.includes('دلخواه') || tx.title?.includes('دلخواه'));

  let typeRowText = _wTr('خرید بسته', 'Plan Purchase');
  let planHtml = '';

  if (isCustom) {
    typeRowText = _wTr('خرید بسته دلخواه', 'Custom Plan Purchase');
    const traf = Number(tx.traffic_gb || 0);
    const days = Number(tx.duration_days || 0);
    const trafStr = traf > 0 ? (typeof fmtTraffic === 'function' ? fmtTraffic(traf, { html: false }) : (isEn ? `${traf} GiB` : `${traf} گیگابایت`)) : '';
    const daysTxt = isEn ? `${days} days` : `${days} روز`;
    const specsStr = (traf > 0 && days > 0) ? `${trafStr} - ${daysTxt}` : (traf > 0 ? trafStr : (days > 0 ? daysTxt : _wTr('بسته اختصاصی', 'Custom Package')));
    planHtml = `<bdi class="font-bold select-all font-sans">${escapeHtml(specsStr)}</bdi>`;
  } else {
    const traf = Number(tx.traffic_gb || 0);
    const days = Number(tx.duration_days || 0);
    if (traf > 0 && days > 0) {
      typeRowText = _wTr('خرید بسته کامل', 'Full Plan Purchase');
    } else if (traf > 0 && days === 0) {
      typeRowText = _wTr('خرید بسته حجم', 'Data Add-on Purchase');
    } else if (traf === 0 && days > 0) {
      typeRowText = _wTr('خرید بسته زمان', 'Time Extension Purchase');
    } else {
      if (rawPlan.includes('حجم')) typeRowText = _wTr('خرید بسته حجم', 'Data Add-on Purchase');
      else if (rawPlan.includes('زمان') || rawPlan.includes('روز')) typeRowText = _wTr('خرید بسته زمان', 'Time Extension Purchase');
      else typeRowText = _wTr('خرید بسته کامل', 'Full Plan Purchase');
    }

    const emojiRegex = /[\p{Extended_Pictographic}\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu;
    const emojis = rawPlan.match(emojiRegex);
    let cleanOnly = rawPlan.replace(emojiRegex, '').trim();

    // Strip duplicate 'بسته' prefix since row 1 already shows 'خرید بسته ...'
    cleanOnly = cleanOnly.replace(/^بسته\s+/, '').trim();
    if (!cleanOnly || cleanOnly === 'بسته') {
      cleanOnly = _wTr('سرویس اشتراکی', 'VPN Plan');
    } else if (cleanOnly.includes('دلخواه') && isEn) {
      cleanOnly = 'Custom Plan';
    }

    let emojiStr = (emojis && emojis.length > 0) ? emojis.join('') : '';
    if (!emojiStr) {
      const lowerName = cleanOnly.toLowerCase();
      if (lowerName.includes('طلایی') || lowerName.includes('gold')) emojiStr = 'medal-gold';
      else if (lowerName.includes('نقره') || lowerName.includes('silver')) emojiStr = 'medal-silver';
      else if (lowerName.includes('برنز') || lowerName.includes('bronze')) emojiStr = 'medal-bronze';
      else if (lowerName.includes('الماس') || lowerName.includes('diamond')) emojiStr = 'diamond';
      else if (lowerName.includes('ویژه') || lowerName.includes('vip')) emojiStr = 'crown';
      else if (lowerName.includes('گیم') || lowerName.includes('game')) emojiStr = 'gamepad';
      else if (lowerName.includes('خانواده') || lowerName.includes('family')) emojiStr = 'users';
      else if (traf > 0 && days === 0) emojiStr = 'zap';
      else if (traf === 0 && days > 0) emojiStr = 'clock';
      else emojiStr = 'package';
    }

    const iconHtml = `<span class="shrink-0 inline-flex items-center justify-center">${typeof uiEmojiIcon === 'function' ? uiEmojiIcon(emojiStr || '📦', 'w-4 h-4') : (emojiStr || '📦')}</span>`;
    planHtml = `<span class="inline-flex items-center gap-1.5"><bdi class="font-bold select-all">${escapeHtml(cleanOnly)}</bdi>${iconHtml}</span>`;
  }

  return { typeRowText, planHtml };
}

function formatTxPlan(tx) {
  return getTxPurchaseInfo(tx).planHtml;
}

function formatTxTitle(tx) {
  if (!tx) return _wTr('تراکنش', 'Transaction');
  if (tx.type === 'order' || (tx.title && tx.title.startsWith('خرید '))) {
    const { typeRowText } = getTxPurchaseInfo(tx);
    return typeRowText;
  }
  return escapeHtml(tx.title || _wTr('تراکنش', 'Transaction'));
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
      <div class="empty-state">
        <img src="/static/img/icons/receipt.svg?v=fl2" class="empty-state-icon" width="40" height="40" alt="" />
        <span class="empty-state-title">${_wTr('تاریخچه تراکنش‌ها خالی است', 'No transactions yet')}</span>
        <span class="empty-state-desc">${_wTr('هنوز تراکنش یا سفارشی برای این حساب ثبت نشده است.', 'No payments or orders have been recorded for this account yet.')}</span>
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
  const isEnLang = _wIsEn();

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
      const rawTitle = (typeof window.translateUiPhrase === 'function' && isEnLang)
        ? window.translateUiPhrase(tx.title || 'تراکنش')
        : (tx.title || _wTr('تراکنش', 'Transaction'));
      titleBlock = `<div class="font-bold t-main text-xs sm:text-sm leading-snug break-words">${escapeHtml(rawTitle)}</div>`;
    }

    const invoiceBtn = isOrder ? `
      <button type="button" onclick="event.stopPropagation(); window.openInvoiceModal && window.openInvoiceModal(${tx.id}, '${tx.type || 'order'}');" class="text-[10px] text-cyan-600 dark:text-cyan-400 hover:underline flex items-center gap-0.5 font-bold" title="${_wTr('مشاهده و دانلود فاکتور رسمی', 'View and download official invoice')}">
        <span>🧾</span> <span>${_wTr('فاکتور', 'Invoice')}</span>
      </button>
    ` : '';

    const txIcon = ({ topup: '💳', card_auto: '💳', crypto: '💎', admin_adjust: '⚡️' })[tx.type] || '🛒';
    const txUnitLabel = isEnLang ? 'Toman' : 'تومان';
    const txDateDisplay = toEnglishDigits(isEnLang ? (tx.date_formatted || tx.date_jalali || '') : (tx.date_jalali || ''));
    const rawStatus = tx.status || 'موفق';
    const displayStatus = (isEnLang && typeof window.translateUiPhrase === 'function')
      ? window.translateUiPhrase(rawStatus)
      : rawStatus;
    return `
    <div class="card-inset rounded-2xl p-4 sm:p-4.5 flex items-center justify-between text-xs sm:text-[13px] gap-3 min-h-[72px] ${isOrder ? 'cursor-pointer hover:border-cyan-500/40 transition active:scale-[0.99]' : ''}" ${isOrder ? `onclick="window.openInvoiceModal && window.openInvoiceModal(${tx.id}, '${tx.type || 'order'}');"` : ''}>
      <div class="flex items-center gap-2.5 min-w-0 flex-1">
        <span class="text-xl shrink-0">${txIcon}</span>
        <div class="min-w-0 flex-1 space-y-1">
          ${titleBlock}
          <span class="text-[10px] t-muted font-sans num-bidi block" dir="ltr">${txDateDisplay}</span>
        </div>
      </div>
      <div class="${isEnLang ? 'text-right' : 'text-left'} shrink-0 space-y-0.5">
        <div class="inline-flex items-center gap-1 font-bold ${tx.is_positive ? 't-success' : 't-main'}" dir="${isEnLang ? 'ltr' : 'rtl'}">
          <span class="font-sans num-bidi text-xs sm:text-sm" dir="ltr">${tx.is_positive ? "+" : "-"}${Number(tx.amount != null ? tx.amount : 0).toLocaleString("en-US")}</span>
          <span class="font-sans text-[10px] t-muted font-normal">${txUnitLabel}</span>
        </div>
        <div class="flex items-center justify-end gap-1.5">
          <span class="text-[10px] ${statusColor} font-sans block">
            ${escapeHtml(displayStatus)}
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
      <button type="button" id="walletPrevPageBtn" class="p-1.5 rounded-lg border border-[var(--card-border)] bg-transparent t-muted hover:t-main transition active:scale-95 flex items-center justify-center ${currentWalletPage === 1 ? 'opacity-30 cursor-not-allowed pointer-events-none' : ''}" title="${_wTr('صفحه قبل', 'Previous Page')}">
        <svg class="w-4 h-4 ${isEnLang ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
      </button>
      <span class="text-[11px] text-slate-400 font-sans num-bidi">
        ${isEnLang ? `Page <b class="t-main">${currentWalletPage}</b> of <b class="t-main">${totalPages}</b>` : `صفحه <b class="t-main">${currentWalletPage}</b> از <b class="t-main">${totalPages}</b>`}
      </span>
      <button type="button" id="walletNextPageBtn" class="p-1.5 rounded-lg border border-[var(--card-border)] bg-transparent t-muted hover:t-main transition active:scale-95 flex items-center justify-center ${currentWalletPage === totalPages ? 'opacity-30 cursor-not-allowed pointer-events-none' : ''}" title="${_wTr('صفحه بعد', 'Next Page')}">
        <svg class="w-4 h-4 ${isEnLang ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
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
  const moneyUnit = _wTr('تومان', 'Toman');
  if (!amt || isNaN(amt) || amt <= 0) {
    if (window.showToast) {
      window.showToast(_wTr('لطفاً ابتدا مبلغ شارژ مورد نظر خود را وارد یا انتخاب نمایید.', 'Please enter or select a top-up amount first.'), 'warning');
    }
    return false;
  }
  if (amt < minAmt) {
    if (window.showToast) {
      window.showToast(
        _wIsEn() ? `Minimum top-up amount is ${minAmt.toLocaleString('en-US')} ${moneyUnit}.` : `حداقل مبلغ شارژ ${minAmt.toLocaleString('en-US')} تومان است.`,
        'warning'
      );
    }
    return false;
  }
  if (maxAmt > 0 && amt > maxAmt) {
    if (window.showToast) {
      window.showToast(
        _wIsEn() ? `Maximum top-up amount is ${maxAmt.toLocaleString('en-US')} ${moneyUnit}.` : `حداکثر مبلغ شارژ ${maxAmt.toLocaleString('en-US')} تومان است.`,
        'warning'
      );
    }
    return false;
  }
  return true;
}
window.validateTopupAmount = validateTopupAmount;

function updateTopupDisplays(amt) {
  const moneyUnit = _wTr('تومان', 'Toman');
  const cardAmountDisplay = document.getElementById('topupCardAmountDisplay');
  if (cardAmountDisplay) {
    const formattedAmt = Number(amt || 0).toLocaleString('en-US');
    cardAmountDisplay.innerHTML = `<span class="font-sans font-bold">${formattedAmt}</span> <span class="text-xs font-medium">${moneyUnit}</span>`;
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
  if (starsRateEl) {
    starsRateEl.innerHTML = `<span class="font-sans font-bold" dir="ltr">${Number(starsRate).toLocaleString('en-US')}</span> <span>${moneyUnit}</span>`;
  }
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
    submitCardBtn.innerText = _wTr('🔒 نیاز به تأیید شماره تماس', '🔒 Phone Verification Required');
    setDisabled(true, '');
    return;
  }

  if (_cardTopupGuardState.manualBlockUntilMs > Date.now()) {
    submitCardBtn.innerText = _wTr(`🔒 ارسال دستی تا ${MANUAL_CARD_LOCK_HOURS} ساعت مسدود است`, `🔒 Manual receipts locked for ${MANUAL_CARD_LOCK_HOURS}h`);
    setDisabled(true, _wTr(
      `🔒 به دلیل وجود فاکتور کارت‌به‌کارت خودکار، تا ${MANUAL_CARD_LOCK_HOURS} ساعت امکان ثبت دستی فیش وجود ندارد.`,
      `🔒 Due to an auto card-to-card invoice, manual receipt uploads are locked for ${MANUAL_CARD_LOCK_HOURS} hours.`
    ));
    return;
  }

  submitCardBtn.innerText = _wTr('📤 ثبت و ارسال رسید پرداخت', '📤 Submit Payment Receipt');

  const amt = parseInt(document.getElementById('topupAmountInput')?.value || '0', 10) || 0;
  const minAmt = window.storeSettings?.topup_min_amount || 10000;
  const maxAmt = window.storeSettings?.topup_max_amount || 50000000;

  if (amt > 0 && _cardTopupGuardState.recentPaidAutoAmounts.has(amt)) {
    setDisabled(true, _wTr('⚠️ این مبلغ پیش‌تر به‌صورت خودکار تأیید و شارژ شده است؛ نیازی به ارسال فیش نیست.', '⚠️ This amount was already credited automatically; no receipt upload needed.'));
    return;
  }

  const dupImg = (
    (_cardTopupGuardState.selectedImageHash && _cardTopupGuardState.knownDuplicateHashes.has(_cardTopupGuardState.selectedImageHash))
    || (_cardTopupGuardState.selectedFileKey && _cardTopupGuardState.knownDuplicateHashes.has(_cardTopupGuardState.selectedFileKey))
  );
  if (dupImg) {
    setDisabled(true, _wTr('⚠️ این تصویر فیش قبلاً ثبت شده و تکراری است؛ لطفاً تصویر فیش جدید بارگذاری کنید.', '⚠️ This receipt image was already submitted; please upload a new receipt.'));
    return;
  }

  if (_cardTopupGuardState.selectedTextHash && _cardTopupGuardState.knownDuplicateHashes.has(_cardTopupGuardState.selectedTextHash)) {
    setDisabled(true, _wTr('⚠️ این کد پیگیری قبلاً ثبت شده و تکراری است؛ لطفاً کد جدید یا متن متفاوتی وارد کنید.', '⚠️ This reference code was already submitted; please enter a new one.'));
    return;
  }

  const currentKey = `${amt}|${_cardTopupGuardState.selectedImageHash || ''}|${_cardTopupGuardState.selectedTextHash || ''}`;
  if (_cardTopupGuardState.serverRejectedKey && _cardTopupGuardState.serverRejectedKey === currentKey) {
    setDisabled(true, _cardTopupGuardState.serverRejectedMsg || _wTr('⚠️ این درخواست قبلاً ثبت شده است.', '⚠️ This request has already been submitted.'));
    return;
  }

  const hasValidAmount = amt >= minAmt && amt <= maxAmt;
  const hasImage = Boolean(_cardTopupGuardState.selectedImageBase64);
  setDisabled(!(hasImage && hasValidAmount), '');
};

async function loadTopupInfo(options = {}) {
  try {
    const res = await window.api.getTopupInfo(options);
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
      const rawHolder = res.card_holder || _wTr('مدیریت سرور', 'Store Admin');

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
      if (window.renderUserWalletCard) window.renderUserWalletCard();

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
        const typeName = activeType === 'CARD'
          ? _wTr('کارت‌به‌کارت', 'Card-to-Card')
          : (activeType === 'TRX' ? _wTr('ترون (TRX)', 'TRON (TRX)') : (activeType === 'POL' ? _wTr('پلیگان (POL)', 'Polygon (POL)') : _wTr('تون (TON)', 'TON')));
        window.showToast(
          _wTr(`شما یک فاکتور فعال در جریان (${typeName}) دارید. لطفاً ابتدا آن را پرداخت یا لغو نمایید.`, `You have an active pending invoice (${typeName}). Please pay or cancel it first.`),
          'warning'
        );
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
  const holderToDisplay = inv.card_holder || window.storeSettings?.card_holder || _wTr('مدیریت سرور', 'Store Admin');

  if (exactTomanEl) {
    const tomanVal = Number(inv.exact_amount || 0).toLocaleString('en-US');
    exactTomanEl.innerHTML = `<span class="font-sans font-bold">${tomanVal}</span> <span class="text-xs font-medium">${_wTr('تومان', 'Toman')}</span>`;
  }
  if (exactRialEl) {
    const rialVal = Number(inv.exact_rial || (inv.exact_amount * 10) || 0).toLocaleString('en-US');
    exactRialEl.innerHTML = `<span class="font-sans font-bold">${rialVal}</span> <span class="text-xs font-medium">${_wTr('ریال', 'Rial')}</span>`;
  }
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
      if (timerEl) timerEl.innerText = _wTr('00:00 (منقضی شد)', '00:00 (Expired)');
      if (window.activePendingInvoiceType === 'CARD') {
        const pendingTimer = document.getElementById('activeCryptoPendingTimer');
        if (pendingTimer) pendingTimer.innerText = _wTr('00:00 (منقضی شد)', '00:00 (Expired)');
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
            window.showToast(_wTr('✅ پرداخت شما با موفقیت تأیید شد و کیف پول شارژ گردید!', '✅ Payment confirmed and wallet topped up!'), 'success');
          }
          window.hapticFeedback?.('success');
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
    btn.innerHTML = `<span class="inline-block animate-spin mr-1">⌛</span> ${_wTr('در حال ایجاد فاکتور...', 'Creating invoice...')}`;
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
      if (window.showToast) window.showToast(_wTr('فاکتور پرداخت هوشمند با موفقیت ایجاد شد.', 'Smart payment invoice created successfully.'), 'success');
    } else {
      if (window.showToast) window.showToast(res?.message || _wTr('خطا در ایجاد فاکتور', 'Error creating invoice'), 'error');
    }
  } catch (err) {
    if (window.showToast) window.showToast(_wTr('خطا در برقراری ارتباط با سرور', 'Server connection error'), 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<img src="/static/img/icons/zap.svg?v=fl2" class="ui-icon-img w-4 h-4 shrink-0 inline-block icon-white" width="16" height="16" alt="" /> <span class="text-white">${_wTr('ایجاد فاکتور پرداخت آنی کارت‌به‌کارت', 'Create Instant Card Payment Invoice')}</span>`;
    }
  }
};

window.checkCardAutoStatus = async function (isManual = false) {
  if (!activeCardAutoUuid) return;
  const chkBtn = document.getElementById('checkCardAutoStatus');
  if (isManual && chkBtn) {
    chkBtn.disabled = true;
    chkBtn.innerHTML = `<svg class="w-4 h-4 shrink-0 animate-spin" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg><span>${_wTr('در حال بررسی...', 'Checking...')}</span>`;
  }
  try {
    const res = await window.api.getCardAutoStatus(activeCardAutoUuid);
    if (res && res.ok) {
      if (res.status === 'paid') {
        stopCardAutoPolling();
        if (window.showToast) window.showToast(_wTr('✅ پرداخت تایید شد و حساب شما شارژ گردید!', '✅ Payment confirmed and account topped up!'), 'success');
        resetCardAutoUI();
        applyManualCardLockState(res.manual_card_blocked ? res.manual_card_blocked_until : null, res.manual_card_block_remaining_seconds || 0);
        if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
        if (typeof closeModal === 'function') closeModal('topupModal');
      } else if (res.status === 'expired') {
        if (window.showToast) window.showToast(_wTr('مهلت پرداخت این فاکتور به پایان رسیده است.', 'This invoice payment window has expired.'), 'warning');
        resetCardAutoUI();
        applyManualCardLockState(res.manual_card_blocked ? res.manual_card_blocked_until : null, res.manual_card_block_remaining_seconds || 0);
      } else if (isManual) {
        if (window.showToast) window.showToast(_wTr('هنوز پیامی مبنی بر واریز دریافت نشده است؛ لطفاً پس از واریز صبور باشید.', 'No bank deposit notification received yet; please wait shortly after paying.'), 'info');
      }
    }
  } catch (e) {} finally {
    if (isManual && chkBtn) {
      chkBtn.disabled = false;
      chkBtn.innerHTML = `<svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg><span>${_wTr('بررسی وضعیت', 'Check Status')}</span>`;
    }
  }
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
      if (window.showToast) window.showToast(cancelRes.message || _wTr('امکان لغو این فاکتور وجود ندارد.', 'Cannot cancel this invoice.'), 'warning');
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
    if (window.showToast) window.showToast(_wTr('فاکتور پرداخت لغو گردید.', 'Payment invoice cancelled.'), 'info');
  } catch (e) {}
};

window.copyCardNumber = function (btnEl) {
  const el = document.getElementById('cardAutoCardNumber') || document.getElementById('topupCardNumber');
  const card = el?.innerText?.trim();
  if (card && !card.includes('----') && !card.includes('ثبت نشده')) {
    const cleanDigits = card.replace(/[^\d]/g, '');
    const copyFn = typeof copyToClipboard === 'function' ? copyToClipboard : window.copyToClipboard;
    if (copyFn) copyFn(cleanDigits || card, _wTr('📋 شماره کارت در کلیپ‌بورد کپی شد.', '📋 Card number copied.'));
    if (typeof hapticFeedback === 'function') hapticFeedback('success');
    const targetBtn = btnEl || document.getElementById('copyCardAutoBtn') || document.getElementById('copyTopupCardBtn');
    if (targetBtn && targetBtn.tagName === 'BUTTON') {
      const orig = targetBtn.innerText;
      targetBtn.innerText = '✅';
      setTimeout(() => { targetBtn.innerText = orig; }, 1500);
    }
  } else {
    if (typeof showToast === 'function') showToast(_wTr('⚠️ شماره کارتی برای کپی کردن یافت نشد.', '⚠️ No card number found to copy.'));
  }
};

window.copyCardAutoAmount = function (type) {
  const el = type === 'rial' ? document.getElementById('cardAutoExactRial') : document.getElementById('cardAutoExactToman');
  const text = el?.innerText?.trim() || '';
  const digits = text.replace(/[^\d]/g, '');
  if (digits) {
    const unitLabel = type === 'rial' ? _wTr('ریال', 'Rial') : _wTr('تومان', 'Toman');
    copyToClipboard(digits, _wTr(`📋 مبلغ (${unitLabel}) در کلیپ‌بورد کپی شد.`, `📋 Amount (${unitLabel}) copied.`));
  }
};

window.toggleManualReceiptUpload = function () {
  const section = document.getElementById('manualCardTopupSection');
  if (_cardTopupGuardState.manualBlockUntilMs > Date.now()) {
    if (section) section.classList.add('hidden');
    if (window.showToast) {
      const rem = formatLockCountdownHHMMSS(Math.ceil((_cardTopupGuardState.manualBlockUntilMs - Date.now()) / 1000));
      window.showToast(
        _wTr(
          `🔒 تا ${MANUAL_CARD_LOCK_HOURS} ساعت پس از ایجاد یا استفاده از فاکتور کارت‌به‌کارت خودکار (${rem})، امکان ارسال دستی فیش وجود ندارد.`,
          `🔒 Manual receipt uploads are locked for ${MANUAL_CARD_LOCK_HOURS}h after an auto card invoice (${rem}).`
        ),
        'warning'
      );
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
      titleEl.innerText = _wTr('فاکتور ترون (TRX) در جریان', 'Active TRON (TRX) Invoice');
    } else if (type === 'POL') {
      titleEl.innerText = _wTr('فاکتور پلیگان (POL) در جریان', 'Active Polygon (POL) Invoice');
    } else if (type === 'CARD') {
      titleEl.innerText = _wTr('فاکتور کارت‌به‌کارت در جریان', 'Active Card Payment Invoice');
    } else {
      titleEl.innerText = _wTr('فاکتور تون (TON) در جریان', 'Active TON Invoice');
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
      amtEl.innerText = `${Number(rial).toLocaleString('en-US')} ${_wTr('ریال', 'Rial')}`;
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
        timer.innerText = _wTr('00:00 (منقضی شد)', '00:00 (Expired)');
        timer.classList.remove('t-warn', 'text-amber-400', 'bg-amber-500/10', 'border-amber-500/20');
        timer.classList.add('t-danger');
      }
      if (pendingTimer && window.activePendingInvoiceType === 'TON') {
        pendingTimer.innerText = _wTr('00:00 (منقضی شد)', '00:00 (Expired)');
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
    genBtn.innerText = _wTr('💎 ایجاد فاکتور پرداخت TON', '💎 Create TON Payment Invoice');
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
  showToast(_wTr('✅ فاکتور لغو شد. می‌توانید فاکتور جدید صادر فرمایید.', '✅ Invoice cancelled. You can create a new one.'));
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
      copyToClipboard(inv.pay_address, _wTr(`📋 آدرس ترون کپی شد (${trxAmount} TRX)`, `📋 TRON address copied (${trxAmount} TRX)`));
    }

    if (window.Telegram?.WebApp?.openLink) {
      window.Telegram.WebApp.openLink(redirectUrl);
      return;
    }

    try {
      window.location.href = tronUri;
    } catch (_) {
      window.openExternalUrl ? window.openExternalUrl(redirectUrl) : window.open(redirectUrl, '_blank', 'noopener,noreferrer');
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
      if (timer) timer.innerText = _wTr('00:00 (منقضی شد)', '00:00 (Expired)');
      if (pendingTimer && window.activePendingInvoiceType === 'TRX') pendingTimer.innerText = _wTr('00:00 (منقضی شد)', '00:00 (Expired)');
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
      if (timer) timer.innerText = _wTr('00:00 (منقضی شد)', '00:00 (Expired)');
      if (pendingTimer && window.activePendingInvoiceType === 'POL') pendingTimer.innerText = _wTr('00:00 (منقضی شد)', '00:00 (Expired)');
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
    inputEl.placeholder = _wTr('مبلغ دلخواه را وارد کنید (تومان)', 'Enter custom amount (Toman)');
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
    await loadTopupInfo({ refresh: true });
    applyMethodTabs(window.storeSettings, false);
  } catch (e) {}
}

function setupWalletListeners() {
  // Initialize wallet card graphic/classic view state from localStorage
  const isGraphic = localStorage.getItem('user_wallet_card_view') !== 'classic';
  if (window.toggleWalletCardView) {
    window.toggleWalletCardView(isGraphic, false);
  }

  const soundToggle = document.getElementById('settingToggleSoundFx');
  if (soundToggle) {
    soundToggle.checked = localStorage.getItem('user_sound_fx_disabled') !== '1';
  }

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
    if (card && !card.includes('----') && !card.includes('ثبت نشده') && !card.includes('Not set')) {
      const cleanDigits = card.replace(/[^\d]/g, '');
      copyToClipboard(cleanDigits || card, _wTr('📋 شماره کارت در کلیپ‌بورد کپی شد.', '📋 Card number copied to clipboard.'));
      hapticFeedback('success');
      const btn = document.getElementById('copyTopupCardBtn');
      if (btn) {
        btn.innerText = '✅';
        setTimeout(() => { btn.innerText = '📋'; }, 1500);
      }
    } else {
      showToast(_wTr('⚠️ شماره کارتی برای کپی کردن یافت نشد.', '⚠️ No card number found to copy.'));
    }
  };

  document.getElementById('copyTopupCardBtn')?.addEventListener('click', handleCopyCard);
  document.getElementById('topupCardNumber')?.addEventListener('click', handleCopyCard);

  const handleCopyCardAmount = () => {
    const amtEl = document.getElementById('topupCardAmountDisplay');
    const amtText = amtEl?.innerText?.trim();
    if (amtText && !amtText.includes('--')) {
      const cleanDigits = amtText.replace(/[^\d]/g, '');
      copyToClipboard(cleanDigits || amtText, _wTr('📋 مبلغ در کلیپ‌بورد کپی شد.', '📋 Amount copied to clipboard.'));
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
      showToast(_wTr('⚠️ حداکثر حجم مجاز تصویر 10 مگابایت است.', '⚠️ Maximum allowed image size is 10 MB.'));
      return;
    }
    const compressedBase64 = await compressReceiptImage(file);
    if (!compressedBase64) {
      showToast(_wTr('⚠️ خطا در پردازش تصویر فیش.', '⚠️ Failed to process the receipt image.'));
      return;
    }
    _cardTopupGuardState.selectedImageBase64 = compressedBase64;
    _cardTopupGuardState.selectedFileKey = `file:${file.name}:${file.size}:${file.lastModified}`;
    _cardTopupGuardState.selectedImageHash = await computeReceiptImageFingerprint(compressedBase64);
    if (previewImg) previewImg.src = _cardTopupGuardState.selectedImageBase64;
    if (previewName) previewName.innerText = file.name || _wTr('تصویر رسید انتخاب شد', 'Receipt image selected');
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
      showToast(_wTr('⚠️ لطفاً تصویر فیش واریزی را بارگذاری فرمایید.', '⚠️ Please upload the payment receipt image.'));
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
    submitBtn.innerText = _wTr('در حال ثبت...', 'Submitting...');
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
        showToast(_wTr('✅ رسید با موفقیت ثبت شد و پس از بررسی ادمین حساب شارژ می‌گردد.', '✅ Receipt submitted and will be credited after admin review.'));
        resetSelectedReceiptImage();
        closeModal('topupModal');
        if (typeof window.markAwaitingTopupSync === 'function') window.markAwaitingTopupSync();
        if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId, { refresh: true });
      } else {
        const msg = String(res.message || _wTr('خطا در ثبت رسید', 'Failed to submit receipt'));
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
      showToast(_wTr('❌ خطا در ارسال درخواست.', '❌ Request failed.'));
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
      btn.innerHTML = `<span class="inline-flex items-center gap-1.5">${uiIcon('recycle', 'w-3.5 h-3.5 inline-block shrink-0 animate-spin')}<span>${_wTr('در حال ایجاد فاکتور استارز...', 'Creating Stars invoice...')}</span></span>`;
    }
    try {
      const res = await window.api.createStarsInvoice(amt);
      if (res && res.ok && res.invoice_link) {
        if (window.Telegram?.WebApp?.openInvoice) {
          window.Telegram.WebApp.openInvoice(res.invoice_link, (status) => {
            if (status === 'paid') {
              showToast(_wTr('🎉 پرداخت استارز با موفقیت تایید شد و کیف پول شارژ گردید!', '🎉 Stars payment confirmed and wallet credited!'));
              closeModal('topupModal');
              const sync = () => {
                if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId, { refresh: true });
              };
              sync();
              setTimeout(sync, 1500);
            } else if (status === 'cancelled') {
              showToast(_wTr('پرداخت استارز لغو شد.', 'Stars payment cancelled.'));
            } else if (status === 'failed') {
              showToast(_wTr('❌ پرداخت استارز انجام نشد.', '❌ Stars payment failed.'));
            }
          });
        } else {
          window.openExternalUrl ? window.openExternalUrl(res.invoice_link) : window.open(res.invoice_link, '_blank', 'noopener,noreferrer');
        }
      } else {
        showToast(`❌ ${res?.error || res?.message || _wTr('خطا در ایجاد فاکتور استارز', 'Error creating Stars invoice')}`);
      }
    } catch (e) {
      showToast(_wTr('❌ خطا در ارتباط با سرور.', '❌ Server connection error.'));
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<span>⭐</span> ${_wTr('پرداخت با استارز تلگرام', 'Pay with Telegram Stars')}`;
      }
    }
  });

  document.getElementById('generateTonInvoiceBtn')?.addEventListener('click', async () => {
    const amt = parseInt(topupAmountInput?.value || '0', 10);
    if (!validateTopupAmount(amt)) return;
    const genBtn = document.getElementById('generateTonInvoiceBtn');
    genBtn.disabled = true;
    genBtn.innerText = _wTr('ایجاد فاکتور...', 'Creating invoice...');
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
        showToast(`❌ ${res.message || _wTr('خطا در ایجاد فاکتور کریپتو', 'Error creating TON invoice')}`);
      }
    } catch (e) {
      showToast(_wTr('❌ خطا در برقراری ارتباط.', '❌ Connection failed.'));
    } finally {
      genBtn.disabled = false;
      genBtn.innerText = _wTr('💎 ایجاد فاکتور پرداخت TON', '💎 Create TON Payment Invoice');
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
          window.openExternalUrl ? window.openExternalUrl(targetLink) : window.open(targetLink, '_blank', 'noopener,noreferrer');
        }
      } else {
        window.openExternalUrl ? window.openExternalUrl(targetLink) : window.open(targetLink, '_blank', 'noopener,noreferrer');
      }
    }
  });

  document.getElementById('copyTonAmountBtn')?.addEventListener('click', () => {
    if (currentTopupInvoice?.amount_ton) {
      copyToClipboard(String(currentTopupInvoice.amount_ton), _wTr('📋 مقدار TON کپی شد.', '📋 TON amount copied.'));
    }
  });

  document.getElementById('copyTonAddressBtn')?.addEventListener('click', () => {
    if (currentTopupInvoice?.pay_address) {
      copyToClipboard(currentTopupInvoice.pay_address, _wTr('📋 آدرس ولت TON کپی شد.', '📋 TON wallet address copied.'));
    }
  });

  document.getElementById('copyTonCommentBtn')?.addEventListener('click', () => {
    if (currentTopupInvoice?.comment) {
      copyToClipboard(currentTopupInvoice.comment, _wTr('📋 کامنت (Memo) کپی شد.', '📋 Comment (Memo) copied.'));
    }
  });

  document.getElementById('cryptoCancelInvoiceBtn')?.addEventListener('click', async () => {
    const invId = currentTopupInvoice?.id;
    if (invId && window.api?.cancelCryptoInvoice) {
      try {
        await window.api.cancelCryptoInvoice(invId);
      } catch (err) {
        console.warn('cancelCryptoInvoice error:', err);
      }
    }
    clearActiveCryptoInvoice();
    showToast(_wTr('فاکتور قبلی لغو شد. می‌توانید فاکتور جدید صادر فرمایید.', 'Previous invoice cancelled. You can create a new one.'));
  });

  document.getElementById('cryptoCheckStatusBtn')?.addEventListener('click', async () => {
    if (!currentTopupInvoice?.id) return;
    const chkBtn = document.getElementById('cryptoCheckStatusBtn');
    chkBtn.disabled = true;
    chkBtn.innerHTML = `<svg class="w-4 h-4 shrink-0 animate-spin" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg><span>${_wTr('در حال بررسی...', 'Checking...')}</span>`;
    try {
      const res = await window.api.checkCryptoInvoice(currentTopupInvoice.id);
      if (res.ok && res.paid) {
        showToast(_wTr('🎉 پرداخت تایید شد و کیف پول شارژ گردید!', '🎉 Payment confirmed and wallet credited!'));
        clearActiveCryptoInvoice();
        closeModal('topupModal');
        if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
      } else {
        showToast(res.message || _wTr('تراکنش هنوز تایید نشده است.', 'Transaction not confirmed yet.'));
      }
    } catch (e) {
      showToast(_wTr('❌ خطا در استعلام پرداخت.', '❌ Failed to check payment status.'));
    } finally {
      chkBtn.disabled = false;
      chkBtn.innerHTML = '<svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg><span>بررسی وضعیت</span>';
    }
  });

  const redeemBtn = document.getElementById('redeemVoucherBtn');
  const voucherInput = document.getElementById('voucherCodeInput');
  if (redeemBtn && voucherInput) {
    redeemBtn.addEventListener('click', async () => {
      const code = voucherInput.value.trim();
      if (!code) {
        showToast(_wTr('لطفاً کد شارژ را وارد نمایید.', 'Please enter a voucher code.'), 'warning');
        return;
      }
      redeemBtn.disabled = true;
      redeemBtn.innerHTML = `<span>${_wTr('در حال بررسی...', 'Checking...')}</span>`;
      try {
        const res = await window.api.redeemVoucher(code);
        if (res.ok) {
          showToast(res.message || _wTr('کیف پول با موفقیت شارژ گردید!', 'Wallet credited successfully!'), 'success');
          voucherInput.value = '';
          const haptic = window.api?.haptic || window.hapticFeedback;
          if (haptic) haptic('success');
          if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
        } else {
          showToast(res.message || _wTr('کد شارژ نامعتبر است.', 'Invalid voucher code.'), 'error');
        }
      } catch (err) {
        showToast(_wTr('خطا در برقراری ارتباط با سرور.', 'Server connection error.'), 'error');
      } finally {
        redeemBtn.disabled = false;
        redeemBtn.innerHTML = `<span class="inline-flex items-center gap-1"><img src="/static/img/icons/zap.svg?v=fl2" class="ui-icon-img w-3.5 h-3.5 shrink-0" width="14" height="14" alt="" /><span>${_wTr('اعمال', 'Apply')}</span></span>`;
      }
    });
  }

  document.getElementById('tonConnectPayBtn')?.addEventListener('click', () => {
    if (!currentTopupInvoice?.pay_address) {
      showToast(_wTr('⚠️ ابتدا فاکتور پرداخت TON را ایجاد فرمایید.', '⚠️ Please create a TON invoice first.'));
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
        window.openExternalUrl ? window.openExternalUrl(tonUrl) : window.open(tonUrl, '_blank', 'noopener,noreferrer');
      }
    } else {
      window.openExternalUrl ? window.openExternalUrl(tonUrl) : window.open(tonUrl, '_blank', 'noopener,noreferrer');
    }
  });

  // TRX Gateway Listeners
  document.getElementById('generateTrxInvoiceBtn')?.addEventListener('click', async () => {
    const amt = parseInt(topupAmountInput?.value || '0', 10);
    if (!validateTopupAmount(amt)) return;
    const btn = document.getElementById('generateTrxInvoiceBtn');
    btn.disabled = true;
    btn.innerText = _wTr('در حال ایجاد فاکتور ترون...', 'Creating TRON invoice...');
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
        showToast(`❌ ${res.message || _wTr('خطا در ایجاد فاکتور ترون', 'Error creating TRON invoice')}`);
      }
    } catch (e) {
      showToast(_wTr('❌ خطا در برقراری ارتباط با سرور.', '❌ Server connection error.'));
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<span>🔴</span> ${_wTr('ایجاد فاکتور ترون (TRX)', 'Create TRON Invoice (TRX)')}`;
    }
  });

  const handleCopyTrxAddress = () => {
    const addr = document.getElementById('trxPayAddress')?.innerText?.trim();
    if (addr && addr !== '--') {
      copyToClipboard(addr, _wTr('📋 آدرس ولت ترون کپی شد.', '📋 TRON wallet address copied.'));
      hapticFeedback('success');
    }
  };
  document.getElementById('copyTrxAddressBtn')?.addEventListener('click', handleCopyTrxAddress);
  document.getElementById('trxPayAddress')?.addEventListener('click', handleCopyTrxAddress);

  document.getElementById('copyTrxAmountBtn')?.addEventListener('click', () => {
    const amt = currentTrxInvoice?.amount_trx;
    if (amt) {
      copyToClipboard(String(amt), _wTr('📋 مقدار TRX کپی شد.', '📋 TRX amount copied.'));
      hapticFeedback('success');
    }
  });

  document.getElementById('cancelTrxInvoiceBtn')?.addEventListener('click', async () => {
    if (currentTrxInvoice?.id && window.api?.cancelCryptoInvoice) {
      try { await window.api.cancelCryptoInvoice(currentTrxInvoice.id); } catch (e) {}
    }
    clearActiveTrxInvoice();
    updateTopupMutexUI();
    showToast(_wTr('فاکتور ترون لغو شد.', 'TRON invoice cancelled.'));
  });

  document.getElementById('submitTrxTxIdBtn')?.addEventListener('click', async () => {
    if (!currentTrxInvoice?.id) {
      showToast(_wTr('⚠️ ابتدا فاکتور ترون را ایجاد فرمایید.', '⚠️ Please create a TRON invoice first.'));
      return;
    }
    const txId = document.getElementById('trxTxIdInput')?.value?.trim();
    if (!txId) {
      showToast(_wTr('⚠️ لطفاً شناسه تراکنش (TxID) را وارد فرمایید.', '⚠️ Please enter the Transaction ID (TxID).'));
      return;
    }
    const btn = document.getElementById('submitTrxTxIdBtn');
    btn.disabled = true;
    btn.innerHTML = `<svg class="w-4 h-4 shrink-0 animate-spin" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg><span>${_wTr('در حال بررسی...', 'Checking...')}</span>`;
    try {
      const res = await window.api.verifyTrxInvoice(currentTrxInvoice.id, txId);
      if (res.ok) {
        showToast(_wTr('🎉 واریز TRX در شبکه تأیید شد و کیف پول شارژ گردید!', '🎉 TRX deposit verified and wallet credited!'));
        clearActiveTrxInvoice();
        closeModal('topupModal');
        hapticFeedback('success');
        if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
      } else {
        showToast(`❌ ${res.message || _wTr('تراکنش در شبکه ترون تأیید نشد', 'Transaction not confirmed on TRON network')}`);
      }
    } catch (e) {
      showToast(_wTr('❌ خطا در بررسی تراکنش.', '❌ Failed to verify transaction.'));
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg><span>${_wTr('بررسی وضعیت', 'Check Status')}</span>`;
    }
  });

  // POL Gateway Listeners
  document.getElementById('generatePolInvoiceBtn')?.addEventListener('click', async () => {
    const amt = parseInt(topupAmountInput?.value || '0', 10);
    if (!validateTopupAmount(amt)) return;
    const btn = document.getElementById('generatePolInvoiceBtn');
    btn.disabled = true;
    btn.innerText = _wTr('در حال ایجاد فاکتور پلیگان...', 'Creating Polygon invoice...');
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
        showToast(`❌ ${res.message || _wTr('خطا در ایجاد فاکتور پلیگان', 'Error creating Polygon invoice')}`);
      }
    } catch (e) {
      showToast(_wTr('❌ خطا در برقراری ارتباط با سرور.', '❌ Server connection error.'));
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<span>🟣</span> ${_wTr('ایجاد فاکتور پلیگان (POL)', 'Create Polygon Invoice (POL)')}`;
    }
  });

  const handleCopyPolAddress = () => {
    const addr = document.getElementById('polPayAddress')?.innerText?.trim();
    if (addr && addr !== '--') {
      copyToClipboard(addr, _wTr('📋 آدرس ولت پلیگان کپی شد.', '📋 Polygon wallet address copied.'));
      hapticFeedback('success');
    }
  };
  document.getElementById('copyPolAddressBtn')?.addEventListener('click', handleCopyPolAddress);
  document.getElementById('polPayAddress')?.addEventListener('click', handleCopyPolAddress);

  document.getElementById('copyPolAmountBtn')?.addEventListener('click', () => {
    const amt = currentPolInvoice?.amount_pol;
    if (amt) {
      copyToClipboard(String(amt), _wTr('📋 مقدار POL کپی شد.', '📋 POL amount copied.'));
      hapticFeedback('success');
    }
  });

  document.getElementById('cancelPolInvoiceBtn')?.addEventListener('click', async () => {
    if (currentPolInvoice?.id && window.api?.cancelCryptoInvoice) {
      try { await window.api.cancelCryptoInvoice(currentPolInvoice.id); } catch (e) {}
    }
    clearActivePolInvoice();
    updateTopupMutexUI();
    showToast(_wTr('فاکتور پلیگان لغو شد.', 'Polygon invoice cancelled.'));
  });

  document.getElementById('openMetaMaskBtn')?.addEventListener('click', async () => {
    if (!currentPolInvoice || !currentPolInvoice.pay_address) {
      showToast(_wTr('⚠️ ابتدا فاکتور پلیگان را ایجاد فرمایید.', '⚠️ Please create a Polygon invoice first.'));
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
      copyToClipboard(toAddress, _wTr(`📋 آدرس ولت کپی شد (${currentPolInvoice.amount_pol} POL)`, `📋 Wallet address copied (${currentPolInvoice.amount_pol} POL)`));
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
            showToast(_wTr('✅ تراکنش در متامسک ثبت شد! در حال تأیید خودکار...', '✅ Transaction submitted in MetaMask! Verifying...'));
            setTimeout(() => {
              document.getElementById('submitPolTxIdBtn')?.click();
            }, 1200);
            return;
          }
        }
      } catch (ethErr) {
        console.warn('MetaMask error:', ethErr);
        if (ethErr.code === 4001) {
          showToast(_wTr('تراکنش در متامسک لغو شد.', 'MetaMask transaction cancelled.'));
          return;
        }
      }
    }

    // Deep link fallback for mobile / TMA
    const deepLink = `https://metamask.app.link/send/${toAddress}?value=${weiHex}&chainId=137`;
    if (window.Telegram?.WebApp?.openLink) {
      window.Telegram.WebApp.openLink(deepLink);
    } else {
      window.openExternalUrl ? window.openExternalUrl(deepLink) : window.open(deepLink, '_blank', 'noopener,noreferrer');
    }
  });

  document.getElementById('submitPolTxIdBtn')?.addEventListener('click', async () => {
    if (!currentPolInvoice?.id) {
      showToast(_wTr('⚠️ ابتدا فاکتور پلیگان را ایجاد فرمایید.', '⚠️ Please create a Polygon invoice first.'));
      return;
    }
    const txId = document.getElementById('polTxIdInput')?.value?.trim();
    if (!txId) {
      showToast(_wTr('⚠️ لطفاً هش تراکنش (TxHash) را وارد فرمایید.', '⚠️ Please enter the transaction hash (TxHash).'));
      return;
    }
    const btn = document.getElementById('submitPolTxIdBtn');
    btn.disabled = true;
    btn.innerHTML = `<svg class="w-4 h-4 shrink-0 animate-spin" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg><span>${_wTr('در حال بررسی...', 'Checking...')}</span>`;
    try {
      const res = await window.api.verifyPolInvoice(currentPolInvoice.id, txId);
      if (res.ok) {
        showToast(_wTr('🎉 واریز POL در شبکه پلیگان تأیید شد و کیف پول شارژ گردید!', '🎉 POL deposit verified on Polygon and wallet credited!'));
        clearActivePolInvoice();
        closeModal('topupModal');
        hapticFeedback('success');
        if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
      } else {
        showToast(`❌ ${res.message || _wTr('تراکنش در شبکه پلیگان تأیید نشد', 'Transaction not confirmed on Polygon')}`);
      }
    } catch (e) {
      showToast(_wTr('❌ خطا در بررسی تراکنش.', '❌ Failed to verify transaction.'));
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg><span>${_wTr('بررسی وضعیت', 'Check Status')}</span>`;
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
window.unlockTopupPhoneVerificationUI = function () {
  _cardTopupGuardState.phoneLocked = false;
  if (window.storeSettings && typeof window.storeSettings === 'object') {
    window.storeSettings.is_phone_verified = true;
  }
  const cardPhoneWarning = document.getElementById('cardPhoneVerificationWarning');
  const cardDetailsBox = document.getElementById('topupCardDetailsBox');
  const cardUploadBtn = document.getElementById('uploadCardReceiptImageBtn');
  if (cardPhoneWarning) cardPhoneWarning.classList.add('hidden');
  if (cardDetailsBox) cardDetailsBox.classList.remove('hidden');
  if (cardUploadBtn) {
    cardUploadBtn.disabled = false;
    cardUploadBtn.classList.remove('opacity-40', 'cursor-not-allowed');
  }
  if (typeof window.updateCardTopupSubmitState === 'function') {
    window.updateCardTopupSubmitState();
  }
};
window.refreshTopupModalState = async function (options = { refresh: true }) {
  await loadTopupInfo(options);
  if (window.storeSettings?.card_auto_enabled && typeof checkActiveCardAutoInvoice === 'function') {
    await checkActiveCardAutoInvoice();
  }
  if (typeof window.updateCardTopupSubmitState === 'function') {
    window.updateCardTopupSubmitState();
  }
};
window.setupWalletListeners = setupWalletListeners;
