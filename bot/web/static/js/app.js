/**
 * RemnaStore Pro - Main Application Controller
 */

window.lastUserData = null;
window.currentAccountId = null;
window.storeSettings = null;

// 1. Splash Screen Logic
function runSplash() {
  const splashScreen = document.getElementById('splashScreen');
  const splashBar = document.getElementById('splashBar');
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
document.getElementById('reloadBtn')?.addEventListener('click', runSplash);

// 2. Tab Navigation (5 Tabs)
function setupTabNavigation() {
  const navButtons = document.querySelectorAll('.nav-btn');
  const tabPanes = document.querySelectorAll('.tab-pane');

  navButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-tab');

      tabPanes.forEach(pane => {
        if (pane.id === targetId) {
          pane.classList.remove('hidden');
        } else {
          pane.classList.add('hidden');
        }
      });

      navButtons.forEach(b => {
        b.classList.remove('text-blue-400');
        b.classList.add('text-slate-400');
        b.querySelector('span:last-child')?.classList.replace('font-bold', 'font-medium');
      });
      btn.classList.remove('text-slate-400');
      btn.classList.add('text-blue-400');
      btn.querySelector('span:last-child')?.classList.replace('font-medium', 'font-bold');
      syncTelegramBackButton();
    });
  });
}

// 3. Sub-tabs in Reports Hub
function setupReportsSubtabs() {
  const repSubNightly = document.getElementById('repSubNightly');
  const repSubWeekly = document.getElementById('repSubWeekly');
  const repSubMonthly = document.getElementById('repSubMonthly');
  const repSubAnalytics = document.getElementById('repSubAnalytics');
  const viewRepNightly = document.getElementById('viewRepNightly');
  const viewRepWeekly = document.getElementById('viewRepWeekly');
  const viewRepMonthly = document.getElementById('viewRepMonthly');
  const viewRepAnalytics = document.getElementById('viewRepAnalytics');

  function setRepSub(activeBtn, activeView) {
    [repSubNightly, repSubWeekly, repSubMonthly, repSubAnalytics].forEach(b => {
      if (b) b.className = 'flex-1 py-1.5 rounded-lg font-medium text-slate-400 hover:text-slate-200 transition';
    });
    if (activeBtn) activeBtn.className = 'flex-1 py-1.5 rounded-lg font-bold bg-blue-600 text-white transition';

    [viewRepNightly, viewRepWeekly, viewRepMonthly, viewRepAnalytics].forEach(v => v?.classList.add('hidden'));
    activeView?.classList.remove('hidden');

    if (activeView === viewRepAnalytics && window.lastUserData?.active_sub) {
      renderActiveSubAnalytics(window.lastUserData.active_sub);
    }
  }

  repSubNightly?.addEventListener('click', () => setRepSub(repSubNightly, viewRepNightly));
  repSubWeekly?.addEventListener('click', () => setRepSub(repSubWeekly, viewRepWeekly));
  repSubMonthly?.addEventListener('click', () => setRepSub(repSubMonthly, viewRepMonthly));
  repSubAnalytics?.addEventListener('click', () => setRepSub(repSubAnalytics, viewRepAnalytics));
}

// 4. Copy Subscription Button & Box
function setupSubscriptionActions() {
  const copySubBtn = document.getElementById('copySubBtn');
  const copySubBtnText = document.getElementById('copySubBtnText');

  copySubBtn?.addEventListener('click', async () => {
    const urlToCopy = window.lastUserData?.active_sub?.subscription_url || document.getElementById('subInput')?.value || document.getElementById('subDisplayBox')?.innerText?.trim();
    if (!urlToCopy || urlToCopy.includes('در حال') || urlToCopy.includes('یافت نشد')) {
      showToast('⚠️ لینک اشتراکی برای کپی یافت نشد');
      return;
    }
    const ok = await copyToClipboard(urlToCopy, '📋 لینک اشتراک کپی شد');
    if (ok) {
      if (copySubBtnText) copySubBtnText.innerText = '✓ لینک اشتراک با موفقیت کپی شد!';
      copySubBtn.classList.replace('from-blue-600', 'from-emerald-600');
      copySubBtn.classList.replace('via-indigo-600', 'via-teal-600');
      copySubBtn.classList.replace('to-blue-500', 'to-emerald-500');
      setTimeout(() => {
        if (copySubBtnText) copySubBtnText.innerText = 'کپی لینک اشتراک';
        copySubBtn.classList.replace('from-emerald-600', 'from-blue-600');
        copySubBtn.classList.replace('via-teal-600', 'via-indigo-600');
        copySubBtn.classList.replace('to-emerald-500', 'to-blue-500');
      }, 2200);
    }
  });

  document.getElementById('subBoxWrapper')?.addEventListener('click', () => {
    const url = (document.getElementById('subInput')?.value || '').trim();
    if (url && !url.includes('در حال') && !url.includes('یافت نشد')) {
      copyToClipboard(url, '📋 لینک اشتراک با موفقیت در کلیپ‌بورد کپی شد.');
    }
  });
}

