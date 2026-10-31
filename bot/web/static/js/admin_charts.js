/**
 * RemnaAdmin Pro - Charts & Telemetry Module (admin_charts.js)
 * High-performance analytics, chart renderers and cluster overview.
 */
(function (window) {
  'use strict';

  const $ = id => document.getElementById(id);
  const api = window.api;
  const tg = window.Telegram?.WebApp;
  const formatNumber = window.formatNumber || (n => String(n));
  const dismissSplash = window.dismissSplash || (() => {});
  window.adminActions = window.adminActions || {};

  let cachedOverviewData = null;

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

  const getThemeColors = () => {
    if (typeof getChartThemeTokens === 'function') {
      const tokens = getChartThemeTokens(!isDark);
      return {
        ...tokens,
        legendText: tokens.legend,
      };
    }
    return {
      success: isDark ? '#34d399' : '#047857',
      accent: isDark ? '#22d3ee' : '#0891b2',
      warn: isDark ? '#fbbf24' : '#b45309',
      grid: isDark ? 'rgba(51, 65, 85, 0.3)' : 'rgba(203, 213, 225, 0.7)',
      tick: isDark ? '#cbd5e1' : '#475569',
      legendText: isDark ? '#f8fafc' : '#0f172a',
      pointBorder: isDark ? '#0f172a' : '#ffffff',
    };
  };

  const updateChartsTheme = () => {
    const colors = getThemeColors();
    const { grid, tick, legendText, pointBorder, success, accent, warn } = colors;

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
        monthlySalesChartInstance.data.datasets[0].borderColor = success;
        monthlySalesChartInstance.data.datasets[0].pointBackgroundColor = success;
        monthlySalesChartInstance.data.datasets[0].pointBorderColor = pointBorder;
      }
      updateScaleChart(monthlySalesChartInstance);
    }
    if (trafficChartInstance) {
      if (trafficChartInstance.data?.datasets?.[0]) {
        trafficChartInstance.data.datasets[0].borderColor = accent;
        trafficChartInstance.data.datasets[0].pointBackgroundColor = accent;
        trafficChartInstance.data.datasets[0].pointBorderColor = pointBorder;
      }
      updateScaleChart(trafficChartInstance);
    }
    if (hourlyChartInstance) {
      if (hourlyChartInstance.data?.datasets?.[0]) {
        hourlyChartInstance.data.datasets[0].borderColor = warn;
        hourlyChartInstance.data.datasets[0].pointBackgroundColor = warn;
        hourlyChartInstance.data.datasets[0].pointBorderColor = pointBorder;
      }
      updateScaleChart(hourlyChartInstance);
    }
    updateScaleChart(retentionChartInstance);
    updateScaleChart(hwidChartInstance);
    updateScaleChart(topConsumersChartInstance);

    updateDoughnutChart(locationChartInstance);
    updateDoughnutChart(planSalesChartInstance);
    updateDoughnutChart(platformChartInstance);
    updateDoughnutChart(paymentChartInstance);
    updateDoughnutChart(churnChartInstance);
  };

  const applyThemeClasses = () => {
    if (isDark) {
      document.documentElement.classList.add('dark');
      document.documentElement.classList.remove('theme-light');
      if (adminThemeIcon) adminThemeIcon.innerHTML = `<svg class="w-3.5 h-3.5 t-warn" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" /></svg>`;
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('theme-light');
      if (adminThemeIcon) adminThemeIcon.innerHTML = `<svg class="w-3.5 h-3.5 t-muted" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z" /></svg>`;
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

      // Traffic: format via SSOT fmtTraffic (handles TB auto-conversion & BiDi isolation)
      const bw = $('adminMonthTraffic');
      if (bw) {
        bw.innerHTML = fmtTraffic(m.month_traffic_gb, { html: true });
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
          pMargin.className = 'text-[10px] font-mono font-bold bg-transparent text-slate-400 border border-slate-600/40 px-1.5 py-0.5 rounded-md';
        } else {
          const sign = marginVal > 0 ? '+' : (marginVal < 0 ? '-' : '');
          const absVal = Math.abs(marginVal);
          pMargin.innerHTML = `<span class="inline-flex items-center gap-0.5" dir="rtl"><span>مارجین:</span><span class="inline-flex items-center font-mono" dir="ltr"><span>${sign}</span><span>${absVal}</span><span>%</span></span></span>`;
          pMargin.className = marginVal >= 0
            ? 'text-[10px] font-mono font-bold bg-transparent text-emerald-400 border border-emerald-500/30 px-1.5 py-0.5 rounded-md'
            : 'text-[10px] font-mono font-bold bg-transparent text-rose-400 border border-rose-500/30 px-1.5 py-0.5 rounded-md';
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
      cachedOverviewData = data;
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
          if (c.top_consumers) renderAdminTopConsumersChart(c.top_consumers);
        }
      }

      // Render Accordion Nodes
      if (window.renderOverviewNodes) window.renderOverviewNodes(nodes);
      if (window.renderFullNodes) window.renderFullNodes(nodes);
      dismissSplash();
    } catch (err) {
      console.error('Failed to sync admin overview:', err);
      dismissSplash();
    }
  }

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
    if (totalEl) totalEl.innerHTML = `<span class="font-mono font-bold t-main">${formatNumber(totalSum)}</span> <span class="t-muted">تومان</span>`;

    const emptyOverlay = $('adminSalesEmptyOverlay');
    if (emptyOverlay) {
      if (totalSum === 0) emptyOverlay.classList.remove('hidden');
      else emptyOverlay.classList.add('hidden');
    }

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
              label: (ctx) => typeof fmtMoney === 'function' ? fmtMoney(ctx.raw) : `${formatNumber(ctx.raw)} تومان`
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
            suggestedMax: (values && values.some(v => v > 0)) ? undefined : 100000,
            grid: { color: isDark ? 'rgba(51, 65, 85, 0.3)' : 'rgba(203, 213, 225, 0.7)' },
            ticks: {
              color: isDark ? '#cbd5e1' : '#0f172a',
              font: { family: 'Vazirmatn', size: 9 },
              callback: (val) => typeof fmtCompact === 'function' ? fmtCompact(val) : (val >= 1000000 ? `${(val/1000000).toFixed(1)}M` : (val >= 1000 ? `${(val/1000).toFixed(0)}K` : val))
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
    if (totalEl) totalEl.innerHTML = `<span class="font-mono font-bold t-main">${formatNumber(total)}</span> <span class="t-muted">تومان</span>`;

    const emptyMonthlyOverlay = $('adminMonthlySalesEmptyOverlay');
    if (emptyMonthlyOverlay) {
      if (total === 0) emptyMonthlyOverlay.classList.remove('hidden');
      else emptyMonthlyOverlay.classList.add('hidden');
    }

    if (monthlySalesChartInstance) {
      monthlySalesChartInstance.data.labels = labels || [];
      monthlySalesChartInstance.data.datasets[0].data = values || [];
      monthlySalesChartInstance.update();
      return;
    }

    const gradient = ctx.createLinearGradient(0, 0, 0, 140);
    gradient.addColorStop(0, 'rgba(16, 185, 129, 0.40)');
    gradient.addColorStop(1, 'rgba(16, 185, 129, 0.0)');

    const tc = getThemeColors();
    monthlySalesChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels || [],
        datasets: [{
          label: 'فروش ۳۰ روزه (تومان)',
          data: values || [],
          borderColor: tc.success,
          borderWidth: 2,
          backgroundColor: gradient,
          fill: true,
          tension: 0.35,
          pointRadius: (ctx) => ((labels || []).length > 15 ? 1 : 2),
          pointHoverRadius: 5,
          pointBackgroundColor: tc.success,
          pointBorderColor: tc.pointBorder,
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
              label: (ctx) => typeof fmtMoney === 'function' ? fmtMoney(ctx.raw) : `${formatNumber(ctx.raw)} تومان`
            }
          }
        },
        scales: {
          x: {
            grid: { display: true, color: tc.grid },
            ticks: {
              color: tc.tick,
              font: { family: 'Vazirmatn', size: 9 },
              maxTicksLimit: 10,
            }
          },
          y: {
            beginAtZero: true,
            suggestedMax: (values && values.some(v => v > 0)) ? undefined : 100000,
            grid: { color: tc.grid },
            ticks: {
              color: tc.tick,
              font: { family: 'Vazirmatn', size: 9 },
              callback: (val) => typeof fmtCompact === 'function' ? fmtCompact(val) : (val >= 1000000 ? `${(val/1000000).toFixed(1)}M` : (val >= 1000 ? `${(val/1000).toFixed(0)}K` : val))
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
      totalEl.innerHTML = `<span class="t-main font-bold font-mono text-xs">${fmtTraffic(totalGb || currentToday || 0, { html: true })}</span>`;
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

    const tc = getThemeColors();
    trafficChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'مصرف ترافیک (GB)',
          data: values,
          borderColor: tc.accent,
          borderWidth: 2.5,
          backgroundColor: gradient,
          fill: true,
          tension: 0.35,
          pointBackgroundColor: tc.accent,
          pointBorderColor: tc.pointBorder,
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
              label: (ctx) => `مصرف: ${fmtTraffic(ctx.raw, { html: false, isolate: true })}`
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: tc.tick, font: { family: 'Vazirmatn', size: 9 } }
          },
          y: {
            beginAtZero: true,
            suggestedMax: (values && values.some(v => v > 0)) ? undefined : 10,
            grid: { color: tc.grid },
            ticks: {
              color: tc.tick,
              font: { family: 'Vazirmatn', size: 9 },
              callback: (val) => fmtTraffic(val, { html: false, isolate: true })
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
      ? (locationShare.labels || []).map(l => (l || '').trim() || '🌐')
      : ['بدون مصرف'];
    const values = hasData ? locationShare.data : [1];
    const unit = locationShare?.unit || 'GB';
    const bgColors = hasData ? getDonutPalette(!isDark) : ['rgba(100, 116, 139, 0.4)'];

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
              label: (ctx) => hasData ? `${ctx.label}: ${typeof fmtTraffic === 'function' ? fmtTraffic(ctx.raw, { html: false, isolate: true }) : `${formatNumber(ctx.raw)} ${unit}`}` : 'داده‌ای برای سرورها ثبت نشده است'
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

    const tc = getThemeColors();
    hourlyChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'مصرف ساعتی (GB)',
          data: values,
          borderColor: tc.warn,
          borderWidth: 2,
          backgroundColor: gradient,
          fill: true,
          tension: 0.38,
          pointRadius: 1.5,
          pointHoverRadius: 4.5,
          pointBackgroundColor: tc.warn,
          pointBorderColor: tc.pointBorder,
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
            backgroundColor: isDark ? '#0f172a' : '#ffffff',
            titleColor: isDark ? '#ffffff' : '#0f172a',
            bodyColor: isDark ? tc.warn : '#b45309',
            borderColor: isDark ? '#334155' : '#e2e8f0',
            borderWidth: 1,
            callbacks: {
              label: (ctx) => `ساعت ${ctx.label}: ${fmtTraffic(ctx.raw, { html: false, isolate: true })}`
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: tc.tick,
              font: { family: 'Vazirmatn', size: 10 },
              maxTicksLimit: 12,
            }
          },
          y: {
            beginAtZero: true,
            suggestedMax: (values && values.some(v => v > 0)) ? undefined : 1,
            grid: { color: tc.grid },
            ticks: {
              color: tc.tick,
              font: { family: 'Vazirmatn', size: 10 },
              callback: (val) => fmtTraffic(val, { html: false, isolate: true })
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
    const totalRetentionUsers = [...(newSales || []), ...(renewalSales || [])].reduce((a, b) => a + b, 0);

    const emptyOverlay = $('adminRetentionEmptyOverlay');
    if (emptyOverlay) {
      if (totalRetentionUsers === 0) emptyOverlay.classList.remove('hidden');
      else emptyOverlay.classList.add('hidden');
    }

    if (retentionChartInstance) {
      retentionChartInstance.data.labels = labels;
      retentionChartInstance.data.datasets[0].data = newSales;
      retentionChartInstance.data.datasets[1].data = renewalSales;
      retentionChartInstance.options.scales.y.suggestedMax = (totalRetentionUsers > 0) ? undefined : 5;
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
            suggestedMax: (totalRetentionUsers > 0) ? undefined : 5,
            suggestedMax: (newSales.some(v => v > 0) || renewalSales.some(v => v > 0)) ? undefined : 5,
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

  let planSalesChartInstance = null;
  function renderAdminPlanSalesChart(planDist) {
    const canvas = $('adminPlanSalesChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const hasSales = Boolean(planDist?.has_data ?? (planDist?.sales_count && planDist.sales_count.some(c => c > 0)));
    const labels = hasSales
      ? (planDist.labels || []).map(l => formatPlanTitle(l, { plainText: true }))
      : ['بدون سفارش ثبت‌شده'];
    const values = hasSales ? planDist.sales_count : [1];
    const bgColors = hasSales ? getDonutPalette(!isDark) : ['rgba(100, 116, 139, 0.4)'];

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

    window.currentHighRiskUsers = hwidDist?.high_risk_users || [];
    const badge = $('hwidRiskBadge');
    if (badge) {
      badge.innerText = riskCount > 0 ? `⚠️ ${riskCount} کاربر پرخطر` : 'توزیع HWID';
      badge.className = riskCount > 0
        ? 'text-[10px] text-rose-700 dark:text-rose-400 font-bold font-mono animate-pulse cursor-pointer hover:underline'
        : 'text-[10px] text-slate-700 dark:text-slate-300 font-bold font-mono cursor-pointer hover:underline';
      badge.onclick = () => window.adminActions.openHighRiskUsersModal();
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


  // High Risk Users Modal Actions
  Object.assign(window.adminActions, {
openHighRiskUsersModal() {
      const modal = $('highRiskUsersModal');
      const list = $('highRiskUsersModalList');
      if (!modal || !list) return;

      const users = window.currentHighRiskUsers || [];
      if (users.length === 0) {
        list.innerHTML = `
          <div class="text-center py-8 text-slate-400 space-y-2">
            <span class="text-3xl">🛡️</span>
            <div class="text-xs font-bold text-slate-200">هیچ کاربر پرخطری یافت نشد</div>
            <div class="text-[11px] text-slate-400">تمام کاربران دارای ۳ دستگاه متصل یا کمتر هستند.</div>
          </div>
        `;
      } else {
        list.innerHTML = users.map((u, idx) => {
          const accountName = escapeHtml(u.name || u.username || `اکانت #${u.user_id}`);
          const tgId = u.telegram_id || u.user_id;
          const tgInfo = tgId ? `شناسه: ${tgId}` : '';
          const devCount = u.device_count || 3;
          const pUserId = u.user_id ? String(u.user_id) : '';
          return `
            <div class="p-3 card-inset border border-slate-700/50 rounded-2xl flex items-center justify-between gap-2.5 transition">
              <div class="flex items-center gap-2.5 min-w-0 flex-1">
                <span class="w-6 text-center font-mono font-bold text-xs text-rose-600 dark:text-rose-400 shrink-0">
                  ${idx + 1}.
                </span>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <span class="font-bold t-main text-xs truncate font-mono" dir="ltr">${accountName}</span>
                    <span class="text-[10px] font-mono text-rose-600 dark:text-rose-400 font-bold shrink-0">
                      🔥 ${devCount} دستگاه
                    </span>
                  </div>
                  ${tgInfo ? `<span class="text-[10px] t-muted block truncate mt-0.5" dir="rtl">${escapeHtml(tgInfo)}</span>` : ''}
                </div>
              </div>
              <div class="flex items-center gap-1.5 shrink-0">
                <button type="button" onclick="window.adminActions.inspectHighRiskUser('${tgId}', '${accountName.replace(/'/g, "\\'")}', '${pUserId}')" class="px-2.5 py-1.5 rounded-xl bg-transparent hover:bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/40 text-[11px] font-bold transition active:scale-95 flex items-center gap-1">
                  <span>🔍</span><span>بررسی</span>
                </button>
              </div>
            </div>
          `;
        }).join('');
      }

      modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    closeHighRiskUsersModal() {
      $('highRiskUsersModal')?.classList.add('hidden');
    },

    inspectHighRiskUser(telegramId, name, panelUserId = null) {
      this.closeHighRiskUsersModal();
      if (this.openHwidModal) {
        this.openHwidModal(telegramId, name || telegramId, 'hwid', panelUserId);
      } else if (this.openModifyModal) {
        this.openModifyModal(telegramId);
      }
    }
  });

  // Top Consumers & Daily Champion Chart
  let topConsumersChartInstance = null;
  function renderAdminTopConsumersChart(topData) {
    const canvas = $('adminTopConsumersChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const labels = topData?.labels || [];
    const values = topData?.data || [];
    const champIdx = Number(topData?.champion_day_index ?? -1);
    const champLabel = topData?.champion_day_label || '—';
    const champTraffic = topData?.champion_day_traffic || 0;
    const topUsers = topData?.top_users || [];

    // Update champion badge
    const badgeLabel = $('championDayLabel');
    if (badgeLabel) {
      const champTrafStr = typeof fmtTraffic === 'function' ? fmtTraffic(champTraffic, { html: false }) : champTraffic;
      badgeLabel.innerText = `قهرمان هفته: ${champLabel} (${champTrafStr})`;
    }

    // Render leaderboard
    const usersListEl = $('adminTopUsersList');
    if (usersListEl) {
      if (topUsers.length === 0) {
        usersListEl.innerHTML = '<div class="text-slate-400 text-[11px] text-center py-4">داده‌ای ثبت نشده است</div>';
      } else {
        const medals = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣'];
        usersListEl.innerHTML = topUsers.map((u, i) => {
          const medal = medals[i] || '👤';
          const isChamp = u.is_champion;
          const bgCls = isChamp ? 'bg-amber-500/10 border border-amber-500/30' : 'bg-slate-700/30 border border-slate-700/40';
          const txtCls = isChamp ? 'text-amber-300 font-bold' : 't-main';
          const crown = isChamp ? '<span class="text-xs">👑</span>' : '';
          const userTrafStr = typeof fmtTraffic === 'function' ? fmtTraffic(u.used_gb, { html: false }) : u.used_gb;
          return `
            <div class="flex items-center justify-between p-1.5 rounded-lg ${bgCls}">
              <div class="flex items-center gap-1.5 min-w-0">
                <span class="text-xs">${medal}</span>
                <span class="font-mono text-xs ${txtCls} truncate max-w-[110px]" dir="ltr">@${u.username}</span>
                ${crown}
              </div>
              <span class="font-mono text-xs text-cyan-400 font-bold" dir="ltr">${userTrafStr}</span>
            </div>
          `;
        }).join('');
      }
    }

    // Generate colors: Highlight champion day with gold amber gradient
    const bgColors = values.map((_, i) => i === champIdx ? 'rgba(245, 158, 11, 0.85)' : 'rgba(99, 102, 241, 0.55)');
    const borderColors = values.map((_, i) => i === champIdx ? '#fbbf24' : '#818cf8');
    const borderWidths = values.map((_, i) => i === champIdx ? 2 : 1);

    if (topConsumersChartInstance) {
      topConsumersChartInstance.data.labels = labels;
      topConsumersChartInstance.data.datasets[0].data = values;
      topConsumersChartInstance.data.datasets[0].backgroundColor = bgColors;
      topConsumersChartInstance.data.datasets[0].borderColor = borderColors;
      topConsumersChartInstance.data.datasets[0].borderWidth = borderWidths;
      topConsumersChartInstance.update();
      return;
    }

    const { grid: gridColor, tick: tickColor } = getThemeColors();

    topConsumersChartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'مصرف ترافیک (GB)',
          data: values,
          backgroundColor: bgColors,
          borderColor: borderColors,
          borderWidth: borderWidths,
          borderRadius: 6,
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
                const isC = c.dataIndex === champIdx;
                const trafVal = typeof fmtTraffic === 'function' ? fmtTraffic(c.raw, { html: false, isolate: true }) : c.raw;
                return `${isC ? '👑 قهرمان مصرف: ' : 'مصرف: '}${trafVal}`;
              },
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: tickColor, font: { family: 'Vazirmatn', size: 10 } },
          },
          y: {
            grid: { color: gridColor },
            ticks: {
              color: tickColor,
              font: { family: 'Vazirmatn', size: 10 },
              callback: (v) => typeof fmtTraffic === 'function' ? fmtTraffic(v, { html: false, isolate: true }) : v,
            },
            beginAtZero: true,
          },
        },
      },
    });
  }

  // Global exports
  window.syncAdminOverview = syncAdminOverview;
  window.updateChartsTheme = updateChartsTheme;
  window.applyThemeClasses = applyThemeClasses;
  window.adminCharts = {
    resizeAll() {
      salesChartInstance?.resize();
      monthlySalesChartInstance?.resize();
      trafficChartInstance?.resize();
      locationChartInstance?.resize();
      hourlyChartInstance?.resize();
      retentionChartInstance?.resize();
      planSalesChartInstance?.resize();
      platformChartInstance?.resize();
      paymentChartInstance?.resize();
      churnChartInstance?.resize();
      hwidChartInstance?.resize();
      topConsumersChartInstance?.resize();
    }
  };
})(window);
