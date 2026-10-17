/**
 * RemnaStore Pro - Core DRY Utilities
 */

// Robust HTML escaping to prevent XSS injection
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
if (typeof window !== 'undefined') {
  window.escapeHtml = escapeHtml;
}

// Toast notification utility
function showToast(msg) {
  let toast = document.getElementById('appToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'appToast';
    toast.className = 'fixed top-12 left-1/2 transform -translate-x-1/2 z-50 bg-slate-900/95 text-white border border-slate-700/80 px-4 py-2.5 rounded-2xl shadow-2xl text-xs font-semibold text-center transition-all duration-300 opacity-0 pointer-events-none max-w-[90%]';
    toast.dir = 'rtl';
    document.body.appendChild(toast);
  }
  if (/<[a-z][\s\S]*>/i.test(msg)) {
    toast.innerHTML = msg;
  } else {
    toast.innerText = msg;
  }
  toast.classList.remove('opacity-0', '-translate-y-2');
  toast.classList.add('opacity-100', 'translate-y-0');
  setTimeout(() => {
    toast.classList.remove('opacity-100', 'translate-y-0');
    toast.classList.add('opacity-0', '-translate-y-2');
  }, 3000);
}

// Global Banner Notification Utility (for session expiry, timeouts, system notices)
function showBanner(msg, type = 'warning', options = {}) {
  const bannerId = options.id || 'appGlobalBanner';
  let banner = document.getElementById(bannerId);
  const container = document.getElementById('contentArea') || document.body;

  const bgBorderMap = {
    error: 'bg-rose-950/80 border-rose-500/50 text-rose-200',
    warning: 'bg-amber-950/80 border-amber-500/50 text-amber-200',
    info: 'bg-blue-950/80 border-blue-500/50 text-blue-200',
    success: 'bg-emerald-950/80 border-emerald-500/50 text-emerald-200',
  };
  const iconMap = {
    error: '🚫',
    warning: '⚠️',
    info: 'ℹ️',
    success: '✅',
  };

  const styleClasses = bgBorderMap[type] || bgBorderMap.warning;
  const icon = options.icon || iconMap[type] || '⚠️';

  if (!banner) {
    banner = document.createElement('div');
    banner.id = bannerId;
    if (container.firstChild) {
      container.insertBefore(banner, container.firstChild);
    } else {
      container.appendChild(banner);
    }
  }

  banner.className = `w-full rounded-2xl p-3 border backdrop-blur-md shadow-lg transition-all duration-300 text-xs flex items-center justify-between gap-2.5 mb-3.5 ${styleClasses}`;

  let actionBtnHtml = '';
  if (options.actionText) {
    actionBtnHtml = `<button type="button" class="banner-action-btn flex-shrink-0 px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 active:scale-95 text-white font-bold text-[11px] border border-white/20 transition cursor-pointer">${escapeHtml(options.actionText)}</button>`;
  }

  let closeBtnHtml = '';
  if (options.dismissible !== false && !options.actionText) {
    closeBtnHtml = `<button type="button" class="banner-close-btn flex-shrink-0 text-slate-400 hover:text-white p-1 text-sm bg-transparent border-0 cursor-pointer" title="بستن">✕</button>`;
  }

  banner.innerHTML = `
    <div class="flex items-center gap-2 min-w-0">
      <span class="text-base flex-shrink-0">${icon}</span>
      <span class="font-medium leading-relaxed break-words">${escapeHtml(msg)}</span>
    </div>
    <div class="flex items-center gap-1.5 flex-shrink-0">
      ${actionBtnHtml}
      ${closeBtnHtml}
    </div>
  `;

  if (options.actionText && typeof options.onAction === 'function') {
    const actBtn = banner.querySelector('.banner-action-btn');
    if (actBtn) {
      actBtn.onclick = (e) => {
        e.preventDefault();
        options.onAction();
      };
    }
  }

  const clsBtn = banner.querySelector('.banner-close-btn');
  if (clsBtn) {
    clsBtn.onclick = () => hideBanner(bannerId);
  }
}

function hideBanner(bannerId = 'appGlobalBanner') {
  const banner = document.getElementById(bannerId);
  if (banner) {
    banner.remove();
  }
}

if (typeof window !== 'undefined') {
  window.showToast = showToast;
  window.showBanner = showBanner;
  window.hideBanner = hideBanner;
}

// Telegram Haptic Feedback
function hapticFeedback(type = 'success') {
  if (window.Telegram?.WebApp?.HapticFeedback) {
    try {
      if (type === 'impact') {
        window.Telegram.WebApp.HapticFeedback.impactOccurred('medium');
      } else if (type === 'light') {
        window.Telegram.WebApp.HapticFeedback.impactOccurred('light');
      } else if (type === 'selection') {
        window.Telegram.WebApp.HapticFeedback.selectionChanged();
      } else {
        window.Telegram.WebApp.HapticFeedback.notificationOccurred(type);
      }
    } catch (e) {}
  }
}
if (typeof window !== 'undefined') {
  window.hapticFeedback = hapticFeedback;
}

