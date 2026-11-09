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

let currentMonthlyIndex = 0;

function updateMonthlyReportView(index) {
  if (typeof index === 'number') currentMonthlyIndex = index;
  const sub = window.lastUserData?.active_sub || window.currentSub;
  if (!sub) return;

  const history = (Array.isArray(sub.monthly_history) && sub.monthly_history.length > 0)
    ? sub.monthly_history
    : [{
        month_name: sub.current_month_name || 'ماه جاری',
        full_name: sub.current_month_name || 'ماه جاری',
        total_used_gb: sub.month_used_gb ?? '0.00',
        month_weeks_totals_gb: sub.month_weeks_totals_gb || [0, 0, 0, 0],
        nodes_breakdown: sub.week_breakdown || sub.today_breakdown || [],
      }];

  if (currentMonthlyIndex < 0) currentMonthlyIndex = 0;
  if (currentMonthlyIndex >= history.length) currentMonthlyIndex = history.length - 1;

  const mData = history[currentMonthlyIndex];

  const repMonthlyTitle = $('repMonthlyTitle');
  if (repMonthlyTitle) repMonthlyTitle.innerText = `📅 گزارش جامع ماه ${mData.month_name || ''}`;

  const repMonthlyCurrentLabel = $('repMonthlyCurrentLabel');
  if (repMonthlyCurrentLabel) repMonthlyCurrentLabel.innerText = mData.full_name || mData.month_name || 'ماه جاری';

  const repMonthlyPeriodBadge = $('repMonthlyPeriodBadge');
  if (repMonthlyPeriodBadge) {
    repMonthlyPeriodBadge.innerText = (currentMonthlyIndex === 0) ? 'ماه جاری' : 'آرشیو گذشته';
  }

  const repMonthlyTotal = $('repMonthlyTotal');
  if (repMonthlyTotal) repMonthlyTotal.innerHTML = fmtTraffic(mData.total_used_gb ?? '0.00', { html: true });

  const monthlyCanvas = $('repMonthlyChartCanvas');
  const monthlyEmpty = $('repMonthlyEmptyState');
  if (monthlyCanvas && monthlyEmpty) {
    monthlyCanvas.classList.remove('hidden');
    monthlyEmpty.classList.add('hidden');
  }

  if (typeof renderBarChart === 'function') {
    try {
      renderBarChart(
        'repMonthlyChartCanvas',
        mData.month_weeks_totals_gb || [0, 0, 0, 0],
        ['هفته 1', 'هفته 2', 'هفته 3', 'هفته 4'],
        true
      );
    } catch (e) {
      console.warn('Could not render monthly chart:', e);
    }
  }

  if (typeof renderNodeBreakdown === 'function') {
    renderNodeBreakdown(
      'repMonthlyNodesContainer',
      mData.nodes_breakdown || [],
      `مصرفی در ماه ${mData.month_name || ''} ثبت نشده است.`
    );
  }

  const prevBtn = $('repMonthPrevBtn');
  const nextBtn = $('repMonthNextBtn');
  const prevLabel = $('repMonthPrevLabel');
  const nextLabel = $('repMonthNextLabel');

  const hasPrev = currentMonthlyIndex < history.length - 1;
  const hasNext = currentMonthlyIndex > 0;

  if (prevBtn) {
    prevBtn.disabled = !hasPrev;
    prevBtn.classList.toggle('opacity-40', !hasPrev);
    prevBtn.classList.toggle('cursor-not-allowed', !hasPrev);
  }
  if (prevLabel) {
    prevLabel.innerText = hasPrev ? (history[currentMonthlyIndex + 1]?.month_name || 'ماه قبل') : 'ماه قبل';
  }

  if (nextBtn) {
    nextBtn.disabled = !hasNext;
    nextBtn.classList.toggle('opacity-40', !hasNext);
    nextBtn.classList.toggle('cursor-not-allowed', !hasNext);
  }
  if (nextLabel) {
    nextLabel.innerText = hasNext ? (history[currentMonthlyIndex - 1]?.month_name || 'ماه بعد') : 'ماه بعد';
  }
}
window.updateMonthlyReportView = updateMonthlyReportView;

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
  const dailyCanvas = $('repDailyChartCanvas');
  const dailyEmpty = $('repDailyEmptyState');
  if (dailyCanvas) dailyCanvas.classList.remove('hidden');
  if (dailyEmpty) dailyEmpty.classList.add('hidden');

  const nightlyCanvas = $('repNightlyChartCanvas');
  const nightlyEmpty = $('repNightlyEmptyState');
  if (nightlyCanvas) nightlyCanvas.classList.remove('hidden');
  if (nightlyEmpty) nightlyEmpty.classList.add('hidden');

  const weeklyCanvas = $('repWeeklyChartCanvas');
  const weeklyEmpty = $('repWeeklyEmptyState');
  if (weeklyCanvas) weeklyCanvas.classList.remove('hidden');
  if (weeklyEmpty) weeklyEmpty.classList.add('hidden');

  const monthlyCanvas = $('repMonthlyChartCanvas');
  const monthlyEmpty = $('repMonthlyEmptyState');
  if (monthlyCanvas) monthlyCanvas.classList.remove('hidden');
  if (monthlyEmpty) monthlyEmpty.classList.add('hidden');

  const hourlyData = currentSub.hourly_usage?.data || Array(12).fill(0);
  const hourlyLabels = currentSub.hourly_usage?.labels || [
    '00-02','02-04','04-06','06-08','08-10','10-12',
    '12-14','14-16','16-18','18-20','20-22','22-24'
  ];

  const yHourlyData = currentSub.yesterday_hourly_usage?.data || Array(12).fill(0);
  const yHourlyLabels = currentSub.yesterday_hourly_usage?.labels || hourlyLabels;
  const hasYTraffic = Boolean(
    (currentSub.yesterday_used_gb && Number(currentSub.yesterday_used_gb) > 0) ||
    yHourlyData.some(v => Number(v) > 0)
  );

  if (nightlyCanvas) nightlyCanvas.classList.toggle('hidden', !hasYTraffic);
  if (nightlyEmpty) nightlyEmpty.classList.toggle('hidden', hasYTraffic);

  if (typeof renderBarChart === 'function') {
    renderBarChart('repDailyChartCanvas', hourlyData, hourlyLabels, false);
    if (hasYTraffic) {
      renderBarChart('repNightlyChartCanvas', yHourlyData, yHourlyLabels, false);
    }
    renderBarChart('repWeeklyChartCanvas', currentSub.week_daily_totals_gb || [0, 0, 0, 0, 0, 0, 0], currentSub.week_day_labels || ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'], false);
  }
  if (typeof updateMonthlyReportView === 'function') {
    updateMonthlyReportView(currentMonthlyIndex);
  } else if (typeof renderBarChart === 'function') {
    renderBarChart('repMonthlyChartCanvas', currentSub.month_weeks_totals_gb || [0, 0, 0, 0], ['هفته 1', 'هفته 2', 'هفته 3', 'هفته 4'], true);
  }
  if (typeof renderActiveSubAnalytics === 'function') {
    renderActiveSubAnalytics(currentSub);
  }
}
window.renderReportsCharts = renderReportsCharts;

function switchTab(targetId) {
  if (!targetId || window.isSystemBlocked) return;
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
    b.classList.toggle('is-active', isTarget);
    b.setAttribute('aria-selected', isTarget ? 'true' : 'false');
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
      if (window.isSystemBlocked) return;
      const targetId = btn.getAttribute('data-tab');
      if (targetId) switchTab(targetId);
    };
  });
}
window.setupTabNavigation = setupTabNavigation;

