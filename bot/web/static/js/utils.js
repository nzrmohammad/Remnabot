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
    document.body.appendChild(toast);
  }
  toast.innerText = msg;
  toast.classList.remove('opacity-0', '-translate-y-2');
  toast.classList.add('opacity-100', 'translate-y-0');
  setTimeout(() => {
    toast.classList.remove('opacity-100', 'translate-y-0');
    toast.classList.add('opacity-0', '-translate-y-2');
  }, 3000);
}

// Telegram Haptic Feedback
function hapticFeedback(type = 'success') {
  if (window.Telegram?.WebApp?.HapticFeedback) {
    try {
      if (type === 'impact') {
        window.Telegram.WebApp.HapticFeedback.impactOccurred('medium');
      } else {
        window.Telegram.WebApp.HapticFeedback.notificationOccurred(type);
      }
    } catch (e) {}
  }
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

