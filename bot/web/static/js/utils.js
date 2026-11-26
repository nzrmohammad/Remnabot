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

// Toast notification utility with Clean Code auto-icon injection & DRY type handling
let _appToastTimer = null;
function showToast(msg, typeOrDuration = 3200, duration = 3200) {
  let toast = document.getElementById('appToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'appToast';
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'assertive');
    toast.dir = 'rtl';
    document.body.appendChild(toast);
  }
  toast.className = 'fixed top-6 left-1/2 transform -translate-x-1/2 z-[100] modal-card t-main px-4 sm:px-6 py-3 rounded-2xl shadow-2xl text-xs sm:text-[13px] font-semibold text-center transition-all duration-300 opacity-0 pointer-events-none w-full max-w-lg leading-relaxed flex items-center justify-center gap-2.5 border box-border';
  if (_appToastTimer) {
    clearTimeout(_appToastTimer);
    _appToastTimer = null;
  }
  let delay = 3200;
  let type = null;
  if (typeof typeOrDuration === 'string') {
    type = typeOrDuration;
    if (typeof duration === 'number' && duration > 0) delay = duration;
  } else if (typeof typeOrDuration === 'number' && !isNaN(typeOrDuration) && typeOrDuration > 0) {
    delay = typeOrDuration;
  }

  let text = String(msg || '').trim();

  // Clean Code & DRY: Auto-detect toast type from leading emoji prefixes and strip them
  if (!type) {
    if (/^[✅✔]/u.test(text)) {
      type = 'success';
      text = text.replace(/^[✅✔]\s*/u, '');
    } else if (/^[❌✖🚫]/u.test(text)) {
      type = 'error';
      text = text.replace(/^[❌✖🚫]\s*/u, '');
    } else if (/^[⚠️⚡]/u.test(text)) {
      type = 'warning';
      text = text.replace(/^[⚠️⚡]\s*/u, '');
    } else if (/^[📋]/u.test(text)) {
      type = 'copy';
      text = text.replace(/^[📋]\s*/u, '');
    } else if (/^[🔄⏳]/u.test(text)) {
      type = 'sync';
      text = text.replace(/^[🔄⏳]\s*/u, '');
    } else if (/^[🔒🔐]/u.test(text)) {
      type = 'lock';
      text = text.replace(/^[🔒🔐]\s*/u, '');
    } else if (/^[📢🔔]/u.test(text)) {
      type = 'info';
      text = text.replace(/^[📢🔔]\s*/u, '');
    }
  }

  // Strip any orphan broken surrogates to prevent rendering missing glyph/tofu boxes
  text = text.replace(/[\uD800-\uDFFF]/g, '').trim();

  const iconNameMap = {
    success: 'check',
    error: 'cross',
    warning: 'warning',
    copy: 'copy',
    sync: 'recycle',
    lock: 'lock_shield',
    info: 'bell',
  };

  const borderClassMap = {
    success: 'border-emerald-500/30',
    error: 'border-rose-500/30',
    warning: 'border-amber-500/30',
    copy: 'border-blue-500/30',
    sync: 'border-cyan-500/30',
    lock: 'border-purple-500/30',
    info: 'border-sky-500/30',
  };

  // Reset any previous toast border classes
  toast.classList.remove(
    'border-emerald-500/30',
    'border-rose-500/30',
    'border-amber-500/30',
    'border-blue-500/30',
    'border-cyan-500/30',
    'border-purple-500/30',
    'border-sky-500/30'
  );

  let iconHtml = '';
  if (type && iconNameMap[type] && typeof uiIcon === 'function') {
    iconHtml = uiIcon(iconNameMap[type], 'w-4 h-4 shrink-0 inline-block');
    const borderCls = borderClassMap[type];
    if (borderCls) {
      toast.classList.add(borderCls);
    }
  }

  toast.innerHTML = `${iconHtml}<span class="flex-1 text-center text-xs sm:text-[13px] leading-relaxed font-sans whitespace-pre-line">${escapeHtml(text)}</span>`;
  toast.classList.remove('opacity-0', '-translate-y-2');
  toast.classList.add('opacity-100', 'translate-y-0');
  _appToastTimer = setTimeout(() => {
    toast.classList.remove('opacity-100', 'translate-y-0');
    toast.classList.add('opacity-0', '-translate-y-2');
    _appToastTimer = null;
  }, delay);
}

function dismissToast() {
  const toast = document.getElementById('appToast');
  if (!toast) return;
  if (_appToastTimer) {
    clearTimeout(_appToastTimer);
    _appToastTimer = null;
  }
  toast.classList.remove('opacity-100', 'translate-y-0');
  toast.classList.add('opacity-0', '-translate-y-2');
}
if (typeof window !== 'undefined') {
  window.dismissToast = dismissToast;
}

