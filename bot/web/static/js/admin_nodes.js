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
    const container = $('adminOverviewNodesList');
    if (!container) return;
    if (!nodes || nodes.length === 0) {
      container.innerHTML = '<div class="p-3 text-center text-slate-400">هیچ نودی یافت نشد</div>';
      return;
    }

    container.innerHTML = nodes.map((n, idx) => {
      const flag = n.flag || getFlagEmoji(n.country_code);
      const isOnline = (n.status || '').toUpperCase() === 'ONLINE';
      const statusColor = isOnline ? 't-success' : 't-danger';
      const statusBadge = isOnline
        ? '<span class="inline-flex items-center gap-1 text-[10px] font-bold bg-transparent t-success border border-emerald-500/30 px-2 py-0.5 rounded-lg"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>آنلاین</span>'
        : '<span class="inline-flex items-center gap-1 text-[10px] font-bold bg-transparent t-danger border border-rose-500/30 px-2 py-0.5 rounded-lg"><span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>آفلاین</span>';

      const cpuText = (n.cpu_percent && n.cpu_percent > 0) ? `CPU: ${n.cpu_percent}%` : null;
      const ramText = (n.ram_percent && n.ram_percent > 0) ? `RAM: ${n.ram_percent}%` : null;
      const dlSpeed = Number(n.download_speed || 0);
      const ulSpeed = Number(n.upload_speed || 0);
      const speedText = (dlSpeed > 0 || ulSpeed > 0) ? `↓${formatSpeed(dlSpeed)} ↑${formatSpeed(ulSpeed)}` : null;
      const specs = [cpuText, ramText, speedText].filter(Boolean).join(' | ');

      return `
        <div class="bg-slate-900/70 rounded-2xl border border-slate-700/60 overflow-hidden transition shadow-sm">
          <!-- Accordion Header -->
          <div class="p-3 flex justify-between items-center cursor-pointer hover:bg-slate-500/10 transition select-none" onclick="window.toggleNodeAccordion(${idx})">
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
                <b class="text-cyan-400 font-mono text-xs num-bidi" dir="ltr">${n.traffic_used_gb ? fmtTraffic(n.traffic_used_gb, { html: false }) : '—'}</b>
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

      const editBtnHtml = item.is_custom
        ? `<button type="button" data-domain="${escapeHtml(item.domain)}" class="btn-edit-ssl-domain p-1.5 rounded-xl bg-transparent hover:bg-cyan-500/15 text-cyan-400 hover:text-cyan-300 border border-slate-700/70 hover:border-cyan-500/40 transition active:scale-95 flex-shrink-0 flex items-center justify-center" title="ویرایش دامنه">
             <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
           </button>`
        : '';

      const deleteBtnHtml = item.is_custom
        ? `<button type="button" data-domain="${escapeHtml(item.domain)}" class="btn-del-ssl-domain p-1.5 rounded-xl bg-transparent hover:bg-rose-500/15 text-rose-400 hover:text-rose-300 border border-slate-700/70 hover:border-rose-500/30 transition active:scale-95 flex-shrink-0 flex items-center justify-center" title="حذف دامنه">
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
          <div class="space-y-1 text-slate-300 text-xs">
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
          <div class="text-xs text-rose-400/90 leading-relaxed">
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

      const cpuDisplay = isOnline ? (cpu > 0 ? (cpu % 1 === 0 ? cpu : cpu.toFixed(1)) + '%' : '< 1%') : 'آفلاین';
      const ramDisplay = isOnline ? (ram > 0 ? (ram % 1 === 0 ? ram : ram.toFixed(1)) + '%' : '< 1%') : 'آفلاین';

      const shamsiDate = n.due_date_jalali || n.due_date;
      let dueBadgeHtml = '<span class="text-slate-500 font-medium">ثبت‌نشده</span>';
      if (n.days_until_due !== null && n.days_until_due !== undefined) {
        if (n.days_until_due < 0) {
          dueBadgeHtml = `<span class="bg-transparent text-rose-400 border border-rose-500/30 px-2 py-0.5 rounded-lg font-bold">⚠️ منقضی (${Math.abs(n.days_until_due)} روز پیش - ${shamsiDate})</span>`;
        } else if (n.days_until_due === 0) {
          dueBadgeHtml = `<span class="bg-transparent text-rose-400 border border-rose-500/40 px-2 py-0.5 rounded-lg font-bold animate-pulse">⚠️ سررسید امروز! (${shamsiDate})</span>`;
        } else if (n.days_until_due <= 3) {
          dueBadgeHtml = `<span class="bg-transparent text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-lg font-bold">⏳ ${n.days_until_due} روز تا تمدید (${shamsiDate})</span>`;
        } else {
          dueBadgeHtml = `<span class="bg-transparent text-slate-300 border border-slate-700/80 px-2 py-0.5 rounded-lg font-mono">🗓️ ${escapeHtml(shamsiDate)} (${n.days_until_due} روز)</span>`;
        }
      }

      const boxId = `nodeBox_${n.id || idx}`;

      return `
        <div class="node-card settings-box bg-slate-800/90 rounded-2xl border border-slate-700/80 shadow-md relative overflow-hidden transition-all">
          <!-- Top Accent Light -->
          <div class="absolute top-0 right-0 left-0 h-[2px] ${isOnline ? 'bg-gradient-to-r from-emerald-500/0 via-emerald-400/50 to-emerald-500/0' : 'bg-gradient-to-r from-rose-500/0 via-rose-500/40 to-rose-500/0'}"></div>

          <!-- Header: Flag, Name, Status & Chevron (Clickable) -->
          <div class="node-header p-3.5 flex justify-between items-center cursor-pointer select-none hover:bg-slate-500/10 transition active:scale-[0.99]" onclick="window.adminActions.toggleSettingsBox('${boxId}')">
            <!-- Right: Flag and Server Name -->
            <div class="flex items-center gap-2.5 min-w-0">
              <span class="text-2xl flex-shrink-0 filter drop-shadow">${flag}</span>
              <h4 class="font-bold text-xs text-white truncate">${escapeHtml(n.name || 'Server Node')}</h4>
            </div>

            <!-- Left: Online Status + Speeds + Renewal Alert + Chevron Arrow -->
            <div class="flex items-center gap-2 flex-shrink-0">
              ${(n.days_until_due !== null && n.days_until_due <= 3) ? `
                <span class="text-[10px] font-bold bg-transparent text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-xl flex items-center gap-1">
                  <span>⏳</span>
                  <span>${n.days_until_due <= 0 ? 'سررسید!' : n.days_until_due + ' روز'}</span>
                </span>
              ` : ''}
              ${isOnline && (dlSpeed > 0 || ulSpeed > 0) ? `
                <div class="hidden sm:flex items-center gap-1.5 text-[10px] font-mono text-slate-300 bg-slate-900/60 px-2 py-0.5 rounded-xl border border-slate-700/60" dir="ltr">
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
              <span class="text-[11px] text-slate-400 flex items-center gap-1.5">
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
                  <span class="text-[10px] text-slate-500 font-mono">RX</span>
                </div>
                <b class="text-emerald-400 font-mono text-xs block text-left" dir="ltr">↓ ${formatSpeed(dlSpeed)}</b>
              </div>
              <div class="bg-transparent p-2.5 rounded-xl border border-slate-700/60">
                <div class="flex items-center justify-between text-[10px] mb-1">
                  <span class="text-slate-400 flex items-center gap-1">
                    <svg class="w-3 h-3 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18"/></svg>
                    <span>سرعت آپلود (UL):</span>
                  </span>
                  <span class="text-[10px] text-slate-500 font-mono">TX</span>
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
                <b class="t-success font-mono text-xs">${formatNumber(n.connected_users || 0)} نفر</b>
              </div>
              <div class="bg-transparent p-2 rounded-xl border border-slate-700/60">
                <span class="text-slate-400 block mb-0.5">ترافیک مصرفی نود</span>
                <b class="text-blue-600 dark:text-cyan-400 font-mono text-xs num-bidi" dir="ltr">${fmtTraffic(n.traffic_used_gb || 0, { html: false })}</b>
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
                    <span class="text-[10px] text-slate-400 font-sans">تومان</span>
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
                      <span class="text-[10px] text-slate-400 font-sans">تومان</span>
                    ` : '—'}
                  </b>
                </div>
              </div>

              <!-- Node Profit / Loss & Estimated Revenue Strip -->
              <div class="grid grid-cols-2 gap-2 pt-1 border-t border-slate-800 text-[10px]">
                <div>
                  <span class="text-slate-400 block mb-0.5">درآمد تخمینی نود:</span>
                  <b class="text-emerald-400 font-mono block">
                    ${n.est_revenue_toman ? `${formatNumber(n.est_revenue_toman)} <span class="text-[10px] text-slate-400 font-sans">تومان</span>` : '۰ تومان'}
                  </b>
                </div>
                <div>
                  <span class="text-slate-400 block mb-0.5">سود/زیان خالص:</span>
                  <b class="${n.is_profitable ? 'text-emerald-400' : 'text-rose-400'} font-bold block text-xs">
                    <span class="inline-flex items-center gap-1 font-mono" dir="ltr"><span>${(n.net_profit_toman || 0) > 0 ? '+' : ''}${formatNumber(n.net_profit_toman || 0)}</span> <span class="font-sans text-[10px] text-slate-300">تومان</span> ${n.roi_percent !== null && n.roi_percent !== undefined ? `<span dir="ltr">(${n.roi_percent > 0 ? '+' : ''}${n.roi_percent}%)</span>` : ''}</span>
                  </b>
                </div>
              </div>

              <!-- Button to configure node billing -->
              <div class="pt-1">
                <button type="button" class="btn-node-billing w-full bg-transparent hover:bg-cyan-500/10 text-cyan-500 dark:text-cyan-400 py-1.5 rounded-xl border border-cyan-500/30 transition flex items-center justify-center gap-1.5 font-bold active:scale-95 shadow-sm"
                  data-uuid="${escapeHtml(n.uuid || n.id || '')}"
                  data-name="${escapeHtml(n.name || '')}"
                  data-provider="${escapeHtml(n.provider || '')}"
                  data-cost-toman="${Number(n.monthly_cost_toman || 0)}"
                  data-cost-eur="${Number(n.monthly_cost_eur || 0)}"
                  data-due="${escapeHtml(n.due_date || '')}"
                  data-notes="${escapeHtml(n.notes || '')}"
                  data-flag="${escapeHtml(flag || '')}"
                  data-currency="${escapeHtml(n.currency || 'EUR')}">
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
            tabBtn.className = 'admin-app-os-tab w-full py-1.5 px-0.5 rounded-xl font-bold text-[10px] sm:text-[11px] whitespace-nowrap transition flex items-center justify-center gap-0.5 sm:gap-1 bg-cyan-600 text-white shadow';
          } else {
            tabBtn.className = 'admin-app-os-tab w-full py-1.5 px-0.5 rounded-xl font-medium text-[10px] sm:text-[11px] whitespace-nowrap text-slate-400 hover:text-slate-200 transition flex items-center justify-center gap-0.5 sm:gap-1';
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
          if (window.syncAdminOverview) window.syncAdminOverview(true);
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

    if (window.hapticFeedback) window.hapticFeedback('selection');

    const isSsl = subtab === 'ssl';
    btnServers?.classList.toggle('is-active', !isSsl);
    btnServers?.setAttribute('aria-selected', !isSsl ? 'true' : 'false');
    btnSsl?.classList.toggle('is-active', isSsl);
    btnSsl?.setAttribute('aria-selected', isSsl ? 'true' : 'false');

    contentServers?.classList.toggle('hidden', isSsl);
    contentSsl?.classList.toggle('hidden', !isSsl);

    if (isSsl) {
      fetchAdminSslHealth();
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

  // Global exports
  window.renderOverviewNodes = renderOverviewNodes;
  window.renderFullNodes = renderFullNodes;
  window.renderSslHealth = renderSslHealth;
  window.fetchAdminSslHealth = fetchAdminSslHealth;
})(window);
