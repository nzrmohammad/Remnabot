/**
 * RemnaAdmin Pro - Users Management Module (admin_users.js)
 * User accounts, subscription URL regeneration, sessions, bans, bulk operations and user creation.
 */
(function (window) {
  'use strict';

  const $ = id => document.getElementById(id);
  const api = window.api;
  const tg = window.Telegram?.WebApp;
  const formatNumber = window.formatNumber || (n => String(n));
  const getFlagEmoji = window.getFlagEmoji || (() => '🌐');
  const formatDateToJalali = window.formatDateToJalali || (d => d);
  const showConfirmModal = window.showConfirmModal || window.adminActions?.showConfirmModal;
  const showOperationReportModal = window.showOperationReportModal || window.adminActions?.showOperationReportModal;
  window.adminActions = window.adminActions || {};

  let currentPage = 1;
  let currentFilter = 'all';
  let currentSearch = '';
  let currentModifyTarget = null;
  let currentHwidTarget = null;
  let currentSubTarget = null;
  let currentTrialTarget = null;

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
        listContainer.innerHTML = `<div class="p-6 text-center text-rose-400 text-xs">${escapeHtml(res?.error || 'خطا در بارگذاری کاربران')}</div>`;
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

      let statusBadge = '<span class="px-1.5 py-0.5 rounded-lg text-[10px] bg-transparent border border-slate-400/30 t-muted font-medium">بدون اکانت</span>';
      if (u.is_banned) {
        statusBadge = '<span class="px-1.5 py-0.5 rounded-lg text-[10px] bg-transparent t-danger font-bold border border-rose-500/30">مسدود</span>';
      } else if (u.is_expired || (p && p.exists && (p.status || '').toUpperCase() === 'EXPIRED')) {
        statusBadge = '<span class="px-1.5 py-0.5 rounded-lg text-[10px] bg-transparent t-danger font-bold border border-rose-500/30">منقضی</span>';
      } else if (p && p.exists) {
        const st = (p.status || '').toUpperCase();
        if (st === 'ACTIVE') statusBadge = '<span class="px-1.5 py-0.5 rounded-lg text-[10px] bg-transparent t-success font-bold border border-emerald-500/30">فعال</span>';
        else if (st === 'DISABLED') statusBadge = '<span class="px-1.5 py-0.5 rounded-lg text-[10px] bg-transparent t-warn font-bold border border-amber-500/30">غیرفعال</span>';
        else statusBadge = `<span class="px-1.5 py-0.5 rounded-lg text-[10px] bg-transparent t-info font-bold border border-blue-500/30">${st}</span>`;
      }

      const isExpiring = u.is_expiring || (p && p.exists && !u.is_expired && ((p.days_left !== null && p.days_left > 0 && p.days_left <= 3) || (p.remaining_traffic_gb >= 0 && p.remaining_traffic_gb <= 2.0 && p.limit_traffic_gb > 0)));
      const expiringBadgeHtml = isExpiring
        ? '<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[10px] font-bold animate-pulse flex-shrink-0 whitespace-nowrap" title="هشدار: حجم یا زمان رو به اتمام است"><svg class="w-2.5 h-2.5 text-amber-300" fill="currentColor" viewBox="0 0 20 20"><path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zM10 18a3 3 0 01-3-3h6a3 3 0 01-3 3z"/></svg> رو به اتمام</span>'
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
        let badgeColor = 't-success bg-transparent border-emerald-500/30';
        let statusLabel = `${percentUsed}%`;

        if (isUnlimited) {
          barGradient = 'from-blue-500 to-indigo-500';
          barGlow = 'shadow-[0_0_10px_rgba(59,130,246,0.3)]';
          badgeColor = 't-info bg-transparent border-blue-500/30';
          statusLabel = 'ترافیک نامحدود';
          percentUsed = 100;
        } else if (percentUsed >= 90) {
          barGradient = 'from-rose-500 to-red-500';
          barGlow = 'shadow-[0_0_10px_rgba(244,63,94,0.4)]';
          badgeColor = 't-danger bg-transparent border-rose-500/30';
          statusLabel = `${percentUsed}% (بحرانی)`;
        } else if (percentUsed >= 70) {
          barGradient = 'from-amber-500 to-orange-400';
          barGlow = 'shadow-[0_0_10px_rgba(245,158,11,0.35)]';
          badgeColor = 't-warn bg-transparent border-amber-500/30';
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
            timeColor = 't-success';
            timeBoxBorder = 'border-emerald-500/30';
            timeBoxBg = 'bg-transparent';
          } else if (p.days_left > 0) {
            timeText = `${formatNumber(p.days_left)} روز اعتبار`;
            timeSub = expireJalali ? `تا ${expireJalali}` : 'رو به اتمام';
            timeColor = 't-warn';
            timeBoxBorder = 'border-amber-500/30';
            timeBoxBg = 'bg-transparent';
          } else {
            timeText = 'منقضی شده';
            timeSub = expireJalali ? `انقضا: ${expireJalali}` : 'پایان مهلت';
            timeColor = 't-danger';
            timeBoxBorder = 'border-rose-500/30';
            timeBoxBg = 'bg-transparent';
          }
        }

        const remDisplay = isUnlimited ? 'نامحدود' : fmtTraffic(remGb, { html: false });
        const totalDisplay = isUnlimited ? 'نامحدود' : fmtTraffic(limitGb, { html: false });
        const usedDisplay = fmtTraffic(usedGb, { html: false });

        serviceLineHtml = `
          <div class="bg-transparent rounded-xl p-2.5 border border-slate-700/60 space-y-2">
            <!-- Glass Progress Bar & Top Metrics -->
            <div class="space-y-1">
              <div class="flex items-center justify-between text-[10px]">
                <div class="flex items-center gap-1 font-mono text-slate-300">
                  <span class="text-slate-400 text-[10px] font-sans">مصرف:</span>
                  <span dir="ltr" class="font-bold t-main num-bidi">${usedDisplay}</span>
                  <span class="text-slate-400 font-sans">از</span>
                  <span dir="ltr" class="text-slate-400 font-mono num-bidi">${totalDisplay}</span>
                </div>
                <span class="px-1.5 py-0.5 rounded-md text-[10px] font-mono font-bold border ${badgeColor}">
                  ${statusLabel}
                </span>
              </div>
              <!-- Vercel-Style Glass Track -->
              <div class="w-full h-1.5 rounded-full card-inset border border-slate-700/40 overflow-hidden relative" dir="ltr">
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
                  <span class="text-slate-400 text-[10px] block">حجم باقی‌مانده</span>
                  <span dir="ltr" class="font-mono font-bold t-accent truncate block text-[11px]">
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
                  <span class="text-slate-400 text-[10px] block truncate" title="${timeSub}">${timeSub}</span>
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
            <!-- Right: Avatar + Profile Name + Status Badge (Clickable to open Profile Modal) -->
            <div class="flex items-center gap-2.5 min-w-0 cursor-pointer group select-none" onclick="window.adminActions.openUserProfileModal(${u.telegram_id})" title="مشاهده شناسنامه و پروفایل کاربر">
              <!-- User Profile Avatar with Online/Offline indicator badge at bottom-left -->
              <div class="relative flex-shrink-0">
                <div class="w-10 h-10 rounded-full bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-white text-xs shadow overflow-hidden group-hover:ring-2 group-hover:ring-cyan-400/50 transition">
                  <img src="${avatarSrc}" alt="Avatar" class="w-full h-full object-cover" onerror="this.classList.add('hidden'); if(this.nextElementSibling) this.nextElementSibling.classList.remove('hidden');" />
                  <span class="${u.avatar_url ? 'hidden' : ''} font-bold">${escapeHtml(initial)}</span>
                </div>
                <!-- Online / Offline Badge at Bottom-Left of the Avatar -->
                <span class="absolute bottom-0 left-0 w-3 h-3 rounded-full border-2 border-slate-900 ${u.is_online ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.9)] animate-pulse' : 'bg-slate-500'}" title="${u.is_online ? 'آنلاین (متصل به سرور)' : 'آفلاین'}"></span>
              </div>

              <!-- Name and Status Badge side-by-side on the same line -->
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5 min-w-0 flex-wrap">
                  <span class="text-xs font-bold text-white truncate max-w-[120px] sm:max-w-[160px] group-hover:text-cyan-300 transition">
                    ${(displayName || '').startsWith('@') ? `<span class="truncate inline-block font-mono" dir="ltr" style="unicode-bidi: isolate;">${escapeHtml(displayName)}</span>` : `<span class="truncate">${escapeHtml(displayName)}</span>`}
                  </span>
                  <div class="flex-shrink-0">${statusBadge}</div>
                  ${expiringBadgeHtml}
                </div>
              </div>
            </div>

            <!-- Left: Wallet Balance (Number on top, small تومان underneath) -->
            <div class="text-left flex-shrink-0">
              <div class="flex flex-col items-center justify-center text-center leading-tight min-w-[50px]" title="موجودی کیف پول کاربر">
                <span class="text-xs font-mono font-bold text-emerald-600 dark:text-emerald-400 num-bidi" dir="ltr">
                  ${formatNumber(u.wallet_balance || 0)}
                </span>
                <span class="text-[9.5px] font-sans text-emerald-600/80 dark:text-emerald-400/80 -mt-0.5">تومان</span>
              </div>
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
              <button class="bg-transparent hover:bg-emerald-500/10 t-success border border-emerald-500/30 hover:border-emerald-400/60 py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" data-action="wallet" data-tgid="${u.telegram_id}" data-name="${escapeHtml(displayName)}" onclick="window.adminActions.openWalletModal(this.dataset.tgid, this.dataset.name)" title="شارژ یا کسر موجودی">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"/></svg>
                <span>موجودی</span>
              </button>
              <button class="bg-transparent hover:bg-purple-500/10 t-purple border border-purple-500/30 hover:border-purple-400/60 py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" data-action="trial" data-tgid="${u.telegram_id}" data-username="${escapeHtml(u.username || '')}" data-name="${escapeHtml(displayName)}" onclick="window.adminActions.openTrialModal(this.dataset.tgid, this.dataset.username, this.dataset.name)" title="فعال‌سازی مجدد تست">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v13m0-13V6a2 2 0 112 2h-2zm0 0V5.5A2.5 2.5 0 109.5 8H12zm-7 4h14M5 12a2 2 0 01-2-2V7a2 2 0 012-2h14a2 2 0 012 2v3a2 2 0 01-2 2M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7"/></svg>
                <span>اکانت تست</span>
              </button>
            </div>
            <div class="grid grid-cols-3 gap-1.5 text-center text-[10px]">
              <button class="bg-transparent hover:bg-cyan-500/10 t-accent border border-cyan-500/30 hover:border-cyan-400/60 py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" data-action="sub" data-tgid="${u.telegram_id}" data-name="${escapeHtml(displayName)}" data-suburl="${escapeHtml(p?.subscription_url || '')}" onclick="window.adminActions.openSubModal(this.dataset.tgid, this.dataset.name, this.dataset.suburl)" title="لینک سابسکریپشن">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/></svg>
                <span>لینک ساب</span>
              </button>
              <button class="bg-transparent hover:bg-teal-500/10 text-teal-600 dark:text-teal-400 border border-teal-500/30 hover:border-teal-400/60 py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" data-action="hwid" data-tgid="${u.telegram_id}" data-name="${escapeHtml(displayName)}" onclick="window.adminActions.openHwidModal(this.dataset.tgid, this.dataset.name)" title="دستگاه‌های فعال و نشست‌ها">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z"/></svg>
                <span>دستگاه‌ها</span>
              </button>
              <button class="${u.is_banned ? 't-success border-emerald-500/30 hover:border-emerald-400/60 hover:bg-emerald-500/10' : 't-danger border-rose-500/30 hover:border-rose-400/60 hover:bg-rose-500/10'} bg-transparent border py-1.5 rounded-xl transition active:scale-95 font-medium flex items-center justify-center gap-1" onclick="window.adminActions.toggleBan(${u.telegram_id}, ${u.is_banned})">
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
        b.className = 'user-filter-btn px-2.5 py-1 rounded-xl card-inset text-slate-700 dark:text-slate-200 hover:text-white font-bold transition flex items-center gap-1 border border-slate-700/50';
      });
      btn.className = 'user-filter-btn px-2.5 py-1 rounded-xl bg-blue-600 text-white font-bold transition flex items-center gap-1 border border-blue-500 shadow-sm';
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


  // User Actions
  Object.assign(window.adminActions, {
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
          if (window.syncAdminOverview) window.syncAdminOverview();
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
          if (window.syncAdminOverview) window.syncAdminOverview();
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
      if (typeof copyToClipboard === 'function') {
        await copyToClipboard(input.value, '✅ لینک اشتراک با موفقیت کپی شد.');
      } else if (window.copyToClipboard) {
        await window.copyToClipboard(input.value, '✅ لینک اشتراک با موفقیت کپی شد.');
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
      const inactiveClass = 'py-1.5 rounded-xl t-muted hover:t-main font-medium text-center flex items-center justify-center gap-1 transition';

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
          if (list) list.innerHTML = `<div class="p-4 text-center text-rose-400">${escapeHtml(res?.error || 'خطا در دریافت تاریخچه')}</div>`;
          return;
        }
        const records = res.data || [];
        if (records.length === 0) {
          if (list) list.innerHTML = '<div class="p-6 text-center text-slate-400">هنوز درخواستی برای دریافت لینک کانفیگ ثبت نشده است (کاربر نرم‌افزار خود را آپدیت نکرده است).</div>';
          return;
        }

        if (list) {
          list.innerHTML = records.map(r => `
            <div class="srh-card card-inset p-2.5 rounded-2xl border border-slate-700/50 space-y-1.5">
              <!-- Line 1: Client name & tag on right, status badge on left -->
              <div class="flex items-center justify-between gap-2">
                <div class="flex items-center gap-1.5 min-w-0 flex-1">
                  <span class="text-base flex-shrink-0">${r.client_icon || '📱'}</span>
                  <b class="t-main text-xs truncate" title="${escapeHtml(r.user_agent || r.client_name || '')}">${escapeHtml(r.client_name || 'کلاینت')}</b>
                  <span class="text-[9.5px] px-1.5 py-0.5 rounded-md card-inset border border-slate-700/60 t-muted font-mono flex-shrink-0">${escapeHtml(r.client_tag || 'App')}</span>
                </div>
                <span class="inline-flex items-center gap-1 text-[10px] font-bold ${r.is_success ? 'text-emerald-600 dark:text-emerald-400 border-emerald-500/30' : 'text-rose-600 dark:text-rose-400 border-rose-500/30'} bg-transparent px-2 py-0.5 rounded-lg border flex-shrink-0">
                  ${r.is_success ? 'موفق' : (r.status_code ? 'خطا ' + r.status_code : 'خطا')}
                </span>
              </div>

              <!-- Line 2: IP with tap-to-copy, and update time -->
              <div class="flex items-center justify-between text-[10px] pt-1 border-t border-slate-800/60 t-muted gap-2">
                <div class="flex items-center gap-1.5 min-w-0">
                  <button type="button" dir="ltr" class="font-mono text-cyan-700 dark:text-cyan-400 font-bold select-all hover:underline cursor-pointer flex items-center gap-1 btn-copy-ip-r" data-ip="${escapeHtml(r.ip || '')}" title="کلیک جهت کپی آی‌پی">
                    <span>🌐 ${escapeHtml(r.ip || '')}</span>
                    <span class="text-[10px] opacity-70">📋</span>
                  </button>
                </div>
                <div class="flex items-center gap-1.5 text-[10px] t-muted font-mono flex-shrink-0" dir="ltr">
                  <span>⏱</span>
                  <span class="font-bold t-main" title="${escapeHtml(r.relative_time || '')}">${toEnglishDigits(r.date_str && r.date_str !== '—' ? r.date_str : (r.relative_time || 'ثبت‌شده'))}</span>
                  ${r.relative_time && r.relative_time !== '—' && r.relative_time !== r.date_str ? `<span class="text-[10px] t-dim font-sans">(${r.relative_time})</span>` : ''}
                </div>
              </div>
            </div>
          `).join('');

          list.querySelectorAll('.btn-copy-ip-r').forEach(btn => {
            btn.onclick = () => {
              const ip = btn.getAttribute('data-ip');
              if (ip) window.copyToClipboard(ip, 'آدرس IP کپی شد');
            };
          });
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
          if (list) list.innerHTML = `<div class="p-4 text-center text-rose-400">${escapeHtml(res?.error || 'خطا در دریافت لیست')}</div>`;
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
                  timeHtml = `<div class="flex items-center gap-1.5 mt-1 text-[10px] t-muted font-mono justify-start" dir="rtl"><span class="text-xs">⏱</span><span dir="ltr">${toEnglishDigits(timeStr)} - ${toEnglishDigits(dateStr)}</span></div>`;
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
                    <button type="button" dir="ltr" class="font-mono text-cyan-700 dark:text-cyan-400 font-bold select-all hover:underline cursor-pointer flex items-center gap-1 btn-copy-hwid-ip" data-ip="${escapeHtml(ip)}" title="کپی آی‌پی">
                      <span>${escapeHtml(ip)}</span>
                      <span class="text-[10px] opacity-70">📋</span>
                    </button>
                  </div>
                  <div class="flex items-center gap-1.5 mt-1">
                    <span class="text-[10px] text-slate-400">HWID:</span>
                    <span dir="ltr" class="font-mono text-[10px] text-slate-300 bg-transparent px-2 py-0.5 rounded-lg border border-slate-700/60 truncate max-w-[170px]" title="${escapeHtml(hwid)}">${escapeHtml(hwid)}</span>
                  </div>
                  ${timeHtml}
                </div>
                <button type="button" class="btn-del-hwid bg-transparent hover:bg-rose-500/10 text-rose-400 border border-rose-500/30 hover:border-rose-400 p-2.5 rounded-xl transition active:scale-95 flex items-center justify-center flex-shrink-0" data-tid="${telegram_id}" data-hwid="${escapeHtml(hwid)}" title="قطع اتصال این دستگاه">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                </button>
              </div>
            `;
          }).join('');

          list.querySelectorAll('.btn-del-hwid').forEach(btn => {
            btn.onclick = () => {
              const tid = btn.getAttribute('data-tid');
              const hw = btn.getAttribute('data-hwid');
              if (tid && hw) window.adminActions.deleteHwid(tid, hw);
            };
          });
          list.querySelectorAll('.btn-copy-hwid-ip').forEach(btn => {
            btn.onclick = () => {
              const ip = btn.getAttribute('data-ip');
              if (ip) window.copyToClipboard(ip, 'آدرس IP کپی شد');
            };
          });
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
          if (list) list.innerHTML = `<div class="p-4 text-center text-rose-400 text-xs">${escapeHtml(res?.error || 'خطا در دریافت اطلاعات اتصالات')}</div>`;
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
            <span class="text-[11px] text-slate-400">کاربر در حال حاضر به هیچ سروری متصل نیست.</span>
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
            <button type="button" dir="ltr" class="btn-copy-ip-direct font-mono text-cyan-700 dark:text-cyan-400 font-bold select-all hover:underline cursor-pointer flex items-center gap-1" data-ip="${escapeHtml(ip)}" title="کلیک جهت کپی آی‌پی">
              <span>${escapeHtml(ip)}</span>
              <span class="text-[10px] opacity-70">📋</span>
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
              <span class="text-[10px] card-inset text-cyan-700 dark:text-cyan-300 border border-cyan-500/40 px-2 py-0.5 rounded-lg font-mono font-bold">
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
          if (window.syncAdminOverview) window.syncAdminOverview();
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

