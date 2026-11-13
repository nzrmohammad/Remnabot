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
let _appToastTimer = null;
function showToast(msg, typeOrDuration = 3200, duration = 3200) {
  let toast = document.getElementById('appToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'appToast';
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'assertive');
    toast.className = 'fixed top-12 left-1/2 transform -translate-x-1/2 z-50 modal-card t-main px-4 py-2.5 rounded-2xl shadow-2xl text-xs font-semibold text-center transition-all duration-300 opacity-0 pointer-events-none max-w-[90%] whitespace-pre-line leading-relaxed';
    toast.dir = 'rtl';
    document.body.appendChild(toast);
  }
  if (_appToastTimer) {
    clearTimeout(_appToastTimer);
    _appToastTimer = null;
  }
  let delay = 3200;
  if (typeof typeOrDuration === 'number' && !isNaN(typeOrDuration) && typeOrDuration > 0) {
    delay = typeOrDuration;
  } else if (typeof duration === 'number' && !isNaN(duration) && duration > 0) {
    delay = duration;
  }
  toast.textContent = String(msg || '');
  toast.classList.remove('opacity-0', '-translate-y-2');
  toast.classList.add('opacity-100', 'translate-y-0');
  _appToastTimer = setTimeout(() => {
    toast.classList.remove('opacity-100', 'translate-y-0');
    toast.classList.add('opacity-0', '-translate-y-2');
    _appToastTimer = null;
  }, delay);
}