// Centralized Single Source of Truth (SSOT) for User Subscription Status Badges
function renderUserStatusBadge(u) {
  if (!u) return '<span class="badge badge-neutral">بدون اکانت</span>';
  const p = u.panel_account;
  const pStatus = (p && p.exists && p.status) ? String(p.status).toUpperCase() : '';
  const isLimited = u.is_limited || (p && p.exists && (pStatus === 'LIMITED' || (p.remaining_traffic_gb === 0 && p.limit_traffic_gb > 0)));
  const isExpired = u.is_expired || (p && p.exists && pStatus === 'EXPIRED');

  if (u.is_banned) {
    return `<span class="badge badge-danger">${uiIcon('ban', 'w-3 h-3')}<span>مسدود</span></span>`;
  }
  if (isLimited) {
    return `<span class="badge badge-warn">${uiIcon('warning', 'w-3 h-3')}<span>اتمام حجم</span></span>`;
  }
  if (isExpired) {
    return `<span class="badge badge-danger">${uiIcon('cross', 'w-3 h-3')}<span>منقضی</span></span>`;
  }
  const rawStatus = (pStatus || String(u.raw_status || '')).toUpperCase();
  if (rawStatus === 'ACTIVE') {
    return `<span class="badge badge-success">${uiIcon('check', 'w-3 h-3')}<span>فعال</span></span>`;
  }
  if (rawStatus === 'DISABLED') {
    return `<span class="badge badge-warn">${uiIcon('pause', 'w-3 h-3')}<span>غیرفعال</span></span>`;
  }
  if (rawStatus) {
    return `<span class="badge badge-info"><span>${escapeHtml(rawStatus)}</span></span>`;
  }
  return '<span class="badge badge-neutral">بدون اکانت</span>';
}
// Centralized Single Source of Truth (SSOT) for Node Online/Offline Status Badges
function renderNodeStatusBadge(isOnline) {
  return isOnline
    ? '<span class="relative flex items-center justify-center w-3 h-3" title="آنلاین"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span><span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span></span>'
    : '<span class="badge badge-danger font-sans flex items-center gap-1 text-[11px]"><span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span><span>آفلاین</span></span>';
}
if (typeof window !== 'undefined') {
  window.renderUserStatusBadge = renderUserStatusBadge;
  window.renderNodeStatusBadge = renderNodeStatusBadge;
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

// Centralized Web Audio API Sound Synthesizer (Zero-latency, 0 kB overhead, offline safe)
let _appAudioCtx = null;
function getAppAudioContext() {
  if (!_appAudioCtx && typeof window !== 'undefined') {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (AudioCtx) _appAudioCtx = new AudioCtx();
  }
  if (_appAudioCtx && _appAudioCtx.state === 'suspended') {
    _appAudioCtx.resume().catch(() => {});
  }
  return _appAudioCtx;
}

function playSubtleSound(type = 'click') {
  try {
    if (typeof localStorage !== 'undefined' && localStorage.getItem('user_sound_fx_disabled') === '1') {
      return;
    }
    const ctx = getAppAudioContext();
    if (!ctx) return;
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    if (type === 'flip' || type === 'card_flip') {
      // Soft metallic double pulse for 3D card flip
      osc.type = 'sine';
      osc.frequency.setValueAtTime(320, now);
      osc.frequency.exponentialRampToValueAtTime(520, now + 0.07);
      osc.frequency.exponentialRampToValueAtTime(380, now + 0.14);
      gain.gain.setValueAtTime(0.045, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.16);
      osc.start(now);
      osc.stop(now + 0.16);
    } else if (type === 'color_switch' || type === 'selection') {
      // Crisp glass droplet chime for color/theme selection
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(680, now);
      osc.frequency.exponentialRampToValueAtTime(880, now + 0.05);
      gain.gain.setValueAtTime(0.035, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.06);
      osc.start(now);
      osc.stop(now + 0.06);
    } else if (type === 'success' || type === 'coin_success') {
      // Cheerful ascending bell chime for purchase or wallet top-up
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, now); // D5
      osc.frequency.setValueAtTime(880, now + 0.08); // A5
      osc.frequency.setValueAtTime(1174.66, now + 0.16); // D6
      gain.gain.setValueAtTime(0.06, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
      osc.start(now);
      osc.stop(now + 0.35);
    } else if (type === 'tap' || type === 'light') {
      // Muted luxury micro-thump
      osc.type = 'sine';
      osc.frequency.setValueAtTime(160, now);
      gain.gain.setValueAtTime(0.03, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
      osc.start(now);
      osc.stop(now + 0.04);
    } else if (type === 'copy') {
      // Crisp crystal micro-chirp for copying
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(840, now);
      osc.frequency.exponentialRampToValueAtTime(1260, now + 0.04);
      gain.gain.setValueAtTime(0.04, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
      osc.start(now);
      osc.stop(now + 0.05);
    } else if (type === 'scratch') {
      // Subtle textured friction sound for scratching foil
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(220 + Math.random() * 140, now);
      gain.gain.setValueAtTime(0.015, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.035);
      osc.start(now);
      osc.stop(now + 0.035);
    } else if (type === 'slash' || type === 'discount') {
      // Snappy swoosh sound for price discount slash
      osc.type = 'sine';
      osc.frequency.setValueAtTime(740, now);
      osc.frequency.exponentialRampToValueAtTime(320, now + 0.08);
      gain.gain.setValueAtTime(0.045, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.09);
      osc.start(now);
      osc.stop(now + 0.09);
    }
  } catch (e) {}
}

// Silky Smooth Number Ticker (Odometer Ease-Out)
function animateNumber(element, startVal, endVal, duration = 650, formatter = (n) => n.toLocaleString('en-US')) {
  if (!element) return;
  const start = Number(String(startVal).replace(/[^0-9.-]/g, '')) || 0;
  const end = Number(String(endVal).replace(/[^0-9.-]/g, '')) || 0;
  if (start === end || isNaN(start) || isNaN(end)) {
    element.textContent = formatter(end);
    return;
  }
  const startTime = performance.now();
  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const easeProgress = 1 - Math.pow(1 - progress, 3);
    const current = Math.round(start + (end - start) * easeProgress);
    element.textContent = formatter(current);
    if (progress < 1) {
      requestAnimationFrame(update);
    } else {
      element.textContent = formatter(end);
    }
  }
  requestAnimationFrame(update);
}

// Centralized Celebration Confetti Particles Engine
function launchCelebrationConfetti(targetContainer = null) {
  if (typeof document === 'undefined') return;
  const container = targetContainer || document.body;
  const canvas = document.createElement('canvas');
  canvas.className = 'absolute inset-0 pointer-events-none z-[120] w-full h-full';
  const prevPos = window.getComputedStyle(container).position;
  if (!prevPos || prevPos === 'static') {
    container.style.position = 'relative';
  }
  container.appendChild(canvas);
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  canvas.width = container.clientWidth || 360;
  canvas.height = container.clientHeight || 500;

  const colors = ['#f59e0b', '#06b6d4', '#10b981', '#ec4899', '#8b5cf6', '#3b82f6', '#fbbf24', '#f43f5e'];
  const particles = Array.from({ length: 55 }, () => ({
    x: canvas.width * (0.35 + Math.random() * 0.3),
    y: canvas.height * 0.35,
    vx: (Math.random() - 0.5) * 11,
    vy: (Math.random() - 0.75) * 12,
    size: Math.random() * 6 + 4,
    color: colors[Math.floor(Math.random() * colors.length)],
    alpha: 1,
    rot: Math.random() * 360,
    rotSpeed: (Math.random() - 0.5) * 12,
  }));

  let frame = 0;
  function step() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      p.vy += 0.28;
      p.alpha -= 0.014;
      p.rot += p.rotSpeed;
      if (p.alpha > 0) {
        ctx.save();
        ctx.globalAlpha = Math.max(0, p.alpha);
        ctx.fillStyle = p.color;
        ctx.translate(p.x, p.y);
        ctx.rotate((p.rot * Math.PI) / 180);
        ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 1.35);
        ctx.restore();
      }
    });
    frame++;
    if (frame < 75) {
      requestAnimationFrame(step);
    } else {
      canvas.remove();
    }
  }
  requestAnimationFrame(step);
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
const _avatarBlobPromiseCache = new Map();