// Robust clipboard copying
function fallbackCopy(text) {
  const el = document.createElement('textarea');
  el.value = text;
  el.setAttribute('readonly', '');
  el.style.position = 'fixed';
  el.style.left = '-9999px';
  document.body.appendChild(el);
  el.focus();
  el.select();
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch (e) {}
  document.body.removeChild(el);
  return ok;
}

async function copyToClipboard(text, successToast = null) {
  if (!text) return false;
  let copied = false;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
    } catch (e) {
      copied = fallbackCopy(text);
    }
  } else {
    copied = fallbackCopy(text);
  }

  if (copied) {
    hapticFeedback('success');
    if (successToast) {
      showToast(successToast);
    }
  } else {
    showToast('خطا در کپی خودکار؛ لطفاً متن را دستی انتخاب و کپی فرمایید.');
  }
  return copied;
}

// Format seconds into HH:MM:SS
function formatCountdown(sec) {
  if (sec <= 0) return '00:00:00';
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// Modal open/close helpers
function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('hidden');
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('hidden');
}

// DRY Accordion setup helper
function setupAccordion(btnId, bodyId, chevronId) {
  const btn = document.getElementById(btnId);
  const body = document.getElementById(bodyId);
  const chevron = document.getElementById(chevronId);
  if (btn && body && chevron) {
    btn.addEventListener('click', () => {
      body.classList.toggle('hidden');
      chevron.style.transform = body.classList.contains('hidden') ? 'rotate(0deg)' : 'rotate(-90deg)';
    });
  }
}

// Gregorian to Jalali converter
function gregorianToJalali(gy, gm, gd) {
  const g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  let jy = (gy <= 1600) ? 0 : 979;
  gy -= (gy <= 1600) ? 621 : 1600;
  const gy2 = (gm > 2) ? (gy + 1) : gy;
  let days = (365 * gy) + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100) + Math.floor((gy2 + 399) / 400) - 80 + gd + g_d_m[gm - 1];
  jy += 33 * Math.floor(days / 12053);
  days %= 12053;
  jy += 4 * Math.floor(days / 1461);
  days %= 1461;
  if (days > 365) {
    jy += Math.floor((days - 1) / 365);
    days = (days - 1) % 365;
  }
  const jm = (days < 186) ? 1 + Math.floor(days / 31) : 7 + Math.floor((days - 186) / 30);
  const jd = 1 + ((days < 186) ? (days % 31) : ((days - 186) % 30));
  return [jy, jm, jd];
}

function formatDateToJalali(dateStr) {
  if (!dateStr) return '';
  try {
    const parts = dateStr.slice(0, 10).split('-');
    if (parts.length === 3) {
      const [y, m, d] = parts.map(Number);
      const [jy, jm, jd] = gregorianToJalali(y, m, d);
      return `${jy}/${String(jm).padStart(2, '0')}/${String(jd).padStart(2, '0')}`;
    }
  } catch (e) {}
  return dateStr;
}

// Convert Persian and Arabic digits to ASCII English digits
function toEnglishDigits(str) {
  if (str === null || str === undefined) return '';
  const fa = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];
  const ar = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
  let res = String(str);
  for (let i = 0; i < 10; i++) {
    res = res.replaceAll(fa[i], String(i)).replaceAll(ar[i], String(i));
  }
  return res;
}

// Convert ASCII English digits to Persian digits
function toPersianDigits(str) {
  if (str === null || str === undefined) return '';
  const fa = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];
  return String(str).replace(/[0-9]/g, w => fa[Number(w)]);
}

function formatPrice(amt) {
  if (amt == null || isNaN(amt)) return '0';
  return Number(amt).toLocaleString('en-US');
}

