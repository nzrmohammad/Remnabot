/**
 * RemnaAdmin Pro - Nodes & Infrastructure Module (admin_nodes.js)
 * Node health, telemetry, ping monitoring, custom SSL domains and node billing.
 */
(function (window) {
  'use strict';

  const $ = id => document.getElementById(id);
  const api = window.api;
  const tg = window.Telegram?.WebApp;
  const formatNumber = window.formatNumber || (n => String(n));
  const getFlagEmoji = window.getFlagEmoji || (() => '🌐');
  const formatSpeed = window.formatSpeed || (n => String(n));
  const formatDateToJalali = window.formatDateToJalali || (d => d);
  window.adminActions = window.adminActions || {};

  let currentEditSslDomainTarget = null;
  let currentDeleteSslDomainTarget = null;

  // Collapsible Accordion Node Card Renderer
  function renderOverviewNodes(nodes) {
    const container = $('adminOverviewNodesList') || $('adminNodesFullList');
    if (!container) return;
    if (!nodes || nodes.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <img src="/static/img/icons/nodes.svg?v=fl2" class="empty-state-icon" width="40" height="40" alt="" />
          <span class="empty-state-title">هیچ نودی یافت نشد</span>
          <span class="empty-state-desc">ارتباط با کلاستر رمنانو برقرار است اما نودی ثبت نشده است.</span>
        </div>
      `;
      return;
    }

    container.innerHTML = nodes.map((n, idx) => {
      const flag = n.flag || getFlagEmoji(n.country_code);
      const isOnline = (n.status || '').toUpperCase() === 'ONLINE';
      const statusColor = isOnline ? 't-success' : 't-danger';
      const statusBadge = typeof renderNodeStatusBadge === 'function'
        ? renderNodeStatusBadge(isOnline)
        : (isOnline
          ? '<span class="relative flex items-center justify-center w-3 h-3" title="آنلاین"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span><span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span></span>'
          : '<span class="inline-flex items-center gap-1 text-[11px] font-bold bg-transparent t-danger border border-rose-500/30 px-2 py-0.5 rounded-lg"><span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>آفلاین</span>');

      const cpuText = (n.cpu_percent && n.cpu_percent > 0) ? `CPU: ${n.cpu_percent}%` : null;
      const ramText = (n.ram_percent && n.ram_percent > 0) ? `RAM: ${n.ram_percent}%` : null;
      const dlSpeed = Number(n.download_speed || 0);
      const ulSpeed = Number(n.upload_speed || 0);
      const speedText = (dlSpeed > 0 || ulSpeed > 0) ? `↓${formatSpeed(dlSpeed)} ↑${formatSpeed(ulSpeed)}` : null;
      const specs = [cpuText, ramText, speedText].filter(Boolean).join(' | ');

      return `
        <div class="card rounded-2xl border border-card-border overflow-hidden transition shadow-sm">
          <!-- Accordion Header -->
          <div class="p-3 flex justify-between items-center cursor-pointer hover:bg-slate-500/10 transition select-none" onclick="window.toggleNodeAccordion(${idx})">
            <div class="flex items-center gap-2.5">
              <span class="text-xl flex-shrink-0">${typeof renderFlagHtml === 'function' ? renderFlagHtml(flag, 'w-5 h-3.5 inline-block rounded-xs shadow-xs object-cover align-middle') : flag}</span>
              <div>
                <span class="font-bold t-main block text-xs">${escapeHtml(n.name || 'Node')}</span>
                ${specs ? `<span class="text-[11px] t-muted font-sans">${specs}</span>` : ''}
              </div>
            </div>
            <div class="flex items-center gap-2">
              <span class="${statusColor} font-bold text-[11px] font-sans">${formatNumber(n.connected_users || 0)} آنلاین</span>
              <span id="nodeChevron_${idx}" class="text-xs t-muted transition-transform duration-200">▼</span>
            </div>
          </div>

          <!-- Accordion Details Body -->
          <div id="nodeBody_${idx}" class="hidden p-3 card-inset border-t border-card-border text-xs space-y-2 rounded-none">
            <div class="grid grid-cols-2 gap-2 text-[11px]">
              <div class="card p-2 rounded-xl">
                <span class="t-muted text-[11px] block mb-0.5">آدرس سرور:</span>
                <span class="font-sans t-accent text-xs block truncate" dir="ltr">${escapeHtml(n.address || '—')}</span>
              </div>
              <div class="card p-2 rounded-xl">
                <span class="t-muted text-[11px] block mb-0.5">وضعیت اتصال:</span>
                <span>${statusBadge}</span>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-2 text-[11px]">
              <div class="card p-2 rounded-xl">
                <span class="t-muted text-[11px] block mb-0.5">کاربران متصل زنده:</span>
                <b class="t-success font-sans text-xs">${formatNumber(n.connected_users || 0)} نفر</b>
              </div>
              <div class="card p-2 rounded-xl">
                <span class="t-muted text-[11px] block mb-0.5">ترافیک مصرفی نود:</span>
                <b class="t-accent font-sans text-xs num-bidi" dir="ltr">${n.traffic_used_gb ? fmtTraffic(n.traffic_used_gb, { html: false }) : '—'}</b>
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
    if (!container) return false;
    try {
      const res = await window.api.getSslHealth();
      if (res && res.ok && Array.isArray(res.data)) {
        cachedSslHealthItems = res.data;
        renderSslHealth(cachedSslHealthItems);
        return true;
      } else {
        container.innerHTML = '<div class="p-3 text-center text-xs t-danger">خطا در دریافت وضعیت گواهی‌های SSL</div>';
        return false;
      }
    } catch (err) {
      console.error('SSL Health fetch error:', err);
      container.innerHTML = '<div class="p-3 text-center text-xs t-danger">عدم برقراری ارتباط با سرور</div>';
      return false;
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
        badgeHtml = '<span class="text-[11px] text-slate-400 font-sans">IP سرور</span>';
      } else if (item.valid) {
        if (item.status === 'ok') {
          badgeHtml = `<span class="text-[11px] font-bold t-success">معتبر (${item.days_left} روز)</span>`;
        } else if (item.status === 'warning') {
          badgeHtml = `<span class="text-[11px] font-bold t-warn">هشدار (${item.days_left} روز)</span>`;
        } else if (item.status === 'critical') {
          badgeHtml = `<span class="text-[11px] font-bold t-danger animate-pulse">فوری (${item.days_left} روز)</span>`;
        } else {
          badgeHtml = `<span class="text-[11px] font-bold t-danger">منقضی شده</span>`;
        }
      } else {
        badgeHtml = `<span class="text-[11px] font-bold t-danger">خطا / قطع</span>`;
      }

      let statusDotHtml = '';
      if (item.is_ip) {
        statusDotHtml = '<span class="w-2 h-2 rounded-full bg-slate-500 flex-shrink-0" title="IP سرور"></span>';
      } else if (item.valid) {
        if (item.status === 'ok') {
          statusDotHtml = '<span class="relative flex items-center justify-center w-2.5 h-2.5 flex-shrink-0" title="معتبر"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span><span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span></span>';
        } else if (item.status === 'warning') {
          statusDotHtml = '<span class="relative flex items-center justify-center w-2.5 h-2.5 flex-shrink-0" title="هشدار انقضا"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span><span class="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span></span>';
        } else {
          statusDotHtml = '<span class="relative flex items-center justify-center w-2.5 h-2.5 flex-shrink-0" title="انقضا فوری"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span><span class="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span></span>';
        }
      } else {
        statusDotHtml = '<span class="relative flex items-center justify-center w-2.5 h-2.5 flex-shrink-0" title="خطا / قطع"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span><span class="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span></span>';
      }

      const editBtnHtml = item.is_custom
        ? `<button type="button" data-domain="${escapeHtml(item.domain)}" class="btn-edit-ssl-domain p-1.5 rounded-xl bg-transparent hover:bg-cyan-500/15 t-accent hover:text-cyan-300 border border-slate-700/70 hover:border-cyan-500/40 transition active:scale-95 flex-shrink-0 flex items-center justify-center" title="ویرایش دامنه">
             <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
           </button>`
        : '';

      const deleteBtnHtml = item.is_custom
        ? `<button type="button" data-domain="${escapeHtml(item.domain)}" class="btn-del-ssl-domain p-1.5 rounded-xl bg-transparent hover:bg-rose-500/15 t-danger hover:text-rose-300 border border-slate-700/70 hover:border-rose-500/30 transition active:scale-95 flex-shrink-0 flex items-center justify-center" title="حذف دامنه">
             <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
           </button>`
        : '';

      let detailsHtml = '';
      if (item.is_ip) {
        detailsHtml = `
          <div class="text-[11px] text-slate-500">
            <span>آدرس IP مستقیم (بدون گواهی SSL دامنه)</span>
          </div>`;
      } else if (item.valid) {
        detailsHtml = `
          <div class="space-y-1 text-slate-300 text-xs">
            <div class="flex items-center gap-1.5">
              <span class="text-slate-400">مرجع :</span>
              <span class="font-medium text-slate-200">${escapeHtml(item.issuer || 'نامشخص')}</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="text-slate-400">تاریخ انقضا :</span>
              <span class="font-sans text-slate-200" dir="ltr">${expiryDateFa}</span>
            </div>
          </div>`;
      } else {
        detailsHtml = `
          <div class="text-xs t-danger/90 leading-relaxed">
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
              ${statusDotHtml}
              <span class="font-sans text-xs font-semibold text-slate-100 select-all break-all leading-normal" title="${escapeHtml(item.domain)}">${escapeHtml(item.domain)}</span>
            </div>
          </div>

          <!-- Row 2: Right = Issuer & Jalali Expiration (زیر هم), Left = Actions (Edit, Delete) -->
          <div class="flex items-end justify-between pt-2 border-t border-slate-800/80 gap-2">
            ${detailsHtml}
            <div class="flex items-center gap-1.5 flex-shrink-0">
              ${editBtnHtml}
              ${deleteBtnHtml}
            </div>
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
      const statusBorder = isOnline ? 'border-emerald-500/30 t-success' : 'border-rose-500/30 t-danger';

      const cpu = Number(n.cpu_percent || 0);
      const ram = Number(n.ram_percent || 0);
      const dlSpeed = Number(n.download_speed || 0);
      const ulSpeed = Number(n.upload_speed || 0);

      const cpuBarColor = cpu > 85 ? 'bg-rose-500' : (cpu > 60 ? 'bg-amber-500' : 'bg-cyan-500');
      const ramBarColor = ram > 85 ? 'bg-rose-500' : (ram > 60 ? 'bg-amber-500' : 'bg-indigo-500');
      const isOverloaded = isOnline && (cpu > 85 || ram > 85);

      const cpuDisplay = isOnline ? (cpu > 0 ? (cpu % 1 === 0 ? cpu : cpu.toFixed(1)) + '%' : '< 1%') : 'آفلاین';
      const ramDisplay = isOnline ? (ram > 0 ? (ram % 1 === 0 ? ram : ram.toFixed(1)) + '%' : '< 1%') : 'آفلاین';

      const shamsiDate = n.due_date_jalali || n.due_date;
      let dueBadgeHtml = '<span class="t-subtle font-medium">ثبت‌نشده</span>';
      if (n.days_until_due !== null && n.days_until_due !== undefined) {
        if (n.days_until_due < 0) {
          dueBadgeHtml = `<span class="t-danger font-bold font-sans">منقضی (${Math.abs(n.days_until_due)} روز پیش)</span>`;
        } else if (n.days_until_due === 0) {
          dueBadgeHtml = `<span class="t-danger font-bold animate-pulse font-sans">سررسید امروز!</span>`;
        } else if (n.days_until_due <= 3) {
          dueBadgeHtml = `<span class="t-warn font-bold font-sans">${toEnglishDigits(n.days_until_due)} روز تا تمدید</span>`;
        } else {
          dueBadgeHtml = `<span class="t-main font-bold font-sans">${toEnglishDigits(n.days_until_due)} روز مانده</span>`;
        }
      }

      const usdRate = Number(window.currentUsdRate) > 0 ? Number(window.currentUsdRate) : 95000;
      const eurRate = Number(window.currentEurRate) > 0 ? Number(window.currentEurRate) : 105000;
      const rawForeign = Number(n.monthly_cost_eur || 0);
      const costToman = Number(n.monthly_cost_toman || 0);
      const nodeCurr = String(n.currency || 'EUR').toUpperCase();
      let usdCost = 0;
      let eurCost = 0;
      if (nodeCurr === 'USD') {
        usdCost = rawForeign;
        eurCost = rawForeign > 0
          ? ((costToman > 0 ? costToman : rawForeign * usdRate) / eurRate)
          : (costToman > 0 ? (costToman / eurRate) : 0);
      } else {
        eurCost = rawForeign;
        usdCost = rawForeign > 0
          ? ((costToman > 0 ? costToman : rawForeign * eurRate) / usdRate)
          : (costToman > 0 ? (costToman / usdRate) : 0);
      }
      const fmtFx = (v) => toEnglishDigits(Number(Number(v).toFixed(2)));

      const boxId = `nodeBox_${n.id || idx}`;

      return `
        <div class="node-card settings-box bg-slate-800/90 rounded-2xl border ${isOverloaded ? 'border-rose-500/80 shadow-[0_0_15px_rgba(244,63,94,0.3)] animate-heartbeat' : 'border-slate-700/80'} shadow-md relative overflow-hidden transition-all">
          <!-- Top Accent Light -->
          <div class="absolute top-0 right-0 left-0 h-[2px] ${isOnline ? 'bg-gradient-to-r from-emerald-500/0 via-emerald-400/50 to-emerald-500/0' : 'bg-gradient-to-r from-rose-500/0 via-rose-500/40 to-rose-500/0'}"></div>

          <!-- Header: Flag, Name, Status & Chevron (Clickable) -->
          <div class="node-header p-3.5 flex justify-between items-center cursor-pointer select-none hover:bg-slate-500/10 transition active:scale-[0.99]" onclick="window.adminActions.toggleSettingsBox('${boxId}')">
            <!-- Right: Flag and Server Name -->
            <div class="flex items-center gap-2.5 min-w-0">
              <span class="text-2xl flex-shrink-0 filter drop-shadow">${typeof renderFlagHtml === 'function' ? renderFlagHtml(flag, 'w-6 h-4 inline-block rounded-xs shadow-xs object-cover align-middle') : flag}</span>
              <h4 class="font-bold text-xs text-white truncate">${escapeHtml(n.name || 'Server Node')}</h4>
              ${n.is_disabled ? '<span class="badge badge-danger text-[10px] shrink-0">غیرفعال</span>' : ''}
            </div>

            <!-- Left: Online Status + Speeds + Renewal Alert + Chevron Arrow -->
            <div class="flex items-center gap-2 flex-shrink-0">
              ${(n.days_until_due !== null && n.days_until_due <= 3) ? `
                <span class="relative inline-flex items-center justify-center w-6 h-6 rounded-full ${n.days_until_due <= 0 ? 'bg-rose-500/15 border border-rose-500/40 text-rose-400' : 'bg-amber-500/15 border border-amber-500/40 text-amber-400'}" title="${n.days_until_due <= 0 ? 'سررسید پرداخت!' : 'سررسید تا ' + n.days_until_due + ' روز آینده'}" aria-label="هشدار سررسید">
                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full ${n.days_until_due <= 0 ? 'bg-rose-400' : 'bg-amber-400'} opacity-45"></span>
                  ${uiIcon('clock', 'relative w-3.5 h-3.5')}
                </span>
              ` : ''}
              ${isOnline && (dlSpeed > 0 || ulSpeed > 0) ? `
                <div class="hidden sm:flex items-center gap-1.5 text-[11px] font-sans text-slate-300 bg-slate-900/60 px-2 py-0.5 rounded-xl border border-slate-700/60" dir="ltr">
                  <span class="t-success font-bold">↓${formatSpeed(dlSpeed)}</span>
                  <span class="text-slate-600">|</span>
                  <span class="text-indigo-400 font-bold">↑${formatSpeed(ulSpeed)}</span>
                </div>
              ` : ''}
              ${typeof renderNodeStatusBadge === 'function' ? renderNodeStatusBadge(isOnline) : (isOnline ? '<span class="relative flex items-center justify-center w-3 h-3" title="آنلاین"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span><span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span></span>' : '<span class="badge badge-danger font-sans flex items-center gap-1 text-[11px]"><span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span><span>آفلاین</span></span>')}
              <svg class="settings-box-chevron node-chevron w-4 h-4 text-slate-400 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
              </svg>
            </div>
          </div>

          <!-- Collapsible Body Details (Hidden by default, expands on click) -->
          <div id="${boxId}" class="node-body p-3.5 pt-2 border-t border-slate-700/60 space-y-3 hidden">
            <!-- Server Host Address Strip -->
            <div class="bg-transparent px-3 py-2 rounded-xl border border-slate-700/60 flex items-center justify-between text-xs">
              <span class="text-[11px] text-slate-400 flex items-center gap-1.5">
                <svg class="w-3.5 h-3.5 t-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"/></svg>
                <span>آدرس سرور:</span>
              </span>
              <span class="font-sans text-blue-600 dark:text-cyan-300 text-xs font-semibold truncate max-w-[210px] select-all" dir="ltr" title="${n.address || '—'}">${n.address || '—'}</span>
            </div>

            <!-- Real-time Speeds: Download & Upload -->
            <div class="grid grid-cols-2 gap-2 text-center text-[11px]">
              <div class="bg-transparent p-2.5 rounded-xl border border-slate-700/60">
                <div class="flex items-center justify-between text-[11px] mb-1">
                  <span class="text-slate-400 flex items-center gap-1">
                    <svg class="w-3 h-3 t-success" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7m0 0l-7-7m7 7V3"/></svg>
                    <span>سرعت دانلود (DL):</span>
                  </span>
                  <span class="text-[11px] text-slate-500 font-sans">RX</span>
                </div>
                <b class="t-success font-sans text-xs block text-left" dir="ltr">↓ ${formatSpeed(dlSpeed)}</b>
              </div>
              <div class="bg-transparent p-2.5 rounded-xl border border-slate-700/60">
                <div class="flex items-center justify-between text-[11px] mb-1">
                  <span class="text-slate-400 flex items-center gap-1">
                    <svg class="w-3 h-3 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18"/></svg>
                    <span>سرعت آپلود (UL):</span>
                  </span>
                  <span class="text-[11px] text-slate-500 font-sans">TX</span>
                </div>
                <b class="text-indigo-400 font-sans text-xs block text-left" dir="ltr">↑ ${formatSpeed(ulSpeed)}</b>
              </div>
            </div>

            <!-- System Resource Gauges (CPU & RAM Progress Bars) -->
            <div class="space-y-2 bg-transparent p-2.5 rounded-xl border border-slate-700/50">
              <!-- CPU Progress -->
              <div class="space-y-1">
                <div class="flex justify-between items-center text-[11px]">
                  <span class="text-slate-400">پردازنده (CPU):</span>
                  <span class="font-sans font-bold ${cpu > 80 ? 't-danger' : 'text-slate-100'}">${cpuDisplay}</span>
                </div>
                <div class="w-full h-1.5 bg-slate-700/60 rounded-full overflow-hidden">
                  <div class="h-full ${cpuBarColor} ${cpu > 80 ? 'shimmer-bar' : ''} transition-all duration-500" style="width: ${Math.min(100, Math.max(0, isOnline ? (cpu > 0 ? cpu : 1) : 0))}%"></div>
                </div>
              </div>

              <!-- RAM Progress -->
              <div class="space-y-1">
                <div class="flex justify-between items-center text-[11px]">
                  <span class="text-slate-400">حافظه رم (RAM):</span>
                  <span class="font-sans font-bold ${ram > 80 ? 't-danger' : 'text-slate-100'}">${ramDisplay}</span>
                </div>
                <div class="w-full h-1.5 bg-slate-700/60 rounded-full overflow-hidden">
                  <div class="h-full ${ramBarColor} ${ram > 80 ? 'shimmer-bar' : ''} transition-all duration-500" style="width: ${Math.min(100, Math.max(0, isOnline ? (ram > 0 ? ram : 1) : 0))}%"></div>
                </div>
              </div>
            </div>

            <!-- Bottom Metrics: Connected users & Traffic -->
            <div class="grid grid-cols-2 gap-2 text-center text-[11px]">
              <div class="bg-transparent p-2 rounded-xl border border-card-border">
                <span class="t-muted block mb-0.5">کاربران متصل</span>
                <b class="t-success font-sans text-xs">${formatNumber(n.connected_users || 0)} نفر</b>
              </div>
              <div class="bg-transparent p-2 rounded-xl border border-card-border">
                <span class="t-muted block mb-0.5">ترافیک مصرفی نود</span>
                <b class="t-accent font-sans text-xs num-bidi" dir="ltr">${fmtTraffic(n.traffic_used_gb || 0, { html: false })}</b>
              </div>
            </div>

            <!-- Infra-Billing & Server Cost Details Strip -->
            <div class="bg-transparent p-2.5 rounded-xl border border-card-border space-y-2 text-[11px]">
              <div class="space-y-1.5">
                <div class="flex items-center justify-between">
                  <span class="t-muted flex items-center gap-1">
                    <svg class="w-3.5 h-3.5 t-success shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"/></svg>
                    <span>هزینه ماهانه سرور:</span>
                  </span>
                  <div class="flex items-center gap-1 font-bold">
                    ${costToman ? `
                      <span class="font-sans t-success num-bidi" dir="ltr">${formatNumber(costToman)}</span>
                      <span class="text-[11px] t-muted font-sans font-medium">تومان</span>
                    ` : '<span class="t-subtle font-medium">ثبت‌نشده</span>'}
                  </div>
                </div>
                ${usdCost > 0 ? `
                  <div class="flex items-center justify-between text-[11px]">
                    <span class="t-muted flex items-center gap-1">
                      <svg class="w-3.5 h-3.5 t-info shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                      <span>هزینه ارزی سرویس:</span>
                    </span>
                    <span class="inline-flex items-center gap-1 font-sans font-bold t-info">
                      <span class="num-bidi" dir="ltr">${fmtFx(usdCost)}</span>
                      <span class="text-[10.5px] t-muted font-medium">دلار</span>
                    </span>
                  </div>
                ` : ''}
                ${eurCost > 0 ? `
                  <div class="flex items-center justify-between text-[11px]">
                    <span class="t-muted flex items-center gap-1">
                      <svg class="w-3.5 h-3.5 t-accent shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.121 15.536c-1.171 1.952-3.07 1.952-4.242 0-1.172-1.953-1.172-5.119 0-7.072 1.171-1.952 3.07-1.952 4.242 0M8 10.5h4m-4 3h4m9-1.5a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                      <span>هزینه یورویی سرور:</span>
                    </span>
                    <span class="inline-flex items-center gap-1 font-sans font-bold t-accent">
                      <span class="num-bidi" dir="ltr">${fmtFx(eurCost)}</span>
                      <span class="text-[10.5px] t-muted font-medium">یورو</span>
                    </span>
                  </div>
                ` : ''}
              </div>

              <div class="flex items-center justify-between">
                <span class="text-slate-400 flex items-center gap-1">
                  <img src="/static/img/icons/calendar.svg?v=fl2" class="ui-icon-img w-3.5 h-3.5 shrink-0" alt="" />
                  <span>موعد سررسید تمدید:</span>
                </span>
                <div>${dueBadgeHtml}</div>
              </div>

              <div class="space-y-1.5 pt-1.5 border-t border-card-border text-[11px]">
                <div class="flex items-center justify-between gap-2 min-w-0">
                  <span class="t-muted flex items-center gap-1 shrink-0">
                    ${uiIcon('desktop', 'w-3.5 h-3.5 t-muted shrink-0')}
                    <span>ارائه‌دهنده:</span>
                  </span>
                  <b class="t-main font-semibold truncate text-left">${n.provider || 'ثبت‌نشده'}</b>
                </div>
                <div class="flex items-center justify-between gap-2 min-w-0">
                  <span class="t-muted flex items-center gap-1 shrink-0">
                    ${uiIcon('coins', 'w-3.5 h-3.5 t-warn shrink-0')}
                    <span>قیمت تمام‌شده به ازای هر گیگ:</span>
                  </span>
                  <b class="t-main font-bold shrink-0">
                    ${n.cost_per_gb ? `
                      <span class="font-sans num-bidi" dir="ltr">${formatNumber(n.cost_per_gb)}</span>
                      <span class="text-[11px] t-muted font-sans font-medium">تومان</span>
                    ` : '—'}
                  </b>
                </div>
              </div>

              <!-- Panel Config, Versions & Multipliers Summary -->
              <div class="space-y-1.5 pt-1.5 border-t border-card-border text-[11px]">
                <div class="flex items-center justify-between gap-2">
                  <span class="t-muted flex items-center gap-1.5">
                    <span>🧩</span>
                    <span>ورژن هسته (Xray):</span>
                  </span>
                  <b class="t-accent font-sans num-bidi font-bold" dir="ltr">${n.xray_version ? escapeHtml(String(n.xray_version)) : '—'}</b>
                </div>
                <div class="flex items-center justify-between gap-2">
                  <span class="t-muted flex items-center gap-1.5">
                    <span>⚙️</span>
                    <span>ورژن نود:</span>
                  </span>
                  <b class="t-main font-sans num-bidi font-bold" dir="ltr">${n.node_version ? escapeHtml(String(n.node_version)) : '—'}</b>
                </div>
                ${(n.consumption_multiplier != null || n.node_consumption_multiplier != null || n.is_traffic_tracking_active != null) ? `
                  <div class="flex items-center justify-between gap-2">
                    <span class="t-muted flex items-center gap-1.5">
                      <span>👤</span>
                      <span>ضریب مصرف کاربر:</span>
                    </span>
                    <b class="t-info font-sans num-bidi font-bold" dir="ltr">${n.consumption_multiplier ?? 1}x</b>
                  </div>
                  <div class="flex items-center justify-between gap-2">
                    <span class="t-muted flex items-center gap-1.5">
                      <span>🖥️</span>
                      <span>ضریب مصرف سرور:</span>
                    </span>
                    <b class="t-purple font-sans num-bidi font-bold" dir="ltr">${n.node_consumption_multiplier ?? 1}x</b>
                  </div>
                  <div class="flex items-center justify-between gap-2">
                    <span class="t-muted flex items-center gap-1.5">
                      <span>📊</span>
                      <span>ردیابی ترافیک:</span>
                    </span>
                    <b class="font-sans font-bold ${n.is_traffic_tracking_active === true ? 't-success' : 't-muted'}">
                      ${n.is_traffic_tracking_active === true
                        ? (n.traffic_limit_gb > 0 ? `فعال (${fmtTraffic(n.traffic_limit_gb)})` : 'فعال')
                        : 'غیرفعال'}
                    </b>
                  </div>
                ` : ''}
                ${n.description ? `
                  <div class="flex items-center justify-between gap-2 min-w-0">
                    <span class="t-muted shrink-0">توضیحات پنل:</span>
                    <span class="t-main truncate text-left">${escapeHtml(n.description)}</span>
                  </div>
                ` : ''}
              </div>

              <!-- Node Profit / Loss & Estimated Revenue Strip -->
              <div class="space-y-1.5 pt-1.5 border-t border-card-border text-[11px]">
                <div class="flex items-center justify-between gap-2">
                  <span class="t-muted flex items-center gap-1 shrink-0">
                    ${uiIcon('finance', 'w-3.5 h-3.5 t-accent shrink-0')}
                    <span>درآمد تخمینی نود:</span>
                  </span>
                  <b class="t-main font-bold font-sans shrink-0">
                    ${n.est_revenue_toman ? `<span class="num-bidi" dir="ltr">${formatNumber(n.est_revenue_toman)}</span> <span class="text-[11px] t-muted font-sans font-medium">تومان</span>` : '0 <span class="text-[11px] t-muted font-sans font-medium">تومان</span>'}
                  </b>
                </div>
                <div class="flex items-center justify-between gap-2">
                  <span class="t-muted flex items-center gap-1 shrink-0">
                    ${uiIcon('reports', `w-3.5 h-3.5 ${n.is_profitable ? 't-success' : 't-danger'} shrink-0`)}
                    <span>سود/زیان خالص:</span>
                  </span>
                  <b class="${n.is_profitable ? 't-success' : 't-danger'} font-bold font-sans shrink-0">
                    <span class="inline-flex items-center gap-1">
                      <span dir="ltr" class="num-bidi">${(n.net_profit_toman || 0) > 0 ? '+' : ''}${formatNumber(n.net_profit_toman || 0)}</span>
                      <span class="text-[11px] t-muted font-sans font-medium">تومان</span>
                    </span>
                  </b>
                </div>
              </div>

              <!-- Buttons to configure node, restart, toggle & reset traffic -->
              <div class="pt-1 grid grid-cols-2 gap-1.5">
                <button type="button" class="btn-node-billing bg-transparent hover:bg-cyan-500/10 t-accent py-1.5 px-2 rounded-xl border border-cyan-500/30 transition flex items-center justify-center gap-1.5 font-bold active:scale-95 shadow-sm min-w-0"
                  data-uuid="${escapeHtml(n.uuid || n.id || '')}"
                  data-name="${escapeHtml(n.name || '')}"
                  data-provider="${escapeHtml(n.provider || '')}"
                  data-provider-uuid="${escapeHtml(n.provider_uuid || '')}"
                  data-description="${escapeHtml(n.description || '')}"
                  data-tracking-active="${n.is_traffic_tracking_active === true ? '1' : (n.is_traffic_tracking_active === false ? '0' : '')}"
                  data-user-multiplier="${n.consumption_multiplier != null ? Number(n.consumption_multiplier) : ''}"
                  data-node-multiplier="${n.node_consumption_multiplier != null ? Number(n.node_consumption_multiplier) : ''}"
                  data-traffic-limit-gb="${n.traffic_limit_gb != null ? Number(n.traffic_limit_gb) : ''}"
                  data-traffic-reset-day="${n.traffic_reset_day != null ? Number(n.traffic_reset_day) : ''}"
                  data-notify-percent="${n.notify_percent != null ? Number(n.notify_percent) : ''}"
                  data-config-profile-uuid="${escapeHtml(n.active_config_profile_uuid || '')}"
                  data-active-inbounds="${escapeHtml((n.active_inbounds || []).join(','))}"
                  data-cost-toman="${Number(n.monthly_cost_toman || 0)}"
                  data-cost-eur="${Number(n.monthly_cost_eur || 0)}"
                  data-due="${escapeHtml(n.due_date || '')}"
                  data-notes="${escapeHtml(n.notes || '')}"
                  data-flag="${escapeHtml(flag || '')}"
                  data-currency="${escapeHtml(n.currency || 'EUR')}">
                  <svg class="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                  <span class="truncate">تنظیمات سرور</span>
                </button>
                <button type="button" class="btn-restart-node bg-transparent hover:bg-amber-500/10 t-warn py-1.5 px-2 rounded-xl border border-amber-500/35 transition flex items-center justify-center gap-1.5 font-bold active:scale-95 shadow-sm min-w-0"
                  data-uuid="${escapeHtml(n.uuid || n.id || '')}"
                  data-name="${escapeHtml(n.name || '')}"
                  title="ریستارت سرور">
                  <svg class="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                  <span class="truncate">ریستارت</span>
                </button>
                <button type="button" class="btn-toggle-node-state bg-transparent ${n.is_disabled ? 'hover:bg-emerald-500/10 t-success border-emerald-500/35' : 'hover:bg-rose-500/10 t-danger border-rose-500/35'} py-1.5 px-2 rounded-xl border transition flex items-center justify-center gap-1.5 font-bold active:scale-95 shadow-sm min-w-0"
                  data-uuid="${escapeHtml(n.uuid || n.id || '')}"
                  data-name="${escapeHtml(n.name || '')}"
                  data-disabled="${n.is_disabled ? '1' : '0'}"
                  title="${n.is_disabled ? 'فعال‌سازی سرور' : 'غیرفعال کردن سرور'}">
                  <svg class="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5.636 5.636a9 9 0 1012.728 0M12 3v9"/></svg>
                  <span class="truncate">${n.is_disabled ? 'فعال‌سازی' : 'غیرفعال'}</span>
                </button>
                <button type="button" class="btn-reset-node-traffic bg-transparent hover:bg-indigo-500/10 t-info py-1.5 px-2 rounded-xl border border-indigo-500/35 transition flex items-center justify-center gap-1.5 font-bold active:scale-95 shadow-sm min-w-0"
                  data-uuid="${escapeHtml(n.uuid || n.id || '')}"
                  data-name="${escapeHtml(n.name || '')}"
                  title="ریست ترافیک مصرفی سرور">
                  <img src="/static/img/icons/trash.svg?v=fl2" class="ui-icon-img w-3.5 h-3.5 shrink-0" alt="" />
                  <span class="truncate">ریست ترافیک</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }


  // SSL Domain & Node Billing Actions
  Object.assign(window.adminActions, {
openEditSslDomainModal(domain) {
      if (!domain) return;
      currentEditSslDomainTarget = domain;
      const curEl = $('editSslDomainCurrent');
      const inpEl = $('editSslDomainNewInput');
      if (curEl) curEl.innerText = domain;
      if (inpEl) {
        inpEl.value = domain;
        setTimeout(() => inpEl.focus(), 100);
      }
      const modal = $('editSslDomainModal');
      if (modal) modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    closeEditSslDomainModal() {
      const modal = $('editSslDomainModal');
      if (modal) modal.classList.add('hidden');
      currentEditSslDomainTarget = null;
    },

    async executeEditSslDomain() {
      if (!currentEditSslDomainTarget) return;
      const inpEl = $('editSslDomainNewInput');
      const newDomain = inpEl?.value?.trim()?.toLowerCase();
      if (!newDomain) {
        if (window.showToast) window.showToast('لطفاً آدرس جدید دامنه را وارد کنید.');
        return;
      }
      if (newDomain === currentEditSslDomainTarget.toLowerCase()) {
        this.closeEditSslDomainModal();
        return;
      }

      const btn = $('confirmEditSslDomainBtn');
      if (btn) {
        btn.disabled = true;
        btn.innerText = 'در حال ذخیره...';
      }
      try {
        if (window.hapticFeedback) window.hapticFeedback('impact');
        const delRes = await window.api.deleteCustomSslDomain(currentEditSslDomainTarget);
        if (delRes && delRes.ok) {
          const addRes = await window.api.addCustomSslDomain(newDomain);
          if (addRes && addRes.ok) {
            this.closeEditSslDomainModal();
            if (window.showToast) window.showToast('دامنه با موفقیت ویرایش شد');
            if (window.hapticFeedback) window.hapticFeedback('success');
            if (typeof fetchAdminSslHealth === 'function') fetchAdminSslHealth();
          } else {
            if (window.showToast) window.showToast(addRes?.error || 'خطا در ثبت دامنه جدید');
            if (typeof fetchAdminSslHealth === 'function') fetchAdminSslHealth();
          }
        } else {
          if (window.showToast) window.showToast(delRes?.error || 'خطا در ویرایش دامنه');
        }
      } catch (err) {
        console.error('Edit SSL domain error:', err);
        if (window.showToast) window.showToast('خطا در برقراری ارتباط');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerText = 'ذخیره تغییرات';
        }
      }
    },

    editSslDomain(domain) {
      this.openEditSslDomainModal(domain);
    },

    openDeleteSslDomainModal(domain) {
      if (!domain) return;
      currentDeleteSslDomainTarget = domain;
      const targetEl = $('deleteSslDomainTarget');
      if (targetEl) targetEl.innerText = domain;
      const modal = $('deleteSslDomainModal');
      if (modal) modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('warning');
    },

    closeDeleteSslDomainModal() {
      const modal = $('deleteSslDomainModal');
      if (modal) modal.classList.add('hidden');
      currentDeleteSslDomainTarget = null;
    },

    async executeDeleteSslDomain() {
      if (!currentDeleteSslDomainTarget) return;
      const domain = currentDeleteSslDomainTarget;
      const btn = $('confirmDeleteSslDomainBtn');
      if (btn) {
        btn.disabled = true;
        btn.innerText = 'در حال حذف...';
      }
      try {
        if (window.hapticFeedback) window.hapticFeedback('impact');
        const res = await window.api.deleteCustomSslDomain(domain);
        if (res && res.ok) {
          this.closeDeleteSslDomainModal();
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
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg><span>حذف دامنه</span>`;
        }
      }
    },

    deleteSslDomain(domain) {
      this.openDeleteSslDomainModal(domain);
    },

// --- Node Infra-Billing & Panel Config Actions ---
    switchNodeBillingTab(tabKey = 'finance') {
      const tabs = ['finance', 'panel'];
      const activeCls = 'h-8 rounded-xl text-[11px] font-bold transition bg-cyan-600 text-white shadow flex items-center justify-center gap-1.5';
      const inactiveCls = 'h-8 rounded-xl text-[11px] font-medium transition t-muted hover:t-main flex items-center justify-center gap-1.5';
      tabs.forEach(k => {
        const btn = $(`nodeBillingTabBtn_${k}`);
        const pane = $(`nodeBillingTabPane_${k}`);
        const isActive = k === tabKey;
        if (btn) btn.className = isActive ? activeCls : inactiveCls;
        if (pane) pane.classList.toggle('hidden', !isActive);
      });
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    toggleNodeTrafficTrackingOptions() {
      const enabled = Boolean($('nodeBillingTrafficTracking')?.checked);
      const box = $('nodeTrafficTrackingOptions');
      if (box) box.classList.toggle('hidden', !enabled);
    },

    _applySelectedNodeProvider(uuidVal = '', fallbackName = '') {
      const providers = Array.isArray(this._cachedInfraProviders) ? this._cachedInfraProviders : [];
      const uuidInput = $('nodeBillingProviderUuid');
      const dispEl = $('nodeBillingProviderDisplay');
      const customWrap = $('nodeBillingProviderCustomWrap');
      const customInput = $('nodeBillingProvider');

      const cleanUuid = String(uuidVal || '').trim();
      const cleanName = String(fallbackName || '').trim();
      const matchByUuid = cleanUuid && cleanUuid !== '__custom__'
        ? providers.find(p => String(p.uuid) === cleanUuid)
        : null;
      const matchByName = !matchByUuid && cleanUuid !== '__custom__' && cleanName
        ? providers.find(p => String(p.name || '').trim().toLowerCase() === cleanName.toLowerCase())
        : null;

      if (matchByUuid || matchByName) {
        const hit = matchByUuid || matchByName;
        if (uuidInput) uuidInput.value = hit.uuid;
        if (dispEl) dispEl.innerText = hit.name;
        if (customWrap) customWrap.classList.add('hidden');
        if (customInput) customInput.value = hit.name;
      } else if (cleanUuid === '__custom__' || cleanName) {
        if (uuidInput) uuidInput.value = '__custom__';
        if (dispEl) dispEl.innerText = cleanName || 'سایر / وارد کردن دستی';
        if (customWrap) customWrap.classList.remove('hidden');
        if (customInput && cleanName) customInput.value = cleanName;
      } else {
        if (uuidInput) uuidInput.value = '';
        if (dispEl) dispEl.innerText = 'بدون ارائه‌دهنده';
        if (customWrap) customWrap.classList.add('hidden');
        if (customInput) customInput.value = '';
      }
    },

    _renderNodeProviderList() {
      const listEl = $('nodeProviderPickerList');
      if (!listEl) return;
      const providers = Array.isArray(this._cachedInfraProviders) ? this._cachedInfraProviders : [];
      const currentVal = $('nodeBillingProviderUuid')?.value || '';
      const row = (val, title, sub = '', isEnglish = false) => renderModalPickerRow({
        onClick: `window.adminActions.selectNodeProvider('${escapeHtml(val)}', '${escapeHtml(title)}')`,
        title,
        sub,
        selected: currentVal === val,
        isEnglish,
        rowDir: '',
        extraRowCls: isEnglish ? 'flex-row-reverse text-left' : 'text-right',
      });

      let html = row('', 'بدون ارائه‌دهنده', '', false);
      for (const p of providers) {
        html += row(p.uuid, p.name, p.login || '', true);
      }
      html += row('__custom__', 'سایر / وارد کردن دستی...', '', false);
      listEl.innerHTML = html;
    },

    openAddProviderFromPicker() {
      if (window.panelCtrl?.openProviderModal) {
        window.panelCtrl.openProviderModal('', async (prov) => {
          this._cachedInfraProviders = null;
          await this.loadInfraProviders(prov?.uuid || '', prov?.name || '');
          this._renderNodeProviderList();
        });
      }
    },

    async openNodeProviderModal() {
      const modal = $('nodeProviderPickerModal');
      if (!modal) return;
      modal.classList.remove('hidden');
      this._renderNodeProviderList();
      if (!Array.isArray(this._cachedInfraProviders)) {
        await this.loadInfraProviders($('nodeBillingProviderUuid')?.value || '', $('nodeBillingProvider')?.value || '');
        this._renderNodeProviderList();
      }
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    closeNodeProviderModal() {
      const modal = $('nodeProviderPickerModal');
      if (modal) modal.classList.add('hidden');
    },

    selectNodeProvider(uuidVal = '', label = '') {
      this._applySelectedNodeProvider(uuidVal, uuidVal === '__custom__' ? ($('nodeBillingProvider')?.value || '') : label);
      this.closeNodeProviderModal();
      if (uuidVal === '__custom__') {
        setTimeout(() => $('nodeBillingProvider')?.focus(), 60);
      }
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    async loadInfraProviders(selectedUuid = '', fallbackName = '') {
      this._applySelectedNodeProvider(selectedUuid, fallbackName);
      if (Array.isArray(this._cachedInfraProviders)) return;

      try {
        const res = await window.api?.getInfraProviders?.();
        if (res && res.ok && Array.isArray(res.providers)) {
          this._cachedInfraProviders = res.providers;
          this._applySelectedNodeProvider(selectedUuid, fallbackName);
        }
      } catch (err) {
        console.warn('Could not load panel infra providers:', err);
      }
    },

    _applySelectedNodeConfigProfile(profileUuid = '') {
      const hiddenEl = $('nodeBillingConfigProfileSelect');
      const dispEl = $('nodeBillingConfigProfileDisplay');
      if (hiddenEl) hiddenEl.value = profileUuid || '';
      const profiles = this._nodeConfigProfilesCache || window.panelCtrl?.getConfigProfiles?.() || [];
      const hit = profileUuid ? profiles.find(p => String(p.uuid) === String(profileUuid)) : null;
      if (dispEl) {
        if (hit) {
          dispEl.innerText = hit.name || hit.uuid;
          dispEl.setAttribute('dir', 'ltr');
        } else {
          dispEl.innerText = 'بدون تغییر پروفایل';
          dispEl.setAttribute('dir', 'rtl');
        }
      }
    },

    _renderNodeConfigProfileList() {
      const listEl = $('nodeConfigProfilePickerList');
      if (!listEl) return;
      const profiles = this._nodeConfigProfilesCache || window.panelCtrl?.getConfigProfiles?.() || [];
      const currentVal = $('nodeBillingConfigProfileSelect')?.value || '';
      const row = (val, title, sub = '', isEnglish = true) => renderModalPickerRow({
        onClick: `window.adminActions.selectNodeConfigProfile('${escapeHtml(val)}')`,
        title,
        sub,
        selected: String(currentVal) === String(val),
        isEnglish,
        rowDir: 'ltr',
        subDir: 'rtl',
      });

      let html = row('', 'بدون تغییر پروفایل', 'حفظ تنظیمات فعلی نود در پنل', false);
      for (const prof of profiles) {
        const cnt = Array.isArray(prof.inbounds) ? prof.inbounds.length : 0;
        html += row(prof.uuid, prof.name || prof.uuid, `${cnt} اینباند`, true);
      }
      listEl.innerHTML = html;
    },

    async openNodeConfigProfileModal() {
      const modal = $('nodeConfigProfilePickerModal');
      if (!modal) return;
      modal.classList.remove('hidden');
      this._renderNodeConfigProfileList();
      if (!(this._nodeConfigProfilesCache || []).length) {
        await this.loadNodeConfigProfiles($('nodeBillingConfigProfileSelect')?.value || '');
        this._renderNodeConfigProfileList();
      }
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    closeNodeConfigProfileModal() {
      const modal = $('nodeConfigProfilePickerModal');
      if (modal) modal.classList.add('hidden');
    },

    selectNodeConfigProfile(profileUuid = '') {
      this._applySelectedNodeConfigProfile(profileUuid);
      this.onNodeConfigProfileChange([]);
      this.closeNodeConfigProfileModal();
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    async loadNodeConfigProfiles(selectedProfileUuid = '', selectedInbounds = []) {
      const sel = $('nodeBillingConfigProfileSelect');
      if (!sel) return;
      let profiles = window.panelCtrl?.getConfigProfiles?.() || [];
      if (!profiles.length && window.panelCtrl?.fetchOverview) {
        const data = await window.panelCtrl.fetchOverview(false);
        profiles = data?.config_profiles || [];
      }
      this._nodeConfigProfilesCache = profiles;
      this._applySelectedNodeConfigProfile(selectedProfileUuid || '');
      this._renderNodeConfigProfileList();
      this.onNodeConfigProfileChange(selectedInbounds);
    },

    onNodeConfigProfileChange(preselectedInbounds = null) {
      const sel = $('nodeBillingConfigProfileSelect');
      const wrap = $('nodeBillingInboundsWrap');
      if (!sel || !wrap) return;
      const profileUuid = sel.value;
      const profiles = this._nodeConfigProfilesCache || window.panelCtrl?.getConfigProfiles?.() || [];
      const prof = profiles.find(p => String(p.uuid) === String(profileUuid));
      const inbounds = Array.isArray(prof?.inbounds) ? prof.inbounds : [];
      if (!profileUuid || !inbounds.length) {
        wrap.innerHTML = '';
        wrap.classList.add('hidden');
        return;
      }
      const chosenSet = new Set(
        Array.isArray(preselectedInbounds) && preselectedInbounds.length
          ? preselectedInbounds
          : inbounds.map(i => String(i.uuid || '')).filter(Boolean)
      );
      wrap.innerHTML = inbounds.map(i => {
        const u = String(i.uuid || '');
        const checked = chosenSet.has(u) ? 'checked' : '';
        return `
          <label class="card px-2 py-1 rounded-lg border border-card-border text-[10px] font-en flex items-center gap-1 cursor-pointer">
            <input type="checkbox" class="node-inbound-chk accent-cyan-500 rounded" value="${escapeHtml(u)}" ${checked} />
            <span>${escapeHtml(i.tag || i.type || 'Inbound')}</span>
          </label>
        `;
      }).join('');
      wrap.classList.remove('hidden');
    },

    async syncNodeBillingToPanel() {
      const nodeUuid = $('nodeBillingUuid')?.value?.trim() || '';
      const providerUuid = $('nodeBillingProviderUuid')?.value?.trim() || '';
      const dueDate = $('nodeBillingDueDate')?.value?.trim() || '';
      if (!nodeUuid || !providerUuid || providerUuid === '__custom__') {
        if (window.showToast) window.showToast('ابتدا یک ارائه‌دهنده ثبت‌شده در پنل انتخاب کنید.');
        return;
      }
      const res = await window.api?.syncInfraNodeBilling?.(nodeUuid, providerUuid, dueDate);
      if (res && res.ok) {
        if (window.showToast) window.showToast(`✅ ${res.message}`);
        if (window.hapticFeedback) window.hapticFeedback('success');
      } else {
        if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در همگام‌سازی بیلینگ با پنل'}`);
      }
    },

    toggleNodeEnabledState(nodeUuid, nodeName, isCurrentlyDisabled) {
      if (!nodeUuid) return;
      const run = async () => {
        const action = isCurrentlyDisabled ? 'enable' : 'disable';
        const res = await window.api?.runNodeAction?.(action, nodeUuid, nodeName);
        if (res && res.ok) {
          if (window.showToast) window.showToast(`✅ ${res.message}`);
          if (window.hapticFeedback) window.hapticFeedback('success');
          if (window.syncAdminOverview) window.syncAdminOverview(true);
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در تغییر وضعیت سرور'}`);
        }
      };
      if (isCurrentlyDisabled) {
        run();
      } else if (window.panelCtrl?.confirmAction) {
        window.panelCtrl.confirmAction({
          title: 'غیرفعال کردن سرور',
          message: `آیا سرور «${nodeName || nodeUuid}» در پنل غیرفعال شود؟`,
          btnText: 'غیرفعال شود',
          onConfirm: run,
        });
      }
    },

    resetNodeTrafficWithConfirm(nodeUuid, nodeName) {
      if (!nodeUuid || !window.panelCtrl?.confirmAction) return;
      window.panelCtrl.confirmAction({
        title: 'ریست ترافیک مصرفی سرور',
        message: `آمار ترافیک مصرفی سرور «${nodeName || nodeUuid}» در پنل صفر شود؟`,
        btnText: 'ریست ترافیک',
        onConfirm: async () => {
          const res = await window.api?.runNodeAction?.('reset_traffic', nodeUuid, nodeName);
          if (res && res.ok) {
            if (window.showToast) window.showToast(`✅ ${res.message}`);
            if (window.hapticFeedback) window.hapticFeedback('success');
            if (window.syncAdminOverview) window.syncAdminOverview(true);
          } else {
            if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ریست ترافیک'}`);
          }
        },
      });
    },

    setRestartNodeMode(forceRestart = false) {
      const isForce = Boolean(forceRestart);
      if ($('restartNodeForceToggle')) $('restartNodeForceToggle').checked = isForce;

      const optSoft = $('restartModeOptSoft');
      const optForce = $('restartModeOptForce');
      const dotSoft = $('restartModeDotSoft');
      const dotForce = $('restartModeDotForce');
      const btn = $('confirmRestartNodeBtn');

      if (optSoft) {
        optSoft.className = !isForce
          ? 'w-full text-right p-3 rounded-2xl border border-cyan-500/40 bg-cyan-500/10 transition active:scale-[0.99] space-y-1'
          : 'w-full text-right p-3 rounded-2xl border border-card-border card-inset hover:border-cyan-500/35 transition active:scale-[0.99] space-y-1';
      }
      if (optForce) {
        optForce.className = isForce
          ? 'w-full text-right p-3 rounded-2xl border border-rose-500/45 bg-rose-500/10 transition active:scale-[0.99] space-y-1'
          : 'w-full text-right p-3 rounded-2xl border border-card-border card-inset hover:border-amber-500/40 transition active:scale-[0.99] space-y-1';
      }
      if (dotSoft) {
        dotSoft.className = !isForce
          ? 'w-3.5 h-3.5 rounded-full bg-cyan-500 border-2 border-white shadow shrink-0'
          : 'w-3.5 h-3.5 rounded-full border border-card-border shrink-0';
      }
      if (dotForce) {
        dotForce.className = isForce
          ? 'w-3.5 h-3.5 rounded-full bg-rose-500 border-2 border-white shadow shrink-0'
          : 'w-3.5 h-3.5 rounded-full border border-card-border shrink-0';
      }
      if (btn) {
        btn.innerText = isForce ? 'ریستارت کامل و اجباری' : 'ریستارت نرم Xray';
      }
    },

    openRestartNodeModal(nodeUuid, nodeName = '') {
      const modal = $('restartNodeConfirmModal');
      if (!modal || !nodeUuid) return;
      if ($('restartNodeTargetUuid')) $('restartNodeTargetUuid').value = nodeUuid;
      if ($('restartNodeTargetName')) $('restartNodeTargetName').innerText = nodeName || nodeUuid;
      this.setRestartNodeMode(false);
      modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('warning');
    },

    openRestartNodeFromModal() {
      const uuid = $('nodeBillingUuid')?.value?.trim();
      const name = $('nodeBillingName')?.value?.trim();
      if (!uuid) return;
      this.openRestartNodeModal(uuid, name);
    },

    closeRestartNodeModal() {
      const modal = $('restartNodeConfirmModal');
      if (modal) modal.classList.add('hidden');
    },

    async executeRestartNode() {
      const nodeUuid = $('restartNodeTargetUuid')?.value?.trim();
      const forceRestart = Boolean($('restartNodeForceToggle')?.checked);
      const btn = $('confirmRestartNodeBtn');
      if (!nodeUuid) return;
      if (btn) {
        btn.disabled = true;
        btn.innerText = 'در حال ریستارت...';
      }
      try {
        const res = nodeUuid === '__ALL__'
          ? await window.api?.runNodeAction?.('restart_all', '', 'همه سرورها', forceRestart)
          : await window.api?.restartNode?.(nodeUuid, forceRestart);
        if (res && res.ok) {
          if (window.showToast) window.showToast(`✅ ${res.message || 'سرور با موفقیت ریستارت شد'}`);
          if (window.hapticFeedback) window.hapticFeedback('success');
          this.closeRestartNodeModal();
          if (window.syncAdminOverview) window.syncAdminOverview(true);
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ریستارت سرور'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (err) {
        if (window.showToast) window.showToast('خطای ارتباط در ارسال دستور ریستارت');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerText = forceRestart ? 'ریستارت کامل و اجباری' : 'ریستارت نرم Xray';
        }
      }
    },

    openNodeBillingModal(nodeUuid, nodeName, provider = '', costToman = 0, costEur = 0, dueDate = '', notes = '', flag = '', currency = 'EUR', panelMeta = {}) {
      const modal = $('nodeBillingModal');
      if (!modal) return;
      $('nodeBillingUuid').value = nodeUuid || '';
      $('nodeBillingName').value = nodeName || '';
      if ($('nodeBillingModalTitle')) $('nodeBillingModalTitle').innerText = 'تنظیمات سرور';
      if ($('nodeBillingServerNameLabel')) $('nodeBillingServerNameLabel').innerText = nodeName || 'سرور';
      const flagEl = $('nodeBillingModalFlag');
      if (flagEl) {
        flagEl.innerHTML = flag && flag !== '🖥️'
          ? (typeof renderFlagHtml === 'function' ? renderFlagHtml(flag, 'w-6 h-4 inline-block rounded shadow-xs object-cover align-middle') : flag)
          : uiIcon('desktop', 'w-5 h-5 shrink-0 text-cyan-400 align-middle');
      }
      $('nodeBillingProvider').value = provider || '';
      $('nodeBillingCostToman').value = costToman || '';
      $('nodeBillingCostEur').value = costEur || '';
      $('nodeBillingDueDate').value = dueDate ? dueDate.slice(0, 10) : '';
      $('nodeBillingNotes').value = notes || '';

      const meta = panelMeta || {};
      const userMult = meta.userMultiplier !== undefined && meta.userMultiplier !== '' ? String(meta.userMultiplier) : '';
      const nodeMult = meta.nodeMultiplier !== undefined && meta.nodeMultiplier !== '' ? String(meta.nodeMultiplier) : '';
      const descVal = meta.description || '';
      const trackingStr = String(meta.trackingActive ?? '');
      const trackingBool = trackingStr === '1' || trackingStr === 'true';
      const providerUuid = meta.providerUuid || '';
      const limitGb = meta.trafficLimitGb !== undefined && meta.trafficLimitGb !== '' ? String(meta.trafficLimitGb) : '';
      const resetDay = meta.trafficResetDay !== undefined && meta.trafficResetDay !== '' ? String(meta.trafficResetDay) : '';
      const notifyPct = meta.notifyPercent !== undefined && meta.notifyPercent !== '' ? String(meta.notifyPercent) : '';
      const configProfileUuid = meta.configProfileUuid || '';
      const activeInbounds = String(meta.activeInbounds || '').split(',').map(x => x.trim()).filter(Boolean);

      if ($('nodeBillingUserMultiplier')) $('nodeBillingUserMultiplier').value = userMult;
      if ($('nodeBillingNodeMultiplier')) $('nodeBillingNodeMultiplier').value = nodeMult;
      if ($('nodeBillingPanelDescription')) $('nodeBillingPanelDescription').value = descVal;
      if ($('nodeBillingTrafficTracking')) $('nodeBillingTrafficTracking').checked = trackingBool;
      if ($('nodeBillingTrafficLimitGb')) $('nodeBillingTrafficLimitGb').value = limitGb;
      if ($('nodeBillingTrafficResetDay')) $('nodeBillingTrafficResetDay').value = resetDay;
      if ($('nodeBillingNotifyPercent')) $('nodeBillingNotifyPercent').value = notifyPct;
      this.toggleNodeTrafficTrackingOptions();
      this.switchNodeBillingTab('finance');

      this._nodePanelSnapshot = {
        userMultiplier: userMult,
        nodeMultiplier: nodeMult,
        description: descVal,
        trackingActive: trackingStr === '' ? null : trackingBool,
        providerUuid,
        trafficLimitGb: limitGb,
        trafficResetDay: resetDay,
        notifyPercent: notifyPct,
        configProfileUuid,
        activeInboundsKey: activeInbounds.slice().sort().join(','),
      };
      this.loadInfraProviders(providerUuid, provider);
      this.loadNodeConfigProfiles(configProfileUuid, activeInbounds);

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
        const activeCls = 'flex-1 h-full rounded-lg text-[11px] font-bold transition flex items-center justify-center text-white bg-blue-600 shadow';
        const inactiveCls = 'flex-1 h-full rounded-lg text-[11px] font-medium transition flex items-center justify-center t-muted hover:t-main';
        eurBtn.className = isEur ? activeCls : inactiveCls;
        usdBtn.className = isEur ? inactiveCls : activeCls;
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

    async payAndExtendNodeBilling() {
      const input = $('nodeBillingDueDate');
      const jalaliPreview = $('nodeBillingJalaliPreview');
      if (!input) return;

      const currentVal = input.value?.trim();
      let baseDate = new Date();
      if (currentVal) {
        const parsed = new Date(currentVal + 'T00:00:00');
        if (!isNaN(parsed.getTime())) {
          const now = new Date();
          now.setHours(0, 0, 0, 0);
          if (parsed >= now) {
            baseDate = parsed;
          }
        }
      }
      baseDate.setDate(baseDate.getDate() + 30);
      const yyyy = baseDate.getFullYear();
      const mm = String(baseDate.getMonth() + 1).padStart(2, '0');
      const dd = String(baseDate.getDate()).padStart(2, '0');
      const isoStr = `${yyyy}-${mm}-${dd}`;
      input.value = isoStr;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      if (jalaliPreview) {
        jalaliPreview.innerText = window.formatDateToJalali ? window.formatDateToJalali(isoStr) : isoStr;
      }

      if (window.hapticFeedback) window.hapticFeedback('success');
      if (window.showToast) window.showToast('✅ تمدید 1 ماهه اعمال شد، در حال ثبت...');
      await this.saveNodeBilling();
    },

    switchAdminAppsTab(osKey = 'ios') {
      const osList = ['ios', 'android', 'windows', 'macos', 'linux', 'dns', 'prerequisites'];
      osList.forEach(os => {
        const tabBtn = $(`adminAppTab_${os}`);
        const pane = $(`adminAppsPane_${os}`);
        const isTarget = os === osKey;
        if (tabBtn) {
          if (isTarget) {
            tabBtn.className = 'admin-app-os-tab px-3 py-1.5 rounded-xl font-bold text-xs whitespace-nowrap shrink-0 transition flex items-center justify-center gap-1.5 bg-cyan-600 text-white shadow';
          } else {
            tabBtn.className = 'admin-app-os-tab px-3 py-1.5 rounded-xl font-medium text-xs whitespace-nowrap shrink-0 t-muted hover:text-slate-200 transition flex items-center justify-center gap-1.5';
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
      const selectedProvVal = $('nodeBillingProviderUuid')?.value?.trim() ?? '';
      let provider = $('nodeBillingProvider')?.value?.trim() || '';
      if (selectedProvVal && selectedProvVal !== '__custom__') {
        provider = $('nodeBillingProviderDisplay')?.innerText?.trim() || provider;
      }
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

        const snap = this._nodePanelSnapshot || {};
        const userMultStr = $('nodeBillingUserMultiplier')?.value?.trim() ?? '';
        const nodeMultStr = $('nodeBillingNodeMultiplier')?.value?.trim() ?? '';
        const descVal = $('nodeBillingPanelDescription')?.value?.trim() ?? '';
        const trackingChecked = Boolean($('nodeBillingTrafficTracking')?.checked);
        const limitGbStr = $('nodeBillingTrafficLimitGb')?.value?.trim() ?? '';
        const resetDayStr = $('nodeBillingTrafficResetDay')?.value?.trim() ?? '';
        const notifyPctStr = $('nodeBillingNotifyPercent')?.value?.trim() ?? '';
        const providerUuidVal = selectedProvVal === '__custom__' ? null : (selectedProvVal || null);

        if (userMultStr !== String(snap.userMultiplier ?? '') && userMultStr !== '') {
          payload.consumption_multiplier = parseFloat(userMultStr);
        }
        if (nodeMultStr !== String(snap.nodeMultiplier ?? '') && nodeMultStr !== '') {
          payload.node_consumption_multiplier = parseFloat(nodeMultStr);
        }
        if (descVal !== String(snap.description ?? '')) {
          payload.description = descVal;
        }
        if (snap.trackingActive !== null && trackingChecked !== snap.trackingActive) {
          payload.is_traffic_tracking_active = trackingChecked;
        } else if (snap.trackingActive === null && trackingChecked) {
          payload.is_traffic_tracking_active = true;
        }
        if (limitGbStr !== String(snap.trafficLimitGb ?? '') && limitGbStr !== '') {
          payload.traffic_limit_gb = parseFloat(limitGbStr);
        }
        if (resetDayStr !== String(snap.trafficResetDay ?? '') && resetDayStr !== '') {
          payload.traffic_reset_day = parseInt(resetDayStr, 10);
        }
        if (notifyPctStr !== String(snap.notifyPercent ?? '') && notifyPctStr !== '') {
          payload.notify_percent = parseInt(notifyPctStr, 10);
        }
        if (selectedProvVal !== '__custom__' && (providerUuidVal || '') !== String(snap.providerUuid || '')) {
          payload.provider_uuid = providerUuidVal;
        }
        const cfgProfSel = $('nodeBillingConfigProfileSelect');
        const cfgProfUuid = cfgProfSel?.value?.trim() || '';
        const selectedInbounds = Array.from(document.querySelectorAll('#nodeBillingInboundsWrap .node-inbound-chk:checked'))
          .map(el => el.value)
          .filter(Boolean);
        const inboundsKey = selectedInbounds.slice().sort().join(',');
        if (cfgProfUuid && (cfgProfUuid !== String(snap.configProfileUuid || '') || inboundsKey !== String(snap.activeInboundsKey || ''))) {
          payload.config_profile_uuid = cfgProfUuid;
          payload.active_inbounds = selectedInbounds;
        }

        const res = await window.api.saveNodeCost(payload);
        if (res && res.ok) {
          if (window.showToast) window.showToast('✅ اطلاعات سرور و تنظیمات با موفقیت ثبت شد');
          if (window.hapticFeedback) window.hapticFeedback('success');
          this.closeNodeBillingModal();
          if (window.syncAdminOverview) window.syncAdminOverview(true);
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ذخیره تنظیمات سرور'}`);
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
    }
  });

  $('syncAllNodesBtn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    if (window.syncAdminOverview) window.syncAdminOverview(true);
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
      if (window.syncAdminOverview) await window.syncAdminOverview(true);
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
      const ok = await fetchAdminSslHealth();
      if (ok) {
        if (window.showToast) window.showToast('وضعیت گواهی‌های SSL به‌روزرسانی شد', 'success');
        if (window.hapticFeedback) window.hapticFeedback('success');
      } else {
        if (window.showToast) window.showToast('خطا در دریافت وضعیت گواهی‌های SSL', 'error');
        if (window.hapticFeedback) window.hapticFeedback('error');
      }
    } finally {
      setTimeout(() => {
        if (icon) icon.classList.remove('animate-spin');
      }, 500);
    }
  });

  // Nodes Tab Subtabs Switcher
  window.switchNodesSubtab = function(subtab) {
    const btnServers = $('subtabBtnNodesServers');
    const btnPanel = $('subtabBtnNodesPanel');
    const btnSsl = $('subtabBtnNodesSsl');
    const btnTools = $('subtabBtnNodesTools');
    const contentServers = $('subtabContentNodesServers');
    const contentPanel = $('subtabContentNodesPanel');
    const contentSsl = $('subtabContentNodesSsl');
    const contentTools = $('subtabContentNodesTools');

    if (window.hapticFeedback) window.hapticFeedback('selection');

    btnServers?.classList.toggle('is-active', subtab === 'servers');
    btnServers?.setAttribute('aria-selected', subtab === 'servers' ? 'true' : 'false');
    btnPanel?.classList.toggle('is-active', subtab === 'panel');
    btnPanel?.setAttribute('aria-selected', subtab === 'panel' ? 'true' : 'false');
    btnSsl?.classList.toggle('is-active', subtab === 'ssl');
    btnSsl?.setAttribute('aria-selected', subtab === 'ssl' ? 'true' : 'false');
    btnTools?.classList.toggle('is-active', subtab === 'tools');
    btnTools?.setAttribute('aria-selected', subtab === 'tools' ? 'true' : 'false');

    contentServers?.classList.toggle('hidden', subtab !== 'servers');
    contentPanel?.classList.toggle('hidden', subtab !== 'panel');
    contentSsl?.classList.toggle('hidden', subtab !== 'ssl');
    contentTools?.classList.toggle('hidden', subtab !== 'tools');

    if (subtab === 'ssl') {
      fetchAdminSslHealth();
    } else if (subtab === 'panel') {
      window.panelCtrl?.fetchOverview?.(false);
    }
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


  // --- Network Diagnostics Tools (Check-Host & RIPE Stat) ---
  window.toggleToolsAccordion = function(boxId) {
    const box = $(boxId);
    const chevron = $(boxId + 'Chevron');
    if (!box) return;
    const isClosed = box.classList.contains('hidden');
    box.classList.toggle('hidden', !isClosed);
    if (chevron) {
      chevron.style.transform = isClosed ? 'rotate(180deg)' : 'rotate(0deg)';
    }
    if (window.hapticFeedback) window.hapticFeedback('light');
  };

  window.openCheckHostTypeModal = function() {
    const m = $('checkHostTypeModal');
    if (m) m.classList.remove('hidden');
    if (window.hapticFeedback) window.hapticFeedback('light');
  };

  window.closeCheckHostTypeModal = function() {
    const m = $('checkHostTypeModal');
    if (m) m.classList.add('hidden');
  };

  const CHECK_HOST_TYPE_ICONS = {
    ping: '/static/img/icons/antenna.svg?v=fl2',
    tcp: '/static/img/icons/zap.svg?v=fl2',
    http: '/static/img/icons/globe.svg?v=fl2',
    dns: '/static/img/icons/search.svg?v=fl2',
  };

  window.selectCheckHostType = function(type, label, icon) {
    const input = $('checkHostTypeSelect');
    if (input) input.value = type;
    const disp = $('checkHostTypeDisplay');
    if (disp) {
      const iconSrc = CHECK_HOST_TYPE_ICONS[type] || '/static/img/icons/antenna.svg?v=fl2';
      disp.innerHTML = `<img src="${iconSrc}" class="ui-icon-img w-4 h-4 shrink-0 inline-block align-middle" width="16" height="16" alt="" /><span>${label || type}</span>`;
    }
    window.handleCheckHostTypeChange(type);
    window.closeCheckHostTypeModal();
    if (window.hapticFeedback) window.hapticFeedback('selection');
  };

  window.openCheckHostNodesModal = function() {
    const m = $('checkHostNodesModal');
    if (m) m.classList.remove('hidden');
    if (window.hapticFeedback) window.hapticFeedback('light');
  };

  window.closeCheckHostNodesModal = function() {
    const m = $('checkHostNodesModal');
    if (m) m.classList.add('hidden');
  };

  window.selectCheckHostNodes = function(count, label, icon) {
    const input = $('checkHostMaxNodesSelect');
    if (input) input.value = count;
    const disp = $('checkHostNodesDisplay');
    if (disp) {
      disp.innerHTML = `<img src="/static/img/icons/globe.svg?v=fl2" class="ui-icon-img w-4 h-4 shrink-0 inline-block align-middle" width="16" height="16" alt="" /><span>${label || count + ' نود'}</span>`;
    }
    window.closeCheckHostNodesModal();
    if (window.hapticFeedback) window.hapticFeedback('selection');
  };

  window.handleCheckHostTypeChange = function(type) {
    const portRow = $('checkHostPortRow');
    if (portRow) portRow.classList.toggle('hidden', type !== 'tcp');
  };

  window.runCheckHostTest = async function() {
    const targetInput = $('checkHostTargetInput');
    const target = (targetInput?.value || '').trim();
    if (!target) {
      if (window.showToast) window.showToast('لطفاً آدرس سرور یا دامنه را وارد کنید', 'warning');
      return;
    }
    const type = $('checkHostTypeSelect')?.value || 'ping';
    const port = parseInt($('checkHostPortInput')?.value || '443', 10);
    const maxNodes = parseInt($('checkHostMaxNodesSelect')?.value || '10', 10);

    const btn = $('runCheckHostBtn');
    const btnText = $('runCheckHostBtnText');
    const icon = $('runCheckHostIcon');
    const resBox = $('checkHostResultsBox');
    const resList = $('checkHostResultsList');
    const badge = $('checkHostStatusBadge');

    if (btn) btn.disabled = true;
    if (btnText) btnText.innerText = 'درحال اتصال به Check-Host...';
    if (icon) icon.classList.add('animate-spin');
    if (resBox) resBox.classList.remove('hidden');
    if (resList) resList.innerHTML = '<div class="col-span-2 p-6 text-center t-muted text-xs">در حال ارسال درخواست به نودهای جهانی و دریافت نتایج...</div>';
    if (badge) {
      badge.className = 'badge badge-info';
      badge.innerText = 'درحال بررسی...';
    }

    try {
      const payload = { host: target, check_type: type, max_nodes: maxNodes };
      if (type === 'tcp') payload.port = port;
      const res = await window.api.runCheckHost(payload);
      const esc = typeof window.escapeHtml === 'function' ? window.escapeHtml : (s => String(s ?? ''));
      if (!res || !res.ok) {
        if (badge) {
          badge.className = 'badge badge-danger';
          badge.innerText = 'خطا در ارزیابی';
        }
        if (resList) resList.innerHTML = `<div class="col-span-2 p-4 text-center text-rose-500 font-bold">${esc(res?.message || 'خطا در دریافت نتایج از Check-Host')}</div>`;
        return;
      }

      if (badge) {
        badge.className = 'badge badge-success';
        badge.innerText = `تکمیل شد (${res.results?.length || 0} نود)`;
      }

      if (!res.results || res.results.length === 0) {
        if (resList) resList.innerHTML = '<div class="col-span-2 p-4 text-center t-muted">هیچ نتیجه‌ای بازگردانده نشد.</div>';
        return;
      }

      resList.innerHTML = res.results.map(r => {
        const isOk = r.ok;
        const statusClass = isOk ? 'text-emerald-500 border-emerald-500/30' : 'text-rose-500 border-rose-500/30';
        const pingTime = r.ping_ms !== undefined && r.ping_ms !== null ? `${esc(r.ping_ms)} ms` : esc(r.status || (isOk ? 'OK' : 'عدم دسترسی'));
        return `
          <div class="card-inset p-2 rounded-xl border flex items-center justify-between ${statusClass}" dir="ltr">
            <div class="flex items-center gap-1.5 truncate">
              <span class="text-sm">${esc(r.flag || '🌐')}</span>
              <span class="t-main font-bold truncate">${esc(r.node_name || r.location)}</span>
            </div>
            <span class="font-bold text-xs font-sans">${pingTime}</span>
          </div>
        `;
      }).join('');
    } catch (err) {
      const esc = typeof window.escapeHtml === 'function' ? window.escapeHtml : (s => String(s ?? ''));
      if (resList) resList.innerHTML = `<div class="col-span-2 p-4 text-center text-rose-500 font-bold">خطا: ${esc(err?.message || 'عدم دسترسی به سرور')}</div>`;
    } finally {
      if (btn) btn.disabled = false;
      if (btnText) btnText.innerText = 'شروع بررسی آنلاین';
      if (icon) icon.classList.remove('animate-spin');
    }
  };

  let cachedAsnPrefixes = [];

  window.selectAsnPreset = function(asn) {
    const inp = $('asnNumberInput');
    if (inp) {
      inp.value = asn;
      window.runAsnLookup();
    }
  };

  window.runAsnLookup = async function() {
    const input = $('asnNumberInput');
    let asn = (input?.value || '').trim();
    if (!asn) {
      if (window.showToast) window.showToast('لطفاً شماره ASN را وارد کنید (مثال: AS44244)', 'warning');
      return;
    }
    const cleanAsn = asn.toUpperCase().startsWith('AS') ? asn.toUpperCase().replace('AS', '') : asn;

    const btn = $('runAsnLookupBtn');
    const btnText = $('runAsnLookupBtnText');
    const icon = $('runAsnLookupIcon');
    const resultsBox = $('asnResultsBox');
    const list = $('asnPrefixesList');
    const countBadge = $('asnCountBadge');

    if (btn) btn.disabled = true;
    if (btnText) btnText.innerText = 'در حال استعلام...';
    if (icon) icon.classList.add('animate-spin');
    if (resultsBox) resultsBox.classList.remove('hidden');
    if (list) list.innerHTML = '<div class="col-span-4 p-4 text-center t-muted text-xs">در حال استعلام پیشوندها از RIPE Stat API...</div>';

    const esc = typeof window.escapeHtml === 'function' ? window.escapeHtml : (s => String(s ?? ''));
    try {
      const res = await window.api.getAsnPrefixes(cleanAsn);
      if (!res || !res.ok) {
        if (list) list.innerHTML = `<div class="col-span-4 p-4 text-center text-rose-500 font-bold">${esc(res?.message || 'خطا در استعلام ASN')}</div>`;
        return;
      }
      cachedAsnPrefixes = res.prefixes || [];
      if (countBadge) countBadge.innerHTML = `<span class="num-bidi font-bold font-sans">${cachedAsnPrefixes.length}</span> رنج`;
      renderAsnPrefixes(cachedAsnPrefixes);
      if (window.showToast) window.showToast(`✅ ${cachedAsnPrefixes.length} پیشوند برای AS${cleanAsn} دریافت شد`, 'success');
    } catch (err) {
      if (list) list.innerHTML = `<div class="col-span-4 p-4 text-center text-rose-500 font-bold">خطا: ${esc(err?.message || 'خطای شبکه')}</div>`;
    } finally {
      if (btn) btn.disabled = false;
      if (btnText) btnText.innerText = 'دریافت رنج‌ها';
      if (icon) icon.classList.remove('animate-spin');
    }
  };

  function renderAsnPrefixes(items) {
    const list = $('asnPrefixesList');
    if (!list) return;
    if (!items || items.length === 0) {
      list.innerHTML = '<div class="col-span-4 p-4 text-center t-muted">هیچ پیشوندی یافت نشد.</div>';
      return;
    }
    list.innerHTML = items.map(p => `
      <div class="px-2 py-1 rounded-lg card-inset border border-[var(--card-border)] hover:border-purple-500 t-purple font-bold text-[11px] text-center cursor-pointer select-all active:scale-95 transition" onclick="window.copyToClipboard('${p}', 'پیشوند ${p} کپی شد')">
        ${p}
      </div>
    `).join('');
  }

  window.filterAsnPrefixes = function(val) {
    const q = (val || '').trim().toLowerCase();
    if (!q) {
      renderAsnPrefixes(cachedAsnPrefixes);
      return;
    }
    const filtered = cachedAsnPrefixes.filter(p => p.toLowerCase().includes(q));
    renderAsnPrefixes(filtered);
  };

  window.copyAllAsnPrefixes = function() {
    if (!cachedAsnPrefixes || cachedAsnPrefixes.length === 0) {
      if (window.showToast) window.showToast('رنجی برای کپی وجود ندارد', 'warning');
      return;
    }
    const text = cachedAsnPrefixes.join('\n');
    window.copyToClipboard(text, `✅ ${cachedAsnPrefixes.length} رنج در کلیپ‌بورد کپی شد`);
  };


  // --- System Health & Reconciliation Audit ---
  function renderSystemHealth(h) {
    const box = $('adminSystemHealthBody');
    if (!box || !h) return;
    const esc = typeof window.escapeHtml === 'function' ? window.escapeHtml : (s => String(s ?? ''));
    const dbOk = Boolean(h.db?.ok);
    const redisSt = h.redis?.status || 'disabled';
    const panelOk = Boolean(h.remnawave?.healthy);
    const bkp = h.backup || {};
    const rec = h.reconciliation || {};
    const q = h.queue || {};

    const redisBadge = redisSt === 'connected'
      ? `<span class="t-success font-bold font-sans num-bidi">${h.redis?.latency_ms ?? 0} ms</span>`
      : (redisSt === 'error' ? '<span class="t-danger font-bold">خطا</span>' : '<span class="t-warn font-bold">Memory</span>');

    const bkpSizeStr = bkp.exists
      ? (typeof window.fmtTraffic === 'function'
        ? window.fmtTraffic(Math.round(Number(bkp.size_mb || 0) * 1024 * 1024), { isBytes: true, html: true, persianDigits: false })
        : `<span class="font-sans num-bidi">${bkp.size_mb}</span>`)
      : '';
    const bkpText = bkp.exists
      ? `${bkp.encrypted ? '🔐' : '📦'} ${bkpSizeStr} (${bkp.age_hours}h پیش)`
      : '<span class="t-warn">بکاپ محلی یافت نشد</span>';

    const mismatchItems = Array.isArray(rec.panel_mismatches) ? rec.panel_mismatches : [];
    const mismatchHtml = mismatchItems.length > 0
      ? `<div class="card-inset p-2.5 rounded-xl border border-[var(--card-border)] space-y-1.5">
          <div class="t-danger font-bold text-[11px]">⚠️ مغایرت سفارش‌های پرداخت‌شده با پنل (${mismatchItems.length}):</div>
          ${mismatchItems.slice(0, 5).map(m => `
            <div class="flex items-center justify-between text-[11px]">
              <span class="t-main">#${esc(m.order_id)} • <span class="font-sans" dir="ltr">${esc(m.telegram_id)}</span> (${esc(m.service_name)})</span>
              <span class="t-danger">${esc(m.issue_label)}</span>
            </div>
          `).join('')}
        </div>`
      : '';

    box.innerHTML = `
      <div class="grid grid-cols-2 gap-2 text-[11px]">
        <div class="card-inset p-2.5 rounded-xl flex items-center justify-between">
          <span class="t-muted">دیتابیس:</span>
          <span class="${dbOk ? 't-success' : 't-danger'} font-bold font-sans num-bidi">${dbOk ? `${h.db?.latency_ms ?? 0} ms` : 'خطا'}</span>
        </div>
        <div class="card-inset p-2.5 rounded-xl flex items-center justify-between">
          <span class="t-muted">Redis:</span>
          ${redisBadge}
        </div>
        <div class="card-inset p-2.5 rounded-xl flex items-center justify-between">
          <span class="t-muted">پنل Remnawave:</span>
          <span class="${panelOk ? 't-success' : 't-danger'} font-bold font-sans num-bidi">${panelOk ? `${h.remnawave?.latency_ms ?? 0} ms` : 'قطع'}</span>
        </div>
        <div class="card-inset p-2.5 rounded-xl flex items-center justify-between">
          <span class="t-muted">آخرین بکاپ:</span>
          <span class="t-main font-semibold">${bkpText}</span>
        </div>
      </div>
      <div class="card-inset p-2.5 rounded-xl flex flex-wrap items-center justify-between gap-2 text-[11px]">
        <span>سفارش معلق: <b class="font-sans ${rec.stale_pending_orders > 0 ? 't-warn' : 't-success'}">${rec.stale_pending_orders || 0}</b></span>
        <span>فاکتور منقضی باز: <b class="font-sans">${(rec.stalled_crypto_invoices || 0) + (rec.stalled_card_invoices || 0)}</b></span>
        <span>مغایرت پنل: <b class="font-sans ${rec.panel_mismatches_count > 0 ? 't-danger' : 't-success'}">${rec.panel_mismatches_count || 0}</b></span>
        <span>صف برادکست: <b class="font-sans">${q.in_process_running || 0} فعال / ${q.pending_queue_len || 0} صف</b></span>
      </div>
      ${mismatchHtml}
    `;
  }

  window.toggleSystemHealthAccordion = function(forceOpen = null) {
    const body = $('adminSystemHealthBody');
    const chev = $('systemHealthChevron');
    if (!body) return;
    const willOpen = forceOpen !== null ? Boolean(forceOpen) : body.classList.contains('hidden');
    body.classList.toggle('hidden', !willOpen);
    if (chev) {
      chev.classList.toggle('rotate-180', willOpen);
    }
    if (forceOpen === null) {
      if (window.hapticFeedback) window.hapticFeedback('selection');
      if (willOpen) fetchAdminSystemHealth(true);
    }
  };

  async function fetchAdminSystemHealth(forceRefresh = false) {
    try {
      const res = await window.api?.getSystemHealth?.(forceRefresh);
      if (res && res.ok && res.health) {
        renderSystemHealth(res.health);
        return true;
      }
    } catch (err) {
      console.error('System health fetch error:', err);
    }
    return false;
  }

  window.runAdminReconcile = async function() {
    const btn = $('runAdminReconcileBtn');
    if (btn) btn.disabled = true;
    window.toggleSystemHealthAccordion(true);
    try {
      const res = await window.api?.runAdminReconcile?.();
      if (res && res.ok) {
        if (window.showToast) window.showToast(`✅ ${res.message || 'آشتی خودکار انجام شد'}`);
        await fetchAdminSystemHealth(true);
      } else {
        if (window.showToast) window.showToast(`❌ ${res?.error || 'خطا در اجرای آشتی خودکار'}`);
      }
    } catch (err) {
      if (window.showToast) window.showToast('❌ خطای ارتباط در آشتی خودکار');
    } finally {
      if (btn) btn.disabled = false;
    }
  };

  // Global exports
  window.renderOverviewNodes = renderOverviewNodes;
  window.renderFullNodes = renderFullNodes;
  window.renderSslHealth = renderSslHealth;
  window.fetchAdminSslHealth = fetchAdminSslHealth;
  window.fetchAdminSystemHealth = fetchAdminSystemHealth;
})(window);