async function _resolveProxyAvatarBlobUrl(proxyUrl) {
  if (!proxyUrl || !window.api || typeof window.api.getBlob !== 'function') return '';
  if (_avatarBlobPromiseCache.has(proxyUrl)) {
    return _avatarBlobPromiseCache.get(proxyUrl);
  }
  const promise = (async () => {
    try {
      const blob = await window.api.getBlob(proxyUrl);
      if (blob && blob.size > 0 && String(blob.type || '').startsWith('image/')) {
        return URL.createObjectURL(blob);
      }
    } catch (e) {
      // Fallback handled cleanly by caller
    }
    return '';
  })();
  _avatarBlobPromiseCache.set(proxyUrl, promise);
  const resolved = await promise;
  if (!resolved) {
    _avatarBlobPromiseCache.delete(proxyUrl);
  }
  return resolved;
}

function loadAvatarWithFallback(imgEl, initialEl, directPhoto, userId, explicitProxyUrl = '') {
  if (!imgEl) return;
  imgEl.referrerPolicy = 'no-referrer';
  const profParam = directPhoto ? `&url=${encodeURIComponent(directPhoto)}` : '';
  const proxyUrl = explicitProxyUrl
    || (userId ? `/api/user/avatar?user_id=${userId}${profParam}` : (directPhoto ? `/api/user/avatar?url=${encodeURIComponent(directPhoto)}` : ''));

  if (!proxyUrl && !directPhoto) {
    imgEl.classList.add('hidden');
    if (initialEl) initialEl.classList.remove('hidden');
    return;
  }

  const cacheKey = proxyUrl || directPhoto;
  if (imgEl.dataset.avatarSrc === cacheKey && !imgEl.classList.contains('hidden')) {
    return;
  }
  imgEl.dataset.avatarSrc = cacheKey;

  const showImg = () => {
    imgEl.classList.remove('hidden');
    if (initialEl) initialEl.classList.add('hidden');
  };
  const showInitial = () => {
    imgEl.classList.add('hidden');
    if (initialEl) initialEl.classList.remove('hidden');
  };

  imgEl.onload = showImg;
  imgEl.onerror = () => {
    if (directPhoto && imgEl.src !== directPhoto && !imgEl.dataset.directRetried) {
      imgEl.dataset.directRetried = '1';
      imgEl.src = directPhoto;
    } else {
      showInitial();
    }
  };

  if (proxyUrl && window.api && typeof window.api.getBlob === 'function') {
    _resolveProxyAvatarBlobUrl(proxyUrl).then((blobUrl) => {
      if (imgEl.dataset.avatarSrc !== cacheKey) return;
      if (blobUrl) {
        imgEl.src = blobUrl;
        if (imgEl.complete && imgEl.naturalWidth > 0) showImg();
      } else if (directPhoto) {
        imgEl.dataset.directRetried = '1';
        imgEl.src = directPhoto;
      } else {
        showInitial();
      }
    });
  } else if (directPhoto) {
    imgEl.src = directPhoto;
    if (imgEl.complete && imgEl.naturalWidth > 0) showImg();
  } else {
    showInitial();
  }
}

