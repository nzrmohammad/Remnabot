/**
 * RemnaAdmin Pro - Modular Admin Suite JavaScript
 * Follows DRY, anti-bloat, and high-performance asynchronous standards.
 */

(function () {
  'use strict';

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
        syncAdminOverview(false);
      } else if (targetId === 'tab-admin-users' && document.getElementById('adminUsersList')?.children.length <= 1) {
        fetchAdminUsers(1);
      } else if (targetId === 'tab-admin-plans') {
        fetchAdminPlans();
        fetchAdminCoupons();
      } else if (targetId === 'tab-admin-coupons') {
        fetchAdminCoupons();
      } else if (targetId === 'tab-admin-tickets') {
        fetchAdminTopups();
        fetchTicketThreads();
      } else if (targetId === 'tab-admin-settings') {
        fetchAdminSettings();
      }
    });
  });

  // Subtab switcher for Unified Plans & Discounts Tab
  window.switchServicesSubtab = function(subtab) {
    const btnPlans = document.getElementById('subtabBtnPlans');
    const btnCoupons = document.getElementById('subtabBtnCoupons');
    const contentPlans = document.getElementById('subtabContentPlans');
    const contentCoupons = document.getElementById('subtabContentCoupons');

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

  // --- 3. Theme Toggle ---
  const adminThemeToggle = document.getElementById('adminThemeToggle');
  const adminThemeIcon = document.getElementById('adminThemeIcon');
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
    grid: isDark ? 'rgba(51, 65, 85, 0.3)' : 'rgba(203, 213, 225, 0.7)',
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
      chart.update();
    };

    const updateDoughnutChart = (chart) => {
      if (!chart) return;
      if (chart.options?.plugins?.legend?.labels) {
        chart.options.plugins.legend.labels.color = legendText;
      }
      if (chart.legend?.legendItems) {
        chart.legend.legendItems.forEach(i => { i.fontColor = legendText; });
      }
      chart.update();
    };

    updateScaleChart(salesChartInstance);
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
    const appBody = document.getElementById('appBody');
    const phoneFrame = document.getElementById('phoneFrame');
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
      const totalU = document.getElementById('adminTotalUsers');
      if (totalU) totalU.innerText = formatNumber(m.total_users || 0);

      const activeU = document.getElementById('adminActiveUsers');
      if (activeU) activeU.innerText = `${formatNumber(m.active_panel_users || 0)} اکانت فعال پنل`;

      const rev = document.getElementById('adminTodayRevenue');
      if (rev) rev.innerText = formatNumber(m.today_revenue_toman || 0);

      // Traffic: if >= 1000 GB, convert to TB for concise and single-line layout
      const bw = document.getElementById('adminMonthTraffic');
      if (bw) {
        const trafficGb = Number(m.month_traffic_gb || 0);
        if (trafficGb >= 1000) {
          bw.innerText = `${(trafficGb / 1024).toFixed(2)} TB`;
        } else {
          bw.innerText = `${trafficGb} GB`;
        }
      }

      const onDev = document.getElementById('adminOnlineDevices');
      if (onDev) onDev.innerText = formatNumber(m.online_devices || 0);

      // Infra-Billing & Net Profit Analytics
      const mRev = document.getElementById('adminMonthlyRevenue');
      if (mRev) mRev.innerText = formatNumber(m.monthly_revenue_toman || 0);

      const iCost = document.getElementById('adminTotalInfraCost');
      if (iCost) iCost.innerText = formatNumber(m.total_infra_cost_toman || 0);

      const nProf = document.getElementById('adminNetProfit');
      if (nProf) {
        const netVal = Number(m.net_profit_toman || 0);
        const sign = netVal > 0 ? '+' : (netVal < 0 ? '-' : '');
        nProf.innerHTML = `<span dir="ltr">${sign}${formatNumber(Math.abs(netVal))}</span>`;
        nProf.className = netVal >= 0
          ? 'text-emerald-400 font-mono font-bold text-lg'
          : 'text-rose-400 font-mono font-bold text-lg';
      }

      const pMargin = document.getElementById('adminProfitMarginBadge');
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

      const costGb = document.getElementById('adminAvgCostPerGb');
      if (costGb) costGb.innerText = formatNumber(m.avg_cost_per_gb || 0);

      // Dynamic Pending Tasks Alert Banner (Hidden if no pending tasks)
      const pendingBox = document.getElementById('adminPendingBanner');
      const pendingSum = document.getElementById('adminPendingSummary');
      const viewPendingBtn = document.getElementById('viewPendingBtn');
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
      const clusterText = document.getElementById('adminClusterStatusText');
      if (clusterText) {
        clusterText.innerHTML = `وضعیت کلاستر: <b class="text-emerald-400">${formatNumber(onlineNodes)} از ${formatNumber(nodes.length)} نود آنلاین</b>`;
      }
      const syncText = document.getElementById('adminLastSyncText');
      if (syncText) syncText.innerText = 'Sync: آنلاین';

      // Render Dashboard Analytics Charts
      lastOverviewData = data;
      if (data.charts) {
        const c = data.charts;
        if (typeof Chart !== 'undefined') {
          renderAdminSalesChart(c.sales_labels, c.sales_data);
          renderAdminTrafficChart(c.traffic_labels, c.traffic_data, c.traffic_total_gb, c.today_traffic_gb);
          renderAdminLocationChart(c.location_share);
          renderAdminHourlyChart(c.hourly_distribution);
          renderAdminRetentionChart(c.retention_trend);
          renderAdminPlanSalesChart(c.plan_distribution);
          renderAdminPlatformChart(c.platform_distribution);
          renderAdminPaymentChart(c.payment_distribution);
          renderAdminRetentionStatsChart(c.retention_stats);
          renderAdminHwidChart(c.hwid_distribution);
        } else {
          setTimeout(() => {
            if (typeof Chart !== 'undefined' && lastOverviewData?.charts) {
              const ch = lastOverviewData.charts;
              renderAdminSalesChart(ch.sales_labels, ch.sales_data);
              renderAdminTrafficChart(ch.traffic_labels, ch.traffic_data, ch.traffic_total_gb, ch.today_traffic_gb);
              renderAdminLocationChart(ch.location_share);
              renderAdminHourlyChart(ch.hourly_distribution);
              renderAdminRetentionChart(ch.retention_trend);
              renderAdminPlanSalesChart(ch.plan_distribution);
              renderAdminPlatformChart(ch.platform_distribution);
              renderAdminPaymentChart(ch.payment_distribution);
              renderAdminRetentionStatsChart(ch.retention_stats);
              renderAdminHwidChart(ch.hwid_distribution);
            }
          }, 350);
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
    const canvas = document.getElementById('adminSalesChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const totalSum = (values || []).reduce((a, b) => a + b, 0);
    const totalEl = document.getElementById('salesChartTotal');
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

  let trafficChartInstance = null;
  function renderAdminTrafficChart(labels, values, totalGb, todayGb) {
    const canvas = document.getElementById('adminTrafficChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const currentToday = Number(todayGb || (values && values[values.length - 1]) || 0);
    const totalEl = document.getElementById('trafficChartTotal');
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
      color: isDark ? '#f8fafc' : '#0f172a',
      font: { family: 'Vazirmatn', size: 10, weight: '600' },
      generateLabels: (chart) => {
        const data = chart.data;
        if (!data.labels?.length || !data.datasets?.length) return [];
        const dataset = data.datasets[0];
        const textColor = isDark ? '#f8fafc' : '#0f172a';
        return data.labels.map((label, i) => {
          const fill = Array.isArray(dataset.backgroundColor) ? dataset.backgroundColor[i] : dataset.backgroundColor;
          return {
            text: label,
            fontColor: textColor,
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
    const canvas = document.getElementById('adminLocationChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rawLabels = locationShare?.labels || ['🌐'];
    const labels = rawLabels.map(l => {
      const clean = (l || '').replace(/[A-Za-z0-9_-]+/g, '').trim();
      return clean || '🌐';
    });
    const values = locationShare?.data || [1];
    const unit = locationShare?.unit || 'GB';

    if (locationChartInstance) {
      locationChartInstance.data.labels = labels;
      locationChartInstance.data.datasets[0].data = values;
      locationChartInstance.update();
      return;
    }

    locationChartInstance = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: [
            'rgba(139, 92, 246, 0.85)',
            'rgba(6, 182, 212, 0.85)',
            'rgba(16, 185, 129, 0.85)',
            'rgba(245, 158, 11, 0.85)',
            'rgba(244, 63, 94, 0.85)',
            'rgba(99, 102, 241, 0.85)',
          ],
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
              label: (ctx) => `${ctx.label}: ${formatNumber(ctx.raw)} ${unit}`
            }
          }
        }
      }
    });
  }

  let hourlyChartInstance = null;
  function renderAdminHourlyChart(hourlyDist) {
    const canvas = document.getElementById('adminHourlyChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const labels = hourlyDist?.labels || [];
    const values = hourlyDist?.data || [];
    const peakBadge = document.getElementById('peakHourBadge');
    if (peakBadge && hourlyDist?.peak_hour) {
      peakBadge.innerText = `Peak: ${hourlyDist.peak_hour}`;
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
              maxTicksLimit: 7,
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
    const canvas = document.getElementById('adminRetentionChart');
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
    const canvas = document.getElementById('adminPlanSalesChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rawLabels = planDist?.labels || ['پلن استاندارد'];
    const labels = rawLabels.map(formatPlanLabelWithIconFirst);
    const values = planDist?.sales_count || [1];

    if (planSalesChartInstance) {
      planSalesChartInstance.data.labels = labels;
      planSalesChartInstance.data.datasets[0].data = values;
      planSalesChartInstance.update();
      return;
    }

    planSalesChartInstance = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: [
            'rgba(236, 72, 153, 0.85)',
            'rgba(168, 85, 247, 0.85)',
            'rgba(99, 102, 241, 0.85)',
            'rgba(6, 182, 212, 0.85)',
            'rgba(16, 185, 129, 0.85)',
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
              label: (ctx) => `${ctx.label}: ${formatNumber(ctx.raw)} سفارش`
            }
          }
        }
      }
    });
  }

  // OS & Platform Share Chart
  let platformChartInstance = null;
  function renderAdminPlatformChart(platformDist) {
    const canvas = document.getElementById('adminPlatformChart');
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
    const canvas = document.getElementById('adminPaymentChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const labels = paymentDist?.labels || ['کارت به کارت (ریالی)', 'ارز دیجیتال (کریپتو / TON)'];
    const values = paymentDist?.counts || [0, 0];
    const volumes = paymentDist?.volumes || [0, 0];

    if (paymentChartInstance) {
      paymentChartInstance.data.labels = labels;
      paymentChartInstance.data.datasets[0].data = values;
      paymentChartInstance.update();
      return;
    }

    paymentChartInstance = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: [
            'rgba(6, 182, 212, 0.85)',
            'rgba(168, 85, 247, 0.85)',
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
    const canvas = document.getElementById('adminChurnChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const labels = retentionStats?.labels || ['تمدید شده (مشتریان وفادار)', 'دوره اول (فعال)', 'ریزش (عدم تمدید)'];
    const values = retentionStats?.data || [0, 0, 0];
    const retRate = retentionStats?.retention_rate !== undefined ? retentionStats.retention_rate : 0;

    const badge = document.getElementById('churnRateBadge');
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
    const canvas = document.getElementById('adminHwidChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const labels = hwidDist?.labels || ['1 دستگاه', '2 دستگاه', '3+ دستگاه', 'ریسک بالا (4+)'];
    const values = hwidDist?.data || [0, 0, 0, 0];
    const riskCount = hwidDist?.high_risk_count || 0;

    const badge = document.getElementById('hwidRiskBadge');
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
    const container = document.getElementById('adminOverviewNodesList');
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
                <span class="font-bold text-white block text-xs">${n.name || 'Node'}</span>
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
                <span class="font-mono text-cyan-300 text-xs block truncate" dir="ltr">${n.address || '—'}</span>
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
    const body = document.getElementById(`nodeBody_${idx}`);
    const chev = document.getElementById(`nodeChevron_${idx}`);
    if (body) {
      body.classList.toggle('hidden');
      if (chev) {
        chev.style.transform = body.classList.contains('hidden') ? 'rotate(0deg)' : 'rotate(180deg)';
      }
    }
    if (window.hapticFeedback) window.hapticFeedback('impact');
  };

  function renderFullNodes(nodes) {
    const container = document.getElementById('adminNodesFullList');
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
          dueBadgeHtml = `<span class="bg-slate-800 text-slate-300 border border-slate-700 px-2 py-0.5 rounded-lg font-mono">🗓️ ${shamsiDate} (${n.days_until_due} روز)</span>`;
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
              <h4 class="font-bold text-xs text-white truncate">${n.name || 'Server Node'}</h4>
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
              <span class="text-[10px] font-bold font-mono ${statusBorder} bg-transparent px-2.5 py-1 rounded-xl border flex items-center gap-1.5">
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
    const listContainer = document.getElementById('adminUsersList');
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
      const paginationEl = document.getElementById('adminUsersPagination');
      const pageInfo = document.getElementById('adminUsersPageInfo');
      const prevBtn = document.getElementById('adminUsersPrevBtn');
      const nextBtn = document.getElementById('adminUsersNextBtn');

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
    const listContainer = document.getElementById('adminUsersList');
    if (!listContainer) return;
    if (users.length === 0) {
      listContainer.innerHTML = '<div class="p-8 text-center text-xs text-slate-400">هیچ کاربری با این مشخصات یافت نشد.</div>';
      return;
    }

    listContainer.innerHTML = users.map(u => {
      // Prioritize real full_name; fallback to 'کاربر ID' if missing or starts with @
      const rawName = u.full_name || '';
      const displayName = (rawName && !rawName.startsWith('@')) ? rawName : `کاربر ${u.telegram_id}`;
      const safeDisplayName = (displayName || '').replace(/'/g, "\\'");
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
        let statusLabel = `${percentUsed}% مصرف`;

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
          statusLabel = `${percentUsed}% مصرف (بحرانی)`;
        } else if (percentUsed >= 70) {
          barGradient = 'from-amber-500 to-orange-400';
          barGlow = 'shadow-[0_0_10px_rgba(245,158,11,0.35)]';
          badgeColor = 'text-amber-600 dark:text-amber-400 bg-transparent border-amber-500/30';
          statusLabel = `${percentUsed}% مصرف`;
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
            <!-- Right: Avatar + Profile Name + Status Badge underneath -->
            <div class="flex items-center gap-2.5 min-w-0">
              <!-- User Profile Avatar with Initials Fallback -->
              <div class="w-10 h-10 rounded-full bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-white text-xs shadow overflow-hidden flex-shrink-0 relative">
                <img src="${avatarSrc}" alt="Avatar" class="w-full h-full object-cover" onerror="this.classList.add('hidden'); if(this.nextElementSibling) this.nextElementSibling.classList.remove('hidden');" />
                <span class="${u.avatar_url ? 'hidden' : ''} font-bold">${initial}</span>
              </div>

              <!-- Name on top, Status Badge underneath -->
              <div class="min-w-0 flex-1">
                <!-- 1. Profile Name (اسم پروفایل کاربر) -->
                <div class="flex items-center gap-1.5 min-w-0">
                  <div onclick="window.adminActions.quickCopy('${safeDisplayName}', 'نام کاربر')" class="text-xs font-bold text-white truncate max-w-[130px] sm:max-w-[170px] cursor-pointer hover:text-cyan-300 active:scale-95 transition" title="${escapeHtml(displayName)}">
                    ${(displayName || '').startsWith('@') ? `<span class="truncate inline-block font-mono" dir="ltr" style="unicode-bidi: isolate;">${escapeHtml(displayName)}</span>` : `<span class="truncate">${escapeHtml(displayName)}</span>`}
                  </div>
                  ${u.is_online ? '<span class="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)] animate-pulse flex-shrink-0" title="متصل به سرور"></span>' : ''}
                </div>

                <!-- Status Badge (فعال / بدون اکانت) Under the name -->
                <div class="flex items-center gap-1.5 mt-1">
                  <div>${statusBadge}</div>
                  ${expiringBadgeHtml}
                </div>
              </div>
            </div>

            <!-- Left: Top = Wallet Balance, Bottom = @Username + ID on ONE line -->
            <div class="text-left flex flex-col items-end gap-1 flex-shrink-0">
              <span class="text-[11px] font-mono font-bold text-emerald-400">
                ${formatNumber(u.wallet_balance || 0)} ت
              </span>

              <!-- Items 2 & 3: Username + Telegram ID together on ONE line on the left side -->
              <div class="flex items-center gap-1 text-[10px] text-slate-400 font-mono" dir="ltr">
                ${u.username ? `<span onclick="window.adminActions.quickCopy('@${u.username}', 'نام کاربری')" class="cursor-pointer hover:text-cyan-300 text-slate-300 font-mono truncate max-w-[95px] inline-block" title="@${u.username}">@${u.username}</span>` : ''}
                ${u.username ? '<span class="text-slate-600">•</span>' : ''}
                <span onclick="window.adminActions.quickCopy('${u.telegram_id}', 'شناسه عددی')" class="cursor-pointer hover:text-cyan-300 text-slate-400" title="شناسه تلگرام">${u.telegram_id}</span>
              </div>
            </div>
          </div>

          <!-- Structured Service Metrics -->
          ${serviceLineHtml}

          <!-- Quick Action Buttons: 3x2 Symmetrical Grid -->
          <div class="space-y-1.5 pt-1">
            <div class="grid grid-cols-3 gap-1.5 text-center text-[10px]">
              <button class="bg-transparent hover:bg-blue-500/10 text-blue-500 dark:text-blue-400 border border-blue-500/30 hover:border-blue-400/60 py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" onclick="window.adminActions.openModifyUser(${u.telegram_id}, '${(u.username || '').replace(/'/g, "\\'")}', '${safeDisplayName}')" title="افزایش حجم یا تمدید زمان">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"/></svg>
                <span>حجم و تمدید</span>
              </button>
              <button class="bg-transparent hover:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 hover:border-emerald-400/60 py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" onclick="window.adminActions.openWalletModal(${u.telegram_id}, '${safeDisplayName}')" title="شارژ یا کسر موجودی">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"/></svg>
                <span>موجودی</span>
              </button>
              <button class="bg-transparent hover:bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/30 hover:border-purple-400/60 py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" onclick="window.adminActions.openTrialModal(${u.telegram_id}, '${(u.username || '').replace(/'/g, "\\'")}', '${safeDisplayName}')" title="فعال‌سازی مجدد تست">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v13m0-13V6a2 2 0 112 2h-2zm0 0V5.5A2.5 2.5 0 109.5 8H12zm-7 4h14M5 12a2 2 0 01-2-2V7a2 2 0 012-2h14a2 2 0 012 2v3a2 2 0 01-2 2M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7"/></svg>
                <span>اکانت تست</span>
              </button>
            </div>
            <div class="grid grid-cols-3 gap-1.5 text-center text-[10px]">
              <button class="bg-transparent hover:bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border border-cyan-500/30 hover:border-cyan-400/60 py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" onclick="window.adminActions.openSubModal(${u.telegram_id}, '${safeDisplayName}', '${p?.subscription_url || ''}')" title="لینک سابسکریپشن">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/></svg>
                <span>لینک ساب</span>
              </button>
              <button class="bg-transparent hover:bg-teal-500/10 text-teal-600 dark:text-teal-400 border border-teal-500/30 hover:border-teal-400/60 py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" onclick="window.adminActions.openHwidModal(${u.telegram_id}, '${safeDisplayName}')" title="دستگاه‌های فعال و نشست‌ها">
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
  const userSearchInput = document.getElementById('userSearchInput');
  const userSearchClear = document.getElementById('userSearchClear');

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
  document.getElementById('adminUsersPrevBtn')?.addEventListener('click', () => {
    if (currentPage > 1) {
      fetchAdminUsers(currentPage - 1);
      if (window.hapticFeedback) window.hapticFeedback('impact');
    }
  });

  document.getElementById('adminUsersNextBtn')?.addEventListener('click', () => {
    fetchAdminUsers(currentPage + 1);
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  // --- Confirmation & Report Modals ---
  function showConfirmModal({ title = 'تایید عملیات', message = 'آیا از انجام این عملیات اطمینان دارید؟', confirmText = 'تایید و اجرا', isDanger = true }) {
    return new Promise((resolve) => {
      const modal = document.getElementById('confirmActionModal');
      const titleEl = document.getElementById('confirmModalTitle');
      const msgEl = document.getElementById('confirmModalMessage');
      const confirmBtn = document.getElementById('confirmModalConfirmBtn');
      const cancelBtn = document.getElementById('confirmModalCancelBtn');
      const iconBox = document.getElementById('confirmModalIconBox');

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
    const modal = document.getElementById('operationReportModal');
    const titleEl = document.getElementById('opReportTitle');
    const subEl = document.getElementById('opReportSubtitle');
    const iconBox = document.getElementById('opReportIconBox');
    const contentEl = document.getElementById('opReportContent');

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
      document.getElementById('operationReportModal')?.classList.add('hidden');
    },

    // Unified Modify User (Volume & Duration)
    openModifyUser(telegram_id, username = '', name = '') {
      currentModifyTarget = { telegram_id, username, name };
      const modal = document.getElementById('modifyUserModal');
      const dispEl = document.getElementById('modifyModalUserDisplay');
      const trInput = document.getElementById('modifyModalTraffic');
      const daysInput = document.getElementById('modifyModalDays');

      if (modal) modal.classList.remove('hidden');
      const handle = username ? `@${username}` : (name || `کاربر ${telegram_id}`);
      if (dispEl) dispEl.innerText = `${handle} - ${telegram_id}`;
      if (trInput) trInput.value = '';
      if (daysInput) daysInput.value = '';
      trInput?.focus();
      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    setModifyTraffic(gb) {
      const trInput = document.getElementById('modifyModalTraffic');
      if (trInput) {
        const cur = parseFloat(trInput.value) || 0;
        trInput.value = (cur + gb);
      }
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    setModifyDays(days) {
      const daysInput = document.getElementById('modifyModalDays');
      if (daysInput) {
        const cur = parseInt(daysInput.value, 10) || 0;
        daysInput.value = (cur + days);
      }
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    closeModifyModal() {
      const modal = document.getElementById('modifyUserModal');
      if (modal) modal.classList.add('hidden');
      currentModifyTarget = null;
    },

    async applyUserModification() {
      if (!currentModifyTarget) return;
      const trafficGb = parseFloat(document.getElementById('modifyModalTraffic')?.value || 0);
      const days = parseInt(document.getElementById('modifyModalDays')?.value || 0, 10);

      const validTraffic = !isNaN(trafficGb) && trafficGb > 0 ? trafficGb : 0;
      const validDays = !isNaN(days) && days > 0 ? days : 0;

      if (validTraffic <= 0 && validDays <= 0) {
        if (window.showToast) window.showToast('لطفاً حداقل یکی از مقادیر حجم یا روز را وارد کنید.');
        return;
      }

      const submitBtn = document.getElementById('modifyModalSubmitBtn');
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
      const nameEl = document.getElementById('trialModalUserName');
      if (nameEl) nameEl.innerText = name || (username ? `@${username}` : `کاربر ${telegram_id}`);
      const idEl = document.getElementById('trialModalUserId');
      if (idEl) idEl.innerText = `#${telegram_id}`;
      document.getElementById('trialModal')?.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    closeTrialModal() {
      document.getElementById('trialModal')?.classList.add('hidden');
      currentTrialTarget = null;
    },

    async confirmResetTrial() {
      if (!currentTrialTarget) return;
      const { telegram_id, name } = currentTrialTarget;
      const btn = document.getElementById('confirmTrialResetBtn');
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

    // --- Wallet Actions ---
    openWalletModal(telegram_id, name) {
      currentWalletTarget = { telegram_id, name };
      const modal = document.getElementById('walletModal');
      const title = document.getElementById('walletModalTitle');
      const amtInput = document.getElementById('walletModalAmount');
      const reasonInput = document.getElementById('walletModalReason');
      if (modal) modal.classList.remove('hidden');
      if (title) title.innerText = `💰 کیف پول: ${name}`;
      if (amtInput) amtInput.value = '50000';
      if (reasonInput) reasonInput.value = 'شارژ دستی توسط مدیریت';
      amtInput?.focus();
    },

    closeWalletModal() {
      document.getElementById('walletModal')?.classList.add('hidden');
      currentWalletTarget = null;
    },

    async applyWalletModification() {
      if (!currentWalletTarget) return;
      const rawAmount = parseInt(document.getElementById('walletModalAmount')?.value || '0', 10);
      if (isNaN(rawAmount) || rawAmount <= 0) {
        if (window.showToast) window.showToast('لطفاً مبلغ معتبری وارد کنید.');
        return;
      }
      const finalAmount = walletActionType === 'add' ? rawAmount : -rawAmount;
      const reason = document.getElementById('walletModalReason')?.value?.trim() || 'شارژ توسط مدیریت';
      const submitBtn = document.getElementById('walletModalSubmitBtn');
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
      const modal = document.getElementById('subModal');
      const title = document.getElementById('subModalTitle');
      const input = document.getElementById('subModalInput');
      if (modal) modal.classList.remove('hidden');
      if (title) title.innerText = `🔄 لینک اشتراک: ${name}`;
      if (input) {
        input.value = subUrl || '';
        if (!subUrl) input.placeholder = 'اکانت پنل برای این کاربر یافت نشد یا لینکی صادر نشده است';
      }
      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    closeSubModal() {
      document.getElementById('subModal')?.classList.add('hidden');
      currentSubTarget = null;
    },

    async copySubLink() {
      const input = document.getElementById('subModalInput');
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

      const regenBtn = document.getElementById('subModalRegenBtn');
      if (regenBtn) {
        regenBtn.disabled = true;
        regenBtn.innerText = 'در حال صدور لینک جدید...';
      }
      try {
        const res = await window.api.revokeUserSub(telegram_id);
        if (res && res.ok && res.subscription_url) {
          currentSubTarget.subUrl = res.subscription_url;
          const input = document.getElementById('subModalInput');
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
      const modal = document.getElementById('hwidModal');
      const title = document.getElementById('hwidModalTitle');
      if (modal) modal.classList.remove('hidden');
      if (title) title.innerText = `📱 دستگاه‌ها و نشست‌ها: ${name}`;
      if (window.hapticFeedback) window.hapticFeedback('impact');
      await this.switchDeviceModalTab(initialTab);
    },

    async switchDeviceModalTab(tab = 'hwid') {
      this.currentDeviceTab = tab;
      const hwidBtn = document.getElementById('deviceTabBtn_hwid');
      const sessionsBtn = document.getElementById('deviceTabBtn_sessions');
      const srhBtn = document.getElementById('deviceTabBtn_srh');
      const hwidPane = document.getElementById('hwidTabPane');
      const sessionsPane = document.getElementById('sessionsTabPane');
      const srhPane = document.getElementById('srhTabPane');

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
      const list = document.getElementById('userSrhList');
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
            <div class="srh-card bg-slate-900/60 p-2.5 rounded-2xl border border-slate-700/60 flex items-center justify-between gap-2">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5 mb-1">
                  <span class="text-sm">${r.client_icon || '📱'}</span>
                  <b class="text-white text-xs truncate">${r.client_name || 'کلاینت'}</b>
                  <span class="text-[9px] px-1.5 py-0.5 rounded bg-transparent border border-slate-700/60 text-slate-400 font-mono">${r.client_tag || 'App'}</span>
                </div>
                <div class="flex items-center gap-2 text-[10px] text-slate-400">
                  <span dir="ltr" class="font-mono text-cyan-300 select-all cursor-pointer" onclick="window.copyToClipboard('${r.ip}')" title="کپی آی‌پی">🌐 ${r.ip}</span>
                  <span>•</span>
                  <span>⏱️ ${r.relative_time}</span>
                </div>
              </div>
              <div class="flex-shrink-0 text-right">
                <span class="inline-flex items-center gap-1 text-[9px] font-bold ${r.is_success ? 'text-emerald-400 border-emerald-500/30' : 'text-rose-400 border-rose-500/30'} bg-transparent px-2 py-0.5 rounded-lg border">
                  ${r.is_success ? 'موفق' : (r.status_code ? 'خطا ' + r.status_code : 'خطا')}
                </span>
                <span class="block text-[8px] text-slate-500 font-mono mt-0.5">${r.date_str ? r.date_str.split(' ')[1] : ''}</span>
              </div>
            </div>
          `).join('');
        }
      } catch (e) {
        if (list) list.innerHTML = '<div class="p-4 text-center text-rose-400">خطای ارتباط با سرور</div>';
      }
    },

    async loadHwidDevices(telegram_id) {
      const list = document.getElementById('hwidDevicesList');
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
            const os = d.os || d.platform || 'دستگاه متصل';
            const brand = d.brand || d.model || '';
            const ip = d.requestIp || d.ip || d.lastIp || d.clientIp || '—';
            return `
              <div class="bg-transparent p-3 rounded-2xl border border-slate-700/60 dark:border-slate-700/60 flex items-center justify-between gap-2.5">
                <div class="min-w-0 flex-1">
                  <b class="text-white text-xs block truncate">${os} ${brand ? '(' + brand + ')' : ''}</b>
                  <div class="flex items-center gap-1.5 mt-0.5 text-[10px] text-slate-400">
                    <span>آی‌پی:</span>
                    <span dir="ltr" class="font-mono text-cyan-400 dark:text-cyan-300">${ip}</span>
                  </div>
                  <div class="flex items-center gap-1.5 mt-1">
                    <span class="text-[9px] text-slate-400">HWID:</span>
                    <span dir="ltr" class="font-mono text-[9px] text-slate-300 bg-transparent px-2 py-0.5 rounded-lg border border-slate-700/60 truncate max-w-[170px]" title="${hwid}">${hwid}</span>
                  </div>
                </div>
                <button onclick="window.adminActions.deleteHwid(${telegram_id}, '${hwid}')" class="bg-transparent hover:bg-rose-500/10 text-rose-400 border border-rose-500/30 hover:border-rose-400 p-2.5 rounded-xl transition active:scale-95 flex items-center justify-center flex-shrink-0" title="قطع اتصال این دستگاه">
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
      const list = document.getElementById('userSessionsList');
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
      const list = document.getElementById('userSessionsList');
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
          <div class="flex items-center justify-between bg-slate-900/80 px-2.5 py-1 rounded-xl border border-slate-700/60 text-xs">
            <span class="text-slate-400 text-[10px]">آی‌پی کلاینت:</span>
            <span dir="ltr" class="font-mono text-cyan-400 dark:text-cyan-300 font-bold">${ip}</span>
          </div>
        `).join('');

        return `
          <div class="bg-slate-800/80 rounded-2xl p-3 border border-slate-700/60 space-y-2">
            <div class="flex items-center justify-between">
              <span class="text-white font-bold text-xs flex items-center gap-1.5">
                <span class="text-sm">${flag}</span>
                <span>${nodeName}</span>
              </span>
              <span class="text-[10px] bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 px-2 py-0.5 rounded-lg font-mono">
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
      document.getElementById('hwidModal')?.classList.add('hidden');
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
      const container = document.getElementById('adminPlansList');
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
                    <b class="text-white text-xs font-bold truncate">${cleanName}</b>
                    ${pkgIcon ? `<span class="text-sm select-none leading-none flex-shrink-0" title="آیکون بسته">${pkgIcon}</span>` : ''}
                    ${statusBadge}
                  </div>
                </div>

                <!-- Price on the left -->
                <span class="text-sm font-black text-emerald-400 font-mono flex-shrink-0">${formatNumber(p.price || 0)} <span class="text-[10px] font-sans font-normal text-slate-400">تومان</span></span>
              </div>

              ${p.description ? `<p class="text-[10px] text-slate-400 line-clamp-1 pr-9.5">${p.description}</p>` : ''}

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
                <button onclick="window.adminActions.deletePlan(${p.id}, '${p.name}')" class="bg-transparent hover:bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/30 hover:border-rose-400/60 px-3 py-1.5 rounded-xl transition font-medium flex items-center justify-center active:scale-95" title="حذف سرویس">
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
      const modal = document.getElementById('planModal');
      if (modal) modal.classList.remove('hidden');
      document.getElementById('planModalTitle').innerText = plan ? `ویرایش تعرفه: ${plan.name}` : 'ایجاد تعرفه جدید';
      document.getElementById('planModalId').value = plan ? plan.id : '';
      document.getElementById('planModalName').value = plan ? plan.name : '';
      document.getElementById('planModalPrice').value = plan ? plan.price : '';
      document.getElementById('planModalTraffic').value = plan ? plan.traffic_gb : '';
      document.getElementById('planModalDuration').value = plan ? plan.duration_days : '';
      document.getElementById('planModalHwid').value = plan ? (plan.hwid_limit || '') : '';
      document.getElementById('planModalDesc').value = plan ? (plan.description || '') : '';
      document.getElementById('planModalActive').checked = plan ? !!plan.is_active : true;
    },

    closePlanModal() {
      document.getElementById('planModal')?.classList.add('hidden');
    },

    async savePlan() {
      const id = document.getElementById('planModalId')?.value;
      const name = document.getElementById('planModalName')?.value?.trim();
      const price = parseInt(document.getElementById('planModalPrice')?.value || '0', 10);
      const traffic_gb = parseInt(document.getElementById('planModalTraffic')?.value || '0', 10);
      const duration_days = parseInt(document.getElementById('planModalDuration')?.value || '0', 10);
      const hwid_limit = parseInt(document.getElementById('planModalHwid')?.value || '0', 10) || null;
      const description = document.getElementById('planModalDesc')?.value?.trim();
      const is_active = document.getElementById('planModalActive')?.checked ?? true;

      if (!name) {
        if (window.showToast) window.showToast('نام تعرفه الزامی است.');
        return;
      }

      const saveBtn = document.getElementById('planModalSaveBtn');
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
      const container = document.getElementById('adminCouponsList');
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
          const statusBadge = c.is_active
            ? '<span class="text-[10px] bg-transparent text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-lg font-bold">فعال</span>'
            : '<span class="text-[10px] bg-transparent text-slate-500 dark:text-slate-400 border border-slate-400/30 px-2 py-0.5 rounded-lg font-medium">غیرفعال</span>';

          const discountText = c.discount_percent > 0
            ? `${c.discount_percent}٪ تخفیف`
            : `${formatNumber(c.discount_amount || 0)} تومان`;

          const maxText = c.max_uses > 0 ? `${c.used_count || 0} / ${c.max_uses}` : `${c.used_count || 0} (نامحدود)`;
          const expiryText = c.expires_at || 'نامحدود (دائمی)';

          return `
            <div class="coupon-card bg-slate-800/80 rounded-2xl p-4 border border-slate-700/80 space-y-3 shadow transition">
              <div class="flex items-start justify-between">
                <div>
                  <div class="flex items-center gap-2">
                    <span class="font-mono font-bold text-pink-600 dark:text-pink-400 text-sm tracking-wider uppercase bg-pink-500/10 border border-pink-500/30 px-2.5 py-0.5 rounded-xl">${c.code}</span>
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
                  <b class="text-slate-200">${expiryText}</b>
                </div>
              </div>

              <div class="flex gap-2 pt-1 text-[11px]">
                <button onclick="window.adminActions.openCouponUsages(${c.id}, '${c.code}')" class="flex-1 bg-transparent hover:bg-pink-500/10 text-pink-600 dark:text-pink-400 border border-pink-500/30 hover:border-pink-400/60 py-1.5 rounded-xl transition font-semibold text-center flex items-center justify-center gap-1.5 active:scale-95">
                  <svg class="w-3.5 h-3.5 text-pink-600 dark:text-pink-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
                  <span>استفاده‌کنندگان (${formatNumber(c.used_count || 0)})</span>
                </button>
                <button onclick="window.adminActions.toggleCoupon(${c.id}, ${c.is_active})" class="bg-transparent hover:bg-slate-500/10 ${c.is_active ? 'text-amber-600 dark:text-amber-400 border border-amber-500/30 hover:border-amber-400/60' : 'text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 hover:border-emerald-400/60'} py-1.5 px-3 rounded-xl transition font-semibold text-center active:scale-95">
                  ${c.is_active ? 'غیرفعال‌سازی' : 'فعال‌سازی'}
                </button>
                <button onclick="window.adminActions.deleteCoupon(${c.id}, '${c.code}')" class="bg-transparent hover:bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/30 hover:border-rose-400/60 px-3 py-1.5 rounded-xl transition font-medium flex items-center justify-center active:scale-95" title="حذف کد تخفیف">
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
      document.getElementById('couponModal')?.classList.remove('hidden');
      document.getElementById('couponModalCode').value = '';
      document.getElementById('couponModalPercent').value = '20';
      document.getElementById('couponModalAmount').value = '0';
      document.getElementById('couponModalMaxUses').value = '0';
      document.getElementById('couponModalDays').value = '30';
    },

    closeCouponModal() {
      document.getElementById('couponModal')?.classList.add('hidden');
    },

    async saveCoupon() {
      const code = document.getElementById('couponModalCode')?.value?.trim();
      const discount_percent = parseInt(document.getElementById('couponModalPercent')?.value || '0', 10);
      const discount_amount = parseInt(document.getElementById('couponModalAmount')?.value || '0', 10);
      const max_uses = parseInt(document.getElementById('couponModalMaxUses')?.value || '0', 10);
      const expires_days = parseInt(document.getElementById('couponModalDays')?.value || '0', 10);

      if (!code) {
        if (window.showToast) window.showToast('کد تخفیف الزامی است.');
        return;
      }

      const saveBtn = document.getElementById('couponModalSaveBtn');
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

    async deleteCoupon(id, code) {
      if (!confirm(`آیا از حذف کد تخفیف «${code}» اطمینان دارید؟`)) return;
      try {
        const res = await window.api.deleteAdminCoupon(id);
        if (res && res.ok) {
          if (window.showToast) window.showToast('✅ کد تخفیف با موفقیت حذف شد.');
          this.fetchAdminCoupons();
        }
      } catch (e) {}
    },

    async openCouponUsages(coupon_id, code) {
      const modal = document.getElementById('couponUsagesModal');
      const subtitle = document.getElementById('couponUsagesModalSubtitle');
      const list = document.getElementById('couponUsagesList');
      const countStat = document.getElementById('couponUsagesCountStat');
      const totalDiscStat = document.getElementById('couponUsagesTotalDiscountStat');

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
          const safeDisplayName = displayName.replace(/'/g, "\\'");
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
                    <b class="text-slate-900 dark:text-white text-xs font-bold block truncate max-w-[130px] sm:max-w-[160px] cursor-pointer hover:text-pink-400" onclick="window.adminActions.quickCopy('${safeDisplayName}', 'نام کاربر')" title="${displayName}">${displayName}</b>
                    <div class="flex items-baseline gap-1 text-emerald-600 dark:text-emerald-400 font-bold" dir="rtl">
                      <span class="text-xs font-black font-mono leading-none">${formatNumber(u.discount_applied || 0)}</span>
                      <span class="text-[10px] text-emerald-600/90 dark:text-emerald-500/90 font-sans">تومان</span>
                    </div>
                  </div>
                </div>

                <!-- Left column: Username on line 1, Numeric ID on line 2 (سمت چپ‌ترین نقطه، بالا و بدون ID:) -->
                <div class="flex flex-col items-start justify-center gap-0.5 font-mono text-[11px] text-slate-500 dark:text-slate-400 flex-shrink-0 text-left" dir="ltr">
                  ${hasUsername ? `
                    <div class="text-[11px] text-pink-500 dark:text-pink-400 font-mono cursor-pointer hover:underline truncate max-w-[130px] leading-tight" onclick="window.adminActions.quickCopy('@${u.username}', 'نام کاربری')" title="@${u.username}">
                      @${u.username}
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
      document.getElementById('couponUsagesModal')?.classList.add('hidden');
    },

    openUserChat(telegram_id, name, tag, topup_id) {
      activeChatTelegramId = telegram_id;
      activeChatUserName = name || String(telegram_id);
      const inputId = document.getElementById('directTicketUserId');
      if (inputId) inputId.value = String(telegram_id);

      const chatContainer = document.getElementById('adminChatContainer');
      if (chatContainer) chatContainer.classList.remove('hidden');

      const badgeEl = document.getElementById('activeChatReceiptBadge');
      if (badgeEl) badgeEl.style.display = 'none';

      const statusBadgeEl = document.getElementById('activeChatStatusBadge');
      if (statusBadgeEl) {
        if (topup_id) {
          statusBadgeEl.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30';
          statusBadgeEl.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>فیش ${topup_id}`;
        } else {
          statusBadgeEl.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-bold bg-blue-500/15 text-blue-400 border border-blue-500/30';
          statusBadgeEl.innerText = 'پشتیبانی کاربر';
        }
      }

      const nameEl = document.getElementById('activeChatUserName');
      if (nameEl) nameEl.textContent = name || `کاربر ${telegram_id}`;

      const avatarEl = document.getElementById('activeChatUserAvatar');
      if (avatarEl) {
        const initial = ((name || 'U').replace('@', '')[0] || 'U').toUpperCase();
        avatarEl.innerHTML = `<img src="/api/user/avatar?user_id=${telegram_id}" alt="Avatar" class="w-full h-full object-cover" onerror="this.classList.add('hidden'); if(this.nextElementSibling) this.nextElementSibling.classList.remove('hidden');" /><span class="font-bold">${initial}</span>`;
      }

      const tagEl = document.getElementById('activeChatUserTag');
      if (tagEl) {
        const cleanTag = tag && tag.startsWith('@') ? tag : (name && name.startsWith('@') ? name : '');
        tagEl.textContent = cleanTag || '';
        tagEl.style.display = cleanTag ? 'block' : 'none';
      }

      const idEl = document.getElementById('activeChatUserId');
      if (idEl) idEl.innerHTML = `<span onclick="window.adminActions.quickCopy('${telegram_id}', 'شناسه عددی')" class="cursor-pointer hover:text-cyan-300 transition">${telegram_id}</span>`;

      loadUserChatMessages(telegram_id);

      const msgInput = document.getElementById('directTicketMsg');
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
      const chatContainer = document.getElementById('adminChatContainer');
      if (chatContainer) chatContainer.classList.add('hidden');
      if (window.hapticFeedback) window.hapticFeedback('light');
    },

    toggleSettingsBox(targetId) {
      if (!targetId) return;
      const targetBody = document.getElementById(targetId);
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
      const modal = document.getElementById('receiptPhotoModal');
      const img = document.getElementById('receiptModalImage');
      const spinner = document.getElementById('receiptModalSpinner');
      const errBox = document.getElementById('receiptModalError');
      const textBox = document.getElementById('receiptModalTextInfo');
      const titleEl = document.getElementById('receiptModalTitle');

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
        const initData = window.Telegram?.WebApp?.initData || '';
        const fetchUrl = (photoUrl && photoUrl.includes('?'))
          ? `${photoUrl}&initData=${encodeURIComponent(initData)}`
          : `/api/admin/topup/photo?id=${topupId || ''}&initData=${encodeURIComponent(initData)}`;

        const response = await fetch(fetchUrl, {
          headers: {
            'X-Telegram-Init-Data': initData,
          }
        });

        if (!response.ok) {
          throw new Error(response.status === 404 ? 'تصویری برای این فیش یافت نشد یا ثبت نشده است.' : 'خطا در دریافت تصویر رسید از تلگرام');
        }

        const blob = await response.blob();
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
      const modal = document.getElementById('receiptPhotoModal');
      const img = document.getElementById('receiptModalImage');
      const spinner = document.getElementById('receiptModalSpinner');
      const errBox = document.getElementById('receiptModalError');
      const textBox = document.getElementById('receiptModalTextInfo');
      const textContent = document.getElementById('receiptModalTextContent');
      const titleEl = document.getElementById('receiptModalTitle');

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
      const modal = document.getElementById('receiptPhotoModal');
      if (modal) modal.classList.add('hidden');
    },

    openCryptoRatesModal() {
      const modal = document.getElementById('cryptoRatesModal');
      if (modal) modal.classList.remove('hidden');
      this.refreshLiveCryptoRates();
      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    closeCryptoRatesModal() {
      document.getElementById('cryptoRatesModal')?.classList.add('hidden');
    },

    async refreshLiveCryptoRates() {
      const container = document.getElementById('cryptoRatesContent');
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
                <button onclick="window.adminActions.applySpecificRate('usdt', ${p})" class="bg-transparent hover:bg-emerald-500/10 text-emerald-400 hover:text-emerald-300 border border-emerald-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
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
                <button onclick="window.adminActions.applySpecificRate('eur', ${p})" class="bg-transparent hover:bg-indigo-500/10 text-indigo-400 hover:text-indigo-300 border border-indigo-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
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
                <button onclick="window.adminActions.applySpecificRate('ton', ${p})" class="bg-transparent hover:bg-cyan-500/10 text-cyan-400 hover:text-cyan-300 border border-cyan-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
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
                <button onclick="window.adminActions.applySpecificRate('ton', ${tonTomanBinance})" class="bg-transparent hover:bg-cyan-500/10 text-cyan-400 hover:text-cyan-300 border border-cyan-500/40 text-[10px] font-bold px-2 py-0.5 rounded-lg transition active:scale-95">
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
        `;
      } catch (e) {
        container.innerHTML = '<div class="p-6 text-center text-xs text-rose-400">خطای ارتباط با سرور در استعلام نرخ‌ها</div>';
      }
    },

    async applySpecificRate(type, val) {
      if (!val) return;
      const numVal = parseInt(val, 10);
      if (isNaN(numVal) || numVal <= 0) return;

      const payload = {};
      if (type === 'usdt') {
        const inp = document.getElementById('settingUsdtRate');
        if (inp) inp.value = numVal;
        payload.usdt_rate_toman = numVal;
        window.currentUsdRate = numVal;
      } else if (type === 'eur') {
        const inp = document.getElementById('settingEurRate');
        if (inp) inp.value = numVal;
        payload.eur_rate_toman = numVal;
        window.currentEurRate = numVal;
      } else if (type === 'ton') {
        const inp = document.getElementById('settingTonRate');
        if (inp) inp.value = numVal;
        payload.ton_rate_toman = numVal;
      }

      try {
        const res = await window.api.saveAdminSettings(payload);
        if (res && res.ok) {
          const typeName = type === 'usdt' ? 'تتر' : (type === 'eur' ? 'یورو' : 'تون');
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
      const rates = window.lastLiveCryptoRates;
      if (!rates) return;
      const usdtInp = document.getElementById('settingUsdtRate');
      const eurInp = document.getElementById('settingEurRate');
      const tonInp = document.getElementById('settingTonRate');
      if (usdtInp && rates.usdt) {
        usdtInp.value = rates.usdt;
        window.currentUsdRate = rates.usdt;
      }
      if (eurInp && rates.eur) {
        eurInp.value = rates.eur;
        window.currentEurRate = rates.eur;
      }
      if (tonInp && rates.ton) tonInp.value = rates.ton;

      try {
        const payload = {};
        if (rates.usdt) payload.usdt_rate_toman = rates.usdt;
        if (rates.eur) payload.eur_rate_toman = rates.eur;
        if (rates.ton) payload.ton_rate_toman = rates.ton;
        const res = await window.api.saveAdminSettings(payload);
        if (res && res.ok) {
          if (window.showToast) window.showToast('✅ تمامی نرخ‌ها با موفقیت در تنظیمات ذخیره شدند');
          this.closeCryptoRatesModal();
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
      const modal = document.getElementById('bulkUsersModal');
      if (modal) modal.classList.remove('hidden');
      this.setBulkActionType('add_traffic');
      const valInput = document.getElementById('bulkAmountInput');
      if (valInput) valInput.value = '5';
      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    closeBulkUsersModal() {
      const modal = document.getElementById('bulkUsersModal');
      if (modal) modal.classList.add('hidden');
    },

    setBulkActionType(type = 'add_traffic') {
      this.currentBulkActionType = type;
      const trafficBtn = document.getElementById('bulkTypeBtn_traffic');
      const daysBtn = document.getElementById('bulkTypeBtn_days');
      const labelEl = document.getElementById('bulkAmountLabel');
      const inputEl = document.getElementById('bulkAmountInput');

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
      const amount = parseInt(document.getElementById('bulkAmountInput')?.value, 10);
      if (!amount || amount <= 0) {
        if (window.showToast) window.showToast('⚠️ لطفاً مقدار معتبری وارد کنید.');
        return;
      }

      const audience = document.getElementById('bulkTargetSelect')?.value || 'all_active';
      const typeText = this.currentBulkActionType === 'add_traffic' ? `${amount} گیگابایت حجم` : `${amount} روز اعتبار`;
      const audText = audience === 'all_active' ? 'تمام کاربران فعال' : 'تمام کاربران پنل';

      if (!confirm(`آیا از اعمال گروهی (${typeText}) برای ${audText} اطمینان دارید؟`)) {
        return;
      }

      const btn = document.getElementById('bulkSubmitBtn');
      const txt = document.getElementById('bulkSubmitText');
      const spin = document.getElementById('bulkSubmitSpinner');

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
      const modal = document.getElementById('nodeBillingModal');
      if (!modal) return;
      document.getElementById('nodeBillingUuid').value = nodeUuid || '';
      document.getElementById('nodeBillingName').value = nodeName || '';
      document.getElementById('nodeBillingModalTitle').innerText = nodeName ? `هزینه و تمدید: ${nodeName}` : 'هزینه و تمدید سرور';
      document.getElementById('nodeBillingModalFlag').innerText = flag || '🖥️';
      document.getElementById('nodeBillingProvider').value = provider || '';
      document.getElementById('nodeBillingCostToman').value = costToman || '';
      document.getElementById('nodeBillingCostEur').value = costEur || '';
      document.getElementById('nodeBillingDueDate').value = dueDate ? dueDate.slice(0, 10) : '';
      document.getElementById('nodeBillingNotes').value = notes || '';

      const jalaliPreview = document.getElementById('nodeBillingJalaliPreview');
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
      const hiddenInput = document.getElementById('nodeBillingCurrency');
      if (hiddenInput) hiddenInput.value = isEur ? 'EUR' : 'USD';

      const eurBtn = document.getElementById('nodeBillingCurrEur');
      const usdBtn = document.getElementById('nodeBillingCurrUsd');
      const symbolSpan = document.getElementById('nodeBillingCurrencySymbol');

      if (eurBtn && usdBtn) {
        if (isEur) {
          eurBtn.className = 'px-2 py-0.5 rounded font-bold transition text-cyan-400 bg-slate-700 shadow-sm';
          usdBtn.className = 'px-2 py-0.5 rounded font-bold transition text-slate-400 hover:text-white';
        } else {
          usdBtn.className = 'px-2 py-0.5 rounded font-bold transition text-emerald-400 bg-slate-700 shadow-sm';
          eurBtn.className = 'px-2 py-0.5 rounded font-bold transition text-slate-400 hover:text-white';
        }
      }
      if (symbolSpan) {
        symbolSpan.innerText = isEur ? '€' : '$';
      }

      if (recalculate) {
        this.updateNodeBillingConversion(true);
      }
    },

    updateNodeBillingConversion(forceRecalcToman = false) {
      const curr = (document.getElementById('nodeBillingCurrency')?.value || 'EUR').toUpperCase();
      const valInput = document.getElementById('nodeBillingCostEur');
      const tomanInput = document.getElementById('nodeBillingCostToman');
      const hint = document.getElementById('nodeBillingEurConvertHint');
      const text = document.getElementById('nodeBillingEurConvertText');
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
        text.innerText = `محاسبه خودکار: ${symbol}${numVal} × ${formatNumber(rate)} = ${formatNumber(currentTomanVal || convertedToman)} تومان`;
        hint.classList.remove('hidden');
      } else {
        hint.classList.add('hidden');
      }
    },

    closeNodeBillingModal() {
      const modal = document.getElementById('nodeBillingModal');
      if (modal) modal.classList.add('hidden');
    },

    async saveNodeBilling() {
      const node_uuid = document.getElementById('nodeBillingUuid')?.value?.trim();
      const node_name = document.getElementById('nodeBillingName')?.value?.trim();
      const provider = document.getElementById('nodeBillingProvider')?.value?.trim();
      const monthly_cost_toman = parseInt(document.getElementById('nodeBillingCostToman')?.value || '0', 10);
      const monthly_cost_eur = parseFloat(document.getElementById('nodeBillingCostEur')?.value || '0');
      const currency = (document.getElementById('nodeBillingCurrency')?.value || 'EUR').toUpperCase();
      const due_date = document.getElementById('nodeBillingDueDate')?.value?.trim() || null;
      const notes = document.getElementById('nodeBillingNotes')?.value?.trim();

      if (!node_uuid) {
        if (window.showToast) window.showToast('شناسه سرور یافت نشد.');
        return;
      }

      const saveBtn = document.getElementById('saveNodeBillingBtn');
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
  };

  const fetchAdminPlans = () => window.adminActions.fetchAdminPlans();
  const fetchAdminCoupons = () => window.adminActions.fetchAdminCoupons();

  document.getElementById('openCreatePlanBtn')?.addEventListener('click', () => {
    window.adminActions.openPlanModal();
  });
  document.getElementById('openCreateCouponBtn')?.addEventListener('click', () => {
    window.adminActions.openCouponModal();
  });

  let walletActionType = 'add';
  const walletActionAddBtn = document.getElementById('walletActionAddBtn');
  const walletActionDeductBtn = document.getElementById('walletActionDeductBtn');

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
    const container = document.getElementById('adminPendingTopupsList');
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
        const safeDisplayName = (uLabel || '').replace(/'/g, "\\'");
        const initial = (uLabel[0] || 'U').toUpperCase();
        const dateStr = t.created_at ? new Date(t.created_at).toLocaleDateString('fa-IR', { numberingSystem: 'latn', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }) : '—';
        const avatarSrc = t.avatar_url || `/api/user/avatar?user_id=${t.telegram_id}`;
        const hasPhoto = Boolean(t.has_photo || t.receipt_photo_id || (t.receipt_hash && (t.receipt_hash.startsWith('img:') || t.receipt_hash.startsWith('photo:'))));
        const photoUrl = hasPhoto ? `/api/admin/topup/photo?id=${t.id}` : null;
        const usernameTag = t.username ? `@${t.username}` : '';
        const userTagArg = (usernameTag || ('#' + t.telegram_id)).replace(/'/g, "\\'");

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
                  <span class="font-bold">${initial}</span>
                </div>
                <div class="min-w-0 space-y-0.5">
                  <b class="text-white text-xs font-bold block truncate max-w-[140px] cursor-pointer hover:text-cyan-300" onclick="window.adminActions.quickCopy('${safeDisplayName}', 'نام')" title="${escapeHtml(uLabel)}">${escapeHtml(uLabel)}</b>
                  <div class="flex items-baseline gap-1 text-emerald-400 font-bold" dir="rtl">
                    <span class="text-sm font-black font-mono leading-none">${formatNumber(t.amount || 0)}</span>
                    <span class="text-[10px] text-emerald-500/90 font-sans">تومان</span>
                  </div>
                </div>
              </div>

              <!-- Left column: Username on line 1, Numeric ID on line 2 (بدون ID: و کاملاً چسبیده به چپ بدون فاصله) -->
              <div class="flex flex-col items-start justify-center gap-0.5 font-mono text-[11px] text-slate-400 flex-shrink-0 text-left" dir="ltr">
                ${t.username ? `<span onclick="window.adminActions.quickCopy('@${t.username}', 'نام کاربری')" class="cursor-pointer hover:text-cyan-300 text-slate-300 font-mono truncate max-w-[130px] block leading-tight" title="@${t.username}">@${t.username}</span>` : ''}
                <span class="cursor-pointer hover:text-cyan-300 text-slate-400 font-mono block leading-tight" onclick="window.adminActions.quickCopy('${t.telegram_id}', 'شناسه عددی')" title="شناسه عددی">${t.telegram_id}</span>
              </div>
            </div>

            <!-- Action Buttons: Chat on right, Photo icon & Action buttons on left (همه بدون پس‌زمینه) -->
            <div class="flex items-center justify-between gap-2 pt-1 border-t border-slate-700/50">
              <button onclick="window.adminActions.openUserChat(${t.telegram_id}, '${safeDisplayName}', '${userTagArg}', ${t.id})" class="bg-transparent hover:bg-slate-750/30 text-slate-300 hover:text-white px-3 py-1.5 rounded-xl text-xs font-medium transition flex items-center gap-1.5 active:scale-95 border border-slate-700/60" title="گفتگوی مستقیم با کاربر">
                <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
                <span>چت با کاربر</span>
              </button>

              <div class="flex items-center gap-1.5">
                ${hasPhoto ? `
                  <button type="button" onclick="window.adminActions.openReceiptImageModal('${photoUrl}', ${t.id})" class="w-8 h-8 rounded-xl bg-transparent hover:bg-cyan-500/10 text-cyan-400 border border-cyan-500/40 flex items-center justify-center transition active:scale-95 shadow-sm" title="مشاهده تصویر فیش">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                  </button>
                ` : `
                  <button type="button" onclick="window.adminActions.showReceiptInfoModal(${t.id}, '${(t.receipt_hash || '').replace(/'/g, "\\'")}', '${formatNumber(t.amount || 0)}')" class="w-8 h-8 rounded-xl bg-transparent hover:bg-cyan-500/10 text-cyan-400 border border-cyan-500/40 flex items-center justify-center transition active:scale-95 shadow-sm" title="مشاهده مشخصات رسید / کد پیگیری">
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
    const streamEl = document.getElementById('ticketChatStream');
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
      const nameEl = document.getElementById('activeChatUserName');
      if (nameEl) nameEl.innerText = user.full_name || `کاربر ${telegram_id}`;
      const tagEl = document.getElementById('activeChatUserTag');
      if (tagEl) {
        tagEl.innerText = user.username ? `@${user.username}` : '';
        tagEl.style.display = user.username ? 'block' : 'none';
      }
      const idEl = document.getElementById('activeChatUserId');
      if (idEl) idEl.innerHTML = `<span onclick="window.adminActions.quickCopy('${telegram_id}', 'شناسه عددی')" class="cursor-pointer hover:text-cyan-300 transition">${telegram_id}</span>`;
      const avatarEl = document.getElementById('activeChatUserAvatar');
      if (avatarEl) {
        const initial = ((user.full_name || user.username || String(telegram_id)).replace('@', '')[0] || 'U').toUpperCase();
        avatarEl.innerHTML = `<img src="/api/user/avatar?user_id=${telegram_id}" alt="Avatar" class="w-full h-full object-cover" onerror="this.classList.add('hidden'); if(this.nextElementSibling) this.nextElementSibling.classList.remove('hidden');" /><span class="font-bold">${initial}</span>`;
      }

      const badgeEl = document.getElementById('activeChatStatusBadge');
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
  document.getElementById('sendDirectTicketReplyBtn')?.addEventListener('click', async () => {
    const uid = document.getElementById('directTicketUserId')?.value?.trim() || activeChatTelegramId;
    const txtEl = document.getElementById('directTicketMsg');
    const txt = txtEl?.value?.trim();
    if (!uid) {
      if (window.showToast) window.showToast('لطفاً ابتدا یک کاربر را از لیست بالا انتخاب کنید.');
      return;
    }
    if (!txt) {
      if (window.showToast) window.showToast('لطفاً متن پیام را وارد کنید.');
      return;
    }
    const sendBtn = document.getElementById('sendDirectTicketReplyBtn');
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
      const input = document.getElementById('directTicketMsg');
      if (input && msg) {
        input.value = msg;
        input.focus();
      }
      if (window.hapticFeedback) window.hapticFeedback('impact');
    });
  });

  document.getElementById('refreshChatThreadsBtn')?.addEventListener('click', () => {
    fetchTicketThreads();
    if (activeChatTelegramId) loadUserChatMessages(activeChatTelegramId);
    if (window.showToast) window.showToast('🔄 گفتگوها به‌روزرسانی شد');
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  document.getElementById('directTicketMsg')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      document.getElementById('sendDirectTicketReplyBtn')?.click();
    }
  });

  // --- 8. System Settings ---
  async function fetchAdminSettings() {
    try {
      const res = await window.api.getAdminSettings();
      if (!res || !res.ok || !res.settings) return;
      const s = res.settings;

      // Switches
      const maintSwitch = document.getElementById('settingMaintSwitch');
      if (maintSwitch) maintSwitch.checked = !!s.maintenance;

      const cardSwitch = document.getElementById('settingCardSwitch');
      if (cardSwitch) cardSwitch.checked = !!s.card_enabled;

      const cryptoSwitch = document.getElementById('settingCryptoSwitch');
      if (cryptoSwitch) cryptoSwitch.checked = !!s.crypto_enabled;

      const trialSwitch = document.getElementById('settingTrialSwitch');
      if (trialSwitch) trialSwitch.checked = !!s.trial_enabled;

      const refSwitch = document.getElementById('settingRefSwitch');
      if (refSwitch) refSwitch.checked = !!s.referral_enabled;

      const supDirectSwitch = document.getElementById('settingSupportDirectSwitch');
      if (supDirectSwitch) supDirectSwitch.checked = !!s.support_direct_enabled;

      // Bank & Topup
      const cardNum = document.getElementById('settingCardNumber');
      if (cardNum) cardNum.value = s.card_number || '';

      const cardHolder = document.getElementById('settingCardHolder');
      if (cardHolder) cardHolder.value = s.card_holder || '';

      const minTopup = document.getElementById('settingMinTopup');
      if (minTopup) minTopup.value = s.topup_min_amount ?? 20000;

      // Crypto & Rates
      const usdtRate = document.getElementById('settingUsdtRate');
      if (usdtRate) usdtRate.value = s.usdt_rate_toman ?? 95000;
      if (s.usdt_rate_toman) window.currentUsdRate = s.usdt_rate_toman;

      const eurRate = document.getElementById('settingEurRate');
      if (eurRate) eurRate.value = s.eur_rate_toman ?? 105000;
      if (s.eur_rate_toman) window.currentEurRate = s.eur_rate_toman;

      const tonRate = document.getElementById('settingTonRate');
      if (tonRate) tonRate.value = s.ton_rate_toman ?? 0;

      const tonWallet = document.getElementById('settingTonWallet');
      if (tonWallet) tonWallet.value = s.ton_wallet_address || '';

      // Trial & Referral
      const trialTraffic = document.getElementById('settingTrialTraffic');
      if (trialTraffic) trialTraffic.value = s.trial_traffic_gb ?? 1;

      const trialDays = document.getElementById('settingTrialDays');
      if (trialDays) trialDays.value = s.trial_duration_days ?? 1;

      const refReward = document.getElementById('settingRefReward');
      if (refReward) refReward.value = s.referral_reward_gb ?? 5;

      const supContact = document.getElementById('settingSupportContact');
      if (supContact) supContact.value = s.support_contact || '';

      // Telegram Supergroup Forum Topics
      const topicTopups = document.getElementById('settingTopicTopups');
      if (topicTopups) topicTopups.value = s.topic_topups ?? '';

      const topicOrders = document.getElementById('settingTopicOrders');
      if (topicOrders) topicOrders.value = s.topic_orders ?? '';

      const topicSupport = document.getElementById('settingTopicSupport');
      if (topicSupport) topicSupport.value = s.topic_support ?? '';

      const topicAlerts = document.getElementById('settingTopicAlerts');
      if (topicAlerts) topicAlerts.value = s.topic_alerts ?? '';

      const topicCrypto = document.getElementById('settingTopicCrypto');
      if (topicCrypto) topicCrypto.value = s.topic_crypto ?? '';

      const topicErrors = document.getElementById('settingTopicErrors');
      if (topicErrors) topicErrors.value = s.topic_errors ?? '';
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

  document.getElementById('settingMaintSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('maintenance', e.target.checked);
  });
  document.getElementById('settingCardSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('card_enabled', e.target.checked);
  });
  document.getElementById('settingCryptoSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('crypto_enabled', e.target.checked);
  });
  document.getElementById('settingTrialSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('trial_enabled', e.target.checked);
  });
  document.getElementById('settingRefSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('referral_enabled', e.target.checked);
  });
  document.getElementById('settingSupportDirectSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('support_direct_enabled', e.target.checked);
  });

  async function handleSaveAllSettings() {
    const payload = {
      maintenance: document.getElementById('settingMaintSwitch')?.checked ?? false,
      card_enabled: document.getElementById('settingCardSwitch')?.checked ?? true,
      crypto_enabled: document.getElementById('settingCryptoSwitch')?.checked ?? false,
      trial_enabled: document.getElementById('settingTrialSwitch')?.checked ?? true,
      referral_enabled: document.getElementById('settingRefSwitch')?.checked ?? true,
      support_direct_enabled: document.getElementById('settingSupportDirectSwitch')?.checked ?? true,
      card_number: document.getElementById('settingCardNumber')?.value?.trim() || '',
      card_holder: document.getElementById('settingCardHolder')?.value?.trim() || '',
      topup_min_amount: parseInt(document.getElementById('settingMinTopup')?.value || '20000', 10),
      usdt_rate_toman: parseInt(document.getElementById('settingUsdtRate')?.value || '95000', 10),
      eur_rate_toman: parseInt(document.getElementById('settingEurRate')?.value || '105000', 10),
      ton_rate_toman: parseInt(document.getElementById('settingTonRate')?.value || '0', 10),
      ton_wallet_address: document.getElementById('settingTonWallet')?.value?.trim() || '',
      trial_traffic_gb: parseInt(document.getElementById('settingTrialTraffic')?.value || '1', 10),
      trial_duration_days: parseInt(document.getElementById('settingTrialDays')?.value || '1', 10),
      referral_reward_gb: parseInt(document.getElementById('settingRefReward')?.value || '5', 10),
      support_contact: document.getElementById('settingSupportContact')?.value?.trim() || '',
      topic_topups: document.getElementById('settingTopicTopups')?.value?.trim() ? parseInt(document.getElementById('settingTopicTopups').value, 10) : null,
      topic_orders: document.getElementById('settingTopicOrders')?.value?.trim() ? parseInt(document.getElementById('settingTopicOrders').value, 10) : null,
      topic_support: document.getElementById('settingTopicSupport')?.value?.trim() ? parseInt(document.getElementById('settingTopicSupport').value, 10) : null,
      topic_alerts: document.getElementById('settingTopicAlerts')?.value?.trim() ? parseInt(document.getElementById('settingTopicAlerts').value, 10) : null,
      topic_crypto: document.getElementById('settingTopicCrypto')?.value?.trim() ? parseInt(document.getElementById('settingTopicCrypto').value, 10) : null,
      topic_errors: document.getElementById('settingTopicErrors')?.value?.trim() ? parseInt(document.getElementById('settingTopicErrors').value, 10) : null,
    };

    const saveBtns = [document.getElementById('saveAllSettingsBtn'), document.getElementById('saveAllSettingsTopBtn')];
    saveBtns.forEach(b => { if (b) { b.disabled = true; b.innerText = 'در حال ذخیره...'; } });

    try {
      const res = await window.api.saveAdminSettings(payload);
      if (res && res.ok) {
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
      const mainBtn = document.getElementById('saveAllSettingsBtn');
      if (mainBtn) mainBtn.innerHTML = '<span>💾</span> ذخیره تمامی تغییرات تنظیمات';
    }
  }

  document.getElementById('saveAllSettingsBtn')?.addEventListener('click', handleSaveAllSettings);
  document.getElementById('saveAllSettingsTopBtn')?.addEventListener('click', handleSaveAllSettings);

  // Settings Accordion Boxes toggle handled by window.adminActions.toggleSettingsBox

  // Crypto rates modal trigger in settings
  document.getElementById('openCryptoRatesModalBtn')?.addEventListener('click', () => {
    window.adminActions.openCryptoRatesModal();
  });

  // --- 9. Broadcast Modal & Live Report Modal ---
  const broadcastModal = document.getElementById('broadcastModal');
  const broadcastReportModal = document.getElementById('broadcastReportModal');
  const openBroadcastModalBtn = document.getElementById('openBroadcastModalBtn');
  const closeBroadcastBtn = document.getElementById('closeBroadcastBtn');
  const sendBroadcastBtn = document.getElementById('sendBroadcastBtn');
  const closeBroadcastReportBtn = document.getElementById('closeBroadcastReportBtn');
  const dismissReportModalBtn = document.getElementById('dismissReportModalBtn');

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
      const targetLabel = document.getElementById('broadcastTargetLabel');
      if (targetLabel) targetLabel.innerText = labelMap[currentBroadcastTarget] || 'کاربران';

      if (window.hapticFeedback) window.hapticFeedback('impact');
    });
  });

  sendBroadcastBtn?.addEventListener('click', async () => {
    const txt = document.getElementById('broadcastTextArea')?.value?.trim();
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
        const txtEl = document.getElementById('broadcastTextArea');
        if (txtEl) txtEl.value = '';

        // Open Live Progress Report Modal
        if (broadcastReportModal) {
          broadcastReportModal.classList.remove('hidden');
          const targetEl = document.getElementById('reportTargetLabel');
          if (targetEl) targetEl.innerText = res.stats?.target_label || 'همه کاربران';
          const totalEl = document.getElementById('reportTotalCount');
          if (totalEl) totalEl.innerText = `${formatNumber(res.stats?.total || 0)} نفر`;
          const sentEl = document.getElementById('reportSentCount');
          if (sentEl) sentEl.innerText = '0 پیام';
          const failEl = document.getElementById('reportFailedCount');
          if (failEl) failEl.innerText = '0';
          const statusEl = document.getElementById('reportStatusText');
          if (statusEl) statusEl.innerText = 'در حال ارسال پیام‌ها...';
          const pBar = document.getElementById('reportProgressBar');
          if (pBar) pBar.style.width = '10%';
          const pText = document.getElementById('reportPercentText');
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
  document.getElementById('adminReloadBtn')?.addEventListener('click', () => {
    syncAdminOverview(true);
    if (window.showToast) window.showToast('🔄 اطلاعات به‌روزرسانی شد.');
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  document.getElementById('quickRefreshMetricsBtn')?.addEventListener('click', () => {
    syncAdminOverview(true);
    if (window.showToast) window.showToast('🔄 داده‌ها سینک شدند.');
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  document.getElementById('syncAllNodesBtn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    syncAdminOverview(true);
    if (window.showToast) window.showToast('🔄 نودها همگام‌سازی شدند.');
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  const overviewNodesToggleHeader = document.getElementById('overviewNodesToggleHeader');
  const overviewNodesCollapseBody = document.getElementById('overviewNodesCollapseBody');
  const overviewNodesChevron = document.getElementById('overviewNodesChevron');

  overviewNodesToggleHeader?.addEventListener('click', (e) => {
    if (e.target.closest('#syncAllNodesBtn')) return;
    if (!overviewNodesCollapseBody) return;
    const isHidden = overviewNodesCollapseBody.classList.toggle('hidden');
    if (overviewNodesChevron) {
      overviewNodesChevron.style.transform = isHidden ? 'rotate(0deg)' : 'rotate(180deg)';
    }
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  document.getElementById('refreshNodesTabBtn')?.addEventListener('click', async () => {
    const icon = document.getElementById('refreshNodesTabIcon');
    if (icon) icon.classList.add('animate-spin');
    try {
      await syncAdminOverview(true);
      if (window.showToast) window.showToast('🔄 وضعیت سرورها و سرعت شبکه به‌روزرسانی شد');
      if (window.hapticFeedback) window.hapticFeedback('success');
    } finally {
      setTimeout(() => {
        if (icon) icon.classList.remove('animate-spin');
      }, 500);
    }
  });

  // Node Billing auto-convert EUR to Toman & Shamsi preview
  const nodeCostEurInput = document.getElementById('nodeBillingCostEur');
  const nodeCostTomanInput = document.getElementById('nodeBillingCostToman');
  const nodeEurHint = document.getElementById('nodeBillingEurConvertHint');
  const nodeEurHintText = document.getElementById('nodeBillingEurConvertText');
  const nodeDueDateInput = document.getElementById('nodeBillingDueDate');
  const nodeJalaliPreview = document.getElementById('nodeBillingJalaliPreview');

  nodeCostEurInput?.addEventListener('input', () => {
    window.adminActions?.updateNodeBillingConversion();
  });

  nodeDueDateInput?.addEventListener('input', (e) => {
    const d = e.target.value;
    if (nodeJalaliPreview) {
      nodeJalaliPreview.innerText = d ? (window.formatDateToJalali ? window.formatDateToJalali(d) : d) : '';
    }
  });

  document.getElementById('settingEurRate')?.addEventListener('input', (e) => {
    const val = parseInt(e.target.value, 10);
    if (!isNaN(val) && val > 0) {
      window.currentEurRate = val;
    }
  });

  document.getElementById('settingUsdtRate')?.addEventListener('input', (e) => {
    const val = parseInt(e.target.value, 10);
    if (!isNaN(val) && val > 0) {
      window.currentUsdRate = val;
    }
  });

  document.getElementById('refreshTopupsBtn')?.addEventListener('click', () => {
    fetchAdminTopups();
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  document.getElementById('viewPendingBtn')?.addEventListener('click', () => {
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

  // Initial Sync
  syncAdminOverview();
})();