// Global Banner Notification Utility (for session expiry, timeouts, system notices)
function showBanner(msg, type = 'warning', options = {}) {
  const bannerId = options.id || 'appGlobalBanner';
  let banner = document.getElementById(bannerId);
  const container = document.getElementById('contentArea') || document.body;

  const bgBorderMap = {
    error: 's-danger-soft',
    warning: 's-warn-soft',
    info: 's-info-soft',
    success: 's-success-soft',
  };
  const iconMap = {
    error: uiIcon('ban', 'w-4 h-4'),
    warning: uiIcon('zap', 'w-4 h-4'),
    info: uiIcon('sparkles', 'w-4 h-4'),
    success: uiIcon('shield', 'w-4 h-4'),
  };

  const styleClasses = bgBorderMap[type] || bgBorderMap.warning;
  const icon = options.icon || iconMap[type] || uiIcon('zap', 'w-4 h-4');

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
    actionBtnHtml = `<button type="button" class="banner-action-btn btn-secondary flex-shrink-0 px-3 py-1.5 rounded-xl active:scale-95 font-bold text-[11px] transition cursor-pointer">${escapeHtml(options.actionText)}</button>`;
  }

  let closeBtnHtml = '';
  if (options.dismissible !== false && !options.actionText) {
    closeBtnHtml = `<button type="button" class="banner-close-btn flex-shrink-0 t-muted hover:t-main p-1 text-sm bg-transparent border-0 cursor-pointer" title="بستن">✕</button>`;
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

// Global delegated haptic feedback on switch toggles
if (typeof document !== 'undefined') {
  document.addEventListener('change', (e) => {
    if (e.target && e.target.classList && e.target.classList.contains('switch-checkbox')) {
      hapticFeedback('light');
    }
  });
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

// Modal open/close helpers with background scroll lock
function openModal(id) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.remove('hidden');
    document.body.classList.add('modal-open');
  }
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('hidden');
  const anyOpen = document.querySelector('[id$="Modal"]:not(.hidden)');
  if (!anyOpen) {
    document.body.classList.remove('modal-open');
  }
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

// Legacy alias retained for callers: returns ASCII English digits cleanly (no Persian digits)
function toPersianDigits(str) {
  return toEnglishDigits(str);
}

function formatPrice(amt) {
  if (amt == null || isNaN(amt)) return '0';
  return Number(amt).toLocaleString('en-US');
}

function formatNumber(num) {
  if (num === null || num === undefined || isNaN(Number(num))) return '0';
  const n = Number(num);
  const rounded = Number.isInteger(n) ? n.toString() : (Math.round(n * 100) / 100).toString();
  const [intPart, decPart] = rounded.split('.');
  const formattedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return decPart !== undefined ? `${formattedInt}.${decPart}` : formattedInt;
}

const UI_ICON_FILES = {
  dashboard: 'dashboard',
  reports: 'reports',
  shop: 'shop',
  wallet: 'wallet',
  profile: 'profile',
  users: 'users',
  plans: 'plans',
  nodes: 'nodes',
  finance: 'finance',
  settings: 'settings',
  chat: 'chat',
  sync: 'sync',
  sun: 'sun',
  moon: 'moon',
  award: 'award',
  medal_gold: 'medal-gold',
  medal_silver: 'medal-silver',
  medal_bronze: 'medal-bronze',
  crown: 'crown',
  diamond: 'diamond',
  star: 'star',
  flame: 'flame',
  rocket: 'rocket',
  zap: 'zap',
  clock: 'clock',
  coins: 'coins',
  shield: 'shield',
  lock_shield: 'lock-shield',
  gamepad: 'gamepad',
  play: 'play',
  route: 'route',
  layers: 'layers',
  package: 'package',
  sparkles: 'sparkles',
  ticket: 'ticket',
  gift: 'gift',
  wheel: 'wheel',
  phone: 'phone',
  globe: 'globe',
  edit: 'edit',
  copy: 'copy',
  pause: 'pause',
  play_btn: 'play-btn',
  trash: 'trash',
  trophy: 'trophy',
  credit_card: 'credit-card',
  inbox: 'inbox',
  ban: 'ban',
  recycle: 'recycle',
  cart: 'cart',
  database: 'database',
  lightning: 'lightning',
  calendar: 'calendar',
  check: 'check',
  warning: 'warning',
  alert: 'warning',
  info: 'lightbulb',
  lightbulb: 'lightbulb',
  plus: 'plus',
  receipt: 'receipt',
  link: 'link',
  support: 'support',
  faq: 'faq',
  tutorial: 'tutorial',
  cross: 'cross',
  cake: 'cake',
  birthday: 'cake',
  key: 'key',
  bell: 'bell',
  desktop: 'desktop',
  antenna: 'antenna',
  signal: 'signal',
  sunrise: 'sunrise',
  sunset: 'sunset',
  wifi: 'wifi',
  search: 'search',
};

function uiIcon(name, className = 'w-4 h-4') {
  const file = UI_ICON_FILES[name] || name || 'sparkles';
  return `<img src="/static/img/icons/${file}.svg?v=ri7" class="ui-icon ui-icon-img shrink-0 ${className}" alt="" aria-hidden="true" loading="eager" />`;
}

const EMOJI_TO_UI_ICON = {
  // Medals kept as native vibrant emojis per user preference
  '💎': 'diamond',
  '👑': 'crown',
  '🏆': 'trophy',
  '🎖️': 'award',
  '🎖': 'award',
  '⭐': 'star',
  '⭐️': 'star',
  '🌟': 'sparkles',
  '✨': 'sparkles',
  '🎉': 'sparkles',
  '🔥': 'flame',
  '📅': 'calendar',
  '🗓': 'calendar',
  '🗓️': 'calendar',
  '📆': 'calendar',
  '🌙': 'moon',
  '☀️': 'sun',
  '☀': 'sun',
  '🌅': 'sunrise',
  '🌆': 'sunset',
  '🎫': 'ticket',
  '🎟️': 'ticket',
  '🎟': 'ticket',
  '⚙️': 'settings',
  '⚙': 'settings',
  '🛡️': 'shield',
  '🛡': 'shield',
  '🔐': 'lock_shield',
  '🔒': 'lock_shield',
  '🚫': 'ban',
  '⛔️': 'ban',
  '⛔': 'ban',
  '🎧': 'support',
  '🎂': 'cake',
  '💳': 'credit_card',
  '💰': 'wallet',
  '🪙': 'coins',
  '🧾': 'receipt',
  '📊': 'reports',
  '⚡': 'zap',
  '⚡️': 'zap',
  '⏳': 'clock',
  '🕒': 'clock',
  '⏱': 'clock',
  '⏱️': 'clock',
  '⏰': 'clock',
  '📦': 'package',
  '🎁': 'gift',
  '🎡': 'wheel',
  '👥': 'users',
  '👤': 'profile',
  '📱': 'phone',
  '📞': 'phone',
  '💬': 'chat',
  '📨': 'chat',
  '🌐': 'globe',
  '🚀': 'rocket',
  '🔍': 'search',
  '🔎': 'search',
  '💡': 'lightbulb',
  '🔔': 'bell',
  '🔄': 'sync',
  '📋': 'copy',
  '🔗': 'link',
  '🔑': 'key',
  '📡': 'antenna',
  '📶': 'signal',
  '🖥': 'desktop',
  '🖥️': 'desktop',
  '💻': 'desktop',
  '🎮': 'gamepad',
  '🧹': 'trash',
  '🗑️': 'trash',
  '🗑': 'trash',
  '✏️': 'edit',
  '✏': 'edit',
  '➕': 'plus',
  '✅': 'check',
  '✓': 'check',
  '⚠️': 'warning',
  '⚠': 'warning',
  '❌': 'cross',
  '✕': 'cross',
  '🛒': 'cart',
};

function uiEmojiIcon(emojiOrKey, className = 'w-4 h-4') {
  const raw = String(emojiOrKey || '').trim();
  const key = EMOJI_TO_UI_ICON[raw] || (UI_ICON_FILES[raw] ? raw : null);
  if (key) return uiIcon(key, className);
  return `<span aria-hidden="true">${escapeHtml(raw)}</span>`;
}

function getFlagEmoji(code) {
  if (!code || code.length !== 2) return '🌐';
  const c = code.toUpperCase();
  const offset = 127397;
  return String.fromCodePoint(c.charCodeAt(0) + offset, c.charCodeAt(1) + offset);
}

function getCountryCodeFromEmoji(emoji) {
  if (!emoji || typeof emoji !== 'string') return '';
  const chars = [...emoji.trim()];
  if (chars.length === 2) {
    const c1 = chars[0].codePointAt(0) - 127397;
    const c2 = chars[1].codePointAt(0) - 127397;
    if (c1 >= 65 && c1 <= 90 && c2 >= 65 && c2 <= 90) {
      return String.fromCharCode(c1, c2).toUpperCase();
    }
  }
  return '';
}

function renderFlagHtml(countryCodeOrEmoji, className = 'w-4 h-3 inline-block rounded-xs shadow-xs object-cover align-middle') {
  if (!countryCodeOrEmoji) return '<span class="inline-block">🌐</span>';
  const str = String(countryCodeOrEmoji).trim();
  if (str === '🌐' || str === '🖥️') return `<span class="inline-block">${str}</span>`;
  let cc = '';
  if (str.length === 2 && /^[a-zA-Z]{2}$/.test(str)) {
    cc = str.toUpperCase();
  } else {
    cc = getCountryCodeFromEmoji(str);
  }
  if (cc && cc.length === 2) {
    const code = cc.toLowerCase();
    const fallback = getFlagEmoji(cc);
    return `<img src="/static/img/flags/${code}.svg" class="${className}" alt="${cc}" title="${cc}" onerror="this.outerHTML='<span class=\'inline-block\'>${fallback}</span>'" loading="lazy" />`;
  }
  return `<span class="inline-block">${escapeHtml(str)}</span>`;
}


function formatSpeed(bytesPerSec) {
  const bytes = Number(bytesPerSec || 0);
  if (!bytes || bytes <= 0) return '0 B/s';
  const units = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
  let i = 0;
  let val = bytes;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(val >= 10 ? 1 : 2)} ${units[i]}`;
}

function formatChatTimestamp(m) {
  if (!m) return '';
  if (m.timestamp) {
    const tsMs = m.timestamp > 1e11 ? m.timestamp : m.timestamp * 1000;
    const d = new Date(tsMs);
    if (!isNaN(d.getTime())) {
      return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
    }
  }
  if (m.created_at) {
    if (typeof m.created_at === 'string' && m.created_at.includes('T')) {
      const d = new Date(m.created_at);
      if (!isNaN(d.getTime())) {
        return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
      }
    }
    return m.created_at;
  }
  return '';
}

function dismissSplash() {
  const splash = document.getElementById('splashScreen');
  const splashBar = document.getElementById('splashBar');
  if (!splash || splash.classList.contains('hidden')) return;

  if (splashBar) splashBar.style.width = '100%';
  setTimeout(() => {
    splash.style.opacity = '0';
    splash.style.pointerEvents = 'none';
    setTimeout(() => {
      splash.classList.add('hidden');
    }, 350);
  }, 250);
}


// Plan Title Formatter (places icon on the visual left of the plan name)
function formatPlanTitle(name, options = {}) {
  if (!name) return options.plainText ? '💎 پلن' : '';
  const emojiRegex = /[\p{Extended_Pictographic}\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu;
  const str = String(name).trim();
  const emojis = str.match(emojiRegex);
  const cleanText = str.replace(emojiRegex, '').trim();
  let emojiStr = (emojis && emojis.length > 0) ? emojis.join('') : (options.defaultIcon || '');

  if (!emojiStr) {
    const lowerName = str.toLowerCase();
    if (lowerName.includes('طلایی') || lowerName.includes('gold')) emojiStr = '🥇';
    else if (lowerName.includes('نقره') || lowerName.includes('silver')) emojiStr = '🥈';
    else if (lowerName.includes('برنز') || lowerName.includes('bronze')) emojiStr = '🥉';
    else if (lowerName.includes('الماس') || lowerName.includes('diamond')) emojiStr = '💎';
    else if (lowerName.includes('ویژه') || lowerName.includes('vip')) emojiStr = '👑';
  }

  if (options.plainText) {
    const icon = emojiStr || '💎';
    return cleanText ? `${icon} ${cleanText}` : icon;
  }

  if (!emojiStr) {
    return `<bdi dir="ltr" class="inline-block font-bold select-all">${escapeHtml(name)}</bdi>`;
  }
  if (!cleanText) {
    return `<span class="inline-block text-base">${emojiStr}</span>`;
  }
  return `<span class="inline-flex items-center gap-1.5"><span class="shrink-0 text-base">${emojiStr}</span><bdi dir="ltr" class="font-bold select-all">${escapeHtml(cleanText)}</bdi></span>`;
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

  const onKeyDown = (e) => {
    if (e.key === 'Escape' || e.key === 'Esc') {
      close();
    }
  };

  const open = () => {
    modalEl.classList.remove('hidden');
    document.addEventListener('keydown', onKeyDown);
    const focusable = modalEl.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    if (focusable) {
      setTimeout(() => focusable.focus(), 50);
    }
  };

  const close = () => {
    modalEl.classList.add('hidden');
    document.removeEventListener('keydown', onKeyDown);
  };

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
    // Strip BiDi isolation/control marks server formatters may embed (LRI/PDI/LRM/RLM etc.)
    const trimmed = val.trim().replace(/[\u200E\u200F\u202A-\u202E\u2066-\u2069]/g, '');
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

  const finalDigits = numStr;
  const formatted = `${finalDigits} ${displayUnit}`;
  if (html) {
    return `<span class="num-bidi">${escapeHtml(formatted)}</span>`;
  }
  if (options.isolate) {
    return `\u2066${formatted}\u2069`;
  }
  return formatted;
}

function getDonutPalette(isLight = false) {
  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    try {
      const s = getComputedStyle(document.documentElement);
      const vars = [1, 2, 3, 4, 5, 6].map(i => s.getPropertyValue(`--chart-${i}`)?.trim());
      if (vars.every(Boolean)) return vars;
    } catch (e) {}
  }
  return isLight
    ? ['#0284c7', '#7c3aed', '#be123c', '#b45309', '#047857', '#4338ca']
    : ['#38bdf8', '#a78bfa', '#fb7185', '#fbbf24', '#34d399', '#818cf8'];
}

function getChartThemeTokens(isLight = false) {
  const defaultTooltip = {
    bg: isLight ? '#ffffff' : '#111a2e',
    title: isLight ? '#0f172a' : '#e2e8f0',
    body: isLight ? '#0369a1' : '#38bdf8',
    border: isLight ? '#cbd5e1' : '#334155',
  };

  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    try {
      const s = getComputedStyle(document.documentElement);
      const getVar = name => s.getPropertyValue(name)?.trim() || '';
      const success = getVar('--c-success');
      const accent = getVar('--c-accent');
      const warn = getVar('--c-warn');
      const textMain = getVar('--text-main');
      const textMuted = getVar('--text-muted');
      const chartGrid = getVar('--chart-grid');
      const chartTick = getVar('--chart-tick');
      const frameBg = getVar('--frame-bg');
      const tooltip = {
        bg: getVar('--chart-tooltip-bg') || defaultTooltip.bg,
        title: getVar('--chart-tooltip-text') || textMain || defaultTooltip.title,
        body: accent || defaultTooltip.body,
        border: getVar('--chart-tooltip-border') || defaultTooltip.border,
      };
      if (success && accent && warn) {
        return {
          success,
          accent,
          warn,
          grid: chartGrid || (isLight ? 'rgba(148, 163, 184, 0.28)' : 'rgba(148, 163, 184, 0.14)'),
          tick: chartTick || textMuted || (isLight ? '#475569' : '#94a3b8'),
          legend: textMain || (isLight ? '#0f172a' : '#e2e8f0'),
          pointBorder: isLight ? '#ffffff' : (frameBg || '#111a2e'),
          tooltip,
          tooltipBg: tooltip.bg,
          tooltipTitle: tooltip.title,
          tooltipBody: tooltip.body,
          tooltipBorder: tooltip.border,
        };
      }
    } catch (e) {}
  }
  const tooltip = defaultTooltip;
  const tooltipBg = tooltip.bg;
  const tooltipTitle = tooltip.title;
  const tooltipBody = tooltip.body;
  const tooltipBorder = tooltip.border;
  return isLight
    ? {
        success: '#047857',
        accent: '#0369a1',
        warn: '#b45309',
        grid: 'rgba(148, 163, 184, 0.28)',
        tick: '#475569',
        legend: '#0f172a',
        pointBorder: '#ffffff',
        tooltip,
        tooltipBg,
        tooltipTitle,
        tooltipBody,
        tooltipBorder,
      }
    : {
        success: '#34d399',
        accent: '#38bdf8',
        warn: '#fbbf24',
        grid: 'rgba(148, 163, 184, 0.14)',
        tick: '#94a3b8',
        legend: '#e2e8f0',
        pointBorder: '#111a2e',
        tooltip,
        tooltipBg,
        tooltipTitle,
        tooltipBody,
        tooltipBorder,
      };
}

function fmtMoney(amount, currency = 'تومان') {
  if (amount == null || isNaN(amount)) return `0 ${currency}`;
  return `${formatPrice(amount)} ${currency}`;
}

function fmtCompact(val) {
  const num = typeof val === 'number' ? val : parseFloat(val) || 0;
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(0)}K`;
  return String(num);
}