function hydrateAuthAvatars(rootEl) {
  if (!rootEl || typeof rootEl.querySelectorAll !== 'function') return;
  rootEl.querySelectorAll('img[data-auth-avatar]').forEach(img => {
    const url = img.getAttribute('data-auth-avatar');
    if (!url) return;
    const initialEl = img.nextElementSibling;
    loadAvatarWithFallback(img, initialEl, null, null, url);
  });
}

const _qrBlobPromiseCache = new Map();
function setAuthQrImage(imgEl, text) {
  if (!imgEl || !text) return;
  const qrUrl = `/api/user/qr?text=${encodeURIComponent(text)}`;
  if (imgEl.dataset.qrKey === qrUrl && imgEl.src) return;
  imgEl.dataset.qrKey = qrUrl;

  if (!window.api || typeof window.api.getBlob !== 'function') {
    imgEl.src = qrUrl;
    return;
  }

  let promise = _qrBlobPromiseCache.get(qrUrl);
  if (!promise) {
    if (_qrBlobPromiseCache.size >= 40) {
      const oldest = _qrBlobPromiseCache.keys().next().value;
      _qrBlobPromiseCache.delete(oldest);
    }
    promise = window.api.getBlob(qrUrl).then(blob => (blob && blob.size > 0 ? URL.createObjectURL(blob) : '')).catch(() => '');
    _qrBlobPromiseCache.set(qrUrl, promise);
  }
  promise.then(blobUrl => {
    if (imgEl.dataset.qrKey !== qrUrl) return;
    if (blobUrl) {
      imgEl.src = blobUrl;
    } else {
      _qrBlobPromiseCache.delete(qrUrl);
    }
  });
}

if (typeof window !== 'undefined') {
  window.hapticFeedback = hapticFeedback;
  window.playSubtleSound = playSubtleSound;
  window.animateNumber = animateNumber;
  window.launchCelebrationConfetti = launchCelebrationConfetti;
  window.initScratchCard = initScratchCard;
  window.loadAvatarWithFallback = loadAvatarWithFallback;
  window.hydrateAuthAvatars = hydrateAuthAvatars;
  window.setAuthQrImage = setAuthQrImage;
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

async function copyToClipboard(text, successToast = null, toastType = 'success') {
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
    if (typeof playSubtleSound === 'function') {
      playSubtleSound('copy');
    }
    try {
      const activeEl = document.activeElement;
      if (activeEl && activeEl !== document.body && !activeEl.classList.contains('copy-flash')) {
        activeEl.classList.add('copy-flash');
        setTimeout(() => activeEl.classList.remove('copy-flash'), 500);
      }
    } catch (_) {}
    if (successToast) {
      showToast(successToast, toastType);
    }
  } else {
    showToast('خطا در کپی خودکار؛ لطفاً متن را دستی انتخاب و کپی فرمایید.', 'error');
  }
  return copied;
}