// Plan Title Formatter (places icon on the visual left of the plan name)
function formatPlanTitle(name, options = {}) {
  if (!name) return options.plainText ? '💎 پلن' : '';
  const emojiRegex = /[\p{Extended_Pictographic}\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu;
  const str = String(name).trim();
  const emojis = str.match(emojiRegex);
  const cleanText = str.replace(emojiRegex, '').trim();
  const emojiStr = (emojis && emojis.length > 0) ? emojis.join('') : (options.defaultIcon || '');

  if (options.plainText) {
    const icon = emojiStr || '💎';
    return cleanText ? `${icon} ${cleanText}` : icon;
  }

  if (!emojiStr) {
    return `<span class="inline-block font-bold">${escapeHtml(name)}</span>`;
  }
  if (!cleanText) {
    return `<span class="inline-block text-base">${emojiStr}</span>`;
  }
  return `<span class="inline-flex items-center gap-1.5" dir="ltr"><span class="shrink-0 text-base">${emojiStr}</span><span class="font-bold">${escapeHtml(cleanText)}</span></span>`;
}

function buildRefLink(botUsername, userId) {
  const uid = userId != null ? String(userId).trim() : '';
  const cleanUser = botUsername ? String(botUsername).replace(/^@/, '').trim() : '';
  return cleanUser ? `https://t.me/${cleanUser}?start=ref_${uid}` : `https://t.me/?start=ref_${uid}`;
}

function bindModal(modalId, closeBtnId) {
  const modalEl = typeof modalId === 'string' ? document.getElementById(modalId) : modalId;
  const closeBtnEl = typeof closeBtnId === 'string' ? document.getElementById(closeBtnId) : closeBtnId;
  if (!modalEl) return { open: () => {}, close: () => {} };
  const open = () => modalEl.classList.remove('hidden');
  const close = () => modalEl.classList.add('hidden');
  if (closeBtnEl) closeBtnEl.addEventListener('click', close);
  modalEl.addEventListener('click', (e) => {
    if (e.target === modalEl) close();
  });
  return { open, close };
}

/**
 * Single Source of Truth (SSOT) Traffic Parser & Formatter with BiDi Isolation.
 */
function fmtTrafficValue(val, isBytes = false) {
  if (val === null || val === undefined || val === '') return null;
  let num = 0;
  let unit = 'GB';

  if (typeof val === 'string') {
    const trimmed = val.trim();
    if (trimmed.startsWith('--') || trimmed === '—' || trimmed === '-') return null;
    const match = trimmed.match(/^([\d.,]+)\s*([A-Za-z]+)?$/);
    if (match) {
      num = parseFloat(match[1].replace(/,/g, '')) || 0;
      unit = (match[2] || 'GB').toUpperCase();
    } else {
      num = parseFloat(trimmed.replace(/,/g, '')) || 0;
    }
  } else {
    num = Number(val);
    if (isNaN(num)) return null;

    if (isBytes) {
      const TB_BYTES = 1099511627776; // 1024^4
      const GB_BYTES = 1073741824;    // 1024^3
      const MB_BYTES = 1048576;       // 1024^2

      if (num >= TB_BYTES) {
        num = num / TB_BYTES;
        unit = 'TB';
      } else if (num >= GB_BYTES) {
        num = num / GB_BYTES;
        unit = 'GB';
      } else if (num >= MB_BYTES || num > 0) {
        num = num / MB_BYTES;
        unit = 'MB';
      } else {
        num = 0;
        unit = 'GB';
      }
    } else {
      // Value in Gigabytes
      if (num >= 1024) {
        num = num / 1024;
        unit = 'TB';
      } else if (num > 0 && num < 0.1) {
        num = num * 1024;
        unit = 'MB';
      } else {
        unit = 'GB';
      }
    }
  }
  return { num, unit };
}

function fmtTraffic(val, options = {}) {
  const {
    isBytes = false,
    persianDigits = false,
    persianUnit = false,
    html = true,
    placeholder = '-- GB',
    precision = 2
  } = options;

  const parsed = fmtTrafficValue(val, isBytes);
  if (!parsed) {
    return html ? `<span class="num-bidi">${escapeHtml(placeholder)}</span>` : placeholder;
  }

  let numStr = parsed.num.toFixed(precision);
  if (numStr.includes('.')) {
    numStr = numStr.replace(/\.?0+$/, '');
  }

  let displayUnit = parsed.unit;
  if (persianUnit) {
    if (displayUnit === 'TB') displayUnit = 'ترابایت';
    else if (displayUnit === 'GB') displayUnit = 'گیگابایت';
    else if (displayUnit === 'MB') displayUnit = 'مگابایت';
    else if (displayUnit === 'KB') displayUnit = 'کیلوبایت';
  }

  const finalDigits = persianDigits && typeof toPersianDigits === 'function' ? toPersianDigits(numStr) : numStr;
  const formatted = `${finalDigits} ${displayUnit}`;
  return html ? `<span class="num-bidi">${escapeHtml(formatted)}</span>` : formatted;
}

if (typeof window !== 'undefined') {
  window.toEnglishDigits = toEnglishDigits;
  window.toPersianDigits = toPersianDigits;
  window.formatPrice = formatPrice;
  window.formatPlanTitle = formatPlanTitle;
  window.buildRefLink = buildRefLink;
  window.bindModal = bindModal;
  window.fmtTrafficValue = fmtTrafficValue;
  window.fmtTraffic = fmtTraffic;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    escapeHtml,
    toEnglishDigits,
    toPersianDigits,
    formatPrice,
    formatPlanTitle,
    fmtTrafficValue,
    fmtTraffic,
  };
}


