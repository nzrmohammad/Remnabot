/**
 * RemnaAdmin Pro - Modular Admin Suite JavaScript
 * Follows DRY, anti-bloat, and high-performance asynchronous standards.
 */

(function () {
  'use strict';

  const _domCache = new Map();
  const $ = id => {
    let elem = _domCache.get(id);
    if (!elem || !elem.isConnected) {
      elem = document.getElementById(id);
      if (elem) _domCache.set(id, elem);
    }
    return elem;
  };
  const el = new Proxy({}, { get: (_, id) => $(id) });

  // State Management
  const tg = window.Telegram?.WebApp;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.setHeaderColor) tg.setHeaderColor('#0f172a');
      if (tg.setBackgroundColor) tg.setBackgroundColor('#080d1a');
    } catch (e) {}
  }

  let currentPage = 1;
  let currentFilter = 'all';
  let currentSearch = '';
  let currentModifyTarget = null;
  let currentWalletTarget = null;
  let currentHwidTarget = null;
  let currentSubTarget = null;
  let currentTrialTarget = null;
  let adminPlansData = [];
  let adminCouponsData = [];
  let currentBroadcastTarget = 'all';
  let cachedOverviewData = null;

  // --- 0. Splash Screen Handler ---
  function dismissSplash() {
    const splash = $('splashScreen');
    const splashBar = $('splashBar');
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

  // Fail-safe auto-dismiss after 950ms
  setTimeout(dismissSplash, 950);

  // --- 1. Helper Utilities ---
  function getFlagEmoji(code) {
    if (!code || code.length !== 2) return '🌐';
    const c = code.toUpperCase();
    const offset = 127397;
    return String.fromCodePoint(c.charCodeAt(0) + offset, c.charCodeAt(1) + offset);
  }

  function formatNumber(num) {
    if (num === null || num === undefined || isNaN(Number(num))) return '0';
    const n = Number(num);
    const rounded = Number.isInteger(n) ? n.toString() : (Math.round(n * 100) / 100).toString();
    const [intPart, decPart] = rounded.split('.');
    const formattedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return decPart !== undefined ? `${formattedInt}.${decPart}` : formattedInt;
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

  // --- 2. Tab Navigation ---
  const adminNavButtons = document.querySelectorAll('.admin-nav-btn');
  const adminTabPanes = document.querySelectorAll('.admin-tab-pane');

  adminNavButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-admin-tab');
      adminTabPanes.forEach(pane => {
        if (pane.id === targetId) {
          pane.classList.remove('hidden');
        } else {
          pane.classList.add('hidden');
        }
      });

      adminNavButtons.forEach(b => {
        b.classList.remove('text-blue-400');
        b.classList.add('text-slate-400');
        const label = b.querySelector('span:last-child');
        if (label) {
          label.classList.remove('font-bold');
          label.classList.add('font-medium');
        }
      });
      btn.classList.remove('text-slate-400');
      btn.classList.add('text-blue-400');
      const activeLabel = btn.querySelector('span:last-child');
      if (activeLabel) {
        activeLabel.classList.remove('font-medium');
        activeLabel.classList.add('font-bold');
      }

      if (window.hapticFeedback) window.hapticFeedback('impact');

      if (targetId === 'tab-admin-overview' || targetId === 'tab-admin-dashboard') {
        salesChartInstance?.resize();
        trafficChartInstance?.resize();
        locationChartInstance?.resize();
        hourlyChartInstance?.resize();
        retentionChartInstance?.resize();
        planSalesChartInstance?.resize();
        platformChartInstance?.resize();
        paymentChartInstance?.resize();
        churnChartInstance?.resize();
        hwidChartInstance?.resize();
      }

      // Lazy load tab data
      if (targetId === 'tab-admin-nodes') {
        if ($('adminOverviewNodesList')?.children.length <= 1) {
          syncAdminOverview(false);
        }
        if ($('adminSslHealthList')?.children.length <= 1) {
          fetchAdminSslHealth();
        }
      } else if (targetId === 'tab-admin-users' && $('adminUsersList')?.children.length <= 1) {
        fetchAdminUsers(1);
      } else if (targetId === 'tab-admin-plans') {
        if ($('adminPlansList')?.children.length <= 1) {
          fetchAdminPlans();
          fetchAdminCoupons();
        }
      } else if (targetId === 'tab-admin-coupons') {
        if ($('adminCouponsList')?.children.length <= 1) {
          fetchAdminCoupons();
        }
      } else if (targetId === 'tab-admin-tickets') {
        if ($('ticketThreadsList')?.children.length === 0) {
          fetchAdminTopups();
          fetchTicketThreads();
          const contentCampaigns = $('subtabContentCampaigns');
          if (contentCampaigns && !contentCampaigns.classList.contains('hidden')) {
            window.adminActions?.fetchAdminCampaigns?.();
          }
        }
      } else if (targetId === 'tab-admin-campaigns') {
        if ($('adminCampaignsList')?.children.length <= 1) {
          window.adminActions?.fetchAdminCampaigns?.();
        }
      } else if (targetId === 'tab-admin-settings') {
        if (!window._adminSettingsLoaded) {
          fetchAdminSettings();
        }
      }
    });
  });

  // Subtab switcher for Unified Plans & Discounts Tab
  window.switchServicesSubtab = function(subtab) {
    const btnPlans = $('subtabBtnPlans');
    const btnCoupons = $('subtabBtnCoupons');
    const contentPlans = $('subtabContentPlans');
    const contentCoupons = $('subtabContentCoupons');

    if (window.hapticFeedback) window.hapticFeedback('selection');

    if (subtab === 'plans') {
      btnPlans?.classList.add('bg-blue-600', 'text-white', 'shadow');
      btnPlans?.classList.remove('text-slate-400', 'hover:text-slate-200');
      btnCoupons?.classList.remove('bg-purple-600', 'bg-blue-600', 'text-white', 'shadow');
      btnCoupons?.classList.add('text-slate-400', 'hover:text-slate-200');

      contentPlans?.classList.remove('hidden');
      contentCoupons?.classList.add('hidden');
      if (typeof fetchAdminPlans === 'function') fetchAdminPlans();
    } else {
      btnCoupons?.classList.add('bg-purple-600', 'text-white', 'shadow');
      btnCoupons?.classList.remove('text-slate-400', 'hover:text-slate-200');
      btnPlans?.classList.remove('bg-blue-600', 'text-white', 'shadow');
      btnPlans?.classList.add('text-slate-400', 'hover:text-slate-200');

      contentCoupons?.classList.remove('hidden');
      contentPlans?.classList.add('hidden');
      if (typeof fetchAdminCoupons === 'function') fetchAdminCoupons();
    }
  };

  // Subtab switcher for Unified Financial Tab (Topups vs Campaigns)
  window.switchFinanceSubtab = function(subtab) {
    const btnTopups = $('subtabBtnTopups');
    const btnCampaigns = $('subtabBtnCampaigns');
    const contentTopups = $('subtabContentTopups');
    const contentCampaigns = $('subtabContentCampaigns');

    if (window.hapticFeedback) window.hapticFeedback('selection');

    if (subtab === 'topups') {
      btnTopups?.classList.add('bg-blue-600', 'text-white', 'shadow');
      btnTopups?.classList.remove('text-slate-400', 'hover:text-slate-200');
      btnCampaigns?.classList.remove('bg-blue-600', 'text-white', 'shadow');
      btnCampaigns?.classList.add('text-slate-400', 'hover:text-slate-200');

      contentTopups?.classList.remove('hidden');
      contentCampaigns?.classList.add('hidden');
      if (typeof fetchAdminTopups === 'function') fetchAdminTopups();
    } else {
      btnCampaigns?.classList.add('bg-blue-600', 'text-white', 'shadow');
      btnCampaigns?.classList.remove('text-slate-400', 'hover:text-slate-200');
      btnTopups?.classList.remove('bg-blue-600', 'text-white', 'shadow');
      btnTopups?.classList.add('text-slate-400', 'hover:text-slate-200');

      contentCampaigns?.classList.remove('hidden');
      contentTopups?.classList.add('hidden');
      if (window.adminActions && typeof window.adminActions.fetchAdminCampaigns === 'function') {
        window.adminActions.fetchAdminCampaigns();
      }
    }
  };

  // --- 3. Theme Toggle ---
  const adminThemeToggle = $('adminThemeToggle');
  const adminThemeIcon = $('adminThemeIcon');
  const getInitialAdminTheme = () => {
    const saved = localStorage.getItem('remna_admin_theme');
    if (saved) return saved === 'dark';
    if (window.Telegram?.WebApp?.colorScheme) {
      return window.Telegram.WebApp.colorScheme === 'dark';
    }
    return !(window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches);
  };
  let isDark = getInitialAdminTheme();

  const getThemeColors = () => ({
    grid: isDark ? 'rgba(51, 65, 85, 0.3)' : 'rgba(148, 163, 184, 0.45)',
    tick: isDark ? '#cbd5e1' : '#0f172a',
    legendText: isDark ? '#f8fafc' : '#0f172a',
    pointBorder: isDark ? '#0f172a' : '#ffffff',
  });

  const updateChartsTheme = () => {
    const { grid, tick, legendText, pointBorder } = getThemeColors();

    const updateScaleChart = (chart) => {
      if (!chart) return;
      if (chart.options?.scales?.x?.ticks) chart.options.scales.x.ticks.color = tick;
      if (chart.options?.scales?.y?.ticks) chart.options.scales.y.ticks.color = tick;
      if (chart.options?.scales?.y?.grid) chart.options.scales.y.grid.color = grid;
      if (chart.options?.scales?.x?.grid) chart.options.scales.x.grid.color = grid;
      chart.update();
    };

    const updateDoughnutChart = (chart) => {
      if (!chart) return;
      if (chart.options?.plugins?.legend?.labels) {
        chart.options.plugins.legend.labels.color = legendText;
      }
      if (chart.legend?.legendItems) {
        chart.legend.legendItems.forEach(i => {
          i.fontColor = legendText;
          i.color = legendText;
        });
      }
      chart.update();
    };

    updateScaleChart(salesChartInstance);
    if (monthlySalesChartInstance) {
      if (monthlySalesChartInstance.data?.datasets?.[0]) {
        monthlySalesChartInstance.data.datasets[0].pointBorderColor = pointBorder;
      }
      updateScaleChart(monthlySalesChartInstance);
    }
    if (trafficChartInstance) {
      if (trafficChartInstance.data?.datasets?.[0]) {
        trafficChartInstance.data.datasets[0].pointBorderColor = pointBorder;
      }
      updateScaleChart(trafficChartInstance);
    }
    if (hourlyChartInstance) {
      if (hourlyChartInstance.data?.datasets?.[0]) {
        hourlyChartInstance.data.datasets[0].pointBorderColor = pointBorder;
      }
      updateScaleChart(hourlyChartInstance);
    }
    updateScaleChart(retentionChartInstance);
    updateScaleChart(hwidChartInstance);

    updateDoughnutChart(locationChartInstance);
    updateDoughnutChart(planSalesChartInstance);
    updateDoughnutChart(platformChartInstance);
    updateDoughnutChart(paymentChartInstance);
    updateDoughnutChart(churnChartInstance);
  };

  const applyThemeClasses = () => {
    const appBody = $('appBody');
    const phoneFrame = $('phoneFrame');
    if (isDark) {
      document.documentElement.classList.add('dark');
      document.documentElement.classList.remove('theme-light');
      if (adminThemeIcon) adminThemeIcon.innerHTML = `<svg class="w-3.5 h-3.5 text-amber-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" /></svg>`;
      appBody?.classList.replace('bg-slate-100', 'bg-[#080d1a]');
      phoneFrame?.classList.replace('bg-white', 'bg-[#0f172a]');
      phoneFrame?.classList.replace('text-slate-900', 'text-slate-100');
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('theme-light');
      if (adminThemeIcon) adminThemeIcon.innerHTML = `<svg class="w-3.5 h-3.5 text-indigo-300" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z" /></svg>`;
      appBody?.classList.replace('bg-[#080d1a]', 'bg-slate-100');
      phoneFrame?.classList.replace('bg-[#0f172a]', 'bg-white');
      phoneFrame?.classList.replace('text-slate-100', 'text-slate-900');
    }
  };

  // Apply initial theme immediately (saved or auto-detected)
  applyThemeClasses();

  try {
    window.Telegram?.WebApp?.onEvent('themeChanged', () => {
      if (!localStorage.getItem('remna_admin_theme')) {
        isDark = window.Telegram.WebApp.colorScheme === 'dark';
        applyThemeClasses();
        updateChartsTheme();
      }
    });
  } catch (e) {}

  adminThemeToggle?.addEventListener('click', () => {
    isDark = !isDark;
    localStorage.setItem('remna_admin_theme', isDark ? 'dark' : 'light');
    applyThemeClasses();
    updateChartsTheme();
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  // --- 4. Overview & Cluster Metrics ---
  async function syncAdminOverview(isForce = false) {
    try {
      const params = isForce ? { refresh: 1, t: Date.now() } : {};
      const res = await window.api.getAdminOverview(params);
      if (!res || !res.ok || !res.data) {
        dismissSplash();
        return;
      }

      const data = res.data;
      cachedOverviewData = data;
      const m = data.metrics || {};
      const nodes = data.nodes || [];

      // KPI Cards
      const totalU = $('adminTotalUsers');
      if (totalU) totalU.innerText = formatNumber(m.total_users || 0);

      const activeU = $('adminActiveUsers');
      if (activeU) activeU.innerText = `${formatNumber(m.active_panel_users || 0)} اکانت فعال پنل`;

      const rev = $('adminTodayRevenue');
      if (rev) rev.innerText = formatNumber(m.today_revenue_toman || 0);

      // Traffic: if >= 1000 GB, convert to TB for concise and single-line layout
      const bw = $('adminMonthTraffic');
      if (bw) {
        const trafficGb = Number(m.month_traffic_gb || 0);
        if (trafficGb >= 1000) {
          bw.innerText = `${(trafficGb / 1024).toFixed(2)} TB`;
        } else {
          bw.innerText = `${trafficGb} GB`;
        }
      }

      const onDev = $('adminOnlineDevices');
      if (onDev) onDev.innerText = formatNumber(m.online_devices || 0);

      // Infra-Billing & Net Profit Analytics
      const mRev = $('adminMonthlyRevenue');
      if (mRev) mRev.innerText = formatNumber(m.monthly_revenue_toman || 0);

      const iCost = $('adminTotalInfraCost');
      if (iCost) iCost.innerText = formatNumber(m.total_infra_cost_toman || 0);

      const nProf = $('adminNetProfit');
      if (nProf) {
        const netVal = Number(m.net_profit_toman || 0);
        const sign = netVal > 0 ? '+' : (netVal < 0 ? '-' : '');
        nProf.innerHTML = `<span dir="ltr">${sign}${formatNumber(Math.abs(netVal))}</span>`;
        nProf.className = netVal >= 0
          ? 'text-emerald-400 font-mono font-bold text-lg'
          : 'text-rose-400 font-mono font-bold text-lg';
      }

      const pMargin = $('adminProfitMarginBadge');
      if (pMargin) {
        const hasRevenue = Number(m.monthly_revenue_toman || 0) > 0;
        const marginVal = m.profit_margin_percent;
        if (!hasRevenue || marginVal === null || marginVal === undefined) {
          pMargin.innerText = 'مارجین: —';
          pMargin.className = 'text-[9px] font-mono font-bold bg-transparent text-slate-400 border border-slate-600/40 px-1.5 py-0.5 rounded-md';
        } else {
          const sign = marginVal > 0 ? '+' : (marginVal < 0 ? '-' : '');
          const absVal = Math.abs(marginVal);
          pMargin.innerHTML = `<span class="inline-flex items-center gap-0.5" dir="rtl"><span>مارجین:</span><span class="inline-flex items-center font-mono" dir="ltr"><span>${sign}</span><span>${absVal}</span><span>%</span></span></span>`;
          pMargin.className = marginVal >= 0
            ? 'text-[9px] font-mono font-bold bg-transparent text-emerald-400 border border-emerald-500/30 px-1.5 py-0.5 rounded-md'
            : 'text-[9px] font-mono font-bold bg-transparent text-rose-400 border border-rose-500/30 px-1.5 py-0.5 rounded-md';
        }
      }

      const costGb = $('adminAvgCostPerGb');
      if (costGb) costGb.innerText = formatNumber(m.avg_cost_per_gb || 0);

      // Dynamic Pending Tasks Alert Banner (Hidden if no pending tasks)
      const pendingBox = $('adminPendingBanner');
      const pendingSum = $('adminPendingSummary');
      const viewPendingBtn = $('viewPendingBtn');
      const pTopups = m.pending_topups || 0;
      const offNodes = m.offline_nodes || 0;

      if (pTopups > 0 || offNodes > 0) {
        const parts = [];
        if (pTopups > 0) parts.push(`${formatNumber(pTopups)} فیش واریزی در انتظار`);
        if (offNodes > 0) parts.push(`${formatNumber(offNodes)} سرور آفلاین`);

        if (pendingSum) pendingSum.innerText = parts.join(' + ');
        if (pendingBox) pendingBox.classList.remove('hidden');
        if (viewPendingBtn) viewPendingBtn.classList.remove('hidden');
      } else {
        if (pendingBox) pendingBox.classList.add('hidden');
      }

      // Cluster Status Header Bar
      const onlineNodes = nodes.filter(n => (n.status || '').toUpperCase() === 'ONLINE').length;
      const clusterText = $('adminClusterStatusText');
      if (clusterText) {
        clusterText.innerHTML = `وضعیت کلاستر: <b class="text-emerald-400">${formatNumber(onlineNodes)} از ${formatNumber(nodes.length)} نود آنلاین</b>`;
      }
      const syncText = $('adminLastSyncText');
      if (syncText) syncText.innerText = 'Sync: آنلاین';

      // Render Dashboard Analytics Charts
      lastOverviewData = data;
      if (data.rates) {
        if (data.rates.usdt_rate_toman) window.currentUsdRate = Number(data.rates.usdt_rate_toman);
        if (data.rates.eur_rate_toman) window.currentEurRate = Number(data.rates.eur_rate_toman);
      }
      if (data.charts) {
        const c = data.charts;
        if (typeof Chart === 'undefined' && typeof window.ensureChart === 'function') {
          try { await window.ensureChart(); } catch (e) {}
        }
        if (typeof Chart !== 'undefined') {
          renderAdminSalesChart(c.sales_labels, c.sales_data);
          renderAdminMonthlySalesChart(c.sales_30d_labels, c.sales_30d_data, c.sales_30d_total);
          renderAdminTrafficChart(c.traffic_labels, c.traffic_data, c.traffic_total_gb, c.today_traffic_gb);
          renderAdminLocationChart(c.location_share);
          renderAdminHourlyChart(c.hourly_distribution);
          renderAdminRetentionChart(c.retention_trend);
          renderAdminPlanSalesChart(c.plan_distribution);
          renderAdminPlatformChart(c.platform_distribution);
          renderAdminPaymentChart(c.payment_distribution);
          renderAdminRetentionStatsChart(c.retention_stats);
          renderAdminHwidChart(c.hwid_distribution);
        }
      }

      // Render Accordion Nodes
      renderOverviewNodes(nodes);
      renderFullNodes(nodes);
      dismissSplash();
    } catch (err) {
      console.error('Failed to sync admin overview:', err);
      dismissSplash();
    }
  }

  let lastOverviewData = null;
  if (typeof Chart !== 'undefined') {
    Chart.defaults.color = isDark ? '#f8fafc' : '#0f172a';
    Chart.defaults.font.family = 'Vazirmatn';
  }
  let salesChartInstance = null;
  function renderAdminSalesChart(labels, values) {
    const canvas = $('adminSalesChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const totalSum = (values || []).reduce((a, b) => a + b, 0);
    const totalEl = $('salesChartTotal');
    if (totalEl) totalEl.innerHTML = `<span class="font-mono font-bold">${formatNumber(totalSum)}</span> <span>تومان</span>`;

    if (salesChartInstance) {
      salesChartInstance.data.labels = labels;
      salesChartInstance.data.datasets[0].data = values;
      salesChartInstance.update();
      return;
    }

    salesChartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'درآمد (تومان)',
          data: values,
          backgroundColor: 'rgba(59, 130, 246, 0.75)',
          hoverBackgroundColor: 'rgba(96, 165, 250, 1)',
          borderRadius: 6,
          borderSkipped: false,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            rtl: true,
            textDirection: 'rtl',
            callbacks: {
              label: (ctx) => `${formatNumber(ctx.raw)} تومان`
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: isDark ? '#cbd5e1' : '#0f172a', font: { family: 'Vazirmatn', size: 9 } }
          },
          y: {
            beginAtZero: true,
            grid: { color: isDark ? 'rgba(51, 65, 85, 0.3)' : 'rgba(203, 213, 225, 0.7)' },
            ticks: {
              color: isDark ? '#cbd5e1' : '#0f172a',
              font: { family: 'Vazirmatn', size: 9 },
              callback: (val) => val >= 1000000 ? `${(val/1000000).toFixed(1)}M` : (val >= 1000 ? `${(val/1000).toFixed(0)}K` : val)
            }
          }
        }
      }
    });
  }

  let monthlySalesChartInstance = null;
  function renderAdminMonthlySalesChart(labels, values, totalSum) {
    const canvas = $('adminMonthlySalesChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const total = totalSum != null ? totalSum : (values || []).reduce((a, b) => a + b, 0);
    const totalEl = $('monthlySalesChartTotal');
    if (totalEl) totalEl.innerHTML = `<span class="font-mono font-bold">${formatNumber(total)}</span> <span>تومان</span>`;

    if (monthlySalesChartInstance) {
      monthlySalesChartInstance.data.labels = labels || [];
      monthlySalesChartInstance.data.datasets[0].data = values || [];
      monthlySalesChartInstance.update();
      return;
    }

    const gradient = ctx.createLinearGradient(0, 0, 0, 140);
    gradient.addColorStop(0, 'rgba(16, 185, 129, 0.40)');
    gradient.addColorStop(1, 'rgba(16, 185, 129, 0.0)');

    monthlySalesChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels || [],
        datasets: [{
          label: 'فروش ۳۰ روزه (تومان)',
          data: values || [],
          borderColor: '#10b981',
          borderWidth: 2,
          backgroundColor: gradient,
          fill: true,
          tension: 0.35,
          pointRadius: (ctx) => ((labels || []).length > 15 ? 1 : 2),
          pointHoverRadius: 5,
          pointBackgroundColor: '#34d399',
          pointBorderColor: isDark ? '#0f172a' : '#ffffff',
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            rtl: true,
            textDirection: 'rtl',
            callbacks: {
              label: (ctx) => `${formatNumber(ctx.raw)} تومان`
            }
          }
        },
        scales: {
          x: {
            grid: { display: true, color: isDark ? 'rgba(51, 65, 85, 0.25)' : 'rgba(148, 163, 184, 0.45)' },
            ticks: {
              color: isDark ? '#cbd5e1' : '#0f172a',
              font: { family: 'Vazirmatn', size: 9 },
              maxTicksLimit: 10,
            }
          },
          y: {
            beginAtZero: true,
            grid: { color: isDark ? 'rgba(51, 65, 85, 0.3)' : 'rgba(148, 163, 184, 0.45)' },
            ticks: {
              color: isDark ? '#cbd5e1' : '#0f172a',
              font: { family: 'Vazirmatn', size: 9 },
              callback: (val) => val >= 1000000 ? `${(val/1000000).toFixed(1)}M` : (val >= 1000 ? `${(val/1000).toFixed(0)}K` : val)
            }
          }
        }
      }
    });
  }

  let trafficChartInstance = null;
  function renderAdminTrafficChart(labels, values, totalGb, todayGb) {
    const canvas = $('adminTrafficChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const currentToday = Number(todayGb || (values && values[values.length - 1]) || 0);
    const totalEl = $('trafficChartTotal');
    if (totalEl) {
      totalEl.innerHTML = `<span dir="ltr" class="inline-flex items-baseline gap-1"><span class="font-bold text-cyan-300 font-mono text-xs">${formatNumber(totalGb || currentToday || 0)}</span> <span class="text-[9px] text-cyan-300 font-sans">GB</span></span>`;
    }

    if (trafficChartInstance) {
      trafficChartInstance.data.labels = labels;
      trafficChartInstance.data.datasets[0].data = values;
      trafficChartInstance.update();
      return;
    }

    const gradient = ctx.createLinearGradient(0, 0, 0, 140);
    gradient.addColorStop(0, 'rgba(6, 182, 212, 0.45)');
    gradient.addColorStop(1, 'rgba(6, 182, 212, 0.0)');

    trafficChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'مصرف ترافیک (GB)',
          data: values,
          borderColor: '#06b6d4',
          borderWidth: 2.5,
          backgroundColor: gradient,
          fill: true,
          tension: 0.35,
          pointBackgroundColor: '#22d3ee',
          pointBorderColor: isDark ? '#0f172a' : '#ffffff',
          pointBorderWidth: 1.5,
          pointRadius: 3.5,
          pointHoverRadius: 5.5,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            rtl: true,
            textDirection: 'rtl',
            callbacks: {
              label: (ctx) => `مصرف: \u200E${formatNumber(ctx.raw)} GB`
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: isDark ? '#cbd5e1' : '#0f172a', font: { family: 'Vazirmatn', size: 9 } }
          },
          y: {
            beginAtZero: true,
            grid: { color: isDark ? 'rgba(51, 65, 85, 0.3)' : 'rgba(203, 213, 225, 0.7)' },
            ticks: {
              color: isDark ? '#cbd5e1' : '#0f172a',
              font: { family: 'Vazirmatn', size: 9 },
              callback: (val) => `\u200E${val} GB`
            }
          }
        }
      }
    });
  }

  function createDoughnutLegendLabels() {
    return {
      usePointStyle: true,
      pointStyle: 'circle',
      boxWidth: 7,
      boxHeight: 7,
      padding: 10,
      color: () => {
        const curIsDark = document.documentElement.classList.contains('dark') || !document.documentElement.classList.contains('theme-light');
        return curIsDark ? '#f8fafc' : '#0f172a';
      },
      font: { family: 'Vazirmatn', size: 10, weight: '600' },
      generateLabels: (chart) => {
        const data = chart.data;
        if (!data.labels?.length || !data.datasets?.length) return [];
        const dataset = data.datasets[0];
        const curIsDark = document.documentElement.classList.contains('dark') || !document.documentElement.classList.contains('theme-light');
        const textColor = curIsDark ? '#f8fafc' : '#0f172a';
        return data.labels.map((label, i) => {
          const fill = Array.isArray(dataset.backgroundColor) ? dataset.backgroundColor[i] : dataset.backgroundColor;
          return {
            text: label,
            fontColor: textColor,
            color: textColor,
            fillStyle: fill,
            strokeStyle: fill,
            lineWidth: 0,
            pointStyle: 'circle',
            hidden: isNaN(dataset.data[i]) || chart.getDataVisibility(i) === false,
            index: i,
            datasetIndex: 0
          };
        });
      }
    };
  }

  let locationChartInstance = null;
  function renderAdminLocationChart(locationShare) {
    const canvas = $('adminLocationChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const hasData = Boolean(locationShare?.has_data && locationShare?.data?.length && locationShare.data.some(v => v > 0));
    const labels = hasData
      ? (locationShare.labels || []).map(l => (l || '').replace(/[A-Za-z0-9_-]+/g, '').trim() || l || '🌐')
      : ['بدون مصرف'];
    const values = hasData ? locationShare.data : [1];
    const unit = locationShare?.unit || 'GB';
    const bgColors = hasData ? [
      'rgba(139, 92, 246, 0.85)',
      'rgba(6, 182, 212, 0.85)',
      'rgba(16, 185, 129, 0.85)',
      'rgba(245, 158, 11, 0.85)',
      'rgba(244, 63, 94, 0.85)',
      'rgba(99, 102, 241, 0.85)',
    ] : ['rgba(100, 116, 139, 0.4)'];

    if (locationChartInstance) {
      locationChartInstance.data.labels = labels;
      locationChartInstance.data.datasets[0].data = values;
      locationChartInstance.data.datasets[0].backgroundColor = bgColors;
      locationChartInstance.update();
      return;
    }

    locationChartInstance = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: bgColors,
          borderWidth: 0,
          borderColor: 'transparent',
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        plugins: {
          legend: {
            position: 'bottom',
            rtl: true,
            textDirection: 'rtl',
            labels: createDoughnutLegendLabels()
          },
          tooltip: {
            rtl: true,
            textDirection: 'rtl',
            callbacks: {
              label: (ctx) => hasData ? `${ctx.label}: ${formatNumber(ctx.raw)} ${unit}` : 'داده‌ای برای سرورها ثبت نشده است'
            }
          }
        }
      }
    });
  }

  let hourlyChartInstance = null;
  function renderAdminHourlyChart(hourlyDist) {
    const canvas = $('adminHourlyChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const labels = hourlyDist?.labels || [];
    const values = hourlyDist?.data || [];
    const peakBadge = $('peakHourBadge');
    if (peakBadge) {
      if (hourlyDist?.is_real_telemetry && hourlyDist?.peak_hour) {
        peakBadge.innerText = `Peak: ${hourlyDist.peak_hour}`;
      } else if (hourlyDist?.is_real_telemetry) {
        peakBadge.innerText = `تله‌متری زنده`;
      } else {
        peakBadge.innerText = `در حال ثبت اسنپ‌شات`;
      }
    }

    if (hourlyChartInstance) {
      hourlyChartInstance.data.labels = labels;
      hourlyChartInstance.data.datasets[0].data = values;
      hourlyChartInstance.update();
      return;
    }

    const gradient = ctx.createLinearGradient(0, 0, 0, 140);
    gradient.addColorStop(0, 'rgba(245, 158, 11, 0.40)');
    gradient.addColorStop(1, 'rgba(245, 158, 11, 0.0)');

    hourlyChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'مصرف ساعتی (GB)',
          data: values,
          borderColor: '#f59e0b',
          borderWidth: 2,
          backgroundColor: gradient,
          fill: true,
          tension: 0.38,
          pointRadius: 1.5,
          pointHoverRadius: 4.5,
          pointBackgroundColor: '#fbbf24',
          pointBorderColor: isDark ? '#0f172a' : '#ffffff',
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => `ساعت ${ctx.label}: ${formatNumber(ctx.raw)} GB`
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: isDark ? '#cbd5e1' : '#0f172a',
              font: { family: 'Vazirmatn', size: 8 },
              maxTicksLimit: 12,
            }
          },
          y: {
            beginAtZero: true,
            grid: { color: isDark ? 'rgba(51, 65, 85, 0.3)' : 'rgba(203, 213, 225, 0.7)' },
            ticks: {
              color: isDark ? '#cbd5e1' : '#0f172a',
              font: { family: 'Vazirmatn', size: 9 },
              callback: (val) => `${val}G`
            }
          }
        }
      }
    });
  }

  let retentionChartInstance = null;
  function renderAdminRetentionChart(retentionTrend) {
    const canvas = $('adminRetentionChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const labels = retentionTrend?.labels || [];
    const newSales = retentionTrend?.new_sales || [];
    const renewalSales = retentionTrend?.renewal_sales || [];

    if (retentionChartInstance) {
      retentionChartInstance.data.labels = labels;
      retentionChartInstance.data.datasets[0].data = newSales;
      retentionChartInstance.data.datasets[1].data = renewalSales;
      retentionChartInstance.update();
      return;
    }

    retentionChartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'کاربر جدید',
            data: newSales,
            backgroundColor: 'rgba(16, 185, 129, 0.85)',
            hoverBackgroundColor: 'rgba(52, 211, 153, 1)',
            borderRadius: 4,
            borderSkipped: false,
          },
          {
            label: 'تمدید اشتراک',
            data: renewalSales,
            backgroundColor: 'rgba(59, 130, 246, 0.85)',
            hoverBackgroundColor: 'rgba(96, 165, 250, 1)',
            borderRadius: 4,
            borderSkipped: false,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${formatNumber(ctx.raw)} کاربر`
            }
          }
        },
        scales: {
          x: {
            stacked: true,
            grid: { display: false },
            ticks: { color: isDark ? '#cbd5e1' : '#0f172a', font: { family: 'Vazirmatn', size: 9 } }
          },
          y: {
            stacked: true,
            beginAtZero: true,
            grid: { color: isDark ? 'rgba(51, 65, 85, 0.3)' : 'rgba(203, 213, 225, 0.7)' },
            ticks: {
              color: isDark ? '#cbd5e1' : '#0f172a',
              font: { family: 'Vazirmatn', size: 9 },
              precision: 0,
            }
          }
        }
      }
    });
  }

  function formatPlanLabelWithIconFirst(label) {
    if (!label) return '\u200E💎 پلن';
    const str = String(label).trim();
    const emojiRegex = /(\p{Extended_Pictographic}|\p{Emoji_Presentation})/gu;
    const matches = str.match(emojiRegex);
    const cleanText = str.replace(emojiRegex, '').trim();
    const icons = (matches && matches.length > 0) ? matches.join('') : '💎';
    return cleanText ? `\u200E${icons} ${cleanText}` : icons;
  }

  let planSalesChartInstance = null;
  function renderAdminPlanSalesChart(planDist) {
    const canvas = $('adminPlanSalesChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const hasSales = Boolean(planDist?.has_data ?? (planDist?.sales_count && planDist.sales_count.some(c => c > 0)));
    const labels = hasSales
      ? (planDist.labels || []).map(formatPlanLabelWithIconFirst)
      : ['بدون سفارش ثبت‌شده'];
    const values = hasSales ? planDist.sales_count : [1];
    const bgColors = hasSales ? [
      'rgba(236, 72, 153, 0.85)',
      'rgba(168, 85, 247, 0.85)',
      'rgba(99, 102, 241, 0.85)',
      'rgba(6, 182, 212, 0.85)',
      'rgba(16, 185, 129, 0.85)',
    ] : ['rgba(100, 116, 139, 0.4)'];

    if (planSalesChartInstance) {
      planSalesChartInstance.data.labels = labels;
      planSalesChartInstance.data.datasets[0].data = values;
      planSalesChartInstance.data.datasets[0].backgroundColor = bgColors;
      planSalesChartInstance.update();
      return;
    }

    planSalesChartInstance = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: bgColors,
          borderWidth: 0,
          borderColor: 'transparent',
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '66%',
        plugins: {
          legend: {
            position: 'bottom',
            rtl: true,
            textDirection: 'rtl',
            labels: createDoughnutLegendLabels()
          },
          tooltip: {
            rtl: true,
            textDirection: 'rtl',
            callbacks: {
              label: (ctx) => hasSales ? `${ctx.label}: ${formatNumber(ctx.raw)} سفارش` : 'سفارشی برای پلن‌ها ثبت نشده است'
            }
          }
        }
      }
    });
  }

  // OS & Platform Share Chart
  let platformChartInstance = null;
  function renderAdminPlatformChart(platformDist) {
    const canvas = $('adminPlatformChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const labels = platformDist?.labels || ['اندروید (Android)', 'آیفون (iOS)', 'ویندوز (Windows)', 'مک و لینوکس', 'سایر'];
    const values = platformDist?.data || [0, 0, 0, 0, 0];

    const platformColors = [
      'rgba(16, 185, 129, 0.9)', // Android: Emerald Green
      'rgba(99, 102, 241, 0.9)', // iPhone (iOS): Royal Indigo / Blue
      'rgba(245, 158, 11, 0.9)', // Windows: Amber / Vibrant Orange
      'rgba(244, 63, 94, 0.9)',  // macOS / Linux: Rose / Coral
      'rgba(6, 182, 212, 0.9)',  // Other: Cyan
    ];

    if (platformChartInstance) {
      platformChartInstance.data.labels = labels;
      platformChartInstance.data.datasets[0].data = values;
      platformChartInstance.data.datasets[0].backgroundColor = platformColors;
      platformChartInstance.update();
      return;
    }

    platformChartInstance = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: platformColors,
          borderWidth: 0,
          borderColor: 'transparent',
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '66%',
        plugins: {
          legend: {
            position: 'bottom',
            rtl: true,
            textDirection: 'rtl',
            labels: createDoughnutLegendLabels()
          },
          tooltip: {
            rtl: true,
            textDirection: 'rtl',
            callbacks: {
              label: (ctx) => `${ctx.label}: ${formatNumber(ctx.raw)} دستگاه`
            }
          }
        }
      }
    });
  }

  // Payment Methods Breakdown Chart (Card-to-card vs Crypto)
  let paymentChartInstance = null;
  function renderAdminPaymentChart(paymentDist) {
    const canvas = $('adminPaymentChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const labels = paymentDist?.labels || ['کارت به کارت (ریالی)', 'ارز دیجیتال (کریپتو / TON)', 'تلگرام استارز (XTR)'];
    const values = paymentDist?.counts || [0, 0, 0];
    const volumes = paymentDist?.volumes || [0, 0, 0];

    const chartColors = [
      'rgba(6, 182, 212, 0.85)',
      'rgba(168, 85, 247, 0.85)',
      'rgba(250, 204, 21, 0.85)',
    ];

    if (paymentChartInstance) {
      paymentChartInstance.data.labels = labels;
      paymentChartInstance.data.datasets[0].data = values;
      paymentChartInstance.data.datasets[0].backgroundColor = chartColors.slice(0, labels.length);
      paymentChartInstance.update();
      return;
    }

    paymentChartInstance = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: chartColors.slice(0, labels.length),
          borderWidth: 0,
          borderColor: 'transparent',
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '66%',
        plugins: {
          legend: {
            position: 'bottom',
            rtl: true,
            textDirection: 'rtl',
            labels: createDoughnutLegendLabels()
          },
          tooltip: {
            rtl: true,
            textDirection: 'rtl',
            callbacks: {
              label: (ctx) => {
                const vol = volumes[ctx.dataIndex] || 0;
                return `${ctx.label}: ${formatNumber(ctx.raw)} تراکنش (${formatNumber(vol)} تومان)`;
              }
            }
          }
        }
      }
    });
  }

  // Retention & Churn Rate Chart
  let churnChartInstance = null;
  function renderAdminRetentionStatsChart(retentionStats) {
    const canvas = $('adminChurnChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const labels = retentionStats?.labels || ['تمدید شده (مشتریان وفادار)', 'دوره اول (فعال)', 'ریزش (عدم تمدید)'];
    const values = retentionStats?.data || [0, 0, 0];
    const retRate = retentionStats?.retention_rate !== undefined ? retentionStats.retention_rate : 0;

    const badge = $('churnRateBadge');
    if (badge) badge.innerText = `تمدید: ${retRate}%`;

    if (churnChartInstance) {
      churnChartInstance.data.labels = labels;
      churnChartInstance.data.datasets[0].data = values;
      churnChartInstance.update();
      return;
    }

    churnChartInstance = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: [
            'rgba(99, 102, 241, 0.85)',
            'rgba(16, 185, 129, 0.85)',
            'rgba(244, 63, 94, 0.85)',
          ],
          borderWidth: 0,
          borderColor: 'transparent',
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '66%',
        plugins: {
          legend: {
            position: 'bottom',
            rtl: true,
            textDirection: 'rtl',
            labels: createDoughnutLegendLabels()
          },
          tooltip: {
            rtl: true,
            textDirection: 'rtl',
            callbacks: {
              label: (ctx) => `${ctx.label}: ${formatNumber(ctx.raw)} کاربر`
            }
          }
        }
      }
    });
  }

  // HWID Inspector Distribution & Account Sharing Risk Chart
  let hwidChartInstance = null;
  function renderAdminHwidChart(hwidDist) {
    const canvas = $('adminHwidChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const labels = hwidDist?.labels || ['1 دستگاه', '2 دستگاه', '3+ دستگاه', 'ریسک بالا (4+)'];
    const values = hwidDist?.data || [0, 0, 0, 0];
    const riskCount = hwidDist?.high_risk_count || 0;

    const badge = $('hwidRiskBadge');
    if (badge) {
      badge.innerText = riskCount > 0 ? `⚠️ ${riskCount} کاربر پرخطر` : 'توزیع HWID';
      if (riskCount > 0) {
        badge.className = 'text-[10px] text-rose-400 font-bold font-mono animate-pulse';
      }
    }

    if (hwidChartInstance) {
      hwidChartInstance.data.labels = labels;
      hwidChartInstance.data.datasets[0].data = values;
      hwidChartInstance.update();
      return;
    }

    const { grid: gridColor, tick: tickColor } = getThemeColors();

    hwidChartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'تعداد کاربران',
          data: values,
          backgroundColor: [
            'rgba(16, 185, 129, 0.8)',
            'rgba(59, 130, 246, 0.8)',
            'rgba(245, 158, 11, 0.8)',
            'rgba(244, 63, 94, 0.85)',
          ],
          borderRadius: 6,
          borderSkipped: false,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            rtl: true,
            textDirection: 'rtl',
            callbacks: {
              label: (ctx) => `${ctx.label}: ${formatNumber(ctx.raw)} کاربر`
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: tickColor,
              font: { family: 'Vazirmatn', size: 9.5, weight: '500' },
            }
          },
          y: {
            grid: { color: gridColor },
            ticks: {
              color: tickColor,
              font: { family: 'Vazirmatn', size: 9.5, weight: '500' },
              precision: 0,
            }
          }
        }
      }
    });
  }

  // Collapsible Accordion Node Card Renderer
  function renderOverviewNodes(nodes) {
    const container = $('adminOverviewNodesList');
    if (!container) return;
    if (!nodes || nodes.length === 0) {
      container.innerHTML = '<div class="p-3 text-center text-slate-400">هیچ نودی یافت نشد</div>';
      return;
    }

    container.innerHTML = nodes.map((n, idx) => {
      const flag = n.flag || getFlagEmoji(n.country_code);
      const isOnline = (n.status || '').toUpperCase() === 'ONLINE';
      const statusColor = isOnline ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400';
      const statusBadge = isOnline
        ? '<span class="inline-flex items-center gap-1 text-[10px] font-bold bg-transparent text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-lg"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>آنلاین</span>'
        : '<span class="inline-flex items-center gap-1 text-[10px] font-bold bg-transparent text-rose-600 dark:text-rose-400 border border-rose-500/30 px-2 py-0.5 rounded-lg"><span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>آفلاین</span>';

      const cpuText = (n.cpu_percent && n.cpu_percent > 0) ? `CPU: ${n.cpu_percent}%` : null;
      const ramText = (n.ram_percent && n.ram_percent > 0) ? `RAM: ${n.ram_percent}%` : null;
      const dlSpeed = Number(n.download_speed || 0);
      const ulSpeed = Number(n.upload_speed || 0);
      const speedText = (dlSpeed > 0 || ulSpeed > 0) ? `↓${formatSpeed(dlSpeed)} ↑${formatSpeed(ulSpeed)}` : null;
      const specs = [cpuText, ramText, speedText].filter(Boolean).join(' | ');

      return `
        <div class="bg-slate-900/70 rounded-2xl border border-slate-700/60 overflow-hidden transition shadow-sm">
          <!-- Accordion Header -->
          <div class="p-3 flex justify-between items-center cursor-pointer hover:bg-slate-800/40 transition select-none" onclick="window.toggleNodeAccordion(${idx})">
            <div class="flex items-center gap-2.5">
              <span class="text-xl flex-shrink-0">${flag}</span>
              <div>
                <span class="font-bold text-white block text-xs">${escapeHtml(n.name || 'Node')}</span>
                ${specs ? `<span class="text-[10px] text-slate-400 font-mono">${specs}</span>` : ''}
              </div>
            </div>
            <div class="flex items-center gap-2">
              <span class="${statusColor} font-bold text-[11px] font-mono">${formatNumber(n.connected_users || 0)} آنلاین</span>
              <span id="nodeChevron_${idx}" class="text-xs text-slate-400 transition-transform duration-200">▼</span>
            </div>
          </div>

          <!-- Accordion Details Body -->
          <div id="nodeBody_${idx}" class="hidden p-3 bg-slate-950/60 border-t border-slate-800/60 text-xs space-y-2">
            <div class="grid grid-cols-2 gap-2 text-[11px]">
              <div class="bg-slate-900/80 p-2 rounded-xl">
                <span class="text-slate-400 text-[10px] block mb-0.5">آدرس سرور:</span>
                <span class="font-mono text-cyan-300 text-xs block truncate" dir="ltr">${escapeHtml(n.address || '—')}</span>
              </div>
              <div class="bg-slate-900/80 p-2 rounded-xl">
                <span class="text-slate-400 text-[10px] block mb-0.5">وضعیت اتصال:</span>
                <span>${statusBadge}</span>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-2 text-[11px]">
              <div class="bg-slate-900/80 p-2 rounded-xl">
                <span class="text-slate-400 text-[10px] block mb-0.5">کاربران متصل زنده:</span>
                <b class="text-emerald-400 font-mono text-xs">${formatNumber(n.connected_users || 0)} نفر</b>
              </div>
              <div class="bg-slate-900/80 p-2 rounded-xl">
                <span class="text-slate-400 text-[10px] block mb-0.5">ترافیک مصرفی نود:</span>
                <b class="text-cyan-400 font-mono text-xs" dir="ltr">${n.traffic_used_gb ? n.traffic_used_gb + ' GB' : '—'}</b>
              </div>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  window.toggleNodeAccordion = (idx) => {
    const body = $(`nodeBody_${idx}`);
    const chev = $(`nodeChevron_${idx}`);
    if (body) {
      body.classList.toggle('hidden');
      if (chev) {
        chev.style.transform = body.classList.contains('hidden') ? 'rotate(0deg)' : 'rotate(180deg)';
      }
    }
    if (window.hapticFeedback) window.hapticFeedback('impact');
  };

  let cachedSslHealthItems = [];

  async function fetchAdminSslHealth() {
    const container = $('adminSslHealthList');
    if (!container) return;
    try {
      const res = await window.api.getSslHealth();
      if (res && res.ok && Array.isArray(res.data)) {
        cachedSslHealthItems = res.data;
        renderSslHealth(cachedSslHealthItems);
      } else {
        container.innerHTML = '<div class="p-3 text-center text-xs text-rose-400">خطا در دریافت وضعیت گواهی‌های SSL</div>';
      }
    } catch (err) {
      console.error('SSL Health fetch error:', err);
      container.innerHTML = '<div class="p-3 text-center text-xs text-rose-400">عدم برقراری ارتباط با سرور</div>';
    }
  }

  function renderSslHealth(items) {
    const container = $('adminSslHealthList');
    if (!container) return;
    if (!items || items.length === 0) {
      container.innerHTML = '<div class="p-4 text-center text-xs text-slate-400">هیچ دامنه‌ای برای پایش ثبت نشده است. از کادر بالا دامنه جدید اضافه کنید.</div>';
      return;
    }

    container.innerHTML = items.map(item => {
      let badgeHtml = '';
      const expiryDateFa = item.expires_at_jalali || (item.expires_at && typeof formatDateToJalali === 'function' ? formatDateToJalali(item.expires_at) : (item.expires_at || '—'));

      if (item.is_ip) {
        badgeHtml = '<span class="text-[10px] text-slate-400 font-mono">IP سرور</span>';
      } else if (item.valid) {
        if (item.status === 'ok') {
          badgeHtml = `<span class="text-[11px] font-bold text-emerald-400">معتبر (${item.days_left} روز)</span>`;
        } else if (item.status === 'warning') {
          badgeHtml = `<span class="text-[11px] font-bold text-amber-400">هشدار (${item.days_left} روز)</span>`;
        } else if (item.status === 'critical') {
          badgeHtml = `<span class="text-[11px] font-bold text-rose-400 animate-pulse">فوری (${item.days_left} روز)</span>`;
        } else {
          badgeHtml = `<span class="text-[11px] font-bold text-rose-400">منقضی شده</span>`;
        }
      } else {
        badgeHtml = `<span class="text-[11px] font-bold text-rose-400">خطا / قطع</span>`;
      }

      const deleteBtnHtml = item.is_custom
        ? `<button onclick="window.adminActions.deleteSslDomain('${escapeHtml(item.domain)}')" class="p-1.5 rounded-xl bg-slate-800/80 hover:bg-rose-500/15 text-rose-400 hover:text-rose-300 border border-slate-700/70 hover:border-rose-500/30 transition active:scale-95 flex-shrink-0 flex items-center justify-center" title="حذف دامنه">
             <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
           </button>`
        : '';

      let detailsHtml = '';
      if (item.is_ip) {
        detailsHtml = `
          <div class="text-[10px] text-slate-500">
            <span>آدرس IP مستقیم (بدون گواهی SSL دامنه)</span>
          </div>`;
      } else if (item.valid) {
        detailsHtml = `
          <div class="space-y-1 text-slate-300 text-[10.5px]">
            <div class="flex items-center gap-1.5">
              <span class="text-slate-400">مرجع :</span>
              <span class="font-medium text-slate-200">${escapeHtml(item.issuer || 'نامشخص')}</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="text-slate-400">تاریخ انقضا :</span>
              <span class="font-mono text-slate-200" dir="ltr">${expiryDateFa}</span>
            </div>
          </div>`;
      } else {
        detailsHtml = `
          <div class="text-[10.5px] text-rose-400/90 leading-relaxed">
            ${escapeHtml(item.error || 'ارتباط با پورت SSL برقرار نشد')}
          </div>`;
      }

      return `
        <div class="p-3.5 rounded-2xl bg-slate-900/60 border border-slate-700/60 flex flex-col gap-2.5 transition hover:border-slate-600/70 shadow-sm">
          <!-- Row 1: Right = Status / Days Left, Left = Domain Name (with status dot on its left) -->
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center flex-shrink-0">
              ${badgeHtml}
            </div>
            <div class="text-left min-w-0 flex items-center gap-2" dir="ltr">
              <span class="w-2 h-2 rounded-full ${item.valid ? (item.status === 'ok' ? 'bg-emerald-400' : 'bg-amber-400') : (item.is_ip ? 'bg-slate-500' : 'bg-rose-500')} flex-shrink-0"></span>
              <span class="font-mono text-xs font-semibold text-slate-100 select-all break-all leading-normal" title="${escapeHtml(item.domain)}">${escapeHtml(item.domain)}</span>
            </div>
          </div>

          <!-- Row 2: Right = Issuer & Jalali Expiration (زیر هم), Left = Delete Button -->
          <div class="flex items-end justify-between pt-2 border-t border-slate-800/80 gap-2">
            ${detailsHtml}
            ${deleteBtnHtml}
          </div>
        </div>
      `;
    }).join('');
  }

  function renderFullNodes(nodes) {
    const container = $('adminNodesFullList');
    if (!container) return;
    if (!nodes || nodes.length === 0) {
      container.innerHTML = '<div class="p-8 text-center text-slate-400 text-xs">هیچ سروری در کلاستر یافت نشد.</div>';
      return;
    }

    container.innerHTML = nodes.map((n, idx) => {
      const flag = n.flag || getFlagEmoji(n.country_code);
      const isOnline = (n.status || '').toUpperCase() === 'ONLINE';
      const statusBadge = isOnline ? 'آنلاین' : 'آفلاین';
      const statusBorder = isOnline ? 'border-emerald-500/30 text-emerald-600 dark:text-emerald-400' : 'border-rose-500/30 text-rose-600 dark:text-rose-400';

      const cpu = Number(n.cpu_percent || 0);
      const ram = Number(n.ram_percent || 0);
      const dlSpeed = Number(n.download_speed || 0);
      const ulSpeed = Number(n.upload_speed || 0);

      const cpuBarColor = cpu > 85 ? 'bg-rose-500' : (cpu > 60 ? 'bg-amber-500' : 'bg-cyan-500');
      const ramBarColor = ram > 85 ? 'bg-rose-500' : (ram > 60 ? 'bg-amber-500' : 'bg-indigo-500');

      const cpuDisplay = isOnline ? (cpu > 0 ? (cpu % 1 === 0 ? cpu : cpu.toFixed(1)) + '%' : '< 1%') : 'آفلاین';
      const ramDisplay = isOnline ? (ram > 0 ? (ram % 1 === 0 ? ram : ram.toFixed(1)) + '%' : '< 1%') : 'آفلاین';

      const shamsiDate = n.due_date_jalali || n.due_date;
      let dueBadgeHtml = '<span class="text-slate-500 font-medium">ثبت‌نشده</span>';
      if (n.days_until_due !== null && n.days_until_due !== undefined) {
        if (n.days_until_due < 0) {
          dueBadgeHtml = `<span class="bg-rose-500/15 text-rose-400 border border-rose-500/30 px-2 py-0.5 rounded-lg font-bold">⚠️ منقضی (${Math.abs(n.days_until_due)} روز پیش - ${shamsiDate})</span>`;
        } else if (n.days_until_due === 0) {
          dueBadgeHtml = `<span class="bg-rose-500/20 text-rose-400 border border-rose-500/40 px-2 py-0.5 rounded-lg font-bold animate-pulse">⚠️ سررسید امروز! (${shamsiDate})</span>`;
        } else if (n.days_until_due <= 3) {
          dueBadgeHtml = `<span class="bg-amber-500/15 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-lg font-bold">⏳ ${n.days_until_due} روز تا تمدید (${shamsiDate})</span>`;
        } else {
          dueBadgeHtml = `<span class="bg-slate-800 text-slate-300 border border-slate-700 px-2 py-0.5 rounded-lg font-mono">🗓️ ${escapeHtml(shamsiDate)} (${n.days_until_due} روز)</span>`;
        }
      }

      const boxId = `nodeBox_${n.id || idx}`;

      return `
        <div class="node-card settings-box bg-slate-800/90 rounded-2xl border border-slate-700/80 shadow-md relative overflow-hidden transition-all">
          <!-- Top Accent Light -->
          <div class="absolute top-0 right-0 left-0 h-[2px] ${isOnline ? 'bg-gradient-to-r from-emerald-500/0 via-emerald-400/50 to-emerald-500/0' : 'bg-gradient-to-r from-rose-500/0 via-rose-500/40 to-rose-500/0'}"></div>

          <!-- Header: Flag, Name, Status & Chevron (Clickable) -->
          <div class="node-header p-3.5 flex justify-between items-center cursor-pointer select-none hover:bg-slate-750/30 transition active:scale-[0.99]" onclick="window.adminActions.toggleSettingsBox('${boxId}')">
            <!-- Right: Flag and Server Name -->
            <div class="flex items-center gap-2.5 min-w-0">
              <span class="text-2xl flex-shrink-0 filter drop-shadow">${flag}</span>
              <h4 class="font-bold text-xs text-white truncate">${escapeHtml(n.name || 'Server Node')}</h4>
            </div>

            <!-- Left: Online Status + Speeds + Renewal Alert + Chevron Arrow -->
            <div class="flex items-center gap-2 flex-shrink-0">
              ${(n.days_until_due !== null && n.days_until_due <= 3) ? `
                <span class="text-[9px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-xl flex items-center gap-1">
                  <span>⏳</span>
                  <span>${n.days_until_due <= 0 ? 'سررسید!' : n.days_until_due + ' روز'}</span>
                </span>
              ` : ''}
              ${isOnline && (dlSpeed > 0 || ulSpeed > 0) ? `
                <div class="hidden sm:flex items-center gap-1.5 text-[9px] font-mono text-slate-300 bg-slate-900/60 px-2 py-0.5 rounded-xl border border-slate-700/60" dir="ltr">
                  <span class="text-emerald-400 font-bold">↓${formatSpeed(dlSpeed)}</span>
                  <span class="text-slate-600">|</span>
                  <span class="text-indigo-400 font-bold">↑${formatSpeed(ulSpeed)}</span>
                </div>
              ` : ''}
              <span class="text-[10px] font-bold font-sans ${statusBorder} bg-transparent px-2.5 py-1 rounded-xl border flex items-center gap-1.5">
                <span class="w-1.5 h-1.5 rounded-full ${isOnline ? 'bg-emerald-400' : 'bg-rose-400'}"></span>
                ${statusBadge}
              </span>
              <svg class="settings-box-chevron node-chevron w-4 h-4 text-slate-400 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
              </svg>
            </div>
          </div>

          <!-- Collapsible Body Details (Hidden by default, expands on click) -->
          <div id="${boxId}" class="node-body p-3.5 pt-2 border-t border-slate-700/60 space-y-3 hidden">
            <!-- Server Host Address Strip -->
            <div class="bg-transparent px-3 py-2 rounded-xl border border-slate-700/60 flex items-center justify-between text-xs">
              <span class="text-[10px] text-slate-400 flex items-center gap-1.5">
                <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"/></svg>
                <span>آدرس سرور:</span>
              </span>
              <span class="font-mono text-blue-600 dark:text-cyan-300 text-xs font-semibold truncate max-w-[210px] select-all" dir="ltr" title="${n.address || '—'}">${n.address || '—'}</span>
            </div>

            <!-- Real-time Speeds: Download & Upload -->
            <div class="grid grid-cols-2 gap-2 text-center text-[10px]">
              <div class="bg-transparent p-2.5 rounded-xl border border-slate-700/60">
                <div class="flex items-center justify-between text-[10px] mb-1">
                  <span class="text-slate-400 flex items-center gap-1">
                    <svg class="w-3 h-3 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7m0 0l-7-7m7 7V3"/></svg>
                    <span>سرعت دانلود (DL):</span>
                  </span>
                  <span class="text-[8px] text-slate-500 font-mono">RX</span>
                </div>
                <b class="text-emerald-400 font-mono text-xs block text-left" dir="ltr">↓ ${formatSpeed(dlSpeed)}</b>
              </div>
              <div class="bg-transparent p-2.5 rounded-xl border border-slate-700/60">
                <div class="flex items-center justify-between text-[10px] mb-1">
                  <span class="text-slate-400 flex items-center gap-1">
                    <svg class="w-3 h-3 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18"/></svg>
                    <span>سرعت آپلود (UL):</span>
                  </span>
                  <span class="text-[8px] text-slate-500 font-mono">TX</span>
                </div>
                <b class="text-indigo-400 font-mono text-xs block text-left" dir="ltr">↑ ${formatSpeed(ulSpeed)}</b>
              </div>
            </div>

            <!-- System Resource Gauges (CPU & RAM Progress Bars) -->
            <div class="space-y-2 bg-transparent p-2.5 rounded-xl border border-slate-700/50">
              <!-- CPU Progress -->
              <div class="space-y-1">
                <div class="flex justify-between items-center text-[10px]">
                  <span class="text-slate-400">پردازنده (CPU):</span>
                  <span class="font-mono font-bold ${cpu > 80 ? 'text-rose-400' : 'text-slate-100'}">${cpuDisplay}</span>
                </div>
                <div class="w-full h-1.5 bg-slate-700/60 rounded-full overflow-hidden">
                  <div class="h-full ${cpuBarColor} transition-all duration-500" style="width: ${Math.min(100, Math.max(0, isOnline ? (cpu > 0 ? cpu : 1) : 0))}%"></div>
                </div>
              </div>

              <!-- RAM Progress -->
              <div class="space-y-1">
                <div class="flex justify-between items-center text-[10px]">
                  <span class="text-slate-400">حافظه رم (RAM):</span>
                  <span class="font-mono font-bold ${ram > 80 ? 'text-rose-400' : 'text-slate-100'}">${ramDisplay}</span>
                </div>
                <div class="w-full h-1.5 bg-slate-700/60 rounded-full overflow-hidden">
                  <div class="h-full ${ramBarColor} transition-all duration-500" style="width: ${Math.min(100, Math.max(0, isOnline ? (ram > 0 ? ram : 1) : 0))}%"></div>
                </div>
              </div>
            </div>

            <!-- Bottom Metrics: Connected users & Traffic -->
            <div class="grid grid-cols-2 gap-2 text-center text-[10px]">
              <div class="bg-transparent p-2 rounded-xl border border-slate-700/60">
                <span class="text-slate-400 block mb-0.5">کاربران متصل</span>
                <b class="text-emerald-600 dark:text-emerald-400 font-mono text-xs">${formatNumber(n.connected_users || 0)} نفر</b>
              </div>
              <div class="bg-transparent p-2 rounded-xl border border-slate-700/60">
                <span class="text-slate-400 block mb-0.5">ترافیک مصرفی نود</span>
                <b class="text-blue-600 dark:text-cyan-400 font-mono text-xs" dir="ltr">${n.traffic_used_gb ? n.traffic_used_gb + ' GB' : '0 GB'}</b>
              </div>
            </div>

            <!-- Infra-Billing & Server Cost Details Strip -->
            <div class="bg-transparent p-2.5 rounded-xl border border-slate-700/60 space-y-2 text-[10px]">
              <div class="flex items-center justify-between">
                <span class="text-slate-400 flex items-center gap-1">
                  <svg class="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  <span>هزینه ماهانه سرور:</span>
                </span>
                <div class="flex items-center gap-1 font-bold">
                  ${n.monthly_cost_toman ? `
                    <span class="font-mono text-emerald-400">${formatNumber(n.monthly_cost_toman)}</span>
                    <span class="text-[9px] text-slate-400 font-sans">تومان</span>
                    ${n.monthly_cost_eur ? `<span class="text-indigo-300 font-mono text-[10px] mr-1">(${n.currency === 'USD' ? '$' : '€'}${n.monthly_cost_eur})</span>` : ''}
                  ` : '<span class="text-slate-500 font-medium">ثبت‌نشده</span>'}
                </div>
              </div>

              <div class="flex items-center justify-between">
                <span class="text-slate-400 flex items-center gap-1">
                  <svg class="w-3.5 h-3.5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                  <span>موعد سررسید تمدید:</span>
                </span>
                <div>${dueBadgeHtml}</div>
              </div>

              <div class="grid grid-cols-2 gap-2 pt-1 border-t border-slate-800 text-[10px]">
                <div>
                  <span class="text-slate-400 block mb-0.5">ارائه‌دهنده (هاست):</span>
                  <b class="text-cyan-300 truncate block">${n.provider || 'ثبت‌نشده'}</b>
                </div>
                <div>
                  <span class="text-slate-400 block mb-0.5">قیمت تمام‌شده هر گیگ:</span>
                  <b class="text-indigo-300 font-bold block">
                    ${n.cost_per_gb ? `
                      <span class="font-mono">${formatNumber(n.cost_per_gb)}</span>
                      <span class="text-[9px] text-slate-400 font-sans">تومان</span>
                    ` : '—'}
                  </b>
                </div>
              </div>

              <!-- Node Profit / Loss & Estimated Revenue Strip -->
              <div class="grid grid-cols-2 gap-2 pt-1 border-t border-slate-800 text-[10px]">
                <div>
                  <span class="text-slate-400 block mb-0.5">درآمد تخمینی نود:</span>
                  <b class="text-emerald-400 font-mono block">
                    ${n.est_revenue_toman ? `${formatNumber(n.est_revenue_toman)} <span class="text-[9px] text-slate-400 font-sans">تومان</span>` : '۰ تومان'}
                  </b>
                </div>
                <div>
                  <span class="text-slate-400 block mb-0.5">سود/زیان خالص:</span>
                  <b class="${n.is_profitable ? 'text-emerald-400' : 'text-rose-400'} font-bold block font-mono text-[10.5px]" dir="ltr">
                    ${(n.net_profit_toman || 0) > 0 ? '+' : ''}${formatNumber(n.net_profit_toman || 0)}${n.roi_percent !== null && n.roi_percent !== undefined ? ` (${n.roi_percent > 0 ? '+' : ''}${n.roi_percent}%)` : ''}
                  </b>
                </div>
              </div>

              <!-- Button to configure node billing -->
              <div class="pt-1">
                <button type="button" onclick="event.stopPropagation(); window.adminActions.openNodeBillingModal('${(n.uuid || n.id || '').replace(/'/g, "\\'")}', '${(n.name || '').replace(/'/g, "\\'")}', '${(n.provider || '').replace(/'/g, "\\'")}', ${Number(n.monthly_cost_toman || 0)}, ${Number(n.monthly_cost_eur || 0)}, '${n.due_date || ''}', '${(n.notes || '').replace(/'/g, "\\'")}', '${flag}', '${n.currency || 'EUR'}')" class="w-full bg-transparent hover:bg-cyan-500/10 text-cyan-500 dark:text-cyan-400 py-1.5 rounded-xl border border-cyan-500/30 transition flex items-center justify-center gap-1.5 font-bold active:scale-95 shadow-sm">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                  <span>مدیریت هزینه و تمدید سرور</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  // --- 5. Users Management ---
  async function fetchAdminUsers(page = 1) {
    currentPage = page;
    const listContainer = $('adminUsersList');
    if (!listContainer) return;
    listContainer.innerHTML = '<div class="p-8 text-center text-xs text-slate-400">در حال دریافت کاربران...</div>';

    try {
      const params = {
        page: page,
        limit: 15,
        filter: currentFilter,
      };
      if (currentSearch) params.q = currentSearch;

      const res = await window.api.getAdminUsers(params);
      if (!res || !res.ok) {
        listContainer.innerHTML = `<div class="p-6 text-center text-rose-400 text-xs">${res?.error || 'خطا در بارگذاری کاربران'}</div>`;
        return;
      }

      renderUsersList(res.users || []);

      // Pagination Controls with Dynamic Visibility
      const total = res.total || 0;
      const totalPages = Math.max(1, Math.ceil(total / 15));
      const paginationEl = $('adminUsersPagination');
      const pageInfo = $('adminUsersPageInfo');
      const prevBtn = $('adminUsersPrevBtn');
      const nextBtn = $('adminUsersNextBtn');

      if (paginationEl) {
        if (totalPages > 1) {
          paginationEl.classList.remove('hidden');
        } else {
          paginationEl.classList.add('hidden');
        }
      }

      if (pageInfo) {
        pageInfo.innerText = `صفحه ${formatNumber(page)} از ${formatNumber(totalPages)} (${formatNumber(total)} کاربر)`;
      }
      if (prevBtn) prevBtn.disabled = page <= 1;
      if (nextBtn) nextBtn.disabled = page >= totalPages;
    } catch (err) {
      listContainer.innerHTML = '<div class="p-6 text-center text-rose-400 text-xs">خطای شبکه در دریافت کاربران</div>';
    }
  }

  function renderUsersList(users) {
    window.currentAdminUsersList = users;
    const listContainer = $('adminUsersList');
    if (!listContainer) return;
    if (users.length === 0) {
      listContainer.innerHTML = '<div class="p-8 text-center text-xs text-slate-400">هیچ کاربری با این مشخصات یافت نشد.</div>';
      return;
    }

    listContainer.innerHTML = users.map(u => {
      // Prioritize real full_name; fallback to 'کاربر ID' if missing or starts with @
      const rawName = u.full_name || '';
      const displayName = (rawName && !rawName.startsWith('@')) ? rawName : `کاربر ${u.telegram_id}`;
      const initial = (displayName || String(u.telegram_id))[0].toUpperCase();
      const p = u.panel_account;

      let statusBadge = '<span class="px-1.5 py-0.5 rounded-lg text-[9px] bg-transparent border border-slate-400/30 text-slate-500 dark:text-slate-400 font-medium">بدون اکانت</span>';
      if (u.is_banned) {
        statusBadge = '<span class="px-1.5 py-0.5 rounded-lg text-[9px] bg-transparent text-rose-600 dark:text-rose-400 font-bold border border-rose-500/30">مسدود</span>';
      } else if (u.is_expired || (p && p.exists && (p.status || '').toUpperCase() === 'EXPIRED')) {
        statusBadge = '<span class="px-1.5 py-0.5 rounded-lg text-[9px] bg-transparent text-rose-600 dark:text-rose-400 font-bold border border-rose-500/30">منقضی</span>';
      } else if (p && p.exists) {
        const st = (p.status || '').toUpperCase();
        if (st === 'ACTIVE') statusBadge = '<span class="px-1.5 py-0.5 rounded-lg text-[9px] bg-transparent text-emerald-600 dark:text-emerald-400 font-bold border border-emerald-500/30">فعال</span>';
        else if (st === 'DISABLED') statusBadge = '<span class="px-1.5 py-0.5 rounded-lg text-[9px] bg-transparent text-amber-600 dark:text-amber-400 font-bold border border-amber-500/30">غیرفعال</span>';
        else statusBadge = `<span class="px-1.5 py-0.5 rounded-lg text-[9px] bg-transparent text-blue-600 dark:text-blue-400 font-bold border border-blue-500/30">${st}</span>`;
      }

      const isExpiring = u.is_expiring || (p && p.exists && !u.is_expired && ((p.days_left !== null && p.days_left > 0 && p.days_left <= 3) || (p.remaining_traffic_gb >= 0 && p.remaining_traffic_gb <= 2.0 && p.limit_traffic_gb > 0)));
      const expiringBadgeHtml = isExpiring
        ? '<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[9px] font-bold animate-pulse flex-shrink-0 whitespace-nowrap" title="هشدار: حجم یا زمان رو به اتمام است"><svg class="w-2.5 h-2.5 text-amber-300" fill="currentColor" viewBox="0 0 20 20"><path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zM10 18a3 3 0 01-3-3h6a3 3 0 01-3 3z"/></svg> رو به اتمام</span>'
        : '';

      let serviceLineHtml = `
        <div class="bg-transparent p-2.5 rounded-xl border border-dashed border-slate-700/60 flex items-center justify-center text-[11px] text-slate-400 gap-1.5">
          <span class="w-1.5 h-1.5 rounded-full bg-slate-500"></span>
          <span>فاقد اشتراک فعال در پنل</span>
        </div>
      `;
      if (p && p.exists) {
        const isUnlimited = !(p.limit_traffic_gb > 0);
        const limitGb = p.limit_traffic_gb || 0;
        const usedGb = p.used_traffic_gb !== undefined && p.used_traffic_gb !== null ? p.used_traffic_gb : 0;
        const remGb = p.remaining_traffic_gb !== undefined && p.remaining_traffic_gb >= 0 
          ? p.remaining_traffic_gb 
          : (limitGb > 0 ? Math.max(0, limitGb - usedGb) : 0);

        let percentUsed = 0;
        if (!isUnlimited && limitGb > 0) {
          percentUsed = Math.min(100, Math.max(0, Math.round((usedGb / limitGb) * 100)));
        }

        let barGradient = 'from-emerald-500 via-teal-400 to-cyan-400';
        let barGlow = 'shadow-[0_0_10px_rgba(52,211,153,0.35)]';
        let badgeColor = 'text-emerald-600 dark:text-emerald-400 bg-transparent border-emerald-500/30';
        let statusLabel = `${percentUsed}%`;

        if (isUnlimited) {
          barGradient = 'from-blue-500 to-indigo-500';
          barGlow = 'shadow-[0_0_10px_rgba(59,130,246,0.3)]';
          badgeColor = 'text-blue-600 dark:text-blue-400 bg-transparent border-blue-500/30';
          statusLabel = 'ترافیک نامحدود';
          percentUsed = 100;
        } else if (percentUsed >= 90) {
          barGradient = 'from-rose-500 to-red-500';
          barGlow = 'shadow-[0_0_10px_rgba(244,63,94,0.4)]';
          badgeColor = 'text-rose-600 dark:text-rose-400 bg-transparent border-rose-500/30';
          statusLabel = `${percentUsed}% (بحرانی)`;
        } else if (percentUsed >= 70) {
          barGradient = 'from-amber-500 to-orange-400';
          barGlow = 'shadow-[0_0_10px_rgba(245,158,11,0.35)]';
          badgeColor = 'text-amber-600 dark:text-amber-400 bg-transparent border-amber-500/30';
          statusLabel = `${percentUsed}%`;
        }

        const expireJalali = p.expire_jalali || (p.expire_at && typeof formatDateToJalali === 'function' ? formatDateToJalali(p.expire_at) : '');
        let timeText = 'نامحدود';
        let timeSub = 'بدون انقضا';
        let timeColor = 'text-indigo-600 dark:text-indigo-400';
        let timeBoxBorder = 'border-indigo-500/30';
        let timeBoxBg = 'bg-transparent';

        if (p.days_left !== undefined && p.days_left !== null) {
          if (p.days_left > 3) {
            timeText = `${formatNumber(p.days_left)} روز اعتبار`;
            timeSub = expireJalali ? `تا ${expireJalali}` : 'اعتبار فعال';
            timeColor = 'text-emerald-600 dark:text-emerald-400';
            timeBoxBorder = 'border-emerald-500/30';
            timeBoxBg = 'bg-transparent';
          } else if (p.days_left > 0) {
            timeText = `${formatNumber(p.days_left)} روز اعتبار`;
            timeSub = expireJalali ? `تا ${expireJalali}` : 'رو به اتمام';
            timeColor = 'text-amber-600 dark:text-amber-400';
            timeBoxBorder = 'border-amber-500/30';
            timeBoxBg = 'bg-transparent';
          } else {
            timeText = 'منقضی شده';
            timeSub = expireJalali ? `انقضا: ${expireJalali}` : 'پایان مهلت';
            timeColor = 'text-rose-600 dark:text-rose-400';
            timeBoxBorder = 'border-rose-500/30';
            timeBoxBg = 'bg-transparent';
          }
        }

        const remDisplay = isUnlimited ? 'نامحدود' : `${formatNumber(remGb)} GB`;
        const totalDisplay = isUnlimited ? 'نامحدود' : `${formatNumber(limitGb)} GB`;
        const usedDisplay = `${formatNumber(usedGb)} GB`;

        serviceLineHtml = `
          <div class="bg-transparent rounded-xl p-2.5 border border-slate-700/60 space-y-2">
            <!-- Glass Progress Bar & Top Metrics -->
            <div class="space-y-1">
              <div class="flex items-center justify-between text-[10px]">
                <div class="flex items-center gap-1 font-mono text-slate-300">
                  <span class="text-slate-400 text-[10px] font-sans">مصرف:</span>
                  <span dir="ltr" class="font-bold text-white dark:text-slate-100">${usedDisplay}</span>
                  <span class="text-slate-400 font-sans">از</span>
                  <span dir="ltr" class="text-slate-400 font-mono">${totalDisplay}</span>
                </div>
                <span class="px-1.5 py-0.5 rounded-md text-[9px] font-mono font-bold border ${badgeColor}">
                  ${statusLabel}
                </span>
              </div>
              <!-- Vercel-Style Glass Track -->
              <div class="w-full h-1.5 rounded-full bg-slate-800/40 p-[1px] border border-slate-700/40 overflow-hidden relative" dir="ltr">
                <div class="h-full rounded-full bg-gradient-to-r ${barGradient} ${barGlow} transition-all duration-500" style="width: ${percentUsed}%;"></div>
              </div>
            </div>

            <!-- Dual Metric Grid (گرید دوقلو بدون پس‌زمینه) -->
            <div class="grid grid-cols-2 gap-2 pt-1 border-t border-slate-800/80 text-[10px]">
              <!-- Column 1: Remaining Volume -->
              <div class="bg-transparent rounded-lg p-1.5 border border-slate-700/60 flex items-center gap-2">
                <div class="w-7 h-7 rounded-md bg-transparent border border-cyan-500/30 flex items-center justify-center text-cyan-500 dark:text-cyan-400 text-xs shrink-0">
                  ⚡
                </div>
                <div class="min-w-0 flex-1 leading-tight">
                  <span class="text-slate-400 text-[9px] block">حجم باقی‌مانده</span>
                  <span dir="ltr" class="font-mono font-bold text-cyan-600 dark:text-cyan-300 truncate block text-[11px]">
                    ${remDisplay}
                  </span>
                </div>
              </div>

              <!-- Column 2: Time & Expiration -->
              <div class="bg-transparent rounded-lg p-1.5 border border-slate-700/60 flex items-center gap-2">
                <div class="w-7 h-7 rounded-md bg-transparent border ${timeBoxBorder} flex items-center justify-center ${timeColor} text-xs shrink-0">
                  ⏳
                </div>
                <div class="min-w-0 flex-1 leading-tight">
                  <span class="text-slate-400 text-[9px] block truncate" title="${timeSub}">${timeSub}</span>
                  <span class="font-bold ${timeColor} truncate block text-[10px]">
                    ${timeText}
                  </span>
                </div>
              </div>
            </div>
          </div>
        `;
      }

      const avatarSrc = u.avatar_url || `/api/user/avatar?user_id=${u.telegram_id}`;

      return `
        <div class="bg-slate-800/80 rounded-2xl p-3.5 border border-slate-700/80 space-y-2.5 shadow transition">
          <div class="flex items-center justify-between gap-3">
            <!-- Right: Avatar + Profile Name + Status Badge underneath (Clickable to open Profile Modal) -->
            <div class="flex items-center gap-2.5 min-w-0 cursor-pointer group select-none" onclick="window.adminActions.openUserProfileModal(${u.telegram_id})" title="مشاهده شناسنامه و پروفایل کاربر">
              <!-- User Profile Avatar with Initials Fallback -->
              <div class="w-10 h-10 rounded-full bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-white text-xs shadow overflow-hidden flex-shrink-0 relative group-hover:ring-2 group-hover:ring-cyan-400/50 transition">
                <img src="${avatarSrc}" alt="Avatar" class="w-full h-full object-cover" onerror="this.classList.add('hidden'); if(this.nextElementSibling) this.nextElementSibling.classList.remove('hidden');" />
                <span class="${u.avatar_url ? 'hidden' : ''} font-bold">${escapeHtml(initial)}</span>
              </div>

              <!-- Name on top, Status Badge underneath -->
              <div class="min-w-0 flex-1">
                <!-- 1. Profile Name (اسم پروفایل کاربر) -->
                <div class="flex items-center gap-1.5 min-w-0">
                  <div class="text-xs font-bold text-white truncate max-w-[140px] sm:max-w-[190px] group-hover:text-cyan-300 transition">
                    ${(displayName || '').startsWith('@') ? `<span class="truncate inline-block font-mono" dir="ltr" style="unicode-bidi: isolate;">${escapeHtml(displayName)}</span>` : `<span class="truncate">${escapeHtml(displayName)}</span>`}
                  </div>
                  ${u.is_online ? '<span class="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)] animate-pulse flex-shrink-0" title="متصل به سرور"></span>' : ''}
                </div>

                <!-- Status Badge (فعال / بدون اکانت) Under the name -->
                <div class="flex flex-wrap items-center gap-1.5 mt-1">
                  <div>${statusBadge}</div>
                  ${expiringBadgeHtml}
                </div>
              </div>
            </div>

            <!-- Left: Top = Wallet Balance, Bottom = Compact Profile Button -->
            <div class="text-left flex flex-col items-end gap-1.5 flex-shrink-0">
              <span class="text-[11px] font-mono font-bold text-emerald-400">
                ${formatNumber(u.wallet_balance || 0)} ت
              </span>

              <button type="button" onclick="window.adminActions.openUserProfileModal(${u.telegram_id})" class="px-2.5 py-1 rounded-xl bg-slate-700/60 hover:bg-slate-700 border border-slate-600/70 text-slate-300 hover:text-white text-[10px] font-medium transition active:scale-95 flex items-center gap-1 shadow-sm" title="مشخصات و شناسنامه کاربر">
                <svg class="w-3 h-3 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg>
                <span>مشخصات</span>
              </button>
            </div>
          </div>

          <!-- Structured Service Metrics -->
          ${serviceLineHtml}

          <!-- Quick Action Buttons: 3x2 Symmetrical Grid -->
          <div class="space-y-1.5 pt-1">
            <div class="grid grid-cols-3 gap-1.5 text-center text-[10px]">
              <button class="bg-transparent hover:bg-blue-500/10 text-blue-500 dark:text-blue-400 border border-blue-500/30 hover:border-blue-400/60 py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" data-action="modify" data-tgid="${u.telegram_id}" data-username="${escapeHtml(u.username || '')}" data-name="${escapeHtml(displayName)}" onclick="window.adminActions.openModifyUser(this.dataset.tgid, this.dataset.username, this.dataset.name)" title="افزایش حجم یا تمدید زمان">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"/></svg>
                <span>حجم و تمدید</span>
              </button>
              <button class="bg-transparent hover:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 hover:border-emerald-400/60 py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" data-action="wallet" data-tgid="${u.telegram_id}" data-name="${escapeHtml(displayName)}" onclick="window.adminActions.openWalletModal(this.dataset.tgid, this.dataset.name)" title="شارژ یا کسر موجودی">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"/></svg>
                <span>موجودی</span>
              </button>
              <button class="bg-transparent hover:bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/30 hover:border-purple-400/60 py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" data-action="trial" data-tgid="${u.telegram_id}" data-username="${escapeHtml(u.username || '')}" data-name="${escapeHtml(displayName)}" onclick="window.adminActions.openTrialModal(this.dataset.tgid, this.dataset.username, this.dataset.name)" title="فعال‌سازی مجدد تست">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v13m0-13V6a2 2 0 112 2h-2zm0 0V5.5A2.5 2.5 0 109.5 8H12zm-7 4h14M5 12a2 2 0 01-2-2V7a2 2 0 012-2h14a2 2 0 012 2v3a2 2 0 01-2 2M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7"/></svg>
                <span>اکانت تست</span>
              </button>
            </div>
            <div class="grid grid-cols-3 gap-1.5 text-center text-[10px]">
              <button class="bg-transparent hover:bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border border-cyan-500/30 hover:border-cyan-400/60 py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" data-action="sub" data-tgid="${u.telegram_id}" data-name="${escapeHtml(displayName)}" data-suburl="${escapeHtml(p?.subscription_url || '')}" onclick="window.adminActions.openSubModal(this.dataset.tgid, this.dataset.name, this.dataset.suburl)" title="لینک سابسکریپشن">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/></svg>
                <span>لینک ساب</span>
              </button>
              <button class="bg-transparent hover:bg-teal-500/10 text-teal-600 dark:text-teal-400 border border-teal-500/30 hover:border-teal-400/60 py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" data-action="hwid" data-tgid="${u.telegram_id}" data-name="${escapeHtml(displayName)}" onclick="window.adminActions.openHwidModal(this.dataset.tgid, this.dataset.name)" title="دستگاه‌های فعال و نشست‌ها">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z"/></svg>
                <span>دستگاه‌ها</span>
              </button>
              <button class="${u.is_banned ? 'text-emerald-600 dark:text-emerald-400 border-emerald-500/30 hover:border-emerald-400/60 hover:bg-emerald-500/10' : 'text-rose-600 dark:text-rose-400 border-rose-500/30 hover:border-rose-400/60 hover:bg-rose-500/10'} bg-transparent border py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" onclick="window.adminActions.toggleBan(${u.telegram_id}, ${u.is_banned})">
                ${u.is_banned ? '<svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg><span>آزاد</span>' : '<svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"/></svg><span>مسدود</span>'}
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  // Search input debounce
  let searchDebounce = null;
  const userSearchInput = $('userSearchInput');
  const userSearchClear = $('userSearchClear');

  userSearchInput?.addEventListener('input', (e) => {
    const val = e.target.value.trim();
    if (userSearchClear) userSearchClear.classList.toggle('hidden', !val);
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      currentSearch = val;
      fetchAdminUsers(1);
    }, 320);
  });

  userSearchClear?.addEventListener('click', () => {
    if (userSearchInput) userSearchInput.value = '';
    userSearchClear.classList.add('hidden');
    currentSearch = '';
    fetchAdminUsers(1);
  });

  // User Filter buttons
  document.querySelectorAll('.user-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.user-filter-btn').forEach(b => {
        b.className = 'user-filter-btn px-2.5 py-1 rounded-xl bg-transparent text-slate-400 hover:text-white transition flex items-center gap-1 border border-slate-700/60';
      });
      btn.className = 'user-filter-btn px-2.5 py-1 rounded-xl bg-blue-600/20 text-blue-400 font-bold transition flex items-center gap-1 border border-blue-500 shadow-sm';
      currentFilter = btn.getAttribute('data-filter') || 'all';
      fetchAdminUsers(1);
      if (window.hapticFeedback) window.hapticFeedback('impact');
    });
  });

  // Icon-only Pagination Handlers
  $('adminUsersPrevBtn')?.addEventListener('click', () => {
    if (currentPage > 1) {
      fetchAdminUsers(currentPage - 1);
      if (window.hapticFeedback) window.hapticFeedback('impact');
    }
  });

  $('adminUsersNextBtn')?.addEventListener('click', () => {
    fetchAdminUsers(currentPage + 1);
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  // --- Confirmation & Report Modals ---
  function showConfirmModal({ title = 'تایید عملیات', message = 'آیا از انجام این عملیات اطمینان دارید؟', confirmText = 'تایید و اجرا', isDanger = true }) {
    return new Promise((resolve) => {
      const modal = $('confirmActionModal');
      const titleEl = $('confirmModalTitle');
      const msgEl = $('confirmModalMessage');
      const confirmBtn = $('confirmModalConfirmBtn');
      const cancelBtn = $('confirmModalCancelBtn');
      const iconBox = $('confirmModalIconBox');

      if (!modal || !confirmBtn || !cancelBtn) {
        resolve(window.confirm(message));
        return;
      }

      if (titleEl) titleEl.innerText = title;
      if (msgEl) msgEl.innerText = message;
      if (confirmBtn) {
        confirmBtn.innerText = confirmText;
        if (isDanger) {
          confirmBtn.className = 'flex-1 bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs py-2.5 rounded-xl transition shadow active:scale-95 flex items-center justify-center gap-1.5';
          if (iconBox) iconBox.className = 'w-10 h-10 rounded-2xl bg-rose-500/20 text-rose-400 border border-rose-500/30 flex items-center justify-center flex-shrink-0';
        } else {
          confirmBtn.className = 'flex-1 bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs py-2.5 rounded-xl transition shadow active:scale-95 flex items-center justify-center gap-1.5';
          if (iconBox) iconBox.className = 'w-10 h-10 rounded-2xl bg-blue-500/20 text-blue-400 border border-blue-500/30 flex items-center justify-center flex-shrink-0';
        }
      }

      const cleanup = () => {
        modal.classList.add('hidden');
        confirmBtn.removeEventListener('click', onConfirm);
        cancelBtn.removeEventListener('click', onCancel);
      };

      const onConfirm = () => {
        cleanup();
        if (window.hapticFeedback) window.hapticFeedback('impact');
        resolve(true);
      };

      const onCancel = () => {
        cleanup();
        resolve(false);
      };

      confirmBtn.addEventListener('click', onConfirm);
      cancelBtn.addEventListener('click', onCancel);
      modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('warning');
    });
  }

  function showOperationReportModal({ title, subtitle, iconType = 'success', items = [] }) {
    const modal = $('operationReportModal');
    const titleEl = $('opReportTitle');
    const subEl = $('opReportSubtitle');
    const iconBox = $('opReportIconBox');
    const contentEl = $('opReportContent');

    if (!modal) return;
    if (titleEl) titleEl.innerText = title || 'گزارش عملیات';
    if (subEl) subEl.innerText = subtitle || 'عملیات با موفقیت ثبت شد';

    if (iconBox) {
      if (iconType === 'success') {
        iconBox.className = 'w-10 h-10 rounded-2xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center flex-shrink-0';
        iconBox.innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>';
      } else if (iconType === 'purple') {
        iconBox.className = 'w-10 h-10 rounded-2xl bg-purple-500/20 text-purple-400 border border-purple-500/30 flex items-center justify-center flex-shrink-0';
        iconBox.innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"/></svg>';
      }
    }

    if (contentEl) {
      contentEl.innerHTML = items.map(item => {
        if (item.highlight) {
          return `
            <div class="bg-emerald-950/40 p-3 rounded-2xl border border-emerald-600/30 flex items-center justify-between text-xs">
              <span class="text-slate-300 font-medium">${item.label}:</span>
              <b class="text-emerald-400 font-mono font-bold text-sm" dir="ltr">${item.value}</b>
            </div>
          `;
        }
        return `
          <div class="bg-slate-900/60 p-2.5 rounded-xl border border-slate-800 flex items-center justify-between text-xs">
            <span class="text-slate-400 text-[11px]">${item.label}:</span>
            <span class="${item.color || 'text-white'} font-semibold text-xs truncate max-w-[200px]" dir="${item.dir || 'auto'}">${item.value}</span>
          </div>
        `;
      }).join('');
    }

    modal.classList.remove('hidden');
    if (window.hapticFeedback) window.hapticFeedback('success');
  }

  // --- 6. Admin Actions Namespace ---

  window.adminActions = {
    async quickCopy(text, label = 'مقدار') {
      if (!text) return;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(String(text));
        } else {
          const tempInput = document.createElement('textarea');
          tempInput.value = String(text);
          tempInput.style.position = 'fixed';
          tempInput.style.opacity = '0';
          document.body.appendChild(tempInput);
          tempInput.select();
          document.execCommand('copy');
          document.body.removeChild(tempInput);
        }
        if (window.showToast) window.showToast(`📋 ${label} کپی شد: ${text}`);
        if (window.hapticFeedback) window.hapticFeedback('success');
      } catch (e) {
        if (window.showToast) window.showToast(`📋 کپی شد: ${text}`);
      }
    },

    closeOperationReportModal() {
      $('operationReportModal')?.classList.add('hidden');
    },

    // Unified Modify User (Volume & Duration)
    openModifyUser(telegram_id, username = '', name = '') {
      currentModifyTarget = { telegram_id, username, name };
      const modal = $('modifyUserModal');
      const dispEl = $('modifyModalUserDisplay');
      const trInput = $('modifyModalTraffic');
      const daysInput = $('modifyModalDays');

      if (modal) modal.classList.remove('hidden');
      const handle = username ? `@${username}` : (name || `کاربر ${telegram_id}`);
      if (dispEl) dispEl.innerText = `${handle} - ${telegram_id}`;
      if (trInput) trInput.value = '';
      if (daysInput) daysInput.value = '';
      trInput?.focus();
      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    setModifyTraffic(gb) {
      const trInput = $('modifyModalTraffic');
      if (trInput) {
        const cur = parseFloat(trInput.value) || 0;
        trInput.value = (cur + gb);
      }
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    setModifyDays(days) {
      const daysInput = $('modifyModalDays');
      if (daysInput) {
        const cur = parseInt(daysInput.value, 10) || 0;
        daysInput.value = (cur + days);
      }
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    closeModifyModal() {
      const modal = $('modifyUserModal');
      if (modal) modal.classList.add('hidden');
      currentModifyTarget = null;
    },

    async deleteSslDomain(domain) {
      if (!domain) return;
      if (!confirm(`آیا از حذف دامنه «${domain}» از پایش SSL اطمینان دارید؟`)) return;
      try {
        const res = await window.api.deleteCustomSslDomain(domain);
        if (res && res.ok) {
          cachedSslHealthItems = cachedSslHealthItems.filter(x => x.domain.toLowerCase() !== domain.toLowerCase());
          renderSslHealth(cachedSslHealthItems);
          if (window.showToast) window.showToast('دامنه با موفقیت حذف شد');
          if (window.hapticFeedback) window.hapticFeedback('success');
        } else {
          if (window.showToast) window.showToast(res?.error || 'خطا در حذف دامنه');
        }
      } catch (err) {
        console.error('Delete SSL domain error:', err);
        if (window.showToast) window.showToast('خطا در برقراری ارتباط');
      }
    },

    async applyUserModification() {
      if (!currentModifyTarget) return;
      const trafficGb = parseFloat($('modifyModalTraffic')?.value || 0);
      const days = parseInt($('modifyModalDays')?.value || 0, 10);

      const validTraffic = !isNaN(trafficGb) && trafficGb > 0 ? trafficGb : 0;
      const validDays = !isNaN(days) && days > 0 ? days : 0;

      if (validTraffic <= 0 && validDays <= 0) {
        if (window.showToast) window.showToast('لطفاً حداقل یکی از مقادیر حجم یا روز را وارد کنید.');
        return;
      }

      const submitBtn = $('modifyModalSubmitBtn');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = 'در حال ثبت...';
      }
      try {
        const res = await window.api.modifyUser(
          currentModifyTarget.telegram_id,
          { traffic_gb: validTraffic, days: validDays }
        );
        if (res && res.ok) {
          if (window.showToast) window.showToast(`✅ ${res.message || 'عملیات با موفقیت اعمال شد'}`);
          if (window.hapticFeedback) window.hapticFeedback('success');
          this.closeModifyModal();
          fetchAdminUsers(currentPage);
          syncAdminOverview();
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ثبت تغییرات'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطای شبکه در ارتباط با سرور.');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg><span>ثبت تغییرات سرویس</span>';
        }
      }
    },

    openTrialModal(telegram_id, username = '', name = '') {
      currentTrialTarget = { telegram_id, username, name };
      const nameEl = $('trialModalUserName');
      if (nameEl) nameEl.innerText = name || (username ? `@${username}` : `کاربر ${telegram_id}`);
      const idEl = $('trialModalUserId');
      if (idEl) idEl.innerText = `#${telegram_id}`;
      $('trialModal')?.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    closeTrialModal() {
      $('trialModal')?.classList.add('hidden');
      currentTrialTarget = null;
    },

    async confirmResetTrial() {
      if (!currentTrialTarget) return;
      const { telegram_id, name } = currentTrialTarget;
      const btn = $('confirmTrialResetBtn');
      if (btn) {
        btn.disabled = true;
        btn.innerText = 'در حال فعال‌سازی...';
      }
      try {
        const res = await window.api.resetUserTrial(telegram_id);
        if (res && res.ok) {
          this.closeTrialModal();
          showOperationReportModal({
            title: 'گزارش فعال‌سازی مجدد تست',
            subtitle: 'محدودیت دریافت اکانت تست برای کاربر برداشته شد',
            iconType: 'purple',
            items: [
              { label: 'کاربر منتخب', value: name },
              { label: 'شناسه تلگرام', value: `#${telegram_id}`, dir: 'ltr' },
              { label: 'وضعیت جدید', value: 'مجاز به دریافت تست رایگان', color: 'text-purple-400' },
              { label: 'نتیجه عملیات', value: res.message || 'اکانت تست با موفقیت ریست شد و کاربر می‌تواند از ربات تست دریافت کند.' },
            ]
          });
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در فعال‌سازی تست'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطا در برقراری ارتباط');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg><span>تایید و فعال‌سازی مجدد تست</span>';
        }
      }
    },

    resetTrial(telegram_id, name) {
      this.openTrialModal(telegram_id, name);
    },

    async killSessions(telegram_id, name) {
      const ok = await showConfirmModal({
        title: 'قطع تمامی اتصالات',
        message: `آیا از قطع کامل تمامی نشست‌ها و اتصالات دستگاه‌های کاربر ${name} اطمینان دارید؟`,
        confirmText: 'قطع اتصالات کاربر',
        isDanger: true,
      });
      if (!ok) return;

      try {
        const res = await window.api.killUserSessions(telegram_id);
        if (res && res.ok) {
          if (window.showToast) window.showToast(`✅ تعداد ${formatNumber(res.killed_devices || 0)} نشست فعال قطع شدند.`);
          if (window.hapticFeedback) window.hapticFeedback('success');
          syncAdminOverview();
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در قطع نشست‌ها'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطا در ارتباط با سرور');
      }
    },

    async toggleBan(telegram_id, isBanned) {
      const actionText = isBanned ? 'رفع مسدودیت' : 'مسدود کردن';
      const ok = await showConfirmModal({
        title: `${actionText} کاربر`,
        message: `آیا از ${actionText} این کاربر اطمینان دارید؟`,
        confirmText: `بله، ${actionText}`,
        isDanger: !isBanned,
      });
      if (!ok) return;

      try {
        const res = await window.api.toggleUserBan(telegram_id, !isBanned);
        if (res && res.ok) {
          if (window.showToast) window.showToast(`✅ کاربر با موفقیت ${res.banned ? 'مسدود' : 'آزاد'} شد.`);
          if (window.hapticFeedback) window.hapticFeedback('success');
          fetchAdminUsers(currentPage);
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در تغییر وضعیت کاربر'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطا در برقراری ارتباط');
      }
    },

    async handleTopup(topup_id, approved) {
      const ok = await showConfirmModal({
        title: approved ? 'تایید و شارژ فیش' : 'رد کردن فیش واریزی',
        message: `آیا از ${approved ? 'تایید و شارژ' : 'رد کردن'} این فیش مطمئن هستید؟`,
        confirmText: approved ? 'تایید و شارژ' : 'رد فیش',
        isDanger: !approved,
      });
      if (!ok) return;

      try {
        const res = await window.api.handleTopupAction(topup_id, approved);
        if (res && res.ok) {
          if (window.showToast) window.showToast(`✅ ${res.message}`);
          if (window.hapticFeedback) window.hapticFeedback('success');
          fetchAdminTopups();
          syncAdminOverview();
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در تعیین تکلیف فیش'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (err) {
        if (window.showToast) window.showToast('خطا در برقراری ارتباط');
      }
    },

    // --- User Profile Modal ---
    openUserProfileModal(telegram_id) {
      const user = (window.currentAdminUsersList || []).find(x => String(x.telegram_id) === String(telegram_id));
      if (!user) {
        if (window.showToast) window.showToast('اطلاعات کاربر یافت نشد.');
        return;
      }

      const rawName = user.full_name || '';
      const displayName = (rawName && !rawName.startsWith('@')) ? rawName : (user.username ? ('@' + user.username) : `کاربر ${user.telegram_id}`);
      const initial = (displayName || String(user.telegram_id))[0].toUpperCase();

      // Avatar & Initial
      const avatarImg = $('userProfModalAvatar');
      const initialSpan = $('userProfModalInitial');
      if (avatarImg && initialSpan) {
        if (user.avatar_url) {
          avatarImg.src = user.avatar_url;
          avatarImg.classList.remove('hidden');
          initialSpan.classList.add('hidden');
          avatarImg.onerror = () => {
            avatarImg.classList.add('hidden');
            initialSpan.classList.remove('hidden');
          };
        } else {
          avatarImg.classList.add('hidden');
          initialSpan.classList.remove('hidden');
        }
        initialSpan.innerText = initial;
      }

      // Name & Online Dot
      const nameElem = $('userProfModalFullName');
      if (nameElem) nameElem.innerText = displayName;

      const onlineDot = $('userProfModalOnlineDot');
      if (onlineDot) {
        if (user.is_online) onlineDot.classList.remove('hidden');
        else onlineDot.classList.add('hidden');
      }

      // Status Badge
      const p = user.panel_account;
      let statusBadge = '<span class="px-2 py-0.5 rounded-lg text-[10px] bg-slate-800 border border-slate-700 text-slate-400 font-medium">بدون اکانت</span>';
      if (user.is_banned) {
        statusBadge = '<span class="px-2 py-0.5 rounded-lg text-[10px] bg-rose-500/10 text-rose-400 font-bold border border-rose-500/30">مسدود</span>';
      } else if (user.is_expired || (p && p.exists && (p.status || '').toUpperCase() === 'EXPIRED')) {
        statusBadge = '<span class="px-2 py-0.5 rounded-lg text-[10px] bg-rose-500/10 text-rose-400 font-bold border border-rose-500/30">منقضی</span>';
      } else if (p && p.exists) {
        const st = (p.status || '').toUpperCase();
        if (st === 'ACTIVE') {
          statusBadge = '<span class="px-2 py-0.5 rounded-lg text-[10px] bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/30">فعال</span>';
        } else if (st === 'DISABLED') {
          statusBadge = '<span class="px-2 py-0.5 rounded-lg text-[10px] bg-amber-500/10 text-amber-400 font-bold border border-amber-500/30">غیرفعال</span>';
        } else if (st === 'LIMITED') {
          statusBadge = '<span class="px-2 py-0.5 rounded-lg text-[10px] bg-purple-500/10 text-purple-400 font-bold border border-purple-500/30">محدود شده</span>';
        } else {
          statusBadge = `<span class="px-2 py-0.5 rounded-lg text-[10px] bg-slate-800 border border-slate-700 text-slate-300 font-medium">${escapeHtml(st)}</span>`;
        }
      }
      const statusBadgeElem = $('userProfModalStatusBadge');
      if (statusBadgeElem) statusBadgeElem.innerHTML = statusBadge;

      const expBadgeElem = $('userProfModalExpiringBadge');
      if (expBadgeElem) {
        expBadgeElem.innerHTML = user.is_expiring ? '<span class="px-2 py-0.5 rounded-lg text-[10px] bg-amber-500/10 text-amber-300 font-bold border border-amber-500/30">رو به اتمام</span>' : '';
      }

      // Username
      const uNameElem = $('userProfModalUsername');
      const tgLinkBtn = $('userProfModalTgLinkBtn');
      const copyUNameBtn = $('userProfModalCopyUsernameBtn');
      if (user.username) {
        if (uNameElem) uNameElem.innerText = '@' + user.username;
        if (tgLinkBtn) {
          tgLinkBtn.classList.remove('hidden');
          tgLinkBtn.onclick = () => window.open(`https://t.me/${user.username}`, '_blank');
        }
        if (copyUNameBtn) {
          copyUNameBtn.classList.remove('hidden');
          copyUNameBtn.onclick = () => window.adminActions.quickCopy('@' + user.username, 'نام کاربری');
        }
      } else {
        if (uNameElem) uNameElem.innerText = 'ندارد';
        if (tgLinkBtn) tgLinkBtn.classList.add('hidden');
        if (copyUNameBtn) copyUNameBtn.classList.add('hidden');
      }

      // Telegram ID
      const idElem = $('userProfModalId');
      if (idElem) idElem.innerText = String(user.telegram_id);
      const tgIdLinkBtn = $('userProfModalTgIdLinkBtn');
      if (tgIdLinkBtn) tgIdLinkBtn.onclick = () => window.open(`tg://user?id=${user.telegram_id}`, '_blank');
      const copyIdBtn = $('userProfModalCopyIdBtn');
      if (copyIdBtn) copyIdBtn.onclick = () => window.adminActions.quickCopy(String(user.telegram_id), 'شناسه عددی');

      // Phone
      const phoneElem = $('userProfModalPhone');
      const callBtn = $('userProfModalCallBtn');
      const copyPhoneBtn = $('userProfModalCopyPhoneBtn');
      if (user.phone_number) {
        if (phoneElem) phoneElem.innerText = user.phone_number;
        if (callBtn) {
          callBtn.href = `tel:${user.phone_number}`;
          callBtn.classList.remove('hidden');
        }
        if (copyPhoneBtn) {
          copyPhoneBtn.classList.remove('hidden');
          copyPhoneBtn.onclick = () => window.adminActions.quickCopy(user.phone_number, 'شماره تماس');
        }
      } else {
        if (phoneElem) phoneElem.innerText = 'ثبت نشده';
        if (callBtn) callBtn.classList.add('hidden');
        if (copyPhoneBtn) copyPhoneBtn.classList.add('hidden');
      }

      // Birthday
      const bdayElem = $('userProfModalBirthday');
      if (bdayElem) bdayElem.innerText = user.birth_date ? user.birth_date : 'ثبت نشده';

      // Wallet
      const walletElem = $('userProfModalWallet');
      if (walletElem) walletElem.innerText = `${formatNumber(user.wallet_balance || 0)} تومان`;

      // Created At
      const createdElem = $('userProfModalCreatedAt');
      if (createdElem) createdElem.innerText = user.created_at_jalali ? user.created_at_jalali : (user.created_at ? user.created_at.slice(0, 10) : 'نامشخص');

      // Quick Chat Button
      const chatBtn = $('userProfModalQuickChatBtn');
      if (chatBtn) {
        if (user.username) {
          chatBtn.onclick = () => window.open(`https://t.me/${user.username}`, '_blank');
        } else {
          chatBtn.onclick = () => window.open(`tg://user?id=${user.telegram_id}`, '_blank');
        }
      }

      // Open Modal
      const modal = $('userProfileModal');
      if (modal) modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('light');
    },

    closeUserProfileModal() {
      const modal = $('userProfileModal');
      if (modal) modal.classList.add('hidden');
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    // --- Wallet Actions ---
    openWalletModal(telegram_id, name) {
      currentWalletTarget = { telegram_id, name };
      const modal = $('walletModal');
      const title = $('walletModalTitle');
      const amtInput = $('walletModalAmount');
      const reasonInput = $('walletModalReason');
      if (modal) modal.classList.remove('hidden');
      if (title) title.innerText = `💰 کیف پول: ${name}`;
      if (amtInput) amtInput.value = '50000';
      if (reasonInput) reasonInput.value = 'شارژ دستی توسط مدیریت';
      amtInput?.focus();
    },

    closeWalletModal() {
      $('walletModal')?.classList.add('hidden');
      currentWalletTarget = null;
    },

    async applyWalletModification() {
      if (!currentWalletTarget) return;
      const rawAmount = parseInt($('walletModalAmount')?.value || '0', 10);
      if (isNaN(rawAmount) || rawAmount <= 0) {
        if (window.showToast) window.showToast('لطفاً مبلغ معتبری وارد کنید.');
        return;
      }
      const finalAmount = walletActionType === 'add' ? rawAmount : -rawAmount;
      const reason = $('walletModalReason')?.value?.trim() || 'شارژ توسط مدیریت';
      const submitBtn = $('walletModalSubmitBtn');
      if (submitBtn) { submitBtn.disabled = true; submitBtn.innerText = 'در حال ثبت...'; }

      try {
        const res = await window.api.modifyUserWallet(currentWalletTarget.telegram_id, finalAmount, reason);
        if (res && res.ok) {
          const oldBal = Number(res.old_balance !== undefined ? res.old_balance : 0);
          const newBal = Number(res.new_balance !== undefined ? res.new_balance : 0);
          const delta = Number(res.delta !== undefined ? res.delta : finalAmount);
          const isAdd = delta > 0;
          const targetName = currentWalletTarget.name;
          const targetId = currentWalletTarget.telegram_id;

          this.closeWalletModal();
          fetchAdminUsers(currentPage);
          syncAdminOverview();

          showOperationReportModal({
            title: 'گزارش تراکنش کیف پول',
            subtitle: isAdd ? 'افزایش موجودی با موفقیت ثبت شد' : 'کسر موجودی با موفقیت ثبت شد',
            iconType: 'success',
            items: [
              { label: 'کاربر منتخب', value: targetName },
              { label: 'شناسه تلگرام', value: `#${targetId}`, dir: 'ltr' },
              { label: 'نوع عملیات', value: isAdd ? 'افزایش اعتبار (شارژ دستی)' : 'کسر موجودی دستی', color: isAdd ? 'text-emerald-400' : 'text-rose-400' },
              { label: 'موجودی قبلی', value: `${formatNumber(oldBal)} تومان`, dir: 'rtl' },
              { label: 'مبلغ تغییر یافته', value: `${isAdd ? '+' : ''}${formatNumber(delta)} تومان`, color: isAdd ? 'text-emerald-400' : 'text-rose-400', dir: 'rtl' },
              { label: 'موجودی جدید کیف پول', value: `${formatNumber(newBal)} تومان`, highlight: true },
              { label: 'توضیحات / بابت', value: reason || 'ثبت توسط مدیریت' },
            ]
          });
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در تغییر موجودی'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطای شبکه در ثبت موجودی');
      } finally {
        if (submitBtn) { submitBtn.disabled = false; submitBtn.innerText = 'ثبت تغییر موجودی'; }
      }
    },

    // --- Subscription URL Inspector & Regenerator ---
    openSubModal(telegram_id, name, subUrl) {
      currentSubTarget = { telegram_id, name, subUrl };
      const modal = $('subModal');
      const title = $('subModalTitle');
      const input = $('subModalInput');
      if (modal) modal.classList.remove('hidden');
      if (title) title.innerText = `🔄 لینک اشتراک: ${name}`;
      if (input) {
        input.value = subUrl || '';
        if (!subUrl) input.placeholder = 'اکانت پنل برای این کاربر یافت نشد یا لینکی صادر نشده است';
      }
      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    closeSubModal() {
      $('subModal')?.classList.add('hidden');
      currentSubTarget = null;
    },

    async copySubLink() {
      const input = $('subModalInput');
      if (!input || !input.value) {
        if (window.showToast) window.showToast('لینکی برای کپی کردن وجود ندارد.');
        return;
      }
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(input.value);
        } else {
          input.select();
          document.execCommand('copy');
        }
        if (window.showToast) window.showToast('✅ لینک اشتراک با موفقیت کپی شد.');
        if (window.hapticFeedback) window.hapticFeedback('success');
      } catch (err) {
        input.select();
        document.execCommand('copy');
        if (window.showToast) window.showToast('✅ لینک کپی شد.');
      }
    },

    async confirmRegenerateSub() {
      if (!currentSubTarget) return;
      const { telegram_id, name } = currentSubTarget;
      const ok = await showConfirmModal({
        title: 'ابطال و صدور لینک جدید',
        message: `آیا از باطل کردن لینک قبلی و صدور لینک جدید برای ${name} اطمینان دارید؟ با این کار کانفیگ‌های قبلی باطل می‌شوند.`,
        confirmText: 'صدور لینک جدید',
        isDanger: false,
      });
      if (!ok) return;

      const regenBtn = $('subModalRegenBtn');
      if (regenBtn) {
        regenBtn.disabled = true;
        regenBtn.innerText = 'در حال صدور لینک جدید...';
      }
      try {
        const res = await window.api.revokeUserSub(telegram_id);
        if (res && res.ok && res.subscription_url) {
          currentSubTarget.subUrl = res.subscription_url;
          const input = $('subModalInput');
          if (input) input.value = res.subscription_url;
          if (window.showToast) window.showToast('✅ لینک جدید سابسکریپشن صادر و جایگزین شد.');
          if (window.hapticFeedback) window.hapticFeedback('success');
          fetchAdminUsers(currentPage);
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ایجاد لینک جدید'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (err) {
        if (window.showToast) window.showToast('خطای شبکه در ارتباط با سرور.');
      } finally {
        if (regenBtn) {
          regenBtn.disabled = false;
          regenBtn.innerHTML = '<span>🔄</span><span>باطل کردن و صدور لینک جدید</span>';
        }
      }
    },

    // --- Revoke Subscription URL (Quick trigger backward-compat) ---
    async revokeSub(telegram_id, name) {
      const ok = await showConfirmModal({
        title: 'ابطال لینک سابسکریپشن',
        message: `آیا از ابطال لینک قبلی و ساخت لینک جدید برای کاربر ${name} اطمینان دارید؟`,
        confirmText: 'تایید و صدور مجدد',
        isDanger: false,
      });
      if (!ok) return;

      try {
        const res = await window.api.revokeUserSub(telegram_id);
        if (res && res.ok) {
          if (window.showToast) window.showToast('✅ لینک سابسکریپشن کاربر با موفقیت تغییر یافت.');
          if (window.hapticFeedback) window.hapticFeedback('success');
          fetchAdminUsers(currentPage);
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در تغییر لینک'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطا در ارتباط با سرور');
      }
    },

    // --- Unified Devices & Live Sessions Modal ---
    currentDeviceTab: 'hwid',

    async openHwidModal(telegram_id, name, initialTab = 'hwid') {
      currentHwidTarget = { telegram_id, name };
      this.currentUserSessionsTarget = { telegram_id, name };
      const modal = $('hwidModal');
      const title = $('hwidModalTitle');
      if (modal) modal.classList.remove('hidden');
      if (title) title.innerText = `📱 دستگاه‌ها و نشست‌ها: ${name}`;
      if (window.hapticFeedback) window.hapticFeedback('impact');
      await this.switchDeviceModalTab(initialTab);
    },

    async switchDeviceModalTab(tab = 'hwid') {
      this.currentDeviceTab = tab;
      const hwidBtn = $('deviceTabBtn_hwid');
      const sessionsBtn = $('deviceTabBtn_sessions');
      const srhBtn = $('deviceTabBtn_srh');
      const hwidPane = $('hwidTabPane');
      const sessionsPane = $('sessionsTabPane');
      const srhPane = $('srhTabPane');

      const activeClass = 'py-1.5 rounded-xl font-bold bg-cyan-600 text-white shadow text-center flex items-center justify-center gap-1 transition';
      const inactiveClass = 'py-1.5 rounded-xl text-slate-400 hover:text-cyan-300 font-medium text-center flex items-center justify-center gap-1 transition';

      if (hwidBtn) hwidBtn.className = (tab === 'hwid') ? activeClass : inactiveClass;
      if (sessionsBtn) sessionsBtn.className = (tab === 'sessions') ? activeClass : inactiveClass;
      if (srhBtn) srhBtn.className = (tab === 'srh') ? activeClass : inactiveClass;

      if (hwidPane) hwidPane.classList.toggle('hidden', tab !== 'hwid');
      if (sessionsPane) sessionsPane.classList.toggle('hidden', tab !== 'sessions');
      if (srhPane) srhPane.classList.toggle('hidden', tab !== 'srh');

      if (currentHwidTarget) {
        if (tab === 'hwid') {
          await this.loadHwidDevices(currentHwidTarget.telegram_id);
        } else if (tab === 'sessions') {
          await this.loadUserSessions(currentHwidTarget.telegram_id);
        } else if (tab === 'srh') {
          await this.loadUserSrh(currentHwidTarget.telegram_id);
        }
      }
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    async refreshCurrentDeviceTab() {
      if (!currentHwidTarget) return;
      if (this.currentDeviceTab === 'sessions') {
        await this.loadUserSessions(currentHwidTarget.telegram_id);
      } else if (this.currentDeviceTab === 'srh') {
        await this.loadUserSrh(currentHwidTarget.telegram_id);
      } else {
        await this.loadHwidDevices(currentHwidTarget.telegram_id);
      }
    },

    async loadUserSrh(telegram_id) {
      const list = $('userSrhList');
      if (list) list.innerHTML = '<div class="p-6 text-center text-slate-400">در حال دریافت تاریخچه سابسکریپشن...</div>';

      try {
        const res = await window.api.getUserSrh({ telegram_id });
        if (!res || !res.ok) {
          if (list) list.innerHTML = `<div class="p-4 text-center text-rose-400">${res?.error || 'خطا در دریافت تاریخچه'}</div>`;
          return;
        }
        const records = res.data || [];
        if (records.length === 0) {
          if (list) list.innerHTML = '<div class="p-6 text-center text-slate-400">هنوز درخواستی برای دریافت لینک کانفیگ ثبت نشده است (کاربر نرم‌افزار خود را آپدیت نکرده است).</div>';
          return;
        }

        if (list) {
          list.innerHTML = records.map(r => `
            <div class="srh-card bg-transparent p-2.5 rounded-2xl border border-slate-700/60 space-y-1.5">
              <!-- Line 1: Client name on right, status badge on left -->
              <div class="flex items-center justify-between gap-2">
                <div class="flex items-center gap-1.5 min-w-0 flex-1">
                  <span class="text-base flex-shrink-0">${r.client_icon || '📱'}</span>
                  <b class="text-white text-xs truncate" title="${escapeHtml(r.user_agent || r.client_name || '')}">${escapeHtml(r.client_name || 'کلاینت')}</b>
                </div>
                <span class="inline-flex items-center gap-1 text-[9px] font-bold ${r.is_success ? 'text-emerald-400 border-emerald-500/30' : 'text-rose-400 border-rose-500/30'} bg-transparent px-2 py-0.5 rounded-lg border flex-shrink-0">
                  ${r.is_success ? 'موفق' : (r.status_code ? 'خطا ' + r.status_code : 'خطا')}
                </span>
              </div>

              <!-- Line 2: Tag badge, IP with tap-to-copy, and update time -->
              <div class="flex items-center justify-between text-[10px] pt-1 border-t border-slate-800/60 text-slate-400 gap-2">
                <div class="flex items-center gap-1.5 flex-wrap min-w-0">
                  <span class="text-[9px] px-1.5 py-0.5 rounded-md bg-transparent border border-slate-700/80 text-slate-300 font-mono flex-shrink-0">${escapeHtml(r.client_tag || 'App')}</span>
                  <button type="button" dir="ltr" class="font-mono text-cyan-400 dark:text-cyan-300 font-semibold select-all hover:underline cursor-pointer flex items-center gap-1" onclick="window.copyToClipboard('${r.ip}', 'آدرس IP کپی شد')" title="کلیک جهت کپی آی‌پی">
                    <span>🌐 ${r.ip}</span>
                    <span class="text-[9px] opacity-70">📋</span>
                  </button>
                </div>
                <div class="flex items-center gap-1.5 text-[10px] text-slate-300 font-mono flex-shrink-0" dir="ltr">
                  <span>⏱</span>
                  <span class="font-bold text-slate-200" title="${escapeHtml(r.relative_time || '')}">${toEnglishDigits(r.date_str && r.date_str !== '—' ? r.date_str : (r.relative_time || 'ثبت‌شده'))}</span>
                  ${r.relative_time && r.relative_time !== '—' && r.relative_time !== r.date_str ? `<span class="text-[9px] text-slate-400 font-sans">(${r.relative_time})</span>` : ''}
                </div>
              </div>
            </div>
          `).join('');
        }
      } catch (e) {
        if (list) list.innerHTML = '<div class="p-4 text-center text-rose-400">خطای ارتباط با سرور</div>';
      }
    },

    async loadHwidDevices(telegram_id) {
      const list = $('hwidDevicesList');
      if (list) list.innerHTML = '<div class="p-6 text-center text-slate-400">در حال دریافت دستگاه‌ها...</div>';

      try {
        const res = await window.api.getUserHwidDevices(telegram_id);
        if (!res || !res.ok) {
          if (list) list.innerHTML = `<div class="p-4 text-center text-rose-400">${res?.error || 'خطا در دریافت لیست'}</div>`;
          return;
        }
        const devices = res.devices || [];
        if (devices.length === 0) {
          if (list) list.innerHTML = '<div class="p-6 text-center text-slate-400">هیچ دستگاه فعالی متصل نیست 🟢</div>';
          return;
        }

        if (list) {
          list.innerHTML = devices.map(d => {
            const hwid = d.hwid || d.id || '';
            let rawOs = String(d.os || d.platform || d.clientApp || d.userAgent || '').trim();
            const osLower = rawOs.toLowerCase();
            let osDisplay = rawOs || 'دستگاه متصل';
            let osIcon = '📱';

            if (osLower.includes('windows') || osLower.includes('win32') || osLower.includes('win64')) {
              osDisplay = 'ویندوز';
              osIcon = '🪟';
            } else if (osLower.includes('android')) {
              osDisplay = 'اندروید';
              osIcon = '🤖';
            } else if (osLower.includes('ios') || osLower.includes('iphone') || osLower.includes('ipad')) {
              osDisplay = 'iOS (آیفون)';
              osIcon = '🍏';
            } else if (osLower.includes('mac') || osLower.includes('darwin') || osLower.includes('osx')) {
              osDisplay = 'macOS (مک)';
              osIcon = '🍎';
            } else if (osLower.includes('linux')) {
              osDisplay = 'لینوکس';
              osIcon = '🐧';
            } else if (!rawOs || osLower === 'client') {
              osDisplay = 'دستگاه متصل';
            }

            const brand = d.brand || d.model || '';
            const ip = d.requestIp || d.ip || d.lastIp || d.clientIp || '—';

            const createdRaw = d.createdAt || d.created_at || d.updatedAt || d.lastSeen || d.lastActivity || d.timestamp;
            let timeHtml = '';
            if (createdRaw) {
              try {
                const dateObj = new Date(createdRaw);
                if (!isNaN(dateObj.getTime())) {
                  const dateStr = dateObj.toLocaleDateString('fa-IR');
                  const timeStr = dateObj.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' });
                  timeHtml = `<div class="flex items-center gap-1 mt-1 text-[9.5px] text-slate-400 font-mono" dir="ltr"><span>⏱</span><span>${toEnglishDigits(timeStr)} - ${toEnglishDigits(dateStr)}</span></div>`;
                }
              } catch(e) {}
            }

            return `
              <div class="bg-transparent p-3 rounded-2xl border border-slate-700/60 dark:border-slate-700/60 flex items-center justify-between gap-2.5">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-1.5">
                    <span class="text-sm flex-shrink-0">${osIcon}</span>
                    <b class="text-white text-xs block truncate">${escapeHtml(osDisplay)} ${brand ? '(' + escapeHtml(brand) + ')' : ''}</b>
                  </div>
                  <div class="flex items-center gap-1.5 mt-0.5 text-[10px] text-slate-400">
                    <span>آی‌پی:</span>
                    <button type="button" dir="ltr" class="font-mono text-cyan-400 dark:text-cyan-300 font-semibold select-all hover:underline cursor-pointer flex items-center gap-1" onclick="window.copyToClipboard('${escapeHtml(ip)}', 'آدرس IP کپی شد')" title="کپی آی‌پی">
                      <span>${escapeHtml(ip)}</span>
                      <span class="text-[9px] opacity-70">📋</span>
                    </button>
                  </div>
                  <div class="flex items-center gap-1.5 mt-1">
                    <span class="text-[9px] text-slate-400">HWID:</span>
                    <span dir="ltr" class="font-mono text-[9px] text-slate-300 bg-transparent px-2 py-0.5 rounded-lg border border-slate-700/60 truncate max-w-[170px]" title="${escapeHtml(hwid)}">${escapeHtml(hwid)}</span>
                  </div>
                  ${timeHtml}
                </div>
                <button onclick="window.adminActions.deleteHwid(${telegram_id}, '${escapeHtml(hwid).replace(/'/g, "\\'")}')" class="bg-transparent hover:bg-rose-500/10 text-rose-400 border border-rose-500/30 hover:border-rose-400 p-2.5 rounded-xl transition active:scale-95 flex items-center justify-center flex-shrink-0" title="قطع اتصال این دستگاه">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                </button>
              </div>
            `;
          }).join('');
        }
      } catch (e) {
        if (list) list.innerHTML = '<div class="p-4 text-center text-rose-400">خطای شبکه در دریافت اطلاعات دستگاه‌ها</div>';
      }
    },

    async loadUserSessions(telegram_id) {
      const list = $('userSessionsList');
      if (list) {
        list.innerHTML = `
          <div class="p-8 text-center text-xs text-slate-400 flex flex-col items-center gap-2">
            <span class="w-6 h-6 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin"></span>
            <span>در حال بررسی نودها و دریافت اتصالات...</span>
          </div>
        `;
      }

      try {
        const res = await window.api.getUserLiveSessions(telegram_id);
        if (!res || !res.ok) {
          if (list) list.innerHTML = `<div class="p-4 text-center text-rose-400 text-xs">${res?.error || 'خطا در دریافت اطلاعات اتصالات'}</div>`;
          return;
        }

        const data = res.data || {};
        this.renderUserSessionsList(data);
      } catch (e) {
        if (list) list.innerHTML = '<div class="p-4 text-center text-rose-400 text-xs">خطای شبکه در دریافت اتصالات</div>';
      }
    },

    renderUserSessionsList(data) {
      const list = $('userSessionsList');
      if (!list) return;

      const isOnline = !!data?.isOnline;
      const conns = data?.nodeConnections || [];

      if (!isOnline || conns.length === 0) {
        list.innerHTML = `
          <div class="p-8 text-center text-xs text-slate-400 flex flex-col items-center gap-2">
            <span class="w-10 h-10 rounded-2xl bg-slate-800/80 flex items-center justify-center text-slate-500 text-lg">💤</span>
            <b class="text-white text-xs">هیچ نشست یا اتصال فعالی یافت نشد</b>
            <span class="text-[10px] text-slate-400">کاربر در حال حاضر به هیچ سروری متصل نیست.</span>
          </div>
        `;
        return;
      }

      list.innerHTML = conns.map(nc => {
        const flag = getFlagEmoji(nc.countryCode);
        const nodeName = nc.nodeName || 'سرور';
        const ips = nc.ips || [];
        const ipsHtml = ips.map(ip => `
          <div class="flex items-center justify-between bg-transparent px-2.5 py-1.5 rounded-xl border border-slate-700/60 text-xs">
            <span class="text-slate-400 text-[10px]">آی‌پی کلاینت:</span>
            <button type="button" dir="ltr" class="font-mono text-cyan-400 dark:text-cyan-300 font-bold select-all hover:underline cursor-pointer flex items-center gap-1" onclick="window.copyToClipboard('${escapeHtml(ip)}', 'آدرس IP کپی شد')" title="کلیک جهت کپی آی‌پی">
              <span>${escapeHtml(ip)}</span>
              <span class="text-[9px] opacity-70">📋</span>
            </button>
          </div>
        `).join('');

        return `
          <div class="bg-transparent rounded-2xl p-3 border border-slate-700/60 space-y-2">
            <div class="flex items-center justify-between">
              <span class="text-white font-bold text-xs flex items-center gap-1.5">
                <span class="text-sm">${flag}</span>
                <span>${escapeHtml(nodeName)}</span>
              </span>
              <span class="text-[10px] bg-transparent text-cyan-400 border border-cyan-500/30 px-2 py-0.5 rounded-lg font-mono">
                ${formatNumber(ips.length)} اتصال
              </span>
            </div>
            <div class="space-y-1 pt-1">
              ${ipsHtml || '<div class="text-slate-500 text-[10px] text-center">آی‌پی ثبت‌نشده</div>'}
            </div>
          </div>
        `;
      }).join('');
    },

    closeHwidModal() {
      $('hwidModal')?.classList.add('hidden');
      currentHwidTarget = null;
      this.currentUserSessionsTarget = null;
    },

    closeUserSessionsModal() {
      this.closeHwidModal();
    },

    async openUserSessionsModal(telegram_id, name) {
      await this.openHwidModal(telegram_id, name, 'sessions');
    },

    async refreshUserSessions() {
      if (currentHwidTarget) {
        await this.loadUserSessions(currentHwidTarget.telegram_id);
      }
    },

    async killSessionsFromModal() {
      if (!currentHwidTarget) return;
      const { telegram_id, name } = currentHwidTarget;
      const ok = await showConfirmModal({
        title: 'قطع تمامی نشست‌های فعال',
        message: `آیا از قطع تمام نشست‌ها و اتصالات کاربر ${name} اطمینان دارید؟`,
        confirmText: 'قطع تمامی نشست‌ها',
        isDanger: true,
      });
      if (!ok) return;

      try {
        const res = await window.api.killUserSessions(telegram_id);
        if (res && res.ok) {
          if (window.showToast) window.showToast(`✅ تمامی نشست‌های فعال کاربر قطع شدند.`);
          if (window.hapticFeedback) window.hapticFeedback('success');
          await this.refreshCurrentDeviceTab();
          syncAdminOverview();
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در قطع نشست‌ها'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطا در ارتباط با سرور');
      }
    },

    async killUserSessionsFromModal() {
      await this.killSessionsFromModal();
    },

    async deleteHwid(telegram_id, hwid) {
      const ok = await showConfirmModal({
        title: 'قطع اتصال دستگاه',
        message: 'آیا از قطع اتصال این دستگاه کاربر اطمینان دارید؟',
        confirmText: 'قطع اتصال',
        isDanger: true,
      });
      if (!ok) return;

      try {
        const res = await window.api.deleteUserHwid(telegram_id, hwid);
        if (res && res.ok) {
          if (window.showToast) window.showToast('✅ اتصال دستگاه با موفقیت قطع شد.');
          if (window.hapticFeedback) window.hapticFeedback('success');
          if (currentHwidTarget) await this.loadHwidDevices(currentHwidTarget.telegram_id);
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در قطع اتصال'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطا در برقراری ارتباط');
      }
    },

    // --- Plans Actions ---
    async fetchAdminPlans() {
      const container = $('adminPlansList');
      if (!container) return;
      container.innerHTML = '<div class="p-8 text-center text-xs text-slate-400">در حال دریافت تعرفه‌ها...</div>';
      try {
        const res = await window.api.getAdminPlans();
        if (!res || !res.ok) {
          container.innerHTML = `<div class="p-6 text-center text-rose-400 text-xs">${res?.error || 'خطا در دریافت تعرفه‌ها'}</div>`;
          return;
        }
        adminPlansData = res.plans || [];
        if (adminPlansData.length === 0) {
          container.innerHTML = `
            <div class="bg-slate-900/50 border border-slate-800 rounded-2xl p-6 text-center text-slate-400 space-y-3">
              <div class="w-10 h-10 rounded-2xl bg-blue-500/15 text-blue-400 flex items-center justify-center mx-auto">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>
              </div>
              <p class="text-xs">هیچ سرویس یا تعرفه‌ای هنوز ثبت نشده است.</p>
              <button onclick="window.adminActions.openPlanModal()" class="bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold px-4 py-2 rounded-xl transition shadow active:scale-95">
                + ایجاد اولین سرویس
              </button>
            </div>
          `;
          return;
        }

        container.innerHTML = adminPlansData.map(p => {
          const statusBadge = p.is_active
            ? '<span class="text-[10px] bg-transparent text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-lg font-bold">فعال</span>'
            : '<span class="text-[10px] bg-transparent text-slate-500 dark:text-slate-400 border border-slate-400/30 px-2 py-0.5 rounded-lg font-medium">غیرفعال</span>';

          const trafficHtml = p.traffic_gb > 0
            ? `<span class="inline-flex items-center justify-center gap-1 font-mono font-bold" dir="rtl"><span class="text-cyan-400 text-[10px]">GB</span><span class="text-cyan-300 text-xs">${p.traffic_gb}</span></span>`
            : '<span class="text-cyan-300 font-bold">نامحدود</span>';
          const durationText = p.duration_days > 0 ? `${p.duration_days} روز` : 'نامحدود';
          const hwidText = p.hwid_limit > 0 ? `${p.hwid_limit} کاربر` : 'پیش‌فرض';

          const rawName = (p.name || '').trim();
          const emojiRegex = /([\uD800-\uDBFF][\uDC00-\uDFFF]|[\u2600-\u27BF]|\p{Extended_Pictographic}|\p{Emoji_Presentation})/u;
          const emojiMatch = rawName.match(emojiRegex);
          const pkgIcon = emojiMatch ? emojiMatch[0] : '';
          const cleanName = pkgIcon ? rawName.replace(emojiRegex, '').trim() : rawName;

          return `
            <div class="plan-card bg-slate-800/80 rounded-2xl p-4 border border-slate-700/80 space-y-3 shadow transition">
              <div class="flex items-center justify-between gap-3">
                <div class="flex items-center gap-2.5 min-w-0">
                  <!-- 1. General Box Icon on the FAR RIGHT of the item -->
                  <span class="w-7 h-7 rounded-xl bg-transparent text-blue-400 border border-blue-500/30 flex items-center justify-center flex-shrink-0" title="بسته">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>
                  </span>

                  <!-- 2. Plan Name + 3. Package Emoji (on the left of the name) + 4. Status Badge -->
                  <div class="flex items-center gap-1.5 min-w-0">
                    <b class="text-white text-xs font-bold truncate">${escapeHtml(cleanName)}</b>
                    ${pkgIcon ? `<span class="text-sm select-none leading-none flex-shrink-0" title="آیکون بسته">${pkgIcon}</span>` : ''}
                    ${statusBadge}
                  </div>
                </div>

                <!-- Price on the left -->
                <span class="text-sm font-black text-emerald-400 font-mono flex-shrink-0">${formatNumber(p.price || 0)} <span class="text-[10px] font-sans font-normal text-slate-400">تومان</span></span>
              </div>

              ${p.description ? `<p class="text-[10px] text-slate-400 line-clamp-1 pr-9.5">${escapeHtml(p.description)}</p>` : ''}

              <div class="grid grid-cols-3 gap-1.5 text-center text-[10px] bg-slate-900/60 p-2 rounded-xl font-mono">
                <div>
                  <span class="text-slate-400 block text-[9px] font-sans">حجم ترافیک</span>
                  ${trafficHtml}
                </div>
                <div>
                  <span class="text-slate-400 block text-[9px] font-sans">مدت زمان</span>
                  <b class="text-amber-300">${durationText}</b>
                </div>
                <div>
                  <span class="text-slate-400 block text-[9px] font-sans">محدودیت HWID</span>
                  <b class="text-purple-300">${hwidText}</b>
                </div>
              </div>

              <div class="flex gap-2 pt-1 text-[11px]">
                <button onclick="window.adminActions.openPlanModal(${p.id})" class="flex-1 bg-transparent hover:bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/30 hover:border-blue-400/60 py-1.5 rounded-xl transition text-center flex items-center justify-center gap-1.5 font-bold active:scale-95">
                  <svg class="w-3.5 h-3.5 text-blue-500 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
                  <span>ویرایش</span>
                </button>
                <button onclick="window.adminActions.togglePlan(${p.id}, ${p.is_active})" class="flex-1 bg-transparent hover:bg-slate-500/10 ${p.is_active ? 'text-amber-600 dark:text-amber-400 border border-amber-500/30 hover:border-amber-400/60' : 'text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 hover:border-emerald-400/60'} py-1.5 rounded-xl transition font-semibold text-center active:scale-95">
                  ${p.is_active ? 'غیرفعال‌سازی' : 'فعال‌سازی'}
                </button>
                <button onclick="window.adminActions.deletePlan(${p.id}, '${escapeHtml(p.name).replace(/'/g, "\\'")}')" class="bg-transparent hover:bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/30 hover:border-rose-400/60 px-3 py-1.5 rounded-xl transition font-medium flex items-center justify-center active:scale-95" title="حذف سرویس">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                </button>
              </div>
            </div>
          `;
        }).join('');
      } catch (e) {
        container.innerHTML = '<div class="p-6 text-center text-rose-400 text-xs">خطای شبکه در دریافت تعرفه‌ها</div>';
      }
    },

    openPlanModal(planOrId = null) {
      let plan = planOrId;
      if (typeof planOrId === 'number') {
        plan = adminPlansData.find(p => p.id === planOrId) || null;
      }
      const modal = $('planModal');
      if (modal) modal.classList.remove('hidden');
      $('planModalTitle').innerText = plan ? `ویرایش تعرفه: ${plan.name}` : 'ایجاد تعرفه جدید';
      $('planModalId').value = plan ? plan.id : '';
      $('planModalName').value = plan ? plan.name : '';
      $('planModalPrice').value = plan ? plan.price : '';
      $('planModalTraffic').value = plan ? plan.traffic_gb : '';
      $('planModalDuration').value = plan ? plan.duration_days : '';
      $('planModalHwid').value = plan ? (plan.hwid_limit || '') : '';
      $('planModalDesc').value = plan ? (plan.description || '') : '';
      $('planModalActive').checked = plan ? !!plan.is_active : true;
    },

    closePlanModal() {
      $('planModal')?.classList.add('hidden');
    },

    async savePlan() {
      const id = $('planModalId')?.value;
      const name = $('planModalName')?.value?.trim();
      const price = parseInt($('planModalPrice')?.value || '0', 10);
      const traffic_gb = parseInt($('planModalTraffic')?.value || '0', 10);
      const duration_days = parseInt($('planModalDuration')?.value || '0', 10);
      const hwid_limit = parseInt($('planModalHwid')?.value || '0', 10) || null;
      const description = $('planModalDesc')?.value?.trim();
      const is_active = $('planModalActive')?.checked ?? true;

      if (!name) {
        if (window.showToast) window.showToast('نام تعرفه الزامی است.');
        return;
      }

      const saveBtn = $('planModalSaveBtn');
      if (saveBtn) { saveBtn.disabled = true; saveBtn.innerText = 'در حال ذخیره...'; }

      try {
        const payload = { id: id ? parseInt(id, 10) : undefined, name, price, traffic_gb, duration_days, hwid_limit, description, is_active };
        const res = await window.api.saveAdminPlan(payload);
        if (res && res.ok) {
          if (window.showToast) window.showToast(`✅ ${res.message}`);
          if (window.hapticFeedback) window.hapticFeedback('success');
          this.closePlanModal();
          this.fetchAdminPlans();
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ذخیره تعرفه'}`);
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطای شبکه در ذخیره تعرفه');
      } finally {
        if (saveBtn) { saveBtn.disabled = false; saveBtn.innerText = 'ذخیره سرویس'; }
      }
    },

    async togglePlan(id, is_active) {
      try {
        const res = await window.api.toggleAdminPlan(id, !is_active);
        if (res && res.ok) {
          if (window.showToast) window.showToast('✓ وضعیت تعرفه تغییر یافت');
          this.fetchAdminPlans();
        }
      } catch (e) {}
    },

    async deletePlan(id, name) {
      if (!confirm(`آیا از حذف کامل تعرفه «${name}» اطمینان دارید؟`)) return;
      try {
        const res = await window.api.deleteAdminPlan(id);
        if (res && res.ok) {
          if (window.showToast) window.showToast('✅ تعرفه با موفقیت حذف شد.');
          this.fetchAdminPlans();
        }
      } catch (e) {}
    },

    // --- Coupons Actions ---
    async fetchAdminCoupons() {
      const container = $('adminCouponsList');
      if (!container) return;
      container.innerHTML = '<div class="p-8 text-center text-xs text-slate-400">در حال دریافت کدهای تخفیف...</div>';
      try {
        const res = await window.api.getAdminCoupons();
        if (!res || !res.ok) {
          container.innerHTML = `<div class="p-6 text-center text-rose-400 text-xs">${res?.error || 'خطا در دریافت کدهای تخفیف'}</div>`;
          return;
        }
        adminCouponsData = res.coupons || [];
        if (adminCouponsData.length === 0) {
          container.innerHTML = `
            <div class="bg-slate-900/50 border border-slate-800 rounded-2xl p-6 text-center text-slate-400 space-y-3">
              <div class="w-10 h-10 rounded-2xl bg-pink-500/15 text-pink-400 flex items-center justify-center mx-auto">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z"/></svg>
              </div>
              <p class="text-xs">هیچ کد تخفیفی ایجاد نشده است.</p>
              <button onclick="window.adminActions.openCouponModal()" class="bg-gradient-to-r from-purple-600 to-pink-600 text-white text-xs font-bold px-4 py-2 rounded-xl transition shadow active:scale-95">
                + ایجاد اولین کد تخفیف
              </button>
            </div>
          `;
          return;
        }

        container.innerHTML = adminCouponsData.map(c => {
          const usedCount = c.used_count || 0;
          const statusBadge = c.is_active
            ? '<span class="text-[10px] bg-transparent text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-lg font-bold">فعال</span>'
            : (usedCount > 0
                ? '<span class="text-[10px] bg-transparent text-slate-500 dark:text-slate-400 border border-slate-400/30 px-2 py-0.5 rounded-lg font-medium">غیرفعال (مصرف‌شده)</span>'
                : '<span class="text-[10px] bg-transparent text-amber-500 dark:text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-lg font-medium">غیرفعال (استفاده‌نشده)</span>');

          const discountText = c.discount_percent > 0
            ? `<span dir="ltr">${toEnglishDigits(c.discount_percent)}%</span> تخفیف`
            : `${formatNumber(c.discount_amount || 0)} تومان`;

          const maxText = c.max_uses > 0 ? `${toEnglishDigits(usedCount)} / ${toEnglishDigits(c.max_uses)}` : `${toEnglishDigits(usedCount)} (نامحدود)`;
          const expiryText = c.expires_at_jalali || (c.expires_at ? (window.formatDateToJalali ? window.formatDateToJalali(c.expires_at) : c.expires_at) : 'نامحدود (دائمی)');

          const usagesBtnHtml = usedCount > 0
            ? `<button onclick="window.adminActions.openCouponUsages(${c.id}, '${escapeHtml(c.code).replace(/'/g, "\\'")}')" class="flex-1 bg-transparent hover:bg-pink-500/10 text-pink-600 dark:text-pink-400 border border-pink-500/30 hover:border-pink-400/60 py-1.5 rounded-xl transition font-semibold text-center flex items-center justify-center gap-1.5 active:scale-95">
                <svg class="w-3.5 h-3.5 text-pink-600 dark:text-pink-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
                <span>استفاده‌کنندگان (${formatNumber(usedCount)})</span>
              </button>`
            : `<div class="flex-1 bg-transparent text-slate-400 dark:text-slate-500 border border-slate-700/40 py-1.5 rounded-xl font-medium text-center flex items-center justify-center gap-1.5 opacity-60 cursor-not-allowed select-none">
                <svg class="w-3.5 h-3.5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
                <span>فاقد استفاده</span>
              </div>`;

          return `
            <div class="coupon-card bg-slate-800/80 rounded-2xl p-4 border border-slate-700/80 space-y-3 shadow transition">
              <div class="flex items-start justify-between">
                <div>
                  <div class="flex items-center gap-2">
                    <button type="button" onclick="window.adminActions.quickCopy('${escapeHtml(c.code).replace(/'/g, "\\'")}', 'کد تخفیف')" class="flex items-center gap-1.5 cursor-pointer bg-transparent hover:text-pink-300 text-pink-400 border-0 p-0 transition active:scale-95 group" title="کلیک جهت کپی کد تخفیف">
                      <span class="font-mono font-bold text-sm tracking-wider uppercase">${escapeHtml(c.code)}</span>
                      <svg class="w-3.5 h-3.5 text-pink-400/70 group-hover:text-pink-300 transition" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
                    </button>
                    ${statusBadge}
                  </div>
                  <span class="text-[11px] text-emerald-600 dark:text-emerald-400 font-bold block mt-1.5">${discountText}</span>
                </div>
              </div>

              <div class="grid grid-cols-2 gap-2 text-[10px] bg-transparent p-2 rounded-xl border border-slate-700/60 font-mono">
                <div>
                  <span class="text-slate-400 block text-[9px] font-sans">دفعات استفاده:</span>
                  <b class="text-slate-200">${maxText}</b>
                </div>
                <div>
                  <span class="text-slate-400 block text-[9px] font-sans">تاریخ انقضا:</span>
                  <b class="text-slate-200">${escapeHtml(expiryText)}</b>
                </div>
              </div>

              <div class="flex gap-2 pt-1 text-[11px]">
                ${usagesBtnHtml}
                <button onclick="window.adminActions.toggleCoupon(${c.id}, ${c.is_active})" class="bg-transparent hover:bg-slate-500/10 ${c.is_active ? 'text-amber-600 dark:text-amber-400 border border-amber-500/30 hover:border-amber-400/60' : 'text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 hover:border-emerald-400/60'} py-1.5 px-3 rounded-xl transition font-semibold text-center active:scale-95">
                  ${c.is_active ? 'غیرفعال‌سازی' : 'فعال‌سازی'}
                </button>
                <button onclick="window.adminActions.deleteCoupon(${c.id}, '${escapeHtml(c.code).replace(/'/g, "\\'")}')" class="bg-transparent hover:bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/30 hover:border-rose-400/60 px-3 py-1.5 rounded-xl transition font-medium flex items-center justify-center active:scale-95" title="حذف کد تخفیف">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                </button>
              </div>
            </div>
          `;
        }).join('');
      } catch (e) {
        container.innerHTML = '<div class="p-6 text-center text-rose-400 text-xs">خطای شبکه در دریافت کدهای تخفیف</div>';
      }
    },

    openCouponModal() {
      $('couponModal')?.classList.remove('hidden');
      $('couponModalCode').value = '';
      $('couponModalPercent').value = '20';
      $('couponModalAmount').value = '0';
      $('couponModalMaxUses').value = '0';
      $('couponModalDays').value = '30';
    },

    closeCouponModal() {
      $('couponModal')?.classList.add('hidden');
    },

    openBatchVoucherModal() {
      $('batchVoucherResultsBox')?.classList.add('hidden');
      $('batchVoucherModal')?.classList.remove('hidden');
    },

    closeBatchVoucherModal() {
      $('batchVoucherModal')?.classList.add('hidden');
    },

    async generateBatchVouchers() {
      const amount = parseInt($('batchVoucherAmount')?.value || '0', 10);
      const count = parseInt($('batchVoucherCount')?.value || '10', 10);
      const prefix = $('batchVoucherPrefix')?.value?.trim() || 'GIFT-';
      const max_uses = parseInt($('batchVoucherMaxUses')?.value || '1', 10);
      const expire_days = parseInt($('batchVoucherExpireDays')?.value || '30', 10);

      if (amount <= 0) {
        if (window.showToast) window.showToast('مبلغ هر کارت شارژ باید بیشتر از صفر باشد.');
        return;
      }

      const btn = $('batchVoucherGenerateBtn');
      if (btn) { btn.disabled = true; btn.innerText = 'در حال تولید...'; }

      try {
        const res = await window.api.batchGenerateVouchers({
          amount,
          count,
          prefix,
          max_uses,
          expire_days,
        });
        if (res && res.ok) {
          if (window.showToast) window.showToast(`✅ ${res.message}`);
          if (window.hapticFeedback) window.hapticFeedback('success');
          const resultsBox = $('batchVoucherResultsBox');
          const codeArea = $('batchVoucherGeneratedCodes');
          if (resultsBox && codeArea) {
            codeArea.value = (res.codes || []).join('\n');
            resultsBox.classList.remove('hidden');
          }
          this.fetchAdminCoupons();
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در تولید کارت شارژ'}`);
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطای شبکه در تولید کارت‌های شارژ');
      } finally {
        if (btn) { btn.disabled = false; btn.innerText = 'تولید و ثبت'; }
      }
    },

    copyBatchCodes() {
      const codeArea = $('batchVoucherGeneratedCodes');
      if (codeArea && codeArea.value) {
        navigator.clipboard.writeText(codeArea.value).then(() => {
          if (window.showToast) window.showToast('📋 تمام کدها در کلیپ‌بورد کپی شدند.');
        });
      }
    },

    async saveCoupon() {
      const code = $('couponModalCode')?.value?.trim();
      const discount_percent = parseInt($('couponModalPercent')?.value || '0', 10);
      const discount_amount = parseInt($('couponModalAmount')?.value || '0', 10);
      const max_uses = parseInt($('couponModalMaxUses')?.value || '0', 10);
      const expires_days = parseInt($('couponModalDays')?.value || '0', 10);

      if (!code) {
        if (window.showToast) window.showToast('کد تخفیف الزامی است.');
        return;
      }

      const saveBtn = $('couponModalSaveBtn');
      if (saveBtn) { saveBtn.disabled = true; saveBtn.innerText = 'در حال ساخت...'; }

      try {
        const payload = { code, discount_percent, discount_amount, max_uses, expires_days, is_active: true };
        const res = await window.api.saveAdminCoupon(payload);
        if (res && res.ok) {
          if (window.showToast) window.showToast(`✅ ${res.message}`);
          if (window.hapticFeedback) window.hapticFeedback('success');
          this.closeCouponModal();
          this.fetchAdminCoupons();
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ساخت کد تخفیف'}`);
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطای شبکه در ساخت کد تخفیف');
      } finally {
        if (saveBtn) { saveBtn.disabled = false; saveBtn.innerText = 'ایجاد کد تخفیف'; }
      }
    },

    async toggleCoupon(id, is_active) {
      try {
        const res = await window.api.toggleAdminCoupon(id, !is_active);
        if (res && res.ok) {
          if (window.showToast) window.showToast('✓ وضعیت کد تخفیف تغییر یافت');
          this.fetchAdminCoupons();
        }
      } catch (e) {}
    },

    openDeleteCouponModal(id, code) {
      this._pendingDeleteCouponId = id;
      const el = $('deleteCouponModalCode');
      if (el) el.innerText = code || '';
      const modal = $('deleteCouponModal');
      if (modal) modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    closeDeleteCouponModal() {
      const modal = $('deleteCouponModal');
      if (modal) modal.classList.add('hidden');
      this._pendingDeleteCouponId = null;
    },

    async executeDeleteCoupon() {
      const id = this._pendingDeleteCouponId;
      if (!id) return;
      const btn = $('confirmDeleteCouponBtn');
      if (btn) btn.disabled = true;
      try {
        const res = await window.api.deleteAdminCoupon(id);
        if (res && res.ok) {
          if (window.showToast) window.showToast('✅ کد تخفیف با موفقیت حذف شد.');
          this.closeDeleteCouponModal();
          this.fetchAdminCoupons();
          if (window.hapticFeedback) window.hapticFeedback('success');
        } else {
          if (window.showToast) window.showToast(res?.error || 'خطا در حذف کد تخفیف');
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطا در برقراری ارتباط با سرور');
      } finally {
        if (btn) btn.disabled = false;
      }
    },

    deleteCoupon(id, code) {
      this.openDeleteCouponModal(id, code);
    },

    async openCouponUsages(coupon_id, code) {
      const modal = $('couponUsagesModal');
      const subtitle = $('couponUsagesModalSubtitle');
      const list = $('couponUsagesList');
      const countStat = $('couponUsagesCountStat');
      const totalDiscStat = $('couponUsagesTotalDiscountStat');

      if (modal) modal.classList.remove('hidden');
      if (subtitle) subtitle.innerText = `کد تخفیف: ${code}`;
      if (countStat) countStat.innerText = '0 بار';
      if (totalDiscStat) totalDiscStat.innerText = '0 تومان';
      if (list) list.innerHTML = '<div class="p-6 text-center text-xs text-slate-400">در حال دریافت لیست استفاده‌کنندگان...</div>';
      if (window.hapticFeedback) window.hapticFeedback('impact');

      try {
        const res = await window.api.getAdminCouponUsages(coupon_id);
        if (!res || !res.ok) {
          if (list) list.innerHTML = `<div class="p-6 text-center text-xs text-rose-400">${res?.error || 'خطا در دریافت لیست'}</div>`;
          return;
        }

        const usages = res.usages || [];
        const totalDiscountGranted = usages.reduce((sum, u) => sum + (Number(u.discount_applied) || 0), 0);

        if (subtitle) {
          subtitle.innerText = `کد: ${res.coupon?.code || code} | تعداد کل استفاده: ${formatNumber(usages.length)} بار`;
        }
        if (countStat) countStat.innerText = `${formatNumber(usages.length)} بار`;
        if (totalDiscStat) totalDiscStat.innerText = `${formatNumber(totalDiscountGranted)} تومان`;

        if (usages.length === 0) {
          list.innerHTML = `
            <div class="bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 text-center text-slate-500 dark:text-slate-400 space-y-2">
              <div class="w-12 h-12 rounded-2xl bg-pink-500/15 text-pink-500 dark:text-pink-400 flex items-center justify-center mx-auto shadow-sm">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z"/></svg>
              </div>
              <b class="text-xs text-slate-800 dark:text-slate-300 block">بدون استفاده</b>
              <p class="text-[11px] text-slate-500 dark:text-slate-400">هیچ کاربری هنوز از این کد تخفیف استفاده نکرده است.</p>
            </div>
          `;
          return;
        }

        list.innerHTML = usages.map(u => {
          const hasUsername = Boolean(u.username);
          const displayName = u.full_name || (hasUsername ? `@${u.username}` : `کاربر ${u.telegram_id}`);
          const initial = (displayName.replace('@', '')[0] || 'U').toUpperCase();
          const avatarSrc = u.avatar_url || `/api/user/avatar?user_id=${u.telegram_id}`;
          const dateStr = u.created_at ? new Date(u.created_at).toLocaleDateString('fa-IR', { numberingSystem: 'latn', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }) : '—';
          const discountStr = u.discount_applied > 0 ? `${formatNumber(u.discount_applied)} تومان` : 'اعمال‌شده';

          return `
            <div class="coupon-usage-card bg-white dark:bg-slate-900/60 rounded-2xl p-3 border border-slate-200 dark:border-slate-700/60 space-y-2.5 shadow-sm hover:border-pink-500/40 transition">
              <!-- Top Row: Order on right, Date on top-left -->
              <div class="flex items-center justify-between border-b border-slate-200 dark:border-slate-800/80 pb-2">
                <div class="flex items-center gap-1.5 min-w-0">
                  ${u.order_id ? `<span class="text-[11px] font-mono text-cyan-600 dark:text-cyan-400 font-medium">سفارش ${u.order_id}</span>` : `<span class="text-[11px] text-slate-500 dark:text-slate-400">ثبت تخفیف</span>`}
                </div>
                <div class="text-[10px] text-slate-500 dark:text-slate-400 font-mono flex items-center gap-1" dir="ltr">
                  <svg class="w-3 h-3 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  <span>${dateStr}</span>
                </div>
              </div>

              <!-- Main Content: Name, Avatar & Price on right, Username & ID on top-left -->
              <div class="flex items-center justify-between gap-3">
                <div class="flex items-center gap-2.5 min-w-0">
                  <div class="w-10 h-10 rounded-full bg-gradient-to-tr from-pink-600 to-purple-600 text-white font-bold text-xs flex items-center justify-center flex-shrink-0 shadow-sm overflow-hidden relative">
                    <img src="${avatarSrc}" alt="Avatar" class="w-full h-full object-cover" onerror="this.classList.add('hidden'); if(this.nextElementSibling) this.nextElementSibling.classList.remove('hidden');" />
                    <span class="font-bold">${initial}</span>
                  </div>
                  <div class="min-w-0 space-y-0.5">
                    <b class="text-slate-900 dark:text-white text-xs font-bold block truncate max-w-[130px] sm:max-w-[160px] cursor-pointer hover:text-pink-400" data-copy="${escapeHtml(displayName)}" onclick="window.adminActions.quickCopy(this.dataset.copy, 'نام کاربر')" title="${escapeHtml(displayName)}">${escapeHtml(displayName)}</b>
                    <div class="flex items-baseline gap-1 text-emerald-600 dark:text-emerald-400 font-bold" dir="rtl">
                      <span class="text-xs font-black font-mono leading-none">${formatNumber(u.discount_applied || 0)}</span>
                      <span class="text-[10px] text-emerald-600/90 dark:text-emerald-500/90 font-sans">تومان</span>
                    </div>
                  </div>
                </div>

                <!-- Left column: Username on line 1, Numeric ID on line 2 (سمت چپ‌ترین نقطه، بالا و بدون ID:) -->
                <div class="flex flex-col items-start justify-center gap-0.5 font-mono text-[11px] text-slate-500 dark:text-slate-400 flex-shrink-0 text-left" dir="ltr">
                  ${hasUsername ? `
                    <div class="text-[11px] text-pink-500 dark:text-pink-400 font-mono cursor-pointer hover:underline truncate max-w-[130px] leading-tight" onclick="window.adminActions.quickCopy('@${escapeHtml(u.username)}', 'نام کاربری')" title="@${escapeHtml(u.username)}">
                      @${escapeHtml(u.username)}
                    </div>
                  ` : ''}
                  <div class="cursor-pointer hover:text-cyan-500 dark:hover:text-cyan-300 text-slate-500 dark:text-slate-400 font-mono leading-tight" onclick="window.adminActions.quickCopy('${u.telegram_id}', 'شناسه عددی')" title="شناسه عددی">
                    ${u.telegram_id}
                  </div>
                </div>
              </div>
            </div>
          `;
        }).join('');
      } catch (err) {
        if (list) list.innerHTML = '<div class="p-6 text-center text-xs text-rose-400">خطای شبکه در دریافت لیست استفاده‌کنندگان</div>';
      }
    },

    closeCouponUsagesModal() {
      $('couponUsagesModal')?.classList.add('hidden');
    },

    openUserChat(telegram_id, name, tag, topup_id) {
      activeChatTelegramId = telegram_id;
      activeChatUserName = name || String(telegram_id);
      const inputId = $('directTicketUserId');
      if (inputId) inputId.value = String(telegram_id);

      const chatContainer = $('adminChatContainer');
      if (chatContainer) chatContainer.classList.remove('hidden');

      const badgeEl = $('activeChatReceiptBadge');
      if (badgeEl) badgeEl.style.display = 'none';

      const statusBadgeEl = $('activeChatStatusBadge');
      if (statusBadgeEl) {
        if (topup_id) {
          statusBadgeEl.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30';
          statusBadgeEl.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>فیش ${topup_id}`;
        } else {
          statusBadgeEl.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-bold bg-blue-500/15 text-blue-400 border border-blue-500/30';
          statusBadgeEl.innerText = 'پشتیبانی کاربر';
        }
      }

      const nameEl = $('activeChatUserName');
      if (nameEl) nameEl.textContent = name || `کاربر ${telegram_id}`;

      const avatarEl = $('activeChatUserAvatar');
      if (avatarEl) {
        const initial = ((name || 'U').replace('@', '')[0] || 'U').toUpperCase();
        avatarEl.innerHTML = `<img src="/api/user/avatar?user_id=${telegram_id}" alt="Avatar" class="w-full h-full object-cover" onerror="this.classList.add('hidden'); if(this.nextElementSibling) this.nextElementSibling.classList.remove('hidden');" /><span class="font-bold">${initial}</span>`;
      }

      const tagEl = $('activeChatUserTag');
      if (tagEl) {
        const cleanTag = tag && tag.startsWith('@') ? tag : (name && name.startsWith('@') ? name : '');
        tagEl.textContent = cleanTag || '';
        tagEl.style.display = cleanTag ? 'block' : 'none';
      }

      const idEl = $('activeChatUserId');
      if (idEl) idEl.innerHTML = `<span onclick="window.adminActions.quickCopy('${telegram_id}', 'شناسه عددی')" class="cursor-pointer hover:text-cyan-300 transition">${telegram_id}</span>`;

      loadUserChatMessages(telegram_id);

      const msgInput = $('directTicketMsg');
      if (msgInput) {
        msgInput.placeholder = `ارسال پیام به ${name}...`;
        msgInput.focus();
      }

      if (chatContainer) {
        chatContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }

      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    closeUserChat() {
      const chatContainer = $('adminChatContainer');
      if (chatContainer) chatContainer.classList.add('hidden');
      if (window.hapticFeedback) window.hapticFeedback('light');
    },

    toggleSettingsBox(targetId) {
      if (!targetId) return;
      const targetBody = $(targetId);
      if (!targetBody) return;
      const isHidden = targetBody.classList.contains('hidden');
      const box = targetBody.closest('.settings-box, .node-card');
      const chevron = box ? box.querySelector('.settings-box-chevron, .node-chevron') : null;
      if (isHidden) {
        targetBody.classList.remove('hidden');
        chevron?.classList.add('rotate-180');
      } else {
        targetBody.classList.add('hidden');
        chevron?.classList.remove('rotate-180');
      }
      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    toggleNodeBox(targetId) {
      this.toggleSettingsBox(targetId);
    },

    async openReceiptImageModal(photoUrl, topupId) {
      const modal = $('receiptPhotoModal');
      const img = $('receiptModalImage');
      const spinner = $('receiptModalSpinner');
      const errBox = $('receiptModalError');
      const textBox = $('receiptModalTextInfo');
      const titleEl = $('receiptModalTitle');

      if (titleEl) titleEl.textContent = topupId ? `تصویر رسید فیش ${topupId}` : 'تصویر رسید واریزی';
      if (modal) modal.classList.remove('hidden');
      if (img) {
        img.src = '';
        img.classList.add('hidden');
      }
      if (textBox) textBox.classList.add('hidden');
      if (errBox) errBox.classList.add('hidden');
      if (spinner) spinner.classList.remove('hidden');

      try {
        const fetchUrl = photoUrl || `/api/admin/topup/photo?id=${encodeURIComponent(topupId || '')}`;
        let blob;
        try {
          blob = await window.api.getBlob(fetchUrl);
        } catch (fetchErr) {
          throw new Error(fetchErr.status === 404 ? 'تصویری برای این فیش یافت نشد یا ثبت نشده است.' : 'خطا در دریافت تصویر رسید از تلگرام');
        }

        if (!blob || blob.size === 0) {
          throw new Error('فایل تصویر دریافت نشد.');
        }

        const objectUrl = URL.createObjectURL(blob);
        if (img) {
          img.onload = () => {
            if (spinner) spinner.classList.add('hidden');
            img.classList.remove('hidden');
          };
          img.onerror = () => {
            if (spinner) spinner.classList.add('hidden');
            if (errBox) {
              errBox.textContent = 'خطا در نمایش تصویر رسید';
              errBox.classList.remove('hidden');
            }
          };
          img.src = objectUrl;
        }
      } catch (err) {
        if (spinner) spinner.classList.add('hidden');
        if (errBox) {
          errBox.textContent = err.message || 'خطا در بارگذاری تصویر فیش';
          errBox.classList.remove('hidden');
        }
      }

      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    showReceiptInfoModal(topupId, receiptHash, amount) {
      const modal = $('receiptPhotoModal');
      const img = $('receiptModalImage');
      const spinner = $('receiptModalSpinner');
      const errBox = $('receiptModalError');
      const textBox = $('receiptModalTextInfo');
      const textContent = $('receiptModalTextContent');
      const titleEl = $('receiptModalTitle');

      if (titleEl) titleEl.textContent = `مشخصات فیش واریزی ${topupId}`;
      if (modal) modal.classList.remove('hidden');
      if (spinner) spinner.classList.add('hidden');
      if (errBox) errBox.classList.add('hidden');
      if (img) img.classList.add('hidden');

      let cleanText = receiptHash || 'بدون اطلاعات پیگیری';
      if (cleanText.startsWith('text:')) {
        cleanText = cleanText.substring(5);
      }

      if (textContent) {
        textContent.textContent = `${cleanText}\nمبلغ: ${amount} تومان`;
      }
      if (textBox) textBox.classList.remove('hidden');

      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    closeReceiptPhotoModal() {
      const modal = $('receiptPhotoModal');
      if (modal) modal.classList.add('hidden');
    },

    openCryptoRatesModal() {
      const modal = $('cryptoRatesModal');
      if (modal) modal.classList.remove('hidden');
      this.refreshLiveCryptoRates();
      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    closeCryptoRatesModal() {
      $('cryptoRatesModal')?.classList.add('hidden');
    },

    async refreshLiveCryptoRates() {
      const container = $('cryptoRatesContent');
      if (!container) return;
      container.innerHTML = '<div class="p-6 text-center text-xs text-slate-400">در حال استعلام جدیدترین نرخ‌ها از صرافی‌های معتبر...</div>';
      try {
        const res = await window.api.getAdminCryptoRates();
        if (!res || !res.ok) {
          container.innerHTML = `<div class="p-6 text-center text-xs text-rose-400">${res?.error || 'خطا در دریافت نرخ‌ها'}</div>`;
          return;
        }

        const bestTon = res.best_ton || {};
        const bestUsdt = res.best_usdt || {};
        const bestEur = res.best_eur || {};
        window.lastLiveCryptoRates = { ton: bestTon.price, usdt: bestUsdt.price, eur: bestEur.price };
        if (bestEur.price) window.currentEurRate = bestEur.price;
        if (bestUsdt.price) window.currentUsdRate = bestUsdt.price;

        const usdtList = Object.entries(res.usdt_prices || {});
        const eurList = Object.entries(res.eur_prices || {});
        const tonList = Object.entries(res.ton_prices || {});
        const binanceUsd = res.binance_usd;
        const binanceEurUsd = res.binance_eur_usd;

        let usdtRowsHtml = '';
        if (usdtList.length > 0) {
          usdtRowsHtml = usdtList.map(([src, p]) => `
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-xl bg-slate-800/60 border border-slate-700/50 hover:border-slate-600 transition">
              <span class="text-slate-300 font-medium text-[11px]">${src}</span>
              <div class="flex items-center gap-2">
                <span class="font-mono font-bold text-slate-100 text-[11px]">${formatNumber(p)} <span class="text-[9px] text-slate-400 font-sans">تومان</span></span>
                <button onclick="window.adminActions.applySpecificRate('usdt', ${p}, this)" class="bg-transparent hover:bg-emerald-500/10 text-emerald-400 hover:text-emerald-300 border border-emerald-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
                  اعمال
                </button>
              </div>
            </div>
          `).join('');
        }

        let eurRowsHtml = '';
        if (eurList.length > 0) {
          eurRowsHtml = eurList.map(([src, p]) => `
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-xl bg-slate-800/60 border border-slate-700/50 hover:border-slate-600 transition">
              <span class="text-slate-300 font-medium text-[11px]">${src}</span>
              <div class="flex items-center gap-2">
                <span class="font-mono font-bold text-slate-100 text-[11px]">${formatNumber(p)} <span class="text-[9px] text-slate-400 font-sans">تومان</span></span>
                <button onclick="window.adminActions.applySpecificRate('eur', ${p}, this)" class="bg-transparent hover:bg-indigo-500/10 text-indigo-400 hover:text-indigo-300 border border-indigo-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
                  اعمال
                </button>
              </div>
            </div>
          `).join('');
        }

        let tonRowsHtml = '';
        if (tonList.length > 0) {
          tonRowsHtml = tonList.map(([src, p]) => `
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-xl bg-slate-800/60 border border-slate-700/50 hover:border-slate-600 transition">
              <span class="text-slate-300 font-medium text-[11px]">${src}</span>
              <div class="flex items-center gap-2">
                <span class="font-mono font-bold text-slate-100 text-[11px]">${formatNumber(p)} <span class="text-[9px] text-slate-400 font-sans">تومان</span></span>
                <button onclick="window.adminActions.applySpecificRate('ton', ${p}, this)" class="bg-transparent hover:bg-cyan-500/10 text-cyan-400 hover:text-cyan-300 border border-cyan-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
                  اعمال
                </button>
              </div>
            </div>
          `).join('');
        }

        if (binanceUsd) {
          const tonTomanBinance = bestTon.price;
          tonRowsHtml += `
            <div class="flex items-center justify-between py-1.5 px-2.5 rounded-xl bg-slate-800/60 border border-slate-700/50 hover:border-slate-600 transition">
              <span class="text-slate-300 font-medium text-[11px]">بایننس (جهانی)</span>
              <div class="flex items-center gap-2">
                <span class="font-mono font-bold text-cyan-300 text-[11px]">$${Number(binanceUsd).toFixed(2)}</span>
                ${tonTomanBinance ? `
                <button onclick="window.adminActions.applySpecificRate('ton', ${tonTomanBinance}, this)" class="bg-transparent hover:bg-cyan-500/10 text-cyan-400 hover:text-cyan-300 border border-cyan-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
                  اعمال
                </button>` : ''}
              </div>
            </div>
          `;
        }

        container.innerHTML = `
          <!-- All USDT Exchanges List -->
          <div class="space-y-1.5">
            <span class="text-[10px] font-bold text-slate-400 block px-1">استعلام صرافی‌های داخلی (USDT):</span>
            <div class="space-y-1">
              ${usdtRowsHtml || '<div class="text-[10px] text-slate-500 text-center py-1">اطلاعاتی دریافت نشد</div>'}
            </div>
          </div>

          <!-- All EUR Rates List -->
          <div class="space-y-1.5 mt-3">
            <span class="text-[10px] font-bold text-slate-400 block px-1">استعلام نرخ ارز یورو (EUR):</span>
            <div class="space-y-1">
              ${eurRowsHtml || '<div class="text-[10px] text-slate-500 text-center py-1">اطلاعاتی دریافت نشد</div>'}
            </div>
          </div>

          <!-- All TON Exchanges List -->
          <div class="space-y-1.5 mt-3">
            <span class="text-[10px] font-bold text-slate-400 block px-1">استعلام صرافی‌ها (TON):</span>
            <div class="space-y-1">
              ${tonRowsHtml || '<div class="text-[10px] text-slate-500 text-center py-1">اطلاعاتی دریافت نشد</div>'}
            </div>
          </div>

          <!-- Stars Auto-Calculation from Live USDT Benchmark -->
          <div class="space-y-1.5 mt-3 pt-2.5 border-t border-slate-700/60">
            <div class="flex items-center justify-between px-1">
              <span id="modalStarsBenchmarkTitle" class="text-[10px] font-bold text-amber-400">⭐️ نرخ پیشنهادی استارز تلگرام:</span>
            </div>
            <div class="space-y-1.5">
              <div class="flex items-center justify-between py-1.5 px-2.5 rounded-xl bg-slate-800/60 border border-slate-700/50 hover:border-slate-600 transition">
                <div>
                  <span class="text-slate-200 font-bold text-[11px] block">🛡️ فرمول بدون ضرر</span>
                  <span class="text-[9px] text-slate-400">نقد کردن با کسر کارمزد تلگرام</span>
                </div>
                <div class="flex items-center gap-2">
                  <span id="modalStarsLosslessPrice" class="font-mono font-bold text-amber-300 text-[11px]"></span>
                  <button id="modalStarsLosslessBtn" class="bg-transparent hover:bg-amber-500/10 text-amber-400 hover:text-amber-300 border border-amber-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
                    اعمال
                  </button>
                </div>
              </div>
              <div class="flex items-center justify-between py-1.5 px-2.5 rounded-xl bg-slate-800/60 border border-slate-700/50 hover:border-slate-600 transition">
                <div>
                  <span class="text-slate-200 font-bold text-[11px] block">🏷️ نرخ خرید فرگمنت</span>
                  <span class="text-[9px] text-slate-400">بر اساس قیمت خرید استارز در فرگمنت</span>
                </div>
                <div class="flex items-center gap-2">
                  <span id="modalStarsFragmentPrice" class="font-mono font-bold text-blue-300 text-[11px]"></span>
                  <button id="modalStarsFragmentBtn" class="bg-transparent hover:bg-blue-500/10 text-blue-400 hover:text-blue-300 border border-blue-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
                    اعمال
                  </button>
                </div>
              </div>
            </div>
          </div>
        `;

        const initialUsdt = bestUsdt.price || window.lastLiveCryptoRates?.usdt || window.currentUsdRate || 95000;
        this.updateModalStarsRates(initialUsdt);
      } catch (e) {
        container.innerHTML = '<div class="p-6 text-center text-xs text-rose-400">خطای ارتباط با سرور در استعلام نرخ‌ها</div>';
      }
    },

    updateModalStarsRates(usdtPrice) {
      const p = parseInt(usdtPrice || '0', 10) || window.currentUsdRate || 95000;
      const lossless = Math.round(p * 0.013);
      const fragment = Math.round(p * 0.015);

      const titleEl = $('modalStarsBenchmarkTitle');
      if (titleEl) titleEl.textContent = `⭐️ نرخ پیشنهادی استارز تلگرام (بر اساس دلار ${formatNumber(p)} ت):`;

      const losslessPriceEl = $('modalStarsLosslessPrice');
      if (losslessPriceEl) losslessPriceEl.innerHTML = `${formatNumber(lossless)} <span class="text-[9px] text-slate-400 font-sans">تومان</span>`;

      const fragmentPriceEl = $('modalStarsFragmentPrice');
      if (fragmentPriceEl) fragmentPriceEl.innerHTML = `${formatNumber(fragment)} <span class="text-[9px] text-slate-400 font-sans">تومان</span>`;

      const losslessBtn = $('modalStarsLosslessBtn');
      if (losslessBtn) {
        losslessBtn.onclick = () => window.adminActions.applySpecificRate('stars', lossless, losslessBtn);
        losslessBtn.textContent = 'اعمال';
        losslessBtn.classList.remove('bg-emerald-500/20', 'text-emerald-300', 'border-emerald-500');
      }

      const fragmentBtn = $('modalStarsFragmentBtn');
      if (fragmentBtn) {
        fragmentBtn.onclick = () => window.adminActions.applySpecificRate('stars', fragment, fragmentBtn);
        fragmentBtn.textContent = 'اعمال';
        fragmentBtn.classList.remove('bg-emerald-500/20', 'text-emerald-300', 'border-emerald-500');
      }
    },

    async applySpecificRate(type, val, btnEl) {
      if (!val) return;
      const numVal = parseInt(val, 10);
      if (isNaN(numVal) || numVal <= 0) return;

      if (!window.lastLiveCryptoRates) window.lastLiveCryptoRates = {};
      window.lastLiveCryptoRates[type] = numVal;

      const payload = {};
      if (type === 'usdt') {
        const inp = $('settingUsdtRate');
        if (inp) inp.value = numVal;
        payload.usdt_rate_toman = numVal;
        window.currentUsdRate = numVal;
        this.updateStarsHint();
        this.updateModalStarsRates(numVal);
      } else if (type === 'eur') {
        const inp = $('settingEurRate');
        if (inp) inp.value = numVal;
        payload.eur_rate_toman = numVal;
        window.currentEurRate = numVal;
      } else if (type === 'ton') {
        const inp = $('settingTonRate');
        if (inp) inp.value = numVal;
        payload.ton_rate_toman = numVal;
      } else if (type === 'stars') {
        const inp = $('settingStarsRate');
        if (inp) inp.value = numVal;
        payload.stars_rate_toman = numVal;
      }

      if (btnEl) {
        const parent = btnEl.closest('.space-y-1') || btnEl.closest('.space-y-1\\.5');
        if (parent) {
          parent.querySelectorAll('button').forEach(b => {
            b.textContent = 'اعمال';
            b.classList.remove('bg-emerald-500/20', 'text-emerald-300', 'border-emerald-500');
          });
        }
        btnEl.textContent = '✓ اعمال شد';
        btnEl.classList.add('bg-emerald-500/20', 'text-emerald-300', 'border-emerald-500');
      }

      try {
        const res = await window.api.saveAdminSettings(payload);
        if (res && res.ok) {
          const typeName = type === 'usdt' ? 'تتر' : (type === 'eur' ? 'یورو' : (type === 'ton' ? 'تون' : 'استارز'));
          if (window.showToast) window.showToast(`✅ نرخ ${typeName} به ${formatNumber(numVal)} تومان ذخیره شد`);
          if (window.hapticFeedback) window.hapticFeedback('success');
        } else {
          if (window.showToast) window.showToast(`⚠️ نرخ تنظیم شد اما در سرور ذخیره نشد: ${res?.error || ''}`);
        }
      } catch (err) {
        if (window.showToast) window.showToast('خطا در ذخیره نرخ در سرور');
      }
    },

    async applyLiveCryptoRates() {
      const usdtInp = $('settingUsdtRate');
      const eurInp = $('settingEurRate');
      const tonInp = $('settingTonRate');
      const starsInp = $('settingStarsRate');

      const usdtVal = window.lastLiveCryptoRates?.usdt || parseInt(usdtInp?.value || '95000', 10);
      const tonVal = window.lastLiveCryptoRates?.ton || parseInt(tonInp?.value || '0', 10);
      const eurVal = window.lastLiveCryptoRates?.eur || parseInt(eurInp?.value || '105000', 10);
      const starsVal = window.lastLiveCryptoRates?.stars || parseInt(starsInp?.value || '0', 10) || Math.round(usdtVal * 0.013);

      if (usdtInp && usdtVal) {
        usdtInp.value = usdtVal;
        window.currentUsdRate = usdtVal;
      }
      if (tonInp && tonVal) tonInp.value = tonVal;
      if (eurInp && eurVal) {
        eurInp.value = eurVal;
        window.currentEurRate = eurVal;
      }
      if (starsInp && starsVal) starsInp.value = starsVal;

      try {
        const payload = {
          usdt_rate_toman: usdtVal,
          ton_rate_toman: tonVal,
          eur_rate_toman: eurVal,
          stars_rate_toman: starsVal,
        };
        const res = await window.api.saveAdminSettings(payload);
        if (res && res.ok) {
          if (window.showToast) window.showToast('✅ تمامی نرخ‌ها با موفقیت ذخیره شدند');
          this.closeCryptoRatesModal();
          this.updateStarsHint();
          if (window.hapticFeedback) window.hapticFeedback('success');
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ثبت نرخ‌ها'}`);
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطا در ذخیره نرخ‌ها');
      }
    },

    // --- Users Bulk Actions Modal ---
    currentBulkActionType: 'add_traffic',

    openBulkUsersModal() {
      const modal = $('bulkUsersModal');
      if (modal) modal.classList.remove('hidden');
      this.setBulkActionType('add_traffic');
      const valInput = $('bulkAmountInput');
      if (valInput) valInput.value = '5';
      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    closeBulkUsersModal() {
      const modal = $('bulkUsersModal');
      if (modal) modal.classList.add('hidden');
    },

    setBulkActionType(type = 'add_traffic') {
      this.currentBulkActionType = type;
      const trafficBtn = $('bulkTypeBtn_traffic');
      const daysBtn = $('bulkTypeBtn_days');
      const labelEl = $('bulkAmountLabel');
      const inputEl = $('bulkAmountInput');

      const activeClass = 'py-1.5 rounded-xl font-bold bg-blue-600 text-white shadow text-center flex items-center justify-center gap-1.5 transition';
      const inactiveClass = 'py-1.5 rounded-xl text-slate-400 hover:text-white font-medium text-center flex items-center justify-center gap-1.5 transition';

      if (type === 'add_traffic') {
        if (trafficBtn) trafficBtn.className = activeClass;
        if (daysBtn) daysBtn.className = inactiveClass;
        if (labelEl) labelEl.innerText = 'مقدار حجم هدیه (گیگابایت):';
        if (inputEl) inputEl.value = '5';
      } else {
        if (trafficBtn) trafficBtn.className = inactiveClass;
        if (daysBtn) daysBtn.className = activeClass;
        if (labelEl) labelEl.innerText = 'تعداد روز تمدید (روز):';
        if (inputEl) inputEl.value = '7';
      }
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    async submitBulkUsersAction() {
      const amount = parseInt($('bulkAmountInput')?.value, 10);
      if (!amount || amount <= 0) {
        if (window.showToast) window.showToast('⚠️ لطفاً مقدار معتبری وارد کنید.');
        return;
      }

      const audience = $('bulkTargetSelect')?.value || 'all_active';
      const typeText = this.currentBulkActionType === 'add_traffic' ? `${amount} گیگابایت حجم` : `${amount} روز اعتبار`;
      const audText = audience === 'all_active' ? 'تمام کاربران فعال' : 'تمام کاربران پنل';

      if (!confirm(`آیا از اعمال گروهی (${typeText}) برای ${audText} اطمینان دارید؟`)) {
        return;
      }

      const btn = $('bulkSubmitBtn');
      const txt = $('bulkSubmitText');
      const spin = $('bulkSubmitSpinner');

      if (btn) btn.disabled = true;
      if (spin) spin.classList.remove('hidden');
      if (txt) txt.innerText = 'در حال اعمال عملیات...';

      try {
        const res = await window.api.bulkUsersAction({
          action_type: this.currentBulkActionType,
          value: amount,
          audience: audience,
        });

        if (res && res.ok) {
          if (window.showToast) window.showToast(`✅ ${res.message || 'عملیات گروهی انجام شد'}`);
          if (window.hapticFeedback) window.hapticFeedback('success');
          this.closeBulkUsersModal();
          syncAdminOverview(true);
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || res?.message || 'خطا در عملیات گروهی'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (err) {
        if (window.showToast) window.showToast('خطای شبکه در ارتباط با سرور.');
      } finally {
        if (btn) btn.disabled = false;
        if (spin) spin.classList.add('hidden');
        if (txt) txt.innerText = 'اعمال عملیات گروهی';
      }
    },

    // --- Node Infra-Billing & Cost Actions ---
    openNodeBillingModal(nodeUuid, nodeName, provider = '', costToman = 0, costEur = 0, dueDate = '', notes = '', flag = '🖥️', currency = 'EUR') {
      const modal = $('nodeBillingModal');
      if (!modal) return;
      $('nodeBillingUuid').value = nodeUuid || '';
      $('nodeBillingName').value = nodeName || '';
      $('nodeBillingModalTitle').innerText = nodeName ? `هزینه و تمدید: ${nodeName}` : 'هزینه و تمدید سرور';
      $('nodeBillingModalFlag').innerText = flag || '🖥️';
      $('nodeBillingProvider').value = provider || '';
      $('nodeBillingCostToman').value = costToman || '';
      $('nodeBillingCostEur').value = costEur || '';
      $('nodeBillingDueDate').value = dueDate ? dueDate.slice(0, 10) : '';
      $('nodeBillingNotes').value = notes || '';

      const jalaliPreview = $('nodeBillingJalaliPreview');
      if (jalaliPreview) {
        jalaliPreview.innerText = dueDate ? (window.formatDateToJalali ? window.formatDateToJalali(dueDate) : dueDate.slice(0, 10)) : '';
      }

      this.setNodeBillingCurrency(currency || 'EUR', false);
      this.updateNodeBillingConversion(false);

      modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    setNodeBillingCurrency(curr = 'EUR', recalculate = true) {
      const isEur = String(curr).toUpperCase() === 'EUR';
      const hiddenInput = $('nodeBillingCurrency');
      if (hiddenInput) hiddenInput.value = isEur ? 'EUR' : 'USD';

      const eurBtn = $('nodeBillingCurrEur');
      const usdBtn = $('nodeBillingCurrUsd');
      const symbolSpan = $('nodeBillingCurrencySymbol');

      if (eurBtn && usdBtn) {
        if (isEur) {
          eurBtn.className = 'flex-1 h-full rounded-lg text-xs font-bold transition flex items-center justify-center text-white bg-blue-600 shadow';
          usdBtn.className = 'flex-1 h-full rounded-lg text-xs font-medium transition flex items-center justify-center text-slate-400 hover:text-white';
        } else {
          usdBtn.className = 'flex-1 h-full rounded-lg text-xs font-bold transition flex items-center justify-center text-white bg-blue-600 shadow';
          eurBtn.className = 'flex-1 h-full rounded-lg text-xs font-medium transition flex items-center justify-center text-slate-400 hover:text-white';
        }
      }
      if (symbolSpan) {
        symbolSpan.innerText = isEur ? '€' : '$';
      }

      if (recalculate) {
        this.updateNodeBillingConversion(true);
      }
    },

    addDaysToNodeBillingDueDate(days = 30) {
      const input = $('nodeBillingDueDate');
      const jalaliPreview = $('nodeBillingJalaliPreview');
      if (!input) return;
      const baseDate = new Date();
      baseDate.setDate(baseDate.getDate() + Number(days));
      const yyyy = baseDate.getFullYear();
      const mm = String(baseDate.getMonth() + 1).padStart(2, '0');
      const dd = String(baseDate.getDate()).padStart(2, '0');
      const isoStr = `${yyyy}-${mm}-${dd}`;
      input.value = isoStr;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      if (jalaliPreview) {
        jalaliPreview.innerText = window.formatDateToJalali ? window.formatDateToJalali(isoStr) : isoStr;
      }
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    clearNodeBillingDueDate() {
      const input = $('nodeBillingDueDate');
      const jalaliPreview = $('nodeBillingJalaliPreview');
      if (input) {
        input.value = '';
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
      if (jalaliPreview) jalaliPreview.innerText = '';
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    switchAdminAppsTab(osKey = 'ios') {
      const osList = ['ios', 'android', 'windows', 'macos', 'linux'];
      osList.forEach(os => {
        const tabBtn = $(`adminAppTab_${os}`);
        const pane = $(`adminAppsPane_${os}`);
        const isTarget = os === osKey;
        if (tabBtn) {
          if (isTarget) {
            tabBtn.className = 'admin-app-os-tab flex-1 py-1.5 px-2 rounded-lg font-bold text-[11px] whitespace-nowrap transition flex items-center justify-center gap-1 bg-cyan-600 text-white shadow';
          } else {
            tabBtn.className = 'admin-app-os-tab flex-1 py-1.5 px-2 rounded-lg font-medium text-[11px] whitespace-nowrap text-slate-400 hover:text-slate-200 transition flex items-center justify-center gap-1';
          }
        }
        if (pane) {
          if (isTarget) {
            pane.classList.remove('hidden');
          } else {
            pane.classList.add('hidden');
          }
        }
      });
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    updateNodeBillingConversion(forceRecalcToman = false) {
      const curr = ($('nodeBillingCurrency')?.value || 'EUR').toUpperCase();
      const valInput = $('nodeBillingCostEur');
      const tomanInput = $('nodeBillingCostToman');
      const hint = $('nodeBillingEurConvertHint');
      const text = $('nodeBillingEurConvertText');
      if (!valInput || !hint || !text) return;

      const numVal = parseFloat(valInput.value || '0');
      if (!isNaN(numVal) && numVal > 0) {
        const rate = curr === 'USD' ? (window.currentUsdRate || 95000) : (window.currentEurRate || 105000);
        const symbol = curr === 'USD' ? '$' : '€';
        const convertedToman = Math.round(numVal * rate);
        if (tomanInput && (forceRecalcToman || document.activeElement === valInput || !tomanInput.value)) {
          tomanInput.value = convertedToman;
        }
        const currentTomanVal = parseInt(tomanInput?.value || '0', 10);
        text.innerText = `${numVal}${symbol} × ${formatNumber(rate)} = ${formatNumber(currentTomanVal || convertedToman)} تومان`;
        hint.classList.remove('hidden');
      } else {
        hint.classList.add('hidden');
      }
    },

    closeNodeBillingModal() {
      const modal = $('nodeBillingModal');
      if (modal) modal.classList.add('hidden');
    },

    async saveNodeBilling() {
      const node_uuid = $('nodeBillingUuid')?.value?.trim();
      const node_name = $('nodeBillingName')?.value?.trim();
      const provider = $('nodeBillingProvider')?.value?.trim();
      const monthly_cost_toman = parseInt($('nodeBillingCostToman')?.value || '0', 10);
      const monthly_cost_eur = parseFloat($('nodeBillingCostEur')?.value || '0');
      const currency = ($('nodeBillingCurrency')?.value || 'EUR').toUpperCase();
      const due_date = $('nodeBillingDueDate')?.value?.trim() || null;
      const notes = $('nodeBillingNotes')?.value?.trim();

      if (!node_uuid) {
        if (window.showToast) window.showToast('شناسه سرور یافت نشد.');
        return;
      }

      const saveBtn = $('saveNodeBillingBtn');
      if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<span>در حال ذخیره...</span>';
      }

      try {
        const payload = {
          node_uuid,
          node_name,
          provider,
          monthly_cost_toman,
          monthly_cost_eur,
          currency,
          due_date,
          notes,
        };
        const res = await window.api.saveNodeCost(payload);
        if (res && res.ok) {
          if (window.showToast) window.showToast('✅ اطلاعات مالی و تمدید سرور با موفقیت ثبت شد');
          if (window.hapticFeedback) window.hapticFeedback('success');
          this.closeNodeBillingModal();
          syncAdminOverview(true);
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ذخیره هزینه‌های سرور'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (err) {
        if (window.showToast) window.showToast('خطای شبکه در ذخیره اطلاعات سرور');
      } finally {
        if (saveBtn) {
          saveBtn.disabled = false;
          saveBtn.innerHTML = '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg><span>ذخیره اطلاعات سرور</span>';
        }
      }
    },

    // --- Ad Campaigns & Deep-link Tracking Actions ---
    openCreateCampaignModal() {
      const modal = $('createCampaignModal');
      if (!modal) return;
      const n = $('campaignNameInput');
      const c = $('campaignCodeInput');
      const co = $('campaignCostInput');
      if (n) n.value = '';
      if (c) c.value = '';
      if (co) co.value = '';
      modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    closeCreateCampaignModal() {
      const modal = $('createCampaignModal');
      if (modal) modal.classList.add('hidden');
    },

    async submitCreateCampaign(e) {
      if (e) e.preventDefault();
      const name = $('campaignNameInput')?.value?.trim();
      const code = $('campaignCodeInput')?.value?.trim().toLowerCase();
      const cost = parseInt($('campaignCostInput')?.value || '0', 10);

      if (!name || !code) {
        if (window.showToast) window.showToast('⚠️ نام و شناسه کمپین الزامی است.');
        return;
      }

      const submitBtn = $('createCampaignSubmitBtn');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = 'در حال ساخت...';
      }

      try {
        const res = await window.api.createAdminCampaign({ name, code, cost });
        if (res && res.ok) {
          if (window.showToast) window.showToast('✅ کمپین و لینک با موفقیت ایجاد شد.');
          if (window.hapticFeedback) window.hapticFeedback('success');
          this.closeCreateCampaignModal();
          this.fetchAdminCampaigns();
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ساخت کمپین'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (err) {
        if (window.showToast) window.showToast('خطای شبکه در ارتباط با سرور.');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerText = 'ساخت لینک';
        }
      }
    },

    async deleteCampaign(id, name) {
      if (!confirm(`آیا از حذف کمپین «${name}» اطمینان دارید؟`)) return;
      try {
        const res = await window.api.deleteAdminCampaign(id);
        if (res && res.ok) {
          if (window.showToast) window.showToast('🗑 کمپین با موفقیت حذف شد.');
          if (window.hapticFeedback) window.hapticFeedback('success');
          this.fetchAdminCampaigns();
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در حذف کمپین'}`);
        }
      } catch (err) {
        if (window.showToast) window.showToast('خطای شبکه در حذف کمپین.');
      }
    },

    copyCampaignLink(deepLink) {
      if (!deepLink) return;
      let finalLink = deepLink;
      const botUser = window.botUsername || window.Telegram?.WebApp?.initDataUnsafe?.bot?.username || '';
      if (botUser && finalLink.includes('t.me/?start=')) {
        finalLink = finalLink.replace('t.me/?start=', `t.me/${botUser}?start=`);
      }
      if (!finalLink.startsWith('https://') && !finalLink.startsWith('http://')) {
        finalLink = 'https://' + finalLink;
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(finalLink).then(() => {
          if (window.showToast) window.showToast('📋 لینک تبلیغاتی کپی شد: ' + finalLink);
          if (window.hapticFeedback) window.hapticFeedback('light');
        }).catch(() => {
          prompt('لینک تبلیغاتی:', finalLink);
        });
      } else {
        prompt('لینک تبلیغاتی:', finalLink);
      }
    },

    async fetchAdminCampaigns() {
      const container = $('adminCampaignsList');
      if (!container) return;

      container.innerHTML = `
        <div class="p-6 rounded-2xl bg-transparent border border-slate-700/50 text-center text-xs text-slate-400">
          در حال بارگذاری لیست کمپین‌ها...
        </div>
      `;

      try {
        const res = await window.api.getAdminCampaigns();
        if (!res || !res.ok) {
          container.innerHTML = '<div class="p-6 text-center text-xs text-rose-400">خطا در بارگذاری لیست کمپین‌ها</div>';
          return;
        }

        if (res.bot_username) window.botUsername = res.bot_username;
        const botUser = window.botUsername || window.Telegram?.WebApp?.initDataUnsafe?.bot?.username || '';
        const campaigns = res.campaigns || [];
        if (campaigns.length === 0) {
          container.innerHTML = `
            <div class="p-8 rounded-2xl bg-slate-800/40 border border-slate-700/60 text-center space-y-2">
              <div class="w-12 h-12 mx-auto rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z"/></svg>
              </div>
              <p class="text-xs text-white font-bold">هنوز هیچ کمپین یا لینکی ساخته نشده است</p>
              <p class="text-[11px] text-slate-400">با ساخت اولین لینک تبلیغاتی، می‌توانید ورودی‌ها و خرید کاربران از کانال‌ها و افراد مختلف را ردیابی کنید.</p>
            </div>
          `;
          return;
        }

        container.innerHTML = campaigns.map(c => {
          let link = c.deep_link || '';
          if (botUser && link.includes('t.me/?start=')) {
            link = link.replace('t.me/?start=', `t.me/${botUser}?start=`);
          }
          if (!link.startsWith('https://') && !link.startsWith('http://')) {
            link = 'https://' + link;
          }
          const roiText = c.roi !== null && c.roi !== undefined ? `${c.roi > 0 ? '+' : ''}${c.roi}%` : null;
          const roiColor = c.roi !== null && c.roi > 0 ? 'text-emerald-400' : (c.roi !== null && c.roi < 0 ? 'text-rose-400' : 'text-slate-400');
          const costText = c.cost ? `${formatNumber(c.cost)} تومان` : 'بدون هزینه (۰ تومان)';

          return `
            <div class="bg-slate-800/80 p-3.5 rounded-2xl border border-slate-700/80 space-y-3 transition hover:border-slate-600">
              <!-- Top Row: Name & Actions -->
              <div class="flex items-center justify-between gap-2">
                <div class="flex items-center gap-2 min-w-0">
                  <div class="w-8 h-8 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-400 flex items-center justify-center flex-shrink-0">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z"/></svg>
                  </div>
                  <div class="min-w-0">
                    <b class="text-xs text-white block truncate">${escapeHtml(c.name)}</b>
                    <span class="text-[10px] font-mono text-cyan-400 dir-ltr block mt-0.5">ad_${escapeHtml(c.code)}</span>
                  </div>
                </div>
                <div class="flex items-center gap-1.5 flex-shrink-0">
                  <button type="button" onclick="window.adminActions.copyCampaignLink('${escapeHtml(c.deep_link).replace(/'/g, "\\'")}')" class="px-2.5 py-1 bg-transparent hover:bg-cyan-500/10 text-cyan-400 border border-cyan-500/40 rounded-xl text-[10px] font-bold transition flex items-center gap-1 active:scale-95 shadow-sm" title="کپی لینک اختصاصی">
                    <span>کپی لینک</span>
                  </button>
                  <button type="button" onclick="window.adminActions.deleteCampaign(${c.id}, '${escapeHtml(c.name).replace(/'/g, "\\'")}')" class="w-7 h-7 bg-transparent hover:bg-rose-500/10 text-rose-400 border border-rose-500/40 rounded-xl flex items-center justify-center transition active:scale-95" title="حذف کمپین">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                  </button>
                </div>
              </div>

              <!-- Stats Grid -->
              <div class="grid grid-cols-4 gap-2 pt-1 border-t border-slate-700/50 text-center">
                <div class="p-2 rounded-xl bg-slate-900/40 border border-slate-700/40">
                  <span class="text-[9px] text-slate-400 block mb-0.5">ورودی جدید</span>
                  <b class="text-xs font-mono text-white">${formatNumber(c.users_count)}</b>
                </div>
                <div class="p-2 rounded-xl bg-slate-900/40 border border-slate-700/40">
                  <span class="text-[9px] text-slate-400 block mb-0.5">خریداران</span>
                  <b class="text-xs font-mono text-cyan-300">${formatNumber(c.buyers_count)}</b>
                </div>
                <div class="p-2 rounded-xl bg-slate-900/40 border border-slate-700/40">
                  <span class="text-[9px] text-slate-400 block mb-0.5">درآمد فروش</span>
                  <b class="text-xs font-mono text-emerald-400">${formatNumber(c.total_revenue)}</b>
                </div>
                <div class="p-2 rounded-xl bg-slate-900/40 border border-slate-700/40">
                  <span class="text-[9px] text-slate-400 block mb-0.5">بازگشت (ROI)</span>
                  <b class="text-xs font-mono ${roiColor} inline-block" dir="ltr">${roiText || '—'}</b>
                </div>
              </div>

              <!-- Deep Link preview row -->
              <div class="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-700/30">
                <span class="truncate dir-ltr font-mono text-slate-400" dir="ltr">${c.deep_link}</span>
                <span class="flex-shrink-0 text-[9px] text-slate-400 mr-2">${costText}</span>
              </div>
            </div>
          `;
        }).join('');
      } catch (e) {
        container.innerHTML = '<div class="p-6 text-center text-xs text-rose-400">خطای شبکه در بارگذاری کمپین‌ها</div>';
      }
    },

    calcStarsRate(mode = 'lossless') {
      const usdtInp = $('settingUsdtRate');
      const usdtVal = parseInt(usdtInp?.value || '0', 10) || window.currentUsdRate || 95000;
      const multiplier = mode === 'fragment' ? 0.015 : 0.013;
      const calculated = Math.round(usdtVal * multiplier);
      const starsInp = $('settingStarsRate');
      if (starsInp) {
        starsInp.value = calculated;
        if (window.hapticFeedback) window.hapticFeedback('success');
        const modeLabel = mode === 'fragment' ? 'فرگمنت (۰.۰۱۵$)' : 'بدون ضرر (۰.۰۱۳$)';
        if (window.showToast) window.showToast(`✅ نرخ استارز بر اساس دلار ${formatNumber(usdtVal)} تومان روی ${formatNumber(calculated)} ت (${modeLabel}) تنظیم شد`);
      }
      this.updateStarsHint();
    },

    updateStarsHint() {},

    // --- Access Mode Modal (حالت دسترسی ربات) ---
    openAccessModeModal() {
      const modal = $('accessModeModal');
      if (modal) modal.classList.remove('hidden');
      const curMode = $('settingAccessMode')?.value || 'open';
      this.highlightAccessModeOption(curMode);
      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    closeAccessModeModal() {
      $('accessModeModal')?.classList.add('hidden');
    },

    highlightAccessModeOption(mode) {
      document.querySelectorAll('.access-mode-opt').forEach(el => {
        el.classList.remove('border-emerald-500', 'border-cyan-500', 'border-rose-500', 'bg-emerald-500/10', 'bg-cyan-500/10', 'bg-rose-500/10');
        const dot = el.querySelector('.radio-dot');
        if (dot) dot.classList.add('hidden');
        const radio = el.querySelector('.radio-check');
        if (radio) radio.classList.remove('border-emerald-400', 'border-cyan-400', 'border-rose-400');
      });

      const activeEl = $(`accessOpt-${mode}`);
      if (activeEl) {
        const color = mode === 'open' ? 'emerald' : (mode === 'invite_only' ? 'cyan' : 'rose');
        activeEl.classList.add(`border-${color}-500`, `bg-${color}-500/10`);
        const dot = activeEl.querySelector('.radio-dot');
        if (dot) dot.classList.remove('hidden');
        const radio = activeEl.querySelector('.radio-check');
        if (radio) radio.classList.add(`border-${color}-400`);
      }
    },

    async selectAccessMode(mode) {
      const inp = $('settingAccessMode');
      if (inp) inp.value = mode;
      this.renderAccessModeUI(mode);
      this.closeAccessModeModal();
      if (window.hapticFeedback) window.hapticFeedback('success');

      const isMaint = (mode === 'closed');
      const maintSwitch = $('settingMaintSwitch');
      if (maintSwitch) maintSwitch.checked = isMaint;

      try {
        const res = await window.api.saveAdminSettings({ access_mode: mode, maintenance: isMaint });
        if (res && res.ok) {
          const names = { open: 'عمومی (آزاد)', invite_only: 'فقط با دعوت', closed: 'بسته / تعمیرات' };
          if (window.showToast) window.showToast(`✓ حالت دسترسی به «${names[mode] || mode}» تغییر یافت`);
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ذخیره حالت دسترسی'}`);
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطا در ذخیره حالت دسترسی');
      }
    },

    renderAccessModeUI(mode) {
      const badge = $('accessModeBadge');
      const sub = $('accessModeSubtext');
      const icon = $('accessModeIconBox');
      const inp = $('settingAccessMode');
      if (inp) inp.value = mode;

      if (mode === 'invite_only') {
        if (badge) {
          badge.textContent = 'فقط با دعوت';
          badge.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30';
        }
        if (sub) sub.textContent = 'کاربران جدید نیازمند لینک دعوت/رفرال هستند';
        if (icon) {
          icon.textContent = '🎟️';
          icon.className = 'w-8 h-8 rounded-xl bg-cyan-500/15 border border-cyan-500/30 text-cyan-400 flex items-center justify-center text-sm flex-shrink-0';
        }
      } else if (mode === 'closed') {
        if (badge) {
          badge.textContent = 'بسته (تعمیرات)';
          badge.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30';
        }
        if (sub) sub.textContent = 'ثبت‌نام متوقف شده است؛ سرویس‌های فعلی فعالند';
        if (icon) {
          icon.textContent = '🔒';
          icon.className = 'w-8 h-8 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-400 flex items-center justify-center text-sm flex-shrink-0';
        }
      } else {
        if (badge) {
          badge.textContent = 'عمومی (آزاد)';
          badge.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30';
        }
        if (sub) sub.textContent = 'ورود و ثبت‌نام برای تمامی کاربران آزاد است';
        if (icon) {
          icon.textContent = '🌐';
          icon.className = 'w-8 h-8 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 flex items-center justify-center text-sm flex-shrink-0';
        }
      }
    },
  };

  const fetchAdminPlans = () => window.adminActions.fetchAdminPlans();
  const fetchAdminCoupons = () => window.adminActions.fetchAdminCoupons();

  $('openCreatePlanBtn')?.addEventListener('click', () => {
    window.adminActions.openPlanModal();
  });
  $('openCreateCouponBtn')?.addEventListener('click', () => {
    window.adminActions.openCouponModal();
  });

  let walletActionType = 'add';
  const walletActionAddBtn = $('walletActionAddBtn');
  const walletActionDeductBtn = $('walletActionDeductBtn');

  walletActionAddBtn?.addEventListener('click', () => {
    walletActionType = 'add';
    walletActionAddBtn.className = 'flex-1 py-1.5 text-xs font-bold rounded-xl border border-emerald-500/50 bg-emerald-950/70 text-emerald-300 transition';
    walletActionDeductBtn.className = 'flex-1 py-1.5 text-xs font-medium rounded-xl border border-slate-700 bg-slate-900/60 text-slate-400 transition';
  });

  walletActionDeductBtn?.addEventListener('click', () => {
    walletActionType = 'deduct';
    walletActionDeductBtn.className = 'flex-1 py-1.5 text-xs font-bold rounded-xl border border-rose-500/50 bg-rose-950/70 text-rose-300 transition';
    walletActionAddBtn.className = 'flex-1 py-1.5 text-xs font-medium rounded-xl border border-slate-700 bg-slate-900/60 text-slate-400 transition';
  });

  // --- 7. Pending Topups Fetcher ---
  async function fetchAdminTopups() {
    const container = $('adminPendingTopupsList');
    if (!container) return;
    container.innerHTML = '<div class="p-4 text-center text-xs text-slate-400">در حال دریافت فیش‌ها...</div>';

    try {
      const res = await window.api.getAdminTopups();
      if (!res || !res.ok) {
        container.innerHTML = `<div class="p-6 text-center text-rose-400 text-xs">${res?.error || 'خطا در دریافت فیش‌ها'}</div>`;
        return;
      }
      const topups = res.topups || [];
      if (topups.length === 0) {
        container.innerHTML = `
          <div class="bg-slate-900/40 rounded-2xl p-6 text-center text-slate-400 text-xs border border-slate-800 space-y-2">
            <div class="w-10 h-10 rounded-2xl bg-emerald-500/15 text-emerald-400 flex items-center justify-center mx-auto">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
            </div>
            <p class="font-medium text-slate-300">هیچ فیش واریزی در انتظاری وجود ندارد</p>
            <span class="text-[10px] text-slate-500">تمامی پرداخت‌های کارت به کارت بررسی شده‌اند.</span>
          </div>
        `;
        return;
      }

      container.innerHTML = topups.map(t => {
        const uLabel = t.full_name || (t.username ? '@' + t.username : `کاربر ${t.telegram_id}`);
        const initial = (uLabel[0] || 'U').toUpperCase();
        const dateStr = t.created_at ? new Date(t.created_at).toLocaleDateString('fa-IR', { numberingSystem: 'latn', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }) : '—';
        const avatarSrc = t.avatar_url || `/api/user/avatar?user_id=${t.telegram_id}`;
        const hasPhoto = Boolean(t.has_photo || t.receipt_photo_id || (t.receipt_hash && (t.receipt_hash.startsWith('img:') || t.receipt_hash.startsWith('photo:'))));
        const photoUrl = hasPhoto ? `/api/admin/topup/photo?id=${t.id}` : null;
        const usernameTag = t.username ? `@${t.username}` : '';

        return `
          <div class="topup-card bg-slate-800/90 rounded-2xl p-3.5 border border-slate-700/80 space-y-3 shadow-md relative overflow-hidden transition hover:border-slate-600">
            <!-- Top Status Row: Receipt & Status on right (بدون علامت #), Date on left -->
            <div class="flex items-center justify-between border-b border-slate-700/60 pb-2">
              <div class="flex items-center gap-1.5">
                <span class="font-mono text-xs font-bold text-amber-400">فیش ${t.id}</span>
                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30">
                  <span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
                  در انتظار بررسی
                </span>
              </div>
              <span class="font-mono text-[10px] text-slate-500" dir="ltr">${dateStr}</span>
            </div>

            <!-- Middle Row: Photo + Name & Price on right, Username + ID on left (بدون فاصله، کاملاً چسبیده به چپ) -->
            <div class="flex items-center justify-between gap-2.5">
              <div class="flex items-center gap-2.5 min-w-0">
                <div class="w-10 h-10 rounded-full bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-white text-xs shadow flex-shrink-0 overflow-hidden relative">
                  <img src="${avatarSrc}" alt="Avatar" class="w-full h-full object-cover" onerror="this.classList.add('hidden'); if(this.nextElementSibling) this.nextElementSibling.classList.remove('hidden');" />
                  <span class="font-bold">${escapeHtml(initial)}</span>
                </div>
                <div class="min-w-0 space-y-0.5">
                  <b class="text-white text-xs font-bold block truncate max-w-[140px] cursor-pointer hover:text-cyan-300" data-copy="${escapeHtml(uLabel)}" onclick="window.adminActions.quickCopy(this.dataset.copy, 'نام')" title="${escapeHtml(uLabel)}">${escapeHtml(uLabel)}</b>
                  <div class="flex items-baseline gap-1 text-emerald-400 font-bold" dir="rtl">
                    <span class="text-sm font-black font-mono leading-none">${formatNumber(t.amount || 0)}</span>
                    <span class="text-[10px] text-emerald-500/90 font-sans">تومان</span>
                  </div>
                </div>
              </div>

              <!-- Left column: Username on line 1, Numeric ID on line 2 (بدون ID: و کاملاً چسبیده به چپ بدون فاصله) -->
              <div class="flex flex-col items-start justify-center gap-0.5 font-mono text-[11px] text-slate-400 flex-shrink-0 text-left" dir="ltr">
                ${t.username ? `<span onclick="window.adminActions.quickCopy('@${escapeHtml(t.username)}', 'نام کاربری')" class="cursor-pointer hover:text-cyan-300 text-slate-300 font-mono truncate max-w-[130px] block leading-tight" title="@${escapeHtml(t.username)}">@${escapeHtml(t.username)}</span>` : ''}
                <span class="cursor-pointer hover:text-cyan-300 text-slate-400 font-mono block leading-tight" onclick="window.adminActions.quickCopy('${t.telegram_id}', 'شناسه عددی')" title="شناسه عددی">${t.telegram_id}</span>
              </div>
            </div>

            <!-- Action Buttons: Chat on right, Photo icon & Action buttons on left (همه بدون پس‌زمینه) -->
            <div class="flex items-center justify-between gap-2 pt-1 border-t border-slate-700/50">
              <button data-action="chat" data-tgid="${t.telegram_id}" data-name="${escapeHtml(uLabel)}" data-tag="${escapeHtml(usernameTag || ('#' + t.telegram_id))}" data-topupid="${t.id}" onclick="window.adminActions.openUserChat(this.dataset.tgid, this.dataset.name, this.dataset.tag, this.dataset.topupid)" class="bg-transparent hover:bg-slate-750/30 text-slate-300 hover:text-white px-3 py-1.5 rounded-xl text-xs font-medium transition flex items-center gap-1.5 active:scale-95 border border-slate-700/60" title="گفتگوی مستقیم با کاربر">
                <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
                <span>چت با کاربر</span>
              </button>

              <div class="flex items-center gap-1.5">
                ${hasPhoto ? `
                  <button type="button" onclick="window.adminActions.openReceiptImageModal('${photoUrl}', ${t.id})" class="w-8 h-8 rounded-xl bg-transparent hover:bg-cyan-500/10 text-cyan-400 border border-cyan-500/40 flex items-center justify-center transition active:scale-95 shadow-sm" title="مشاهده تصویر فیش">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                  </button>
                ` : `
                  <button type="button" data-action="receipt-info" data-topupid="${t.id}" data-hash="${escapeHtml(t.receipt_hash || '')}" data-amount="${formatNumber(t.amount || 0)}" onclick="window.adminActions.showReceiptInfoModal(this.dataset.topupid, this.dataset.hash, this.dataset.amount)" class="w-8 h-8 rounded-xl bg-transparent hover:bg-cyan-500/10 text-cyan-400 border border-cyan-500/40 flex items-center justify-center transition active:scale-95 shadow-sm" title="مشاهده مشخصات رسید / کد پیگیری">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                  </button>
                `}
                <button type="button" onclick="window.adminActions.handleTopup(${t.id}, false)" class="w-8 h-8 rounded-xl bg-transparent hover:bg-rose-500/10 text-rose-500 hover:text-rose-400 border border-rose-500/40 flex items-center justify-center transition active:scale-95 font-bold text-sm shadow-sm" title="رد فیش">
                  ✕
                </button>
                <button type="button" onclick="window.adminActions.handleTopup(${t.id}, true)" class="w-8 h-8 rounded-xl bg-transparent hover:bg-emerald-500/10 text-emerald-400 hover:text-emerald-300 border border-emerald-500/40 flex items-center justify-center transition active:scale-95 font-bold text-sm shadow-sm" title="تایید و شارژ موجودی">
                  ✓
                </button>
              </div>
            </div>
          </div>
        `;
      }).join('');
    } catch (err) {
      container.innerHTML = '<div class="p-4 text-center text-rose-400 text-xs">خطای شبکه در دریافت فیش‌ها</div>';
    }
  }

  // --- Live Support Chat Room & Thread Manager ---
  let activeChatTelegramId = null;
  let activeChatUserName = '';

  async function fetchTicketThreads() {
    // Active chat threads list was removed from UI; refresh active chat if one is open
    if (activeChatTelegramId) {
      loadUserChatMessages(activeChatTelegramId);
    }
  }

  async function loadUserChatMessages(telegram_id) {
    const streamEl = $('ticketChatStream');
    if (!streamEl) return;
    streamEl.innerHTML = '<div class="p-6 text-center text-slate-400 text-[11px]">در حال بارگذاری پیام‌ها...</div>';
    try {
      const res = await window.api.getAdminTicketMessages(telegram_id);
      if (!res || !res.ok) {
        streamEl.innerHTML = `<div class="p-4 text-center text-rose-400 text-[11px]">${res?.error || 'خطا در دریافت پیام‌ها'}</div>`;
        return;
      }
      const messages = res.messages || [];
      const user = res.user || {};

      // Update header
      const nameEl = $('activeChatUserName');
      if (nameEl) nameEl.innerText = user.full_name || `کاربر ${telegram_id}`;
      const tagEl = $('activeChatUserTag');
      if (tagEl) {
        tagEl.innerText = user.username ? `@${user.username}` : '';
        tagEl.style.display = user.username ? 'block' : 'none';
      }
      const idEl = $('activeChatUserId');
      if (idEl) idEl.innerHTML = `<span onclick="window.adminActions.quickCopy('${telegram_id}', 'شناسه عددی')" class="cursor-pointer hover:text-cyan-300 transition">${telegram_id}</span>`;
      const avatarEl = $('activeChatUserAvatar');
      if (avatarEl) {
        const initial = ((user.full_name || user.username || String(telegram_id)).replace('@', '')[0] || 'U').toUpperCase();
        avatarEl.innerHTML = `<img src="/api/user/avatar?user_id=${telegram_id}" alt="Avatar" class="w-full h-full object-cover" onerror="this.classList.add('hidden'); if(this.nextElementSibling) this.nextElementSibling.classList.remove('hidden');" /><span class="font-bold">${initial}</span>`;
      }

      const badgeEl = $('activeChatStatusBadge');
      if (badgeEl) {
        if (user.pending_topup_id) {
          badgeEl.className = 'text-[9px] bg-transparent text-amber-500 border border-amber-500/30 px-2 py-0.5 rounded-lg font-bold flex items-center gap-1';
          badgeEl.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>فیش ${user.pending_topup_id}`;
        } else {
          badgeEl.className = 'text-[9px] bg-transparent text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-lg font-bold';
          badgeEl.innerText = `${formatNumber(user.wallet_balance || 0)} ت`;
        }
      }

      if (messages.length === 0) {
        streamEl.innerHTML = `
          <div class="p-6 text-center text-slate-400 text-[11px] space-y-1.5">
            <div class="text-xl">💬</div>
            <p>پیامی برای این کاربر ثبت نشده است.</p>
            <p class="text-[10px] text-slate-500">می‌توانید اولین پیام یا راهنمایی را ارسال کنید.</p>
          </div>
        `;
        return;
      }

      streamEl.innerHTML = messages.map(m => {
        if (m.sender === 'system') {
          return `
            <div class="flex justify-center my-1.5">
              <span class="bg-amber-950/40 text-amber-300 border border-amber-500/30 text-[10px] px-3 py-1 rounded-xl text-center leading-relaxed">
                🔔 ${escapeHtml(m.text)}
              </span>
            </div>
          `;
        }

        const isAdmin = m.sender === 'admin';
        const timeDisplay = formatChatTimestamp(m);
        return `
          <div class="flex ${isAdmin ? 'justify-start' : 'justify-end'}">
            <div class="max-w-[85%] rounded-2xl p-2.5 space-y-1 shadow-sm ${isAdmin ? 'bg-blue-600/15 dark:bg-blue-600/25 border border-blue-400/40 dark:border-blue-500/30 text-blue-950 dark:text-blue-100 rounded-tr-sm' : 'bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700/60 text-slate-900 dark:text-slate-200 rounded-tl-sm shadow-sm'}">
              <div class="flex items-center justify-between gap-3 text-[9px] ${isAdmin ? 'text-blue-700 dark:text-blue-300 font-bold' : 'text-slate-600 dark:text-slate-400 font-bold'}">
                <span>${isAdmin ? '🛡️ پشتیبانی' : '👤 کاربر'}</span>
                <span class="font-mono ${isAdmin ? 'text-blue-600 dark:text-blue-400' : 'text-slate-500 dark:text-slate-400'}" dir="ltr">${timeDisplay}</span>
              </div>
              <p class="text-xs leading-relaxed break-words whitespace-pre-wrap text-slate-900 dark:text-slate-100 font-medium dark:font-normal">${escapeHtml(m.text)}</p>
            </div>
          </div>
        `;
      }).join('');

      // Auto-scroll to bottom
      streamEl.scrollTop = streamEl.scrollHeight;
    } catch (e) {
      streamEl.innerHTML = '<div class="p-4 text-center text-rose-400 text-[11px]">خطای شبکه در دریافت پیام‌ها</div>';
    }
  }

  // Direct Ticket Reply Form Handler
  $('sendDirectTicketReplyBtn')?.addEventListener('click', async () => {
    const uid = $('directTicketUserId')?.value?.trim() || activeChatTelegramId;
    const txtEl = $('directTicketMsg');
    const txt = txtEl?.value?.trim();
    if (!uid) {
      if (window.showToast) window.showToast('لطفاً ابتدا یک کاربر را از لیست بالا انتخاب کنید.');
      return;
    }
    if (!txt) {
      if (window.showToast) window.showToast('لطفاً متن پیام را وارد کنید.');
      return;
    }
    const sendBtn = $('sendDirectTicketReplyBtn');
    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.innerText = 'در حال ارسال...';
    }
    try {
      const res = await window.api.replyDirectTicket(parseInt(uid), txt);
      if (res && res.ok) {
        if (window.showToast) window.showToast('✅ پیام برای کاربر ارسال شد.');
        if (window.hapticFeedback) window.hapticFeedback('success');
        if (txtEl) txtEl.value = '';
        loadUserChatMessages(parseInt(uid));
        fetchTicketThreads();
      } else {
        if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ارسال پیام'}`);
        if (window.hapticFeedback) window.hapticFeedback('error');
      }
    } catch (e) {
      if (window.showToast) window.showToast('خطای شبکه در ارسال پیام');
    } finally {
      if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/></svg><span>ارسال</span>';
      }
    }
  });

  // Template Quick Reply Chips
  document.querySelectorAll('.chat-template-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const msg = chip.getAttribute('data-msg');
      const input = $('directTicketMsg');
      if (input && msg) {
        input.value = msg;
        input.focus();
      }
      if (window.hapticFeedback) window.hapticFeedback('impact');
    });
  });

  $('refreshChatThreadsBtn')?.addEventListener('click', () => {
    fetchTicketThreads();
    if (activeChatTelegramId) loadUserChatMessages(activeChatTelegramId);
    if (window.showToast) window.showToast('🔄 گفتگوها به‌روزرسانی شد');
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  $('directTicketMsg')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      $('sendDirectTicketReplyBtn')?.click();
    }
  });

  // --- 8. System Settings ---
  function formatTopicVal(inputEl, val) {
    if (!inputEl) return;
    const num = String(val ?? '').match(/\d+/)?.[0];
    if (num) {
      const label = inputEl.getAttribute('data-topic-label') || '';
      inputEl.value = label ? `${num} (${label})` : num;
    } else {
      inputEl.value = '';
    }
  }

  function parseTopicVal(val) {
    const num = String(val ?? '').match(/\d+/)?.[0];
    return num ? parseInt(num, 10) : null;
  }

  const topicInputIds = [
    'settingTopicTopups',
    'settingTopicOrders',
    'settingTopicSupport',
    'settingTopicAlerts',
    'settingTopicNodes',
    'settingTopicReports',
    'settingTopicCrypto',
    'settingTopicErrors'
  ];

  async function fetchAdminSettings() {
    try {
      const res = await window.api.getAdminSettings();
      if (!res || !res.ok || !res.settings) return;
      window._adminSettingsLoaded = true;
      const s = res.settings;

      // Access Mode & Maintenance Sync
      const isMaint = !!s.maintenance;
      const curMode = s.access_mode || (isMaint ? 'closed' : 'open');
      const finalMode = isMaint ? 'closed' : curMode;

      const maintSwitch = $('settingMaintSwitch');
      if (maintSwitch) maintSwitch.checked = (finalMode === 'closed');

      const accessMode = $('settingAccessMode');
      if (accessMode) accessMode.value = finalMode;
      window.adminActions.renderAccessModeUI(finalMode);
      if (s.bot_username) window.botUsername = s.bot_username;

      // Other Switches
      const cardSwitch = $('settingCardSwitch');
      if (cardSwitch) cardSwitch.checked = !!s.card_enabled;

      const cryptoSwitch = $('settingCryptoSwitch');
      if (cryptoSwitch) cryptoSwitch.checked = !!s.crypto_enabled;

      const trialSwitch = $('settingTrialSwitch');
      if (trialSwitch) trialSwitch.checked = !!s.trial_enabled;

      const refSwitch = $('settingRefSwitch');
      if (refSwitch) refSwitch.checked = !!s.referral_enabled;

      const supDirectSwitch = $('settingSupportDirectSwitch');
      if (supDirectSwitch) supDirectSwitch.checked = !!s.support_direct_enabled;

      // Telegram Stars Gateway
      const starsSwitch = $('settingStarsSwitch');
      if (starsSwitch) starsSwitch.checked = !!s.stars_enabled;

      const starsRate = $('settingStarsRate');
      if (starsRate) starsRate.value = s.stars_rate_toman ?? 1600;



      // Bank & Topup
      const cardNum = $('settingCardNumber');
      if (cardNum) cardNum.value = s.card_number || '';

      const cardHolder = $('settingCardHolder');
      if (cardHolder) cardHolder.value = s.card_holder || '';

      const minTopup = $('settingMinTopup');
      if (minTopup) minTopup.value = s.topup_min_amount ?? 20000;

      const cardPhoneSwitch = $('settingCardRequirePhoneSwitch');
      if (cardPhoneSwitch) cardPhoneSwitch.checked = s.card_require_phone_verification ?? true;

      const cardIranSwitch = $('settingCardPhoneIranSwitch');
      if (cardIranSwitch) cardIranSwitch.checked = s.card_phone_iran_only ?? true;

      // Birthday Rewards
      const bdaySwitch = $('settingBirthdayRewardSwitch');
      if (bdaySwitch) bdaySwitch.checked = s.birthday_reward_enabled ?? true;

      const bdayTraffic = $('settingBirthdayRewardTraffic');
      if (bdayTraffic) bdayTraffic.value = s.birthday_reward_traffic_gb ?? 2;

      const bdayDiscount = $('settingBirthdayRewardDiscount');
      if (bdayDiscount) bdayDiscount.value = s.birthday_reward_discount_percent ?? 20;

      // Join Gate
      const jgSwitch = $('settingJoinGateSwitch');
      if (jgSwitch) jgSwitch.checked = s.join_gate_enabled ?? false;

      const jgChannel = $('settingJoinGateChannel');
      if (jgChannel) jgChannel.value = s.join_gate_channel || '';

      // Crypto & Rates
      const usdtRate = $('settingUsdtRate');
      if (usdtRate) {
        usdtRate.value = s.usdt_rate_toman ?? 95000;
        if (!usdtRate._hasStarsListener) {
          usdtRate.addEventListener('input', () => window.adminActions.updateStarsHint());
          usdtRate._hasStarsListener = true;
        }
      }
      if (s.usdt_rate_toman) window.currentUsdRate = s.usdt_rate_toman;
      window.adminActions.updateStarsHint();

      const eurRate = $('settingEurRate');
      if (eurRate) eurRate.value = s.eur_rate_toman ?? 105000;
      if (s.eur_rate_toman) window.currentEurRate = s.eur_rate_toman;

      const tonRate = $('settingTonRate');
      if (tonRate) tonRate.value = s.ton_rate_toman ?? 0;

      const tonWallet = $('settingTonWallet');
      if (tonWallet) tonWallet.value = s.ton_wallet_address || '';

      // Trial & Referral
      const trialTraffic = $('settingTrialTraffic');
      if (trialTraffic) trialTraffic.value = s.trial_traffic_gb ?? 1;

      const trialDays = $('settingTrialDays');
      if (trialDays) trialDays.value = s.trial_duration_days ?? 1;

      const refReward = $('settingRefReward');
      if (refReward) refReward.value = s.referral_reward_gb ?? 5;

      const supContact = $('settingSupportContact');
      if (supContact) supContact.value = s.support_contact || '';

      // Tutorial Channel URL, Routing Tutorial URL & Client App Overrides
      const tutChannelInp = $('settingTutorialChannelUrl');
      if (tutChannelInp) tutChannelInp.value = s.tutorial_channel_url || '';

      const routingTutInp = $('settingRoutingTutorialUrl');
      if (routingTutInp) routingTutInp.value = s.routing_tutorial_url || '';

      const OS_APPS_MAP = {
        ios: ['streisand', 'v2box', 'incy', 'happ'],
        android: ['v2rayng', 'happ', 'hiddify', 'incy'],
        windows: ['v2rayn', 'hiddify', 'happ', 'incy'],
        macos: ['hiddify', 'happ', 'incy', 'v2box'],
        linux: ['hiddify', 'incy', 'nekoray', 'v2raya']
      };

      if (s.client_apps_json) {
        try {
          const appOverrides = typeof s.client_apps_json === 'string' ? JSON.parse(s.client_apps_json) : s.client_apps_json;
          if (appOverrides && typeof appOverrides === 'object') {
            for (const [os, appIds] of Object.entries(OS_APPS_MAP)) {
              const recSelect = $(`appRecommended_${os}`);
              if (recSelect) {
                recSelect.value = appOverrides.recommended?.[os] || (os === 'windows' ? appOverrides.recommended?.desktop : '') || '';
              }
              const osSource = appOverrides[os] || (os === 'windows' ? appOverrides.desktop : null);
              for (const appId of appIds) {
                const item = osSource?.[appId] || (appOverrides[appId] ? { enabled: true, download_url: appOverrides[appId], tutorial_url: '' } : null);
                const downloadEl = $(`appDownload_${os}_${appId}`);
                const downloadPortableEl = $(`appDownloadPortable_${os}_${appId}`);
                const downloadExtraEl = $(`appDownloadExtra_${os}_${appId}`);
                const tutorialEl = $(`appTutorial_${os}_${appId}`);
                if (downloadEl) downloadEl.value = item?.download_url || '';
                if (downloadPortableEl) downloadPortableEl.value = item?.download_portable_url || '';
                if (downloadExtraEl) downloadExtraEl.value = item?.download_extra_url || '';
                if (tutorialEl) tutorialEl.value = item?.tutorial_url || '';
              }
            }
          }
        } catch (e) {}
      }

      // Telegram Supergroup Forum Topics
      const topicSettings = {
        settingTopicTopups: s.topic_topups,
        settingTopicOrders: s.topic_orders,
        settingTopicSupport: s.topic_support,
        settingTopicAlerts: s.topic_alerts,
        settingTopicNodes: s.topic_nodes,
        settingTopicReports: s.topic_reports,
        settingTopicCrypto: s.topic_crypto,
        settingTopicErrors: s.topic_errors,
      };
      topicInputIds.forEach(id => {
        const inp = $(id);
        if (inp) {
          formatTopicVal(inp, topicSettings[id]);
          if (!inp._hasTopicListeners) {
            inp.addEventListener('focus', () => {
              const num = String(inp.value).match(/\d+/)?.[0] || '';
              inp.value = num;
            });
            inp.addEventListener('blur', () => {
              formatTopicVal(inp, inp.value);
            });
            inp._hasTopicListeners = true;
          }
        }
      });
    } catch (e) {}
  }

  async function updateSettingToggle(key, val) {
    try {
      const res = await window.api.saveAdminSettings({ [key]: val });
      if (res && res.ok) {
        if (window.showToast) window.showToast('✓ تنظیم ذخیره شد');
        if (window.hapticFeedback) window.hapticFeedback('success');
      } else {
        if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ذخیره تنظیم'}`);
      }
    } catch (e) {
      if (window.showToast) window.showToast('خطا در ذخیره تنظیم');
    }
  }

  $('settingMaintSwitch')?.addEventListener('change', async (e) => {
    const isMaint = e.target.checked;
    const newMode = isMaint ? 'closed' : 'open';
    const accInp = $('settingAccessMode');
    if (accInp) accInp.value = newMode;
    window.adminActions.renderAccessModeUI(newMode);
    try {
      const res = await window.api.saveAdminSettings({ maintenance: isMaint, access_mode: newMode });
      if (res && res.ok) {
        if (window.showToast) window.showToast(isMaint ? '🔒 حالت تعمیرات فعال شد (دسترسی ربات بسته شد)' : '✅ حالت تعمیرات غیرفعال شد (دسترسی عمومی)');
        if (window.hapticFeedback) window.hapticFeedback('success');
      }
    } catch (err) {
      if (window.showToast) window.showToast('خطا در ذخیره وضعیت تعمیرات');
    }
  });
  $('settingCardSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('card_enabled', e.target.checked);
  });
  $('settingCryptoSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('crypto_enabled', e.target.checked);
  });
  $('settingTrialSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('trial_enabled', e.target.checked);
  });
  $('settingRefSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('referral_enabled', e.target.checked);
  });
  $('settingSupportDirectSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('support_direct_enabled', e.target.checked);
  });
  $('settingStarsSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('stars_enabled', e.target.checked);
  });
  $('settingCardRequirePhoneSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('card_require_phone_verification', e.target.checked);
  });
  $('settingCardPhoneIranSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('card_phone_iran_only', e.target.checked);
  });
  $('settingBirthdayRewardSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('birthday_reward_enabled', e.target.checked);
  });
  $('settingJoinGateSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('join_gate_enabled', e.target.checked);
  });
  $('settingAccessMode')?.addEventListener('change', (e) => {
    updateSettingToggle('access_mode', e.target.value);
  });

  async function handleSaveAllSettings() {
    const isMaint = $('settingMaintSwitch')?.checked ?? false;
    let accessModeVal = $('settingAccessMode')?.value || 'open';
    if (isMaint) {
      accessModeVal = 'closed';
    } else if (accessModeVal === 'closed') {
      accessModeVal = 'open';
    }

    const payload = {
      maintenance: isMaint,
      access_mode: accessModeVal,
      card_enabled: $('settingCardSwitch')?.checked ?? true,
      card_require_phone_verification: $('settingCardRequirePhoneSwitch')?.checked ?? true,
      card_phone_iran_only: $('settingCardPhoneIranSwitch')?.checked ?? true,
      birthday_reward_enabled: $('settingBirthdayRewardSwitch')?.checked ?? true,
      birthday_reward_traffic_gb: parseInt($('settingBirthdayRewardTraffic')?.value || '2', 10),
      birthday_reward_discount_percent: parseInt($('settingBirthdayRewardDiscount')?.value || '20', 10),
      join_gate_enabled: $('settingJoinGateSwitch')?.checked ?? false,
      join_gate_channel: $('settingJoinGateChannel')?.value?.trim() || '',
      crypto_enabled: $('settingCryptoSwitch')?.checked ?? false,
      stars_enabled: $('settingStarsSwitch')?.checked ?? false,
      stars_rate_toman: parseInt($('settingStarsRate')?.value || '1600', 10),
      trial_enabled: $('settingTrialSwitch')?.checked ?? true,
      referral_enabled: $('settingRefSwitch')?.checked ?? true,
      support_direct_enabled: $('settingSupportDirectSwitch')?.checked ?? true,
      card_number: $('settingCardNumber')?.value?.trim() || '',
      card_holder: $('settingCardHolder')?.value?.trim() || '',
      topup_min_amount: parseInt($('settingMinTopup')?.value || '20000', 10),
      usdt_rate_toman: parseInt($('settingUsdtRate')?.value || '95000', 10),
      eur_rate_toman: parseInt($('settingEurRate')?.value || '105000', 10),
      ton_rate_toman: parseInt($('settingTonRate')?.value || '0', 10),
      ton_wallet_address: $('settingTonWallet')?.value?.trim() || '',
      trial_traffic_gb: parseInt($('settingTrialTraffic')?.value || '1', 10),
      trial_duration_days: parseInt($('settingTrialDays')?.value || '1', 10),
      referral_reward_gb: parseInt($('settingRefReward')?.value || '5', 10),
      support_contact: $('settingSupportContact')?.value?.trim() || '',
      topic_topups: parseTopicVal($('settingTopicTopups')?.value),
      topic_orders: parseTopicVal($('settingTopicOrders')?.value),
      topic_support: parseTopicVal($('settingTopicSupport')?.value),
      topic_alerts: parseTopicVal($('settingTopicAlerts')?.value),
      topic_nodes: parseTopicVal($('settingTopicNodes')?.value),
      topic_reports: parseTopicVal($('settingTopicReports')?.value),
      topic_crypto: parseTopicVal($('settingTopicCrypto')?.value),
      topic_errors: parseTopicVal($('settingTopicErrors')?.value),
      tutorial_channel_url: $('settingTutorialChannelUrl')?.value?.trim() || '',
      routing_tutorial_url: $('settingRoutingTutorialUrl')?.value?.trim() || '',
      client_apps_json: (() => {
        const OS_APPS_MAP = {
          ios: ['streisand', 'v2box', 'incy', 'happ'],
          android: ['v2rayng', 'happ', 'hiddify', 'incy'],
          windows: ['v2rayn', 'hiddify', 'happ', 'incy'],
          macos: ['hiddify', 'happ', 'incy', 'v2box'],
          linux: ['hiddify', 'incy', 'nekoray', 'v2raya']
        };
        const clientAppsObj = {
          recommended: {
            ios: $('appRecommended_ios')?.value || '',
            android: $('appRecommended_android')?.value || '',
            windows: $('appRecommended_windows')?.value || '',
            desktop: $('appRecommended_windows')?.value || '',
            macos: $('appRecommended_macos')?.value || '',
            linux: $('appRecommended_linux')?.value || ''
          }
        };
        for (const [os, appIds] of Object.entries(OS_APPS_MAP)) {
          clientAppsObj[os] = {};
          for (const appId of appIds) {
            const downloadEl = $(`appDownload_${os}_${appId}`);
            const downloadPortableEl = $(`appDownloadPortable_${os}_${appId}`);
            const downloadExtraEl = $(`appDownloadExtra_${os}_${appId}`);
            const tutorialEl = $(`appTutorial_${os}_${appId}`);
            const downloadUrl = downloadEl?.value?.trim() || '';
            const downloadPortableUrl = downloadPortableEl?.value?.trim() || '';
            const downloadExtraUrl = downloadExtraEl?.value?.trim() || '';
            clientAppsObj[os][appId] = {
              enabled: Boolean(downloadUrl || downloadPortableUrl || downloadExtraUrl),
              download_url: downloadUrl,
              download_portable_url: downloadPortableUrl,
              download_extra_url: downloadExtraUrl,
              tutorial_url: tutorialEl?.value?.trim() || ''
            };
          }
        }
        clientAppsObj.desktop = clientAppsObj.windows;
        return JSON.stringify(clientAppsObj);
      })(),
    };

    const saveBtns = [$('saveAllSettingsBtn'), $('saveAllSettingsTopBtn')];
    saveBtns.forEach(b => { if (b) { b.disabled = true; b.innerText = 'در حال ذخیره...'; } });

    try {
      const res = await window.api.saveAdminSettings(payload);
      if (res && res.ok) {
        topicInputIds.forEach(id => {
          const inp = $(id);
          if (inp) formatTopicVal(inp, inp.value);
        });
        if (window.showToast) window.showToast('✅ تمامی تنظیمات با موفقیت ذخیره شدند.');
        if (window.hapticFeedback) window.hapticFeedback('success');
      } else {
        if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ثبت تنظیمات'}`);
        if (window.hapticFeedback) window.hapticFeedback('error');
      }
    } catch (e) {
      if (window.showToast) window.showToast('خطای شبکه در ذخیره تنظیمات');
    } finally {
      saveBtns.forEach(b => { if (b) { b.disabled = false; b.innerText = '💾 ذخیره همه'; } });
      const mainBtn = $('saveAllSettingsBtn');
      if (mainBtn) mainBtn.innerHTML = '<span>💾</span> ذخیره تمامی تغییرات تنظیمات';
    }
  }

  $('saveAllSettingsBtn')?.addEventListener('click', handleSaveAllSettings);
  $('saveAllSettingsTopBtn')?.addEventListener('click', handleSaveAllSettings);

  // Settings Accordion Boxes toggle handled by window.adminActions.toggleSettingsBox

  // Crypto rates modal trigger in settings
  $('openCryptoRatesModalBtn')?.addEventListener('click', () => {
    window.adminActions.openCryptoRatesModal();
  });

  // --- 9. Broadcast Modal & Live Report Modal ---
  const broadcastModal = $('broadcastModal');
  const broadcastReportModal = $('broadcastReportModal');
  const openBroadcastModalBtn = $('openBroadcastModalBtn');
  const closeBroadcastBtn = $('closeBroadcastBtn');
  const sendBroadcastBtn = $('sendBroadcastBtn');
  const closeBroadcastReportBtn = $('closeBroadcastReportBtn');
  const dismissReportModalBtn = $('dismissReportModalBtn');

  openBroadcastModalBtn?.addEventListener('click', () => {
    if (broadcastModal) broadcastModal.classList.remove('hidden');
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  closeBroadcastBtn?.addEventListener('click', () => {
    if (broadcastModal) broadcastModal.classList.add('hidden');
  });

  closeBroadcastReportBtn?.addEventListener('click', () => {
    broadcastReportModal?.classList.add('hidden');
  });
  dismissReportModalBtn?.addEventListener('click', () => {
    broadcastReportModal?.classList.add('hidden');
  });

  // Audience selection chips
  document.querySelectorAll('.broadcast-audience-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.broadcast-audience-btn').forEach(b => {
        b.className = 'broadcast-audience-btn px-2.5 py-1 rounded-xl bg-transparent text-slate-400 hover:text-white text-[10px] transition border border-slate-700/60';
      });
      btn.className = 'broadcast-audience-btn px-2.5 py-1 rounded-xl bg-blue-600/20 text-blue-400 font-bold text-[10px] transition border border-blue-500 shadow-sm';
      currentBroadcastTarget = btn.getAttribute('data-target') || 'all';

      const labelMap = {
        all: 'کل کاربران ربات',
        active: 'کاربران با سرویس فعال',
        expired: 'کاربران منقضی شده',
        buyers: 'خریداران قبلی',
        balance: 'کاربران دارای موجودی کیف پول',
      };
      const targetLabel = $('broadcastTargetLabel');
      if (targetLabel) targetLabel.innerText = labelMap[currentBroadcastTarget] || 'کاربران';

      if (window.hapticFeedback) window.hapticFeedback('impact');
    });
  });

  sendBroadcastBtn?.addEventListener('click', async () => {
    const txt = $('broadcastTextArea')?.value?.trim();
    if (!txt) {
      if (window.showToast) window.showToast('لطفاً متن پیام را وارد کنید.');
      return;
    }
    sendBroadcastBtn.disabled = true;
    sendBroadcastBtn.innerText = 'در حال آماده‌سازی و ارسال...';

    try {
      const res = await window.api.broadcastMessage(txt, currentBroadcastTarget);
      if (res && res.ok && res.broadcast_id) {
        if (broadcastModal) broadcastModal.classList.add('hidden');
        const txtEl = $('broadcastTextArea');
        if (txtEl) txtEl.value = '';

        // Open Live Progress Report Modal
        if (broadcastReportModal) {
          broadcastReportModal.classList.remove('hidden');
          const targetEl = $('reportTargetLabel');
          if (targetEl) targetEl.innerText = res.stats?.target_label || 'همه کاربران';
          const totalEl = $('reportTotalCount');
          if (totalEl) totalEl.innerText = `${formatNumber(res.stats?.total || 0)} نفر`;
          const sentEl = $('reportSentCount');
          if (sentEl) sentEl.innerText = '0 پیام';
          const failEl = $('reportFailedCount');
          if (failEl) failEl.innerText = '0';
          const statusEl = $('reportStatusText');
          if (statusEl) statusEl.innerText = 'در حال ارسال پیام‌ها...';
          const pBar = $('reportProgressBar');
          if (pBar) pBar.style.width = '10%';
          const pText = $('reportPercentText');
          if (pText) pText.innerText = '0%';

          // Poll progress
          const bId = res.broadcast_id;
          const pollTimer = setInterval(async () => {
            try {
              const statusRes = await window.api.getBroadcastStatus(bId);
              if (statusRes && statusRes.ok && statusRes.stats) {
                const s = statusRes.stats;
                if (sentEl) sentEl.innerText = `${formatNumber(s.sent || 0)} پیام`;
                if (failEl) failEl.innerText = formatNumber(s.failed || 0);

                const total = s.total || 1;
                const processed = (s.sent || 0) + (s.failed || 0);
                const pct = Math.min(100, Math.round((processed / total) * 100));

                if (pBar) pBar.style.width = `${pct}%`;
                if (pText) pText.innerText = `${pct}%`;

                if (s.is_completed) {
                  clearInterval(pollTimer);
                  if (statusEl) statusEl.innerText = '✅ ارسال پیام همگانی پایان یافت';
                  if (window.hapticFeedback) window.hapticFeedback('success');
                }
              }
            } catch (err) {
              clearInterval(pollTimer);
            }
          }, 600);
        }
      } else {
        if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ارسال پیام'}`);
        if (window.hapticFeedback) window.hapticFeedback('error');
      }
    } catch (err) {
      if (window.showToast) window.showToast('خطای شبکه در ارسال پیام همگانی');
    } finally {
      sendBroadcastBtn.disabled = false;
      sendBroadcastBtn.innerHTML = '<span>🚀</span><span>شروع ارسال همگانی</span>';
    }
  });

  // --- 10. Header & Action Trigger Buttons ---
  $('adminReloadBtn')?.addEventListener('click', () => {
    syncAdminOverview(true);
    if (window.showToast) window.showToast('🔄 اطلاعات به‌روزرسانی شد.');
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  $('quickRefreshMetricsBtn')?.addEventListener('click', () => {
    syncAdminOverview(true);
    if (window.showToast) window.showToast('🔄 داده‌ها سینک شدند.');
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  $('syncAllNodesBtn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    syncAdminOverview(true);
    if (window.showToast) window.showToast('🔄 نودها همگام‌سازی شدند.');
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  const overviewNodesToggleHeader = $('overviewNodesToggleHeader');
  const overviewNodesCollapseBody = $('overviewNodesCollapseBody');
  const overviewNodesChevron = $('overviewNodesChevron');

  overviewNodesToggleHeader?.addEventListener('click', (e) => {
    if (e.target.closest('#syncAllNodesBtn')) return;
    if (!overviewNodesCollapseBody) return;
    const isHidden = overviewNodesCollapseBody.classList.toggle('hidden');
    if (overviewNodesChevron) {
      overviewNodesChevron.style.transform = isHidden ? 'rotate(0deg)' : 'rotate(180deg)';
    }
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  $('refreshNodesTabBtn')?.addEventListener('click', async () => {
    const icon = $('refreshNodesTabIcon');
    if (icon) icon.classList.add('animate-spin');
    try {
      await syncAdminOverview(true);
      await fetchAdminSslHealth();
      if (window.showToast) window.showToast('🔄 وضعیت سرورها و گواهی‌های SSL به‌روزرسانی شد');
      if (window.hapticFeedback) window.hapticFeedback('success');
    } finally {
      setTimeout(() => {
        if (icon) icon.classList.remove('animate-spin');
      }, 500);
    }
  });

  $('refreshSslHealthBtn')?.addEventListener('click', async () => {
    const icon = $('refreshSslHealthIcon');
    if (icon) icon.classList.add('animate-spin');
    try {
      await fetchAdminSslHealth();
      if (window.showToast) window.showToast('🔒 وضعیت گواهی‌های SSL به‌روزرسانی شد');
      if (window.hapticFeedback) window.hapticFeedback('success');
    } finally {
      setTimeout(() => {
        if (icon) icon.classList.remove('animate-spin');
      }, 500);
    }
  });

  // Nodes Tab Subtabs Switcher
  window.switchNodesSubtab = function(subtab) {
    const btnServers = $('subtabBtnNodesServers');
    const btnSsl = $('subtabBtnNodesSsl');
    const contentServers = $('subtabContentNodesServers');
    const contentSsl = $('subtabContentNodesSsl');

    if (subtab === 'ssl') {
      btnServers?.classList.remove('bg-blue-600', 'bg-indigo-600', 'text-white', 'shadow');
      btnServers?.classList.add('text-slate-400', 'hover:text-slate-200');
      btnSsl?.classList.add('bg-blue-600', 'text-white', 'shadow');
      btnSsl?.classList.remove('text-slate-400', 'hover:text-slate-200');
      contentServers?.classList.add('hidden');
      contentSsl?.classList.remove('hidden');
      fetchAdminSslHealth();
    } else {
      btnSsl?.classList.remove('bg-blue-600', 'bg-indigo-600', 'text-white', 'shadow');
      btnSsl?.classList.add('text-slate-400', 'hover:text-slate-200');
      btnServers?.classList.add('bg-blue-600', 'text-white', 'shadow');
      btnServers?.classList.remove('text-slate-400', 'hover:text-slate-200');
      contentSsl?.classList.add('hidden');
      contentServers?.classList.remove('hidden');
    }
    if (window.hapticFeedback) window.hapticFeedback('selection');
  };

  const handleAddSslDomain = async () => {
    const input = $('customSslDomainInput');
    const domain = (input?.value || '').trim();
    if (!domain) {
      if (window.showToast) window.showToast('لطفاً آدرس دامنه را وارد کنید');
      return;
    }
    const btn = $('addCustomSslBtn') || $('checkCustomSslBtn');
    const prevText = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span>درحال بررسی...</span>';
    }
    try {
      const res = await window.api.addCustomSslDomain(domain);
      if (res && res.ok && res.data) {
        const idx = cachedSslHealthItems.findIndex(x => x.domain.toLowerCase() === res.data.domain.toLowerCase());
        if (idx >= 0) {
          cachedSslHealthItems[idx] = res.data;
        } else {
          cachedSslHealthItems.unshift(res.data);
        }
        renderSslHealth(cachedSslHealthItems);
        if (input) input.value = '';
        if (res.data.valid) {
          if (window.showToast) window.showToast(`✅ دامنه ${domain} افزوده شد (${res.data.days_left} روز باقی‌مانده)`);
        } else {
          if (window.showToast) window.showToast(`⚠️ دامنه ذخیره شد اما: ${res.data.error || 'گواهی نامعتبر است'}`);
        }
        if (window.hapticFeedback) window.hapticFeedback('success');
      } else {
        if (window.showToast) window.showToast(res?.error || 'خطا در ثبت و ارزیابی دامنه');
      }
    } catch (err) {
      console.error('SSL add error:', err);
      if (window.showToast) window.showToast('خطا در ارتباط با سرور');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = prevText;
      }
    }
  };

  $('addCustomSslBtn')?.addEventListener('click', handleAddSslDomain);
  $('checkCustomSslBtn')?.addEventListener('click', handleAddSslDomain);

  // Node Billing auto-convert EUR to Toman & Shamsi preview
  const nodeCostEurInput = $('nodeBillingCostEur');
  const nodeCostTomanInput = $('nodeBillingCostToman');
  const nodeEurHint = $('nodeBillingEurConvertHint');
  const nodeEurHintText = $('nodeBillingEurConvertText');
  const nodeDueDateInput = $('nodeBillingDueDate');
  const nodeJalaliPreview = $('nodeBillingJalaliPreview');

  nodeCostEurInput?.addEventListener('input', () => {
    window.adminActions?.updateNodeBillingConversion();
  });

  nodeCostTomanInput?.addEventListener('input', () => {
    window.adminActions?.updateNodeBillingConversion();
  });

  nodeDueDateInput?.addEventListener('input', (e) => {
    const d = e.target.value;
    if (nodeJalaliPreview) {
      nodeJalaliPreview.innerText = d ? (window.formatDateToJalali ? window.formatDateToJalali(d) : d) : '';
    }
  });

  $('settingEurRate')?.addEventListener('input', (e) => {
    const val = parseInt(e.target.value, 10);
    if (!isNaN(val) && val > 0) {
      window.currentEurRate = val;
    }
  });

  $('settingUsdtRate')?.addEventListener('input', (e) => {
    const val = parseInt(e.target.value, 10);
    if (!isNaN(val) && val > 0) {
      window.currentUsdRate = val;
    }
  });

  $('refreshTopupsBtn')?.addEventListener('click', () => {
    fetchAdminTopups();
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  $('viewPendingBtn')?.addEventListener('click', () => {
    const ticketsNav = document.querySelector('.admin-nav-btn[data-admin-tab="tab-admin-tickets"]');
    ticketsNav?.click();
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  // Global modal triggers for inline onclick backwards-compatibility
  window.closeModifyModal = () => window.adminActions.closeModifyModal();
  window.applyUserModification = () => window.adminActions.applyUserModification();
  window.openModifyUserModal = (id, name, type) => window.adminActions.openModifyUser(id, name, type);
  window.killUserSessions = (id, name) => window.adminActions.killSessions(id, name);
  window.toggleUserBan = (id, ban) => window.adminActions.toggleBan(id, ban);
  window.handleTopupAction = (id, app) => window.adminActions.handleTopup(id, app);
  window.openSubModal = (id, name, url) => window.adminActions.openSubModal(id, name, url);
  window.closeSubModal = () => window.adminActions.closeSubModal();
  window.copySubLink = () => window.adminActions.copySubLink();
  window.confirmRegenerateSub = () => window.adminActions.confirmRegenerateSub();
  window.killSessionsFromModal = () => window.adminActions.killSessionsFromModal();
  window.quickCopy = (text, label) => window.adminActions.quickCopy(text, label);
  window.openBulkUsersModal = () => window.adminActions.openBulkUsersModal();
  window.closeBulkUsersModal = () => window.adminActions.closeBulkUsersModal();
  window.openNodeBillingModal = (...args) => window.adminActions.openNodeBillingModal(...args);
  window.closeNodeBillingModal = () => window.adminActions.closeNodeBillingModal();
  window.saveNodeBilling = () => window.adminActions.saveNodeBilling();
  window.setNodeBillingCurrency = (curr) => window.adminActions.setNodeBillingCurrency(curr);
  window.addDaysToNodeBillingDueDate = (days) => window.adminActions.addDaysToNodeBillingDueDate(days);
  window.clearNodeBillingDueDate = () => window.adminActions.clearNodeBillingDueDate();
  window.switchAdminAppsTab = (os) => window.adminActions.switchAdminAppsTab(os);
  window.openCreateCampaignModal = () => window.adminActions.openCreateCampaignModal();
  window.closeCreateCampaignModal = () => window.adminActions.closeCreateCampaignModal();
  window.submitCreateCampaign = (e) => window.adminActions.submitCreateCampaign(e);
  window.deleteCampaign = (id, name) => window.adminActions.deleteCampaign(id, name);
  window.copyCampaignLink = (url) => window.adminActions.copyCampaignLink(url);
  window.fetchAdminCampaigns = () => window.adminActions.fetchAdminCampaigns();
  window.deleteSslDomain = (domain) => window.adminActions.deleteSslDomain(domain);
  window.openUserProfileModal = (id) => window.adminActions.openUserProfileModal(id);
  window.closeUserProfileModal = () => window.adminActions.closeUserProfileModal();

  // Explicit event listeners for Admin App Tabs and Due Date buttons
  document.querySelectorAll('.admin-app-os-tab').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const id = btn.id || '';
      const os = id.replace('adminAppTab_', '');
      if (os) window.switchAdminAppsTab(os);
    });
  });

  // Initial Sync
  fetchAdminSettings();
  syncAdminOverview();
})();
