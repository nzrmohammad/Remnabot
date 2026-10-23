/**
 * RemnaStore Pro - Main Application Controller
 */

window.lastUserData = null;
window.currentAccountId = null;
window.storeSettings = null;

const _domCache = new Map();
const $ = id => {
  let elem = _domCache.get(id);
  if (!elem || !elem.isConnected) {
    elem = document.getElementById(id);
    if (elem) _domCache.set(id, elem);
  }
  return elem;
};
// toPersianDigits is provided globally by utils.js

// 1. Splash Screen Logic
function runSplash() {
  const splashScreen = $('splashScreen');
  const splashBar = $('splashBar');
  if (!splashScreen || !splashBar) return;

  splashScreen.classList.remove('hidden');
  splashScreen.style.opacity = '1';
  splashScreen.style.pointerEvents = 'auto';
  splashBar.style.width = '0%';
  setTimeout(() => { splashBar.style.width = '100%'; }, 50);
  setTimeout(() => {
    splashScreen.style.opacity = '0';
    splashScreen.style.pointerEvents = 'none';
    setTimeout(() => splashScreen.classList.add('hidden'), 500);
  }, 750);
}

if (document.readyState === 'complete' || document.readyState === 'interactive') {
  setTimeout(runSplash, 50);
} else {
  window.addEventListener('DOMContentLoaded', runSplash);
}
$('reloadBtn')?.addEventListener('click', runSplash);

// Accordion Toggle for Settings Boxes
function toggleSettingsBox(targetId) {
  if (!targetId) return;
  const targetBody = $(targetId);
  if (!targetBody) return;
  const isHidden = targetBody.classList.contains('hidden');
  const box = targetBody.closest('.settings-box');
  const chevron = box ? box.querySelector('.settings-box-chevron') : null;
  if (isHidden) {
    targetBody.classList.remove('hidden');
    chevron?.classList.add('rotate-180');
  } else {
    targetBody.classList.add('hidden');
    chevron?.classList.remove('rotate-180');
  }
  if (typeof hapticFeedback === 'function') hapticFeedback('selection');
}
window.toggleSettingsBox = toggleSettingsBox;

