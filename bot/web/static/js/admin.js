/**
 * RemnaAdmin Pro - Modular Admin Suite JavaScript
 * Follows DRY and high-performance asynchronous standards.
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
    return Number(num).toLocaleString('fa-IR');
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
      if (adminThemeIcon) adminThemeIcon.innerText = '🌙';
      appBody?.classList.replace('bg-slate-100', 'bg-[#080d1a]');
      phoneFrame?.classList.replace('bg-white', 'bg-[#0f172a]');
      phoneFrame?.classList.replace('text-slate-900', 'text-slate-100');
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('theme-light');
      if (adminThemeIcon) adminThemeIcon.innerText = '☀️';
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

      const bw = document.getElementById('adminMonthTraffic');
      if (bw) bw.innerText = `${m.month_traffic_gb || 0} GB`;

      const onDev = document.getElementById('adminOnlineDevices');
      if (onDev) onDev.innerText = formatNumber(m.online_devices || 0);

      // Dynamic Pending Tasks Alert Banner
      const pendingBox = document.getElementById('adminPendingBanner');
      const pendingSum = document.getElementById('adminPendingSummary');
      const viewPendingBtn = document.getElementById('viewPendingBtn');
      const pTopups = m.pending_topups || 0;
      const pTickets = m.open_tickets || 0;
      const offNodes = m.offline_nodes || 0;

      if (pendingSum) {
        if (pTopups > 0 || pTickets > 0 || offNodes > 0) {
          const parts = [];
          if (pTopups > 0) parts.push(`${formatNumber(pTopups)} فیش واریزی در انتظار`);
          if (pTickets > 0) parts.push(`${formatNumber(pTickets)} تیکت جدید`);
          if (offNodes > 0) parts.push(`${formatNumber(offNodes)} سرور آفلاین`);

          pendingSum.innerText = parts.join(' + ');
          if (pendingBox) {
            pendingBox.classList.remove('hidden', 'bg-emerald-950/40', 'border-emerald-500/40');
            pendingBox.classList.add('bg-amber-950/40', 'border-amber-500/40');
          }
          if (viewPendingBtn) viewPendingBtn.classList.remove('hidden');
        } else {
          pendingSum.innerText = 'همه فیش‌ها، تیکت‌ها و سرورها پایدار و تایید شده‌اند 🟢';
          if (pendingBox) {
            pendingBox.classList.remove('bg-amber-950/40', 'border-amber-500/40');
            pendingBox.classList.add('bg-emerald-950/40', 'border-emerald-500/40');
          }
          if (viewPendingBtn) viewPendingBtn.classList.add('hidden');
        }
      }

      // Cluster Status Header Bar
      const onlineNodes = nodes.filter(n => (n.status || '').toUpperCase() === 'ONLINE').length;
      const clusterText = document.getElementById('adminClusterStatusText');
      if (clusterText) {
        clusterText.innerHTML = `وضعیت کلاستر: <b class="text-emerald-400">${formatNumber(onlineNodes)} از ${formatNumber(nodes.length)} نود آنلاین</b>`;
      }
      const syncText = document.getElementById('adminLastSyncText');
      if (syncText) syncText.innerText = 'Sync: آنلاین';

      // Render Overview and Full Nodes
      renderOverviewNodes(nodes);
      renderFullNodes(nodes);
      dismissSplash();
    } catch (err) {
      console.error('Failed to sync admin overview:', err);
      dismissSplash();
    }
  }

  function renderOverviewNodes(nodes) {
    const container = document.getElementById('adminOverviewNodesList');
    if (!container) return;
    if (!nodes || nodes.length === 0) {
      container.innerHTML = '<div class="p-3 text-center text-slate-400">هیچ نودی یافت نشد</div>';
      return;
    }

    container.innerHTML = nodes.map(n => {
      const flag = n.flag || getFlagEmoji(n.country_code);
      const isOnline = (n.status || '').toUpperCase() === 'ONLINE';
      const statusColor = isOnline ? 'text-emerald-400' : 'text-rose-400';
      return `
        <div class="bg-slate-900/60 p-2.5 rounded-xl border border-slate-700/50 flex justify-between items-center transition">
          <div class="flex items-center gap-2">
            <span class="text-lg flex-shrink-0">${flag}</span>
            <div>
              <span class="font-bold text-white block text-xs">${n.name || 'Node'}</span>
              <span class="text-[10px] text-slate-400 font-mono">CPU: ${n.cpu_percent || 0}% | RAM: ${n.ram_percent || 0}%</span>
            </div>
          </div>
          <div class="text-left font-mono">
            <span class="${statusColor} font-bold text-[11px]">${formatNumber(n.connected_users || 0)} آنلاین</span>
            <span class="block text-[9px] ${isOnline ? 'text-slate-400' : 'text-rose-400'}">${isOnline ? 'ONLINE' : 'OFFLINE'}</span>
          </div>
        </div>
      `;
    }).join('');
  }

  function renderFullNodes(nodes) {
    const container = document.getElementById('adminNodesFullList');
    if (!container) return;
    if (!nodes || nodes.length === 0) {
      container.innerHTML = '<div class="p-4 text-center text-slate-400">هیچ نودی ثبت نشده است</div>';
      return;
    }

    container.innerHTML = nodes.map(n => {
      const flag = n.flag || getFlagEmoji(n.country_code);
      const isOnline = (n.status || '').toUpperCase() === 'ONLINE';
      return `
        <div class="bg-slate-800/90 rounded-2xl p-4 border border-slate-700/80 space-y-3 shadow">
          <div class="flex justify-between items-start">
            <div class="flex items-center gap-2.5">
              <span class="text-2xl flex-shrink-0">${flag}</span>
              <div>
                <div class="flex items-center gap-2">
                  <h4 class="font-bold text-xs text-white">${n.name || 'Node'}</h4>
                  <span class="w-2 h-2 rounded-full ${isOnline ? 'bg-emerald-400' : 'bg-rose-400'}"></span>
                </div>
                <span class="text-[10px] text-slate-400 font-mono mt-0.5 block">Node ID: ${n.id || '--'} | ${n.country_code || 'XX'}</span>
              </div>
            </div>
            <span class="text-[10px] font-mono ${isOnline ? 'text-emerald-400 bg-emerald-950/60 border-emerald-800/40' : 'text-rose-400 bg-rose-950/60 border-rose-800/40'} px-2 py-0.5 rounded border">${isOnline ? 'ONLINE' : 'OFFLINE'}</span>
          </div>

          <div class="grid grid-cols-3 gap-2 text-center text-[10px]">
            <div class="bg-slate-900/60 p-2 rounded-xl">
              <span class="text-slate-400 block mb-0.5">مصرف CPU</span>
              <b class="text-cyan-400 font-mono text-xs">${n.cpu_percent || 0}%</b>
            </div>
            <div class="bg-slate-900/60 p-2 rounded-xl">
              <span class="text-slate-400 block mb-0.5">مصرف RAM</span>
              <b class="text-indigo-300 font-mono text-xs">${n.ram_percent || 0}%</b>
            </div>
            <div class="bg-slate-900/60 p-2 rounded-xl">
              <span class="text-slate-400 block mb-0.5">کاربران متصل</span>
              <b class="text-emerald-400 font-mono text-xs">${formatNumber(n.connected_users || 0)}</b>
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
        // Show pagination only when pages > 1 (تعداد زیاد شد)
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

      // Remaining Traffic Volume & Days Left
      let trafficRemainingText = 'بدون سرویس فعال';
      let daysRemainingText = '—';

      if (p && p.exists) {
        if (p.remaining_traffic_gb !== undefined && p.remaining_traffic_gb >= 0) {
          trafficRemainingText = `${p.remaining_traffic_gb} GB باقی‌مانده`;
          if (p.limit_traffic_gb > 0) {
            trafficRemainingText += ` (از ${p.limit_traffic_gb} GB)`;
          }
        } else if (p.remaining_traffic_gb < 0) {
          trafficRemainingText = `نامحدود (مصرف: ${p.used_traffic_gb || 0} GB)`;
        } else {
          trafficRemainingText = `${p.used_traffic_gb || 0} GB مصرف‌شده`;
        }

        if (p.days_left !== undefined && p.days_left !== null) {
          daysRemainingText = p.days_left > 0 ? `${formatNumber(p.days_left)} روز مانده` : 'منقضی شده ⚠️';
        } else {
          daysRemainingText = 'نامحدود';
        }
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
                  <span dir="ltr" class="text-xs font-bold text-white font-mono truncate max-w-[130px]">${usernameText}</span>
                  ${statusBadge}
                </div>
                <div class="text-[10px] text-slate-400 font-mono mt-0.5">
                  <span>ID: ${u.telegram_id}</span>
                </div>
              </div>
            </div>
            <span class="text-[11px] font-mono font-bold text-emerald-400 flex-shrink-0">${formatNumber(u.wallet_balance || 0)} ت</span>
          </div>

          <!-- Subscription Metrics Card (Traffic + Days) -->
          <div class="bg-slate-900/70 rounded-xl p-2.5 text-xs grid grid-cols-2 gap-2 border border-slate-800/60">
            <div>
              <span class="text-[10px] text-slate-400 block mb-0.5">📦 حجم باقی‌مانده:</span>
              <b class="font-mono text-cyan-400 text-[11px] block truncate" dir="ltr">${trafficRemainingText}</b>
            </div>
            <div>
              <span class="text-[10px] text-slate-400 block mb-0.5">⏳ زمان اشتراک:</span>
              <b class="font-mono text-indigo-300 text-[11px] block truncate">${daysRemainingText}</b>
            </div>
          </div>

          <!-- Quick Action Buttons -->
          <div class="grid grid-cols-4 gap-1.5 text-center text-[10px]">
            <button class="bg-blue-950/60 hover:bg-blue-900 text-blue-300 border border-blue-800/50 py-1.5 rounded-lg transition active:scale-95" onclick="window.adminActions.openModifyUser(${u.telegram_id}, '${u.username || u.telegram_id}', 'traffic')">
              ➕ ترافیک
            </button>
            <button class="bg-indigo-950/60 hover:bg-indigo-900 text-indigo-300 border border-indigo-800/50 py-1.5 rounded-lg transition active:scale-95" onclick="window.adminActions.openModifyUser(${u.telegram_id}, '${u.username || u.telegram_id}', 'days')">
              ⏳ تمدید
            </button>
            <button class="bg-amber-950/60 hover:bg-amber-900 text-amber-300 border border-amber-800/50 py-1.5 rounded-lg transition active:scale-95" onclick="window.adminActions.killSessions(${u.telegram_id}, '${u.username || u.telegram_id}')">
              ⛔️ نشست‌ها
            </button>
            <button class="${u.is_banned ? 'bg-emerald-950/60 hover:bg-emerald-900 text-emerald-300 border-emerald-800/50' : 'bg-rose-950/60 hover:bg-rose-900 text-rose-300 border-rose-800/50'} border py-1.5 rounded-lg transition active:scale-95" onclick="window.adminActions.toggleBan(${u.telegram_id}, ${u.is_banned})">
              ${u.is_banned ? '✅ آزاد' : '🚫 مسدود'}
            </button>
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
  };

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

      const maintSwitch = document.getElementById('settingMaintSwitch');
      if (maintSwitch) maintSwitch.checked = !!s.maintenance;

      const cardSwitch = document.getElementById('settingCardSwitch');
      if (cardSwitch) cardSwitch.checked = !!s.card_enabled;

      const cryptoSwitch = document.getElementById('settingCryptoSwitch');
      if (cryptoSwitch) cryptoSwitch.checked = !!s.crypto_enabled;

      const cardNum = document.getElementById('settingCardNumber');
      if (cardNum) cardNum.value = s.card_number || '';

      const cardHolder = document.getElementById('settingCardHolder');
      if (cardHolder) cardHolder.value = s.card_holder || '';
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

  document.getElementById('saveBankSettingsBtn')?.addEventListener('click', async () => {
    const card_number = document.getElementById('settingCardNumber')?.value?.trim();
    const card_holder = document.getElementById('settingCardHolder')?.value?.trim();
    try {
      const res = await window.api.saveAdminSettings({ card_number, card_holder });
      if (res && res.ok) {
        if (window.showToast) window.showToast('✅ اطلاعات بانکی با موفقیت ذخیره شد.');
        if (window.hapticFeedback) window.hapticFeedback('success');
      } else {
        if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا'}`);
      }
    } catch (e) {
      if (window.showToast) window.showToast('خطا در ذخیره اطلاعات');
    }
  });

  // --- 9. Broadcast Modal & Audience Targeting ---
  const broadcastModal = document.getElementById('broadcastModal');
  const openBroadcastModalBtn = document.getElementById('openBroadcastModalBtn');
  const closeBroadcastBtn = document.getElementById('closeBroadcastBtn');
  const sendBroadcastBtn = document.getElementById('sendBroadcastBtn');

  openBroadcastModalBtn?.addEventListener('click', () => {
    if (broadcastModal) broadcastModal.classList.remove('hidden');
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  closeBroadcastBtn?.addEventListener('click', () => {
    if (broadcastModal) broadcastModal.classList.add('hidden');
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
      if (res && res.ok) {
        if (window.showToast) window.showToast(`🚀 ${res.message || 'ارسال پیام همگانی آغاز شد.'}`);
        if (window.hapticFeedback) window.hapticFeedback('success');
        if (broadcastModal) broadcastModal.classList.add('hidden');
        const txtEl = document.getElementById('broadcastTextArea');
        if (txtEl) txtEl.value = '';
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

  document.getElementById('syncAllNodesBtn')?.addEventListener('click', () => {
    syncAdminOverview();
    if (window.showToast) window.showToast('🔄 نودها همگام‌سازی شدند.');
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

  // Initial Sync
  syncAdminOverview();
})();
