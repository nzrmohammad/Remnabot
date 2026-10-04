/**
 * RemnaStore Pro - Core DRY Utilities
 */

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