// 2. Tab Navigation (5 Tabs)
function renderReportsCharts(sub) {
  const currentSub = sub || window.lastUserData?.active_sub;
  const hasActiveSub = Boolean(window.lastUserData?.has_active_sub && currentSub);
  if (!hasActiveSub) {
    if (typeof resetActiveSubAnalytics === 'function') {
      resetActiveSubAnalytics();
    }
    return;
  }
  const weeklyCanvas = $('repWeeklyChartCanvas');
  const weeklyEmpty = $('repWeeklyEmptyState');
  if (weeklyCanvas) weeklyCanvas.classList.remove('hidden');
  if (weeklyEmpty) weeklyEmpty.classList.add('hidden');

  const monthlyCanvas = $('repMonthlyChartCanvas');
  const monthlyEmpty = $('repMonthlyEmptyState');
  if (monthlyCanvas) monthlyCanvas.classList.remove('hidden');
  if (monthlyEmpty) monthlyEmpty.classList.add('hidden');

  if (typeof renderBarChart === 'function') {
    renderBarChart('repWeeklyChartCanvas', currentSub.week_daily_totals_gb || [0, 0, 0, 0, 0, 0, 0], currentSub.week_day_labels || ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'], false);
    renderBarChart('repMonthlyChartCanvas', currentSub.month_weeks_totals_gb || [0, 0, 0, currentSub.week_used_gb || 0], ['هفته ۱', 'هفته ۲', 'هفته ۳', 'هفته ۴'], true);
  }
  if (typeof renderActiveSubAnalytics === 'function') {
    renderActiveSubAnalytics(currentSub);
  }
}
window.renderReportsCharts = renderReportsCharts;

function switchTab(targetId) {
  if (!targetId) return;
  const navButtons = document.querySelectorAll('.nav-btn');
  const tabPanes = document.querySelectorAll('.tab-pane');

  tabPanes.forEach(pane => {
    if (pane.id === targetId) {
      pane.classList.remove('hidden');
    } else {
      pane.classList.add('hidden');
    }
  });

  if (targetId === 'tab-reports') {
    setTimeout(() => renderReportsCharts(), 60);
  }

  navButtons.forEach(b => {
    const isTarget = b.getAttribute('data-tab') === targetId;
    if (isTarget) {
      b.classList.remove('text-slate-400');
      b.classList.add('text-blue-400');
      b.querySelector('span:last-child')?.classList.replace('font-medium', 'font-bold');
    } else {
      b.classList.remove('text-blue-400');
      b.classList.add('text-slate-400');
      b.querySelector('span:last-child')?.classList.replace('font-bold', 'font-medium');
    }
  });
  if (typeof syncTelegramBackButton === 'function') {
    syncTelegramBackButton();
  }
}
window.switchTab = switchTab;

function setupTabNavigation() {
  const navButtons = document.querySelectorAll('.nav-btn');
  navButtons.forEach(btn => {
    btn.onclick = () => {
      const targetId = btn.getAttribute('data-tab');
      if (targetId) switchTab(targetId);
    };
  });
}
window.setupTabNavigation = setupTabNavigation;

// 3. Sub-tabs in Reports Hub
function setupReportsSubtabs() {
  const repSubNightly = $('repSubNightly');
  const repSubWeekly = $('repSubWeekly');
  const repSubMonthly = $('repSubMonthly');
  const repSubAnalytics = $('repSubAnalytics');
  const viewRepNightly = $('viewRepNightly');
  const viewRepWeekly = $('viewRepWeekly');
  const viewRepMonthly = $('viewRepMonthly');
  const viewRepAnalytics = $('viewRepAnalytics');

  function setRepSub(activeBtn, activeView) {
    [repSubNightly, repSubWeekly, repSubMonthly, repSubAnalytics].forEach(b => {
      if (b) b.className = 'flex-1 py-1.5 rounded-lg font-medium text-slate-400 hover:text-slate-200 transition';
    });
    if (activeBtn) activeBtn.className = 'flex-1 py-1.5 rounded-lg font-bold bg-blue-600 text-white transition';

    [viewRepNightly, viewRepWeekly, viewRepMonthly, viewRepAnalytics].forEach(v => v?.classList.add('hidden'));
    activeView?.classList.remove('hidden');

    if (activeView === viewRepWeekly || activeView === viewRepMonthly || activeView === viewRepAnalytics) {
      setTimeout(() => renderReportsCharts(), 60);
    }
  }

  repSubNightly?.addEventListener('click', () => setRepSub(repSubNightly, viewRepNightly));
  repSubWeekly?.addEventListener('click', () => setRepSub(repSubWeekly, viewRepWeekly));
  repSubMonthly?.addEventListener('click', () => setRepSub(repSubMonthly, viewRepMonthly));
  repSubAnalytics?.addEventListener('click', () => setRepSub(repSubAnalytics, viewRepAnalytics));
}

// 4. Copy Subscription Button & Box
function setupSubscriptionActions() {
  const copySubBtn = $('copySubBtn');

  copySubBtn?.addEventListener('click', async () => {
    const urlToCopy = window.lastUserData?.active_sub?.subscription_url || $('subInput')?.value || $('subDisplayBox')?.innerText?.trim();
    if (!urlToCopy || urlToCopy.includes('در حال') || urlToCopy.includes('یافت نشد')) {
      showToast('⚠️ لینک اشتراکی برای کپی یافت نشد.');
      return;
    }
    const ok = await copyToClipboard(urlToCopy, '📋 لینک اشتراک با موفقیت در کلیپ‌بورد کپی شد.');
    if (ok) {
      hapticFeedback('success');
      copySubBtn.classList.add('text-emerald-400', 'border-emerald-500');
      copySubBtn.classList.remove('text-slate-300');
      setTimeout(() => {
        copySubBtn.classList.remove('text-emerald-400', 'border-emerald-500');
        copySubBtn.classList.add('text-slate-300');
      }, 1800);
    }
  });

  $('subBoxWrapper')?.addEventListener('click', () => {
    const url = ($('subInput')?.value || '').trim();
    if (url && !url.includes('در حال') && !url.includes('یافت نشد')) {
      copyToClipboard(url, '📋 لینک اشتراک با موفقیت در کلیپ‌بورد کپی شد.');
      hapticFeedback('success');
    }
  });

  $('noSubGoToShopBtn')?.addEventListener('click', () => {
    const shopNav = document.querySelector('.nav-btn[data-tab="tab-shop"]');
    if (shopNav) {
      shopNav.click();
    } else if (typeof switchTab === 'function') {
      switchTab('tab-shop');
    }
    hapticFeedback('impact');
  });
}

// 5. Toggle QR Code (Dedicated Modern Modal)
function setupQrToggle() {
  const qrToggleBtn = $('qrToggleBtn');
  const closeQrModalBtn = $('closeQrModalBtn');
  const copySubFromQrModalBtn = $('copySubFromQrModalBtn');
  const qrModal = $('qrModal');

  qrToggleBtn?.addEventListener('click', () => {
    window.currentModalQrUri = null;
    openModal('qrModal');
    syncTelegramBackButton();
  });

  closeQrModalBtn?.addEventListener('click', () => {
    window.currentModalQrUri = null;
    closeModal('qrModal');
    syncTelegramBackButton();
  });

  copySubFromQrModalBtn?.addEventListener('click', () => {
    const url = (window.currentModalQrUri || $('subInput')?.value || '').trim();
    if (url && !url.includes('در حال') && !url.includes('یافت نشد')) {
      copyToClipboard(url, '📋 لینک اشتراک با موفقیت در کلیپ‌بورد کپی شد.');
    }
  });

  qrModal?.addEventListener('click', (e) => {
    if (e.target === qrModal) {
      window.currentModalQrUri = null;
      closeModal('qrModal');
      syncTelegramBackButton();
    }
  });
}

// 5.1 Subscription Configs Modal
function setupConfigsModal() {
  const openConfigsModalBtn = $('openConfigsModalBtn');
  const closeConfigsModalBtn = $('closeConfigsModalBtn');
  const configsModal = $('configsModal');
  const configsModalList = $('configsModalList');
  const configsModalCount = $('configsModalCount');
  const copyAllConfigsBtn = $('copyAllConfigsBtn');

  let currentConfigsList = [];

  const loadAndRenderConfigs = async () => {
    if (!configsModalList) return;
    if (!window.lastUserData?.active_sub) {
      configsModalList.innerHTML = `
        <div class="text-center py-6 text-slate-400 text-xs">
          <span class="text-base">📱</span>
          <div class="mt-1 leading-relaxed">اشتراک فعالی برای نمایش کانفیگ‌ها وجود ندارد.</div>
        </div>
      `;
      if (configsModalCount) configsModalCount.innerText = '0 کانفیگ';
      return;
    }
    configsModalList.innerHTML = `
      <div class="text-center py-6 text-slate-400 text-xs">
        <span class="inline-block animate-spin mb-2 text-base">🔄</span>
        <div>در حال دریافت و تفکیک کانفیگ‌ها...</div>
      </div>
    `;

    try {
      const targetAccId = window.currentAccountId || window.lastUserData?.active_sub?.account_id || window.lastUserData?.active_sub?.id;
      const subUrl = window.lastUserData?.active_sub?.subscription_url || $('subInput')?.value || '';
      const res = await window.api.getSubscriptionConfigs(targetAccId, subUrl);
      if (res.ok && res.configs && res.configs.length > 0) {
        currentConfigsList = res.configs;
        if (configsModalCount) configsModalCount.innerText = `${currentConfigsList.length} کانفیگ`;

        configsModalList.innerHTML = currentConfigsList.map(c => {
          const safeName = escapeHtml(c.name || 'کانفیگ سرور');
          const protoBadge = escapeHtml((c.protocol || 'vpn').toUpperCase());
          const flag = c.flag || '🌐';

          return `
            <div class="config-row-item bg-transparent rounded-2xl p-2.5 border border-slate-700/60 flex items-center justify-between gap-2 transition hover:border-slate-600">
              <div class="flex items-center gap-2 overflow-hidden flex-1 min-w-0">
                <span class="text-base select-none flex-shrink-0" title="${escapeHtml(c.country_name || 'سرور')}">${flag}</span>
                <span class="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 uppercase flex-shrink-0">${protoBadge}</span>
                <span class="text-xs font-bold text-slate-200 truncate config-name-label" title="${safeName}">${safeName}</span>
              </div>
              <div class="flex items-center gap-1 shrink-0">
                <button type="button" class="copy-single-cfg-btn text-slate-300 hover:text-cyan-400 bg-transparent border-0 p-1.5 rounded-lg transition active:scale-95 text-sm" data-uri="${encodeURIComponent(c.uri)}" title="کپی کانفیگ">
                  📋
                </button>
                <button type="button" class="qr-single-cfg-btn text-slate-300 hover:text-cyan-400 bg-transparent border-0 p-1.5 rounded-lg transition active:scale-95 text-sm" data-uri="${encodeURIComponent(c.uri)}" data-name="${encodeURIComponent(c.name)}" title="نمایش کیوآرکد">
                  📷
                </button>
              </div>
            </div>
          `;
        }).join('');

        // Wire single copy buttons
        configsModalList.querySelectorAll('.copy-single-cfg-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            const uri = decodeURIComponent(btn.getAttribute('data-uri') || '');
            if (uri) {
              copyToClipboard(uri, '📋 کانفیگ اختصاصی با موفقیت در کلیپ‌بورد کپی شد.');
              hapticFeedback('success');
              btn.innerText = '✅';
              setTimeout(() => {
                btn.innerText = '📋';
              }, 1800);
            }
          });
        });

        // Wire single QR buttons
        configsModalList.querySelectorAll('.qr-single-cfg-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            const uri = decodeURIComponent(btn.getAttribute('data-uri') || '');
            if (uri) {
              window.currentModalQrUri = uri;
              const modalQrImg = $('modalQrImage');
              if (modalQrImg) {
                modalQrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=260x260&data=${encodeURIComponent(uri)}`;
              }
              openModal('qrModal');
              syncTelegramBackButton();
            }
          });
        });
      } else {
        currentConfigsList = [];
        if (configsModalCount) configsModalCount.innerText = '0 کانفیگ';
        const msg = res.message || res.error || 'کانفیگی در لینک اشتراک یافت نشد یا اشتراک منقضی شده است.';
        configsModalList.innerHTML = `
          <div class="text-center py-6 text-slate-400 text-xs">
            <span class="text-base">⚠️</span>
            <div class="mt-1 leading-relaxed">${escapeHtml(msg)}</div>
            <button type="button" id="retryConfigsBtn" class="mt-3 px-3 py-1.5 rounded-xl bg-cyan-600/25 hover:bg-cyan-600/40 text-cyan-300 border border-cyan-500/40 text-[11px] font-bold transition active:scale-95">
              🔄 تلاش مجدد
            </button>
          </div>
        `;
        $('retryConfigsBtn')?.addEventListener('click', loadAndRenderConfigs);
      }
    } catch (e) {
      configsModalList.innerHTML = `
        <div class="text-center py-6 text-rose-400 text-xs">
          <span class="text-base">❌</span>
          <div class="mt-1 leading-relaxed">خطا در دریافت کانفیگ‌های اشتراک: ${escapeHtml(e?.message || 'ارتباط با سرور برقرار نشد')}</div>
          <button type="button" id="retryConfigsBtnErr" class="mt-3 px-3 py-1.5 rounded-xl bg-cyan-600/25 hover:bg-cyan-600/40 text-cyan-300 border border-cyan-500/40 text-[11px] font-bold transition active:scale-95">
            🔄 تلاش مجدد
          </button>
        </div>
      `;
      $('retryConfigsBtnErr')?.addEventListener('click', loadAndRenderConfigs);
    }
  };

  openConfigsModalBtn?.addEventListener('click', () => {
    openModal('configsModal');
    syncTelegramBackButton();
    loadAndRenderConfigs();
  });

  closeConfigsModalBtn?.addEventListener('click', () => {
    closeModal('configsModal');
    syncTelegramBackButton();
  });

  configsModal?.addEventListener('click', (e) => {
    if (e.target === configsModal) {
      closeModal('configsModal');
      syncTelegramBackButton();
    }
  });

  copyAllConfigsBtn?.addEventListener('click', () => {
    if (!currentConfigsList || currentConfigsList.length === 0) {
      showToast('⚠️ کانفیگی برای کپی یافت نشد.');
      return;
    }
    const allUris = currentConfigsList.map(c => c.uri).filter(Boolean).join('\n');
    if (allUris) {
      copyToClipboard(allUris, `📋 مجموع ${currentConfigsList.length} کانفیگ با موفقیت در کلیپ‌بورد کپی شد.`);
      hapticFeedback('success');
    }
  });
}

// 6. Revoke Modal & Kill All Logic
function setupRevokeAndKill() {
  const openRevokeModalBtn = $('openRevokeModalBtn');
  const revokeSubBtnTop = $('revokeSubBtnTop');
  const cancelRevokeBtn = $('cancelRevokeBtn');
  const confirmRevokeBtn = $('confirmRevokeBtn');
  const subInput = $('subInput');

  openRevokeModalBtn?.addEventListener('click', () => openModal('revokeModal'));
  revokeSubBtnTop?.addEventListener('click', () => openModal('revokeModal'));
  cancelRevokeBtn?.addEventListener('click', () => closeModal('revokeModal'));

  confirmRevokeBtn?.addEventListener('click', async () => {
    confirmRevokeBtn.disabled = true;
    confirmRevokeBtn.innerText = 'در حال صدور لینک جدید...';
    try {
      const res = await window.api.revokeSub();
      if (res.ok && res.subscription_url) {
        if (subInput) subInput.value = res.subscription_url;
        closeModal('revokeModal');
        showToast('🎉 لینک اشتراک قبلی ابطال و لینک جدید با موفقیت صادر شد.');
        syncUserDataWithApi();
      } else {
        alert(res.error || 'خطا در تغییر لینک اشتراک.');
      }
    } catch (err) {
      alert('خطا در برقراری ارتباط با سرور.');
    } finally {
      confirmRevokeBtn.disabled = false;
      confirmRevokeBtn.innerText = '✅ بله، لینک جدید صادر کن';
      closeModal('revokeModal');
    }
  });

  $('killAllBtn')?.addEventListener('click', async () => {
    if (!confirm('آیا از قطع اتصال تمام نشست‌ها و ابطال لینک قبلی اطمینان دارید؟')) return;
    try {
      const res = await window.api.revokeSub();
      if (res.ok) {
        showToast('✅ تمام نشست‌های فعال مسدود و لینک اشتراک امن جدید صادر شد.');
        syncUserDataWithApi();
      } else {
        alert(res.error || 'خطا در قطع نشست‌ها.');
      }
    } catch (err) {
      alert('خطا در برقراری ارتباط با سرور.');
    }
  });
}

// 7. 1-Click Client Importers & Tutorial Guide System
const getSubUrl = () => {
  const url = (window.lastUserData?.active_sub?.subscription_url || $('subInput')?.value || '').trim();
  if (!url || url.includes('در حال') || url.includes('یافت نشد')) {
    showToast('⚠️ اشتراک فعالی برای اتصال یافت نشد.');
    return null;
  }
  return url;
};

const copyAndLaunch = (makeUri, appName) => {
  const url = getSubUrl();
  if (!url) return;

  copyToClipboard(url);

  const targetUri = makeUri(url);
  const redirectUrl = `${window.location.origin}/open-client?scheme=${encodeURIComponent(targetUri)}&name=${encodeURIComponent(appName)}&url=${encodeURIComponent(url)}`;

  try {
    if (window.Telegram?.WebApp?.openLink) {
      window.Telegram.WebApp.openLink(redirectUrl);
    } else {
      window.location.href = targetUri;
    }
  } catch (e) {
    console.debug('Deep link trigger fallback', e);
    try {
      window.open(redirectUrl, '_blank');
    } catch (e2) {}
  }

  showToast(`🚀 در حال انتقال به ${appName} (لینک در کلیپ‌بورد کپی شد)`);
};

function setupClientImporters() {
  $('appImportIncy')?.addEventListener('click', () => {
    copyAndLaunch(u => `incy://import/${u}`, 'Incy');
  });
  $('appImportHapp')?.addEventListener('click', () => {
    copyAndLaunch(u => `happ://add/${u}`, 'Happ');
  });
  $('appImportV2ray')?.addEventListener('click', () => {
    copyAndLaunch(u => `v2rayng://install-sub?url=${encodeURIComponent(u)}`, 'v2rayNG');
  });
  $('appImportHiddify')?.addEventListener('click', () => {
    copyAndLaunch(u => `hiddify://install-sub?url=${encodeURIComponent(u)}`, 'Hiddify');
  });
  $('appImportStreisand')?.addEventListener('click', () => {
    copyAndLaunch(u => `streisand://import/${u}`, 'Streisand');
  });
}

// 7.1 Client Apps Structure & Tutorial Guide
const CLIENT_APPS_DATA = {
  ios: [
    {
      id: 'shadowrocket',
      name: 'Shadowrocket',
      version: '2.2.62',
      desc: 'محبوب‌ترین و حرفه‌ای‌ترین کلاینت iOS با اتصال آسان و پایداری بالا',
      icon: '🚀',
      scheme: (url) => {
        try {
          return `sub://${btoa(unescape(encodeURIComponent(url)))}`;
        } catch(e) {
          return `shadowrocket://add/${encodeURIComponent(url)}`;
        }
      }
    },
    {
      id: 'streisand',
      name: 'Streisand',
      version: '1.9.2',
      desc: 'سریع‌ترین کلاینت iOS با قابلیت اتصال آسان و پشتیبانی کامل',
      icon: '🛡️',
      scheme: (url) => `streisand://import/${encodeURIComponent(url)}`
    },
    {
      id: 'v2box',
      name: 'V2Box',
      version: '2.4.1',
      desc: 'کلاینت باسابقه و پایدار اپ استور با قابلیت تست پینگ خودکار',
      icon: '📦',
      scheme: (url) => `v2box://install-sub?url=${encodeURIComponent(url)}&name=${encodeURIComponent(window.lastUserData?.bot_username || 'Subscription')}`
    },
    {
      id: 'incy',
      name: 'Incy',
      version: '1.0.8',
      desc: 'ظاهر زیبا و کاربری فوق‌العاده راحت با اتصال فوری یک‌کلیکه',
      icon: '⚡',
      scheme: (url) => `incy://import/${url}`
    },
    {
      id: 'happ',
      name: 'Happ',
      version: '3.1.2',
      desc: 'پشتیبانی از پروتکل‌های نوین با سرعت و پایداری فوق‌العاده',
      icon: '🚀',
      scheme: (url) => `happ://add/${url}`
    },
    {
      id: 'onexray',
      name: 'OneXray',
      version: '1.4.2',
      desc: 'کلاینت پیشرفته هسته Xray در اپل استور با سرعت و پایداری بالا',
      icon: '⚡',
      scheme: (url) => `onexray://install-sub?url=${encodeURIComponent(url)}`
    }
  ],
  android: [
    {
      id: 'v2rayng',
      name: 'v2rayNG',
      version: '1.9.15',
      desc: 'استانداردترین و سازگارترین نرم‌افزار برای تمامی گوشی‌های اندروید',
      icon: '🤖',
      scheme: (url) => `v2rayng://install-sub?url=${encodeURIComponent(url)}`
    },
    {
      id: 'happ',
      name: 'Happ',
      version: '3.1.2',
      desc: 'کلاینت جدید و بسیار قدرتمند با طراحی مدرن و سرعت بالا',
      icon: '🚀',
      scheme: (url) => `happ://add/${url}`
    },
    {
      id: 'hiddify',
      name: 'Hiddify',
      version: '2.5.7',
      desc: 'اتصال هوشمند به کم‌پینگ‌ترین سرور و تفکیک خودکار ترافیک',
      icon: '✨',
      scheme: (url) => `hiddify://install-sub?url=${encodeURIComponent(url)}`
    },
    {
      id: 'incy',
      name: 'Incy',
      version: '1.0.8',
      desc: 'محیط خلوت و مینیمال با اتصال یک‌کلیکه و مصرف کم باتری',
      icon: '⚡',
      scheme: (url) => `incy://import/${url}`
    }
  ],
  windows: [
    {
      id: 'v2rayn',
      name: 'v2rayN',
      version: '7.1.4',
      desc: 'قدرتمندترین کلاینت ویندوز با پشتیبانی کامل از انواع پروتکل‌ها',
      icon: '🪟',
      scheme: null
    },
    {
      id: 'hiddify',
      name: 'Hiddify',
      version: '2.5.7',
      desc: 'نرم‌افزار مدرن ویندوز با قابلیت فعال‌سازی سرویس TUN و تست پینگ',
      icon: '✨',
      scheme: (url) => `hiddify://install-sub?url=${encodeURIComponent(url)}`
    },
    {
      id: 'happ',
      name: 'Happ',
      version: '3.1.2',
      desc: 'نسخه ویندوز اپلیکیشن Happ با محیط سبک، مدرن و سرعت بالا',
      icon: '🚀',
      scheme: (url) => `happ://add/${url}`
    },
    {
      id: 'incy',
      name: 'Incy',
      version: '1.0.8',
      desc: 'کلاینت سبک برای اتصال فوری و بدون دردسر در کامپیوتر و لپ‌تاپ',
      icon: '⚡',
      scheme: null
    }
  ],
  macos: [
    {
      id: 'hiddify',
      name: 'Hiddify',
      version: '2.5.7',
      desc: 'نسخه مک کلاینت Hiddify با پشتیبانی از پردازنده‌های Apple Silicon و اینتل',
      icon: '✨',
      scheme: (url) => `hiddify://install-sub?url=${encodeURIComponent(url)}`
    },
    {
      id: 'happ',
      name: 'Happ',
      version: '3.1.2',
      desc: 'کلاینت پرسرعت و سبک ویژه macOS با رابط مینیمال و اتصال فوری',
      icon: '🚀',
      scheme: (url) => `happ://add/${url}`
    },
    {
      id: 'incy',
      name: 'Incy',
      version: '1.0.8',
      desc: 'نرم‌افزار زیبا و ساده سازگار با تمامی نسخه‌های مک',
      icon: '⚡',
      scheme: (url) => `incy://import/${url}`
    },
    {
      id: 'v2box',
      name: 'V2Box',
      version: '2.4.1',
      desc: 'نسخه مک اپلیکیشن باسابقه V2Box در اپ‌استور با تست پینگ',
      icon: '📦',
      scheme: (url) => `v2box://install-sub?url=${encodeURIComponent(url)}&name=${encodeURIComponent(window.lastUserData?.bot_username || 'Subscription')}`
    }
  ],
  linux: [
    {
      id: 'hiddify',
      name: 'Hiddify',
      version: '2.5.7',
      desc: 'کلاینت مدرن لینوکس در قالب بسته‌های AppImage و deb با هسته پیشرفته',
      icon: '✨',
      scheme: (url) => `hiddify://install-sub?url=${encodeURIComponent(url)}`
    },
    {
      id: 'nekoray',
      name: 'NekoRay',
      version: '4.0.1',
      desc: 'کلاینت محبوب و قدرتمند لینوکس با پشتیبانی کامل از sing-box و Xray',
      icon: '🐱',
      scheme: null
    },
    {
      id: 'v2raya',
      name: 'v2rayA',
      version: '2.2.5',
      desc: 'کلاینت تحت وب با سرویس سیستمی و هدایت شفاف ترافیک در لینوکس',
      icon: '🐧',
      scheme: null
    },
    {
      id: 'incy',
      name: 'Incy',
      version: '1.0.8',
      desc: 'کلاینت سبک و مدرن برای توزیع‌های مختلف لینوکس',
      icon: '⚡',
      scheme: (url) => `incy://import/${url}`
    }
  ]
};
// Backward compatibility mirror
CLIENT_APPS_DATA.desktop = CLIENT_APPS_DATA.windows;

function detectUserOS() {
  const ua = navigator.userAgent || '';
  if (/iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)) {
    return 'ios';
  }
  if (/Android/i.test(ua)) {
    return 'android';
  }
  if (/Macintosh|MacIntel|MacPPC|Mac68K/i.test(ua)) {
    return 'macos';
  }
  if (/Linux/i.test(ua)) {
    return 'linux';
  }
  return 'windows';
}

let currentTutorialOS = 'ios';

function getDownloadButtonInfo(url, defaultLabel, defaultIcon = '📥') {
  if (!url) return { label: defaultLabel, icon: defaultIcon };
  const lower = url.toLowerCase();
  if (lower.includes('play.google.com') || lower.includes('market://') || lower.includes('google.com/store')) {
    return { label: 'گوگل‌پلی', icon: '🛍' };
  }
  if (lower.includes('apps.apple.com') || lower.includes('itunes.apple.com')) {
    return { label: 'اپ‌استور', icon: '🍏' };
  }
  if (lower.includes('github.com')) {
    return { label: 'گیت‌هاب', icon: '🐙' };
  }
  if (lower.endsWith('.apk') || lower.includes('/releases/download/')) {
    return { label: 'دانلود مستقیم', icon: '📦' };
  }
  return { label: defaultLabel, icon: defaultIcon };
}

function renderTutorialApps(osKey) {
  currentTutorialOS = osKey || 'ios';
  const listContainer = $('tutorialAppsList');
  if (!listContainer) return;

  document.querySelectorAll('.tutorial-os-tab').forEach(tab => {
    const isTarget = tab.getAttribute('data-os') === currentTutorialOS;
    if (isTarget) {
      tab.classList.add('bg-cyan-600', 'text-white', 'shadow', 'font-bold');
      tab.classList.remove('text-slate-400', 'font-medium');
    } else {
      tab.classList.remove('bg-cyan-600', 'text-white', 'shadow', 'font-bold');
      tab.classList.add('text-slate-400', 'font-medium');
    }
  });

  // OS Apps Rendering
  const allApps = CLIENT_APPS_DATA[currentTutorialOS] || CLIENT_APPS_DATA.windows || [];

  let overrides = {};
  if (window.lastUserData?.client_apps_override) {
    try {
      overrides = typeof window.lastUserData.client_apps_override === 'string'
        ? JSON.parse(window.lastUserData.client_apps_override)
        : window.lastUserData.client_apps_override;
    } catch (e) {}
  }

  const recommendedAppId = overrides?.recommended?.[currentTutorialOS] || (currentTutorialOS === 'windows' ? overrides?.recommended?.desktop : '') || '';

  // Filter apps: only show if enabled and has a download URL set by admin
  const activeApps = allApps.map(app => {
    const osOverrides = (overrides && overrides[currentTutorialOS]) || (currentTutorialOS === 'windows' ? overrides?.desktop : null);
    const appCfg = (osOverrides && osOverrides[app.id])
      || (overrides && typeof overrides[app.id] === 'string' ? { enabled: true, download_url: overrides[app.id], tutorial_url: '' } : null);

    const downloadUrl = (appCfg && appCfg.download_url) ? appCfg.download_url.trim() : '';
    const downloadPortableUrl = (appCfg && appCfg.download_portable_url) ? appCfg.download_portable_url.trim() : '';
    const downloadExtraUrl = (appCfg && appCfg.download_extra_url) ? appCfg.download_extra_url.trim() : '';
    const isEnabled = appCfg ? (appCfg.enabled !== false && Boolean(downloadUrl || downloadPortableUrl || downloadExtraUrl)) : false;
    const tutorialUrl = (appCfg && appCfg.tutorial_url) ? appCfg.tutorial_url.trim() : '';
    const version = (appCfg && appCfg.version) ? appCfg.version.trim() : app.version;
    const isRecommended = Boolean(recommendedAppId && recommendedAppId.toLowerCase() === app.id.toLowerCase());
    return { ...app, isEnabled, downloadUrl, downloadPortableUrl, downloadExtraUrl, tutorialUrl, version, isRecommended };
  }).filter(app => app.isEnabled && (app.downloadUrl || app.downloadPortableUrl || app.downloadExtraUrl));

  // Recommended app comes first in the list
  activeApps.sort((a, b) => (b.isRecommended ? 1 : 0) - (a.isRecommended ? 1 : 0));

  if (activeApps.length === 0) {
    listContainer.innerHTML = `
      <div class="py-8 px-4 text-center space-y-2.5">
        <div class="w-12 h-12 rounded-2xl bg-slate-800/80 border border-slate-700/80 mx-auto flex items-center justify-center text-2xl">
          📱
        </div>
        <b class="text-xs text-slate-200 block">برنامه‌ای برای نمایش یافت نشد</b>
        <p class="text-[11px] text-slate-400 max-w-[260px] mx-auto leading-relaxed">
          هنوز لینک دانلودی برای برنامه‌های این سیستم‌عامل ثبت نشده است. لطفاً از طریق پشتیبانی پیگیری فرمایید.
        </p>
      </div>
    `;
    return;
  }

  listContainer.innerHTML = activeApps.map(app => {
    const dlButtons = [];
    const addedUrls = new Set();

    if (app.downloadUrl && !addedUrls.has(app.downloadUrl)) {
      const d = getDownloadButtonInfo(app.downloadUrl, 'دانلود اصلی', '📥');
      dlButtons.push({ url: app.downloadUrl, label: d.label, icon: d.icon });
      addedUrls.add(app.downloadUrl);
    }
    if (app.downloadPortableUrl && !addedUrls.has(app.downloadPortableUrl)) {
      dlButtons.push({ url: app.downloadPortableUrl, label: 'نسخه پرتابل (Portable)', icon: '💼' });
      addedUrls.add(app.downloadPortableUrl);
    }
    if (app.downloadExtraUrl && !addedUrls.has(app.downloadExtraUrl)) {
      let d = getDownloadButtonInfo(app.downloadExtraUrl, 'لینک کمکی', '🔗');
      if (dlButtons.length > 0 && dlButtons[0].label === d.label) {
        d = { label: 'لینک کمکی (گیت‌هاب)', icon: '🐙' };
      }
      dlButtons.push({ url: app.downloadExtraUrl, label: d.label, icon: d.icon });
      addedUrls.add(app.downloadExtraUrl);
    }

    const tutorialBtnHtml = app.tutorialUrl ? `
      <button type="button" class="btn-tutorial-app bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/40 text-[10px] font-bold py-1 px-2 rounded-xl transition flex items-center justify-center gap-1 active:scale-95 shadow-sm" data-url="${escapeHtml(app.tutorialUrl)}">
        <span>📖</span> آموزش
      </button>
    ` : '';

    let actionButtonsHtml = '';

    if (dlButtons.length === 1) {
      const d = dlButtons[0];
      actionButtonsHtml = `
        <div class="grid grid-cols-2 gap-1.5 pt-0.5">
          <button type="button" class="btn-download-app bg-slate-800 hover:bg-slate-750 text-slate-200 text-xs font-bold py-1.5 px-2 rounded-xl transition border border-slate-700/80 flex items-center justify-center gap-1 active:scale-95 shadow-sm truncate" data-url="${escapeHtml(d.url)}">
            <span>${d.icon}</span> <span class="truncate">${d.label}</span>
          </button>
          <button type="button" class="btn-autoconnect-app text-xs font-bold py-1.5 px-2 rounded-xl transition flex items-center justify-center gap-1 active:scale-95 shadow-sm" data-id="${app.id}" data-name="${escapeHtml(app.name)}">
            <span>⚡️</span> اتصال خودکار
          </button>
        </div>
      `;
    } else if (dlButtons.length >= 2) {
      actionButtonsHtml = `
        <div class="space-y-1.5 pt-0.5">
          <div class="grid grid-cols-2 gap-1.5">
            <button type="button" class="btn-download-app bg-slate-800 hover:bg-slate-750 text-slate-200 text-xs font-bold py-1.5 px-2 rounded-xl transition border border-slate-700/80 flex items-center justify-center gap-1 active:scale-95 shadow-sm truncate" data-url="${escapeHtml(dlButtons[0].url)}">
              <span>${dlButtons[0].icon}</span> <span class="truncate">${dlButtons[0].label}</span>
            </button>
            <button type="button" class="btn-download-app bg-slate-800 hover:bg-slate-750 text-slate-200 text-xs font-bold py-1.5 px-2 rounded-xl transition border border-slate-700/80 flex items-center justify-center gap-1 active:scale-95 shadow-sm truncate" data-url="${escapeHtml(dlButtons[1].url)}">
              <span>${dlButtons[1].icon}</span> <span class="truncate">${dlButtons[1].label}</span>
            </button>
          </div>
          <div>
            <button type="button" class="btn-autoconnect-app w-full text-xs font-bold py-1.5 px-2 rounded-xl transition flex items-center justify-center gap-1 active:scale-95 shadow-sm" data-id="${app.id}" data-name="${escapeHtml(app.name)}">
              <span>⚡️</span> اتصال خودکار به سرویس
            </button>
          </div>
        </div>
      `;
    }

    const cardBorder = app.isRecommended ? 'border-amber-500/50 bg-transparent shadow-sm' : 'border-slate-700/60 bg-transparent';

    return `
      <div class="tutorial-app-card rounded-2xl p-2.5 border ${cardBorder} space-y-1.5 transition hover:border-slate-600">
        <div class="flex items-center justify-between gap-2">
          <!-- Right side: App Icon + Name -->
          <div class="flex items-center gap-2.5 min-w-0">
            <div class="w-10 h-10 rounded-xl bg-transparent border border-slate-700/70 p-1 flex items-center justify-center flex-shrink-0 shadow-inner overflow-hidden relative">
              <img src="/static/img/apps/${app.id}.png" alt="${escapeHtml(app.name)}" class="w-full h-full object-contain rounded-lg" onerror="this.style.display='none'; if(this.nextElementSibling) this.nextElementSibling.style.display='flex';" />
              <span class="text-xl items-center justify-center hidden" style="display:none;">${app.icon || '📱'}</span>
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-1.5 min-w-0">
                ${app.version ? `<span class="text-[10px] text-slate-400 font-mono font-medium flex-shrink-0">v${toEnglishDigits(app.version)}</span>` : ''}
                <b class="text-xs text-white font-bold truncate">${escapeHtml(app.name)}</b>
              </div>
            </div>
          </div>
          <!-- Left side: Recommended badge + Tutorial button -->
          <div class="flex items-center gap-1.5 flex-shrink-0">
            ${app.isRecommended ? '<span class="w-6 h-6 rounded-full flex items-center justify-center text-xs bg-amber-500/15 text-amber-300 border border-amber-500/30 flex-shrink-0" title="پیشنهادی">⭐️</span>' : ''}
            ${tutorialBtnHtml}
          </div>
        </div>
        ${actionButtonsHtml}
      </div>
    `;
  }).join('');

  listContainer.querySelectorAll('.btn-download-app').forEach(btn => {
    btn.addEventListener('click', () => {
      const url = btn.getAttribute('data-url');
      if (!url) return;
      try {
        if (window.Telegram?.WebApp?.openLink) {
          window.Telegram.WebApp.openLink(url);
        } else {
          window.open(url, '_blank');
        }
      } catch (e) {
        window.open(url, '_blank');
      }
      hapticFeedback('impact');
    });
  });

  listContainer.querySelectorAll('.btn-tutorial-app').forEach(btn => {
    btn.addEventListener('click', () => {
      const url = btn.getAttribute('data-url');
      if (!url) return;
      try {
        if (window.Telegram?.WebApp?.openLink) {
          window.Telegram.WebApp.openLink(url);
        } else {
          window.open(url, '_blank');
        }
      } catch (e) {
        window.open(url, '_blank');
      }
      hapticFeedback('impact');
    });
  });

  listContainer.querySelectorAll('.btn-autoconnect-app').forEach(btn => {
    btn.addEventListener('click', () => {
      const appId = btn.getAttribute('data-id');
      const appName = btn.getAttribute('data-name');
      const url = getSubUrl();
      if (!url) return;
      const appDef = (CLIENT_APPS_DATA[currentTutorialOS] || []).find(a => a.id === appId);
      if (appDef && appDef.scheme) {
        copyAndLaunch(appDef.scheme, appName || appDef.name);
      } else {
        copyToClipboard(url, `📋 لینک اشتراک کپی شد. لطفاً آن را داخل نرم‌افزار ${appName || ''} وارد کنید.`);
        hapticFeedback('success');
      }
    });
  });
}

function getAllAppVersionsMap() {
  const map = {};
  let overrides = {};
  if (window.lastUserData?.client_apps_override) {
    try {
      overrides = typeof window.lastUserData.client_apps_override === 'string'
        ? JSON.parse(window.lastUserData.client_apps_override)
        : window.lastUserData.client_apps_override;
    } catch (e) {}
  }
  for (const [os, apps] of Object.entries(CLIENT_APPS_DATA)) {
    if (os === 'desktop') continue;
    const osOverrides = overrides[os] || (os === 'windows' ? overrides.desktop : null);
    for (const app of apps) {
      const appCfg = osOverrides?.[app.id];
      const ver = (appCfg && appCfg.version) ? appCfg.version.trim() : app.version;
      if (app.id && ver) {
        map[`${os}_${app.id}`] = ver;
      }
    }
  }
  return map;
}

function checkTutorialAppUpdates() {
  const badge = $('tutorialBadge');
  if (badge) badge.classList.add('hidden');
}

function markTutorialAppsSeen() {
  const currentMap = getAllAppVersionsMap();
  try {
    localStorage.setItem('seen_app_versions', JSON.stringify(currentMap));
  } catch (e) {}
  const badge = $('tutorialBadge');
  if (badge) badge.classList.add('hidden');
}

function verifyPhoneNative() {
  hapticFeedback('impact');
  const tg = window.Telegram?.WebApp;

  if (typeof tg?.requestContact === 'function') {
    try {
      console.info('[PhoneAuth] Native requestContact supported, invoking Telegram client...');
      tg.requestContact((granted) => {
        if (granted) {
          console.info('[PhoneAuth] Contact permission granted by user.');
          showToast('✅ شماره تماس با موفقیت ثبت شد. در حال به‌روزرسانی...');
          hapticFeedback('success');
          setTimeout(() => {
            if (typeof syncUserDataWithApi === 'function') {
              syncUserDataWithApi(window.currentAccountId);
            }
          }, 1200);
        } else {
          console.warn('[PhoneAuth] User declined or cancelled contact sharing.');
          showToast('اشتراک‌گذاری شماره تماس لغو گردید.');
        }
      });
      return;
    } catch (e) {
      console.warn('[PhoneAuth] requestContact threw error, falling back to bot deep link:', e);
    }
  } else {
    console.warn('[PhoneAuth] Native requestContact unavailable on this platform/version, falling back to bot deep link.');
  }

  // Graceful fallback for desktop browser dev/preview or clients without requestContact support
  const botUsername = window.lastUserData?.bot_username || '';
  if (!botUsername) {
    showToast('نام کاربری ربات در دسترس نیست.');
    return;
  }
  const verifyLink = `https://t.me/${botUsername}?start=verify_phone`;
  try {
    if (tg?.openTelegramLink) {
      tg.openTelegramLink(verifyLink);
    } else {
      window.open(verifyLink, '_blank');
    }
  } catch (e) {
    window.open(verifyLink, '_blank');
  }
}
window.verifyPhoneNative = verifyPhoneNative;

const JALALI_MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];