function formatDeviceDate(isoStr) {
  if (!isoStr) return '';
  try {
    const dateObj = new Date(isoStr);
    if (!isNaN(dateObj.getTime())) {
      const dateFa = dateObj.toLocaleDateString('fa-IR');
      const timeFa = dateObj.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' });
      return `${toEnglishDigits(timeFa)} - ${toEnglishDigits(dateFa)}`;
    }
  } catch (e) {}
  return String(isoStr);
}

function parseDeviceMeta(d = {}) {
  const rawPlatform = String(d.platform || d.os || '')
    .replace(/\b(windows\s+1[01])\s+10\.0(?:\.\d+)*\b/gi, '$1')
    .trim();
  let rawOsVer = String(d.osVersion || d.platformVersion || '').trim();
  const ua = String(d.userAgent || d.user_agent || '').trim();

  if (rawPlatform && rawOsVer) {
    const pLow = rawPlatform.toLowerCase();
    const hasVerInPlatform = /\d/.test(rawPlatform);
    const majorVer = rawOsVer.split('.')[0];
    const majorAlreadyInPlatform = Boolean(
      majorVer && new RegExp(`(?:^|\\D)${majorVer.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?:$|\\D)`).test(rawPlatform)
    );
    if (hasVerInPlatform && ((pLow.includes('windows') && /^10(?:\.0+)?(?:\.\d+)?$/i.test(rawOsVer)) || majorAlreadyInPlatform)) {
      rawOsVer = '';
    } else if (pLow.includes('windows') && /^10\.0(?:\.0+)?$/i.test(rawOsVer)) {
      rawOsVer = '10';
    }
  }

  let resolvedOs = [rawPlatform, rawOsVer].filter(Boolean).join(' ').trim();
  if (!resolvedOs && ua) {
    const uaLow = ua.toLowerCase();
    if (uaLow.includes('android')) resolvedOs = 'Android';
    else if (uaLow.includes('iphone') || uaLow.includes('ipad') || uaLow.includes('ios')) resolvedOs = 'iOS';
    else if (uaLow.includes('windows')) resolvedOs = 'Windows';
    else if (uaLow.includes('mac os') || uaLow.includes('macos') || uaLow.includes('darwin')) resolvedOs = 'macOS';
    else if (uaLow.includes('linux')) resolvedOs = 'Linux';
  }

  const pCheck = (rawPlatform || resolvedOs || ua).toLowerCase();
  let icon = '📱';
  if (pCheck.includes('android')) icon = '🤖';
  else if (pCheck.includes('ios') || pCheck.includes('iphone') || pCheck.includes('ipad') || pCheck.includes('apple')) icon = '🍏';
  else if (pCheck.includes('windows')) icon = '💻';
  else if (pCheck.includes('mac') || pCheck.includes('darwin')) icon = '🍏';
  else if (pCheck.includes('linux')) icon = '🐧';

  const model = d.deviceModel || d.model || d.brand || rawPlatform || 'دستگاه متصل';
  const ip = d.requestIp || d.ip || d.lastIp || d.clientIp || '—';
  const hwid = d.hwid || d.id || '';

  let cleanUa = ua;
  if (ua) {
    const clients = [
      'v2rayNG', 'PattNG', 'PattN', 'Zedsecure', 'ZedSecure', 'Happ', 'Hiddify', 'Streisand',
      'V2Box', 'Incy', 'NekoBox', 'ClashMeta', 'Clash', 'Sing-box', 'sing-box',
      'Shadowrocket', 'Quantumult', 'Surge', 'Loon', 'Foxray', 'Karing', 'Wings',
      'WireGuard', 'Outline'
    ];
    let matched = false;
    for (const c of clients) {
      const regex = new RegExp(`(${c})[/\\s]?([0-9]+(?:\\.[0-9]+)*)?`, 'i');
      const m = ua.match(regex);
      if (m) {
        cleanUa = m[2] ? `${m[1]} ${m[2]}` : m[1];
        matched = true;
        break;
      }
    }
    if (!matched) {
      cleanUa = ua.replace(/\s*\([^)]*\)/g, '').trim().split(/[\s;]/)[0] || ua;
      cleanUa = cleanUa.replace('/', ' ').trim();
    }
  }

  const addedRaw = d.createdAt || d.created_at || d.addedAt;
  const updatedRaw = d.updatedAt || d.updated_at || d.lastSeen || d.lastActivity;
  return {
    icon,
    model,
    ip,
    hwid,
    ua,
    cleanUa,
    resolvedOs,
    addedDate: formatDeviceDate(addedRaw),
    updatedDate: formatDeviceDate(updatedRaw),
  };
}