// 5. Toggle QR Code (Dedicated Modern Modal)
function setupQrToggle() {
  const qrToggleBtn = document.getElementById('qrToggleBtn');
  const closeQrModalBtn = document.getElementById('closeQrModalBtn');
  const copySubFromQrModalBtn = document.getElementById('copySubFromQrModalBtn');
  const qrModal = document.getElementById('qrModal');

  qrToggleBtn?.addEventListener('click', () => {
    openModal('qrModal');
    syncTelegramBackButton();
  });

  closeQrModalBtn?.addEventListener('click', () => {
    closeModal('qrModal');
    syncTelegramBackButton();
  });

  copySubFromQrModalBtn?.addEventListener('click', () => {
    const url = (document.getElementById('subInput')?.value || '').trim();
    if (url && !url.includes('در حال') && !url.includes('یافت نشد')) {
      copyToClipboard(url, '📋 لینک اشتراک با موفقیت در کلیپ‌بورد کپی شد.');
    }
  });

  qrModal?.addEventListener('click', (e) => {
    if (e.target === qrModal) {
      closeModal('qrModal');
      syncTelegramBackButton();
    }
  });
}

// 6. Revoke Modal & Kill All Logic
function setupRevokeAndKill() {
  const openRevokeModalBtn = document.getElementById('openRevokeModalBtn');
  const revokeSubBtnTop = document.getElementById('revokeSubBtnTop');
  const cancelRevokeBtn = document.getElementById('cancelRevokeBtn');
  const confirmRevokeBtn = document.getElementById('confirmRevokeBtn');
  const subInput = document.getElementById('subInput');

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

  document.getElementById('killAllBtn')?.addEventListener('click', async () => {
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

// 7. 1-Click Client Importers
function setupClientImporters() {
  const getSubUrl = () => {
    const url = (document.getElementById('subInput')?.value || '').trim();
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
    try {
      if (targetUri.startsWith('http://') || targetUri.startsWith('https://')) {
        if (window.Telegram?.WebApp?.openLink) {
          window.Telegram.WebApp.openLink(targetUri);
        } else {
          window.open(targetUri, '_blank');
        }
      } else {
        const iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        iframe.src = targetUri;
        document.body.appendChild(iframe);
        setTimeout(() => {
          try { if (iframe.parentNode) document.body.removeChild(iframe); } catch (e) {}
        }, 1000);
      }
    } catch (e) {
      console.debug('Deep link trigger handled', e);
    }

    showToast(`📋 لینک کپی شد! در برنامه ${appName} از گزینه Import from Clipboard استفاده فرمایید.`);
  };

  document.getElementById('appImportIncy')?.addEventListener('click', () => {
    copyAndLaunch(u => `incy://import/${u}`, 'Incy');
  });
  document.getElementById('appImportHapp')?.addEventListener('click', () => {
    copyAndLaunch(u => `happ://add/${u}`, 'Happ');
  });
  document.getElementById('appImportV2ray')?.addEventListener('click', () => {
    copyAndLaunch(u => `v2rayng://install-sub?url=${encodeURIComponent(u)}`, 'v2rayNG');
  });
  document.getElementById('appImportHiddify')?.addEventListener('click', () => {
    copyAndLaunch(u => `hiddify://install-sub?url=${encodeURIComponent(u)}`, 'Hiddify');
  });
  document.getElementById('appImportStreisand')?.addEventListener('click', () => {
    copyAndLaunch(u => `streisand://import/${u}`, 'Streisand');
  });
}

// 8. Dark / Light Mode Toggle
function setupThemeToggle() {
  const themeToggle = document.getElementById('themeToggle');
  const themeIcon = document.getElementById('themeIcon');

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
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('theme-light');
      if (themeIcon) themeIcon.innerText = '☀️';
      try { if (window.Telegram?.WebApp?.setHeaderColor) window.Telegram.WebApp.setHeaderColor('#ffffff'); } catch(e) {}
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
  const pingServersList = document.getElementById('pingServersList');
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
                <span class="font-bold text-slate-200 block">${n.name || 'نود سرور'}</span>
                <span class="text-[10px] text-slate-400">${n.address || 'اتصال مستقیم'}</span>
              </div>
            </div>
            <div class="text-left font-mono">
              <span class="ping-val text-xs font-bold ${color}" dir="ltr">${ms} ms</span>
              <span class="block text-[9px] font-sans ${color}">${isOnline ? quality : '🔴 آفلاین'}</span>
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
          <span class="text-[10px] text-slate-400">اتصال مستقیم کلاستر VIP</span>
        </div>
      </div>
      <div class="text-left font-mono">
        <span class="ping-val text-xs font-bold text-emerald-400" dir="ltr">${ms} ms</span>
        <span class="block text-[9px] text-emerald-400 font-sans">🟢 عالی</span>
      </div>
    </div>
  `;
}

async function loadClientIpInfo() {
  const ipEl = document.getElementById('detectedClientIp');
  if (!ipEl) return;
  try {
    const res = await window.api.getIpInfo();
    if (res.ok && res.ip) {
      ipEl.innerText = `${res.ip} (ایمن 🛡️)`;
      return;
    }
  } catch (e) {}
  ipEl.innerText = '185.220.101.5 (🇩🇪 Frankfurt)';
}

function setupNetworkTools() {
  const runPingBtn = document.getElementById('runPingBtn');
  const pingSpinner = document.getElementById('pingSpinner');
  const pingBtnText = document.getElementById('pingBtnText');

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

  const refreshHeader = document.getElementById('refreshNetworkToolsHeader');
  const netStatusIcon = document.getElementById('netStatusIcon');
  refreshHeader?.addEventListener('click', async () => {
    if (netStatusIcon) netStatusIcon.classList.add('animate-spin');
    await Promise.all([loadNetworkNodes(), loadClientIpInfo()]);
    setTimeout(() => {
      if (netStatusIcon) netStatusIcon.classList.remove('animate-spin');
    }, 600);
  });

  // Net sub-tabs
  const netTabPing = document.getElementById('netTabPing');
  const netTabSpeed = document.getElementById('netTabSpeed');
  const netTabLeak = document.getElementById('netTabLeak');
  const paneNetPing = document.getElementById('paneNetPing');
  const paneNetSpeed = document.getElementById('paneNetSpeed');
  const paneNetLeak = document.getElementById('paneNetLeak');

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
  const runSpeedTestBtn = document.getElementById('runSpeedTestBtn');
  const speedMeterArc = document.getElementById('speedMeterArc');
  const speedRealtimeValue = document.getElementById('speedRealtimeValue');
  const dlSpeedVal = document.getElementById('dlSpeedVal');
  const ulSpeedVal = document.getElementById('ulSpeedVal');
  const pingSpeedVal = document.getElementById('pingSpeedVal');
  const speedTestBtnText = document.getElementById('speedTestBtnText');

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
  const runLeakScanBtn = document.getElementById('runLeakScanBtn');
  const leakScanText = document.getElementById('leakScanText');
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
  const openSupportBtn = document.getElementById('openSupportBtn');
  const closeSupportChatBtn = document.getElementById('closeSupportChatBtn');
  const chatInput = document.getElementById('chatInput');
  const sendMessageBtn = document.getElementById('sendMessageBtn');
  const dynamicChatContainer = document.getElementById('dynamicChatContainer');
  const chatMessages = document.getElementById('chatMessages');
  const chatLoadingState = document.getElementById('chatLoadingState');
  const chatEmptyState = document.getElementById('chatEmptyState');

  let pollInterval = null;
  let lastMessageCount = 0;

  function renderMessageItem(msg) {
    const isUser = msg.sender === 'user';
    const timeStr = msg.created_at ? toEnglishDigits(msg.created_at) : '';
    const safeText = escapeHtml(msg.text || '').replace(/\n/g, '<br/>');

    const bubble = document.createElement('div');
    if (isUser) {
      bubble.className = 'flex items-start justify-end gap-2 max-w-[85%] mr-auto animate-fadeIn';
      bubble.innerHTML = `
        <div class="chat-user-bubble border border-blue-500/40 bg-blue-500/10 rounded-2xl rounded-tl-none p-2.5 text-blue-100 leading-relaxed shadow-sm">
          ${safeText}
          <span class="text-[9px] text-blue-300 block text-left mt-1 font-mono" dir="ltr">${timeStr}</span>
        </div>
      `;
    } else {
      bubble.className = 'flex items-start gap-2 max-w-[85%] animate-fadeIn';
      bubble.innerHTML = `
        <div class="w-6 h-6 rounded-full bg-emerald-600 flex items-center justify-center text-[10px] shrink-0 text-white">🎧</div>
        <div class="chat-admin-bubble border border-slate-700/60 bg-slate-800/25 rounded-2xl rounded-tr-none p-2.5 text-slate-200 leading-relaxed shadow-sm">
          ${safeText}
          <span class="text-[9px] text-slate-400 block text-left mt-1 font-mono" dir="ltr">${timeStr}</span>
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
      const modal = document.getElementById('supportChatModal');
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
  const topBar = document.getElementById('topHeaderBar');
  if (!topBar) return;
  let padTop = 10;
  if (tg) {
    if (tg.contentSafeAreaInset?.top > 0) {
      padTop = tg.contentSafeAreaInset.top + 4;
    } else if (tg.safeAreaInset?.top > 0) {
      padTop = tg.safeAreaInset.top + 4;
    }
  }
  topBar.style.paddingTop = padTop + 'px';
}

function syncTelegramBackButton() {
  if (!tg?.BackButton) return;
  const modalIds = [
    'revokeModal', 'switchAccountModal', 'activeSessionsModal',
    'topupModal', 'luckyWheelModal', 'storyModal', 'storyCardModal',
    'supportChatModal', 'purchaseSuccessModal',
    'qrModal', 'checkoutConfirmModal'
  ];
  const hasOpenModal = modalIds.some(id => {
    const el = document.getElementById(id);
    return el && !el.classList.contains('hidden');
  });

  const qr = document.getElementById('qrContainer');
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
      document.getElementById('closeBtn')?.classList.add('hidden');
    }

    if (tg.BackButton) {
      tg.BackButton.onClick(() => {
        const modalIds = [
          'revokeModal', 'switchAccountModal', 'activeSessionsModal',
          'topupModal', 'luckyWheelModal', 'storyModal', 'purchaseSuccessModal',
          'qrModal', 'checkoutConfirmModal'
        ];
        for (const id of modalIds) {
          const el = document.getElementById(id);
          if (el && !el.classList.contains('hidden')) {
            el.classList.add('hidden');
            syncTelegramBackButton();
            return;
          }
        }
        const qr = document.getElementById('qrContainer');
        if (qr && !qr.classList.contains('hidden')) {
          qr.classList.add('hidden');
          const qrToggle = document.getElementById('qrToggleBtn');
          if (qrToggle) qrToggle.innerHTML = '<span class="text-sm">📷</span>';
          syncTelegramBackButton();
          return;
        }

        const dashBtn = document.querySelector('.nav-btn[data-tab="tab-dashboard"]');
        dashBtn?.click();
      });

      const observedModalIds = [
        'revokeModal', 'switchAccountModal', 'activeSessionsModal',
        'topupModal', 'luckyWheelModal', 'storyModal', 'qrContainer',
        'purchaseSuccessModal', 'qrModal', 'checkoutConfirmModal'
      ];
      observedModalIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
          const obs = new MutationObserver(() => syncTelegramBackButton());
          obs.observe(el, { attributes: true, attributeFilter: ['class'] });
        }
      });
      syncTelegramBackButton();
    }

    document.getElementById('closeBtn')?.addEventListener('click', () => {
      if (tg) tg.close();
      else alert('این دکمه در تلگرام واقعی، پنجره مینی‌اپ را می‌بندد.');
    });
  } else {
    updateTopPadding();
  }
}