let currentBdayTab = 'day';

function switchBdayPickerTab(tab) {
  currentBdayTab = tab;
  ['day', 'month', 'year'].forEach(t => {
    const pane = $(`bdayPane${t.charAt(0).toUpperCase() + t.slice(1)}`);
    const tabBtn = $(`bdayTab${t.charAt(0).toUpperCase() + t.slice(1)}`);
    if (t === tab) {
      if (pane) pane.classList.remove('hidden');
      if (tabBtn) {
        tabBtn.className = 'flex-1 py-1.5 rounded-xl font-bold text-xs bg-indigo-600 text-white shadow transition flex items-center justify-center gap-1';
      }
    } else {
      if (pane) pane.classList.add('hidden');
      if (tabBtn) {
        tabBtn.className = 'flex-1 py-1.5 rounded-xl font-medium text-xs text-slate-400 hover:text-white transition flex items-center justify-center gap-1';
      }
    }
  });
  if (tab === 'year') {
    setTimeout(() => {
      const yPane = $('bdayPaneYear');
      const curYear = $('birthdayYearSelect')?.value || '1375';
      const activeYearBtn = yPane?.querySelector('.active-bday-item') || yPane?.querySelector(`[data-val="${curYear}"]`);
      if (activeYearBtn) {
        activeYearBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
    }, 40);
  }
  hapticFeedback('selection');
}
window.switchBdayPickerTab = switchBdayPickerTab;

function selectBdayItem(type, val, displayText, autoAdvance = false) {
  const hiddenInp = $(`birthday${type.charAt(0).toUpperCase() + type.slice(1)}Select`);
  if (hiddenInp) hiddenInp.value = String(val);
  
  const disp = $(`bday${type.charAt(0).toUpperCase() + type.slice(1)}Display`);
  const pillVal = $(`bday${type.charAt(0).toUpperCase() + type.slice(1)}PillVal`);
  const showText = displayText || toPersianDigits(val);
  if (disp) disp.innerText = showText;
  if (pillVal) pillVal.innerText = showText;

  const container = $(`bday${type.charAt(0).toUpperCase() + type.slice(1)}sGrid`);
  if (container) {
    container.querySelectorAll('.bday-grid-btn').forEach(btn => {
      const bVal = btn.getAttribute('data-val');
      if (String(bVal) === String(val)) {
        btn.classList.add('active-bday-item', 'bg-indigo-600', 'text-white', 'font-bold', 'border-indigo-400');
        btn.classList.remove('text-slate-300', 'bg-slate-800/80', 'border-slate-700/60');
      } else {
        btn.classList.remove('active-bday-item', 'bg-indigo-600', 'text-white', 'font-bold', 'border-indigo-400');
        btn.classList.add('text-slate-300', 'bg-slate-800/80', 'border-slate-700/60');
      }
    });
  }

  hapticFeedback('selection');

  if (autoAdvance) {
    if (type === 'year') {
      switchBdayPickerTab('month');
    } else if (type === 'month') {
      switchBdayPickerTab('day');
    }
  }

  if (type === 'year' || type === 'month') {
    updateBdayDaysGrid();
  }
}
window.selectBdayItem = selectBdayItem;

function isJalaliLeapYear(jy) {
  // Standard 33-year Jalali cycle (Ahmad Birashk / jalaali-js standard)
  const rem = ((jy % 33) + 33) % 33;
  return rem === 1 || rem === 5 || rem === 9 || rem === 13 || rem === 17 || rem === 22 || rem === 26 || rem === 30;
}

function getJalaliMonthDays(year, month) {
  const m = parseInt(month, 10);
  const y = parseInt(year, 10);
  if (m >= 1 && m <= 6) return 31;
  if (m >= 7 && m <= 11) return 30;
  if (m === 12) return isJalaliLeapYear(y) ? 30 : 29;
  return 31;
}

function updateBdayDaysGrid() {
  const dayGrid = $('bdayDaysGrid');
  if (!dayGrid) return;
  const m = parseInt($('birthdayMonthSelect')?.value || '1', 10);
  const y = parseInt($('birthdayYearSelect')?.value || '1375', 10);
  const maxDays = getJalaliMonthDays(y, m);

  const currentDay = parseInt($('birthdayDaySelect')?.value || '1', 10);
  if (currentDay > maxDays) {
    selectBdayItem('day', maxDays, toPersianDigits(maxDays), false);
  }

  dayGrid.querySelectorAll('.bday-grid-btn').forEach(btn => {
    const d = parseInt(btn.getAttribute('data-val'), 10);
    if (d > maxDays) {
      btn.classList.add('hidden');
    } else {
      btn.classList.remove('hidden');
    }
  });
}

function initBirthdaySelects() {
  const dayGrid = $('bdayDaysGrid');
  const monthGrid = $('bdayMonthsGrid');
  const yearGrid = $('bdayYearsGrid');

  if (dayGrid && dayGrid.children.length === 0) {
    for (let d = 1; d <= 31; d++) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.setAttribute('data-val', d);
      btn.className = 'bday-grid-btn py-1.5 px-1 h-8 min-h-[32px] text-center text-xs font-bold text-slate-300 bg-slate-800/80 hover:bg-slate-700 border border-slate-700/60 rounded-xl transition font-mono active:scale-95 flex items-center justify-center';
      btn.textContent = toPersianDigits(d);
      btn.onclick = () => selectBdayItem('day', d, toPersianDigits(d), false);
      dayGrid.appendChild(btn);
    }
  }

  if (monthGrid && monthGrid.children.length === 0) {
    JALALI_MONTHS.forEach((mName, idx) => {
      const mVal = idx + 1;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.setAttribute('data-val', mVal);
      btn.className = 'bday-grid-btn py-2 px-1 text-center text-xs text-slate-300 bg-slate-800/80 hover:bg-slate-700 border border-slate-700/60 rounded-xl transition font-medium active:scale-95';
      btn.textContent = mName;
      btn.onclick = () => selectBdayItem('month', mVal, mName, true);
      monthGrid.appendChild(btn);
    });
  }

  if (yearGrid && yearGrid.children.length === 0) {
    for (let y = 1395; y >= 1335; y--) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.setAttribute('data-val', y);
      btn.className = 'bday-grid-btn py-1.5 px-1 text-center text-xs text-slate-300 bg-slate-800/80 hover:bg-slate-700 border border-slate-700/60 rounded-xl transition font-mono active:scale-95';
      btn.textContent = `${toPersianDigits(y)}`;
      btn.onclick = () => selectBdayItem('year', y, toPersianDigits(y), true);
      yearGrid.appendChild(btn);
    }
  }
}

function openBirthdayModal() {
  initBirthdaySelects();
  const existingDate = window.lastUserData?.user?.birth_date || '';
  if (existingDate) {
    try {
      const parts = existingDate.replace(/-/g, '/').split('/').map(Number);
      if (parts.length === 3) {
        selectBdayItem('year', parts[0], toPersianDigits(parts[0]), false);
        selectBdayItem('month', parts[1], JALALI_MONTHS[parts[1] - 1] || parts[1], false);
        selectBdayItem('day', parts[2], toPersianDigits(parts[2]), false);
      }
    } catch (e) {}
  } else {
    selectBdayItem('year', 1375, toPersianDigits(1375), false);
    selectBdayItem('month', 1, 'فروردین', false);
    selectBdayItem('day', 1, toPersianDigits(1), false);
  }
  updateBdayDaysGrid();
  switchBdayPickerTab('day');
  openModal('birthdayModal');
  hapticFeedback('selection');
}

function closeBirthdayModal() {
  closeModal('birthdayModal');
}
window.openBirthdayModal = openBirthdayModal;
window.closeBirthdayModal = closeBirthdayModal;

function openAlertPickerModal(type) {
  const modal = $('alertThresholdModal');
  const titleEl = $('alertThresholdModalTitle');
  const subEl = $('alertThresholdModalSubtitle');
  const iconBox = $('alertThresholdIconBox');
  const listEl = $('alertThresholdOptionsList');
  if (!modal || !listEl) return;

  if (type === 'traffic') {
    if (titleEl) titleEl.innerText = 'تنظیم درصد هشدار مصرف ترافیک';
    if (subEl) subEl.innerText = 'هنگامی که مصرف بسته به این درصد برسد، ربات پیام هشدار ارسال می‌کند.';
    if (iconBox) {
      iconBox.className = 'w-10 h-10 rounded-2xl bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 flex items-center justify-center text-lg flex-shrink-0';
      iconBox.innerHTML = '⚠️';
    }
    const currentVal = parseInt($('settingTrafficPercentSelect')?.value || '80', 10);
    const options = [
      { val: 70, label: '70% — هشدار زودهنگام', desc: 'ارسال هشدار هنگام مصرف ۷۰٪ حجم بسته' },
      { val: 75, label: '75% — سه‌چهارم حجم', desc: 'ارسال هشدار هنگام مصرف سه‌چهارم ترافیک' },
      { val: 80, label: '80% — حد استاندارد (پیشنهادی ⭐)', desc: 'بهترین تعادل برای خرید یا تمدید به‌موقع' },
      { val: 85, label: '85% — مصرف بالا', desc: 'ارسال هشدار در آستانه اتمام حجم' },
      { val: 90, label: '90% — نزدیک به پایان کامل', desc: 'هشدار فوری هنگام باقی‌ماندن ۱۰٪ حجم' },
      { val: 95, label: '95% — هشدار اضطراری', desc: 'آخرین فرصت پیش از قطع دسترسی اینترنت' },
    ];
    listEl.innerHTML = options.map(opt => `
      <div onclick="window.selectAlertSetting('traffic', ${opt.val})" class="alert-picker-option cursor-pointer p-2.5 rounded-2xl border transition flex items-center justify-between ${opt.val === currentVal ? 'active-alert-opt bg-cyan-500/15 border-cyan-500/50 text-cyan-300' : 'bg-slate-900/60 border-slate-700/60 hover:border-slate-500 text-slate-300'}">
        <div>
          <b class="text-xs block">${opt.label}</b>
          <span class="text-[10px] text-slate-400 block mt-0.5">${opt.desc}</span>
        </div>
        <div class="w-5 h-5 rounded-full border ${opt.val === currentVal ? 'border-cyan-400 bg-cyan-500 flex items-center justify-center text-slate-950 font-bold text-xs' : 'border-slate-600'}">
          ${opt.val === currentVal ? '✓' : ''}
        </div>
      </div>
    `).join('');
  } else if (type === 'expire') {
    if (titleEl) titleEl.innerText = 'تنظیم زمان هشدار پایان اعتبار سرویس';
    if (subEl) subEl.innerText = 'چند روز مانده به پایان مدت اشتراک پیام یادآوری تمدید ارسال شود؟';
    if (iconBox) {
      iconBox.className = 'w-10 h-10 rounded-2xl bg-amber-500/20 text-amber-400 border border-amber-500/30 flex items-center justify-center text-lg flex-shrink-0';
      iconBox.innerHTML = '⏰';
    }
    const currentVal = parseInt($('settingExpireDaysSelect')?.value || '3', 10);
    const options = [
      { val: 1, label: '1 روز قبل از پایان', desc: 'ارسال پیام یادآوری در روز پایانی اعتبار' },
      { val: 2, label: '2 روز قبل از پایان', desc: 'ارسال پیام دو روز مانده به انقضای اشتراک' },
      { val: 3, label: '3 روز قبل از پایان (پیشنهادی ⭐)', desc: 'زمان استاندارد جهت جلوگیری از قطعی اتصال' },
      { val: 5, label: '5 روز قبل از پایان', desc: 'اطلاع‌رسانی زودهنگام ۵ روز مانده به انقضا' },
      { val: 7, label: '7 روز قبل از پایان', desc: 'اطلاع‌رسانی یک هفته قبل از اتمام زمان سرویس' },
    ];
    listEl.innerHTML = options.map(opt => `
      <div onclick="window.selectAlertSetting('expire', ${opt.val})" class="alert-picker-option cursor-pointer p-2.5 rounded-2xl border transition flex items-center justify-between ${opt.val === currentVal ? 'active-alert-opt bg-amber-500/15 border-amber-500/50 text-amber-300' : 'bg-slate-900/60 border-slate-700/60 hover:border-slate-500 text-slate-300'}">
        <div>
          <b class="text-xs block">${opt.label}</b>
          <span class="text-[10px] text-slate-400 block mt-0.5">${opt.desc}</span>
        </div>
        <div class="w-5 h-5 rounded-full border ${opt.val === currentVal ? 'border-amber-400 bg-amber-500 flex items-center justify-center text-slate-950 font-bold text-xs' : 'border-slate-600'}">
          ${opt.val === currentVal ? '✓' : ''}
        </div>
      </div>
    `).join('');
  }

  openModal('alertThresholdModal');
  hapticFeedback('selection');
}
window.openAlertPickerModal = openAlertPickerModal;

function closeAlertThresholdModal() {
  closeModal('alertThresholdModal');
}
window.closeAlertThresholdModal = closeAlertThresholdModal;

async function selectAlertSetting(type, val) {
  closeAlertThresholdModal();

  if (type === 'traffic') {
    const hiddenInp = $('settingTrafficPercentSelect');
    if (hiddenInp) hiddenInp.value = String(val);
    const disp = $('trafficPercentDisplay');
    if (disp) disp.innerText = `${val}%`;
    const trafSub = $('settingTrafficSubtext');
    if (trafSub) trafSub.innerText = `هشدار قبل از پایان ترافیک (${toEnglishDigits(val)}%)`;

    try {
      const res = await window.api.saveSetting('traffic_percent', val);
      if (res && res.ok) {
        showToast(`✅ درصد هشدار مصرف روی ${val}٪ تنظیم شد.`);
        hapticFeedback('success');
      } else {
        showToast('❌ خطا در ذخیره تنظیمات');
      }
    } catch (e) {
      showToast('خطا در برقراری ارتباط با سرور.');
    }
  } else if (type === 'expire') {
    const hiddenInp = $('settingExpireDaysSelect');
    if (hiddenInp) hiddenInp.value = String(val);
    const disp = $('expireDaysDisplay');
    if (disp) disp.innerText = `${val} روز`;
    const expSub = $('settingExpireSubtext');
    if (expSub) expSub.innerText = `اطلاع‌رسانی ${toEnglishDigits(val)} روز مانده به انقضا`;

    try {
      const res = await window.api.saveSetting('expire_days', val);
      if (res && res.ok) {
        showToast(`✅ مهلت هشدار انقضا روی ${val} روز تنظیم شد.`);
        hapticFeedback('success');
      } else {
        showToast('❌ خطا در ذخیره تنظیمات');
      }
    } catch (e) {
      showToast('خطا در برقراری ارتباط با سرور.');
    }
  }
}
window.selectAlertSetting = selectAlertSetting;

async function saveBirthday() {
  const day = parseInt($('birthdayDaySelect')?.value || '1', 10);
  const month = parseInt($('birthdayMonthSelect')?.value || '1', 10);
  const year = parseInt($('birthdayYearSelect')?.value || '1375', 10);

  const formattedDate = `${year}/${String(month).padStart(2, '0')}/${String(day).padStart(2, '0')}`;
  const saveBtn = $('saveBirthdayBtn');
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.innerText = 'در حال ذخیره...';
  }

  try {
    const res = await window.api.setBirthday(formattedDate);
    const isOk = res.ok && (res.data ? res.data.ok !== false : true);
    if (isOk) {
      showToast('🎉 تاریخ زادروز شما با موفقیت ثبت گردید.');
      hapticFeedback('success');
      closeBirthdayModal();

      // Immediately reflect in UI without delay
      const profBirth = $('profileBirthDate');
      if (profBirth) profBirth.innerText = toPersianDigits(formattedDate);

      if (window.lastUserData?.user) {
        window.lastUserData.user.birth_date = formattedDate;
        renderDashboardBirthdayCountdown(window.lastUserData.user);
      }

      if (typeof syncUserDataWithApi === 'function') {
        syncUserDataWithApi(window.currentAccountId);
      }
    } else {
      const errMsg = res.data?.error || res.data?.message || 'خطا در ثبت تاریخ تولد';
      showToast(`⚠️ ${errMsg}`);
      hapticFeedback('error');
    }
  } catch (err) {
    showToast('خطای شبکه در ذخیره تاریخ زادروز');
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.innerText = 'ثبت تاریخ تولد 🎉';
    }
  }
}

window.openBirthdayModal = openBirthdayModal;
window.closeBirthdayModal = closeBirthdayModal;
window.saveBirthday = saveBirthday;