// Interactive Scratch-Off Foil Card Engine
function initScratchCard({ canvas, coverText = '✨ لمس و کشیدن انگشت ✨', threshold = 0.40, onReveal }) {
  if (!canvas) return null;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) return null;

  const w = canvas.width = canvas.offsetWidth || 260;
  const h = canvas.height = canvas.offsetHeight || 60;

  // Render metallic brushed silver foil
  const foilGrad = ctx.createLinearGradient(0, 0, w, h);
  foilGrad.addColorStop(0, '#94a3b8');
  foilGrad.addColorStop(0.25, '#e2e8f0');
  foilGrad.addColorStop(0.5, '#64748b');
  foilGrad.addColorStop(0.75, '#cbd5e1');
  foilGrad.addColorStop(1, '#94a3b8');
  ctx.fillStyle = foilGrad;
  ctx.fillRect(0, 0, w, h);

  // Brushed foil noise lines
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.16)';
  ctx.lineWidth = 1;
  for (let i = 0; i < w; i += 5) {
    ctx.beginPath();
    ctx.moveTo(i, 0);
    ctx.lineTo(i + 14, h);
    ctx.stroke();
  }

  // Cover label text
  ctx.fillStyle = '#0f172a';
  ctx.font = 'bold 11px Vazirmatn, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(coverText, w / 2, h / 2);

  let isDrawing = false;
  let revealed = false;

  const getPos = (e) => {
    const rect = canvas.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    return {
      x: (clientX - rect.left) * (w / rect.width),
      y: (clientY - rect.top) * (h / rect.height)
    };
  };

  const scratch = (x, y) => {
    if (revealed) return;
    ctx.globalCompositeOperation = 'destination-out';
    ctx.beginPath();
    ctx.arc(x, y, 16, 0, Math.PI * 2);
    ctx.fill();

    if (typeof playSubtleSound === 'function') {
      playSubtleSound('scratch');
    }
    if (typeof hapticFeedback === 'function') {
      hapticFeedback('light');
    }
  };

  const checkThreshold = () => {
    if (revealed) return;
    try {
      const imgData = ctx.getImageData(0, 0, w, h);
      const data = imgData.data;
      let zeroAlpha = 0;
      for (let i = 3; i < data.length; i += 64) {
        if (data[i] === 0) zeroAlpha++;
      }
      const ratio = zeroAlpha / (data.length / 64);
      if (ratio >= threshold) {
        revealed = true;
        canvas.style.transition = 'opacity 0.35s ease-out';
        canvas.style.opacity = '0';
        setTimeout(() => {
          if (canvas.parentNode) canvas.style.display = 'none';
        }, 360);
        if (typeof playSubtleSound === 'function') playSubtleSound('success');
        if (typeof launchCelebrationConfetti === 'function') {
          launchCelebrationConfetti(canvas.parentElement || document.body);
        }
        if (typeof onReveal === 'function') onReveal();
      }
    } catch (_) {}
  };

  const startDraw = (e) => {
    isDrawing = true;
    const pos = getPos(e);
    scratch(pos.x, pos.y);
  };

  const moveDraw = (e) => {
    if (!isDrawing) return;
    if (e.cancelable) e.preventDefault();
    const pos = getPos(e);
    scratch(pos.x, pos.y);
  };

  const endDraw = () => {
    if (!isDrawing) return;
    isDrawing = false;
    checkThreshold();
  };

  canvas.addEventListener('mousedown', startDraw);
  canvas.addEventListener('mousemove', moveDraw);
  window.addEventListener('mouseup', endDraw);

  canvas.addEventListener('touchstart', startDraw, { passive: false });
  canvas.addEventListener('touchmove', moveDraw, { passive: false });
  window.addEventListener('touchend', endDraw);

  return {
    revealAll: () => {
      if (revealed) return;
      revealed = true;
      canvas.style.transition = 'opacity 0.3s ease-out';
      canvas.style.opacity = '0';
      setTimeout(() => {
        canvas.style.display = 'none';
      }, 310);
      if (typeof onReveal === 'function') onReveal();
    }
  };
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

// Convert Persian and Arabic digits and separators to standard English digits
function toEnglishDigits(str) {
  if (str === null || str === undefined) return '';
  const fa = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];
  const ar = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
  let res = String(str);
  for (let i = 0; i < 10; i++) {
    res = res.replaceAll(fa[i], String(i)).replaceAll(ar[i], String(i));
  }
  // Normalize Persian decimal separator (٫) to dot and thousands separator (٬) to comma
  res = res.replaceAll('٫', '.').replaceAll('٬', ',');
  return res;
}

// Convert digits to Persian digits
function toPersianDigits(str) {
  if (str === null || str === undefined) return '';
  const fa = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];
  const s = toEnglishDigits(str);
  let res = '';
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (ch >= '0' && ch <= '9') {
      res += fa[ch.charCodeAt(0) - 48];
    } else {
      res += ch;
    }
  }
  return res;
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
  github: 'github',
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
  return `<img src="/static/img/icons/${file}.svg?v=fl2" class="ui-icon ui-icon-img shrink-0 ${className}" alt="" aria-hidden="true" loading="eager" />`;
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
  '🥇': 'medal-gold',
  '🥈': 'medal-silver',
  '🥉': 'medal-bronze',
  '👑': 'crown',
  '💎': 'diamond',
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
    return `<img src="/static/img/flags/${code}.svg" class="${className}" alt="${cc}" title="${cc}" onerror="this.outerHTML='<span>${fallback}</span>'" loading="lazy" />`;
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

  // Universal Rule: In HTML UI, icons default to the visual left of the plan name across the entire app
  const isIconLeft = (options.iconPosition === 'left' || options.iconLeft) ? true : (options.iconPosition === 'right' ? false : !options.plainText);

  if (options.plainText) {
    const icon = emojiStr || '💎';
    const textOut = options.raw ? cleanText : escapeHtml(cleanText);
    if (isIconLeft) {
      return textOut ? `${textOut} ${icon}` : icon;
    }
    return textOut ? `${icon} ${textOut}` : icon;
  }

  if (!emojiStr) {
    return `<bdi dir="ltr" class="inline-block font-bold select-all">${escapeHtml(name)}</bdi>`;
  }
  if (!cleanText) {
    return `<span class="inline-block text-base">${emojiStr}</span>`;
  }
  if (isIconLeft) {
    return `<span class="inline-flex items-center gap-1.5" dir="ltr"><span class="shrink-0 text-base">${emojiStr}</span><bdi dir="ltr" class="font-bold select-all">${escapeHtml(cleanText)}</bdi></span>`;
  }
  return `<span class="inline-flex items-center gap-1.5" dir="ltr"><bdi dir="ltr" class="font-bold select-all">${escapeHtml(cleanText)}</bdi><span class="shrink-0 text-base">${emojiStr}</span></span>`;
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
        if (topModal.id === 'confirmActionModal') {
          const cancelConfirm = document.getElementById('confirmModalCancelBtn');
          if (cancelConfirm && typeof cancelConfirm.click === 'function') {
            cancelConfirm.click();
            return;
          }
        }
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
        if (roleBtn) {
          e.preventDefault();
          roleBtn.click();
        }
      }
    });
  }
}