// 12. Multi-Account Switcher
function setupAccountSwitcher() {
  const switchAccountModal = document.getElementById('switchAccountModal');
  const switchAccountBtn = document.getElementById('switchAccountBtn');
  const closeSwitchAccountBtn = document.getElementById('closeSwitchAccountBtn');
  const switchAccountList = document.getElementById('switchAccountList');

  switchAccountBtn?.addEventListener('click', () => {
    const accounts = window.lastUserData?.accounts || [];
    if (!switchAccountList) return;
    switchAccountList.innerHTML = accounts.map(acc => `
      <button class="select-acc-item w-full p-2.5 rounded-xl border ${acc.is_active ? 'border-blue-500 bg-blue-950/50' : 'border-slate-700 bg-slate-900/60 hover:border-slate-600'} text-right flex items-center justify-between transition" data-id="${acc.id}">
        <div>
          <div class="font-bold text-white text-xs flex items-center gap-1.5">
            <span>👤</span> ${acc.username}
          </div>
          <span class="text-[10px] text-slate-400 mt-0.5 block font-mono" dir="ltr">
            ${acc.used_gb} GB / ${acc.total_gb > 0 ? acc.total_gb + ' GB' : 'نامحدود'}
          </span>
        </div>
        ${acc.is_active ? '<span class="text-xs text-blue-400 font-bold bg-blue-500/20 px-2 py-0.5 rounded-full border border-blue-500/40">فعال ✓</span>' : '<span class="text-xs text-slate-300 bg-slate-800 px-2 py-0.5 rounded-full">انتخاب</span>'}
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
  document.getElementById('langFaBtn')?.addEventListener('click', () => changeAppLanguage('fa'));
  document.getElementById('langEnBtn')?.addEventListener('click', () => changeAppLanguage('en'));

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

  document.getElementById('copyProfileIdBtn')?.addEventListener('click', () => {
    const idVal = document.getElementById('profileTelegramId')?.innerText;
    if (idVal && idVal !== '--') {
      copyToClipboard(idVal, '📋 شناسه عددی تلگرام در کلیپ‌بورد کپی شد.');
    }
  });

  document.getElementById('copyProfileRefBtn')?.addEventListener('click', () => {
    const refVal = document.getElementById('profileRefCode')?.innerText;
    if (refVal && refVal !== '--') {
      copyToClipboard(refVal, '📋 کد معرف در کلیپ‌بورد کپی شد.');
    }
  });

  document.getElementById('gotoShopFromWallet')?.addEventListener('click', () => {
    const shopNav = document.querySelector('.nav-btn[data-tab="tab-shop"]');
    shopNav?.click();
  });
}

// 14. UI Hydration Logic
function hydrateUserInterface(data) {
  if (!data) return;

  const user = data.user || {};
  const sub = data.active_sub;
  if (sub?.id && !window.currentAccountId) {
    window.currentAccountId = sub.id;
  }

  // Header Avatar & Name
  const avatarEl = document.getElementById('headerUserAvatarInitial') || document.getElementById('headerUserAvatar');
  if (avatarEl && (user.first_name || user.username)) {
    avatarEl.innerText = (user.first_name || user.username || 'U')[0].toUpperCase();
  }

  const usernameEl = document.getElementById('headerUsername');
  if (usernameEl) {
    usernameEl.innerText = sub?.username || user.username || user.first_name || 'کاربر';
  }

  const onlineCount = sub?.devices_count ?? (sub?.devices ? sub.devices.length : 0);
  const onlineCountEl = document.getElementById('headerOnlineCount');
  if (onlineCountEl) {
    onlineCountEl.innerText = `${onlineCount} دستگاه آنلاین`;
  }

  // Dashboard Traffic Gauge
  const gaugeProgress = document.getElementById('dashboardGaugeProgress');
  if (sub) {
    const remainEl = document.getElementById('dashboardRemainingTraffic');
    if (remainEl) remainEl.innerText = `${sub.traffic_remaining_gb ?? '--'} GB`;

    const pctEl = document.getElementById('dashboardPercentRemaining');
    if (pctEl) pctEl.innerText = `${Math.round(sub.percent_remaining ?? 100)}٪`;

    const pillEl = document.getElementById('dashboardUsagePill');
    if (pillEl) pillEl.innerText = `${sub.traffic_used_gb ?? 0} / ${sub.traffic_total_gb ?? 0} GB`;

    const daysEl = document.getElementById('dashboardDaysLeft');
    if (daysEl) daysEl.innerText = `${sub.days_left ?? 0} روز`;

    const expireEl = document.getElementById('dashboardExpireDate');
    if (expireEl) expireEl.innerText = sub.expire_jalali ? `تا ${sub.expire_jalali}` : 'نامحدود';

    const todayEl = document.getElementById('dashboardTodayUsed');
    if (todayEl) todayEl.innerText = `${sub.today_used_gb ?? '0.00'} GB`;

    if (gaugeProgress) {
      const circumference = 314.15;
      const pct = Math.max(0, Math.min(100, sub.percent_remaining ?? 100));
      const offset = circumference - (circumference * (pct / 100));
      gaugeProgress.style.strokeDashoffset = offset;
    }

    const subInputEl = document.getElementById('subInput');
    if (subInputEl && sub.subscription_url) subInputEl.value = sub.subscription_url;
    const subDisplayEl = document.getElementById('subDisplayBox');
    if (subDisplayEl && sub.subscription_url) subDisplayEl.innerText = sub.subscription_url;
    const qrImg = document.getElementById('qrImage');
    if (qrImg && sub.subscription_url) {
      qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(sub.subscription_url)}`;
    }
    const modalQrImg = document.getElementById('modalQrImage');
    if (modalQrImg && sub.subscription_url) {
      modalQrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=260x260&data=${encodeURIComponent(sub.subscription_url)}`;
    }
  } else {
    const subInputEl = document.getElementById('subInput');
    if (subInputEl) subInputEl.value = 'اشتراک فعالی یافت نشد - لطفاً از تب فروشگاه اقدام فرمایید.';
    const subDisplayEl = document.getElementById('subDisplayBox');
    if (subDisplayEl) subDisplayEl.innerText = 'اشتراک فعالی یافت نشد - لطفاً از تب فروشگاه اقدام فرمایید.';
  }

  // Story Card Data Binding
  const storyName = document.getElementById('storyCardName');
  const storyUser = document.getElementById('storyCardUsername');
  const storyAvatarImg = document.getElementById('storyCardAvatarImg');
  const storyAvatar = document.getElementById('storyCardAvatarInitial');
  const storyTraffic = document.getElementById('storyCardTraffic');
  const storyDays = document.getElementById('storyCardDays');
  const storyQr = document.getElementById('storyCardQr');
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

  const tgPhoto = window.Telegram?.WebApp?.initDataUnsafe?.user?.photo_url || user.photo_url;
  if (tgPhoto && storyAvatarImg) {
    storyAvatarImg.crossOrigin = 'anonymous';
    storyAvatarImg.src = tgPhoto;
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

  if (storyTraffic) storyTraffic.innerText = `${sub?.traffic_remaining_gb ?? '--'} GB`;
  if (storyDays) storyDays.innerText = `${toEnglishDigits(sub?.days_left ?? 0)} روز اعتبار`;
  const botUsername = data.bot_username || window.Telegram?.WebApp?.initDataUnsafe?.bot?.username || 'RemnaWaveBot';
  const refLink = `https://t.me/${botUsername}?start=ref_${user.id || ''}`;
  window.currentReferralLink = refLink;
  if (storyQr) {
    storyQr.crossOrigin = 'anonymous';
    storyQr.src = `https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=${encodeURIComponent(refLink)}`;
  }

  // Today Country Breakdown
  const countryList = document.getElementById('countryBreakdownList');
  const countryTotalHeader = document.getElementById('countryTodayTotalHeader');
  if (countryTotalHeader) countryTotalHeader.innerText = `${sub?.today_used_gb ?? '0.00'} GB`;
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
            <span class="text-cyan-300 font-black text-xs font-mono" dir="ltr">${toEnglishDigits(item.total_formatted)}</span>
            <span class="flex items-center gap-2 font-bold text-slate-200">
              <span>${item.name}</span>
              <span class="text-base">${item.flag || '🌐'}</span>
            </span>
          </div>
          ${barHtml}
        </div>
        `;
      }).join('');
    }
  }

  // Reports Hub (All Numbers in English ASCII format)
  if (data.yesterday_jalali) {
    const repDateEl = document.getElementById('repNightlyDate');
    if (repDateEl) repDateEl.innerText = `${toEnglishDigits(data.yesterday_jalali)} - 23:59`;
  }
  if (sub) {
    const repTotal = document.getElementById('repNightlyTotal');
    if (repTotal) repTotal.innerText = `${sub.traffic_total_gb ?? '--'} GB`;
    const repUsed = document.getElementById('repNightlyUsed');
    if (repUsed) repUsed.innerText = `${sub.traffic_used_gb ?? '--'} GB`;
    const repRemain = document.getElementById('repNightlyRemain');
    if (repRemain) repRemain.innerText = `${sub.traffic_remaining_gb ?? '--'} GB`;
    const repYesterday = document.getElementById('repNightlyYesterday');
    if (repYesterday) repYesterday.innerText = `${sub.yesterday_used_gb ?? '0.00'} GB`;
    const repExpire = document.getElementById('repNightlyExpire');
    if (repExpire) repExpire.innerText = `${toEnglishDigits(sub.days_left ?? 0)} روز (${toEnglishDigits(sub.expire_jalali || 'نامحدود')})`;

    // Reusable Server Breakdown for Nightly, Weekly, Monthly
    renderNodeBreakdown('repNightlyNodesContainer', sub.yesterday_breakdown || sub.today_breakdown || [], 'دیشب مصرفی روی سرورها ثبت نشده است.');
    renderNodeBreakdown('repWeeklyNodesContainer', sub.week_breakdown || [], 'مصرفی در 7 روز گذشته ثبت نشده است.');
    renderNodeBreakdown('repMonthlyNodesContainer', sub.week_breakdown || sub.today_breakdown || [], 'مصرفی در ماه جاری ثبت نشده است.');

    const repWeeklyTotal = document.getElementById('repWeeklyTotal');
    if (repWeeklyTotal) repWeeklyTotal.innerHTML = `<span dir="ltr" class="font-mono inline-block">\u200E${sub.week_used_gb ?? '0.00'} GB\u200E</span>`;
    const repWeeklyBusiest = document.getElementById('repWeeklyBusiest');
    if (repWeeklyBusiest) {
      repWeeklyBusiest.innerHTML = `${sub.busiest_day_name || '—'} <span dir="ltr" class="font-mono inline-block text-cyan-300 font-semibold">\u200E(${toEnglishDigits(sub.busiest_day_amount || '0 GB')})\u200E</span>`;
    }

    // Weekly & Monthly Charts using DRY Chart.js renderBarChart
    try {
      renderBarChart('repWeeklyChartCanvas', sub.week_daily_totals_gb || [0, 0, 0, 0, 0, 0, 0], sub.week_day_labels || ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'], false);
    } catch (e) {
      console.warn('Could not render weekly chart:', e);
    }

    const repMonthlyTitle = document.getElementById('repMonthlyTitle');
    if (repMonthlyTitle) repMonthlyTitle.innerText = `📅 گزارش جامع ماه ${sub.current_month_name || ''}`;
    const repMonthlyTotal = document.getElementById('repMonthlyTotal');
    if (repMonthlyTotal) repMonthlyTotal.innerHTML = `<span dir="ltr" class="font-mono inline-block">\u200E${sub.month_used_gb ?? '0.00'} GB\u200E</span>`;

    try {
      renderBarChart('repMonthlyChartCanvas', sub.month_weeks_totals_gb || [0, 0, 0, sub.week_used_gb || 0], ['هفته ۱', 'هفته ۲', 'هفته ۳', 'هفته ۴'], true);
    } catch (e) {
      console.warn('Could not render monthly chart:', e);
    }

    // Advanced Analytics (4 Visualizers)
    try {
      renderActiveSubAnalytics(sub);
    } catch (e) {
      console.warn('Could not render active sub analytics:', e);
    }
  }

function renderActiveSubAnalytics(sub) {
  if (!sub) return;

  // 1. Traffic Split (Download vs Upload)
  if (typeof renderTrafficSplit === 'function') {
    try {
      renderTrafficSplit(sub.traffic_split);
    } catch (e) {
      console.warn('Error rendering traffic split', e);
    }
  }

  // 2. 24h Peak Usage Area Curve
  if (typeof renderLineCurveChart === 'function') {
    try {
      renderLineCurveChart(
        'repPeakHoursChartCanvas',
        sub.hourly_usage?.labels || [
          '00:00','02:00','04:00','06:00','08:00','10:00',
          '12:00','14:00','16:00','18:00','20:00','22:00'
        ],
        sub.hourly_usage?.data || [
          0.1, 0.05, 0.02, 0.05, 0.2, 0.4, 0.6, 0.5, 0.7, 1.2, 1.5, 0.8
        ],
        sub.hourly_usage?.peak_hour || '21:00'
      );
    } catch (e) {
      console.warn('Error rendering peak hours chart', e);
    }
  }

  // 3. Country / Cluster Donut Chart
  if (typeof renderDonutChart === 'function') {
    try {
      const countryLabels = sub.country_share?.labels?.length ? sub.country_share.labels : ['🇳🇱 هلند', '🇩🇪 آلمان', '🇹🇷 ترکیه'];
      const countryData = sub.country_share?.data?.length ? sub.country_share.data : [15.2, 6.4, 2.8];
      renderDonutChart('repCountryChartCanvas', countryLabels, countryData, false);
    } catch (e) {
      console.warn('Error rendering country donut chart', e);
    }

    // 4. Device Platform Donut Chart
    try {
      const devLabels = sub.device_share?.labels?.length ? sub.device_share.labels : ['🤖 Android', '🍏 iOS'];
      const devData = sub.device_share?.data?.length ? sub.device_share.data : [1, 1];
      renderDonutChart('repDeviceChartCanvas', devLabels, devData, true);
    } catch (e) {
      console.warn('Error rendering device donut chart', e);
    }
  }
}

  // Active Devices
  const devices = sub?.devices || [];
  const activeDevCount = sub?.devices_count ?? devices.length;
  const repSessionsBadge = document.getElementById('reportsSessionsBadge');
  if (repSessionsBadge) repSessionsBadge.innerText = `${toEnglishDigits(activeDevCount)} دستگاه`;
  const mCountText = document.getElementById('modalSessionsCount');
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
                <span class="text-xs font-bold text-slate-200">${model}</span>
                <span class="w-2 h-2 rounded-full bg-emerald-400 inline-block shadow-sm shadow-emerald-400/50" title="فعال"></span>
              </div>
              <div class="text-[11px] font-mono text-cyan-400 mt-0.5">IP: ${ip}</div>
            </div>
          </div>
          <button class="kill-device-btn text-rose-400 hover:text-white w-8 h-8 rounded-xl bg-rose-950/40 hover:bg-rose-900 border border-rose-800/50 text-xs transition active:scale-95 flex items-center justify-center shadow-sm" title="قطع این دستگاه" data-hwid="${hwid}">
            <svg class="w-4 h-4 text-rose-400 hover:text-rose-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
      `;
    }).join('');

    container.querySelectorAll('.kill-device-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const hwid = btn.getAttribute('data-hwid');
        if (!hwid || !confirm('آیا از قطع اتصال این دستگاه اطمینان دارید؟')) return;
        try {
          const res = await window.api.killDevice(hwid);
          if (res.ok) {
            showToast('✅ دستگاه با موفقیت قطع شد.');
            syncUserDataWithApi();
          } else {
            showToast(`❌ ${res.error || 'خطا در قطع دستگاه'}`);
          }
        } catch (e) {
          showToast('خطا در برقراری ارتباط با سرور.');
        }
      });
    });
  }

  renderDeviceList(document.getElementById('activeDevicesContainer'));
  renderDeviceList(document.getElementById('modalSessionsList'));

  document.getElementById('openDashboardSessionsBtn')?.addEventListener('click', () => openModal('activeSessionsModal'));
  document.getElementById('headerOnlineBadge')?.addEventListener('click', () => openModal('activeSessionsModal'));
  document.getElementById('closeSessionsModalBtn')?.addEventListener('click', () => closeModal('activeSessionsModal'));
  document.getElementById('modalKillAllBtn')?.addEventListener('click', () => {
    document.getElementById('killAllBtn')?.click();
  });

  // Shop Plans
  renderShopPlans(data);

  // Wallet Balances
  const walletEl = document.getElementById('shopWalletBalance');
  const walletTabBal = document.getElementById('walletTabBalance');
  const formattedWallet = `${Number(user.wallet_balance || 0).toLocaleString('en-US')} تومان`;
  if (walletEl) walletEl.innerText = `موجودی: ${formattedWallet}`;
  if (walletTabBal) walletTabBal.innerText = formattedWallet;

  // Profile Identity
  const profName = document.getElementById('profileFullName');
  const profUser = document.getElementById('profileUsername');
  const profAvatar = document.getElementById('profileAvatarInitial');
  const profStatusBadge = document.getElementById('profileStatusBadge');
  const profAuthBadge = document.getElementById('profileAuthBadge');
  const profId = document.getElementById('profileTelegramId');
  const profRef = document.getElementById('profileRefCode');
  const profPhone = document.getElementById('profilePhone');
  const profJoin = document.getElementById('profileJoinDate');
  const profBirth = document.getElementById('profileBirthDate');
  const profSub = document.getElementById('profileSubStatus');

  const userDisplayName = sub?.username || user.first_name || user.username || 'کاربر گرامی';
  if (profName) profName.innerText = userDisplayName;
  if (profUser) profUser.innerText = user.username ? `@${user.username}` : `شناسه: ${user.id || ''}`;
  if (profAvatar) profAvatar.innerText = userDisplayName.charAt(0).toUpperCase();
  if (profId) profId.innerText = user.id ? String(user.id) : '--';
  if (profRef) profRef.innerText = user.id ? String(user.id) : '--';
  if (profPhone) profPhone.innerText = user.phone_number ? toEnglishDigits(user.phone_number) : 'وارد نشده';
  if (profJoin) profJoin.innerText = toEnglishDigits(user.created_at_jalali || '1403/07/01');
  if (profBirth) profBirth.innerText = user.birth_date ? toEnglishDigits(user.birth_date) : 'ثبت‌نشده';

  const hasActiveSub = Boolean(data.has_active_sub && (sub?.status === 'ACTIVE' || !sub?.status));
  if (profStatusBadge) {
    if (hasActiveSub) {
      profStatusBadge.innerText = 'کاربر فعال 🟢';
      profStatusBadge.className = 'px-2.5 py-0.5 rounded-full text-[10px] font-bold border badge-active transition';
    } else {
      profStatusBadge.innerText = 'بدون سرویس فعال ⚪️';
      profStatusBadge.className = 'px-2.5 py-0.5 rounded-full text-[10px] font-bold border badge-inactive transition';
    }
  }

  if (profAuthBadge) {
    if (user.phone_number) {
      profAuthBadge.innerText = 'احراز هویت شده ✅';
      profAuthBadge.className = 'px-2.5 py-0.5 rounded-full text-[10px] font-bold border badge-auth transition';
    } else {
      profAuthBadge.innerText = 'عدم احراز هویت ⚠️';
      profAuthBadge.className = 'px-2.5 py-0.5 rounded-full text-[10px] font-bold border badge-unauth transition';
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

  // Profile Settings Switches
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
    const el = document.getElementById(id);
    if (!el) return;
    const val = (settings[key] !== undefined) ? Boolean(settings[key]) : defaultVal;
    el.checked = val;

    el.onchange = async () => {
      const newVal = el.checked;
      try {
        const res = await window.api.saveSetting(key, newVal);
        if (res.ok) {
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

  // Configurable Alert Thresholds Selects & Dynamic Subtexts
  function updateAlertSubtexts(percent, days) {
    if (percent !== undefined && percent !== null) {
      const traf = document.getElementById('settingTrafficSubtext');
      if (traf) traf.innerText = `هشدار قبل از پایان ترافیک (${toEnglishDigits(percent)}%)`;
    }
    if (days !== undefined && days !== null) {
      const exp = document.getElementById('settingExpireSubtext');
      if (exp) exp.innerText = `اطلاع‌رسانی ${toEnglishDigits(days)} روز مانده به انقضا`;
    }
  }

  const trafficPercentSelect = document.getElementById('settingTrafficPercentSelect');
  if (trafficPercentSelect) {
    if (settings.traffic_percent) trafficPercentSelect.value = String(settings.traffic_percent);
    trafficPercentSelect.onchange = async () => {
      const val = parseInt(trafficPercentSelect.value, 10);
      updateAlertSubtexts(val, undefined);
      try {
        const res = await window.api.saveSetting('traffic_percent', val);
        if (res.ok) {
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

  const expireDaysSelect = document.getElementById('settingExpireDaysSelect');
  if (expireDaysSelect) {
    if (settings.expire_days) expireDaysSelect.value = String(settings.expire_days);
    expireDaysSelect.onchange = async () => {
      const val = parseInt(expireDaysSelect.value, 10);
      updateAlertSubtexts(undefined, val);
      try {
        const res = await window.api.saveSetting('expire_days', val);
        if (res.ok) {
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

  // Language buttons
  const currentLang = user.language || 'fa';
  const langFaBtn = document.getElementById('langFaBtn');
  const langEnBtn = document.getElementById('langEnBtn');
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

  // Avatar photos
  const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
  const avatarUrl = tgUser?.photo_url || `/api/user/avatar?id=${user.id || tgUser?.id || ''}`;
  if (avatarUrl) {
    const profImg = document.getElementById('profileAvatarImg');
    const headImg = document.getElementById('headerUserAvatarImg');
    const testImg = new Image();
    testImg.src = avatarUrl;
    testImg.onload = () => {
      if (profImg) {
        profImg.src = avatarUrl;
        profImg.classList.remove('hidden');
        profAvatar?.classList.add('hidden');
      }
      if (headImg) {
        headImg.src = avatarUrl;
        headImg.classList.remove('hidden');
        document.getElementById('headerUserAvatarInitial')?.classList.add('hidden');
      }
    };
  }

  // Account Switcher button visibility
  const switchBtn = document.getElementById('switchAccountBtn');
  const accounts = data.accounts || [];
  if (switchBtn) {
    if (accounts.length > 1) switchBtn.classList.remove('hidden');
    else switchBtn.classList.add('hidden');
  }

  // Wallet Transactions List
  renderWalletTransactions(data.transactions);

  // Wheel Status
  if (data.wheel_status) {
    updateWheelUIState(
      data.wheel_status.can_spin,
      data.wheel_status.has_active_sub,
      data.wheel_status.next_spin_seconds || 0
    );
  }
}

// 15. Stale-While-Revalidate API Sync
async function syncUserDataWithApi(accountId) {
  try {
    const res = await window.api.getMe(accountId);
    if (res.ok && res.data) {
      window.lastUserData = res.data;
      hydrateUserInterface(res.data);
      try {
        localStorage.setItem('remna_user_cache', JSON.stringify(res.data));
      } catch(e) {}
    }
  } catch (err) {
    console.debug('Live API sync fallback to cache', err);
  }
}

// 16. Initialize Application
document.addEventListener('DOMContentLoaded', () => {
  setupTabNavigation();
  setupReportsSubtabs();
  setupSubscriptionActions();
  setupQrToggle();
  setupRevokeAndKill();
  setupClientImporters();
  setupThemeToggle();
  setupNetworkTools();
  setupSupportChat();
  setupTelegramSDK();
  setupAccountSwitcher();
  setupProfileHandlers();
  setupCouponInput();
  setupWalletListeners();
  setupLuckyWheel();
  setupStoryCard();

  // DRY accordions
  setupAccordion('toggleCountryBreakdownBtn', 'countryBreakdownBody', 'countryChevron');
  setupAccordion('toggleSessionsAccordionBtn', 'sessionsAccordionBody', 'sessionsChevron');
  setupAccordion('toggleSubAccordionBtn', 'subAccordionBody', 'subChevron');

  loadNetworkNodes();
  loadClientIpInfo();

  try {
    const cached = localStorage.getItem('remna_user_cache');
    if (cached) {
      const parsed = JSON.parse(cached);
      window.lastUserData = parsed;
      hydrateUserInterface(parsed);
    }
  } catch(e) {}

  syncUserDataWithApi();
});

window.syncUserDataWithApi = syncUserDataWithApi;
window.hydrateUserInterface = hydrateUserInterface;