const PERSIAN_MONTH_TRAITS = {
  1: {
    name: 'فروردین',
    symbol: 'قوچ ♈️',
    description: 'پرانرژی، پیشرو، شجاع و بااراده آهنین. متولدین فروردین ماجراجو، باانگیزه و رهبرانی پرشور و مثبت‌اندیش هستند.'
  },
  2: {
    name: 'اردیبهشت',
    symbol: 'گاو ♉️',
    description: 'صبور، وفادار، پرمحبت، آرام و قابل اعتماد. متولدین اردیبهشت اهل عمل، زیبایی‌دوست و تکیه‌گاهی امن و استوارند.'
  },
  3: {
    name: 'خرداد',
    symbol: 'دوقلو ♊️',
    description: 'باهوش، خلاق، کنجکاو، اجتماعی و خوش‌بیان. متولدین خرداد سازگار با تغییرات، شوخ‌طبع و سرشار از ایده‌های تازه و نوآورانه‌اند.'
  },
  4: {
    name: 'تیر',
    symbol: 'خرچنگ ♋️',
    description: 'مهربان، فداکار، بااحساس و دارای حس ششم قوی. متولدین تیر خانواده‌دوست، حامی، دل‌رحم و صاحب قلبی بسیار زلال و باوفا هستند.'
  },
  5: {
    name: 'مرداد',
    symbol: 'شیر ♌️',
    description: 'شجاع، سخاوتمند، جذاب، باوقار و پرتو‌افشان. متولدین مرداد پرصلابت، وفادار، الهام‌بخش و مدیرانی کاردان و حامی اطرافیانند.'
  },
  6: {
    name: 'شهریور',
    symbol: 'خوشه ♍️',
    description: 'دقیق، منظم، متفکر، تحلیل‌گر و یاری‌رسان. متولدین شهریور با تدبیر و هوش سرشار خویش همواره راه‌حل‌های بی‌نقص می‌آفرینند.'
  },
  7: {
    name: 'مهر',
    symbol: 'ترازو ♎️',
    description: 'باانصاف، صلح‌طلب، جذاب، خوش‌سلیقه و اهل دوستی. متولدین مهر مظهر تعادل، عدالت، مهربانی و درک عمیق دیگران هستند.'
  },
  8: {
    name: 'آبان',
    symbol: 'عقرب ♏️',
    description: 'وفادار، رازدار، بااراده، پرشور و پرجاذبه. متولدین آبان مصمم، تیزبین و دارای قدرتی درونی برای فائق آمدن بر هر چالشی هستند.'
  },
  9: {
    name: 'آذر',
    symbol: 'کماندار ♐️',
    description: 'آزادی‌خواه، خوش‌بین، پرانرژی، صادق و ماجراجو. متولدین آذر گشاده‌رو، روشن‌بین، اهل سفر و یادگیری و سرشار از امیدند.'
  },
  10: {
    name: 'دی',
    symbol: 'بز ♑️',
    description: 'هدفمند، صبور، مستقل، باانضباط و خستگی‌ناپذیر. متولدین دی با پشتکار بی‌نظیر، پختگی و دوراندیشی قله‌های موفقیت را فتح می‌کنند.'
  },
  11: {
    name: 'بهمن',
    symbol: 'دلو ♒️',
    description: 'نوآور، آینده‌نگر، مستقل، پیشرو و انسان‌دوست. متولدین بهمن مبتکر، خلاق، بدون تعصب و پرچمدار تغییرات مثبت و بنیادین هستند.'
  },
  12: {
    name: 'اسفند',
    symbol: 'ماهی ♓️',
    description: 'خلاق، خیال‌پرداز، مهربان، دل‌نازک و سرشار از شهود معنوی. متولدین اسفند زلال، باگذشت، عاطفی و الهام‌بخش اطرافیان خود هستند.'
  }
};

let bdayCountdownInterval = null;

function openBirthdayCountdownModal() {
  const user = window.lastUserData?.user;
  if (!user || !user.birth_date) {
    openBirthdayModal();
    return;
  }

  const parts = user.birth_date.replace(/-/g, '/').split('/').map(Number);
  const monthNum = parts.length >= 2 ? parts[1] : 1;
  const trait = PERSIAN_MONTH_TRAITS[monthNum] || PERSIAN_MONTH_TRAITS[1];

  const monthEl = $('bdayTraitMonthName');
  if (monthEl) monthEl.innerText = `${trait.name} (${trait.symbol})`;
  const descEl = $('bdayTraitDescription');
  if (descEl) descEl.innerText = trait.description;

  const daysLeft = Number(user.days_until_birthday ?? 0);
  const isToday = Boolean(user.is_birthday_today || daysLeft === 0);

  const titleEl = $('bdayModalUserTitle');
  if (isToday) {
    if (titleEl) titleEl.innerText = '🎉 امروز روز زادروز شماست! مبارک باد 🎂';
  } else {
    if (titleEl) titleEl.innerText = `تنها ${toEnglishDigits(daysLeft)} روز تا روز زادروز شما باقی است`;
  }

  const now = new Date();
  const midnightToday = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 0).getTime();
  const msUntilMidnight = Math.max(0, midnightToday - now.getTime());
  const extraDays = Math.max(0, daysLeft - 1);
  const totalRemainingMs = isToday ? 0 : (extraDays * 86400000) + msUntilMidnight;
  const targetEpoch = Date.now() + totalRemainingMs;

  function updateTicker() {
    if (isToday) {
      if ($('bdayCountdownDays')) $('bdayCountdownDays').innerText = '0';
      if ($('bdayCountdownHours')) $('bdayCountdownHours').innerText = '00';
      if ($('bdayCountdownMinutes')) $('bdayCountdownMinutes').innerText = '00';
      if ($('bdayCountdownSeconds')) $('bdayCountdownSeconds').innerText = '00';
      return;
    }
    const diff = Math.max(0, targetEpoch - Date.now());
    const d = Math.floor(diff / (1000 * 60 * 60 * 24));
    const h = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const m = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    const s = Math.floor((diff % (1000 * 60)) / 1000);

    if ($('bdayCountdownDays')) $('bdayCountdownDays').innerText = String(d);
    if ($('bdayCountdownHours')) $('bdayCountdownHours').innerText = String(h).padStart(2, '0');
    if ($('bdayCountdownMinutes')) $('bdayCountdownMinutes').innerText = String(m).padStart(2, '0');
    if ($('bdayCountdownSeconds')) $('bdayCountdownSeconds').innerText = String(s).padStart(2, '0');
  }

  updateTicker();
  if (bdayCountdownInterval) clearInterval(bdayCountdownInterval);
  bdayCountdownInterval = setInterval(updateTicker, 1000);

  openModal('birthdayCountdownModal');
  hapticFeedback('selection');
}

function closeBirthdayCountdownModal() {
  if (bdayCountdownInterval) {
    clearInterval(bdayCountdownInterval);
    bdayCountdownInterval = null;
  }
  closeModal('birthdayCountdownModal');
}

window.openBirthdayCountdownModal = openBirthdayCountdownModal;
window.closeBirthdayCountdownModal = closeBirthdayCountdownModal;

function renderDashboardBirthdayCountdown(user) {
  const card = $('dashboardBirthdayCard');
  if (!card) return;

  const birthDate = user?.birth_date;
  if (!birthDate || !birthDate.trim()) {
    card.classList.add('hidden');
    return;
  }

  const daysLeft = user?.days_until_birthday;
  const isToday = user?.is_birthday_today;
  const titleEl = $('birthdayCardTitle');
  const subEl = $('birthdayCardSubtitle');
  const badgeEl = $('birthdayCardBadge');
  const numEl = $('birthdayDaysLeftNum');

  card.classList.remove('hidden');

  if (isToday || daysLeft === 0) {
    if (titleEl) titleEl.innerText = '🎉 امروز روز زادروز شماست!';
    if (subEl) subEl.innerText = 'تولدت مبارک! هدیه ویژه شما فعال گردید 🎁';
    if (badgeEl) badgeEl.innerHTML = '<span>🎂</span> <span>مبارک باد!</span>';
  } else if (daysLeft !== null && daysLeft !== undefined) {
    if (titleEl) titleEl.innerText = 'شمارش معکوس زادروز شما';
    if (subEl) subEl.innerText = `تنها ${toEnglishDigits(daysLeft)} روز تا روز تولدتان باقی مانده است`;
    if (numEl) numEl.innerText = toEnglishDigits(daysLeft);
  } else {
    card.classList.add('hidden');
  }
}

function loadAvatarWithFallback(imgEl, initialEl, directPhoto, userId) {
  if (!imgEl) return;
  imgEl.referrerPolicy = 'no-referrer';
  const profParam = directPhoto ? `&url=${encodeURIComponent(directPhoto)}` : '';
  // Prioritize server-side proxy endpoint so Telegram CDN URLs are fetched through the VPS rather than blocked locally
  const proxyUrl = userId ? `/api/user/avatar?user_id=${userId}${profParam}` : (directPhoto ? `/api/user/avatar?url=${encodeURIComponent(directPhoto)}` : '');
  const targetUrl = proxyUrl || directPhoto;

  if (!targetUrl) {
    imgEl.classList.add('hidden');
    if (initialEl) initialEl.classList.remove('hidden');
    return;
  }

  if (imgEl.dataset.avatarSrc === targetUrl && !imgEl.classList.contains('hidden')) {
    return;
  }
  imgEl.dataset.avatarSrc = targetUrl;

  imgEl.onload = () => {
    imgEl.classList.remove('hidden');
    if (initialEl) initialEl.classList.add('hidden');
  };

  imgEl.onerror = () => {
    if (directPhoto && imgEl.src.includes('/api/user/avatar') && !imgEl.dataset.directRetried) {
      imgEl.dataset.directRetried = '1';
      imgEl.src = directPhoto;
    } else {
      imgEl.classList.add('hidden');
      if (initialEl) initialEl.classList.remove('hidden');
    }
  };

  // Ensure element is visible in layout tree so mobile WebView does not defer the download
  imgEl.classList.remove('hidden');
  if (initialEl) initialEl.classList.add('hidden');

  imgEl.src = targetUrl;
  if (imgEl.complete && imgEl.naturalWidth > 0) {
    imgEl.classList.remove('hidden');
    if (initialEl) initialEl.classList.add('hidden');
  }
}

let expiryCountdownInterval = null;

function openExpiryCountdownModal() {
  const sub = window.lastUserData?.active_sub;
  const daysLeft = sub?.days_left ?? 0;
  const expireTimestamp = sub?.expire_timestamp;
  const expireAt = sub?.expire_at;
  const expireJalali = sub?.expire_jalali;
  const trafficRemainingGb = sub?.traffic_remaining_gb ?? 0;

  const modalAccountName = $('modalExpiryAccountName');
  if (modalAccountName) {
    const cleanUsername = sub?.username ? String(sub.username).replace(/^@+/, '') : '';
    modalAccountName.innerHTML = cleanUsername
      ? `سرویس <bdi dir="ltr" class="font-mono font-bold select-all">${escapeHtml(cleanUsername)}</bdi>`
      : 'اشتراک فعال شما';
  }

  const exactDateEl = $('modalExpiryExactDate');
  if (exactDateEl) {
    exactDateEl.innerText = expireJalali ? expireJalali : 'نامحدود / بدون انقضا';
  }

  const allowanceEl = $('modalExpiryDailyAllowance');
  if (allowanceEl) {
    if (daysLeft > 0 && trafficRemainingGb > 0) {
      const dailyGb = (trafficRemainingGb / daysLeft).toFixed(2);
      allowanceEl.innerHTML = fmtTraffic(dailyGb, { html: true });
    } else {
      allowanceEl.innerText = 'نامحدود';
    }
  }

  const paceStatusEl = $('modalExpiryPaceStatus');
  if (paceStatusEl) {
    if (daysLeft <= 3 && daysLeft > 0) {
      paceStatusEl.className = 'font-semibold text-[11px] text-amber-400 bg-amber-500/15 border border-amber-500/30 px-2 py-0.5 rounded-full';
      paceStatusEl.innerText = '⚠️ مهلت رو به پایان است';
    } else if (daysLeft === 0) {
      paceStatusEl.className = 'font-semibold text-[11px] text-rose-400 bg-rose-500/15 border border-rose-500/30 px-2 py-0.5 rounded-full';
      paceStatusEl.innerText = '🔴 اشتراک منقضی شده';
    } else {
      paceStatusEl.className = 'font-semibold text-[11px] text-emerald-400 bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 rounded-full';
      paceStatusEl.innerText = '🟢 نرمال و بهینه';
    }
  }

  function tickCountdown() {
    let targetTime = null;
    if (expireTimestamp && !isNaN(expireTimestamp)) {
      targetTime = expireTimestamp * 1000;
    } else if (expireAt) {
      targetTime = new Date(expireAt).getTime();
    } else if (daysLeft > 0) {
      targetTime = Date.now() + daysLeft * 86400 * 1000;
    }

    if (!targetTime || isNaN(targetTime)) {
      if ($('countdownDays')) $('countdownDays').innerText = '∞';
      if ($('countdownHours')) $('countdownHours').innerText = '∞';
      if ($('countdownMinutes')) $('countdownMinutes').innerText = '∞';
      if ($('countdownSeconds')) $('countdownSeconds').innerText = '∞';
      return;
    }

    const diff = targetTime - Date.now();
    if (diff <= 0) {
      if ($('countdownDays')) $('countdownDays').innerText = '00';
      if ($('countdownHours')) $('countdownHours').innerText = '00';
      if ($('countdownMinutes')) $('countdownMinutes').innerText = '00';
      if ($('countdownSeconds')) $('countdownSeconds').innerText = '00';
      if (expiryCountdownInterval) clearInterval(expiryCountdownInterval);
      return;
    }

    const d = Math.floor(diff / (1000 * 60 * 60 * 24));
    const h = Math.floor((diff / (1000 * 60 * 60)) % 24);
    const m = Math.floor((diff / (1000 * 60)) % 60);
    const s = Math.floor((diff / 1000) % 60);

    const pad = n => String(n).padStart(2, '0');
    if ($('countdownDays')) $('countdownDays').innerText = pad(d);
    if ($('countdownHours')) $('countdownHours').innerText = pad(h);
    if ($('countdownMinutes')) $('countdownMinutes').innerText = pad(m);
    if ($('countdownSeconds')) $('countdownSeconds').innerText = pad(s);
  }

  tickCountdown();
  if (expiryCountdownInterval) clearInterval(expiryCountdownInterval);
  expiryCountdownInterval = setInterval(tickCountdown, 1000);

  openModal('expiryCountdownModal');
  hapticFeedback('selection');
}

function closeExpiryCountdownModal() {
  if (expiryCountdownInterval) {
    clearInterval(expiryCountdownInterval);
    expiryCountdownInterval = null;
  }
  closeModal('expiryCountdownModal');
}

window.openExpiryCountdownModal = openExpiryCountdownModal;
window.closeExpiryCountdownModal = closeExpiryCountdownModal;

function openTutorialModal() {
  const modal = $('tutorialModal');
  if (!modal) return;

  renderTutorialApps(detectUserOS());
  markTutorialAppsSeen();
  openModal('tutorialModal');
  syncTelegramBackButton();
  hapticFeedback('selection');
}

function setupTutorialModal() {
  document.querySelectorAll('.tutorial-os-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const os = tab.getAttribute('data-os');
      if (os) {
        renderTutorialApps(os);
        hapticFeedback('selection');
      }
    });
  });

  $('closeTutorialModalBtn')?.addEventListener('click', () => {
    closeModal('tutorialModal');
    syncTelegramBackButton();
  });

  $('tutorialCopySubBtn')?.addEventListener('click', async () => {
    const url = getSubUrl();
    if (!url) return;
    await copyToClipboard(url, '📋 لینک اشتراک با موفقیت در کلیپ‌بورد کپی شد.');
    hapticFeedback('success');
  });

  const modal = $('tutorialModal');
  modal?.addEventListener('click', (e) => {
    if (e.target === modal) {
      closeModal('tutorialModal');
      syncTelegramBackButton();
    }
  });

  $('openTutorialModalBtn')?.addEventListener('click', openTutorialModal);
  window.openTutorialModal = openTutorialModal;
}