function updateTopPadding(topBarId) {
  const topBar = typeof topBarId === 'string' ? document.getElementById(topBarId) : topBarId;
  if (!topBar) return;
  const tg = window.Telegram?.WebApp;
  let padTop = 18;
  if (tg) {
    const safeTop = tg.contentSafeAreaInset?.top || tg.safeAreaInset?.top || 0;
    if (safeTop > 0) {
      padTop = safeTop + 8;
      document.documentElement.style.setProperty('--tg-content-safe-area-inset-top', safeTop + 'px');
      document.documentElement.style.setProperty('--tg-safe-area-inset-top', safeTop + 'px');
    }
  }
  topBar.style.paddingTop = padTop + 'px';
}
function renderModalPickerRow({
  onClick,
  title,
  sub = '',
  selected = false,
  isEnglish = true,
  rowDir = 'ltr',
  subDir = 'ltr',
  extraRowCls = '',
}) {
  const esc = typeof escapeHtml === 'function' ? escapeHtml : s => String(s ?? '');
  const baseCls = selected
    ? 'w-full p-2.5 rounded-2xl border border-cyan-500/40 bg-cyan-500/10 flex items-center justify-between gap-2 transition'
    : 'w-full p-2.5 rounded-2xl border border-card-border card-inset hover:border-cyan-500/30 flex items-center justify-between gap-2 transition';
  const dirAttr = rowDir ? ` dir="${esc(rowDir)}"` : '';
  const alignCls = isEnglish ? 'text-left font-en' : 'text-right font-sans';
  const txtDir = isEnglish ? 'ltr' : 'rtl';
  return `
    <button type="button"${dirAttr} class="${baseCls} ${extraRowCls}" onclick="${onClick}">
      <div class="min-w-0 flex-1 ${alignCls}" dir="${txtDir}">
        <span class="font-bold t-main block truncate">${esc(title)}</span>
        ${sub ? `<span class="text-[10px] t-muted block truncate" dir="${esc(subDir)}">${esc(sub)}</span>` : ''}
      </div>
      <span class="w-5 h-5 rounded-full flex items-center justify-center shrink-0 ${selected ? 'bg-cyan-500 text-white' : 'border border-card-border'}">
        ${selected ? '<svg class="w-3 h-3 text-white" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>' : ''}
      </span>
    </button>
  `;
}