// --- Create User Modal ---
    _usernameCheckTimer: null,

    async openCreateUserModal() {
      const modal = $('createUserModal');
      if (modal) modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('impact');

      // Reset form
      const telegramIdInput = $('createUserTelegramId');
      const usernameInput = $('createUserUsername');
      const usernameStatus = $('createUserUsernameStatus');
      const selectedIdEl = $('createUserSelectedPlanId');
      const iconEl = $('createUserPlanIcon');
      const labelEl = $('createUserPlanLabel');
      const trafficInput = $('createUserTraffic');
      const durationInput = $('createUserDuration');
      const hwidInput = $('createUserHwid');
      const squadSelect = $('createUserSquadSelect');

      if (telegramIdInput) telegramIdInput.value = '';
      if (usernameInput) usernameInput.value = '';
      if (usernameStatus) {
        usernameStatus.className = 'text-[10px] font-medium hidden';
        usernameStatus.innerText = '';
      }
      if (selectedIdEl) selectedIdEl.value = 'custom';
      if (iconEl) iconEl.innerText = '⚙️';
      if (labelEl) labelEl.innerText = 'تنظیمات سفارشی (دستی)';
      if (trafficInput) trafficInput.value = '50';
      if (durationInput) durationInput.value = '30';
      if (hwidInput) hwidInput.value = '';

      // Pre-fetch plans so they are readily available in picker
      if (window.api && window.api.getAdminPlans) {
        try {
          const res = await window.api.getAdminPlans();
          if (res && res.ok && Array.isArray(res.plans)) {
            if (window.adminData) window.adminData.plans = res.plans;
          }
        } catch (e) {
          console.error('Failed to pre-fetch plans for create user modal', e);
        }
      }

      // Initialize internal squad selector
      if (squadSelect) squadSelect.value = '';
      if ($('createUserSquadLabel')) $('createUserSquadLabel').innerText = 'پیش‌فرض فروشگاه / بدون اسکواد اختصاصی';
      if ($('createUserSquadIcon')) $('createUserSquadIcon').innerText = '🌐';

      // Pre-fetch internal squads
      if (window.api && window.api.getAdminInternalSquads) {
        try {
          const res = await window.api.getAdminInternalSquads();
          if (res && res.ok && Array.isArray(res.squads)) {
            window._adminInternalSquads = res.squads;
          }
        } catch (e) {
          console.error('Failed to load internal squads', e);
        }
      }
    },

    closeCreateUserModal() {
      const modal = $('createUserModal');
      if (modal) modal.classList.add('hidden');
    },

    onUsernameInput(val) {
      if (this._usernameCheckTimer) clearTimeout(this._usernameCheckTimer);
      const statusEl = $('createUserUsernameStatus');
      if (!statusEl) return;

      const trimmed = (val || '').trim();
      if (!trimmed) {
        statusEl.className = 'text-[10px] font-medium hidden';
        statusEl.innerText = '';
        return;
      }

      if (trimmed.length < 3) {
        statusEl.className = 'text-[10px] font-medium text-amber-400 block mt-1';
        statusEl.innerText = '⚠️ حداقل ۳ کاراکتر انگلیسی وارد کنید';
        return;
      }

      if (!/^[a-zA-Z0-9_-]{3,32}$/.test(trimmed)) {
        statusEl.className = 'text-[10px] font-medium text-rose-400 block mt-1';
        statusEl.innerText = '✕ فقط حروف انگلیسی، اعداد، _ و - مجاز است';
        return;
      }

      statusEl.className = 'text-[10px] font-medium text-slate-400 block mt-1';
      statusEl.innerText = 'در حال بررسی نام کاربری در پنل...';

      this._usernameCheckTimer = setTimeout(async () => {
        try {
          const res = await window.api.checkAdminUsername(trimmed);
          if (res && res.ok) {
            if (res.available) {
              statusEl.className = 'text-[10px] font-medium text-emerald-400 block mt-1';
              statusEl.innerText = '✓ این نام کاربری آزاد است';
            } else {
              statusEl.className = 'text-[10px] font-medium text-rose-400 block mt-1';
              statusEl.innerText = res.error || '✕ این نام کاربری قبلاً در پنل ثبت شده است';
            }
          }
        } catch (e) {
          console.error('Check username error:', e);
        }
      }, 300);
    },

    async openPlanPickerModal() {
      const modal = $('planPickerModal');
      const list = $('planPickerList');
      if (!modal || !list) return;

      modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('selection');

      // Ensure plans are loaded
      let plans = window.adminData && window.adminData.plans ? window.adminData.plans : [];
      if (!plans.length && window.api && window.api.getAdminPlans) {
        try {
          const res = await window.api.getAdminPlans();
          if (res && res.ok && Array.isArray(res.plans)) {
            plans = res.plans;
            if (window.adminData) window.adminData.plans = plans;
          }
        } catch (e) {
          console.error('Failed to load plans for plan picker modal', e);
        }
      }

      // Filter ONLY complete packages (traffic_gb > 0 && duration_days > 0)
      const completePlans = plans.filter(p => p.is_active !== false && p.traffic_gb > 0 && p.duration_days > 0);
      const selectedId = $('createUserSelectedPlanId')?.value || 'custom';

      let html = `
        <div onclick="window.adminActions.selectCreateUserPlan('custom')" class="p-3 rounded-2xl border transition cursor-pointer flex items-center justify-between gap-3 ${selectedId === 'custom' ? 'bg-blue-600/15 border-blue-500 shadow-sm' : 'card-inset hover:border-slate-500/50'}">
          <div class="flex items-center gap-3 min-w-0">
            <div class="w-9 h-9 rounded-xl bg-blue-500/15 text-blue-400 border border-blue-500/30 flex items-center justify-center font-bold text-base shrink-0">
              ⚙️
            </div>
            <div class="min-w-0">
              <span class="font-bold t-main text-xs block">تنظیمات سفارشی (دستی)</span>
              <span class="text-[10px] t-muted block mt-0.5">تعیین دستی حجم، روز و محدودیت دلخواه</span>
            </div>
          </div>
          <div class="shrink-0 text-blue-400 text-sm font-bold">${selectedId === 'custom' ? '✓' : ''}</div>
        </div>
      `;

      if (completePlans.length === 0) {
        html += `
          <div class="p-4 text-center text-slate-400 text-xs">
            بسته کاملی تعریف نشده است.
          </div>
        `;
      } else {
        html += completePlans.map(p => {
          const isSelected = String(selectedId) === String(p.id);
          const trafficLabel = fmtTraffic(p.traffic_gb, { html: false });
          const badgeHtml = p.badge ? `<span class="px-1.5 py-0.5 text-[9.5px] rounded border border-blue-500/40 text-blue-500 dark:text-blue-400 font-bold">${escapeHtml(p.badge)}</span>` : '';
          const priceLabel = p.price ? (typeof fmtMoney === 'function' ? fmtMoney(p.price) : `${p.price} تومان`) : '';

          return `
            <div onclick="window.adminActions.selectCreateUserPlan('${p.id}')" class="p-3 rounded-2xl border transition cursor-pointer flex items-center justify-between gap-3 ${isSelected ? 'bg-blue-600/15 border-blue-500 shadow-sm' : 'card-inset hover:border-slate-500/50'}">
              <div class="flex items-center gap-3 min-w-0 flex-1">
                <div class="w-9 h-9 rounded-xl bg-blue-500/15 text-blue-400 border border-blue-500/30 flex items-center justify-center font-bold text-base shrink-0">
                  📦
                </div>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-1.5 flex-wrap">
                    <span class="font-bold t-main text-xs truncate">${escapeHtml(p.name)}</span>
                    ${badgeHtml}
                  </div>
                  <div class="flex items-center gap-2 text-[10px] t-muted mt-0.5 font-mono">
                    <span class="text-cyan-600 dark:text-cyan-300 font-bold">${trafficLabel}</span>
                    <span>•</span>
                    <span class="text-amber-600 dark:text-amber-300 font-bold">${p.duration_days} روز</span>
                    ${priceLabel ? `<span>•</span> <span class="t-muted font-sans">${escapeHtml(priceLabel)}</span>` : ''}
                  </div>
                </div>
              </div>
              <div class="shrink-0 text-blue-400 text-sm font-bold">${isSelected ? '✓' : ''}</div>
            </div>
          `;
        }).join('');
      }

      list.innerHTML = html;
    },

    closePlanPickerModal() {
      const modal = $('planPickerModal');
      if (modal) modal.classList.add('hidden');
    },

    async openSquadPickerModal() {
      const modal = $('squadPickerModal');
      const list = $('squadPickerList');
      if (!modal || !list) return;

      modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('selection');

      const currentVal = $('createUserSquadSelect')?.value || '';

      list.innerHTML = '<div class="p-4 text-center t-muted text-xs">در حال بارگذاری اسکوادها...</div>';

      let squads = window._adminInternalSquads || [];
      if (!squads.length && window.api && window.api.getAdminInternalSquads) {
        try {
          const res = await window.api.getAdminInternalSquads();
          if (res && res.ok && Array.isArray(res.squads)) {
            squads = res.squads;
            window._adminInternalSquads = squads;
          }
        } catch (e) {
          console.error('Failed to load squads for picker', e);
        }
      }

      let html = `
        <div onclick="window.adminActions.selectCreateUserSquad('', 'پیش‌فرض فروشگاه / بدون اسکواد اختصاصی', '🌐')" class="p-3 rounded-2xl border transition cursor-pointer flex items-center justify-between gap-3 ${currentVal === '' ? 'bg-blue-600/15 border-blue-500 shadow-sm' : 'card-inset hover:border-slate-500/50'}">
          <div class="flex items-center gap-2.5 min-w-0">
            <span class="text-base">🌐</span>
            <span class="text-xs font-bold ${currentVal === '' ? 't-info' : 't-main'}">پیش‌فرض فروشگاه / بدون اسکواد اختصاصی</span>
          </div>
          <span class="text-xs font-bold t-info">${currentVal === '' ? '✓' : ''}</span>
        </div>
      `;

      squads.forEach(sq => {
        const sqId = sq.uuid || sq.id;
        const sqName = sq.name || sq.uuid || 'Squad';
        const isSelected = String(currentVal) === String(sqId);
        html += `
          <div onclick="window.adminActions.selectCreateUserSquad('${escapeHtml(sqId)}', '${escapeHtml(sqName)}', '🧩')" class="p-3 rounded-2xl border transition cursor-pointer flex items-center justify-between gap-3 ${isSelected ? 'bg-blue-600/15 border-blue-500 shadow-sm' : 'card-inset hover:border-slate-500/50'}">
            <div class="flex items-center gap-2.5 min-w-0">
              <span class="text-base">🧩</span>
              <span class="text-xs font-bold ${isSelected ? 't-info' : 't-main'}">${escapeHtml(sqName)}</span>
            </div>
            <span class="text-xs font-bold t-info">${isSelected ? '✓' : ''}</span>
          </div>
        `;
      });

      list.innerHTML = html;
    },

    closeSquadPickerModal() {
      $('squadPickerModal')?.classList.add('hidden');
    },

    selectCreateUserSquad(uuid, name, icon = '🧩') {
      const input = $('createUserSquadSelect');
      const label = $('createUserSquadLabel');
      const iconEl = $('createUserSquadIcon');
      if (input) input.value = uuid;
      if (label) label.innerText = name;
      if (iconEl) iconEl.innerText = icon;
      this.closeSquadPickerModal();
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    selectCreateUserPlan(planId) {
      this.closePlanPickerModal();
      if (window.hapticFeedback) window.hapticFeedback('selection');

      const selectedIdEl = $('createUserSelectedPlanId');
      const iconEl = $('createUserPlanIcon');
      const labelEl = $('createUserPlanLabel');
      const trafficInput = $('createUserTraffic');
      const durationInput = $('createUserDuration');
      const hwidInput = $('createUserHwid');
      const squadSelect = $('createUserSquadSelect');

      if (selectedIdEl) selectedIdEl.value = planId;

      if (planId === 'custom') {
        if (iconEl) iconEl.innerText = '⚙️';
        if (labelEl) labelEl.innerText = 'تنظیمات سفارشی (دستی)';
        return;
      }

      const plans = (window.adminData && window.adminData.plans) || [];
      const plan = plans.find(p => String(p.id) === String(planId));
      if (!plan) return;

      const trafficLabel = fmtTraffic(plan.traffic_gb, { html: false });
      if (iconEl) iconEl.innerText = '📦';
      if (labelEl) labelEl.innerText = `${plan.name} (${trafficLabel} - ${plan.duration_days} روز)`;
      if (trafficInput) trafficInput.value = plan.traffic_gb || 0;
      if (durationInput) durationInput.value = plan.duration_days || 30;
      if (hwidInput) hwidInput.value = plan.hwid_limit || '';

      if (plan.squad_uuid) {
        if (squadSelect) squadSelect.value = plan.squad_uuid;
        const squads = window._adminInternalSquads || [];
        const sq = squads.find(s => (s.uuid || s.id) === plan.squad_uuid);
        if ($('createUserSquadLabel')) $('createUserSquadLabel').innerText = sq ? (sq.name || sq.uuid) : 'اسکواد بسته انتخابی';
        if ($('createUserSquadIcon')) $('createUserSquadIcon').innerText = '🧩';
      }
    },

    onPlanSelectChange() {
      // Legacy fallback
    },

    async submitCreateUser() {
      const telegramIdInput = $('createUserTelegramId');
      const usernameInput = $('createUserUsername');
      const trafficInput = $('createUserTraffic');
      const durationInput = $('createUserDuration');
      const hwidInput = $('createUserHwid');
      const squadSelect = $('createUserSquadSelect');
      const submitBtn = $('createUserSubmitBtn');

      const telegram_id = (telegramIdInput ? telegramIdInput.value : '').trim();
      if (!telegram_id) {
        if (window.showToast) window.showToast('شناسه عددی تلگرام الزامی است.', 'error');
        if (telegramIdInput) telegramIdInput.focus();
        return;
      }

      const username = (usernameInput ? usernameInput.value : '').trim();
      const traffic_gb = trafficInput ? parseFloat(trafficInput.value) || 0 : 0;
      const duration_days = durationInput ? parseInt(durationInput.value, 10) || 30 : 30;
      const hwid_limit = hwidInput && hwidInput.value.trim() ? parseInt(hwidInput.value.trim(), 10) : null;
      const squad_uuid = squadSelect && squadSelect.value ? squadSelect.value.trim() : null;

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.classList.add('opacity-50', 'pointer-events-none');
      }

      try {
        const res = await window.api.createAdminUser({
          telegram_id: parseInt(telegram_id, 10),
          username: username || undefined,
          traffic_gb,
          duration_days,
          hwid_limit,
          squad_uuids: squad_uuid ? [squad_uuid] : undefined,
        });

        if (res && res.ok) {
          if (window.showToast) window.showToast(res.message || 'کاربر با موفقیت ایجاد شد.', 'success');
          this.closeCreateUserModal();
          // Reload users list
          if (this.loadUsers) this.loadUsers(1);
        } else {
          if (window.showToast) window.showToast((res && res.error) || 'خطا در ایجاد کاربر', 'error');
        }
      } catch (err) {
        console.error('submitCreateUser error:', err);
        if (window.showToast) window.showToast('خطای ارتباط با سرور', 'error');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.classList.remove('opacity-50', 'pointer-events-none');
        }
      }
    },