// 3. Sub-tabs in Reports Hub
function setupReportsSubtabs() {
  const repSubDaily = $('repSubDaily');
  const repSubNightly = $('repSubNightly');
  const repSubWeekly = $('repSubWeekly');
  const repSubMonthly = $('repSubMonthly');
  const repSubAnalytics = $('repSubAnalytics');
  const viewRepDaily = $('viewRepDaily');
  const viewRepNightly = $('viewRepNightly');
  const viewRepWeekly = $('viewRepWeekly');
  const viewRepMonthly = $('viewRepMonthly');
  const viewRepAnalytics = $('viewRepAnalytics');

  function setRepSub(activeBtn, activeView) {
    [repSubDaily, repSubNightly, repSubWeekly, repSubMonthly, repSubAnalytics].forEach(b => {
      if (b) b.className = 'flex-1 py-1.5 rounded-lg font-bold text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition';
    });
    if (activeBtn) activeBtn.className = 'flex-1 py-1.5 rounded-lg font-bold bg-blue-600 text-white shadow-sm transition';

    [viewRepDaily, viewRepNightly, viewRepWeekly, viewRepMonthly, viewRepAnalytics].forEach(v => v?.classList.add('hidden'));
    activeView?.classList.remove('hidden');

    if (activeView === viewRepWeekly || activeView === viewRepMonthly || activeView === viewRepAnalytics) {
      setTimeout(() => renderReportsCharts(), 60);
    }
  }

  repSubDaily?.addEventListener('click', () => setRepSub(repSubDaily, viewRepDaily));
  repSubNightly?.addEventListener('click', () => setRepSub(repSubNightly, viewRepNightly));
  repSubWeekly?.addEventListener('click', () => setRepSub(repSubWeekly, viewRepWeekly));
  repSubMonthly?.addEventListener('click', () => {
    setRepSub(repSubMonthly, viewRepMonthly);
    if (typeof updateMonthlyReportView === 'function') {
      updateMonthlyReportView(currentMonthlyIndex);
    }
  });
  repSubAnalytics?.addEventListener('click', () => setRepSub(repSubAnalytics, viewRepAnalytics));

  $('repMonthPrevBtn')?.addEventListener('click', () => {
    if (typeof updateMonthlyReportView === 'function') {
      updateMonthlyReportView(currentMonthlyIndex + 1);
    }
    if (typeof hapticFeedback === 'function') hapticFeedback('selection');
  });
  $('repMonthNextBtn')?.addEventListener('click', () => {
    if (typeof updateMonthlyReportView === 'function') {
      updateMonthlyReportView(currentMonthlyIndex - 1);
    }
    if (typeof hapticFeedback === 'function') hapticFeedback('selection');
  });
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
      copySubBtn.classList.add('t-success', 'border-emerald-500');
      copySubBtn.classList.remove('text-slate-300');
      setTimeout(() => {
        copySubBtn.classList.remove('t-success', 'border-emerald-500');
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

  const renderConfigsCards = (configs) => {
    currentConfigsList = configs;
    if (configsModalCount) configsModalCount.innerText = `${currentConfigsList.length} کانفیگ`;

    configsModalList.innerHTML = currentConfigsList.map(c => {
      const safeName = escapeHtml(c.name || 'کانفیگ سرور');
      const protoBadge = escapeHtml((c.protocol || 'vpn').toUpperCase());
      const flag = c.flag || '🌐';

      return `
        <div class="config-row-item card-inset p-2.5 flex items-center justify-between gap-2 transition hover:border-slate-600">
          <div class="flex items-center gap-2 overflow-hidden flex-1 min-w-0">
            <span class="text-xs font-bold t-main truncate config-name-label" title="${safeName}">${safeName}</span>
          </div>
          <div class="flex items-center gap-1 shrink-0">
            <button type="button" class="copy-single-cfg-btn btn-icon t-muted hover:t-accent text-sm" data-uri="${encodeURIComponent(c.uri)}" title="کپی کانفیگ">
              📋
            </button>
            <button type="button" class="qr-single-cfg-btn btn-icon t-muted hover:t-accent text-sm" data-uri="${encodeURIComponent(c.uri)}" data-name="${encodeURIComponent(c.name)}" title="نمایش کیوآرکد">
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
  };

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
      <div class="text-center py-6 text-slate-400 text-xs space-y-2">
        <span class="inline-block animate-spin text-base">🔄</span>
        <div>در حال دریافت کانفیگ‌ها از پنل...</div>
      </div>
    `;

    try {
      const targetAccId = window.currentAccountId || window.lastUserData?.active_sub?.account_id || window.lastUserData?.active_sub?.id;
      const res = await window.api.getSubscriptionConfigs(targetAccId);
      const resData = res?.data || res;
      let configs = resData?.configs || res?.configs || [];

      if (configs && configs.length > 0) {
        renderConfigsCards(configs);
      } else {
        currentConfigsList = [];
        if (configsModalCount) configsModalCount.innerText = '0 کانفیگ';
        const msg = resData?.message || res?.message || resData?.error || res?.error || 'کانفیگی در پنل رمنانو یافت نشد.';
        configsModalList.innerHTML = `
          <div class="text-center py-6 t-muted text-xs space-y-2">
            <span class="text-base block">⚠️</span>
            <div class="leading-relaxed font-medium">${escapeHtml(msg)}</div>
            <div class="pt-2 flex items-center justify-center gap-2">
              <button type="button" id="retryConfigsBtn" class="px-3 py-1.5 rounded-xl border border-cyan-500/40 text-cyan-300 text-[11px] font-bold transition active:scale-95">
                🔄 تلاش مجدد
              </button>
            </div>
          </div>
        `;
        $('retryConfigsBtn')?.addEventListener('click', loadAndRenderConfigs);
      }
    } catch (e) {
      configsModalList.innerHTML = `
        <div class="text-center py-6 t-danger text-xs space-y-2">
          <span class="text-base block">❌</span>
          <div class="leading-relaxed">خطا در دریافت کانفیگ‌ها: ${escapeHtml(e?.message || 'ارتباط با سرور برقرار نشد')}</div>
          <div class="pt-2 flex items-center justify-center gap-2">
            <button type="button" id="retryConfigsBtnErr" class="px-3 py-1.5 rounded-xl border border-cyan-500/40 text-cyan-300 text-[11px] font-bold transition active:scale-95">
              🔄 تلاش مجدد
            </button>
          </div>
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

  function prepareAndOpenRevokeModal() {
    const targetEl = $('revokeTargetAccountName');
    const curAcc = window.currentAccountId;
    const accounts = window.lastUserData?.accounts || [];
    let accObj = accounts.find(a => String(a.id) === String(curAcc) || String(a.uuid) === String(curAcc));
    if (!accObj && accounts.length > 0) accObj = accounts[0];
    if (targetEl) {
      if (accObj) {
        targetEl.innerText = `اکانت هدف: ${accObj.username || accObj.id}`;
        targetEl.classList.remove('hidden');
      } else {
        targetEl.classList.add('hidden');
      }
    }
    openModal('revokeModal');
  }

  openRevokeModalBtn?.addEventListener('click', prepareAndOpenRevokeModal);
  revokeSubBtnTop?.addEventListener('click', prepareAndOpenRevokeModal);
  cancelRevokeBtn?.addEventListener('click', () => closeModal('revokeModal'));

  confirmRevokeBtn?.addEventListener('click', async () => {
    confirmRevokeBtn.disabled = true;
    confirmRevokeBtn.innerText = 'در حال صدور لینک جدید...';
    try {
      const res = await window.api.revokeSub(window.currentAccountId);
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

  $('killAllBtn')?.addEventListener('click', () => {
    openKillAllSessionsModal();
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
  $('appImportV2box')?.addEventListener('click', () => {
    copyAndLaunch(u => `v2box://install-sub?url=${encodeURIComponent(u)}&name=${encodeURIComponent(window.lastUserData?.bot_username || 'Subscription')}`, 'V2Box');
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
      tab.classList.remove('t-muted', 'text-slate-400', 'font-medium');
    } else {
      tab.classList.remove('bg-cyan-600', 'text-white', 'shadow', 'font-bold');
      tab.classList.add('t-muted', 'font-medium');
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
        <div class="w-12 h-12 rounded-2xl card-inset mx-auto flex items-center justify-center text-2xl">
          📱
        </div>
        <b class="text-xs t-main block">برنامه‌ای برای نمایش یافت نشد</b>
        <p class="text-[11px] t-muted max-w-[260px] mx-auto leading-relaxed">
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
      <button type="button" class="btn-tutorial-app bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/40 text-[11px] font-bold py-1 px-2 rounded-xl transition flex items-center justify-center gap-1 active:scale-95 shadow-sm" data-url="${escapeHtml(app.tutorialUrl)}">
        <span>📖</span> آموزش
      </button>
    ` : '';

    let actionButtonsHtml = '';

    if (dlButtons.length === 1) {
      const d = dlButtons[0];
      actionButtonsHtml = `
        <div class="grid grid-cols-2 gap-1.5 pt-0.5">
          <button type="button" class="btn-download-app btn-secondary text-xs font-bold py-1.5 px-2 rounded-xl transition flex items-center justify-center gap-1 active:scale-95 shadow-sm truncate" data-url="${escapeHtml(d.url)}">
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
            <button type="button" class="btn-download-app btn-secondary text-xs font-bold py-1.5 px-2 rounded-xl transition flex items-center justify-center gap-1 active:scale-95 shadow-sm truncate" data-url="${escapeHtml(dlButtons[0].url)}">
              <span>${dlButtons[0].icon}</span> <span class="truncate">${dlButtons[0].label}</span>
            </button>
            <button type="button" class="btn-download-app btn-secondary text-xs font-bold py-1.5 px-2 rounded-xl transition flex items-center justify-center gap-1 active:scale-95 shadow-sm truncate" data-url="${escapeHtml(dlButtons[1].url)}">
              <span>${dlButtons[1].icon}</span> <span class="truncate">${dlButtons[1].label}</span>
            </button>
          </div>
          <div>
            <button type="button" class="btn-autoconnect-app w-full text-xs font-bold py-1.5 px-2 rounded-xl transition flex items-center justify-center gap-1 active:scale-95 shadow-sm" data-id="${app.id}" data-name="${escapeHtml(app.name)}">
              <span>⚡️</span> اتصال خودکار
            </button>
          </div>
        </div>
      `;
    }

    const cardBorder = app.isRecommended ? 'border-amber-500/60 dark:border-amber-500/50 card-inset shadow-md ring-1 ring-amber-500/30' : 'card-inset';

    return `
      <div class="tutorial-app-card rounded-2xl p-2.5 ${cardBorder} space-y-1.5 transition">
        <div class="flex items-center justify-between gap-2">
          <!-- Right side: App Icon + Name -->
          <div class="flex items-center gap-2.5 min-w-0">
            <div class="w-10 h-10 rounded-xl card-inset p-1 flex items-center justify-center flex-shrink-0 shadow-inner overflow-hidden relative">
              <img src="/static/img/apps/${app.id}.png" alt="${escapeHtml(app.name)}" class="w-full h-full object-contain rounded-lg" onerror="this.style.display='none'; if(this.nextElementSibling) this.nextElementSibling.style.display='flex';" />
              <span class="text-xl items-center justify-center hidden" style="display:none;">${app.icon || '📱'}</span>
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-1.5 min-w-0">
                ${app.version ? `<span class="text-[11px] t-muted font-mono font-medium flex-shrink-0">v${toEnglishDigits(app.version)}</span>` : ''}
                <b class="text-xs t-main font-bold truncate">${escapeHtml(app.name)}</b>
              </div>
            </div>
          </div>
          <!-- Left side: Recommended badge + Tutorial button -->
          <div class="flex items-center gap-1.5 flex-shrink-0">
            ${app.isRecommended ? '<span class="w-6 h-6 rounded-full flex items-center justify-center text-xs bg-amber-500/25 text-amber-600 dark:text-amber-300 border border-amber-500/60 font-black shadow-sm flex-shrink-0" title="پیشنهادی">⭐️</span>' : ''}
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
      if (yPane && activeYearBtn) {
        const topPos = activeYearBtn.offsetTop - yPane.offsetTop - (yPane.clientHeight / 2) + (activeYearBtn.clientHeight / 2);
        yPane.scrollTop = Math.max(0, topPos);
        if (typeof activeYearBtn.scrollIntoView === 'function') {
          activeYearBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }
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
  const showText = displayText || String(val);
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
    selectBdayItem('day', maxDays, String(maxDays), false);
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
      btn.textContent = String(d);
      btn.onclick = () => selectBdayItem('day', d, String(d), false);
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
      btn.onclick = () => selectBdayItem('month', mVal, mName, false);
      monthGrid.appendChild(btn);
    });
  }

  if (yearGrid && yearGrid.children.length === 0) {
    for (let y = 1406; y >= 1350; y--) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.setAttribute('data-val', y);
      btn.className = 'bday-grid-btn py-1.5 px-0.5 text-center text-xs text-slate-300 bg-slate-800/80 hover:bg-slate-700 border border-slate-700/60 rounded-xl transition font-mono active:scale-95';
      btn.textContent = String(y);
      btn.onclick = () => selectBdayItem('year', y, String(y), false);
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
        selectBdayItem('year', parts[0], String(parts[0]), false);
        selectBdayItem('month', parts[1], JALALI_MONTHS[parts[1] - 1] || parts[1], false);
        selectBdayItem('day', parts[2], String(parts[2]), false);
      }
    } catch (e) {}
  } else {
    selectBdayItem('year', 1375, '1375', false);
    selectBdayItem('month', 1, 'فروردین', false);
    selectBdayItem('day', 1, '1', false);
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
      iconBox.className = 'w-10 h-10 rounded-2xl bg-cyan-500/20 t-accent border border-cyan-500/30 flex items-center justify-center text-lg flex-shrink-0';
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
          <span class="text-[11px] text-slate-400 block mt-0.5">${opt.desc}</span>
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
      iconBox.className = 'w-10 h-10 rounded-2xl bg-amber-500/20 t-warn border border-amber-500/30 flex items-center justify-center text-lg flex-shrink-0';
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
          <span class="text-[11px] text-slate-400 block mt-0.5">${opt.desc}</span>
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
  const daysLeft = user?.days_until_birthday;
  const isToday = user?.is_birthday_today;
  const titleEl = $('birthdayCardTitle');
  const subEl = $('birthdayCardSubtitle');
  const badgeEl = $('birthdayCardBadge');

  if (!birthDate || !birthDate.trim()) {
    card.classList.remove('hidden');
    card.onclick = () => window.openBirthdayModal();
    if (titleEl) titleEl.innerText = '🎂 ثبت تاریخ زادروز و دریافت هدیه';
    if (subEl) subEl.innerText = 'با ثبت روز تولدتان، بسته ترافیک پرسرعت هدیه بگیرید';
    if (badgeEl) badgeEl.innerHTML = '<span class="text-xs">ثبت کنید ✨</span>';
    return;
  }

  card.onclick = () => (typeof window.openBirthdayCountdownModal === 'function' ? window.openBirthdayCountdownModal() : window.openBirthdayModal());
  card.classList.remove('hidden');

  if (isToday || daysLeft === 0) {
    if (titleEl) titleEl.innerText = '🎉 امروز روز زادروز شماست!';
    if (subEl) subEl.innerText = 'تولدت مبارک! هدیه ویژه شما فعال گردید 🎁';
    if (badgeEl) badgeEl.innerHTML = '<span>🎂</span> <span>مبارک باد!</span>';
  } else if (daysLeft !== null && daysLeft !== undefined) {
    if (titleEl) titleEl.innerText = 'شمارش معکوس زادروز شما';
    if (subEl) subEl.innerText = `تنها ${toEnglishDigits(daysLeft)} روز تا روز تولدتان باقی مانده است`;
    if (badgeEl) badgeEl.innerHTML = `<span>⏳</span> <span id="birthdayDaysLeftNum">${toEnglishDigits(daysLeft)}</span> <span>روز</span>`;
  } else {
    card.classList.remove('hidden');
    card.onclick = () => window.openBirthdayModal();
    if (titleEl) titleEl.innerText = 'تاریخ زادروز شما ثبت شده است';
    if (subEl) subEl.innerText = `تاریخ: ${birthDate}`;
    if (badgeEl) badgeEl.innerHTML = '<span class="text-xs">ویرایش ✏️</span>';
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
      paceStatusEl.className = 'font-bold text-[11px] t-warn';
      paceStatusEl.innerText = 'مهلت رو به پایان است';
    } else if (daysLeft === 0) {
      paceStatusEl.className = 'font-bold text-[11px] t-danger';
      paceStatusEl.innerText = 'منقضی شده';
    } else {
      paceStatusEl.className = 'font-bold text-[11px] t-success';
      paceStatusEl.innerText = 'بهینه';
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
        renderBarChart('repMonthlyChartCanvas', sub.month_weeks_totals_gb || [0, 0, 0, 0], ['هفته 1', 'هفته 2', 'هفته 3', 'هفته 4'], true);
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
        <div class="chat-user-bubble chat-bubble-user rounded-2xl rounded-tr-none p-2.5 leading-relaxed shadow-sm text-right">
          ${safeText}
          <span class="text-[11px] text-blue-400 dark:text-blue-300 block text-left mt-1 font-mono" dir="ltr">${timeStr}</span>
        </div>
      `;
    } else {
      bubble.className = 'self-end mr-auto ml-0 max-w-[85%] flex items-start gap-2 animate-fadeIn';
      bubble.innerHTML = `
        <div class="w-6 h-6 rounded-full bg-emerald-600 flex items-center justify-center text-[11px] shrink-0 text-white mt-0.5 shadow-sm">🎧</div>
        <div class="chat-admin-bubble chat-bubble-admin rounded-2xl rounded-tl-none p-2.5 leading-relaxed shadow-md text-right">
          ${safeText}
          <span class="text-[11px] t-muted block text-left mt-1 font-mono" dir="ltr">${timeStr}</span>
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

// Single source of truth for modal ids used by the Telegram BackButton sync
const APP_MODAL_IDS = [
  'revokeModal', 'switchAccountModal', 'activeSessionsModal',
  'topupModal', 'luckyWheelModal', 'storyCardModal',
  'supportChatModal', 'purchaseSuccessModal',
  'qrModal', 'checkoutConfirmModal', 'configsModal', 'tutorialModal',
  'shopGuidanceModal', 'speedTestModal', 'wheelResultModal',
  'speedResultsModal', 'birthdayModal', 'alertThresholdModal',
  'expiryCountdownModal', 'birthdayCountdownModal', 'giftModal',
  'giftServiceSelectModal', 'invoiceModal', 'loyaltyModal', 'killAllSessionsModal', 'killSingleDeviceModal',
];

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

  const activeTabBtn = document.querySelector('.nav-btn.is-active, .nav-btn[aria-selected="true"], .nav-btn.text-blue-400');
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

      const observedModalIds = [...APP_MODAL_IDS, 'qrContainer'];
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
          <span class="text-[11px] text-slate-400 mt-0.5 block font-mono num-bidi" dir="ltr">
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
  ['repDailyChartCanvas', 'repNightlyChartCanvas', 'repWeeklyChartCanvas', 'repMonthlyChartCanvas', 'repPeakHoursChartCanvas', 'repPeakHoursBarCanvas', 'userLeaderboardChartCanvas'].forEach(id => {
    if (window.chartInstances && window.chartInstances[id]) {
      try { window.chartInstances[id].destroy(); } catch(e) {}
      delete window.chartInstances[id];
    }
  });

  // 2. Hide canvases and display clean empty states on daily, nightly, weekly & monthly cards
  const dailyCanvas = $('repDailyChartCanvas');
  const dailyEmpty = $('repDailyEmptyState');
  if (dailyCanvas) dailyCanvas.classList.add('hidden');
  if (dailyEmpty) dailyEmpty.classList.remove('hidden');

  const nightlyCanvas = $('repNightlyChartCanvas');
  const nightlyEmpty = $('repNightlyEmptyState');
  if (nightlyCanvas) nightlyCanvas.classList.add('hidden');
  if (nightlyEmpty) nightlyEmpty.classList.remove('hidden');

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
  currentMonthlyIndex = 0;
  const repMonthlyCurrentLabel = $('repMonthlyCurrentLabel');
  if (repMonthlyCurrentLabel) repMonthlyCurrentLabel.innerText = '—';
  const repMonthlyPeriodBadge = $('repMonthlyPeriodBadge');
  if (repMonthlyPeriodBadge) repMonthlyPeriodBadge.innerText = 'ماه جاری';
  const prevMonthBtn = $('repMonthPrevBtn');
  const nextMonthBtn = $('repMonthNextBtn');
  if (prevMonthBtn) {
    prevMonthBtn.disabled = true;
    prevMonthBtn.classList.add('opacity-40', 'cursor-not-allowed');
  }
  if (nextMonthBtn) {
    nextMonthBtn.disabled = true;
    nextMonthBtn.classList.add('opacity-40', 'cursor-not-allowed');
  }

  // 3. Reset Burn Rate & Analytics
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
  if (analysisBox) analysisBox.className = 'p-2 rounded-xl text-xs t-muted flex items-start gap-2 bg-transparent border-0';

  ['periodDawnVal', 'periodMorningVal', 'periodAfternoonVal', 'periodNightVal',
   'repDailyPeriodDawnVal', 'repDailyPeriodMornVal', 'repDailyPeriodAftVal', 'repDailyPeriodNgtVal',
   'repNightlyPeriodDawnVal', 'repNightlyPeriodMornVal', 'repNightlyPeriodAftVal', 'repNightlyPeriodNgtVal'
  ].forEach(id => { const el = $(id); if (el) el.innerText = '0.00 GB'; });

  ['periodDawnPercent', 'periodMorningPercent', 'periodAfternoonPercent', 'periodNightPercent',
   'repDailyPeriodDawnPct', 'repDailyPeriodMornPct', 'repDailyPeriodAftPct', 'repDailyPeriodNgtPct',
   'repNightlyPeriodDawnPct', 'repNightlyPeriodMornPct', 'repNightlyPeriodAftPct', 'repNightlyPeriodNgtPct'
  ].forEach(id => { const el = $(id); if (el) el.innerText = '0%'; });

  const countryCanvas = $('repCountryChartCanvas');
  const countryEmpty = $('repCountryEmptyState');
  if (countryCanvas) countryCanvas.classList.add('hidden');
  if (countryEmpty) countryEmpty.classList.remove('hidden');

  const devCanvas = $('repDeviceChartCanvas');
  const devEmpty = $('repDeviceEmptyState');
  if (devCanvas) devCanvas.classList.add('hidden');
  if (devEmpty) devEmpty.classList.remove('hidden');
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
      const hasRealTraffic = Boolean(
        (sub.hourly_usage?.has_real_data || hourlyData.some(v => Number(v) > 0)) &&
        hourlyData.length > 0
      );

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
          renderBarChart('repDailyChartCanvas', hourlyData, hourlyLabels, false);
          const yData = sub.yesterday_hourly_usage?.data || Array(12).fill(0);
          const yLabels = sub.yesterday_hourly_usage?.labels || hourlyLabels;
          const hasY = Boolean((sub.yesterday_used_gb && Number(sub.yesterday_used_gb) > 0) || yData.some(v => Number(v) > 0));
          const nCanvas = $('repNightlyChartCanvas');
          const nEmpty = $('repNightlyEmptyState');
          if (nCanvas) nCanvas.classList.toggle('hidden', !hasY);
          if (nEmpty) nEmpty.classList.toggle('hidden', hasY);
          if (hasY) {
            renderBarChart('repNightlyChartCanvas', yData, yLabels, false);
          }
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
          const dawnPct = `${Math.round((dawnSum / totalPeriods) * 100)}%`;
          const mornPct = `${Math.round((morningSum / totalPeriods) * 100)}%`;
          const aftPct = `${Math.round((afternoonSum / totalPeriods) * 100)}%`;
          const ngtPct = `${Math.round((nightSum / totalPeriods) * 100)}%`;

          const dawnTraffic = fmtTraffic(dawnSum, { isBytes: false });
          const mornTraffic = fmtTraffic(morningSum, { isBytes: false });
          const aftTraffic = fmtTraffic(afternoonSum, { isBytes: false });
          const ngtTraffic = fmtTraffic(nightSum, { isBytes: false });

          ['periodDawnVal', 'repDailyPeriodDawnVal', 'repNightlyPeriodDawnVal'].forEach(id => { const el = $(id); if (el) el.innerHTML = dawnTraffic; });
          ['periodDawnPercent', 'repDailyPeriodDawnPct', 'repNightlyPeriodDawnPct'].forEach(id => { const el = $(id); if (el) el.innerText = dawnPct; });

          ['periodMorningVal', 'repDailyPeriodMornVal', 'repNightlyPeriodMornVal'].forEach(id => { const el = $(id); if (el) el.innerHTML = mornTraffic; });
          ['periodMorningPercent', 'repDailyPeriodMornPct', 'repNightlyPeriodMornPct'].forEach(id => { const el = $(id); if (el) el.innerText = mornPct; });

          ['periodAfternoonVal', 'repDailyPeriodAftVal', 'repNightlyPeriodAftVal'].forEach(id => { const el = $(id); if (el) el.innerHTML = aftTraffic; });
          ['periodAfternoonPercent', 'repDailyPeriodAftPct', 'repNightlyPeriodAftPct'].forEach(id => { const el = $(id); if (el) el.innerText = aftPct; });

          ['periodNightVal', 'repDailyPeriodNgtVal', 'repNightlyPeriodNgtVal'].forEach(id => { const el = $(id); if (el) el.innerHTML = ngtTraffic; });
          ['periodNightPercent', 'repDailyPeriodNgtPct', 'repNightlyPeriodNgtPct'].forEach(id => { const el = $(id); if (el) el.innerText = ngtPct; });
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
      const countryCanvas = $('repCountryChartCanvas');
      const countryEmpty = $('repCountryEmptyState');
      const countryLabels = sub.country_share?.labels?.length ? sub.country_share.labels : [];
      const countryData = sub.country_share?.data?.length ? sub.country_share.data : [];
      const hasCountryData = countryData.some(v => Number(v) > 0);

      if (!hasCountryData) {
        if (countryCanvas) countryCanvas.classList.add('hidden');
        if (countryEmpty) countryEmpty.classList.remove('hidden');
      } else {
        if (countryCanvas) countryCanvas.classList.remove('hidden');
        if (countryEmpty) countryEmpty.classList.add('hidden');
        renderDonutChart('repCountryChartCanvas', countryLabels, countryData, false);
      }
    } catch (e) {
      console.warn('Error rendering country donut chart', e);
    }

    // 4. Device Platform Donut Chart
    try {
      const devCanvas = $('repDeviceChartCanvas');
      const devEmpty = $('repDeviceEmptyState');
      const devLabels = sub.device_share?.labels?.length ? sub.device_share.labels : [];
      const devData = sub.device_share?.data?.length ? sub.device_share.data : [];
      const hasDevData = devData.some(v => Number(v) > 0);

      if (!hasDevData) {
        if (devCanvas) devCanvas.classList.add('hidden');
        if (devEmpty) devEmpty.classList.remove('hidden');
      } else {
        if (devCanvas) devCanvas.classList.remove('hidden');
        if (devEmpty) devEmpty.classList.add('hidden');
        renderDonutChart('repDeviceChartCanvas', devLabels, devData, true);
      }
    } catch (e) {
      console.warn('Error rendering device donut chart', e);
    }
  }
}

// 15. Phased, Resilient UI Hydration Logic
function hydrateUserInterface(data) {
  if (!data || typeof data !== 'object') return;

  // --- Support Contact Visibility & Handler ---
  const rawSupportContact = data.support_contact || '';
  const supportLink = data.support_link || '';
  const hasSupportContact = Boolean(supportLink && rawSupportContact && rawSupportContact !== '—' && rawSupportContact !== '-');

  const maintSupportBox = $('maintSupportBox');
  if (maintSupportBox) {
    if (hasSupportContact) maintSupportBox.classList.remove('hidden');
    else maintSupportBox.classList.add('hidden');
  }

  const inviteSupportBox = $('inviteSupportBox');
  if (inviteSupportBox) {
    if (hasSupportContact) inviteSupportBox.classList.remove('hidden');
    else inviteSupportBox.classList.add('hidden');
  }

  // --- Maintenance & Invite-Only Gateways (Unified Experience) ---
  const isBlocked = (data.is_maintenance || data.is_invite_only) && !data.user?.is_admin;
  window.isSystemBlocked = Boolean(isBlocked);
  const maintScreen = $('systemMaintenanceScreen');
  const inviteScreen = $('systemInviteOnlyScreen');

  if (data.is_maintenance && !data.user?.is_admin) {
    if (maintScreen) maintScreen.classList.remove('hidden');
    if (inviteScreen) inviteScreen.classList.add('hidden');
  } else if (data.is_invite_only && !data.user?.is_admin) {
    if (inviteScreen) inviteScreen.classList.remove('hidden');
    if (maintScreen) maintScreen.classList.add('hidden');
  } else {
    if (maintScreen) maintScreen.classList.add('hidden');
    if (inviteScreen) inviteScreen.classList.add('hidden');
  }

  if (isBlocked) {
    const splash = $('splashScreen'); if (splash) splash.classList.add('hidden');
    $('topHeaderBar')?.classList.remove('hidden');
    $('bottomNavigationBar')?.classList.add('hidden');
    $('navBottom')?.classList.add('hidden');
    document.querySelector('nav')?.classList.add('hidden');
    document.querySelectorAll('.tab-pane').forEach(el => el.classList.add('hidden'));

    // Populate user identity in header so avatar and username are shown cleanly
    const user = data.user || {};
    const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
    const sub = data.active_sub;
    const avatarEl = $('headerUserAvatarInitial') || $('headerUserAvatar');
    if (avatarEl) {
      avatarEl.innerText = (user.first_name || user.username || tgUser?.first_name || tgUser?.username || 'U')[0].toUpperCase();
    }
    const usernameEl = $('headerUsername');
    if (usernameEl) {
      usernameEl.innerText = sub?.username || user.username || user.first_name || tgUser?.username || tgUser?.first_name || 'کاربر';
    }
    return;
  }

  $('navBottom')?.classList.remove('hidden');

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
        profPhone.innerHTML = `<span class="text-white font-mono font-bold" dir="ltr">${toEnglishDigits(user.phone_number)}</span> <span class="t-success text-xs inline-flex items-center" title="تأیید شده">✅</span>`;
      }
    } else {
      if (phoneRewardCard) phoneRewardCard.classList.remove('hidden');
      if (warningCard) warningCard.classList.remove('hidden');
      if (verifyBtn) verifyBtn.classList.remove('hidden');
      if (profPhone) {
        profPhone.innerText = 'وارد نشده';
      }
    }
    if (profJoin) profJoin.innerText = user.created_at_jalali ? toEnglishDigits(user.created_at_jalali) : '—';
    if (profBirth) profBirth.innerText = user.birth_date ? toEnglishDigits(user.birth_date) : 'ثبت‌نشده';

    const bdayBtn = $('openBirthdayModalBtn');
    if (bdayBtn) {
      bdayBtn.className = 't-pink hover:text-pink-300 text-xs transition active:scale-95 bg-transparent border-0 p-0 shadow-none';
      bdayBtn.innerHTML = '<span>✏️</span>';
      bdayBtn.title = user.birth_date ? 'ویرایش تاریخ تولد' : 'ثبت تاریخ تولد';
    }

    const hasActiveSub = Boolean(data.has_active_sub && (sub?.status === 'ACTIVE' || !sub?.status));
    if (profStatusBadge) {
      if (hasActiveSub) {
        profStatusBadge.innerHTML = '<span class="inline-flex items-center gap-1"><span>🟢</span><span>کاربر فعال</span></span>';
        profStatusBadge.className = 'badge badge-success rounded-full text-[11px] font-bold inline-flex items-center gap-1';
      } else {
        profStatusBadge.innerHTML = '<span class="inline-flex items-center gap-1"><span>⚪️</span><span>بدون سرویس فعال</span></span>';
        profStatusBadge.className = 'badge badge-warn rounded-full text-[11px] font-bold inline-flex items-center gap-1';
      }
    }

    if (profAuthBadge) {
      if (hasPhone) {
        profAuthBadge.innerHTML = '<span class="inline-flex items-center gap-1"><span>🛡️</span><span>حساب تأییدشده</span></span>';
        profAuthBadge.className = 'px-2.5 py-0.5 rounded-full text-[10.5px] font-bold bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30 inline-flex items-center gap-1 transition';
      } else {
        profAuthBadge.innerHTML = '<span class="inline-flex items-center gap-1"><span>⚠️</span><span>نیازمند احراز شماره</span></span>';
        profAuthBadge.className = 'px-2.5 py-0.5 rounded-full text-[10.5px] font-bold bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30 inline-flex items-center gap-1 transition';
      }
    }

    if (profSub) {
      if (hasActiveSub) {
        profSub.innerText = 'فعال';
        profSub.className = 'font-semibold t-success';
      } else {
        profSub.innerText = 'غیرفعال';
        profSub.className = 'font-semibold t-danger';
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

    // --- VIP Loyalty Tier & Club Integration ---
    const loyalty = data.loyalty;
    const isLoyaltyEnabled = Boolean(loyalty && loyalty.enabled !== false);
    const headerBadge = $('headerLoyaltyBadge');
    if (headerBadge) {
      if (isLoyaltyEnabled) {
        headerBadge.innerText = loyalty.icon || '🥉';
        headerBadge.classList.remove('hidden');
        headerBadge.className = 'w-7 h-7 flex items-center justify-center text-lg bg-transparent border-0 transition cursor-pointer active:scale-95 shrink-0 select-none';
      } else {
        headerBadge.classList.add('hidden');
      }
    }

    const loyaltyCard = $('profileLoyaltyCard');
    if (loyaltyCard) {
      if (!isLoyaltyEnabled) {
        loyaltyCard.classList.add('hidden');
      } else {
        loyaltyCard.classList.remove('hidden');
        if ($('loyaltyTierIcon')) $('loyaltyTierIcon').innerText = loyalty.icon || '🥉';
        if ($('loyaltyTierName')) $('loyaltyTierName').innerText = loyalty.name || 'برنزی';
        const discBadge = $('loyaltyDiscountBadge');
        if (discBadge) {
          discBadge.innerHTML = loyalty.discount_percent > 0 ? `<span class="font-sans font-bold num-bidi" dir="ltr">${toEnglishDigits(loyalty.discount_percent)}%</span> تخفیف` : 'بدون تخفیف';
        }
        const nextText = $('loyaltyNextTierText');
        const progPct = $('loyaltyProgressPct');
        const progBar = $('loyaltyProgressBar');
        const totalSpent = $('loyaltyTotalSpent');
        const targetSpent = $('loyaltyNextTierTarget');
        const benefitDesc = $('loyaltyBenefitDesc');

        if (totalSpent) totalSpent.innerText = `مجموع خرید: ${Number(loyalty.total_spent || 0).toLocaleString('en-US')} تومان`;

        if (loyalty.next_tier_name && loyalty.next_tier_threshold) {
          const pct = loyalty.progress_percent ?? loyalty.progress_pct ?? 0;
          if (nextText) nextText.innerText = `تا سطح بعدی (${loyalty.next_tier_name}):`;
          if (progPct) progPct.innerText = `${pct}%`;
          if (progBar) progBar.style.width = `${pct}%`;
          if (targetSpent) targetSpent.innerText = `هدف بعدی: ${Number(loyalty.next_tier_threshold).toLocaleString('en-US')} تومان`;
        } else {
          if (nextText) nextText.innerText = 'بالاترین سطح باشگاه مشتریان 🎉';
          if (progPct) progPct.innerText = '100%';
          if (progBar) progBar.style.width = '100%';
          if (targetSpent) targetSpent.innerText = `${loyalty.name || 'الماس'}`;
        }

        if (benefitDesc) {
          if (loyalty.discount_percent > 0) {
            benefitDesc.innerHTML = `شما دارای <span class="num-bidi font-sans font-bold" dir="ltr">${toEnglishDigits(loyalty.discount_percent)}%</span> تخفیف وفاداری روی تمامی بسته‌ها هستید. با افزایش خریدها، به سطوح بالاتر با تخفیف‌های بیشتر ارتقا&nbsp;می‌یابید!`;
          } else {
            benefitDesc.innerText = 'با خرید بیشتر از فروشگاه، سطح خود را ارتقا دهید و از تخفیف روی تمامی بسته‌ها بهره‌مند شوید.';
          }
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
    if (refCountEl) refCountEl.innerHTML = `<span class="font-mono font-bold">${toEnglishDigits(refCount)}</span> <span class="font-sans">نفر</span>`;
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

        // Dynamic color transition as remaining traffic decreases
        if (pct <= 15) {
          gaugeProgress.setAttribute('stroke', 'url(#gradientDanger)');
        } else if (pct <= 35) {
          gaugeProgress.setAttribute('stroke', 'url(#gradientWarn)');
        } else {
          gaugeProgress.setAttribute('stroke', 'url(#gradientMain)');
        }
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
      if (gaugeProgress) { gaugeProgress.style.strokeDashoffset = 314.15; gaugeProgress.setAttribute('stroke', 'url(#gradientMain)'); }
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

    function formatDeviceDate(isoStr) {
      if (!isoStr) return '';
      try {
        const dateObj = new Date(isoStr);
        if (!isNaN(dateObj.getTime())) {
          const dateFa = dateObj.toLocaleDateString('fa-IR');
          const timeFa = dateObj.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' });
          return `${toEnglishDigits(timeFa)} - ${toEnglishDigits(dateFa)}`;
        }
      } catch(e) {}
      return String(isoStr);
    }

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

        const model = d.deviceModel || d.model || d.platform || 'دستگاه متصل';
        const ip = d.requestIp || d.ip || d.clientIp || '—';
        const hwid = d.hwid || '';

        const ua = String(d.userAgent || d.user_agent || '').trim();
        let cleanUa = ua;
        if (ua) {
          const clients = [
            'v2rayNG', 'Happ', 'Hiddify', 'Streisand', 'V2Box', 'Incy', 'NekoBox',
            'ClashMeta', 'Clash', 'Sing-box', 'sing-box', 'Shadowrocket', 'Quantumult',
            'Surge', 'Loon', 'Foxray', 'Karing', 'Wings', 'WireGuard', 'Outline'
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
        const uaHtml = cleanUa ? `
          <div class="text-[10.5px] text-cyan-400/90 truncate mt-0.5 font-sans" title="${escapeHtml(ua)}">
            <span class="text-slate-400">کلاینت:</span> ${escapeHtml(cleanUa)}
          </div>
        ` : '';

        const updatedRaw = d.updatedAt || d.updated_at || d.lastSeen || d.lastActivity;
        const updatedDate = formatDeviceDate(updatedRaw);
        const updatedHtml = updatedDate ? `
          <div class="flex items-center justify-between text-slate-400">
            <span class="flex items-center gap-1"><span>🔄</span> آخرین فعالیت:</span>
            <span class="font-sans font-medium text-slate-200 num-bidi" dir="ltr">${updatedDate}</span>
          </div>
        ` : '';

        const addedRaw = d.createdAt || d.created_at || d.addedAt;
        const addedDate = formatDeviceDate(addedRaw);
        const addedHtml = addedDate ? `
          <div class="flex items-center justify-between text-slate-400">
            <span class="flex items-center gap-1"><span>📅</span> زمان ثبت:</span>
            <span class="font-sans font-medium text-slate-300 num-bidi" dir="ltr">${addedDate}</span>
          </div>
        ` : '';

        return `
          <div class="card-inset rounded-2xl p-3 border border-slate-700/60 space-y-2 text-xs">
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2.5 min-w-0 flex-1">
                <span class="text-2xl shrink-0">${icon}</span>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-1.5 flex-wrap">
                    <span class="text-xs font-bold text-slate-200 truncate">${escapeHtml(model)}</span>
                    <span class="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-500 bg-emerald-500/10 px-1.5 py-0.5 rounded-full border border-emerald-500/20">
                      <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                      <span>فعال</span>
                    </span>
                  </div>
                  ${uaHtml}
                </div>
              </div>
              <button class="kill-device-btn t-danger hover:text-rose-300 w-8 h-8 rounded-xl bg-transparent hover:bg-rose-950/30 border border-rose-800/40 text-xs transition active:scale-95 flex items-center justify-center shrink-0 cursor-pointer" title="قطع این دستگاه" data-hwid="${escapeHtml(hwid)}" data-model="${escapeHtml(model)}" data-ip="${escapeHtml(ip)}">
                <svg class="w-4 h-4 t-danger hover:text-rose-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
            </div>

            <!-- Device Meta: IP, Updated, Added -->
            <div class="pt-1.5 border-t border-slate-700/40 text-[11px] font-sans space-y-1">
              <div class="flex items-center justify-between text-slate-400">
                <span class="flex items-center gap-1"><span>🌐</span> آی‌پی:</span>
                <span class="font-sans font-bold t-accent num-bidi" dir="ltr">${escapeHtml(ip)}</span>
              </div>
              ${addedHtml}
              ${updatedHtml}
            </div>
          </div>
        `;
      }).join('');

      container.querySelectorAll('.kill-device-btn').forEach(btn => {
        btn.onclick = () => {
          const hwid = btn.getAttribute('data-hwid');
          const model = btn.getAttribute('data-model') || 'دستگاه متصل';
          const ip = btn.getAttribute('data-ip') || '';
          if (!hwid) return;
          openKillSingleDeviceModal(hwid, model, ip);
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
          <div class="p-3 card-inset text-center text-xs t-muted">
            <span>ℹ️ امروز هنوز ترافیکی روی سرورها ثبت نشده است.</span>
          </div>
        `;
      } else {
        const showBar = bDown.length > 1;
        countryList.innerHTML = bDown.map(item => {
          const pct = item.percent || 0;
          const barHtml = (showBar && pct > 0)
            ? `<div class="w-full card-inset h-1.5 rounded-full overflow-hidden" dir="ltr">
                <div class="bg-gradient-to-r from-blue-500 to-cyan-400 h-full rounded-full transition-all duration-500" style="width: ${pct}%;"></div>
              </div>`
            : '';
          return `
          <div class="p-2.5 card-inset space-y-1.5">
            <div class="flex justify-between items-center text-xs">
              <span class="t-accent font-black text-xs font-mono num-bidi" dir="ltr">${fmtTraffic(item.total_formatted, { html: false })}</span>
              <span class="flex items-center gap-2 font-bold t-main">
                <span>${escapeHtml(item.name || '')}</span>
                <span class="text-base">${typeof renderFlagHtml === 'function' ? renderFlagHtml(item.flag || '🌐', 'w-4 h-3 inline-block rounded-xs shadow-xs object-cover align-middle') : escapeHtml(item.flag || '🌐')}</span>
              </span>
            </div>
            ${barHtml}
          </div>
          `;
        }).join('');
      }
    }

    // Reports Hub
    if (data.today_jalali) {
      const repDailyDateEl = $('repDailyDate');
      if (repDailyDateEl) repDailyDateEl.innerText = `${toEnglishDigits(data.today_jalali)} - 23:59`;
    }
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

      // Daily report card
      const repDailyTotal = $('repDailyTotal');
      if (repDailyTotal) repDailyTotal.innerText = fmtTraffic(sub.traffic_total_gb, { html: false });
      const repDailyUsed = $('repDailyUsed');
      if (repDailyUsed) repDailyUsed.innerText = fmtTraffic(sub.traffic_used_gb, { html: false });
      const repDailyRemain = $('repDailyRemain');
      if (repDailyRemain) repDailyRemain.innerText = fmtTraffic(sub.traffic_remaining_gb, { html: false });
      const repDailyToday = $('repDailyToday');
      if (repDailyToday) repDailyToday.innerText = fmtTraffic(sub.today_used_gb ?? '0.00', { html: false });
      const repDailyExpire = $('repDailyExpire');
      if (repDailyExpire) repDailyExpire.innerText = `${toEnglishDigits(sub.days_left ?? 0)} روز (${toEnglishDigits(sub.expire_jalali || 'نامحدود')})`;

      // Nightly report card
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
        renderNodeBreakdown('repDailyNodesContainer', sub.today_breakdown || [], 'امروز مصرفی روی سرورها ثبت نشده است.');
        renderNodeBreakdown('repNightlyNodesContainer', sub.yesterday_breakdown || sub.today_breakdown || [], 'دیشب مصرفی روی سرورها ثبت نشده است.');
        renderNodeBreakdown('repWeeklyNodesContainer', sub.week_breakdown || [], 'مصرفی در 7 روز گذشته ثبت نشده است.');
      }

      const repWeeklyTotal = $('repWeeklyTotal');
      if (repWeeklyTotal) repWeeklyTotal.innerHTML = fmtTraffic(sub.week_used_gb ?? '0.00', { html: true });
      const repWeeklyBusiest = $('repWeeklyBusiest');
      if (repWeeklyBusiest) {
        repWeeklyBusiest.innerHTML = `${sub.busiest_day_name || '—'} <span class="font-mono t-accent font-bold num-bidi">(${fmtTraffic(sub.busiest_day_amount || '0 GB', { html: false })})</span>`;
      }

      if (typeof renderBarChart === 'function') {
        try {
          renderBarChart('repWeeklyChartCanvas', sub.week_daily_totals_gb || [0, 0, 0, 0, 0, 0, 0], sub.week_day_labels || ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'], false);
        } catch (e) {
          console.warn('Could not render weekly chart:', e);
        }
      }

      if (typeof updateMonthlyReportView === 'function') {
        updateMonthlyReportView(currentMonthlyIndex);
      } else {
        const repMonthlyTitle = $('repMonthlyTitle');
        if (repMonthlyTitle) repMonthlyTitle.innerText = `📅 گزارش جامع ماه ${sub.current_month_name || ''}`;
        const repMonthlyTotal = $('repMonthlyTotal');
        if (repMonthlyTotal) repMonthlyTotal.innerHTML = fmtTraffic(sub.month_used_gb ?? '0.00', { html: true });
        if (typeof renderBarChart === 'function') {
          try {
            renderBarChart('repMonthlyChartCanvas', sub.month_weeks_totals_gb || [0, 0, 0, 0], ['هفته 1', 'هفته 2', 'هفته 3', 'هفته 4'], true);
          } catch (e) {
            console.warn('Could not render monthly chart:', e);
          }
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

    // User Achievements & Perks Card
    if (typeof renderUserAchievements === 'function') {
      renderUserAchievements(data);
    }

    // User Leaderboard (Top 20 Consumers)
    if (typeof renderUserLeaderboard === 'function') {
      renderUserLeaderboard(data?.leaderboard, window.currentUserLbPeriod || 'weekly');
    }

    // Tutorial App Updates Badge
    if (typeof checkTutorialAppUpdates === 'function') {
      checkTutorialAppUpdates();
    }
  });
}

function renderUserAchievements(data) {
  const ach = data?.achievements || {};
  const wonCoupons = data?.won_coupons || [];

  const giftTrafficEl = $('achieveGiftTraffic');
  if (giftTrafficEl) {
    const traf = Number(ach.total_gift_traffic_gb || 0);
    giftTrafficEl.innerText = typeof fmtTraffic === 'function' ? fmtTraffic(traf, { html: false }) : `${traf.toFixed(1)}`;
  }

  const wonCouponsEl = $('achieveWonCoupons');
  const couponsActionEl = $('achieveCouponsAction');
  if (wonCouponsEl) {
    const count = Number(ach.active_coupons_count ?? wonCoupons.length);
    wonCouponsEl.innerText = `${typeof toPersianDigits === 'function' ? toPersianDigits(count) : count} کد`;
    if (couponsActionEl) {
      if (count > 0) {
        couponsActionEl.innerText = 'کپی آخرین کد';
        couponsActionEl.className = 'text-[11px] t-success mt-0.5 font-medium hover:underline bg-transparent border-0 p-0';
      } else {
        couponsActionEl.innerText = 'بدون کد فعال';
        couponsActionEl.className = 'text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 font-medium cursor-default bg-transparent border-0 p-0';
      }
    }
  }

  const bdayStatusEl = $('achieveBdayStatus');
  const bdayBtn = $('achieveBdayBtn');
  if (bdayStatusEl) {
    if (ach.birthday_claimed) {
      bdayStatusEl.innerText = '🎁 دریافت شده';
      bdayStatusEl.className = 't-success text-[11px] font-bold truncate max-w-full';
      if (bdayBtn) bdayBtn.innerText = 'هدیه ثبت شد';
    } else if (ach.is_birthday_today) {
      bdayStatusEl.innerText = '🎉 امروز زادروز شماست!';
      bdayStatusEl.className = 'text-amber-500 dark:text-amber-300 text-[11px] font-bold truncate max-w-full animate-pulse';
      if (bdayBtn) bdayBtn.innerText = 'تبریک زادروز 🎂';
    } else if (ach.has_birthday_set && ach.days_until_birthday !== null && ach.days_until_birthday !== undefined) {
      const d = ach.days_until_birthday;
      bdayStatusEl.innerText = d === 0 ? 'امروز' : `${d} روز مانده`;
      bdayStatusEl.className = 't-accent text-[11px] font-bold truncate max-w-full';
      if (bdayBtn) bdayBtn.innerText = 'ویرایش تاریخ';
    } else {
      bdayStatusEl.innerText = 'ثبت نشده';
      bdayStatusEl.className = 't-warn text-[11px] font-bold truncate max-w-full';
      if (bdayBtn) bdayBtn.innerText = 'ثبت تاریخ';
    }
  }

  const streakEl = $('achieveStreakCount');
  if (streakEl) {
    const s = Number(ach.wheel_streak ?? data?.wheel_status?.streak ?? 0);
    streakEl.innerText = `${s} روز`;
  }

  const spinTicketsEl = $('achieveSpinTickets');
  if (spinTicketsEl) {
    const t = Number(ach.spin_tickets ?? data?.wheel_status?.spin_tickets ?? 0);
    spinTicketsEl.innerText = `${t} عدد`;
  }
}
window.renderUserAchievements = renderUserAchievements;

let cachedUserLeaderboardData = null;
let currentUserLbPeriod = 'weekly';
let currentUserLbMonthIndex = 0;
let userLeaderboardChartInstance = null;

function switchUserLeaderboardPeriod(period) {
  currentUserLbPeriod = period;
  window.currentUserLbPeriod = period;
  const tabDaily = $('userLbTabDaily');
  const tabNightly = $('userLbTabNightly');
  const tabWeekly = $('userLbTabWeekly');
  const tabMonthly30d = $('userLbTabMonthly30d');
  const tabMonthly = $('userLbTabMonthly');
  const monthBar = $('userLbMonthBar');

  const tabs = [
    { el: tabDaily, id: 'daily' },
    { el: tabNightly, id: 'nightly' },
    { el: tabWeekly, id: 'weekly' },
    { el: tabMonthly30d, id: 'monthly_30d' },
    { el: tabMonthly, id: 'monthly' },
  ];

  tabs.forEach(t => {
    if (!t.el) return;
    if (t.id === period) {
      t.el.className = 'w-full py-2 rounded-lg font-bold transition bg-cyan-600 text-white shadow text-center text-xs';
    } else {
      t.el.className = 'w-full py-2 rounded-lg font-medium transition text-slate-400 hover:text-white text-center text-xs';
    }
  });

  if (monthBar) {
    if (period === 'monthly') {
      monthBar.classList.remove('hidden');
      currentUserLbMonthIndex = 0;
    } else {
      monthBar.classList.add('hidden');
    }
  }

  if (cachedUserLeaderboardData) {
    renderUserLeaderboard(cachedUserLeaderboardData, period);
  }
}
window.switchUserLeaderboardPeriod = switchUserLeaderboardPeriod;

function navigateUserLbMonth(dir) {
  const avail = cachedUserLeaderboardData?.available_months || [];
  if (avail.length === 0) return;
  // dir = -1 (prev/older month) -> index increases
  // dir = 1 (next/newer month) -> index decreases
  currentUserLbMonthIndex = Math.max(0, Math.min(avail.length - 1, currentUserLbMonthIndex - dir));
  switchUserLbWeek('all');
}
window.navigateUserLbMonth = navigateUserLbMonth;

const JALALI_MONTHS_MAP = {
  'Farvardin': 'فروردین', 'Ordibehesht': 'اردیبهشت', 'Khordad': 'خرداد',
  'Tir': 'تیر', 'Mordad': 'مرداد', 'Shahrivar': 'شهریور',
  'Mehr': 'مهر', 'Aban': 'آبان', 'Azar': 'آذر',
  'Dey': 'دی', 'Bahman': 'بهمن', 'Esfand': 'اسفند'
};
function toPersianMonthName(m) {
  if (!m) return '';
  return JALALI_MONTHS_MAP[m] || m;
}

let currentUserLbWeek = 'all';

function switchUserLbWeek(week) {
  currentUserLbWeek = week;
  const activeClass = 'py-1 rounded-lg bg-cyan-600 text-white shadow text-center transition font-bold';
  const inactiveClass = 'py-1 rounded-lg t-muted hover:t-main text-center transition';
  const weekMap = {
    all: 'userLbWeekAllBtn',
    week1: 'userLbWeek1Btn',
    week2: 'userLbWeek2Btn',
    week3: 'userLbWeek3Btn',
    week4: 'userLbWeek4Btn',
  };
  Object.entries(weekMap).forEach(([w, btnId]) => {
    const btn = $(btnId);
    if (btn) btn.className = (w === week) ? activeClass : inactiveClass;
  });
  renderUserLeaderboard();
}
window.switchUserLbWeek = switchUserLbWeek;

function renderUserLeaderboard(leaderboardData, period = currentUserLbPeriod) {
  if (leaderboardData) cachedUserLeaderboardData = leaderboardData;

  const avail = cachedUserLeaderboardData?.available_months || [];
  let periodData = null;
  let activeMonthName = '';
  let hasWeeks = false;

  if (period === 'monthly') {
    activeMonthName = avail[currentUserLbMonthIndex] || avail[0] || '';
    const fullMonthData = (activeMonthName && cachedUserLeaderboardData?.calendar_months?.[activeMonthName])
      || cachedUserLeaderboardData?.monthly
      || {};
    hasWeeks = Boolean(fullMonthData.weeks && Object.keys(fullMonthData.weeks).length > 0);
    if (currentUserLbWeek !== 'all' && fullMonthData.weeks?.[currentUserLbWeek]) {
      periodData = fullMonthData.weeks[currentUserLbWeek];
    } else {
      periodData = fullMonthData;
    }
  } else {
    periodData = cachedUserLeaderboardData?.[period] || cachedUserLeaderboardData?.weekly || {};
  }

  const top20 = periodData.top_20 || [];
  const inTop20 = Boolean(periodData.in_top_20);
  const myRank = periodData.my_rank;
  const myUsedGb = Number(periodData.my_used_gb || 0);
  const diffGb = Number(periodData.diff_gb || 0);

  // Sync month navigation bar and 4-week breakdown
  const monthBar = $('userLbMonthBar');
  const weekBar = $('userLbWeekBar');
  const prevBtn = $('userLbMonthPrevBtn');
  const nextBtn = $('userLbMonthNextBtn');
  const prevLabel = $('userLbMonthPrevLabel');
  const nextLabel = $('userLbMonthNextLabel');
  const curLabel = $('userLbMonthCurrentLabel');

  if (period !== 'monthly') {
    if (monthBar) monthBar.classList.add('hidden');
    if (weekBar) weekBar.classList.add('hidden');
  } else {
    if (monthBar) monthBar.classList.remove('hidden');
    if (weekBar) {
      if (hasWeeks) {
        weekBar.classList.remove('hidden');
      } else {
        weekBar.classList.add('hidden');
      }
    }
    if (curLabel) curLabel.innerText = activeMonthName ? `ماه ${toPersianMonthName(activeMonthName)}` : '--';

    const prevMName = avail[currentUserLbMonthIndex + 1] || '';
    const nextMName = avail[currentUserLbMonthIndex - 1] || '';

    if (prevLabel) prevLabel.innerText = toPersianMonthName(prevMName) || '---';
    if (nextLabel) nextLabel.innerText = toPersianMonthName(nextMName) || '---';

    if (prevBtn) {
      const hasPrev = Boolean(prevMName);
      prevBtn.disabled = !hasPrev;
      prevBtn.classList.toggle('opacity-40', !hasPrev);
      prevBtn.classList.toggle('cursor-not-allowed', !hasPrev);
    }
    if (nextBtn) {
      const hasNext = Boolean(nextMName);
      nextBtn.disabled = !hasNext;
      nextBtn.classList.toggle('opacity-40', !hasNext);
      nextBtn.classList.toggle('cursor-not-allowed', !hasNext);
    }
  }

  const noticeEl = $('userLeaderboardNotice');
  const noticeTextEl = $('userLbNoticeText');
  const noticeIconEl = $('userLbNoticeIcon');

  if (noticeTextEl) {
    let periodLabel = periodData.period_label || '7 روز اخیر';
    if (period === 'daily') {
      periodLabel = periodData.period_label || 'روزانه (امروز - 00:00 تا 23:59)';
    } else if (period === 'nightly') {
      periodLabel = periodData.period_label || 'شبانه (روز قبل - 00:00 تا 23:59)';
    } else if (period === 'weekly') {
      periodLabel = '7 روز اخیر';
    } else if (period === 'monthly_30d') {
      periodLabel = '30 روز اخیر';
    } else if (period === 'monthly') {
      const mPersian = toPersianMonthName(activeMonthName) || (periodData.month_name ? toPersianMonthName(periodData.month_name) : 'ماهانه');
      const wLabel = currentUserLbWeek === 'all' ? '' : ` - ${currentUserLbWeek.replace('week', 'هفته ')}`;
      periodLabel = `ماه ${mPersian}${wLabel}`;
    }

    const isPeriodEmpty = top20.length === 0 || top20.every(u => !u.used_gb || u.used_gb <= 0);
    const myTrafficHtml = fmtTraffic(myUsedGb, { html: true, persianDigits: false });

    if (isPeriodEmpty) {
      if (noticeIconEl) noticeIconEl.innerText = '⏳';
      noticeTextEl.innerHTML = `در این بازه هنوز داده‌ای از مصرف کاربران ثبت نشده است.`;
      if (noticeEl) {
        noticeEl.className = 'p-2.5 rounded-xl text-xs flex items-start gap-2 bg-slate-500/10 border border-slate-700/40 t-muted';
      }
    } else if (inTop20 && myRank && myUsedGb > 0) {
      if (noticeIconEl) noticeIconEl.innerText = '🎖️';
      noticeTextEl.innerHTML = `تبریک! شما با مصرف ${myTrafficHtml} در رتبه <b class="font-mono font-bold">${myRank}</b> از <b class="font-mono">20</b> کاربر برتر قرار دارید.`;
      if (noticeEl) {
        noticeEl.className = 'p-2.5 rounded-xl text-xs flex items-start gap-2 bg-emerald-500/10 border border-emerald-500/30 text-emerald-800 dark:text-emerald-300';
      }
    } else if (myRank && myRank > 20 && myUsedGb > 0) {
      if (noticeIconEl) noticeIconEl.innerText = '📊';
      const diffTrafficHtml = fmtTraffic(diffGb, { html: true, persianDigits: false });
      noticeTextEl.innerHTML = `شما با مصرف ${myTrafficHtml} در رتبه <b class="font-mono font-bold">${myRank}</b> قرار دارید. برای ورود به <b class="font-mono">20</b> کاربر برتر، به ${diffTrafficHtml} مصرف بیشتر نیاز دارید.`;
      if (noticeEl) {
        noticeEl.className = 'p-2.5 rounded-xl text-xs flex items-start gap-2 bg-slate-500/10 border border-slate-700/40 t-main';
      }
    } else if (myUsedGb > 0) {
      if (noticeIconEl) noticeIconEl.innerText = '📈';
      noticeTextEl.innerHTML = `مصرف شما برابر ${myTrafficHtml} است. با مصرف بیشتر به جمع <b class="font-mono">20</b> کاربر برتر بپیوندید!`;
      if (noticeEl) {
        noticeEl.className = 'p-2.5 rounded-xl text-xs flex items-start gap-2 bg-slate-500/10 border border-slate-700/40 t-main';
      }
    } else {
      if (noticeIconEl) noticeIconEl.innerText = 'ℹ️';
      noticeTextEl.innerHTML = `در این بازه هنوز مصرفی برای شما ثبت نشده است.`;
      if (noticeEl) {
        noticeEl.className = 'p-2.5 rounded-xl text-xs flex items-start gap-2 bg-slate-500/10 border border-slate-700/40 t-muted';
      }
    }
  }

  const canvas = $('userLeaderboardChartCanvas');
  const emptyState = $('userLeaderboardEmptyState');
  if (!canvas) return;

  if (top20.length === 0 || top20.every(u => !u.used_gb || u.used_gb <= 0)) {
    if (userLeaderboardChartInstance) {
      userLeaderboardChartInstance.destroy();
      userLeaderboardChartInstance = null;
    }
    canvas.classList.add('hidden');
    if (emptyState) emptyState.classList.remove('hidden');
    return;
  }

  canvas.classList.remove('hidden');
  if (emptyState) emptyState.classList.add('hidden');

  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const labels = top20.map(u => u.username);
  const values = top20.map(u => u.used_gb);

  const bgColors = top20.map((u, i) => {
    if (u.is_me) return 'rgba(16, 185, 129, 0.85)';
    if (i === 0) return 'rgba(245, 158, 11, 0.85)';
    return 'rgba(99, 102, 241, 0.45)';
  });
  const borderColors = top20.map((u, i) => {
    if (u.is_me) return '#10b981';
    if (i === 0) return '#fbbf24';
    return '#818cf8';
  });
  const borderWidths = top20.map((u, i) => (u.is_me || i === 0 ? 2 : 1));

  if (userLeaderboardChartInstance) {
    userLeaderboardChartInstance.data.labels = labels;
    userLeaderboardChartInstance.data.datasets[0].data = values;
    userLeaderboardChartInstance.data.datasets[0].backgroundColor = bgColors;
    userLeaderboardChartInstance.data.datasets[0].borderColor = borderColors;
    userLeaderboardChartInstance.data.datasets[0].borderWidth = borderWidths;
    userLeaderboardChartInstance.update();
    return;
  }

  const isLight = document.documentElement.classList.contains('theme-light');
  const gridColor = isLight ? 'rgba(0, 0, 0, 0.05)' : 'rgba(255, 255, 255, 0.05)';
  const tickColor = isLight ? '#475569' : '#94a3b8';

  userLeaderboardChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'مصرف ترافیک',
        data: values,
        backgroundColor: bgColors,
        borderColor: borderColors,
        borderWidth: borderWidths,
        borderRadius: 4,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          rtl: true,
          titleFont: { family: 'Vazirmatn' },
          bodyFont: { family: 'Vazirmatn' },
          callbacks: {
            label: (c) => {
              const u = top20[c.dataIndex] || {};
              const trafVal = typeof fmtTraffic === 'function' ? fmtTraffic(c.raw, { html: false, isolate: true, persianDigits: false }) : c.raw;
              const rankNum = c.dataIndex + 1;
              const prefix = u.is_me ? '👤 شما: ' : (c.dataIndex === 0 ? '👑 رتبه 1: ' : `رتبه ${rankNum}: `);
              return `${prefix}${trafVal}`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            color: tickColor,
            font: { family: 'Vazirmatn', size: 9 },
            maxRotation: 45,
            minRotation: 0,
          },
        },
        y: {
          grid: { color: gridColor },
          ticks: {
            color: tickColor,
            font: { family: 'Vazirmatn', size: 9 },
            callback: (v) => typeof fmtTraffic === 'function' ? fmtTraffic(v, { html: false, isolate: true, persianDigits: false }) : v,
          },
        },
      },
    },
  });
  if (!window.chartInstances) window.chartInstances = {};
  window.chartInstances['userLeaderboardChartCanvas'] = userLeaderboardChartInstance;
}
window.renderUserLeaderboard = renderUserLeaderboard;

function copyActiveCoupon() {
  const coupons = window.lastUserData?.won_coupons || [];
  if (coupons.length === 0) {
    if (typeof showToast === 'function') {
      showToast('کد تخفیف فعالی برای کپی وجود ندارد', 'info');
    }
    return;
  }
  const code = coupons[0]?.code;
  if (code) {
    if (typeof copyToClipboard === 'function') {
      copyToClipboard(code, `کد تخفیف ${code} کپی شد!`);
    } else if (navigator.clipboard) {
      navigator.clipboard.writeText(code);
      if (typeof showToast === 'function') showToast(`کد تخفیف ${code} کپی شد!`, 'success');
    }
    const couponInput = $('couponInput');
    if (couponInput) couponInput.value = code;
  }
}
window.copyActiveCoupon = copyActiveCoupon;

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
          if (parsed.data?.wheel_status && typeof parsed.data.wheel_status.next_spin_seconds === 'number') {
            const elapsedSec = age / 1000;
            const adjustedRemaining = Math.max(0, Math.round(parsed.data.wheel_status.next_spin_seconds - elapsedSec));
            parsed.data.wheel_status.next_spin_seconds = adjustedRemaining;
            if (adjustedRemaining <= 0) {
              parsed.data.wheel_status.can_spin = true;
            }
          }
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

function openSupportModal() {
  const btn = document.getElementById('openSupportBtn');
  if (btn) {
    btn.click();
  } else if (typeof openModal === 'function') {
    openModal('supportChatModal');
  }
}
window.openSupportModal = openSupportModal;

function openSupportContact() {
  const link = window.lastUserData?.support_link || window.lastUserData?.data?.support_link;
  if (link) {
    if (window.Telegram?.WebApp?.openTelegramLink && (link.includes('t.me') || link.startsWith('tg://'))) {
      window.Telegram.WebApp.openTelegramLink(link);
    } else if (window.Telegram?.WebApp?.openLink) {
      window.Telegram.WebApp.openLink(link);
    } else {
      window.open(link, '_blank');
    }
  } else if (typeof window.openSupportModal === 'function') {
    window.openSupportModal();
  } else {
    openSupportModal();
  }
}
window.openSupportContact = openSupportContact;

// ========================================================
// GIFT TO FRIENDS SYSTEM (ارسال هدیه به دوستان)
// ========================================================
let currentGiftType = 'BALANCE';
let currentGiftDelivery = 'DIRECT';

function openGiftModal() {
  const modal = $('giftModal');
  if (!modal) return;
  modal.classList.remove('hidden');
  switchGiftModalTab('new');
  setGiftType('BALANCE');
  setGiftDeliveryType('DIRECT');
  populateGiftServices();
  updateGiftCostDisplay();
  const bal = window.lastUserData?.user?.wallet_balance || 0;
  const currBalEl = $('giftCurrentBalanceDisplay');
  if (currBalEl) currBalEl.innerText = Number(bal).toLocaleString('en-US');
  $('giftCreatedSuccessBox')?.classList.add('hidden');
}

function closeGiftModal() {
  $('giftModal')?.classList.add('hidden');
}

function switchGiftModalTab(tab) {
  $('giftNewView')?.classList.toggle('hidden', tab !== 'new');
  $('giftHistoryView')?.classList.toggle('hidden', tab !== 'history');

  const activeClass = 'flex-1 py-2 px-3 rounded-xl font-bold transition flex items-center justify-center gap-1.5 text-xs bg-pink-600 text-white shadow-sm border-0';
  const inactiveClass = 'flex-1 py-2 px-3 rounded-xl font-medium transition flex items-center justify-center gap-1.5 text-xs t-muted hover:t-main bg-transparent border-0';

  const btnNew = $('giftTabBtn-new');
  const btnHistory = $('giftTabBtn-history');

  if (btnNew) {
    btnNew.className = tab === 'new' ? activeClass : inactiveClass;
    btnNew.setAttribute('aria-selected', tab === 'new' ? 'true' : 'false');
  }
  if (btnHistory) {
    btnHistory.className = tab === 'history' ? activeClass : inactiveClass;
    btnHistory.setAttribute('aria-selected', tab === 'history' ? 'true' : 'false');
  }

  if (tab === 'history') {
    loadGiftsHistory();
  }
}

let _giftSelectedService = null;

function openGiftServiceSelectModal() {
  const modal = $('giftServiceSelectModal');
  if (!modal) return;
  modal.classList.remove('hidden');
  renderGiftServiceSelectModalList();
}
window.openGiftServiceSelectModal = openGiftServiceSelectModal;

function closeGiftServiceSelectModal() {
  $('giftServiceSelectModal')?.classList.add('hidden');
}
window.closeGiftServiceSelectModal = closeGiftServiceSelectModal;

function renderGiftServiceSelectModalList() {
  const container = $('giftServiceSelectModalList');
  if (!container) return;
  const plans = window.lastUserData?.plans || [];
  if (!plans.length) {
    container.innerHTML = '<div class="p-4 rounded-xl card-inset text-center text-xs t-muted">هیچ بسته فعالی یافت نشد.</div>';
    return;
  }

  container.innerHTML = plans.map(p => {
    const isSelected = _giftSelectedService && _giftSelectedService.id === p.id;
    const priceStr = Number(p.price || 0).toLocaleString('en-US');
    const durStr = p.duration_days > 0 ? `${p.duration_days} روز` : 'نامحدود';
    const trafStr = p.traffic_gb > 0 ? fmtTraffic(p.traffic_gb, { html: false }) : 'نامحدود';

    return `
      <div onclick="window.selectGiftService(${p.id})" class="cursor-pointer card-inset p-3 rounded-2xl border ${isSelected ? 'border-pink-500 bg-pink-500/10' : 'border-card-border hover:border-pink-500/50'} flex items-center justify-between transition">
        <div class="space-y-1 min-w-0">
          <b class="text-xs t-main block truncate">${formatPlanTitle(p.name)}</b>
          <div class="flex items-center gap-2 text-[11px] t-muted">
            <span>📊 <b dir="ltr" class="font-sans num-bidi t-main">${trafStr}</b></span>
            <span>📅 <b class="t-main">${durStr}</b></span>
          </div>
        </div>
        <div class="text-left font-sans num-bidi shrink-0 pl-1">
          <span class="text-xs font-black text-pink-600 dark:t-pink block">${priceStr}</span>
          <span class="text-[11px] t-muted font-sans block">تومان</span>
        </div>
      </div>
    `;
  }).join('');
}

function selectGiftService(serviceId) {
  const plans = window.lastUserData?.plans || [];
  const chosen = plans.find(p => p.id === serviceId);
  if (!chosen) return;
  _giftSelectedService = chosen;

  const titleEl = $('giftSelectedServiceTitle');
  const specsEl = $('giftSelectedServiceSpecs');
  const hiddenInp = $('giftServiceSelect');

  if (titleEl) titleEl.innerHTML = formatPlanTitle(chosen.name);
  if (specsEl) {
    const durStr = chosen.duration_days > 0 ? `${chosen.duration_days} روز` : 'نامحدود';
    const trafStr = chosen.traffic_gb > 0 ? fmtTraffic(chosen.traffic_gb, { html: false }) : 'نامحدود';
    specsEl.innerText = `${trafStr} | ${durStr} (${Number(chosen.price).toLocaleString('en-US')} تومان)`;
  }
  if (hiddenInp) hiddenInp.value = chosen.id;

  updateGiftCostDisplay();
  closeGiftServiceSelectModal();
  hapticFeedback('selection');
}
window.selectGiftService = selectGiftService;

function setGiftType(type) {
  currentGiftType = type;
  const isBal = type === 'BALANCE';
  $('giftBalanceSection')?.classList.toggle('hidden', !isBal);
  $('giftServiceSection')?.classList.toggle('hidden', isBal);

  const activeBtnClass = 'py-2.5 px-3 rounded-xl bg-pink-600 text-white font-bold text-xs flex items-center justify-center gap-1.5 transition shadow-sm border border-pink-500/40';
  const inactiveBtnClass = 'py-2.5 px-3 rounded-xl card-inset border border-card-border t-muted hover:t-main font-medium text-xs flex items-center justify-center gap-1.5 transition';

  const btnBal = $('giftTypeBtn-balance');
  const btnSvc = $('giftTypeBtn-service');
  if (btnBal) {
    btnBal.className = isBal ? activeBtnClass : inactiveBtnClass;
    btnBal.setAttribute('aria-selected', isBal ? 'true' : 'false');
  }
  if (btnSvc) {
    btnSvc.className = !isBal ? activeBtnClass : inactiveBtnClass;
    btnSvc.setAttribute('aria-selected', !isBal ? 'true' : 'false');
  }
  updateGiftCostDisplay();
}

function setGiftDeliveryType(type) {
  currentGiftDelivery = type;
  const isDirect = type === 'DIRECT';
  $('giftReceiverSection')?.classList.toggle('hidden', !isDirect);

  const activeBtnClass = 'py-2.5 px-3 rounded-xl bg-pink-600 text-white font-bold text-xs flex items-center justify-center gap-1.5 transition shadow-sm border border-pink-500/40';
  const inactiveBtnClass = 'py-2.5 px-3 rounded-xl card-inset border border-card-border t-muted hover:t-main font-medium text-xs flex items-center justify-center gap-1.5 transition';

  const btnDir = $('giftDeliveryBtn-direct');
  const btnLink = $('giftDeliveryBtn-link');
  if (btnDir) {
    btnDir.className = isDirect ? activeBtnClass : inactiveBtnClass;
    btnDir.setAttribute('aria-selected', isDirect ? 'true' : 'false');
  }
  if (btnLink) {
    btnLink.className = !isDirect ? activeBtnClass : inactiveBtnClass;
    btnLink.setAttribute('aria-selected', !isDirect ? 'true' : 'false');
  }
}

function setGiftBalancePreset(amount) {
  const inp = $('giftBalanceAmount');
  if (inp) {
    inp.value = amount;
    updateGiftCostDisplay();
  }
}

function populateGiftServices() {
  const plans = window.lastUserData?.plans || [];
  if (plans.length > 0 && !_giftSelectedService) {
    selectGiftService(plans[0].id);
  }
}

function updateGiftCostDisplay() {
  let cost = 0;
  if (currentGiftType === 'BALANCE') {
    cost = Math.max(0, Number($('giftBalanceAmount')?.value || 0));
  } else {
    cost = Math.max(0, Number(_giftSelectedService?.price || 0));
  }
  const costEl = $('giftCostDisplay');
  if (costEl) costEl.innerText = Number(cost).toLocaleString('en-US');
}

async function submitCreateGift() {
  const btn = $('submitCreateGiftBtn');
  if (btn) btn.disabled = true;

  try {
    const payload = {
      delivery_type: currentGiftDelivery,
      gift_type: currentGiftType,
      message: $('giftMessageInput')?.value.trim() || ''
    };

    if (currentGiftType === 'BALANCE') {
      const amt = Number($('giftBalanceAmount')?.value || 0);
      if (!amt || amt < 10000) {
        showToast('⚠️ حداقل مبلغ هدیه اعتبار ۱۰,۰۰۰ تومان می‌باشد.');
        if (btn) btn.disabled = false;
        return;
      }
      payload.amount = amt;
    } else {
      const svcId = _giftSelectedService?.id || $('giftServiceSelect')?.value;
      if (!svcId) {
        showToast('⚠️ لطفاً بسته مورد نظر را انتخاب فرمایید.');
        if (btn) btn.disabled = false;
        return;
      }
      payload.service_id = Number(svcId);
    }

    if (currentGiftDelivery === 'DIRECT') {
      let rec = $('giftReceiverInput')?.value.trim() || '';
      if (!rec) {
        showToast('⚠️ لطفاً آیدی یا شناسه عددی تلگرام گیرنده را وارد فرمایید.');
        if (btn) btn.disabled = false;
        return;
      }
      rec = rec.replace(/^@+/, '');
      payload.receiver = rec;
      payload.receiver_target = rec;
    }

    const res = await window.api.createGift(payload);
    if (!res || !res.ok) {
      const errMsg = res?.message || res?.data?.message || 'خطا در ثبت هدیه';
      showToast(`❌ ${errMsg}`);
      hapticFeedback('error');
      return;
    }

    hapticFeedback('success');
    showToast('🎉 کارت هدیه با موفقیت صادر شد!');

    const d = res.data || res || {};
    const successBox = $('giftCreatedSuccessBox');
    if (successBox) {
      successBox.classList.remove('hidden');
      const codeInput = $('giftCreatedCodeInput');
      if (codeInput) codeInput.value = d.code || '';
      const linkInput = $('giftCreatedLinkInput');
      if (linkInput) linkInput.value = d.share_url || d.claim_url || (d.code ? `https://t.me/${window.botUsername || ''}?start=gift_${d.code}` : '');
      const notice = $('giftCreatedNotice');
      if (notice) {
        if (currentGiftDelivery === 'DIRECT') {
          notice.innerText = 'هدیه به دوستتان تحویل شد و پیام تبریک به همراه دکمه فعال‌سازی در تلگرام برای ایشان ارسال گردید.';
        } else {
          notice.innerText = 'لینک بالا را کپی کرده و برای دوستتان ارسال نمایید تا با یک کلیک هدیه را دریافت کند.';
        }
      }
    }

    if (d.cost) {
      const balEl = $('giftCurrentBalanceDisplay');
      if (balEl) {
        const cur = Number(window.lastUserData?.user?.wallet_balance || 0);
        balEl.innerText = Number(Math.max(0, cur - d.cost)).toLocaleString('en-US');
      }
    }

    try {
      if (typeof window.syncUserDataWithApi === 'function') {
        window.syncUserDataWithApi();
      }
    } catch (e) {
      console.warn('Error syncing after gift create:', e);
    }
  } catch (err) {
    console.error('submitCreateGift error:', err);
    showToast('❌ خطا در ارتباط با سرور.');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function copyGiftShareLink() {
  const linkInp = $('giftCreatedLinkInput');
  if (!linkInp || !linkInp.value) return;
  copyToClipboard(linkInp.value);
  showToast('📋 لینک هدیه در کلیپ‌بورد کپی شد!');
  hapticFeedback('selection');
}

function copyGiftCode() {
  const codeInp = $('giftCreatedCodeInput');
  if (!codeInp || !codeInp.value) return;
  copyToClipboard(codeInp.value);
  showToast('📋 کد اختصاصی هدیه کپی شد!');
  hapticFeedback('selection');
}

async function submitClaimVoucher() {
  const inp = $('claimVoucherInput');
  const code = inp?.value.trim().toUpperCase();
  if (!code) {
    showToast('⚠️ لطفاً کد هدیه را وارد فرمایید.');
    return;
  }

  try {
    const res = await window.api.claimGift(code);
    if (!res || !res.ok) {
      showToast(`❌ ${res?.message || 'کد هدیه نامعتبر است یا قبلاً استفاده شده.'}`);
      hapticFeedback('error');
      return;
    }
    hapticFeedback('success');
    const giftType = res.gift_type || res.data?.gift_type;
    const amount = res.amount || res.data?.amount;
    const serviceName = res.service_name || res.data?.service_name;
    const giftTitle = giftType === 'BALANCE'
      ? `${Number(amount || 0).toLocaleString('en-US')} تومان اعتبار کیف پول`
      : `اشتراک «${serviceName || 'سرویس'}»`;
    showToast(`🎉 تبریک! هدیه ${giftTitle} دریافت و به حسابتان اضافه شد!`);
    inp.value = '';
    try {
      if (typeof window.syncUserDataWithApi === 'function') window.syncUserDataWithApi();
    } catch (e) {
      console.warn('Error syncing after claim voucher:', e);
    }
    loadGiftsHistory();
  } catch (err) {
    showToast('❌ خطا در دریافت کد هدیه.');
  }
}

async function loadGiftsHistory() {
  const container = $('giftsHistoryContainer');
  if (!container) return;
  container.innerHTML = '<div class="p-3 rounded-xl card-inset text-center text-xs t-muted">در حال دریافت تاریخچه...</div>';

  try {
    const res = await window.api.getGiftsHistory();
    const giftsObj = res?.gifts || res?.data?.gifts;
    const sent = giftsObj?.sent || res?.sent_gifts || res?.data?.sent_gifts || (Array.isArray(giftsObj) ? giftsObj : []);
    if (!res || !res.ok || !sent.length) {
      container.innerHTML = '<div class="p-3 rounded-xl card-inset text-center text-xs t-muted">هنوز هدیه‌ای ارسال نکرده‌اید.</div>';
      return;
    }
    container.innerHTML = sent.map(g => {
      const isClaimed = g.is_claimed;
      const statusBadge = isClaimed
        ? '<span class="text-emerald-500 font-bold text-[11px] bg-emerald-500/10 px-2 py-0.5 rounded-full">✅ دریافت شده</span>'
        : '<span class="text-amber-500 font-bold text-[11px] bg-amber-500/10 px-2 py-0.5 rounded-full">⏳ در انتظار دریافت</span>';
      const desc = g.gift_type === 'BALANCE'
        ? `${Number(g.amount).toLocaleString('en-US')} تومان شارژ کیف پول`
        : `اشتراک ${g.service_name || 'سرویس'}`;
      const rec = g.receiver_username
        ? `<span dir="ltr">@${escapeHtml(g.receiver_username)}</span>`
        : (g.receiver_telegram_id ? `<span dir="ltr">${escapeHtml(String(g.receiver_telegram_id))}</span>` : 'از طریق لینک هدیه');
      const dateStr = g.created_at_jalali || (g.created_at && window.formatDateToJalali ? window.formatDateToJalali(g.created_at) : '');
      const shareUrl = g.share_url || `https://t.me?start=gift_${g.code}`;
      return `
        <div class="card-inset p-2.5 rounded-xl space-y-1.5 text-xs">
          <div class="flex justify-between items-center">
            <b class="t-main text-[11px]">${desc}</b>
            ${statusBadge}
          </div>
          <div class="flex justify-between items-center text-[11px] t-muted">
            <span>گیرنده: <code class="font-sans num-bidi">${rec}</code></span>
            <span dir="ltr" class="font-sans num-bidi">${toEnglishDigits(dateStr)}</span>
          </div>
          <div class="flex items-center justify-between text-[11px] border-t border-card-border pt-1">
            ${!isClaimed ? `<button type="button" onclick="copyToClipboard('${shareUrl}'); showToast('📋 لینک کپی شد!');" class="text-[11px] t-pink hover:text-pink-300 font-bold flex items-center gap-1 active:scale-95 transition" title="کپی لینک"><span>🔗</span> کپی لینک</button>` : '<span></span>'}
            <div class="flex items-center gap-1.5" dir="ltr">
              <button type="button" onclick="copyToClipboard('${g.code}'); showToast('📋 کد کپی شد!');" class="p-1 rounded-md t-accent hover:text-cyan-300 hover:bg-cyan-500/10 active:scale-95 transition" title="کپی کد">📋</button>
              <span class="font-sans num-bidi t-muted text-[11px] select-all">${g.code}</span>
            </div>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    container.innerHTML = '<div class="p-3 rounded-xl card-inset text-center text-xs t-muted">خطا در بارگذاری تاریخچه.</div>';
  }
}

window.openGiftModal = openGiftModal;
window.closeGiftModal = closeGiftModal;
window.switchGiftModalTab = switchGiftModalTab;
window.setGiftType = setGiftType;
window.setGiftDeliveryType = setGiftDeliveryType;
window.setGiftBalancePreset = setGiftBalancePreset;
window.updateGiftCostDisplay = updateGiftCostDisplay;
window.submitCreateGift = submitCreateGift;
window.copyGiftShareLink = copyGiftShareLink;
window.copyGiftCode = copyGiftCode;
window.submitClaimVoucher = submitClaimVoucher;
window.loadGiftsHistory = loadGiftsHistory;
window.populateGiftServices = populateGiftServices;

// ========================================================
// DIGITAL INVOICE & OFFICIAL RECEIPT CONTROLLERS
// ========================================================
let currentInvoiceData = null;

const invoiceClientCache = new Map();

function renderInvoiceModalFields(inv, orderId) {
  currentInvoiceData = inv;
  $('invNumberDisplay').innerText = inv.invoice_number || `INV-${orderId}`;
  $('invDateDisplay').innerText = `${inv.date_jalali} - ${inv.time_jalali}`;
  $('invSellerName').innerText = inv.seller?.name || 'سرویس ابری رمنا';
  if ($('invSellerDefaultIcon')) $('invSellerDefaultIcon').classList.remove('hidden');
  const bName = inv.buyer?.name || 'کاربر گرامی';
  const bId = inv.buyer?.telegram_id || '';
  if ($('invBuyerName')) $('invBuyerName').innerText = bName;
  if ($('invBuyerId')) {
    $('invBuyerId').innerText = bId ? String(bId) : '';
    $('invBuyerId').className = bId ? 'text-[11px] text-slate-400 font-sans num-bidi block select-all text-left' : 'hidden';
  }

  const rawItemTitle = (inv.item?.title || 'بسته اشتراک').trim();
  const emojiRegex = /([\uD800-\uDBFF][\uDC00-\uDFFF]|[\u2600-\u27BF]|\p{Extended_Pictographic}|\p{Emoji_Presentation})/gu;
  const emojiMatches = rawItemTitle.match(emojiRegex);
  let cleanItemTitle = rawItemTitle.replace(emojiRegex, '').trim() || rawItemTitle;
  cleanItemTitle = cleanItemTitle.replace(/\s*\([^)]*(?:GB|روز|day)[^)]*\)/gi, '').trim();
  let itemIcon = (emojiMatches && emojiMatches[0]) ? emojiMatches[0] : '📦';
  if (!emojiMatches || !emojiMatches.length) {
    const lowerTitle = rawItemTitle.toLowerCase();
    if (lowerTitle.includes('طلایی') || lowerTitle.includes('gold')) itemIcon = '🥇';
    else if (lowerTitle.includes('نقره') || lowerTitle.includes('silver')) itemIcon = '🥈';
    else if (lowerTitle.includes('برنز') || lowerTitle.includes('bronze')) itemIcon = '🥉';
    else if (lowerTitle.includes('الماس') || lowerTitle.includes('diamond')) itemIcon = '💎';
    else if (lowerTitle.includes('ویژه') || lowerTitle.includes('vip')) itemIcon = '👑';
  }

  $('invItemTitle').innerText = cleanItemTitle;
  if ($('invItemIcon')) {
    $('invItemIcon').innerText = itemIcon;
  }
  $('invItemSpecs').innerText = `${inv.item?.traffic_text || ''} | ${inv.item?.duration_text || ''}`;
  $('invItemAmount').innerText = Number(inv.payment?.amount_toman || 0).toLocaleString('en-US');

  $('invFinalAmountToman').innerText = Number(inv.payment?.amount_toman || 0).toLocaleString('en-US');
  $('invFinalAmountRial').innerHTML = `(<span class="num-bidi font-sans">${Number((inv.payment?.amount_toman || 0) * 10).toLocaleString('en-US')}</span> ریال)`;
  $('invTrackingCode').innerText = inv.payment?.tracking_code || `TRX-${orderId}`;

  const statusEl = $('invPaymentStatus');
  if (statusEl) {
    let statusText = inv.payment?.status || 'پرداخت شده';
    if (statusText === 'پرداخت شده و فعال') statusText = 'پرداخت شده';
    let icon = '✅';
    let colorClass = 'text-emerald-500';
    if (statusText.includes('ناموفق') || statusText.includes('لغو')) {
      icon = '❌';
      colorClass = 'text-rose-500';
    } else if (statusText.includes('انتظار')) {
      icon = '⏳';
      colorClass = 'text-amber-500';
    } else if (statusText.includes('مسترد')) {
      icon = '↩️';
      colorClass = 't-purple';
    }
    statusEl.className = `flex items-center gap-1 font-bold ${colorClass}`;
    statusEl.innerHTML = `<span>${icon}</span> <span>${statusText}</span>`;
  }

  const dedStatusEl = $('invWalletDeductionStatus');
  if (dedStatusEl) {
    const note = inv.payment?.deduction_note || (inv.payment?.is_paid ? 'کسر شده از موجودی کیف پول' : 'هیچ هزینه‌ای از کیف پول شما کسر نشده است');
    const isPaid = inv.payment?.is_paid;
    dedStatusEl.innerText = note;
    dedStatusEl.className = `text-xs font-semibold ${isPaid ? 'text-emerald-500' : 'text-slate-400'}`;
  }
}

async function openInvoiceModal(orderId) {
  if (!orderId) return;
  const modal = $('invoiceModal');
  if (!modal) return;

  // SWR: Instant render if cached in client memory (0ms perceived wait)
  if (invoiceClientCache.has(orderId)) {
    renderInvoiceModalFields(invoiceClientCache.get(orderId), orderId);
    modal.classList.remove('hidden');
    // Silently revalidate in background
    window.api.getInvoice(orderId).then(res => {
      if (res && res.ok && res.data) {
        invoiceClientCache.set(orderId, res.data);
        renderInvoiceModalFields(res.data, orderId);
      }
    }).catch(() => {});
    return;
  }

  modal.classList.remove('hidden');
  $('invNumberDisplay').innerText = 'در حال استخراج...';
  $('invDateDisplay').innerText = '--';
  $('invSellerName').innerText = '...';
  if ($('invBuyerName')) $('invBuyerName').innerText = '...';
  if ($('invBuyerId')) $('invBuyerId').innerText = '--';
  $('invItemTitle').innerText = 'در حال دریافت اطلاعات فاکتور...';
  $('invItemSpecs').innerText = '';
  $('invItemAmount').innerText = '--';
  $('invFinalAmountToman').innerText = '--';
  $('invFinalAmountRial').innerText = '';
  $('invTrackingCode').innerText = 'TRX-........';

  try {
    const res = await window.api.getInvoice(orderId);
    if (!res || !res.ok || !res.data) {
      showToast(`❌ ${res?.message || 'فاکتور یافت نشد.'}`);
      closeInvoiceModal();
      return;
    }

    invoiceClientCache.set(orderId, res.data);
    renderInvoiceModalFields(res.data, orderId);
  } catch (err) {
    console.warn('Failed loading invoice:', err);
    showToast('❌ خطا در بارگذاری اطلاعات فاکتور.');
    closeInvoiceModal();
  }
}

function closeInvoiceModal() {
  $('invoiceModal')?.classList.add('hidden');
}

async function sendCurrentInvoiceTelegram() {
  if (!currentInvoiceData || !currentInvoiceData.order_id) {
    showToast('⚠️ اطلاعات فاکتور در دسترس نیست.');
    return;
  }
  const btn = $('sendInvoiceTelegramBtn');
  if (btn) btn.disabled = true;

  try {
    const res = await window.api.sendInvoiceToTelegram(currentInvoiceData.order_id);
    if (res && res.ok) {
      hapticFeedback('success');
      showToast('🎉 فاکتور رسمی به پیوی تلگرام شما ارسال شد!');
    } else {
      showToast(`❌ ${res?.message || 'خطا در ارسال پیام به تلگرام'}`);
    }
  } catch (err) {
    showToast('❌ خطا در ارتباط با سرور.');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function printCurrentInvoice() {
  if (!currentInvoiceData) return;
  hapticFeedback('selection');

  if (window.Telegram?.WebApp?.initData) {
    sendCurrentInvoiceTelegram();
    return;
  }

  try {
    const canvas = document.createElement('canvas');
    canvas.width = 600;
    canvas.height = 760;
    const ctx = canvas.getContext('2d');
    if (ctx) {
      // Background gradient
      const grad = ctx.createLinearGradient(0, 0, 0, 760);
      grad.addColorStop(0, '#0f172a');
      grad.addColorStop(1, '#020617');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, 600, 760);

      // Card border
      ctx.strokeStyle = '#334155';
      ctx.lineWidth = 3;
      ctx.strokeRect(15, 15, 570, 730);

      // Header
      ctx.fillStyle = '#38bdf8';
      ctx.font = 'bold 24px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('رسید رسمی فاکتور خرید', 300, 65);

      // Invoice ID & Date
      const invNum = currentInvoiceData.invoice_number || `INV-${currentInvoiceData.order_id || '---'}`;
      const invDate = currentInvoiceData.date_jalali || '---';
      ctx.fillStyle = '#94a3b8';
      ctx.font = '14px monospace';
      ctx.fillText(`فاکتور: ${invNum}   |   تاریخ: ${invDate}`, 300, 100);

      // Separator line
      ctx.strokeStyle = '#1e293b';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(30, 120);
      ctx.lineTo(570, 120);
      ctx.stroke();

      // Buyer & Service info
      const buyerName = currentInvoiceData.buyer?.name || 'کاربر گرامی';
      const buyerTgId = currentInvoiceData.buyer?.telegram_id || '---';
      ctx.textAlign = 'right';
      ctx.font = 'bold 16px sans-serif';
      ctx.fillStyle = '#e2e8f0';
      ctx.fillText(`مشترک: ${buyerName}`, 550, 160);
      ctx.font = '13px monospace';
      ctx.fillStyle = '#64748b';
      ctx.fillText(`شناسه تلگرام: ${buyerTgId}`, 550, 190);

      // Item box
      ctx.fillStyle = '#1e293b';
      ctx.fillRect(30, 220, 540, 120);
      ctx.strokeStyle = '#334155';
      ctx.strokeRect(30, 220, 540, 120);

      const itemTitle = currentInvoiceData.item?.title || 'سرویس اشتراک';
      const trafficGb = currentInvoiceData.item?.traffic_gb || 0;
      const durationDays = currentInvoiceData.item?.duration_days || 0;
      ctx.fillStyle = '#38bdf8';
      ctx.font = 'bold 18px sans-serif';
      ctx.fillText(itemTitle, 540, 260);

      ctx.fillStyle = '#94a3b8';
      ctx.font = '14px sans-serif';
      ctx.fillText(`${trafficGb} گیگابایت   |   ${durationDays} روز اعتبار`, 540, 295);

      // Total Amount
      const finalAmount = currentInvoiceData.payment?.amount_toman || 0;
      ctx.fillStyle = '#10b981';
      ctx.font = 'bold 22px monospace';
      ctx.textAlign = 'left';
      ctx.fillText(`${Number(finalAmount).toLocaleString('en-US')} تومان`, 50, 280);

      // Status Box
      ctx.textAlign = 'center';
      ctx.fillStyle = '#064e3b';
      ctx.fillRect(30, 370, 540, 50);
      ctx.fillStyle = '#34d399';
      ctx.font = 'bold 16px sans-serif';
      ctx.fillText('✅ پرداخت موفق و فعال‌سازی سرویس انجام شد', 300, 402);

      // Tracking code
      const trackingCode = currentInvoiceData.payment?.tracking_code || `TRX-${currentInvoiceData.order_id || 'SUCCESS'}`;
      ctx.fillStyle = '#94a3b8';
      ctx.font = '13px monospace';
      ctx.fillText(`کد پیگیری تراکنش: ${trackingCode}`, 300, 460);

      // Footer branding
      ctx.fillStyle = '#475569';
      ctx.font = '12px sans-serif';
      ctx.fillText('صادر شده توسط سامانه هوشمند مدیریت سرویس', 300, 710);

      // Trigger download
      const link = document.createElement('a');
      link.download = `Invoice-${currentInvoiceData.order_id || 'receipt'}.png`;
      link.href = canvas.toDataURL('image/png');
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      showToast('📸 تصویر فاکتور رسمی ذخیره شد.');
      return;
    }
  } catch (err) {
    console.warn('Canvas export failed, falling back to print:', err);
  }

  try {
    window.print();
  } catch (e) {}
}

window.openInvoiceModal = openInvoiceModal;
window.closeInvoiceModal = closeInvoiceModal;
window.sendCurrentInvoiceTelegram = sendCurrentInvoiceTelegram;
window.printCurrentInvoice = printCurrentInvoice;

// VIP Loyalty Modal Handler
function openLoyaltyModal() {
  const modal = $('loyaltyModal');
  if (!modal) return;
  const loyalty = window.lastUserData?.loyalty;
  if (loyalty) {
    if ($('loyaltyModalCurrentIcon')) $('loyaltyModalCurrentIcon').innerText = loyalty.icon || '🥉';
    if ($('loyaltyModalCurrentName')) $('loyaltyModalCurrentName').innerText = loyalty.name || 'برنزی';
    if ($('loyaltyModalTotalSpent')) $('loyaltyModalTotalSpent').innerText = `${Number(loyalty.total_spent || 0).toLocaleString('en-US')} تومان`;
    if ($('loyaltyModalCurrentDiscount')) {
      const disc = toEnglishDigits(loyalty.discount_percent || 0);
      $('loyaltyModalCurrentDiscount').innerHTML = Number(disc) > 0 ? `<span class="font-sans font-bold num-bidi" dir="ltr">${disc}%</span> تخفیف` : 'بدون تخفیف';
      $('loyaltyModalCurrentDiscount').className = Number(disc) > 0 ? 'text-xs font-bold text-emerald-500' : 'text-xs font-medium t-muted';
    }
    if ($('loyaltyModalProgressText')) {
      const isMaxTier = Boolean(loyalty.is_max_tier || (loyalty.tier_id === 'diamond'));
      const nextTier = loyalty.next_tier || (loyalty.next_tier_name ? {
        name: loyalty.next_tier_name,
        remaining_amount: loyalty.amount_to_next,
        discount_percent: loyalty.next_tier_discount,
      } : null);

      if (!isMaxTier && nextTier && nextTier.name) {
        const needed = Number(nextTier.remaining_amount || loyalty.amount_to_next || 0).toLocaleString('en-US');
        const nextDisc = toEnglishDigits(nextTier.discount_percent ?? loyalty.next_tier_discount ?? 0);
        $('loyaltyModalProgressText').innerHTML = `با ${needed} تومان خرید دیگر، به سطح ${nextTier.name} ارتقا می‌یابید و از <span class="num-bidi font-sans font-bold" dir="ltr">${nextDisc}%</span> تخفیف بهره‌مند می‌شوید.`;
      } else if (isMaxTier) {
        $('loyaltyModalProgressText').innerText = 'تبریک! شما به بالاترین سطح باشگاه مشتریان (الماس) دست یافته‌اید.';
      } else {
        $('loyaltyModalProgressText').innerText = 'با خرید بسته‌های بیشتر، سطح شما در باشگاه مشتریان ارتقا یافته و تخفیف دریافت می‌کنید.';
      }
    }

    // Dynamic thresholds update if all_tiers is provided
    if (Array.isArray(loyalty.all_tiers)) {
      loyalty.all_tiers.forEach(t => {
        const spentEl = $(`loyaltyTierCard_${t.id}_spent`);
        const pctEl = $(`loyaltyTierCard_${t.id}_pct`);
        if (spentEl && t.min_spent !== undefined) {
          spentEl.innerText = `${Number(t.min_spent).toLocaleString('en-US')} تومان`;
        }
        if (pctEl && t.discount_percent !== undefined) {
          pctEl.innerHTML = `<span class="num-bidi font-sans font-bold" dir="ltr">${toEnglishDigits(t.discount_percent)}%</span>`;
        }
      });
    }

    // Highlight user's active tier card
    const activeTierId = (loyalty.tier_id || 'bronze').toLowerCase();
    ['bronze', 'silver', 'gold', 'platinum', 'ruby', 'emerald', 'diamond'].forEach(t => {
      const card = $(`loyaltyTierCard_${t}`);
      if (card) {
        if (t === activeTierId) {
          card.classList.add('ring-2', 'ring-cyan-500', 'bg-cyan-500/10');
          card.classList.remove('opacity-60');
        } else {
          card.classList.remove('ring-2', 'ring-cyan-500', 'bg-cyan-500/10');
          card.classList.add('opacity-75');
        }
      }
    });
  }
  hapticFeedback('selection');
  modal.classList.remove('hidden');
}

function closeLoyaltyModal() {
  $('loyaltyModal')?.classList.add('hidden');
}

window.openLoyaltyModal = openLoyaltyModal;
window.closeLoyaltyModal = closeLoyaltyModal;

function openKillAllSessionsModal() {
  const m = $('killAllSessionsModal');
  if (m) m.classList.remove('hidden');
  hapticFeedback('warning');
}

function closeKillAllSessionsModal() {
  const m = $('killAllSessionsModal');
  if (m) m.classList.add('hidden');
}

async function confirmKillAllSessions() {
  closeKillAllSessionsModal();
  try {
    const res = await window.api.revokeSub();
    if (res && res.ok) {
      showToast('✅ تمام نشست‌های فعال مسدود و لینک اشتراک امن جدید صادر شد.');
      syncUserDataWithApi();
    } else {
      showToast(`❌ ${res?.error || res?.message || 'خطا در قطع نشست‌ها.'}`);
    }
  } catch (err) {
    showToast('❌ خطا در برقراری ارتباط با سرور.');
  }
}
window.openKillAllSessionsModal = openKillAllSessionsModal;
window.closeKillAllSessionsModal = closeKillAllSessionsModal;
window.confirmKillAllSessions = confirmKillAllSessions;

let pendingKillSingleHwid = null;

function openKillSingleDeviceModal(hwid, model, ip) {
  pendingKillSingleHwid = hwid;
  if ($('killDeviceModalModel')) $('killDeviceModalModel').innerText = model || 'دستگاه متصل';
  if ($('killDeviceModalIp')) $('killDeviceModalIp').innerText = ip ? `IP: ${ip}` : 'IP: —';
  const m = $('killSingleDeviceModal');
  if (m) m.classList.remove('hidden');
  hapticFeedback('warning');
}

function closeKillSingleDeviceModal() {
  pendingKillSingleHwid = null;
  const m = $('killSingleDeviceModal');
  if (m) m.classList.add('hidden');
}

async function confirmKillSingleDevice() {
  const hwid = pendingKillSingleHwid;
  closeKillSingleDeviceModal();
  if (!hwid) return;
  try {
    const res = await window.api.killDevice(hwid);
    if (res && res.ok) {
      showToast('✅ دستگاه با موفقیت قطع شد.');
      syncUserDataWithApi();
    } else {
      showToast(`❌ ${res?.error || 'خطا در قطع دستگاه'}`);
    }
  } catch (e) {
    showToast('❌ خطا در برقراری ارتباط با سرور.');
  }
}

window.openKillSingleDeviceModal = openKillSingleDeviceModal;
window.closeKillSingleDeviceModal = closeKillSingleDeviceModal;
window.confirmKillSingleDevice = confirmKillSingleDevice;
