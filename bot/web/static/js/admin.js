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
    if (num === null || num === undefined) return '۰';
    const str = String(num);
    const [intPart, decPart] = str.split('.');
    const formattedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    const full = decPart !== undefined ? `${formattedInt}.${decPart}` : formattedInt;
    return full.replace(/\d/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);
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

      // Lazy load tab data
      if (targetId === 'tab-admin-users' && document.getElementById('adminUsersList')?.children.length <= 1) {
        fetchAdminUsers(1);
      } else if (targetId === 'tab-admin-plans') {
        fetchAdminPlans();
      } else if (targetId === 'tab-admin-coupons') {
        fetchAdminCoupons();
      } else if (targetId === 'tab-admin-tickets') {
        fetchAdminTopups();
      } else if (targetId === 'tab-admin-settings') {
        fetchAdminSettings();
      }
    });
  });

  // --- 3. Theme Toggle ---
  const adminThemeToggle = document.getElementById('adminThemeToggle');
  const adminThemeIcon = document.getElementById('adminThemeIcon');
  let isDark = true;
  adminThemeToggle?.addEventListener('click', () => {
    isDark = !isDark;
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
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  // --- 4. Overview & Cluster Metrics ---
  async function syncAdminOverview() {
    try {
      const res = await window.api.getAdminOverview();
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

      // Render 7-day Sales & Traffic Charts
      if (data.charts && typeof Chart !== 'undefined') {
        renderAdminSalesChart(data.charts.sales_labels, data.charts.sales_data);
        renderAdminTrafficChart(data.charts.traffic_labels, data.charts.traffic_data, data.charts.traffic_total_gb);
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

  let salesChartInstance = null;
  function renderAdminSalesChart(labels, values) {
    const canvas = document.getElementById('adminSalesChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const totalSum = (values || []).reduce((a, b) => a + b, 0);
    const totalEl = document.getElementById('salesChartTotal');
    if (totalEl) totalEl.innerText = `${formatNumber(totalSum)} تومان`;

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
            callbacks: {
              label: (ctx) => `${formatNumber(ctx.raw)} تومان`
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: '#94a3b8', font: { family: 'Vazirmatn', size: 9 } }
          },
          y: {
            grid: { color: 'rgba(51, 65, 85, 0.3)' },
            ticks: {
              color: '#94a3b8',
              font: { family: 'Vazirmatn', size: 9 },
              callback: (val) => val >= 1000000 ? `${(val/1000000).toFixed(1)}M` : (val >= 1000 ? `${(val/1000).toFixed(0)}K` : val)
            }
          }
        }
      }
    });
  }

  let trafficChartInstance = null;
  function renderAdminTrafficChart(labels, values, totalGb) {
    const canvas = document.getElementById('adminTrafficChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const totalEl = document.getElementById('trafficChartTotal');
    if (totalEl) totalEl.innerHTML = `<span>${formatNumber(totalGb || 0)}</span><span class="text-[9px] text-cyan-300 font-sans">GB</span>`;

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
          pointBorderColor: '#0f172a',
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
            callbacks: {
              label: (ctx) => `${formatNumber(ctx.raw)} GB`
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: '#94a3b8', font: { family: 'Vazirmatn', size: 9 } }
          },
          y: {
            grid: { color: 'rgba(51, 65, 85, 0.3)' },
            ticks: {
              color: '#94a3b8',
              font: { family: 'Vazirmatn', size: 9 },
              callback: (val) => `${val} GB`
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
      const statusColor = isOnline ? 'text-emerald-400' : 'text-rose-400';
      const statusBadge = isOnline ? '🟢 آنلاین' : '🔴 آفلاین';

      const cpuText = (n.cpu_percent && n.cpu_percent > 0) ? `CPU: ${n.cpu_percent}%` : null;
      const ramText = (n.ram_percent && n.ram_percent > 0) ? `RAM: ${n.ram_percent}%` : null;
      const specs = [cpuText, ramText].filter(Boolean).join(' | ');

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
                <span class="font-bold text-xs ${statusColor}">${statusBadge}</span>
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

    container.innerHTML = nodes.map(n => {
      const flag = n.flag || getFlagEmoji(n.country_code);
      const isOnline = (n.status || '').toUpperCase() === 'ONLINE';
      const statusColor = isOnline ? 'text-emerald-400' : 'text-rose-400';
      const statusBadge = isOnline ? 'آنلاین' : 'آفلاین';
      const statusBg = isOnline ? 'bg-emerald-950/80 border-emerald-800/60' : 'bg-rose-950/80 border-rose-800/60';
      const dotPulse = isOnline ? 'bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.8)]' : 'bg-rose-500';

      const cpu = Number(n.cpu_percent || 0);
      const ram = Number(n.ram_percent || 0);

      const cpuBarColor = cpu > 85 ? 'bg-rose-500' : (cpu > 60 ? 'bg-amber-500' : 'bg-cyan-500');
      const ramBarColor = ram > 85 ? 'bg-rose-500' : (ram > 60 ? 'bg-amber-500' : 'bg-indigo-500');

      return `
        <div class="bg-gradient-to-b from-slate-800/90 to-slate-900/95 rounded-2xl p-4 border border-slate-700/80 space-y-3.5 shadow-lg relative overflow-hidden group">
          <!-- Top Accent Light -->
          <div class="absolute top-0 right-0 left-0 h-[2px] ${isOnline ? 'bg-gradient-to-r from-emerald-500/0 via-emerald-400/50 to-emerald-500/0' : 'bg-gradient-to-r from-rose-500/0 via-rose-500/40 to-rose-500/0'}"></div>

          <!-- Header: Flag, Name, Status -->
          <div class="flex justify-between items-center">
            <div class="flex items-center gap-2.5 min-w-0">
              <span class="text-2xl flex-shrink-0 filter drop-shadow">${flag}</span>
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <h4 class="font-bold text-xs text-white truncate">${n.name || 'Server Node'}</h4>
                  <span class="w-2 h-2 rounded-full flex-shrink-0 ${dotPulse}"></span>
                </div>
                <span class="text-[10px] text-slate-400 block mt-0.5 font-sans">${n.country_code ? 'موقعیت: ' + n.country_code : 'کلاستر رمنناویو'}</span>
              </div>
            </div>
            <span class="text-[10px] font-bold font-mono ${statusColor} ${statusBg} px-2.5 py-1 rounded-xl border flex-shrink-0 flex items-center gap-1.5">
              <span class="w-1.5 h-1.5 rounded-full ${isOnline ? 'bg-emerald-400' : 'bg-rose-400'}"></span>
              ${statusBadge}
            </span>
          </div>

          <!-- Host & ID Identifiers Strip (Neat LTR Badges) -->
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div class="bg-slate-950/60 p-2.5 rounded-xl border border-slate-800/80 flex flex-col justify-center">
              <span class="text-[9px] text-slate-400 block mb-0.5">آدرس سرور (Host):</span>
              <span class="font-mono text-cyan-300 text-[11px] truncate" dir="ltr" title="${n.address || '—'}">${n.address || '—'}</span>
            </div>
            <div class="bg-slate-950/60 p-2.5 rounded-xl border border-slate-800/80 flex flex-col justify-center">
              <span class="text-[9px] text-slate-400 block mb-0.5">شناسه نود (Node ID):</span>
              <span class="font-mono text-indigo-300 text-[11px] truncate" dir="ltr" title="${n.id || '--'}">#${n.id || '--'}</span>
            </div>
          </div>

          <!-- System Resource Gauges (CPU & RAM Progress Bars) -->
          <div class="space-y-2 bg-slate-950/40 p-2.5 rounded-xl border border-slate-800/50">
            <!-- CPU Progress -->
            <div class="space-y-1">
              <div class="flex justify-between items-center text-[10px]">
                <span class="text-slate-400">پردازنده (CPU):</span>
                <span class="font-mono font-bold ${cpu > 80 ? 'text-rose-400' : 'text-slate-200'}">${cpu > 0 ? cpu + '%' : 'در دسترس نیست'}</span>
              </div>
              <div class="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div class="h-full ${cpuBarColor} transition-all duration-500" style="width: ${Math.min(100, Math.max(0, cpu))}%"></div>
              </div>
            </div>

            <!-- RAM Progress -->
            <div class="space-y-1">
              <div class="flex justify-between items-center text-[10px]">
                <span class="text-slate-400">حافظه رم (RAM):</span>
                <span class="font-mono font-bold ${ram > 80 ? 'text-rose-400' : 'text-slate-200'}">${ram > 0 ? ram + '%' : 'در دسترس نیست'}</span>
              </div>
              <div class="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div class="h-full ${ramBarColor} transition-all duration-500" style="width: ${Math.min(100, Math.max(0, ram))}%"></div>
              </div>
            </div>
          </div>

          <!-- Bottom Metrics: Connected users & Traffic -->
          <div class="grid grid-cols-2 gap-2 text-center text-[10px]">
            <div class="bg-slate-950/60 p-2 rounded-xl border border-slate-800/80">
              <span class="text-slate-400 block mb-0.5">کاربران متصل زنده</span>
              <b class="text-emerald-400 font-mono text-xs">${formatNumber(n.connected_users || 0)} نفر</b>
            </div>
            <div class="bg-slate-950/60 p-2 rounded-xl border border-slate-800/80">
              <span class="text-slate-400 block mb-0.5">ترافیک مصرفی نود</span>
              <b class="text-cyan-400 font-mono text-xs" dir="ltr">${n.traffic_used_gb ? n.traffic_used_gb + ' GB' : '۰ GB'}</b>
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
      // Username with @ strictly on the left (LTR display)
      const usernameText = u.username ? `@${u.username}` : 'بدون یوزرنیم';
      const initial = (u.username || String(u.telegram_id))[0].toUpperCase();
      const p = u.panel_account;

      let statusBadge = '<span class="px-1.5 py-0.5 rounded text-[9px] bg-slate-700 text-slate-300 font-medium">بدون اکانت</span>';
      if (u.is_banned) {
        statusBadge = '<span class="px-1.5 py-0.5 rounded text-[9px] bg-rose-500/20 text-rose-400 font-bold border border-rose-500/30">مسدود</span>';
      } else if (p && p.exists) {
        const st = (p.status || '').toUpperCase();
        if (st === 'ACTIVE') statusBadge = '<span class="px-1.5 py-0.5 rounded text-[9px] bg-emerald-500/20 text-emerald-400 font-bold border border-emerald-500/30">فعال</span>';
        else if (st === 'DISABLED') statusBadge = '<span class="px-1.5 py-0.5 rounded text-[9px] bg-amber-500/20 text-amber-400 font-bold border border-amber-500/30">غیرفعال</span>';
        else if (st === 'EXPIRED') statusBadge = '<span class="px-1.5 py-0.5 rounded text-[9px] bg-rose-500/20 text-rose-400 font-bold border border-rose-500/30">منقضی</span>';
        else statusBadge = `<span class="px-1.5 py-0.5 rounded text-[9px] bg-blue-500/20 text-blue-400 font-bold border border-blue-500/30">${st}</span>`;
      }

      let serviceLineHtml = `
        <div class="bg-slate-900/60 px-3 py-2 rounded-xl border border-slate-800 text-xs text-slate-400 text-center">
          بدون اشتراک فعال
        </div>
      `;
      if (p && p.exists) {
        const limitStr = p.limit_traffic_gb > 0 ? `${p.limit_traffic_gb} GB` : 'نامحدود';
        const remStr = p.remaining_traffic_gb !== undefined && p.remaining_traffic_gb >= 0
          ? `${p.remaining_traffic_gb} GB`
          : `${p.used_traffic_gb || 0} GB`;

        let daysText = 'نامحدود';
        let daysColor = 'text-indigo-300';
        let daysBg = 'bg-indigo-950/60 border-indigo-800/50';

        if (p.days_left !== undefined && p.days_left !== null) {
          if (p.days_left > 3) {
            daysText = `${formatNumber(p.days_left)} روز`;
            daysColor = 'text-emerald-300';
            daysBg = 'bg-emerald-950/60 border-emerald-800/50';
          } else if (p.days_left > 0) {
            daysText = `${formatNumber(p.days_left)} روز`;
            daysColor = 'text-amber-300';
            daysBg = 'bg-amber-950/60 border-amber-800/50';
          } else {
            daysText = 'منقضی شده';
            daysColor = 'text-rose-400';
            daysBg = 'bg-rose-950/60 border-rose-800/50';
          }
        }

        serviceLineHtml = `
          <div class="bg-slate-900/70 p-2.5 rounded-xl border border-slate-700/60 flex items-center justify-between text-xs gap-2">
            <div class="flex items-center gap-1.5 font-mono text-[11px] truncate">
              <span class="text-slate-400 text-[10px] font-sans">ترافیک:</span>
              <span dir="ltr" class="font-bold text-cyan-300">${limitStr}</span>
              <span dir="ltr" class="text-slate-400 text-[10px]">(${remStr})</span>
            </div>
            <div class="flex items-center gap-1 flex-shrink-0">
              <span class="text-slate-400 text-[10px]">زمان:</span>
              <span class="${daysColor} ${daysBg} border px-2 py-0.5 rounded-lg text-[10px] font-bold">
                ${daysText}
              </span>
            </div>
          </div>
        `;
      }

      const avatarSrc = u.avatar_url || `/api/user/avatar?user_id=${u.telegram_id}`;

      return `
        <div class="bg-slate-800/80 rounded-2xl p-3.5 border border-slate-700/80 space-y-2.5 shadow transition">
          <div class="flex items-start justify-between">
            <div class="flex items-center gap-2.5 min-w-0">
              <!-- User Profile Avatar with Initials Fallback -->
              <div class="w-10 h-10 rounded-full bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-white text-xs shadow overflow-hidden flex-shrink-0 relative">
                <img src="${avatarSrc}" alt="Avatar" class="w-full h-full object-cover" onerror="this.classList.add('hidden'); if(this.nextElementSibling) this.nextElementSibling.classList.remove('hidden');" />
                <span class="${u.avatar_url ? 'hidden' : ''} font-bold">${initial}</span>
              </div>
              <div class="min-w-0">
                <div class="flex items-center gap-1.5 flex-wrap">
                  <div onclick="window.adminActions.quickCopy('@${u.username}', 'نام کاربری')" dir="ltr" class="text-xs font-bold text-white font-mono truncate max-w-[130px] cursor-pointer hover:text-cyan-300 active:scale-95 transition flex items-center gap-1 group" title="برای کپی نام کاربری کلیک کنید">
                    <span>${usernameText}</span>
                    <svg class="w-3 h-3 text-slate-500 group-hover:text-cyan-300 opacity-70 transition flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
                  </div>
                  ${u.is_online ? '<span class="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)] animate-pulse" title="متصل زنده به سرور"></span>' : ''}
                  ${statusBadge}
                  ${(u.is_expiring || (p && p.exists && ((p.days_left !== null && p.days_left > 0 && p.days_left <= 3) || (p.remaining_traffic_gb >= 0 && p.remaining_traffic_gb <= 2.0 && p.limit_traffic_gb > 0)))) ? '<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[9px] font-bold animate-pulse" title="هشدار: حجم یا زمان رو به اتمام است"><svg class="w-2.5 h-2.5 text-amber-300" fill="currentColor" viewBox="0 0 20 20"><path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zM10 18a3 3 0 01-3-3h6a3 3 0 01-3 3z"/></svg> رو به اتمام</span>' : ''}
                </div>
                <div onclick="window.adminActions.quickCopy('${u.telegram_id}', 'شناسه عددی')" class="text-[10px] text-slate-400 font-mono mt-0.5 cursor-pointer hover:text-cyan-300 active:scale-95 transition flex items-center gap-1 group w-fit" title="برای کپی شناسه عددی کلیک کنید">
                  <span>ID: ${u.telegram_id}</span>
                  <svg class="w-2.5 h-2.5 text-slate-500 group-hover:text-cyan-300 opacity-70 transition flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
                </div>
              </div>
            </div>
            <span class="text-[11px] font-mono font-bold text-emerald-400 flex-shrink-0">${formatNumber(u.wallet_balance || 0)} ت</span>
          </div>

          <!-- Structured Service Metrics -->
          ${serviceLineHtml}

          <!-- Quick Action Buttons -->
          <div class="space-y-1.5 pt-1">
            <div class="grid grid-cols-4 gap-1 text-center text-[10px]">
              <button class="bg-blue-950/60 hover:bg-blue-900 text-blue-300 border border-blue-800/50 py-1.5 rounded-lg transition active:scale-95 font-medium flex items-center justify-center gap-1" onclick="window.adminActions.openModifyUser(${u.telegram_id}, '${u.username || u.telegram_id}', 'traffic')" title="افزایش حجم">
                <span>+</span>
                <span>ترافیک</span>
              </button>
              <button class="bg-indigo-950/60 hover:bg-indigo-900 text-indigo-300 border border-indigo-800/50 py-1.5 rounded-lg transition active:scale-95 font-medium flex items-center justify-center gap-1" onclick="window.adminActions.openModifyUser(${u.telegram_id}, '${u.username || u.telegram_id}', 'days')" title="تمدید زمان">
                <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                <span>تمدید</span>
              </button>
              <button class="bg-emerald-950/60 hover:bg-emerald-900 text-emerald-300 border border-emerald-800/50 py-1.5 rounded-lg transition active:scale-95 font-medium flex items-center justify-center gap-1" onclick="window.adminActions.openWalletModal(${u.telegram_id}, '${u.username || u.telegram_id}')" title="شارژ یا کسر موجودی">
                <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"/></svg>
                <span>موجودی</span>
              </button>
              <button class="bg-purple-950/60 hover:bg-purple-900 text-purple-300 border border-purple-800/50 py-1.5 rounded-lg transition active:scale-95 font-medium flex items-center justify-center gap-1" onclick="window.adminActions.resetTrial(${u.telegram_id}, '${u.username || u.telegram_id}')" title="فعال‌سازی مجدد تست">
                <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v13m0-13V6a2 2 0 112 2h-2zm0 0V5.5A2.5 2.5 0 109.5 8H12zm-7 4h14M5 12a2 2 0 01-2-2V7a2 2 0 012-2h14a2 2 0 012 2v3a2 2 0 01-2 2M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7"/></svg>
                <span>تست</span>
              </button>
            </div>
            <div class="grid grid-cols-3 gap-1.5 text-center text-[10px]">
              <button class="bg-cyan-950/60 hover:bg-cyan-900 text-cyan-300 border border-cyan-800/50 py-1.5 rounded-lg transition active:scale-95 font-medium flex items-center justify-center gap-1" onclick="window.adminActions.openSubModal(${u.telegram_id}, '${u.username || u.telegram_id}', '${p?.subscription_url || ''}')" title="مشاهده و تغییر لینک سابسکریپشن">
                <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/></svg>
                <span>لینک ساب</span>
              </button>
              <button class="bg-teal-950/60 hover:bg-teal-900 text-teal-300 border border-teal-800/50 py-1.5 rounded-lg transition active:scale-95 font-medium flex items-center justify-center gap-1" onclick="window.adminActions.openHwidModal(${u.telegram_id}, '${u.username || u.telegram_id}')" title="دستگاه‌های متصل و نشست‌ها">
                <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z"/></svg>
                <span>دستگاه‌ها</span>
              </button>
              <button class="${u.is_banned ? 'bg-emerald-950/60 hover:bg-emerald-900 text-emerald-300 border-emerald-800/50' : 'bg-rose-950/60 hover:bg-rose-900 text-rose-300 border-rose-800/50'} border py-1.5 rounded-lg transition active:scale-95 font-medium flex items-center justify-center gap-1" onclick="window.adminActions.toggleBan(${u.telegram_id}, ${u.is_banned})">
                ${u.is_banned ? '<svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg><span>آزاد</span>' : '<svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"/></svg><span>مسدود</span>'}
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
        b.className = 'user-filter-btn px-2.5 py-1 rounded-lg bg-slate-800 text-slate-400 hover:text-white transition';
      });
      btn.className = 'user-filter-btn px-2.5 py-1 rounded-lg bg-blue-600 text-white font-bold transition';
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

  // --- 6. Admin Actions Namespace ---

  const modifyUserModal = document.getElementById('modifyUserModal');
  const modifyModalTitle = document.getElementById('modifyModalTitle');
  const modifyModalLabel = document.getElementById('modifyModalLabel');
  const modifyModalInput = document.getElementById('modifyModalInput');

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

    openModifyUser(telegram_id, name, type) {
      currentModifyTarget = { telegram_id, name, type };
      if (modifyUserModal) modifyUserModal.classList.remove('hidden');
      if (type === 'traffic') {
        if (modifyModalTitle) modifyModalTitle.innerText = `افزایش ترافیک: ${name}`;
        if (modifyModalLabel) modifyModalLabel.innerText = 'مقدار ترافیک افزایشی (GB):';
        if (modifyModalInput) modifyModalInput.value = '10';
      } else {
        if (modifyModalTitle) modifyModalTitle.innerText = `تمدید اشتراک: ${name}`;
        if (modifyModalLabel) modifyModalLabel.innerText = 'تعداد روز افزایشی:';
        if (modifyModalInput) modifyModalInput.value = '30';
      }
      modifyModalInput?.focus();
    },

    closeModifyModal() {
      if (modifyUserModal) modifyUserModal.classList.add('hidden');
      currentModifyTarget = null;
    },

    async applyUserModification() {
      if (!currentModifyTarget) return;
      const amount = parseFloat(modifyModalInput?.value || 0);
      if (isNaN(amount) || amount <= 0) {
        if (window.showToast) window.showToast('لطفاً مقداری معتبر وارد نمایید.');
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
          currentModifyTarget.type,
          amount
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
          submitBtn.innerText = 'ثبت تغییرات';
        }
      }
    },

    async resetTrial(telegram_id, name) {
      if (!confirm(`آیا از فعال‌سازی مجدد قابلیت دریافت اکانت تست برای کاربر ${name} اطمینان دارید؟`)) return;
      try {
        const res = await window.api.resetUserTrial(telegram_id);
        if (res && res.ok) {
          if (window.showToast) window.showToast(`✅ ${res.message || 'قابلیت تست برای کاربر فعال شد.'}`);
          if (window.hapticFeedback) window.hapticFeedback('success');
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در فعال‌سازی تست'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطا در برقراری ارتباط');
      }
    },

    async killSessions(telegram_id, name) {
      if (!confirm(`آیا از قطع تمام نشست‌های فعال دستگاه‌های کاربر ${name} اطمینان دارید؟`)) return;
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
      if (!confirm(`آیا از ${actionText} این کاربر اطمینان دارید؟`)) return;
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
      if (!confirm(`آیا از ${approved ? 'تایید و شارژ' : 'رد'} این فیش مطمئن هستید؟`)) return;
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
          if (window.showToast) window.showToast(`✅ ${res.message || 'موجودی به‌روز شد'}`);
          if (window.hapticFeedback) window.hapticFeedback('success');
          this.closeWalletModal();
          fetchAdminUsers(currentPage);
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
      if (!confirm(`آیا از باطل کردن لینک قبلی و صدور لینک جدید برای ${name} اطمینان دارید؟`)) return;
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
      if (!confirm(`آیا از ابطال لینک قبلی و ساخت لینک جدید سابسکریپشن برای کاربر ${name} اطمینان دارید؟`)) return;
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

    // --- HWID Devices Inspector ---
    async openHwidModal(telegram_id, name) {
      currentHwidTarget = { telegram_id, name };
      const modal = document.getElementById('hwidModal');
      const title = document.getElementById('hwidModalTitle');
      const list = document.getElementById('hwidDevicesList');
      if (modal) modal.classList.remove('hidden');
      if (title) title.innerText = `📱 دستگاه‌های: ${name}`;
      if (list) list.innerHTML = '<div class="p-6 text-center text-slate-400">در حال دریافت دستگاه‌ها...</div>';

      try {
        const res = await window.api.getUserHwidDevices(telegram_id);
        if (!res || !res.ok) {
          list.innerHTML = `<div class="p-4 text-center text-rose-400">${res?.error || 'خطا در دریافت لیست'}</div>`;
          return;
        }
        const devices = res.devices || [];
        if (devices.length === 0) {
          list.innerHTML = '<div class="p-6 text-center text-slate-400">هیچ دستگاه فعالی متصل نیست 🟢</div>';
          return;
        }

        list.innerHTML = devices.map(d => {
          const hwid = d.hwid || d.id || '';
          const os = d.os || d.platform || 'دستگاه متصل';
          const brand = d.brand || d.model || '';
          const ip = d.requestIp || d.ip || d.lastIp || d.clientIp || '—';
          return `
            <div class="bg-slate-900/90 p-3 rounded-2xl border border-slate-800 flex items-center justify-between gap-2.5">
              <div class="min-w-0 flex-1">
                <b class="text-white text-xs block truncate">${os} ${brand ? '(' + brand + ')' : ''}</b>
                <div class="flex items-center gap-1.5 mt-0.5 text-[10px] text-slate-400">
                  <span>آی‌پی:</span>
                  <span dir="ltr" class="font-mono text-cyan-300">${ip}</span>
                </div>
                <div class="flex items-center gap-1.5 mt-1">
                  <span class="text-[9px] text-slate-500">HWID:</span>
                  <span dir="ltr" class="font-mono text-[9px] text-slate-300 bg-slate-950/70 px-2 py-0.5 rounded border border-slate-800/80 truncate max-w-[170px]" title="${hwid}">${hwid}</span>
                </div>
              </div>
              <button onclick="window.adminActions.deleteHwid(${telegram_id}, '${hwid}')" class="bg-rose-950/60 hover:bg-rose-900 text-rose-300 border border-rose-800/60 p-2.5 rounded-xl transition active:scale-95 flex items-center justify-center flex-shrink-0" title="قطع اتصال این دستگاه">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
              </button>
            </div>
          `;
        }).join('');
      } catch (e) {
        list.innerHTML = '<div class="p-4 text-center text-rose-400">خطای شبکه در دریافت اطلاعات دستگاه‌ها</div>';
      }
    },

    closeHwidModal() {
      document.getElementById('hwidModal')?.classList.add('hidden');
      currentHwidTarget = null;
    },

    async killSessionsFromModal() {
      if (!currentHwidTarget) return;
      const { telegram_id, name } = currentHwidTarget;
      if (!confirm(`آیا از قطع تمام نشست‌ها و اتصالات دستگاه‌های کاربر ${name} اطمینان دارید؟`)) return;
      try {
        const res = await window.api.killUserSessions(telegram_id);
        if (res && res.ok) {
          if (window.showToast) window.showToast(`✅ تعداد ${formatNumber(res.killed_devices || 0)} نشست فعال قطع شدند.`);
          if (window.hapticFeedback) window.hapticFeedback('success');
          this.openHwidModal(telegram_id, name);
          syncAdminOverview();
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در قطع نشست‌ها'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطا در ارتباط با سرور');
      }
    },

    async deleteHwid(telegram_id, hwid) {
      if (!confirm('آیا از قطع اتصال این دستگاه مطمئن هستید؟')) return;
      try {
        const res = await window.api.deleteUserHwid(telegram_id, hwid);
        if (res && res.ok) {
          if (window.showToast) window.showToast('✅ اتصال دستگاه با موفقیت قطع شد.');
          if (window.hapticFeedback) window.hapticFeedback('success');
          if (currentHwidTarget) this.openHwidModal(currentHwidTarget.telegram_id, currentHwidTarget.name);
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
              <p class="text-xs">هیچ پلن یا تعرفه‌ای هنوز ثبت نشده است.</p>
              <button onclick="window.adminActions.openPlanModal()" class="bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold px-4 py-2 rounded-xl transition shadow active:scale-95">
                + ایجاد اولین پلن
              </button>
            </div>
          `;
          return;
        }

        container.innerHTML = adminPlansData.map(p => {
          const statusBadge = p.is_active
            ? '<span class="text-[10px] bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 px-2 py-0.5 rounded-lg font-bold">فعال</span>'
            : '<span class="text-[10px] bg-slate-800 text-slate-400 border border-slate-700 px-2 py-0.5 rounded-lg font-medium">غیرفعال</span>';

          const trafficHtml = p.traffic_gb > 0
            ? `<span class="inline-flex items-center justify-center gap-1 font-mono font-bold" dir="ltr"><span class="text-cyan-300 text-xs">${p.traffic_gb}</span><span class="text-cyan-400 text-[10px]">GB</span></span>`
            : '<span class="text-cyan-300 font-bold">نامحدود</span>';
          const durationText = p.duration_days > 0 ? `${p.duration_days} روز` : 'نامحدود';
          const hwidText = p.hwid_limit > 0 ? `${p.hwid_limit} کاربر` : 'پیش‌فرض';

          return `
            <div class="bg-slate-800/80 rounded-2xl p-4 border border-slate-700/80 space-y-3 shadow transition">
              <div class="flex items-start justify-between">
                <div>
                  <div class="flex items-center gap-2">
                    <b class="text-white text-xs font-bold">${p.name}</b>
                    ${statusBadge}
                  </div>
                  ${p.description ? `<p class="text-[10px] text-slate-400 mt-0.5 line-clamp-1">${p.description}</p>` : ''}
                </div>
                <span class="text-sm font-black text-emerald-400 font-mono">${formatNumber(p.price || 0)} <span class="text-[10px] font-sans font-normal text-slate-400">تومان</span></span>
              </div>

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

              <div class="flex gap-1.5 pt-1 text-[11px]">
                <button onclick="window.adminActions.openPlanModal(${p.id})" class="flex-1 bg-slate-700/70 hover:bg-slate-700 text-white font-medium py-1.5 rounded-xl transition text-center flex items-center justify-center gap-1">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
                  <span>ویرایش</span>
                </button>
                <button onclick="window.adminActions.togglePlan(${p.id}, ${p.is_active})" class="flex-1 ${p.is_active ? 'bg-amber-950/60 text-amber-300 border border-amber-800/50' : 'bg-emerald-950/60 text-emerald-300 border border-emerald-800/50'} py-1.5 rounded-xl transition font-medium text-center">
                  ${p.is_active ? 'غیرفعال‌سازی' : 'فعال‌سازی'}
                </button>
                <button onclick="window.adminActions.deletePlan(${p.id}, '${p.name}')" class="bg-rose-950/60 hover:bg-rose-900 text-rose-300 border border-rose-800/50 px-3 py-1.5 rounded-xl transition font-medium flex items-center justify-center">
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
        if (saveBtn) { saveBtn.disabled = false; saveBtn.innerText = 'ذخیره پلن'; }
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
            ? '<span class="text-[10px] bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 px-2 py-0.5 rounded-lg font-bold">فعال</span>'
            : '<span class="text-[10px] bg-slate-800 text-slate-400 border border-slate-700 px-2 py-0.5 rounded-lg font-medium">غیرفعال</span>';

          const discountText = c.discount_percent > 0
            ? `${c.discount_percent}٪ تخفیف`
            : `${formatNumber(c.discount_amount || 0)} تومان`;

          const maxText = c.max_uses > 0 ? `${c.used_count || 0} / ${c.max_uses}` : `${c.used_count || 0} (نامحدود)`;
          const expiryText = c.expires_at || 'نامحدود (دائمی)';

          return `
            <div class="bg-slate-800/80 rounded-2xl p-4 border border-slate-700/80 space-y-3 shadow transition">
              <div class="flex items-start justify-between">
                <div>
                  <div class="flex items-center gap-2">
                    <span class="font-mono font-bold text-pink-400 text-sm tracking-wider uppercase bg-pink-950/50 border border-pink-800/40 px-2.5 py-0.5 rounded-xl">${c.code}</span>
                    ${statusBadge}
                  </div>
                  <span class="text-[11px] text-emerald-400 font-bold block mt-1.5">${discountText}</span>
                </div>
              </div>

              <div class="grid grid-cols-2 gap-2 text-[10px] bg-slate-900/60 p-2 rounded-xl">
                <div>
                  <span class="text-slate-400 block text-[9px]">دفعات استفاده:</span>
                  <b class="text-slate-200 font-mono">${maxText}</b>
                </div>
                <div>
                  <span class="text-slate-400 block text-[9px]">تاریخ انقضا:</span>
                  <b class="text-slate-200 font-mono">${expiryText}</b>
                </div>
              </div>

              <div class="flex gap-2 pt-1 text-[11px]">
                <button onclick="window.adminActions.toggleCoupon(${c.id}, ${c.is_active})" class="flex-1 ${c.is_active ? 'bg-amber-950/60 text-amber-300 border border-amber-800/50' : 'bg-emerald-950/60 text-emerald-300 border border-emerald-800/50'} py-1.5 rounded-xl transition font-medium text-center">
                  ${c.is_active ? 'غیرفعال‌سازی' : 'فعال‌سازی'}
                </button>
                <button onclick="window.adminActions.deleteCoupon(${c.id}, '${c.code}')" class="bg-rose-950/60 hover:bg-rose-900 text-rose-300 border border-rose-800/50 px-3 py-1.5 rounded-xl transition font-medium flex items-center justify-center">
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
        container.innerHTML = `<div class="p-4 text-center text-rose-400 text-xs">${res?.error || 'خطا در دریافت فیش‌ها'}</div>`;
        return;
      }
      const topups = res.topups || [];
      if (topups.length === 0) {
        container.innerHTML = '<div class="bg-slate-900/40 p-4 rounded-xl text-center text-slate-400 text-xs border border-slate-800">هیچ فیش واریزی در انتظاری وجود ندارد 🟢</div>';
        return;
      }

      container.innerHTML = topups.map(t => `
        <div class="bg-slate-800/90 rounded-2xl p-3.5 border border-slate-700/80 space-y-2.5 shadow">
          <div class="flex justify-between items-center">
            <div>
              <span class="text-xs font-bold text-white">فیش #${t.id}</span>
              <span class="text-[10px] text-slate-400 block font-mono">کاربر: ${t.username ? '@' + t.username : t.telegram_id}</span>
            </div>
            <span class="text-sm font-black text-emerald-400 font-mono">${formatNumber(t.amount || 0)} ت</span>
          </div>
          <div class="flex gap-2 pt-1 text-[11px]">
            <button onclick="window.adminActions.handleTopup(${t.id}, true)" class="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-1.5 rounded-xl transition active:scale-95">
              ✓ تایید و شارژ
            </button>
            <button onclick="window.adminActions.handleTopup(${t.id}, false)" class="flex-1 bg-rose-600 hover:bg-rose-500 text-white font-bold py-1.5 rounded-xl transition active:scale-95">
              ✕ رد فیش
            </button>
          </div>
        </div>
      `).join('');
    } catch (err) {
      container.innerHTML = '<div class="p-4 text-center text-rose-400 text-xs">خطای شبکه در دریافت فیش‌ها</div>';
    }
  }

  // Direct Ticket Reply Handler
  document.getElementById('sendDirectTicketReplyBtn')?.addEventListener('click', async () => {
    const uid = document.getElementById('directTicketUserId')?.value?.trim();
    const txt = document.getElementById('directTicketMsg')?.value?.trim();
    if (!uid || !txt) {
      if (window.showToast) window.showToast('لطفاً شناسه کاربر و متن پیام را وارد کنید.');
      return;
    }
    try {
      const res = await window.api.replyDirectTicket(parseInt(uid), txt);
      if (res && res.ok) {
        if (window.showToast) window.showToast('✅ پیام برای کاربر ارسال شد.');
        if (window.hapticFeedback) window.hapticFeedback('success');
        const txtEl = document.getElementById('directTicketMsg');
        if (txtEl) txtEl.value = '';
      } else {
        if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ارسال پیام'}`);
        if (window.hapticFeedback) window.hapticFeedback('error');
      }
    } catch (e) {
      if (window.showToast) window.showToast('خطای شبکه در ارسال پیام');
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
      ton_rate_toman: parseInt(document.getElementById('settingTonRate')?.value || '0', 10),
      ton_wallet_address: document.getElementById('settingTonWallet')?.value?.trim() || '',
      trial_traffic_gb: parseInt(document.getElementById('settingTrialTraffic')?.value || '1', 10),
      trial_duration_days: parseInt(document.getElementById('settingTrialDays')?.value || '1', 10),
      referral_reward_gb: parseInt(document.getElementById('settingRefReward')?.value || '5', 10),
      support_contact: document.getElementById('settingSupportContact')?.value?.trim() || '',
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
        b.className = 'broadcast-audience-btn px-2.5 py-1 rounded-xl bg-slate-800 text-slate-400 hover:text-white text-[10px] transition border border-slate-700/60';
      });
      btn.className = 'broadcast-audience-btn px-2.5 py-1 rounded-xl bg-blue-600 text-white font-bold text-[10px] transition border border-blue-500 shadow-sm';
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
          if (sentEl) sentEl.innerText = '۰ پیام';
          const failEl = document.getElementById('reportFailedCount');
          if (failEl) failEl.innerText = '۰';
          const statusEl = document.getElementById('reportStatusText');
          if (statusEl) statusEl.innerText = 'در حال ارسال پیام‌ها...';
          const pBar = document.getElementById('reportProgressBar');
          if (pBar) pBar.style.width = '10%';
          const pText = document.getElementById('reportPercentText');
          if (pText) pText.innerText = '۰%';

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
    syncAdminOverview();
    if (window.showToast) window.showToast('🔄 اطلاعات به‌روزرسانی شد.');
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  document.getElementById('quickRefreshMetricsBtn')?.addEventListener('click', () => {
    syncAdminOverview();
    if (window.showToast) window.showToast('🔄 داده‌ها سینک شدند.');
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  document.getElementById('syncAllNodesBtn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    syncAdminOverview();
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

  document.getElementById('refreshNodesTabBtn')?.addEventListener('click', () => {
    syncAdminOverview();
    if (window.showToast) window.showToast('🔄 وضعیت نودها به‌روزرسانی شد.');
    if (window.hapticFeedback) window.hapticFeedback('impact');
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

  // Initial Sync
  syncAdminOverview();
})();