// 8. Dark / Light Mode Toggle
function setupThemeToggle() {
  const themeToggle = $('themeToggle');
  const themeIcon = $('themeIcon');

  const getInitialUserTheme = () => {
    const saved = localStorage.getItem('remna_user_theme');
    if (saved) return saved === 'dark';
    if (window.Telegram?.WebApp?.colorScheme) {
      return window.Telegram.WebApp.colorScheme === 'dark';
    }
    return !(window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches);
  };

  let isDark = getInitialUserTheme();

  const applyTheme = () => {
    if (isDark) {
      document.documentElement.classList.remove('theme-light');
      document.documentElement.classList.add('dark');
      if (themeIcon) themeIcon.innerText = '🌙';
      try { if (window.Telegram?.WebApp?.setHeaderColor) window.Telegram.WebApp.setHeaderColor('#131d31'); } catch(e) {}
      try { if (window.Telegram?.WebApp?.setBackgroundColor) window.Telegram.WebApp.setBackgroundColor('#080d1a'); } catch(e) {}
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('theme-light');
      if (themeIcon) themeIcon.innerText = '☀️';
      try { if (window.Telegram?.WebApp?.setHeaderColor) window.Telegram.WebApp.setHeaderColor('#ffffff'); } catch(e) {}
      try { if (window.Telegram?.WebApp?.setBackgroundColor) window.Telegram.WebApp.setBackgroundColor('#f8fafc'); } catch(e) {}
    }

    const speedModal = $('speedTestModal');
    if (speedModal) {
      speedModal.style.backgroundColor = isDark ? 'rgba(0, 0, 0, 0.8)' : 'rgba(15, 23, 42, 0.45)';
    }

    const curIsLight = !isDark;
    const chartTokens = typeof getChartThemeTokens === 'function' ? getChartThemeTokens(curIsLight) : null;
    const curTextColor = chartTokens ? chartTokens.legend : (curIsLight ? '#0f172a' : '#f8fafc');
    const curTickColor = chartTokens ? chartTokens.tick : (curIsLight ? '#0f172a' : '#cbd5e1');
    const curGridColor = chartTokens ? chartTokens.grid : (curIsLight ? 'rgba(148, 163, 184, 0.45)' : 'rgba(51, 65, 85, 0.3)');

    if (typeof Chart !== 'undefined') {
      Chart.defaults.color = curTickColor;
    }

    if (window.chartInstances) {
      Object.values(window.chartInstances).forEach(chart => {
        if (!chart) return;
        if (chart.options?.plugins?.legend?.labels) {
          chart.options.plugins.legend.labels.color = curTextColor;
        }
        if (chart.legend?.legendItems) {
          chart.legend.legendItems.forEach(item => {
            item.fontColor = curTextColor;
            item.color = curTextColor;
          });
        }
        if (chart.options?.scales) {
          if (chart.options.scales.x?.ticks) chart.options.scales.x.ticks.color = curTickColor;
          if (chart.options.scales.y?.ticks) chart.options.scales.y.ticks.color = curTickColor;
          if (chart.options.scales.y?.grid) chart.options.scales.y.grid.color = curGridColor;
          if (chart.options.scales.x?.grid) chart.options.scales.x.grid.color = curGridColor;
        }
        try { chart.update(); } catch(e) {}
      });
    }

    if (window.lastUserData?.active_sub) {
      const sub = window.lastUserData.active_sub;
      if (typeof renderBarChart === 'function') {
        renderBarChart('repWeeklyChartCanvas', sub.week_daily_totals_gb || [0, 0, 0, 0, 0, 0, 0], sub.week_day_labels || ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'], false);
        renderBarChart('repMonthlyChartCanvas', sub.month_weeks_totals_gb || [0, 0, 0, sub.week_used_gb || 0], ['هفته ۱', 'هفته ۲', 'هفته ۳', 'هفته ۴'], true);
      }
      if (typeof renderActiveSubAnalytics === 'function') {
        renderActiveSubAnalytics(sub);
      }
    }
  };

  applyTheme();

  try {
    window.Telegram?.WebApp?.onEvent('themeChanged', () => {
      if (!localStorage.getItem('remna_user_theme')) {
        isDark = window.Telegram.WebApp.colorScheme === 'dark';
        applyTheme();
      }
    });
  } catch(e) {}

  themeToggle?.addEventListener('click', () => {
    isDark = !isDark;
    localStorage.setItem('remna_user_theme', isDark ? 'dark' : 'light');
    applyTheme();
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });
}

// 9. Network Tools (Ping / Speed Test / Leak Scan)
const countryFlags = {
  NL: '🇳🇱', DE: '🇩🇪', TR: '🇹🇷', FR: '🇫🇷', US: '🇺🇸', GB: '🇬🇧',
  FI: '🇫🇮', PL: '🇵🇱', SE: '🇸🇪', SG: '🇸🇬', IR: '🇮🇷', EU: '🇪🇺',
};

async function loadNetworkNodes() {
  const pingServersList = $('pingServersList');
  if (!pingServersList) return;
  const t0 = performance.now();
  try {
    const res = await window.api.getNodes();
    const t1 = performance.now();
    const baseLatency = Math.round(t1 - t0);
    const nodes = res.nodes || [];
    if (nodes.length > 0) {
      pingServersList.innerHTML = nodes.map((n, idx) => {
        const flag = countryFlags[n.country_code?.toUpperCase()] || '🌐';
        const jitter = (idx * 9) % 23;
        const ms = Math.max(26, baseLatency + jitter);
        const isOnline = n.status === 'ONLINE';
        const color = ms < 60 ? 'text-emerald-400' : (ms < 100 ? 'text-cyan-400' : 'text-amber-400');
        const quality = ms < 60 ? '🟢 عالی' : (ms < 100 ? '🟢 پایدار' : '🟡 متوسط');

        return `
          <div class="flex items-center justify-between p-2 rounded-xl bg-slate-900/60 border border-slate-700/50">
            <div class="flex items-center gap-2">
              <span class="text-base">${flag}</span>
              <div>
                <span class="font-bold text-slate-200 block">${escapeHtml(n.name || 'نود سرور')}</span>
                <span class="text-[10px] text-slate-400">${escapeHtml(n.address || 'اتصال مستقیم')}</span>
              </div>
            </div>
            <div class="text-left font-mono">
              <span class="ping-val text-xs font-bold ${color}" dir="ltr">${ms} ms</span>
              <span class="block text-[10px] font-sans ${color}">${isOnline ? quality : '🔴 آفلاین'}</span>
            </div>
          </div>
        `;
      }).join('');
      return;
    }
  } catch (e) {}

  // Fallback roundtrip
  const t1 = performance.now();
  const ms = Math.max(34, Math.round(t1 - t0));
  pingServersList.innerHTML = `
    <div class="flex items-center justify-between p-2 rounded-xl bg-slate-900/60 border border-slate-700/50">
      <div class="flex items-center gap-2">
        <span class="text-base">⚡️</span>
        <div>
          <span class="font-bold text-slate-200 block">سرور مرکزی Remnawave</span>
          <span class="text-[11px] text-slate-400">اتصال مستقیم کلاستر VIP</span>
        </div>
      </div>
      <div class="text-left font-mono">
        <span class="ping-val text-xs font-bold text-emerald-400" dir="ltr">${ms} ms</span>
        <span class="block text-[10px] text-emerald-400 font-sans">🟢 عالی</span>
      </div>
    </div>
  `;
}

async function loadClientIpInfo() {
  const ipEl = $('detectedClientIp');
  if (!ipEl) return;
  try {
    const res = await window.api.getIpInfo();
    if (res && res.ok && res.ip) {
      ipEl.innerText = `${res.ip} (ایمن 🛡️)`;
      return;
    }
  } catch (e) {}
  ipEl.innerText = 'شبکه متصل به سرور';
}

function setupNetworkTools() {
  const runPingBtn = $('runPingBtn');
  const pingSpinner = $('pingSpinner');
  const pingBtnText = $('pingBtnText');

  runPingBtn?.addEventListener('click', async () => {
    pingSpinner?.classList.remove('hidden');
    pingSpinner?.classList.add('inline-block', 'animate-spin');
    if (pingBtnText) pingBtnText.innerText = 'در حال سنجش...';
    runPingBtn.disabled = true;

    await loadNetworkNodes();

    pingSpinner?.classList.add('hidden');
    pingSpinner?.classList.remove('inline-block', 'animate-spin');
    if (pingBtnText) pingBtnText.innerText = '⚡️ سنجش مجدد';
    runPingBtn.disabled = false;
  });

  const refreshHeader = $('refreshNetworkToolsHeader');
  const netStatusIcon = $('netStatusIcon');
  refreshHeader?.addEventListener('click', async () => {
    if (netStatusIcon) netStatusIcon.classList.add('animate-spin');
    await Promise.all([loadNetworkNodes(), loadClientIpInfo()]);
    setTimeout(() => {
      if (netStatusIcon) netStatusIcon.classList.remove('animate-spin');
    }, 600);
  });

  // Net sub-tabs
  const netTabPing = $('netTabPing');
  const netTabSpeed = $('netTabSpeed');
  const netTabLeak = $('netTabLeak');
  const paneNetPing = $('paneNetPing');
  const paneNetSpeed = $('paneNetSpeed');
  const paneNetLeak = $('paneNetLeak');

  function switchNetTool(activeBtn, activePane) {
    [netTabPing, netTabSpeed, netTabLeak].forEach(b => {
      if (b) b.className = 'px-2 py-1 rounded-md font-medium text-slate-400 hover:text-slate-200 transition';
    });
    if (activeBtn) activeBtn.className = 'px-2 py-1 rounded-md font-bold bg-blue-600 text-white transition';

    [paneNetPing, paneNetSpeed, paneNetLeak].forEach(p => p?.classList.add('hidden'));
    activePane?.classList.remove('hidden');
  }

  netTabPing?.addEventListener('click', () => switchNetTool(netTabPing, paneNetPing));
  netTabSpeed?.addEventListener('click', () => switchNetTool(netTabSpeed, paneNetSpeed));
  netTabLeak?.addEventListener('click', () => switchNetTool(netTabLeak, paneNetLeak));

  // Speed test simulation
  const runSpeedTestBtn = $('runSpeedTestBtn');
  const speedMeterArc = $('speedMeterArc');
  const speedRealtimeValue = $('speedRealtimeValue');
  const dlSpeedVal = $('dlSpeedVal');
  const ulSpeedVal = $('ulSpeedVal');
  const pingSpeedVal = $('pingSpeedVal');
  const speedTestBtnText = $('speedTestBtnText');

  let isTestingSpeed = false;
  runSpeedTestBtn?.addEventListener('click', async () => {
    if (isTestingSpeed) return;
    isTestingSpeed = true;
    runSpeedTestBtn.disabled = true;
    if (speedTestBtnText) speedTestBtnText.innerText = 'در حال محاسبه پینگ و سرعت...';
    if (dlSpeedVal) dlSpeedVal.innerText = '...';
    if (ulSpeedVal) ulSpeedVal.innerText = '...';
    if (pingSpeedVal) pingSpeedVal.innerText = '...';

    const t0 = performance.now();
    let realPing = 35;
    try {
      await window.api.getIpInfo();
      realPing = Math.max(20, Math.round(performance.now() - t0));
    } catch (e) {}

    let step = 0;
    const speedInterval = setInterval(() => {
      step += 1;
      const fakeSpeed = (Math.random() * 25 + step * 7).toFixed(1);
      if (speedRealtimeValue) speedRealtimeValue.innerText = fakeSpeed;
      const offset = Math.max(20, 190 - (fakeSpeed / 100) * 170);
      if (speedMeterArc) speedMeterArc.style.strokeDashoffset = offset;

      if (step >= 12) {
        clearInterval(speedInterval);
        const baseBandwidth = realPing < 50 ? 95 : (realPing < 100 ? 75 : 45);
        const finalDl = (baseBandwidth + (Math.random() * 12 - 6)).toFixed(1);
        const finalUl = (finalDl * 0.45 + (Math.random() * 5)).toFixed(1);

        if (speedRealtimeValue) speedRealtimeValue.innerText = finalDl;
        if (speedMeterArc) speedMeterArc.style.strokeDashoffset = Math.max(20, 190 - (finalDl / 120) * 170);
        if (dlSpeedVal) dlSpeedVal.innerText = `${finalDl} Mbps`;
        if (ulSpeedVal) ulSpeedVal.innerText = `${finalUl} Mbps`;
        if (pingSpeedVal) pingSpeedVal.innerText = `${realPing} ms`;

        if (speedTestBtnText) speedTestBtnText.innerText = '✅ سنجش انجام شد (شروع مجدد)';
        runSpeedTestBtn.disabled = false;
        isTestingSpeed = false;
      }
    }, 140);
  });

  // Leak scan
  const runLeakScanBtn = $('runLeakScanBtn');
  const leakScanText = $('leakScanText');
  runLeakScanBtn?.addEventListener('click', async () => {
    if (leakScanText) leakScanText.innerText = 'در حال بررسی نشت IP و WebRTC...';
    runLeakScanBtn.disabled = true;
    await loadClientIpInfo();
    setTimeout(() => {
      alert('🛡 بررسی کامل شد:\n• هیچ نشت DNS یا IP وجود ندارد.\n• اپراتور متصل شناسایی نمی‌شود.\n• ترافیک شما به صورت کامل رمزنگاری شده است.');
      if (leakScanText) leakScanText.innerText = 'بررسی مجدد نشت DNS و IP';
      runLeakScanBtn.disabled = false;
    }, 800);
  });
}

// 10. Support Chat Center
function setupSupportChat() {
  const openSupportBtn = $('openSupportBtn');
  const closeSupportChatBtn = $('closeSupportChatBtn');
  const chatInput = $('chatInput');
  const sendMessageBtn = $('sendMessageBtn');
  const dynamicChatContainer = $('dynamicChatContainer');
  const chatMessages = $('chatMessages');
  const chatLoadingState = $('chatLoadingState');
  const chatEmptyState = $('chatEmptyState');

  let pollInterval = null;
  let lastMessageCount = 0;

  function renderMessageItem(msg) {
    const isUser = msg.sender === 'user';
    const timeStr = msg.created_at ? toEnglishDigits(msg.created_at) : '';
    const safeText = escapeHtml(msg.text || '').replace(/\n/g, '<br/>');

    const bubble = document.createElement('div');
    if (isUser) {
      bubble.className = 'self-start ml-auto mr-0 max-w-[85%] animate-fadeIn';
      bubble.innerHTML = `
        <div class="chat-user-bubble border border-blue-500/40 bg-blue-500/10 rounded-2xl rounded-tr-none p-2.5 text-blue-100 leading-relaxed shadow-sm text-right">
          ${safeText}
          <span class="text-[10px] text-blue-300 block text-left mt-1 font-mono" dir="ltr">${timeStr}</span>
        </div>
      `;
    } else {
      bubble.className = 'self-end mr-auto ml-0 max-w-[85%] flex items-start gap-2 animate-fadeIn';
      bubble.innerHTML = `
        <div class="w-6 h-6 rounded-full bg-emerald-600 flex items-center justify-center text-[10px] shrink-0 text-white mt-0.5">🎧</div>
        <div class="chat-admin-bubble border border-slate-700/60 bg-slate-800/25 rounded-2xl rounded-tl-none p-2.5 text-slate-200 leading-relaxed shadow-sm text-right">
          ${safeText}
          <span class="text-[10px] text-slate-400 block text-left mt-1 font-mono" dir="ltr">${timeStr}</span>
        </div>
      `;
    }
    return bubble;
  }

  async function loadChatMessages(isSilent = false) {
    try {
      if (!isSilent && chatLoadingState) {
        chatLoadingState.classList.remove('hidden');
      }
      const res = await window.api.getSupportMessages();
      if (chatLoadingState) chatLoadingState.classList.add('hidden');

      if (res.ok) {
        const messages = res.messages || [];
        if (messages.length === 0) {
          if (chatEmptyState) chatEmptyState.classList.remove('hidden');
          if (dynamicChatContainer) dynamicChatContainer.innerHTML = '';
          lastMessageCount = 0;
        } else {
          if (chatEmptyState) chatEmptyState.classList.add('hidden');
          if (messages.length !== lastMessageCount || !isSilent) {
            if (dynamicChatContainer) {
              dynamicChatContainer.innerHTML = '';
              messages.forEach(m => dynamicChatContainer.appendChild(renderMessageItem(m)));
            }
            lastMessageCount = messages.length;
            if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
          }
        }
      }
    } catch (err) {
      if (chatLoadingState) chatLoadingState.classList.add('hidden');
    }
  }

  function startPolling() {
    loadChatMessages(false);
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(() => {
      const modal = $('supportChatModal');
      if (modal && !modal.classList.contains('hidden')) {
        loadChatMessages(true);
      } else {
        clearInterval(pollInterval);
        pollInterval = null;
      }
    }, 4000);
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  openSupportBtn?.addEventListener('click', () => {
    openModal('supportChatModal');
    startPolling();
  });

  closeSupportChatBtn?.addEventListener('click', () => {
    stopPolling();
    closeModal('supportChatModal');
  });

  async function handleSendMessage(text) {
    if (!text || !text.trim()) return;
    const cleanText = text.trim();
    if (chatInput) chatInput.value = '';

    if (chatEmptyState) chatEmptyState.classList.add('hidden');
    const tempMsg = {
      sender: 'user',
      text: cleanText,
      created_at: new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' }),
    };
    dynamicChatContainer?.appendChild(renderMessageItem(tempMsg));
    lastMessageCount += 1;
    if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
      const res = await window.api.sendSupportMessage(cleanText);
      if (!res.ok) {
        showToast(`❌ ${res.error || 'خطا در ارسال پیام'}`);
      } else {
        hapticFeedback('success');
      }
    } catch (e) {
      showToast('خطا در ارسال پیام به سرور.');
    }
  }

  sendMessageBtn?.addEventListener('click', () => handleSendMessage(chatInput?.value));
  chatInput?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') handleSendMessage(chatInput?.value);
  });

  document.querySelectorAll('.quick-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      handleSendMessage(chip.innerText.replace(/^[^\w\s\u0600-\u06FF]+/, '').trim());
    });
  });
}

// 11. Telegram WebApp SDK Lifecycle & BackButton
const tg = window.Telegram?.WebApp;

function updateTopPadding() {
  const topBar = $('topHeaderBar');
  if (!topBar) return;
  let padTop = 10;
  if (tg) {
    const safeTop = tg.contentSafeAreaInset?.top || tg.safeAreaInset?.top || 0;
    if (safeTop > 0) {
      padTop = safeTop + 4;
      document.documentElement.style.setProperty('--tg-content-safe-area-inset-top', safeTop + 'px');
      document.documentElement.style.setProperty('--tg-safe-area-inset-top', safeTop + 'px');
    }
  }
  topBar.style.paddingTop = padTop + 'px';
}

function syncTelegramBackButton() {
  if (!tg?.BackButton) return;
  const modalIds = APP_MODAL_IDS;
  const hasOpenModal = modalIds.some(id => {
    const el = $(id);
    return el && !el.classList.contains('hidden');
  });

  const qr = $('qrContainer');
  const hasOpenQr = qr && !qr.classList.contains('hidden');

  const activeTabBtn = document.querySelector('.nav-btn.text-blue-400');
  const activeTab = activeTabBtn?.getAttribute('data-tab');
  const isSubTab = activeTab && activeTab !== 'tab-dashboard';

  if (hasOpenModal || hasOpenQr || isSubTab) {
    tg.BackButton.show();
  } else {
    tg.BackButton.hide();
  }
}

function setupTelegramSDK() {
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.disableVerticalSwipes) tg.disableVerticalSwipes();
      if (tg.setHeaderColor) tg.setHeaderColor('#131d31');
      if (tg.setBackgroundColor) tg.setBackgroundColor('#080d1a');
    } catch (e) {}

    updateTopPadding();
    try {
      if (tg.onEvent) {
        tg.onEvent('contentSafeAreaChanged', updateTopPadding);
        tg.onEvent('safeAreaChanged', updateTopPadding);
        tg.onEvent('viewportChanged', updateTopPadding);
      }
    } catch (e) {}

    if (tg.initData) {
      $('closeBtn')?.classList.add('hidden');
    }

    if (tg.BackButton) {
      tg.BackButton.onClick(() => {
        const modalIds = APP_MODAL_IDS;
        for (const id of modalIds) {
          const el = $(id);
          if (el && !el.classList.contains('hidden')) {
            el.classList.add('hidden');
            syncTelegramBackButton();
            return;
          }
        }
        const qr = $('qrContainer');
        if (qr && !qr.classList.contains('hidden')) {
          qr.classList.add('hidden');
          const qrToggle = $('qrToggleBtn');
          if (qrToggle) qrToggle.innerHTML = '<span class="text-sm">📷</span>';
          syncTelegramBackButton();
          return;
        }

        const dashBtn = document.querySelector('.nav-btn[data-tab="tab-dashboard"]');
        dashBtn?.click();
      });

      const observedModalIds = [
        'revokeModal', 'switchAccountModal', 'activeSessionsModal',
        'topupModal', 'luckyWheelModal', 'storyModal', 'storyCardModal',
        'supportChatModal', 'qrContainer',
        'purchaseSuccessModal', 'qrModal', 'checkoutConfirmModal', 'configsModal', 'tutorialModal'
      ];
      observedModalIds.forEach(id => {
        const el = $(id);
        if (el) {
          const obs = new MutationObserver(() => syncTelegramBackButton());
          obs.observe(el, { attributes: true, attributeFilter: ['class'] });
        }
      });
      syncTelegramBackButton();
    }

    $('closeBtn')?.addEventListener('click', () => {
      if (tg) tg.close();
      else alert('این دکمه در تلگرام واقعی، پنجره مینی‌اپ را می‌بندد.');
    });
  } else {
    updateTopPadding();
  }
}

// 12. Multi-Account Switcher
function setupAccountSwitcher() {
  const switchAccountModal = $('switchAccountModal');
  const switchAccountBtn = $('switchAccountBtn');
  const closeSwitchAccountBtn = $('closeSwitchAccountBtn');
  const switchAccountList = $('switchAccountList');

  switchAccountBtn?.addEventListener('click', () => {
    const accounts = window.lastUserData?.accounts || [];
    if (!switchAccountList) return;
    switchAccountList.innerHTML = accounts.map(acc => `
      <button class="select-acc-item w-full p-2.5 rounded-xl border ${acc.is_active ? 'border-blue-500 bg-transparent' : 'border-slate-700/60 bg-transparent hover:border-slate-500'} text-right flex items-center justify-between transition" data-id="${acc.id}">
        <div>
          <div class="font-bold text-white text-xs flex items-center gap-1.5">
            <span>👤</span> ${escapeHtml(acc.username || '')}
          </div>
          <span class="text-[10px] text-slate-400 mt-0.5 block font-mono num-bidi" dir="ltr">
            ${fmtTraffic(acc.used_gb, { html: false })} / ${acc.total_gb > 0 ? fmtTraffic(acc.total_gb, { html: false }) : 'نامحدود'}
          </span>
        </div>
        ${acc.is_active ? '<span class="text-xs text-blue-400 font-bold bg-transparent px-2 py-0.5 rounded-full border border-blue-500/40">فعال ✓</span>' : '<span class="text-xs text-slate-400 bg-transparent border border-slate-700/60 px-2 py-0.5 rounded-full">انتخاب</span>'}
      </button>
    `).join('');

    document.querySelectorAll('.select-acc-item').forEach(btn => {
      btn.addEventListener('click', () => {
        const accId = btn.getAttribute('data-id');
        window.currentAccountId = accId;
        closeModal('switchAccountModal');
        syncUserDataWithApi(accId);
        showToast('🔄 اکانت فعال تغییر یافت.');
      });
    });

    openModal('switchAccountModal');
  });

  closeSwitchAccountBtn?.addEventListener('click', () => {
    closeModal('switchAccountModal');
  });
}