if (typeof window !== 'undefined') {
  window.uiIcon = uiIcon;
  window.uiEmojiIcon = uiEmojiIcon;
  window.renderFlagHtml = renderFlagHtml;
  window.getCountryCodeFromEmoji = getCountryCodeFromEmoji;
  window.toEnglishDigits = toEnglishDigits;
  window.toPersianDigits = toPersianDigits;
  window.formatPrice = formatPrice;
  window.formatNumber = formatNumber;
  window.getFlagEmoji = getFlagEmoji;
  window.formatSpeed = formatSpeed;
  window.formatChatTimestamp = formatChatTimestamp;
  window.dismissSplash = dismissSplash;
  window.formatDateToJalali = formatDateToJalali;
  window.formatPlanTitle = formatPlanTitle;
  window.buildRefLink = buildRefLink;
  window.bindModal = bindModal;
  window.fmtTrafficValue = fmtTrafficValue;
  window.fmtTraffic = fmtTraffic;
  window.fmtMoney = fmtMoney;
  window.fmtCompact = fmtCompact;
  window.formatDeviceDate = formatDeviceDate;
  window.parseDeviceMeta = parseDeviceMeta;
  window.getDonutPalette = getDonutPalette;
  window.getChartThemeTokens = getChartThemeTokens;

  // Global keyboard accessibility: Enter/Space on [role="button"] & Escape to close open dialog
  if (typeof document !== 'undefined' && !window.__remnaA11yBound) {
    window.__remnaA11yBound = true;
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const openModals = Array.from(document.querySelectorAll('[role="dialog"][aria-modal="true"]:not(.hidden)'));
        const topModal = openModals[openModals.length - 1];
        if (!topModal) return;
        const closeBtn = topModal.querySelector('.modal-close-btn');
        if (closeBtn && typeof closeBtn.click === 'function') {
          closeBtn.click();
        } else {
          topModal.click();
        }
        return;
      }

      if (e.key === 'Enter' || e.key === ' ') {
        const target = e.target;
        if (!target || typeof target.closest !== 'function') return;
        const tag = target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || tag === 'BUTTON' || tag === 'A') return;
        const roleBtn = target.closest('[role="button"][tabindex="0"]');
        if (roleBtn && target === roleBtn) {
          e.preventDefault();
          roleBtn.click();
        }
      }
    });
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    uiIcon,
    renderFlagHtml,
    getCountryCodeFromEmoji,
    escapeHtml,
    toEnglishDigits,
    toPersianDigits,
    formatPrice,
    formatNumber,
    getFlagEmoji,
    formatSpeed,
    formatChatTimestamp,
    formatDateToJalali,
    formatPlanTitle,
    fmtTrafficValue,
    fmtTraffic,
    fmtMoney,
    fmtCompact,
    formatDeviceDate,
    parseDeviceMeta,
    getDonutPalette,
    getChartThemeTokens,
  };
}