// --- Users Bulk Actions Modal ---
    currentBulkActionType: 'add_traffic',

    openBulkUsersModal() {
      const modal = $('bulkUsersModal');
      if (modal) modal.classList.remove('hidden');
      this.setBulkActionType('add_traffic');
      this.onBulkTargetChange('all_active');
      const valInput = $('bulkAmountInput');
      if (valInput) valInput.value = '5';
      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    closeBulkUsersModal() {
      const modal = $('bulkUsersModal');
      if (modal) modal.classList.add('hidden');
    },

    onBulkTargetChange(target = 'all_active') {
      const hiddenInput = $('bulkTargetSelect');
      if (hiddenInput) hiddenInput.value = target;

      const activeCard = $('bulkTargetCard_active');
      const allCard = $('bulkTargetCard_all');

      if (target === 'all_active') {
        if (activeCard) {
          activeCard.className = 'p-2.5 rounded-xl border border-blue-500 bg-blue-500/10 cursor-pointer flex flex-col items-center text-center gap-1 transition';
        }
        if (allCard) {
          allCard.className = 'p-2.5 rounded-xl border border-slate-700/80 card-inset cursor-pointer flex flex-col items-center text-center gap-1 transition hover:border-slate-500/50';
        }
      } else {
        if (activeCard) {
          activeCard.className = 'p-2.5 rounded-xl border border-slate-700/80 card-inset cursor-pointer flex flex-col items-center text-center gap-1 transition hover:border-slate-500/50';
        }
        if (allCard) {
          allCard.className = 'p-2.5 rounded-xl border border-blue-500 bg-blue-500/10 cursor-pointer flex flex-col items-center text-center gap-1 transition';
        }
      }

      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    setBulkActionType(type = 'add_traffic') {
      this.currentBulkActionType = type;
      const trafficBtn = $('bulkTypeBtn_traffic');
      const daysBtn = $('bulkTypeBtn_days');
      const labelEl = $('bulkAmountLabel');
      const inputEl = $('bulkAmountInput');

      const activeClass = 'py-2 rounded-xl font-bold bg-blue-600 text-white shadow-md text-center flex items-center justify-center gap-1.5 transition active:scale-95';
      const inactiveClass = 'py-2 rounded-xl font-semibold t-muted hover:t-main hover:bg-slate-500/10 text-center flex items-center justify-center gap-1.5 transition active:scale-95';

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
          if (window.syncAdminOverview) window.syncAdminOverview(true);
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
    }
  });

  // Global exports
  window.fetchAdminUsers = fetchAdminUsers;
})(window);