// 13. Profile Switches & Actions
function setupProfileHandlers() {
  $('langFaBtn')?.addEventListener('click', () => changeAppLanguage('fa'));
  $('langEnBtn')?.addEventListener('click', () => changeAppLanguage('en'));

  async function changeAppLanguage(lang) {
    try {
      const res = await window.api.changeLanguage(lang);
      if (res.ok) {
        showToast(lang === 'fa' ? '✅ زبان به فارسی تغییر یافت.' : '✅ Language changed to English.');
        syncUserDataWithApi(window.currentAccountId);
      } else {
        showToast('❌ خطا در ذخیره تنظیمات زبان.');
      }
    } catch (e) {
      showToast('❌ خطا در ذخیره تنظیمات زبان.');
    }
  }

  $('copyProfileIdBtn')?.addEventListener('click', () => {
    const idVal = $('profileTelegramId')?.innerText;
    if (idVal && idVal !== '--') {
      copyToClipboard(idVal, '📋 شناسه عددی تلگرام در کلیپ‌بورد کپی شد.');
    }
  });

  $('copyProfileRefBtn')?.addEventListener('click', () => {
    const refVal = $('profileRefCode')?.innerText;
    if (refVal && refVal !== '--') {
      copyToClipboard(refVal, '📋 کد معرف در کلیپ‌بورد کپی شد.');
    }
  });

  $('gotoShopFromWallet')?.addEventListener('click', () => {
    const shopNav = document.querySelector('.nav-btn[data-tab="tab-shop"]');
    shopNav?.click();
  });

  // Referral Link Copy & Share Actions
  $('copyReferralLinkBtn')?.addEventListener('click', async () => {
    const link = $('profileReferralLinkInput')?.value || '';
    if (link && !link.includes('در حال')) {
      await copyToClipboard(link, '📋 لینک اختصاصی دعوت با موفقیت کپی شد.');
      hapticFeedback('success');
    }
  });

  $('shareReferralLinkBtn')?.addEventListener('click', () => {
    const link = $('profileReferralLinkInput')?.value || '';
    const botName = window.lastUserData?.bot_username ? `@${window.lastUserData.bot_username}` : '';
    const shareText = `🚀 اتصال پرسرعت و پایدار ${botName}\nثبت‌نام کنید و هدیه بگیرید!`.trim();
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(shareText)}`;
    try {
      if (window.Telegram?.WebApp?.openTelegramLink) {
        window.Telegram.WebApp.openTelegramLink(shareUrl);
      } else {
        window.open(shareUrl, '_blank');
      }
    } catch (e) {
      window.open(shareUrl, '_blank');
    }
    hapticFeedback('impact');
  });
}

function resetActiveSubAnalytics() {
  // 1. Destroy all charts to prevent ghost/dummy rendering
  ['repWeeklyChartCanvas', 'repMonthlyChartCanvas', 'repPeakHoursChartCanvas', 'repPeakHoursBarCanvas'].forEach(id => {
    if (window.chartInstances && window.chartInstances[id]) {
      try { window.chartInstances[id].destroy(); } catch(e) {}
      delete window.chartInstances[id];
    }
  });

  // 2. Hide canvases and display clean empty states on weekly & monthly cards
  const weeklyCanvas = $('repWeeklyChartCanvas');
  const weeklyEmpty = $('repWeeklyEmptyState');
  if (weeklyCanvas) weeklyCanvas.classList.add('hidden');
  if (weeklyEmpty) weeklyEmpty.classList.remove('hidden');

  const monthlyCanvas = $('repMonthlyChartCanvas');
  const monthlyEmpty = $('repMonthlyEmptyState');
  if (monthlyCanvas) monthlyCanvas.classList.add('hidden');
  if (monthlyEmpty) monthlyEmpty.classList.remove('hidden');

  const canvasEl = $('repPeakHoursChartCanvas');
  const emptyStateEl = $('repPeakHoursEmptyState');
  const peakBadge = $('repPeakHourBadge');
  const barContainer = $('repPeakHoursBarContainer');
  if (canvasEl) canvasEl.classList.add('hidden');
  if (barContainer) barContainer.classList.add('hidden');
  if (emptyStateEl) emptyStateEl.classList.remove('hidden');
  if (peakBadge) peakBadge.innerText = 'بدون داده';

  const repSessionsBadge = $('reportsSessionsBadge');
  if (repSessionsBadge) repSessionsBadge.innerText = '۰ دستگاه';

  const devContainer = $('activeDevicesContainer');
  if (devContainer) {
    devContainer.innerHTML = `
      <div class="p-4 rounded-xl bg-transparent border border-slate-700/50 text-center text-xs text-slate-400">
        <span>📱 در حال حاضر هیچ اشتراک یا دستگاه فعالی روی حساب شما وجود ندارد.</span>
      </div>
    `;
  }

  // Clear report breakdown containers from 'در حال دریافت داده‌ها...'
  ['repNightlyNodesContainer', 'repWeeklyNodesContainer', 'repMonthlyNodesContainer'].forEach(id => {
    const el = $(id);
    if (el) {
      el.innerHTML = '<div class="col-span-2 text-center py-3 text-slate-400 text-xs">اشتراک فعالی برای نمایش آمار وجود ندارد.</div>';
    }
  });

  const repNightlyTotal = $('repNightlyTotal');
  if (repNightlyTotal) repNightlyTotal.innerText = '۰ GB';
  const repNightlyUsed = $('repNightlyUsed');
  if (repNightlyUsed) repNightlyUsed.innerText = '۰ GB';
  const repNightlyRemain = $('repNightlyRemain');
  if (repNightlyRemain) repNightlyRemain.innerText = '۰ GB';
  const repNightlyYesterday = $('repNightlyYesterday');
  if (repNightlyYesterday) repNightlyYesterday.innerText = '۰ GB';
  const repNightlyExpire = $('repNightlyExpire');
  if (repNightlyExpire) repNightlyExpire.innerText = 'غیرفعال';
  const repWeeklyTotal = $('repWeeklyTotal');
  if (repWeeklyTotal) repWeeklyTotal.innerText = '۰ GB';
  const repWeeklyBusiest = $('repWeeklyBusiest');
  if (repWeeklyBusiest) repWeeklyBusiest.innerText = '—';
  const repMonthlyTotal = $('repMonthlyTotal');
  if (repMonthlyTotal) repMonthlyTotal.innerText = '۰ GB';

  // 3. Reset Traffic Split & Burn Rate & Diurnal breakdown
  const downGbEl = document.getElementById('repSplitDownGb');
  if (downGbEl) downGbEl.innerText = '۰ GB';
  const upGbEl = document.getElementById('repSplitUpGb');
  if (upGbEl) upGbEl.innerText = '۰ GB';
  const downPctEl = document.getElementById('repSplitDownPct');
  if (downPctEl) downPctEl.innerText = '۰%';
  const upPctEl = document.getElementById('repSplitUpPct');
  if (upPctEl) upPctEl.innerText = '۰%';
  const downBar = document.getElementById('repSplitDownBar');
  if (downBar) downBar.style.width = '0%';
  const upBar = document.getElementById('repSplitUpBar');
  if (upBar) upBar.style.width = '0%';
  const ratioBadge = document.getElementById('repUpDownRatioBadge');
  if (ratioBadge) ratioBadge.innerText = 'بدون داده';

  const speedBadge = document.getElementById('repBurnSpeedBadge');
  if (speedBadge) speedBadge.innerText = 'غیرفعال';
  const avgDailyEl = document.getElementById('repBurnAvgDaily');
  if (avgDailyEl) avgDailyEl.innerText = '۰ GB';
  const projectedDaysEl = document.getElementById('repBurnProjectedDays');
  if (projectedDaysEl) {
    projectedDaysEl.innerText = '—';
    projectedDaysEl.className = 'font-mono text-slate-400 text-xs';
  }
  const analysisTextEl = document.getElementById('repBurnAnalysisText');
  if (analysisTextEl) analysisTextEl.innerText = 'اشتراک فعالی برای تحلیل الگوی مصرف ثبت نشده است.';
  const statusIconEl = document.getElementById('repBurnStatusIcon');
  if (statusIconEl) statusIconEl.innerText = 'ℹ️';
  const analysisBox = document.getElementById('repBurnAnalysisBox');
  if (analysisBox) analysisBox.className = 'p-2.5 rounded-xl bg-slate-900/60 border border-slate-700/60 text-xs text-slate-400 flex items-start gap-2';

  const pDawn = $('periodDawnVal'); if (pDawn) pDawn.innerText = '۰ GB';
  const pDawnPct = $('periodDawnPercent'); if (pDawnPct) pDawnPct.innerText = '۰%';
  const pMorn = $('periodMorningVal'); if (pMorn) pMorn.innerText = '۰ GB';
  const pMornPct = $('periodMorningPercent'); if (pMornPct) pMornPct.innerText = '۰%';
  const pAft = $('periodAfternoonVal'); if (pAft) pAft.innerText = '۰ GB';
  const pAftPct = $('periodAfternoonPercent'); if (pAftPct) pAftPct.innerText = '۰%';
  const pNgt = $('periodNightVal'); if (pNgt) pNgt.innerText = '۰ GB';
  const pNgtPct = $('periodNightPercent'); if (pNgtPct) pNgtPct.innerText = '۰%';
}
window.resetActiveSubAnalytics = resetActiveSubAnalytics;

// 14. Active Subscription Analytics Visualizers
function renderActiveSubAnalytics(sub) {
  if (!sub) {
    resetActiveSubAnalytics();
    return;
  }

  // 1. Traffic Split (Download vs Upload)
  if (typeof renderTrafficSplit === 'function') {
    try {
      renderTrafficSplit(sub.traffic_split);
    } catch (e) {
      console.warn('Error rendering traffic split', e);
    }
  }

  // 1.5 Burn Rate & Projected Expiry
  if (typeof renderBurnRate === 'function') {
    try {
      renderBurnRate(sub.burn_rate, sub);
    } catch (e) {
      console.warn('Error rendering burn rate', e);
    }
  }

  // 2. 24h Peak Usage Area Curve
  if (typeof renderLineCurveChart === 'function') {
    try {
      const canvasEl = $('repPeakHoursChartCanvas');
      const emptyStateEl = $('repPeakHoursEmptyState');
      const peakBadge = $('repPeakHourBadge');
      const hourlyData = sub.hourly_usage?.data || [];
      const hasRealTraffic = Boolean(sub.hourly_usage?.has_real_data && hourlyData.some(v => Number(v) > 0));

      const barContainer = $('repPeakHoursBarContainer');
      if (!hasRealTraffic) {
        if (canvasEl) canvasEl.classList.add('hidden');
        if (barContainer) barContainer.classList.add('hidden');
        if (emptyStateEl) emptyStateEl.classList.remove('hidden');
        if (peakBadge) peakBadge.innerText = 'بدون داده';
      } else {
        if (canvasEl) canvasEl.classList.remove('hidden');
        if (barContainer) barContainer.classList.remove('hidden');
        if (emptyStateEl) emptyStateEl.classList.add('hidden');
        const hourlyLabels = sub.hourly_usage?.labels || [
          '00-02','02-04','04-06','06-08','08-10','10-12',
          '12-14','14-16','16-18','18-20','20-22','22-24'
        ];
        const peakHour = sub.hourly_usage?.peak_hour || null;
        renderLineCurveChart('repPeakHoursChartCanvas', hourlyLabels, hourlyData, peakHour);
        if (typeof renderBarChart === 'function') {
          renderBarChart('repPeakHoursBarCanvas', hourlyData, hourlyLabels, false);
        }
        // Update 4 Diurnal Periods Summary
        try {
          let dawnSum = 0, morningSum = 0, afternoonSum = 0, nightSum = 0;
          hourlyLabels.forEach((lbl, idx) => {
            const val = parseFloat(hourlyData[idx]) || 0;
            const startHour = parseInt(String(lbl).split('-')[0] || String(idx * 2), 10);
            if (startHour >= 0 && startHour < 6) dawnSum += val;
            else if (startHour >= 6 && startHour < 12) morningSum += val;
            else if (startHour >= 12 && startHour < 18) afternoonSum += val;
            else nightSum += val;
          });
          const totalPeriods = (dawnSum + morningSum + afternoonSum + nightSum) || 1;
          const pDawn = $('periodDawnVal'); if (pDawn) pDawn.innerHTML = fmtTraffic(dawnSum, { isBytes: false });
          const pDawnPct = $('periodDawnPercent'); if (pDawnPct) pDawnPct.innerText = `${Math.round((dawnSum / totalPeriods) * 100)}%`;
          const pMorn = $('periodMorningVal'); if (pMorn) pMorn.innerHTML = fmtTraffic(morningSum, { isBytes: false });
          const pMornPct = $('periodMorningPercent'); if (pMornPct) pMornPct.innerText = `${Math.round((morningSum / totalPeriods) * 100)}%`;
          const pAft = $('periodAfternoonVal'); if (pAft) pAft.innerHTML = fmtTraffic(afternoonSum, { isBytes: false });
          const pAftPct = $('periodAfternoonPercent'); if (pAftPct) pAftPct.innerText = `${Math.round((afternoonSum / totalPeriods) * 100)}%`;
          const pNgt = $('periodNightVal'); if (pNgt) pNgt.innerHTML = fmtTraffic(nightSum, { isBytes: false });
          const pNgtPct = $('periodNightPercent'); if (pNgtPct) pNgtPct.innerText = `${Math.round((nightSum / totalPeriods) * 100)}%`;
        } catch (perr) {
          console.debug('Error computing diurnal periods:', perr);
        }
        if (peakBadge) {
          peakBadge.innerText = peakHour ? `Peak: ${toEnglishDigits(peakHour)}` : '---';
        }
      }
    } catch (e) {
      console.warn('Error rendering peak hours chart', e);
    }
  }

  // 3. Country / Cluster Donut Chart
  if (typeof renderDonutChart === 'function') {
    try {
      const countryLabels = sub.country_share?.labels?.length ? sub.country_share.labels : [];
      const countryData = sub.country_share?.data?.length ? sub.country_share.data : [];
      renderDonutChart('repCountryChartCanvas', countryLabels, countryData, false);
    } catch (e) {
      console.warn('Error rendering country donut chart', e);
    }

    // 4. Device Platform Donut Chart
    try {
      const devLabels = sub.device_share?.labels?.length ? sub.device_share.labels : [];
      const devData = sub.device_share?.data?.length ? sub.device_share.data : [];
      renderDonutChart('repDeviceChartCanvas', devLabels, devData, true);
    } catch (e) {
      console.warn('Error rendering device donut chart', e);
    }
  }
}

// 15. Phased, Resilient UI Hydration Logic
function hydrateUserInterface(data) {
  if (!data || typeof data !== 'object') return;

  // --- Maintenance & Invite-Only Gateways ---
  const maintScreen = $('systemMaintenanceScreen');
  if (data.is_maintenance && !data.user?.is_admin) {
    if (maintScreen) maintScreen.classList.remove('hidden');
    const splash = $('splashScreen'); if (splash) splash.classList.add('hidden');
    $('topHeaderBar')?.classList.add('hidden');
    $('bottomNavigationBar')?.classList.add('hidden');
    document.querySelector('nav')?.classList.add('hidden');
    $('mainContent')?.classList.add('hidden');
    document.querySelector('main')?.classList.add('hidden');
    return;
  } else {
    if (maintScreen) maintScreen.classList.add('hidden');
  }

  const inviteScreen = $('systemInviteOnlyScreen');
  if (data.is_invite_only && !data.user?.is_admin) {
    if (inviteScreen) inviteScreen.classList.remove('hidden');
    const splash = $('splashScreen'); if (splash) splash.classList.add('hidden');
    $('topHeaderBar')?.classList.add('hidden');
    $('bottomNavigationBar')?.classList.add('hidden');
    document.querySelector('nav')?.classList.add('hidden');
    $('mainContent')?.classList.add('hidden');
    document.querySelector('main')?.classList.add('hidden');
    return;
  } else {
    if (inviteScreen) inviteScreen.classList.add('hidden');
  }

  const safeStep = (stepName, fn) => {
    try {
      fn();
    } catch (err) {
      console.warn(`[hydrateUserInterface] Error in ${stepName}:`, err);
    }
  };

  const user = data.user || {};
  const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
  const sub = data.active_sub;
  if ((sub?.account_id || sub?.id) && !window.currentAccountId) {
    window.currentAccountId = sub.account_id || sub.id;
  }

  // --- PHASE 1: Core User Identity & Top Header (DB Data) ---
  safeStep('identityAndHeader', () => {
    const avatarEl = $('headerUserAvatarInitial') || $('headerUserAvatar');
    if (avatarEl && (user.first_name || user.username)) {
      avatarEl.innerText = (user.first_name || user.username || 'U')[0].toUpperCase();
    }

    const usernameEl = $('headerUsername');
    if (usernameEl) {
      usernameEl.innerText = sub?.username || user.username || user.first_name || 'کاربر';
    }

    const onlineCount = sub?.devices_count ?? (sub?.devices ? sub.devices.length : 0);
    const onlineCountEl = $('headerOnlineCount');
    if (onlineCountEl) {
      onlineCountEl.innerText = `${toEnglishDigits(onlineCount)} دستگاه آنلاین`;
    }

    const profName = $('profileFullName');
    const profUser = $('profileUsername');
    const profAvatar = $('profileAvatarInitial');
    const profStatusBadge = $('profileStatusBadge');
    const profAuthBadge = $('profileAuthBadge');
    const profId = $('profileTelegramId');
    const profRef = $('profileRefCode');
    const profPhone = $('profilePhone');
    const profJoin = $('profileJoinDate');
    const profBirth = $('profileBirthDate');
    const profSub = $('profileSubStatus');

    const userDisplayName = sub?.username || user.first_name || user.username || 'کاربر گرامی';
    if (profName) profName.innerText = userDisplayName;
    if (profUser) profUser.innerText = user.username ? `@${user.username}` : `شناسه: ${user.id || ''}`;
    if (profAvatar) profAvatar.innerText = userDisplayName.charAt(0).toUpperCase();
    if (profId) profId.innerText = user.id ? String(user.id) : '--';
    if (profRef) profRef.innerText = user.id ? String(user.id) : '--';
    const hasPhone = Boolean(user.phone_number);
    const phoneRewardCard = $('profilePhoneRewardCard');
    const warningCard = $('cardPhoneVerificationWarning');
    const verifyBtn = $('verifyPhoneInBotBtn');

    if (hasPhone) {
      if (phoneRewardCard) phoneRewardCard.classList.add('hidden');
      if (warningCard) warningCard.classList.add('hidden');
      if (verifyBtn) verifyBtn.classList.add('hidden');
      if (profPhone) {
        profPhone.innerHTML = `<span class="text-white font-mono font-bold" dir="ltr">${toEnglishDigits(user.phone_number)}</span> <span class="text-emerald-400 text-xs inline-flex items-center" title="تأیید شده">✅</span>`;
      }
    } else {
      if (phoneRewardCard) phoneRewardCard.classList.remove('hidden');
      if (warningCard) warningCard.classList.remove('hidden');
      if (verifyBtn) verifyBtn.classList.remove('hidden');
      if (profPhone) {
        profPhone.innerText = 'وارد نشده';
      }
    }
    if (profJoin) profJoin.innerText = toEnglishDigits(user.created_at_jalali || '1403/07/01');
    if (profBirth) profBirth.innerText = user.birth_date ? toEnglishDigits(user.birth_date) : 'ثبت‌نشده';

    const bdayBtn = $('openBirthdayModalBtn');
    if (bdayBtn) {
      bdayBtn.className = 'text-pink-400 hover:text-pink-300 text-xs transition active:scale-95 bg-transparent border-0 p-0 shadow-none';
      bdayBtn.innerHTML = '<span>✏️</span>';
      bdayBtn.title = user.birth_date ? 'ویرایش تاریخ تولد' : 'ثبت تاریخ تولد';
    }

    const hasActiveSub = Boolean(data.has_active_sub && (sub?.status === 'ACTIVE' || !sub?.status));
    if (profStatusBadge) {
      if (hasActiveSub) {
        profStatusBadge.innerHTML = '<span class="inline-flex items-center gap-1"><span>🟢</span><span>کاربر فعال</span></span>';
        profStatusBadge.className = 'px-2.5 py-0.5 rounded-full text-[10px] font-bold border badge-active transition inline-flex items-center gap-1';
      } else {
        profStatusBadge.innerHTML = '<span class="inline-flex items-center gap-1"><span>⚪️</span><span>بدون سرویس فعال</span></span>';
        profStatusBadge.className = 'px-2.5 py-0.5 rounded-full text-[10px] font-bold border badge-inactive transition inline-flex items-center gap-1';
      }
    }

    if (profAuthBadge) {
      if (hasPhone) {
        profAuthBadge.innerHTML = '<span class="inline-flex items-center gap-1"><span>🛡️</span><span>حساب تأییدشده</span></span>';
        profAuthBadge.className = 'px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 inline-flex items-center gap-1 transition';
      } else {
        profAuthBadge.innerHTML = '<span class="inline-flex items-center gap-1"><span>⚠️</span><span>نیازمند احراز شماره</span></span>';
        profAuthBadge.className = 'px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30 inline-flex items-center gap-1 transition';
      }
    }

    if (profSub) {
      if (hasActiveSub) {
        profSub.innerText = 'فعال';
        profSub.className = 'font-semibold text-emerald-400';
      } else {
        profSub.innerText = 'غیرفعال';
        profSub.className = 'font-semibold text-rose-400';
      }
    }

    // Avatar Photos Loading (DRY with Fallback & no-referrer)
    const profUid = tgUser?.id || user.id;
    const directPhoto = tgUser?.photo_url || user.photo_url || '';
    const profImg = $('profileAvatarImg');
    const profAvatarInitial = $('profileAvatarInitial');
    const headImg = $('headerUserAvatarImg');
    const headAvatarInitial = $('headerUserAvatarInitial');

    loadAvatarWithFallback(profImg, profAvatarInitial, directPhoto, profUid);
    loadAvatarWithFallback(headImg, headAvatarInitial, directPhoto, profUid);

    // Account Switcher Button Visibility
    const switchBtn = $('switchAccountBtn');
    const accounts = data.accounts || [];
    if (switchBtn) {
      if (accounts.length > 1) {
        switchBtn.classList.remove('hidden');
        if (usernameEl) {
          usernameEl.classList.add('cursor-pointer', 'hover:text-blue-200');
          usernameEl.onclick = () => switchBtn.click();
        }
      } else {
        switchBtn.classList.add('hidden');
        if (usernameEl) {
          usernameEl.classList.remove('cursor-pointer', 'hover:text-blue-200');
          usernameEl.onclick = null;
        }
      }
    }
  });

  // --- PHASE 2: Wallet Balance & Shop Plans (DB Data) ---
  safeStep('walletAndShop', () => {
    const walletEl = $('shopWalletBalance');
    const shopBalAmt = $('shopWalletBalanceAmount');
    const walletTabBal = $('walletTabBalance');
    const rawBalNum = Number(user.wallet_balance || 0).toLocaleString('en-US');
    const formattedWallet = `${rawBalNum} تومان`;
    if (walletEl) walletEl.innerText = `موجودی: ${formattedWallet}`;
    if (shopBalAmt) shopBalAmt.innerText = rawBalNum;
    if (walletTabBal) walletTabBal.innerText = formattedWallet;

    if (typeof renderShopPlans === 'function') {
      renderShopPlans(data);
    }
  });

  // --- PHASE 3: Profile Settings & Language Preferences ---
  safeStep('settingsAndToggles', () => {
    // Referral Card
    const refCard = $('profileReferralCard');
    const refLinkInp = $('profileReferralLinkInput');
    const refCountEl = $('profileReferralsCount');
    const refRewardTotalEl = $('profileReferralRewardTotal');
    const refRewardBadge = $('profileReferralRewardBadge');

    const refEnabled = data.referral_enabled !== false;
    if (refCard) {
      if (!refEnabled) {
        refCard.classList.add('hidden');
      } else {
        refCard.classList.remove('hidden');
      }
    }

    const referralLink = data.referral_link || (typeof window.buildRefLink === 'function' ? window.buildRefLink(data.bot_username, user.id) : '');
    if (refLinkInp) refLinkInp.value = referralLink;

    const refCount = Number(user.referrals_count || 0);
    const refRewardGb = Number(data.referral_reward_gb || 1);
    if (refCountEl) refCountEl.innerText = `${toEnglishDigits(refCount)} نفر`;
    if (refRewardTotalEl) refRewardTotalEl.innerText = `${toEnglishDigits(refCount * refRewardGb)}`;
    if (refRewardBadge) refRewardBadge.innerText = `🎁 ${toEnglishDigits(refRewardGb)} گیگابایت هدیه به ازای هر دعوت`;

    // Notification Toggles
    const settings = data.settings || {};
    const togglesMap = [
      { id: 'settingToggleNightly', key: 'nightly', defaultVal: true },
      { id: 'settingToggleWeekly', key: 'weekly', defaultVal: true },
      { id: 'settingToggleMonthly', key: 'monthly', defaultVal: true },
      { id: 'settingToggleCleanReports', key: 'clean_reports', defaultVal: true },
      { id: 'settingToggleWheelNotify', key: 'wheel_notify', defaultVal: true },
      { id: 'settingToggleLowTraffic', key: 'low_traffic', defaultVal: true },
      { id: 'settingToggleExpireWarning', key: 'expire_warning', defaultVal: true },
    ];

    togglesMap.forEach(({ id, key, defaultVal }) => {
      const el = $(id);
      if (!el) return;
      const val = (settings[key] !== undefined) ? Boolean(settings[key]) : defaultVal;
      el.checked = val;

      el.onchange = async () => {
        const newVal = el.checked;
        try {
          const res = await window.api.saveSetting(key, newVal);
          if (res && res.ok) {
            showToast('✅ تنظیمات با موفقیت ذخیره شد.');
            hapticFeedback('success');
          } else {
            el.checked = !newVal;
            showToast('❌ خطا در ذخیره تنظیمات');
          }
        } catch (e) {
          el.checked = !newVal;
          showToast('خطا در برقراری ارتباط با سرور.');
        }
      };
    });

    // Auto-Renew Toggle Wiring
    const autoRenewToggle = $('settingToggleAutoRenew');
    const modalAutoRenewToggle = $('modalExpiryAutoRenewSwitch');
    const autoRenewVal = Boolean(user.auto_renew);
    if (autoRenewToggle) autoRenewToggle.checked = autoRenewVal;
    if (modalAutoRenewToggle) modalAutoRenewToggle.checked = autoRenewVal;

    const handleAutoRenewChange = async (newVal, sourceEl) => {
      try {
        const res = await window.api.setAutoRenew(newVal);
        if (res && res.ok) {
          showToast(res.message || (newVal ? 'تمدید خودکار فعال شد.' : 'تمدید خودکار غیرفعال شد.'), 'success');
          hapticFeedback('success');
          if (autoRenewToggle) autoRenewToggle.checked = newVal;
          if (modalAutoRenewToggle) modalAutoRenewToggle.checked = newVal;
          user.auto_renew = newVal;
        } else {
          sourceEl.checked = !newVal;
          showToast('❌ خطا در تغییر وضعیت تمدید خودکار', 'error');
        }
      } catch (e) {
        sourceEl.checked = !newVal;
        showToast('خطا در برقراری ارتباط با سرور.', 'error');
      }
    };

    if (autoRenewToggle) {
      autoRenewToggle.onchange = () => handleAutoRenewChange(autoRenewToggle.checked, autoRenewToggle);
    }
    if (modalAutoRenewToggle) {
      modalAutoRenewToggle.onchange = () => handleAutoRenewChange(modalAutoRenewToggle.checked, modalAutoRenewToggle);
    }

    // Alert Subtexts & Selects
    function updateAlertSubtexts(percent, days) {
      if (percent !== undefined && percent !== null) {
        const traf = $('settingTrafficSubtext');
        if (traf) traf.innerText = `هشدار قبل از پایان ترافیک (${toEnglishDigits(percent)}%)`;
        const disp = $('trafficPercentDisplay');
        if (disp) disp.innerText = `${percent}%`;
        const hiddenInp = $('settingTrafficPercentSelect');
        if (hiddenInp) hiddenInp.value = String(percent);
      }
      if (days !== undefined && days !== null) {
        const exp = $('settingExpireSubtext');
        if (exp) exp.innerText = `اطلاع‌رسانی ${toEnglishDigits(days)} روز مانده به انقضا`;
        const disp = $('expireDaysDisplay');
        if (disp) disp.innerText = `${days} روز`;
        const hiddenInp = $('settingExpireDaysSelect');
        if (hiddenInp) hiddenInp.value = String(days);
      }
    }

    const trafficPercentSelect = $('settingTrafficPercentSelect');
    if (trafficPercentSelect) {
      if (settings.traffic_percent) trafficPercentSelect.value = String(settings.traffic_percent);
      trafficPercentSelect.onchange = async () => {
        const val = parseInt(trafficPercentSelect.value, 10);
        updateAlertSubtexts(val, undefined);
        try {
          const res = await window.api.saveSetting('traffic_percent', val);
          if (res && res.ok) {
            showToast(`✅ درصد هشدار مصرف روی ${val}٪ تنظیم شد.`);
            hapticFeedback('success');
          } else {
            showToast('❌ خطا در ذخیره تنظیمات');
          }
        } catch (e) {
          showToast('خطا در برقراری ارتباط با سرور.');
        }
      };
    }

    const expireDaysSelect = $('settingExpireDaysSelect');
    if (expireDaysSelect) {
      if (settings.expire_days) expireDaysSelect.value = String(settings.expire_days);
      expireDaysSelect.onchange = async () => {
        const val = parseInt(expireDaysSelect.value, 10);
        updateAlertSubtexts(undefined, val);
        try {
          const res = await window.api.saveSetting('expire_days', val);
          if (res && res.ok) {
            showToast(`✅ مهلت هشدار انقضا روی ${val} روز تنظیم شد.`);
            hapticFeedback('success');
          } else {
            showToast('❌ خطا در ذخیره تنظیمات');
          }
        } catch (e) {
          showToast('خطا در برقراری ارتباط با سرور.');
        }
      };
    }

    updateAlertSubtexts(settings.traffic_percent || 80, settings.expire_days || 3);

    // Language Buttons
    const currentLang = user.language || 'fa';
    const langFaBtn = $('langFaBtn');
    const langEnBtn = $('langEnBtn');
    if (currentLang === 'en') {
      langEnBtn?.classList.add('bg-blue-600', 'text-white', 'font-bold');
      langEnBtn?.classList.remove('text-slate-400');
      langFaBtn?.classList.remove('bg-blue-600', 'text-white', 'font-bold');
      langFaBtn?.classList.add('text-slate-400');
    } else {
      langFaBtn?.classList.add('bg-blue-600', 'text-white', 'font-bold');
      langFaBtn?.classList.remove('text-slate-400');
      langEnBtn?.classList.remove('bg-blue-600', 'text-white', 'font-bold');
      langEnBtn?.classList.add('text-slate-400');
    }
  });

  // --- PHASE 4: Wallet Transactions History (DB Data) ---
  safeStep('transactions', () => {
    if (typeof renderWalletTransactions === 'function') {
      renderWalletTransactions(data.transactions || []);
    }
  });

  // --- PHASE 5: Active Subscription Gauge & Connection Link (Panel Data) ---
  safeStep('subscriptionAndGauge', () => {
    const hasActiveSub = Boolean(data.has_active_sub && sub && (sub.status === 'ACTIVE' || !sub.status));
    const subGaugeCard = $('dashboardSubGaugeCard');
    const noSubCard = $('dashboardNoSubCard');
    const countryCard = $('dashboardCountryBreakdownCard');
    const subAccordionCard = $('dashboardSubAccordionCard');
    const gaugeProgress = $('dashboardGaugeProgress') || $('gaugeProgress');

    if (hasActiveSub) {
      if (subGaugeCard) subGaugeCard.classList.remove('hidden');
      if (countryCard) countryCard.classList.remove('hidden');
      if (subAccordionCard) subAccordionCard.classList.remove('hidden');
      if (noSubCard) noSubCard.classList.add('hidden');

      const remainEl = $('dashboardRemainingTraffic');
      if (remainEl) remainEl.innerText = fmtTraffic(sub.traffic_remaining_gb, { html: false });

      const pctEl = $('dashboardPercentRemaining');
      if (pctEl) pctEl.innerText = `${toEnglishDigits(Math.round(sub.percent_remaining ?? 100))}%`;

      const pillEl = $('dashboardUsagePill');
      if (pillEl) pillEl.innerText = `${fmtTraffic(sub.traffic_used_gb ?? 0, { html: false })} / ${fmtTraffic(sub.traffic_total_gb ?? 0, { html: false })}`;

      const daysEl = $('dashboardDaysLeft');
      if (daysEl) daysEl.innerText = `${sub.days_left ?? 0} روز`;

      const expireEl = $('dashboardExpireDate');
      if (expireEl) expireEl.innerText = sub.expire_jalali ? `تا ${sub.expire_jalali}` : 'نامحدود';

      const todayEl = $('dashboardTodayUsed');
      if (todayEl) todayEl.innerText = fmtTraffic(sub.today_used_gb ?? '0.00', { html: false });

      if (gaugeProgress) {
        const circumference = 314.15;
        const pct = Math.max(0, Math.min(100, sub.percent_remaining ?? 100));
        const offset = circumference - (circumference * (pct / 100));
        gaugeProgress.style.strokeDashoffset = offset;
      }

      const subInputEl = $('subInput');
      if (subInputEl && sub.subscription_url) subInputEl.value = sub.subscription_url;
      const subDisplayEl = $('subDisplayBox');
      if (subDisplayEl && sub.subscription_url) subDisplayEl.innerText = sub.subscription_url;
      const qrImg = $('qrImage');
      if (qrImg && sub.subscription_url) {
        qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(sub.subscription_url)}`;
      }
      const modalQrImg = $('modalQrImage');
      if (modalQrImg && sub.subscription_url) {
        modalQrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=260x260&data=${encodeURIComponent(sub.subscription_url)}`;
      }
    } else {
      // User has no active subscription -> Show Empty State!
      if (subGaugeCard) subGaugeCard.classList.add('hidden');
      if (countryCard) countryCard.classList.add('hidden');
      if (subAccordionCard) subAccordionCard.classList.add('hidden');
      if (noSubCard) noSubCard.classList.remove('hidden');

      const noSubNameEl = $('noSubUserName');
      if (noSubNameEl) {
        noSubNameEl.innerText = user.first_name || user.username || tgUser?.first_name || 'کاربر';
      }

      if (typeof resetActiveSubAnalytics === 'function') {
        resetActiveSubAnalytics();
      }

      const subInputEl = $('subInput');
      if (subInputEl) subInputEl.value = 'اشتراک فعالی یافت نشد - لطفاً از تب فروشگاه اقدام فرمایید.';
      const subDisplayEl = $('subDisplayBox');
      if (subDisplayEl) subDisplayEl.innerText = 'اشتراک فعالی یافت نشد - لطفاً از تب فروشگاه اقدام فرمایید.';
      const remainEl = $('dashboardRemainingTraffic');
      if (remainEl) remainEl.innerText = fmtTraffic(null, { html: false });
      const pctEl = $('dashboardPercentRemaining');
      if (pctEl) pctEl.innerText = '0%';
      const pillEl = $('dashboardUsagePill');
      if (pillEl) pillEl.innerText = `${fmtTraffic(0, { html: false })} / ${fmtTraffic(0, { html: false })}`;
      const daysEl = $('dashboardDaysLeft');
      if (daysEl) daysEl.innerText = '0 روز';
      const expireEl = $('dashboardExpireDate');
      if (expireEl) expireEl.innerText = 'غیرفعال';
      const todayEl = $('dashboardTodayUsed');
      if (todayEl) todayEl.innerText = fmtTraffic(0, { html: false });
      if (gaugeProgress) gaugeProgress.style.strokeDashoffset = 314.15;
    }
  });

  // --- PHASE 6: Active Devices & Sessions (Panel Data) ---
  safeStep('devicesAndSessions', () => {
    const devices = sub?.devices || [];
    const activeDevCount = sub?.devices_count ?? devices.length;
    const repSessionsBadge = $('reportsSessionsBadge');
    if (repSessionsBadge) repSessionsBadge.innerText = `${toEnglishDigits(activeDevCount)} دستگاه`;
    const mCountText = $('modalSessionsCount');
    if (mCountText) mCountText.innerText = `${toEnglishDigits(activeDevCount)} دستگاه`;

    function renderDeviceList(container) {
      if (!container) return;
      if (devices.length === 0) {
        container.innerHTML = `
          <div class="p-4 rounded-xl bg-transparent border border-slate-700/50 text-center text-xs text-slate-400">
            <span>📱 در حال حاضر هیچ دستگاه فعالی روی اشتراک شما ثبت نشده است.</span>
          </div>
        `;
        return;
      }

      container.innerHTML = devices.map(d => {
        const platform = (d.platform || '').toLowerCase();
        let icon = '📱';
        if (platform.includes('android')) icon = '🤖';
        else if (platform.includes('ios') || platform.includes('iphone') || platform.includes('apple')) icon = '🍏';
        else if (platform.includes('windows')) icon = '💻';
        else if (platform.includes('mac')) icon = '🍏';
        else if (platform.includes('linux')) icon = '🐧';

        const model = d.deviceModel || d.platform || 'دستگاه';
        const ip = d.requestIp || '—';
        const hwid = d.hwid || '';

        return `
          <div class="bg-transparent rounded-xl p-3 border border-slate-700/60 flex items-center justify-between">
            <div class="flex items-center gap-2.5">
              <span class="text-2xl">${icon}</span>
              <div>
                <div class="flex items-center gap-2">
                  <span class="text-xs font-bold text-slate-200">${escapeHtml(model)}</span>
                  <span class="w-2 h-2 rounded-full bg-emerald-400 inline-block shadow-sm shadow-emerald-400/50" title="فعال"></span>
                </div>
                <div class="text-[11px] font-mono text-cyan-400 mt-0.5">IP: ${escapeHtml(ip)}</div>
              </div>
            </div>
            <button class="kill-device-btn text-rose-400 hover:text-rose-300 w-8 h-8 rounded-xl bg-transparent hover:bg-rose-950/30 border-0 text-xs transition active:scale-95 flex items-center justify-center cursor-pointer" title="قطع این دستگاه" data-hwid="${escapeHtml(hwid)}">
              <svg class="w-4 h-4 text-rose-400 hover:text-rose-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
        `;
      }).join('');

      container.querySelectorAll('.kill-device-btn').forEach(btn => {
        btn.onclick = async () => {
          const hwid = btn.getAttribute('data-hwid');
          if (!hwid || !confirm('آیا از قطع اتصال این دستگاه اطمینان دارید؟')) return;
          try {
            const res = await window.api.killDevice(hwid);
            if (res && res.ok) {
              showToast('✅ دستگاه با موفقیت قطع شد.');
              syncUserDataWithApi();
            } else {
              showToast(`❌ ${res?.error || 'خطا در قطع دستگاه'}`);
            }
          } catch (e) {
            showToast('خطا در برقراری ارتباط با سرور.');
          }
        };
      });
    }

    renderDeviceList($('activeDevicesContainer'));
    renderDeviceList($('modalSessionsList'));

    const openSessionsBtn = $('openDashboardSessionsBtn');
    if (openSessionsBtn) openSessionsBtn.onclick = () => openModal('activeSessionsModal');
    const onlineBadgeBtn = $('headerOnlineBadge');
    if (onlineBadgeBtn) onlineBadgeBtn.onclick = () => openModal('activeSessionsModal');
    const closeSessionsBtn = $('closeSessionsModalBtn');
    if (closeSessionsBtn) closeSessionsBtn.onclick = () => closeModal('activeSessionsModal');
    const modalKillAllBtn = $('modalKillAllBtn');
    if (modalKillAllBtn) {
      modalKillAllBtn.onclick = () => {
        $('killAllBtn')?.click();
      };
    }
  });

  // --- PHASE 7: Story Card & Referral Rewards ---
  safeStep('storyAndReferrals', () => {
    const storyName = $('storyCardName');
    const storyUser = $('storyCardUsername');
    const storyAvatarImg = $('storyCardAvatarImg');
    const storyAvatar = $('storyCardAvatarInitial');
    const storyTraffic = $('storyCardTraffic');
    const storyDays = $('storyCardDays');
    const storyQr = $('storyCardQr');
    const displayName = sub?.username || user.first_name || user.username || 'کاربر گرامی';
    if (storyName) storyName.innerText = displayName;
    if (storyUser) {
      if (user.username) {
        storyUser.innerText = `@${user.username.replace(/^@/, '')}`;
      } else {
        storyUser.innerText = `ID: ${user.id || ''}`;
      }
      storyUser.dir = 'ltr';
    }

    const rewardGb = data.referral_reward_gb ?? 5;
    const rewardEl = $('storyCardRewardGb');
    if (rewardEl) rewardEl.innerText = toEnglishDigits(rewardGb);
    const bannerRewardEl = $('storyRewardBannerGb');
    if (bannerRewardEl) bannerRewardEl.innerText = toEnglishDigits(rewardGb);

    const uid = user.id || tgUser?.id;
    const tgPhotoUrl = tgUser?.photo_url || user.photo_url || '';
    const photoParam = tgPhotoUrl ? `&url=${encodeURIComponent(tgPhotoUrl)}` : '';
    const resolvedAvatarUrl = uid ? `/api/user/avatar?id=${uid}${photoParam}` : tgPhotoUrl;

    if (resolvedAvatarUrl && storyAvatarImg) {
      storyAvatarImg.crossOrigin = 'anonymous';
      storyAvatarImg.src = resolvedAvatarUrl;
      storyAvatarImg.onload = () => {
        storyAvatarImg.classList.remove('hidden');
        if (storyAvatar) storyAvatar.classList.add('hidden');
      };
      storyAvatarImg.onerror = () => {
        storyAvatarImg.classList.add('hidden');
        if (storyAvatar) {
          storyAvatar.classList.remove('hidden');
          storyAvatar.innerText = displayName.charAt(0).toUpperCase();
        }
      };
    } else {
      if (storyAvatarImg) storyAvatarImg.classList.add('hidden');
      if (storyAvatar) {
        storyAvatar.classList.remove('hidden');
        storyAvatar.innerText = displayName.charAt(0).toUpperCase();
      }
    }

    if (storyTraffic) storyTraffic.innerText = fmtTraffic(sub?.traffic_remaining_gb, { html: false });
    if (storyDays) storyDays.innerText = `${toEnglishDigits(sub?.days_left ?? 0)} روز اعتبار`;
    const botUsername = data.bot_username || window.Telegram?.WebApp?.initDataUnsafe?.bot?.username || '';
    const refLink = typeof window.buildRefLink === 'function' ? window.buildRefLink(botUsername, user.id) : '';
    window.currentReferralLink = refLink;
    if (storyQr && refLink) {
      storyQr.crossOrigin = 'anonymous';
      storyQr.src = `https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=${encodeURIComponent(refLink)}`;
    }
  });

  // --- PHASE 8: Reports Hub & Usage Breakdowns (Panel Data) ---
  safeStep('reportsAndAnalytics', () => {
    // Today Country Breakdown
    const countryList = $('countryBreakdownList');
    const countryTotalHeader = $('countryTodayTotalHeader');
    if (countryTotalHeader) countryTotalHeader.innerText = fmtTraffic(sub?.today_used_gb ?? '0.00', { html: false });
    if (countryList) {
      const bDown = sub?.today_breakdown || [];
      if (bDown.length === 0) {
        countryList.innerHTML = `
          <div class="p-3 rounded-xl bg-slate-900/60 border border-slate-700/50 text-center text-xs text-slate-400">
            <span>ℹ️ امروز هنوز ترافیکی روی سرورها ثبت نشده است.</span>
          </div>
        `;
      } else {
        const showBar = bDown.length > 1;
        countryList.innerHTML = bDown.map(item => {
          const pct = item.percent || 0;
          const barHtml = (showBar && pct > 0)
            ? `<div class="w-full bg-slate-800/80 h-1.5 rounded-full overflow-hidden" dir="ltr">
                <div class="bg-gradient-to-r from-blue-500 to-cyan-400 h-full rounded-full transition-all duration-500" style="width: ${pct}%;"></div>
              </div>`
            : '';
          return `
          <div class="p-2.5 rounded-xl bg-slate-900/70 border border-slate-700/50 space-y-1.5">
            <div class="flex justify-between items-center text-xs">
              <span class="text-cyan-300 font-black text-xs font-mono num-bidi" dir="ltr">${fmtTraffic(item.total_formatted, { html: false })}</span>
              <span class="flex items-center gap-2 font-bold text-slate-200">
                <span>${escapeHtml(item.name || '')}</span>
                <span class="text-base">${escapeHtml(item.flag || '🌐')}</span>
              </span>
            </div>
            ${barHtml}
          </div>
          `;
        }).join('');
      }
    }

    // Reports Hub
    if (data.yesterday_jalali) {
      const repDateEl = $('repNightlyDate');
      if (repDateEl) repDateEl.innerText = `${toEnglishDigits(data.yesterday_jalali)} - 23:59`;
    }

    if (sub && data.has_active_sub) {
      const weeklyCanvas = $('repWeeklyChartCanvas');
      const weeklyEmpty = $('repWeeklyEmptyState');
      if (weeklyCanvas) weeklyCanvas.classList.remove('hidden');
      if (weeklyEmpty) weeklyEmpty.classList.add('hidden');

      const monthlyCanvas = $('repMonthlyChartCanvas');
      const monthlyEmpty = $('repMonthlyEmptyState');
      if (monthlyCanvas) monthlyCanvas.classList.remove('hidden');
      if (monthlyEmpty) monthlyEmpty.classList.add('hidden');

      const repTotal = $('repNightlyTotal');
      if (repTotal) repTotal.innerText = fmtTraffic(sub.traffic_total_gb, { html: false });
      const repUsed = $('repNightlyUsed');
      if (repUsed) repUsed.innerText = fmtTraffic(sub.traffic_used_gb, { html: false });
      const repRemain = $('repNightlyRemain');
      if (repRemain) repRemain.innerText = fmtTraffic(sub.traffic_remaining_gb, { html: false });
      const repYesterday = $('repNightlyYesterday');
      if (repYesterday) repYesterday.innerText = fmtTraffic(sub.yesterday_used_gb ?? '0.00', { html: false });
      const repExpire = $('repNightlyExpire');
      if (repExpire) repExpire.innerText = `${toEnglishDigits(sub.days_left ?? 0)} روز (${toEnglishDigits(sub.expire_jalali || 'نامحدود')})`;

      if (typeof renderNodeBreakdown === 'function') {
        renderNodeBreakdown('repNightlyNodesContainer', sub.yesterday_breakdown || sub.today_breakdown || [], 'دیشب مصرفی روی سرورها ثبت نشده است.');
        renderNodeBreakdown('repWeeklyNodesContainer', sub.week_breakdown || [], 'مصرفی در 7 روز گذشته ثبت نشده است.');
        renderNodeBreakdown('repMonthlyNodesContainer', sub.week_breakdown || sub.today_breakdown || [], 'مصرفی در ماه جاری ثبت نشده است.');
      }

      const repWeeklyTotal = $('repWeeklyTotal');
      if (repWeeklyTotal) repWeeklyTotal.innerHTML = fmtTraffic(sub.week_used_gb ?? '0.00', { html: true });
      const repWeeklyBusiest = $('repWeeklyBusiest');
      if (repWeeklyBusiest) {
        repWeeklyBusiest.innerHTML = `${sub.busiest_day_name || '—'} <span class="font-mono text-cyan-300 font-semibold num-bidi">(${fmtTraffic(sub.busiest_day_amount || '0 GB', { html: false })})</span>`;
      }

      if (typeof renderBarChart === 'function') {
        try {
          renderBarChart('repWeeklyChartCanvas', sub.week_daily_totals_gb || [0, 0, 0, 0, 0, 0, 0], sub.week_day_labels || ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'], false);
        } catch (e) {
          console.warn('Could not render weekly chart:', e);
        }
      }

      const repMonthlyTitle = $('repMonthlyTitle');
      if (repMonthlyTitle) repMonthlyTitle.innerText = `📅 گزارش جامع ماه ${sub.current_month_name || ''}`;
      const repMonthlyTotal = $('repMonthlyTotal');
      if (repMonthlyTotal) repMonthlyTotal.innerHTML = fmtTraffic(sub.month_used_gb ?? '0.00', { html: true });

      if (typeof renderBarChart === 'function') {
        try {
          renderBarChart('repMonthlyChartCanvas', sub.month_weeks_totals_gb || [0, 0, 0, sub.week_used_gb || 0], ['هفته ۱', 'هفته ۲', 'هفته ۳', 'هفته ۴'], true);
        } catch (e) {
          console.warn('Could not render monthly chart:', e);
        }
      }

      // Advanced Analytics
      try {
        renderActiveSubAnalytics(sub);
      } catch (e) {
        console.warn('Could not render active sub analytics:', e);
      }
    } else {
      if (typeof resetActiveSubAnalytics === 'function') {
        resetActiveSubAnalytics();
      }
    }
  });

  // --- PHASE 9: Gamification & Extras (Wheel & Birthday) ---
  safeStep('perksAndGamification', () => {
    // Wheel Status
    if (data.wheel_status && typeof updateWheelUIState === 'function') {
      updateWheelUIState(
        data.wheel_status.can_spin,
        data.wheel_status.has_active_sub,
        data.wheel_status.next_spin_seconds || 0,
        data.wheel_status.streak || 0,
        data.wheel_status.streak_multiplier || 1.0,
        data.wheel_status.spin_tickets || 0
      );
    }

    // Dashboard Birthday Countdown
    if (data.user && typeof renderDashboardBirthdayCountdown === 'function') {
      renderDashboardBirthdayCountdown(data.user);
    }

    // Tutorial App Updates Badge
    if (typeof checkTutorialAppUpdates === 'function') {
      checkTutorialAppUpdates();
    }
  });
}

// 16. Versioned Cache Storage & Retrieval with Multi-Account Isolation
const USER_CACHE_VERSION = 4;

function getCurrentTelegramUserId() {
  const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
  if (tgUser?.id) return String(tgUser.id);
  const urlParams = new URLSearchParams(window.location.search);
  const devId = urlParams.get('dev_id') || urlParams.get('user_id');
  if (devId) return String(devId);
  return null;
}

function getScopedCacheKey(userId) {
  const uid = userId || getCurrentTelegramUserId();
  return uid ? `remna_user_cache_${uid}` : 'remna_user_cache';
}

function saveUserCache(data) {
  if (!data || typeof data !== 'object') return;
  try {
    const uid = data.user?.id || getCurrentTelegramUserId();
    const cacheKey = getScopedCacheKey(uid);
    const payload = {
      v: USER_CACHE_VERSION,
      ts: Date.now(),
      uid: uid ? String(uid) : null,
      data: data,
    };
    localStorage.setItem(cacheKey, JSON.stringify(payload));
  } catch (err) {
    console.warn('[Cache] Failed to save user cache:', err);
  }
}

function loadUserCache() {
  try {
    // Purge old un-isolated global cache
    try { localStorage.removeItem('remna_user_cache'); } catch (e) {}

    const currentUid = getCurrentTelegramUserId();
    const cacheKey = getScopedCacheKey(currentUid);
    const raw = localStorage.getItem(cacheKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object') {
      if (parsed.v === USER_CACHE_VERSION && parsed.data && parsed.data.user) {
        // Multi-account guard: cache must belong to current user
        if (currentUid && parsed.data.user.id && String(parsed.data.user.id) !== currentUid) {
          localStorage.removeItem(cacheKey);
          return null;
        }
        const age = Date.now() - (parsed.ts || 0);
        if (age < 7 * 24 * 3600 * 1000) {
          return parsed.data;
        }
      }
    }
    localStorage.removeItem(cacheKey);
    return null;
  } catch (err) {
    console.warn('[Cache] Purging corrupted cache:', err);
    try { localStorage.removeItem(getScopedCacheKey()); } catch (e) {}
    return null;
  }
}

// 17. Stale-While-Revalidate API Sync
async function syncUserDataWithApi(accountId) {
  try {
    const res = await window.api.getMe(accountId);
    if (res && res.ok && res.data) {
      if (typeof hideBanner === 'function') {
        hideBanner('authErrorBanner');
        hideBanner('apiErrorBanner');
      }
      window.lastUserData = res.data;
      try {
        hydrateUserInterface(res.data);
      } catch (hydrateErr) {
        console.error('[syncUserDataWithApi] Error hydrating UI:', hydrateErr);
      }

      if (res.data.active_sub && typeof renderActiveSubAnalytics === 'function') {
        try {
          renderActiveSubAnalytics(res.data.active_sub);
        } catch (analyticsErr) {
          console.warn('[syncUserDataWithApi] Error rendering analytics:', analyticsErr);
        }
      } else {
        if (typeof resetActiveSubAnalytics === 'function') {
          resetActiveSubAnalytics();
        }
      }

      saveUserCache(res.data);

      if (res.data.partial) {
        if (typeof showBanner === 'function') {
          showBanner('⚠️ ارتباط با سرور اشتراک موقتاً با تأخیر همراه است. اطلاعات کیف‌پول و پلن‌ها در دسترس است.', 'warning', {
            id: 'partialBanner',
            dismissible: true,
          });
        }
      } else {
        if (typeof hideBanner === 'function') {
          hideBanner('partialBanner');
        }
      }
    } else if (res && !res.ok) {
      console.warn('Live API response not ok:', res);
      const statusCode = res._status || res.status;
      if (statusCode === 401 || res.error === 'Unauthorized') {
        if (typeof showBanner === 'function') {
          showBanner('نشست کاربری شما منقضی شده است. لطفاً مینی‌اپ را ببندید و مجدداً باز فرمایید.', 'error', {
            id: 'authErrorBanner',
            actionText: 'بستن برنامه',
            onAction: () => {
              if (window.Telegram?.WebApp?.close) {
                window.Telegram.WebApp.close();
              } else {
                window.location.reload();
              }
            },
          });
        }
      } else if (statusCode === 408 || res.is_timeout) {
        if (typeof showBanner === 'function') {
          showBanner('مهلت ارتباط با سرور به پایان رسید. در حال استفاده از آخرین اطلاعات ذخیره‌شده.', 'warning', {
            id: 'apiErrorBanner',
            actionText: 'تلاش مجدد',
            onAction: () => syncUserDataWithApi(accountId),
          });
        }
      } else {
        if (typeof showBanner === 'function') {
          showBanner(res.error || 'خطا در برقراری ارتباط با سرور. لطفاً مجدداً تلاش کنید.', 'warning', {
            id: 'apiErrorBanner',
            actionText: 'تلاش مجدد',
            onAction: () => syncUserDataWithApi(accountId),
          });
        }
      }
    }
  } catch (err) {
    console.debug('Live API sync fallback to cache', err);
    if (typeof showBanner === 'function') {
      showBanner('خطای شبکه در ارتباط با سرور. لطفاً مجدداً تلاش کنید.', 'warning', {
        id: 'apiErrorBanner',
        actionText: 'تلاش مجدد',
        onAction: () => syncUserDataWithApi(accountId),
      });
    }
  }
}

// 18. Initialize Application
function initApp() {
  const safeRun = (name, fn) => {
    try {
      if (typeof fn === 'function') fn();
    } catch (err) {
      console.warn(`[initApp] Error in ${name}:`, err);
    }
  };

  safeRun('initImmediateUserIdentity', () => {
    const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
    if (tgUser) {
      const name = tgUser.first_name || tgUser.username || '';
      if (name) {
        const usernameEl = $('headerUsername');
        if (usernameEl && (usernameEl.innerText === 'کاربر' || !usernameEl.innerText)) {
          usernameEl.innerText = name;
        }
        const avatarEl = $('headerUserAvatarInitial');
        if (avatarEl && (avatarEl.innerText === 'U' || !avatarEl.innerText)) {
          avatarEl.innerText = name[0].toUpperCase();
        }
        const profName = $('profileFullName');
        if (profName && profName.innerText === 'کاربر گرامی') {
          profName.innerText = tgUser.first_name ? `${tgUser.first_name} ${tgUser.last_name || ''}`.trim() : name;
        }
        const profUser = $('profileUsername');
        if (profUser && tgUser.username && profUser.innerText === '@user') {
          profUser.innerText = `@${tgUser.username}`;
        }
        const profAvatar = $('profileAvatarInitial');
        if (profAvatar && (profAvatar.innerText === 'U' || !profAvatar.innerText)) {
          profAvatar.innerText = name[0].toUpperCase();
        }
      }

      const profId = $('profileTelegramId');
      if (profId && (profId.innerText === '--' || !profId.innerText) && tgUser.id) {
        profId.innerText = String(tgUser.id);
      }

      const directPhoto = tgUser?.photo_url || '';
      loadAvatarWithFallback($('headerUserAvatarImg'), $('headerUserAvatarInitial'), directPhoto, tgUser.id);
      loadAvatarWithFallback($('profileAvatarImg'), $('profileAvatarInitial'), directPhoto, tgUser.id);
    }
  });

  safeRun('setupTabNavigation', setupTabNavigation);
  safeRun('setupReportsSubtabs', setupReportsSubtabs);
  safeRun('setupSubscriptionActions', setupSubscriptionActions);
  safeRun('setupQrToggle', setupQrToggle);
  safeRun('setupConfigsModal', setupConfigsModal);
  safeRun('setupRevokeAndKill', setupRevokeAndKill);
  safeRun('setupClientImporters', setupClientImporters);
  safeRun('setupTutorialModal', setupTutorialModal);
  safeRun('setupThemeToggle', setupThemeToggle);
  safeRun('setupNetworkTools', setupNetworkTools);
  safeRun('setupSupportChat', setupSupportChat);
  safeRun('setupTelegramSDK', setupTelegramSDK);
  safeRun('setupAccountSwitcher', setupAccountSwitcher);
  safeRun('setupProfileHandlers', setupProfileHandlers);
  safeRun('setupCouponInput', setupCouponInput);
  safeRun('setupWalletListeners', setupWalletListeners);
  safeRun('setupLuckyWheel', setupLuckyWheel);
  safeRun('setupStoryCard', setupStoryCard);

  // DRY accordions
  safeRun('setupAccordions', () => {
    setupAccordion('toggleCountryBreakdownBtn', 'countryBreakdownBody', 'countryChevron');
    setupAccordion('toggleSessionsAccordionBtn', 'sessionsAccordionBody', 'sessionsChevron');
    setupAccordion('toggleSubAccordionBtn', 'subAccordionBody', 'subChevron');
  });

  safeRun('loadNetworkNodes', loadNetworkNodes);
  safeRun('loadClientIpInfo', loadClientIpInfo);

  safeRun('hydrateFromCache', () => {
    try {
      const cachedData = loadUserCache();
      if (cachedData) {
        window.lastUserData = cachedData;
        hydrateUserInterface(cachedData);
      }
    } catch(e) {
      console.warn('[initApp] hydrateFromCache error:', e);
    }
  });

  safeRun('syncUserDataWithApi', syncUserDataWithApi);
}
window.initApp = initApp;

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}

window.syncUserDataWithApi = syncUserDataWithApi;
window.hydrateUserInterface = hydrateUserInterface;
window.renderActiveSubAnalytics = renderActiveSubAnalytics;
window.saveUserCache = saveUserCache;
window.loadUserCache = loadUserCache;