function safeHttpUrl(rawUrl) {
  const s = String(rawUrl || '').trim();
  if (!/^https?:\/\//i.test(s)) return '';
  return s;
}

function renderCurrencyIcon(curr = 'USD') {
  const code = String(curr || 'USD').toUpperCase();
  if (code === 'EUR') {
    return '<svg class="w-3.5 h-3.5 shrink-0 inline-block" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-label="یورو"><path stroke-linecap="round" stroke-linejoin="round" d="M14.121 15.536c-1.171 1.952-3.07 1.952-4.242 0-1.172-1.953-1.172-5.119 0-7.072 1.171-1.952 3.07-1.952 4.242 0M8 10.5h4m-4 3h4m9-1.5a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>';
  }
  if (code === 'TOMAN' || code === 'IRT') {
    return '<span class="text-[9.5px] font-bold">تومان</span>';
  }
  return '<svg class="w-3.5 h-3.5 shrink-0 inline-block" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-label="دلار"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>';
}

const COUNTRY_CATALOG = [
  { code: 'DE', nameFa: 'آلمان', nameEn: 'Germany' },
  { code: 'NL', nameFa: 'هلند', nameEn: 'Netherlands' },
  { code: 'FI', nameFa: 'فنلاند', nameEn: 'Finland' },
  { code: 'FR', nameFa: 'فرانسه', nameEn: 'France' },
  { code: 'GB', nameFa: 'انگلیس', nameEn: 'United Kingdom' },
  { code: 'US', nameFa: 'آمریکا', nameEn: 'United States' },
  { code: 'TR', nameFa: 'ترکیه', nameEn: 'Turkey' },
  { code: 'AE', nameFa: 'امارات', nameEn: 'UAE' },
  { code: 'SE', nameFa: 'سوئد', nameEn: 'Sweden' },
  { code: 'CH', nameFa: 'سوئیس', nameEn: 'Switzerland' },
  { code: 'AT', nameFa: 'اتریش', nameEn: 'Austria' },
  { code: 'PL', nameFa: 'لهستان', nameEn: 'Poland' },
  { code: 'RO', nameFa: 'رومانی', nameEn: 'Romania' },
  { code: 'RU', nameFa: 'روسیه', nameEn: 'Russia' },
  { code: 'UA', nameFa: 'اوکراین', nameEn: 'Ukraine' },
  { code: 'AZ', nameFa: 'آذربایجان', nameEn: 'Azerbaijan' },
  { code: 'CA', nameFa: 'کانادا', nameEn: 'Canada' },
  { code: 'IT', nameFa: 'ایتالیا', nameEn: 'Italy' },
  { code: 'ES', nameFa: 'اسپانیا', nameEn: 'Spain' },
  { code: 'JP', nameFa: 'ژاپن', nameEn: 'Japan' },
  { code: 'SG', nameFa: 'سنگاپور', nameEn: 'Singapore' },
  { code: 'IR', nameFa: 'ایران', nameEn: 'Iran' },
  { code: 'HK', nameFa: 'هنگ‌کنگ', nameEn: 'Hong Kong' },
  { code: 'LU', nameFa: 'لوکزامبورگ', nameEn: 'Luxembourg' },
  { code: 'NO', nameFa: 'نروژ', nameEn: 'Norway' },
  { code: 'DK', nameFa: 'دانمارک', nameEn: 'Denmark' },
  { code: 'BE', nameFa: 'بلژیک', nameEn: 'Belgium' },
  { code: 'BG', nameFa: 'بلغارستان', nameEn: 'Bulgaria' },
  { code: 'CZ', nameFa: 'جمهوری چک', nameEn: 'Czechia' },
  { code: 'LV', nameFa: 'لتونی', nameEn: 'Latvia' },
  { code: 'MD', nameFa: 'مولداوی', nameEn: 'Moldova' },
  { code: 'KR', nameFa: 'کره جنوبی', nameEn: 'South Korea' },
  { code: 'IN', nameFa: 'هند', nameEn: 'India' },
  { code: 'BR', nameFa: 'برزیل', nameEn: 'Brazil' },
];

function getCountryInfo(code) {
  const cc = String(code || '').trim().toUpperCase();
  if (!cc || cc === 'XX') return null;
  const hit = COUNTRY_CATALOG.find(c => c.code === cc);
  return hit || { code: cc, nameFa: cc, nameEn: cc };
}

let _quickDiagState = { host: '', port: 443, label: '', mode: 'ping' };

function closeQuickDiagnosticModal() {
  document.getElementById('quickDiagnosticModal')?.classList.add('hidden');
}

function _syncQuickDiagModeUi() {
  const isTcp = _quickDiagState.mode === 'tcp';
  const pingBtn = document.getElementById('quickDiagModePing');
  const tcpBtn = document.getElementById('quickDiagModeTcp');
  const portInput = document.getElementById('quickDiagPortInput');
  const activeCls = 'flex-1 py-1.5 px-2 rounded-xl text-[11px] font-bold transition bg-cyan-600 text-white shadow';
  const inactiveCls = 'flex-1 py-1.5 px-2 rounded-xl text-[11px] font-medium transition card-inset border border-card-border t-muted hover:t-main';
  if (pingBtn) pingBtn.className = isTcp ? inactiveCls : activeCls;
  if (tcpBtn) tcpBtn.className = isTcp ? activeCls : inactiveCls;
  if (portInput) {
    portInput.classList.toggle('hidden', !isTcp);
    if (!portInput.value) portInput.value = String(_quickDiagState.port || 443);
  }
}

async function _runQuickDiagnostic() {
  const targetEl = document.getElementById('quickDiagnosticTarget');
  const badgeEl = document.getElementById('quickDiagnosticBadge');
  const listEl = document.getElementById('quickDiagnosticList');
  const cleanHost = _quickDiagState.host;
  const isTcp = _quickDiagState.mode === 'tcp';
  const portInputVal = parseInt(document.getElementById('quickDiagPortInput')?.value || '', 10);
  const effectivePort = portInputVal > 0 && portInputVal <= 65535 ? portInputVal : (_quickDiagState.port || 443);
  _quickDiagState.port = effectivePort;

  if (targetEl) {
    targetEl.innerText = `${_quickDiagState.label ? _quickDiagState.label + ' • ' : ''}${cleanHost}${isTcp ? ':' + effectivePort : ''}`;
  }
  _syncQuickDiagModeUi();
  if (badgeEl) {
    badgeEl.className = 'badge badge-info';
    badgeEl.innerText = 'در حال بررسی...';
  }
  if (listEl) {
    listEl.innerHTML = `<div class="p-5 text-center t-muted text-xs">در حال تست ${isTcp ? `پورت TCP (${effectivePort})` : 'پینگ (ICMP)'} از نودهای Check-Host...</div>`;
  }

  try {
    const payload = { host: cleanHost, check_type: isTcp ? 'tcp' : 'ping', max_nodes: 8 };
    if (isTcp) payload.port = effectivePort;
    const res = await window.api?.runCheckHost?.(payload);
    if (!res || !res.ok || !Array.isArray(res.results) || !res.results.length) {
      if (badgeEl) {
        badgeEl.className = 'badge badge-danger';
        badgeEl.innerText = 'ناموفق';
      }
      if (listEl) listEl.innerHTML = `<div class="p-4 text-center t-danger text-xs font-bold">${escapeHtml(res?.error || res?.message || 'نتیجه‌ای دریافت نشد')}</div>`;
      return;
    }
    const okCount = res.results.filter(r => r.ok).length;
    if (badgeEl) {
      badgeEl.className = okCount > 0 ? 'badge badge-success' : 'badge badge-danger';
      badgeEl.innerText = `${okCount}/${res.results.length} موفق`;
    }
    if (listEl) {
      const icmpHint = (!isTcp && okCount === 0) ? `
        <div class="card p-2.5 rounded-xl border border-amber-500/35 bg-amber-500/10 text-[10.5px] t-warn space-y-1.5" dir="rtl">
          <div class="font-bold">احتمالاً پینگ ICMP روی فایروال این سرور بسته است.</div>
          <div class="flex items-center justify-between gap-2">
            <span class="t-muted">پورت 443 یا پورت Xray سرور را با TCP تست کنید:</span>
            <button type="button" onclick="window.setQuickDiagnosticMode('tcp')" class="px-2.5 py-1 rounded-lg bg-cyan-600 text-white font-bold shrink-0">تست TCP :443</button>
          </div>
        </div>
      ` : '';
      listEl.innerHTML = icmpHint + res.results.map(r => {
        const cls = r.ok ? 'border-emerald-500/30 t-success' : 'border-rose-500/30 t-danger';
        const val = r.ping_ms !== undefined && r.ping_ms !== null ? `${escapeHtml(r.ping_ms)} ms` : escapeHtml(r.status || (r.ok ? 'OK' : 'Timeout'));
        return `
          <div class="card-inset px-2.5 py-2 rounded-xl border ${cls} flex items-center justify-between gap-2 text-[11px]" dir="ltr">
            <span class="t-main font-bold truncate">${escapeHtml(r.flag || '🌐')} ${escapeHtml(r.node_name || r.location || '')}</span>
            <span class="font-sans font-bold shrink-0">${val}</span>
          </div>
        `;
      }).join('');
    }
  } catch (err) {
    if (badgeEl) {
      badgeEl.className = 'badge badge-danger';
      badgeEl.innerText = 'خطا';
    }
    if (listEl) listEl.innerHTML = `<div class="p-4 text-center t-danger text-xs">${escapeHtml(err?.message || 'خطای شبکه')}</div>`;
  }
}

function setQuickDiagnosticMode(mode = 'ping') {
  _quickDiagState.mode = mode === 'tcp' ? 'tcp' : 'ping';
  _runQuickDiagnostic();
}

async function openQuickDiagnosticModal(rawHost, rawPort = null, label = '') {
  const modal = document.getElementById('quickDiagnosticModal');
  if (!modal) return;
  const cleanHost = String(rawHost || '').trim().replace(/^https?:\/\//i, '').split('/')[0].split(':')[0].trim();
  const parsedPort = rawPort && Number(rawPort) > 0 ? Number(rawPort) : null;
  if (!cleanHost || cleanHost === '—') {
    if (window.showToast) window.showToast('آدرس معتبری برای تست یافت نشد.', 'warning');
    return;
  }
  _quickDiagState = {
    host: cleanHost,
    port: parsedPort || 443,
    label: String(label || ''),
    mode: parsedPort ? 'tcp' : 'ping',
  };
  const portInput = document.getElementById('quickDiagPortInput');
  if (portInput) portInput.value = String(_quickDiagState.port);
  modal.classList.remove('hidden');
  if (window.hapticFeedback) window.hapticFeedback('selection');
  await _runQuickDiagnostic();
}

if (typeof window !== 'undefined') {
  window.COUNTRY_CATALOG = COUNTRY_CATALOG;
  window.getCountryInfo = getCountryInfo;
  window.updateTopPadding = updateTopPadding;
  window.renderModalPickerRow = renderModalPickerRow;
  window.safeHttpUrl = safeHttpUrl;
  window.renderCurrencyIcon = renderCurrencyIcon;
  window.openQuickDiagnosticModal = openQuickDiagnosticModal;
  window.closeQuickDiagnosticModal = closeQuickDiagnosticModal;
  window.setQuickDiagnosticMode = setQuickDiagnosticMode;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    COUNTRY_CATALOG,
    getCountryInfo,
    updateTopPadding,
    renderModalPickerRow,
    safeHttpUrl,
    renderCurrencyIcon,
    openQuickDiagnosticModal,
    closeQuickDiagnosticModal,
    setQuickDiagnosticMode,
    uiIcon,
    renderFlagHtml,
    getCountryCodeFromEmoji,
    escapeHtml,
    toEnglishDigits,
    toPersianDigits,
    formatPrice,
    formatNumber,
    toEnglishDigits,
    toPersianDigits,
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


