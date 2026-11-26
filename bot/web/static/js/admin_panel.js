/**
 * Remnabot Admin — Remnawave Panel Control Suite Module
 * Manages Hosts, Config Profiles, Snippets, External Squads, Subscription Settings,
 * Infra Billing Providers/Nodes Sync, and Panel API Tokens via window.api.
 */
(function(window) {
  'use strict';

  const $ = id => document.getElementById(id);

  let panelState = {
    loaded: false,
    loading: false,
    hosts: [],
    config_profiles: [],
    snippets: [],
    external_squads: [],
    internal_squads: [],
    subscription_settings: {},
    infra_providers: [],
    infra_billing_nodes: [],
    infra_billing_history: [],
    api_tokens_info: { ok: false, tokens: [], jwt_required: false },
  };
  let hostSquadTempMode = 'EXCLUDE';
  let hostSquadTempSet = new Set();
  const TRASH_ICON_SVG = '<svg class="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>';
  const HOSTS_PAGE_SIZE = 15;
  let selectedHostUuids = new Set();
  let hostSearchQuery = '';
  let hostsPage = 1;
  let activeSubSection = 'hosts';
  let pendingConfirmHandler = null;
  let onProviderSavedCallback = null;

  function toast(msg) {
    if (window.showToast) window.showToast(msg);
  }

  function haptic(type = 'selection') {
    if (window.hapticFeedback) window.hapticFeedback(type);
  }

  function switchSubSection(key = 'hosts') {
    activeSubSection = key;
    const keys = ['hosts', 'squads', 'configs', 'infra'];
    const activeCls = 'flex-1 py-1.5 px-2 rounded-xl text-[11px] font-bold transition bg-cyan-600 text-white shadow whitespace-nowrap inline-flex items-center justify-center gap-1';
    const inactiveCls = 'flex-1 py-1.5 px-2 rounded-xl text-[11px] font-medium transition t-muted hover:t-main whitespace-nowrap inline-flex items-center justify-center gap-1';
    keys.forEach(k => {
      const btn = $(`panelCtrlTabBtn_${k}`);
      const pane = $(`panelCtrlPane_${k}`);
      const isHit = k === key;
      if (btn) btn.className = isHit ? activeCls : inactiveCls;
      if (pane) pane.classList.toggle('hidden', !isHit);
    });
    haptic('selection');
  }

  async function fetchOverview(force = false) {
    if (panelState.loading) return;
    if (panelState.loaded && !force) {
      renderAll();
      return;
    }
    panelState.loading = true;

    try {
      const res = await window.api?.getPanelControlOverview?.();
      if (res && res.ok && res.data) {
        panelState = { loaded: true, loading: false, ...res.data };
        renderAll();
        return res.data;
      }
      toast(`⚠️ ${res?.error || 'خطا در دریافت اطلاعات پنل Remnawave'}`);
    } catch (err) {
      console.error('Panel control overview error:', err);
      toast('خطای ارتباط با سرور هنگام بارگذاری کنترل‌پنل');
    } finally {
      panelState.loading = false;
    }
    return null;
  }

  function renderAll() {
    renderHosts();
    renderSubscriptionSettings();
    renderInternalSquads();
    renderExternalSquads();
    renderConfigProfiles();
    renderSnippets();
    renderInfraProviders();
    renderBillingHistory();
    renderApiTokens();
  }

  function allProfileInbounds() {
    const out = [];
    for (const prof of (panelState.config_profiles || [])) {
      for (const inb of (prof.inbounds || [])) {
        if (inb && inb.uuid) {
          out.push({
            uuid: inb.uuid,
            tag: inb.tag || 'Inbound',
            type: inb.type || '',
            port: inb.port || '',
            profileUuid: prof.uuid,
            profileName: prof.name || 'Profile',
          });
        }
      }
    }
    return out;
  }

  // --- Confirmation Modal (Reusable, no window.confirm) ---
  function confirmAction({ title, message, btnText = 'تأیید و اجرا', onConfirm }) {
    const modal = $('panelActionConfirmModal');
    if (!modal) return;
    if ($('panelConfirmModalTitle')) $('panelConfirmModalTitle').innerText = title || 'تأیید عملیات';
    if ($('panelConfirmModalMsg')) $('panelConfirmModalMsg').innerText = message || '';
    const btn = $('panelConfirmExecuteBtn');
    if (btn) {
      btn.disabled = false;
      btn.innerText = btnText;
    }
    pendingConfirmHandler = onConfirm || null;
    modal.classList.remove('hidden');
    haptic('warning');
  }

  function closeConfirmModal() {
    const modal = $('panelActionConfirmModal');
    if (modal) modal.classList.add('hidden');
    pendingConfirmHandler = null;
  }

  async function executeConfirmAction() {
    if (typeof pendingConfirmHandler !== 'function') {
      closeConfirmModal();
      return;
    }
    const btn = $('panelConfirmExecuteBtn');
    const prev = btn ? btn.innerText : '';
    if (btn) {
      btn.disabled = true;
      btn.innerText = 'در حال اجرا...';
    }
    try {
      await pendingConfirmHandler();
      closeConfirmModal();
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerText = prev || 'تأیید';
      }
    }
  }

  function _matchesHostQuery(h, q) {
    if (!q) return true;
    return (
      String(h.remark || '').toLowerCase().includes(q)
      || String(h.address || '').toLowerCase().includes(q)
      || String(h.sni || '').toLowerCase().includes(q)
    );
  }

  // --- 1. Hosts Rendering & Actions ---
  function renderHosts() {
    const listEl = $('panelHostsList');
    if (!listEl) return;
    const allHosts = Array.isArray(panelState.hosts) ? panelState.hosts : [];
    const activeCount = allHosts.filter(h => !h.isDisabled).length;
    const disabledCount = allHosts.length - activeCount;

    if ($('panelHostsTotalBadge')) $('panelHostsTotalBadge').innerText = String(allHosts.length);
    if ($('panelHostsActiveBadge')) $('panelHostsActiveBadge').innerText = String(activeCount);
    if ($('panelHostsDisabledBadge')) $('panelHostsDisabledBadge').innerText = String(disabledCount);

    const q = hostSearchQuery.trim().toLowerCase();
    const filtered = q ? allHosts.filter(h => _matchesHostQuery(h, q)) : allHosts;

    const bulkBar = $('panelHostsBulkBar');
    if (bulkBar) {
      bulkBar.classList.toggle('hidden', selectedHostUuids.size === 0);
      if ($('panelHostsSelectedCount')) $('panelHostsSelectedCount').innerText = `${selectedHostUuids.size} مورد انتخاب شده`;
    }
    const selectAllBtn = $('panelHostsSelectAllBtn');
    if (selectAllBtn) {
      const targetHosts = q ? filtered : allHosts;
      const allSelected = targetHosts.length > 0 && targetHosts.every(h => selectedHostUuids.has(String(h.uuid || '')));
      selectAllBtn.innerText = allSelected ? 'لغو انتخاب همه' : 'انتخاب همه';
    }

    const paginationEl = $('panelHostsPagination');
    if (filtered.length === 0) {
      listEl.innerHTML = '<div class="p-5 text-center text-xs t-muted card-inset rounded-2xl border border-card-border">هیچ هاستی یافت نشد.</div>';
      if (paginationEl) {
        paginationEl.classList.add('hidden');
        paginationEl.innerHTML = '';
      }
      return;
    }

    const totalPages = Math.max(1, Math.ceil(filtered.length / HOSTS_PAGE_SIZE));
    if (hostsPage > totalPages) hostsPage = totalPages;
    if (hostsPage < 1) hostsPage = 1;
    const startIdx = (hostsPage - 1) * HOSTS_PAGE_SIZE;
    const pageItems = filtered.slice(startIdx, startIdx + HOSTS_PAGE_SIZE);

    if (paginationEl) {
      if (totalPages <= 1) {
        paginationEl.classList.add('hidden');
        paginationEl.innerHTML = '';
      } else {
        const endIdx = Math.min(startIdx + pageItems.length, filtered.length);
        const prevDisabled = hostsPage <= 1 ? 'opacity-40 pointer-events-none' : 'hover:border-cyan-500/40';
        const nextDisabled = hostsPage >= totalPages ? 'opacity-40 pointer-events-none' : 'hover:border-cyan-500/40';
        paginationEl.classList.remove('hidden');
        paginationEl.innerHTML = `
          <div class="flex items-center gap-1.5">
            <button type="button" onclick="window.panelCtrl.setHostsPage(${hostsPage - 1})" class="px-2.5 py-1.5 rounded-xl card-inset border border-card-border t-main font-bold transition active:scale-95 ${prevDisabled}" ${hostsPage <= 1 ? 'disabled' : ''}>قبلی</button>
            <button type="button" onclick="window.panelCtrl.setHostsPage(${hostsPage + 1})" class="px-2.5 py-1.5 rounded-xl card-inset border border-card-border t-main font-bold transition active:scale-95 ${nextDisabled}" ${hostsPage >= totalPages ? 'disabled' : ''}>بعدی</button>
          </div>
          <div class="text-[11px] t-muted font-medium" dir="rtl">
            صفحه <span class="font-bold t-main num-bidi">${hostsPage}</span> از <span class="num-bidi">${totalPages}</span>
            <span class="mx-1 opacity-50">•</span>
            <span class="num-bidi">${startIdx + 1}-${endIdx}</span> از <span class="num-bidi">${filtered.length}</span>
          </div>
        `;
      }
    }

    listEl.innerHTML = pageItems.map(h => {
      const uuid = String(h.uuid || '');
      const disabled = Boolean(h.isDisabled);
      const checked = selectedHostUuids.has(uuid);
      const tags = Array.isArray(h.tags) ? h.tags : (h.tag ? [h.tag] : []);
      const sqObj = (h.internalSquads && typeof h.internalSquads === 'object') ? h.internalSquads : null;
      const sqMode = sqObj ? String(sqObj.mode || 'EXCLUDE').toUpperCase() : 'EXCLUDE';
      const sqList = sqObj
        ? (Array.isArray(sqObj.squads) ? sqObj.squads : [])
        : (Array.isArray(h.excludedInternalSquads) ? h.excludedInternalSquads : []);
      const squadBadge = sqMode === 'ALLOW_ONLY'
        ? `<span class="badge badge-info text-[10px]">فقط ${sqList.length} اسکواد</span>`
        : (sqList.length > 0
            ? `<span class="badge badge-warn text-[10px]">بجز ${sqList.length} اسکواد</span>`
            : `<span class="badge badge-neutral text-[10px]">همه اسکوادها</span>`);
      const statusIcon = disabled
        ? '<span class="inline-flex items-center justify-center w-4 h-4 rounded-full bg-rose-500/15 border border-rose-500/40 t-danger shrink-0" title="غیرفعال"><svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg></span>'
        : '<span class="inline-flex items-center justify-center w-4 h-4 rounded-full bg-emerald-500/15 border border-emerald-500/40 t-success shrink-0" title="فعال"><svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg></span>';
      return `
        <div class="card p-3 rounded-2xl border border-card-border space-y-2">
          <div class="flex items-start justify-between gap-2">
            <div class="flex items-center gap-1 shrink-0 pt-0.5">
              <button type="button" onclick="window.openQuickDiagnosticModal('${escapeHtml(h.address || '')}', ${Number(h.port || 443)}, '${escapeHtml(h.remark || 'Host')}')" class="p-1.5 rounded-xl border border-emerald-500/35 t-success hover:bg-emerald-500/10 transition active:scale-95" title="تست پورت / دسترسی">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.14 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0"/></svg>
              </button>
              <button type="button" onclick="window.panelCtrl.openHostModal('${escapeHtml(uuid)}', true)" class="p-1.5 rounded-xl border border-indigo-500/35 t-info hover:bg-indigo-500/10 transition active:scale-95" title="کپی / ساخت مشابه">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
              </button>
              <button type="button" onclick="window.panelCtrl.openHostModal('${escapeHtml(uuid)}')" class="p-1.5 rounded-xl border border-cyan-500/35 t-accent hover:bg-cyan-500/10 transition active:scale-95" title="ویرایش هاست">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
              </button>
              <button type="button" onclick="window.panelCtrl.toggleSingleHost('${escapeHtml(uuid)}', ${disabled ? 'true' : 'false'})" class="p-1.5 rounded-xl border ${disabled ? 'border-emerald-500/35 t-success hover:bg-emerald-500/10' : 'border-rose-500/35 t-danger hover:bg-rose-500/10'} transition active:scale-95" title="${disabled ? 'فعال‌سازی هاست' : 'غیرفعال‌سازی هاست'}">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5.636 5.636a9 9 0 1012.728 0M12 3v9"/></svg>
              </button>
            </div>
            <div class="min-w-0 flex-1 text-left cursor-pointer" dir="ltr" onclick="window.panelCtrl.openHostModal('${escapeHtml(uuid)}')">
              <div class="flex items-center justify-start gap-1.5 min-w-0">
                <b class="text-xs t-main truncate font-en">${escapeHtml(h.remark || 'Host')}</b>
                ${statusIcon}
              </div>
              <div class="text-[11px] t-accent font-sans num-bidi truncate mt-0.5">${escapeHtml(h.address || '—')}:${Number(h.port || 443)}</div>
            </div>
            <input type="checkbox" aria-label="انتخاب هاست" class="w-4 h-4 mt-1 rounded accent-cyan-500 cursor-pointer shrink-0" ${checked ? 'checked' : ''} onchange="window.panelCtrl.toggleHostSelection('${escapeHtml(uuid)}', this.checked)" />
          </div>
          <div class="pt-1.5 border-t border-card-border space-y-1.5 text-[10.5px] t-muted">
            <div class="flex flex-wrap items-center gap-1">
              ${squadBadge}
              ${tags.map(t => `<span class="badge badge-info text-[10px] font-en" dir="ltr">${escapeHtml(t)}</span>`).join('')}
            </div>
            <div class="flex items-start justify-start gap-1 font-en text-left w-full" dir="ltr">
              <span class="shrink-0">SNI:</span>
              <b class="t-main break-all text-left min-w-0">${escapeHtml(h.sni || '—')}</b>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  function setHostsPage(page = 1) {
    const num = parseInt(page, 10);
    hostsPage = Number.isFinite(num) && num >= 1 ? num : 1;
    renderHosts();
  }

  function filterHosts(q = '') {
    hostSearchQuery = q;
    hostsPage = 1;
    renderHosts();
  }

  function toggleHostSelection(uuid, checked) {
    if (checked) selectedHostUuids.add(uuid);
    else selectedHostUuids.delete(uuid);
    renderHosts();
  }

  function toggleSelectAllHosts() {
    const allHosts = Array.isArray(panelState.hosts) ? panelState.hosts : [];
    const q = hostSearchQuery.trim().toLowerCase();
    const targetHosts = q ? allHosts.filter(h => _matchesHostQuery(h, q)) : allHosts;
    const allSelected = targetHosts.length > 0 && targetHosts.every(h => selectedHostUuids.has(String(h.uuid || '')));
    if (allSelected) {
      if (q) {
        targetHosts.forEach(h => { if (h.uuid) selectedHostUuids.delete(String(h.uuid)); });
      } else {
        selectedHostUuids.clear();
      }
    } else {
      targetHosts.forEach(h => { if (h.uuid) selectedHostUuids.add(String(h.uuid)); });
    }
    renderHosts();
  }

  async function toggleSingleHost(uuid, enableNow) {
    const res = await window.api?.bulkPanelHosts?.(enableNow ? 'enable' : 'disable', [uuid]);
    if (res && res.ok) {
      toast(`✅ ${res.message}`);
      haptic('success');
      await fetchOverview(true);
    } else {
      toast(`⚠️ ${res?.error || 'خطا در تغییر وضعیت هاست'}`);
    }
  }

  async function runBulkHosts(action) {
    const uuids = Array.from(selectedHostUuids);
    if (!uuids.length) return;
    const execute = async () => {
      const res = await window.api?.bulkPanelHosts?.(action, uuids);
      if (res && res.ok) {
        toast(`✅ ${res.message}`);
        selectedHostUuids.clear();
        haptic('success');
        await fetchOverview(true);
      } else {
        toast(`⚠️ ${res?.error || 'خطا در اجرای عملیات گروهی'}`);
      }
    };
    if (action === 'delete') {
      confirmAction({
        title: 'حذف گروهی هاست‌ها',
        message: `آیا از حذف ${uuids.length} هاست انتخاب‌شده از پنل Remnawave مطمئن هستید؟`,
        btnText: 'حذف قطعی',
        onConfirm: execute,
      });
    } else {
      await execute();
    }
  }

  function _applySelectedHostInbound(inbUuid = '', profUuid = '') {
    const inbounds = allProfileInbounds();
    const hit = inbUuid ? inbounds.find(x => String(x.uuid) === String(inbUuid)) : null;
    if ($('panelHostInboundSelect')) $('panelHostInboundSelect').value = inbUuid || '';
    if ($('panelHostInboundProfileUuid')) $('panelHostInboundProfileUuid').value = hit?.profileUuid || profUuid || '';
    const disp = $('panelHostInboundDisplay');
    if (disp) {
      if (hit) {
        disp.innerText = `${hit.profileName} — ${hit.tag} (${hit.type || ''}:${hit.port || ''})`;
        disp.setAttribute('dir', 'ltr');
      } else {
        disp.innerText = 'انتخاب اینباند متصل (اختیاری در ویرایش)...';
        disp.setAttribute('dir', 'rtl');
      }
    }
  }

  function _renderHostInboundPickerList() {
    const listEl = $('panelHostInboundPickerList');
    if (!listEl) return;
    const inbounds = allProfileInbounds();
    const currentVal = $('panelHostInboundSelect')?.value || '';
    const row = (val, profUuid, title, sub = '', isEnglish = true) => renderModalPickerRow({
      onClick: `window.panelCtrl.selectHostInbound('${escapeHtml(val)}', '${escapeHtml(profUuid)}')`,
      title,
      sub,
      selected: String(currentVal) === String(val),
      isEnglish,
      rowDir: 'ltr',
      subDir: 'ltr',
    });

    let html = row('', '', 'انتخاب اینباند متصل (اختیاری در ویرایش)', '', false);
    for (const inb of inbounds) {
      html += row(inb.uuid, inb.profileUuid, `${inb.profileName} — ${inb.tag}`, `${inb.type || 'inbound'}:${inb.port || ''}`, true);
    }
    listEl.innerHTML = html;
  }

  function openHostInboundModal() {
    const modal = $('panelHostInboundPickerModal');
    if (!modal) return;
    _renderHostInboundPickerList();
    modal.classList.remove('hidden');
    haptic('selection');
  }

  function closeHostInboundModal() {
    $('panelHostInboundPickerModal')?.classList.add('hidden');
  }

  function selectHostInbound(inbUuid = '', profUuid = '') {
    _applySelectedHostInbound(inbUuid, profUuid);
    closeHostInboundModal();
    haptic('selection');
  }

  function _syncHostSquadDisplay(mode, uuids) {
    const modeEl = $('panelHostSquadModeSelect');
    const uuidsEl = $('panelHostSquadUuidsInput');
    const dispEl = $('panelHostSquadsDisplay');
    const normMode = mode === 'ALLOW_ONLY' ? 'ALLOW_ONLY' : 'EXCLUDE';
    const arr = Array.isArray(uuids) ? uuids.filter(Boolean) : [];
    if (modeEl) modeEl.value = normMode;
    if (uuidsEl) uuidsEl.value = arr.join(',');
    if (dispEl) {
      if (normMode === 'ALLOW_ONLY') {
        dispEl.innerText = arr.length ? `فقط نمایش در ${arr.length} اسکواد انتخاب‌شده` : 'فقط نمایش (هیچ اسکوادی انتخاب نشده)';
      } else {
        dispEl.innerText = arr.length ? `مخفی برای ${arr.length} اسکواد انتخاب‌شده` : 'نمایش در همه اسکوادها (بدون محدودیت)';
      }
    }
  }

  function _renderHostSquadsModalState() {
    const listEl = $('panelHostSquadsModalList');
    const optEx = $('hostSquadModeOptExclude');
    const optAl = $('hostSquadModeOptAllow');
    const dotEx = $('hostSquadModeDotExclude');
    const dotAl = $('hostSquadModeDotAllow');
    const isAllow = hostSquadTempMode === 'ALLOW_ONLY';
    if (optEx) optEx.className = !isAllow ? 'w-full text-right p-2.5 rounded-2xl border border-cyan-500/45 bg-cyan-500/10 transition space-y-0.5' : 'w-full text-right p-2.5 rounded-2xl border border-card-border card-inset transition space-y-0.5';
    if (optAl) optAl.className = isAllow ? 'w-full text-right p-2.5 rounded-2xl border border-cyan-500/45 bg-cyan-500/10 transition space-y-0.5' : 'w-full text-right p-2.5 rounded-2xl border border-card-border card-inset transition space-y-0.5';
    if (dotEx) dotEx.className = !isAllow ? 'w-3.5 h-3.5 rounded-full bg-cyan-500 ring-2 ring-cyan-500/30 shrink-0' : 'w-3.5 h-3.5 rounded-full border border-card-border shrink-0';
    if (dotAl) dotAl.className = isAllow ? 'w-3.5 h-3.5 rounded-full bg-cyan-500 ring-2 ring-cyan-500/30 shrink-0' : 'w-3.5 h-3.5 rounded-full border border-card-border shrink-0';

    if (!listEl) return;
    const squads = Array.isArray(panelState.internal_squads) ? panelState.internal_squads : [];
    if (!squads.length) {
      listEl.innerHTML = '<div class="p-4 text-center text-xs t-muted card-inset rounded-2xl border border-card-border" dir="rtl">اسکواد داخلی در پنل یافت نشد.</div>';
      return;
    }
    listEl.innerHTML = squads.map(sq => {
      const u = String(sq.uuid || '');
      const selected = hostSquadTempSet.has(u);
      return renderModalPickerRow({
        onClick: `window.panelCtrl.toggleHostSquadSelection('${escapeHtml(u)}')`,
        title: sq.name || u,
        sub: '',
        selected,
        isEnglish: true,
        rowDir: 'ltr',
        subDir: 'ltr',
      });
    }).join('');
  }

  function openHostSquadsModal() {
    const modal = $('panelHostSquadsModal');
    if (!modal) return;
    hostSquadTempMode = $('panelHostSquadModeSelect')?.value === 'ALLOW_ONLY' ? 'ALLOW_ONLY' : 'EXCLUDE';
    const raw = $('panelHostSquadUuidsInput')?.value || '';
    hostSquadTempSet = new Set(raw.split(',').map(x => x.trim()).filter(Boolean));
    _renderHostSquadsModalState();
    modal.classList.remove('hidden');
    haptic('selection');
  }

  function closeHostSquadsModal() {
    $('panelHostSquadsModal')?.classList.add('hidden');
  }

  function setHostSquadMode(mode = 'EXCLUDE') {
    hostSquadTempMode = mode === 'ALLOW_ONLY' ? 'ALLOW_ONLY' : 'EXCLUDE';
    _renderHostSquadsModalState();
    haptic('selection');
  }

  function toggleHostSquadSelection(uuid) {
    if (!uuid) return;
    if (hostSquadTempSet.has(uuid)) hostSquadTempSet.delete(uuid);
    else hostSquadTempSet.add(uuid);
    _renderHostSquadsModalState();
    haptic('selection');
  }

  function applyHostSquadsModal() {
    _syncHostSquadDisplay(hostSquadTempMode, Array.from(hostSquadTempSet));
    closeHostSquadsModal();
    haptic('success');
  }

  function openHostModal(hostUuid = '', isClone = false) {
    const modal = $('panelHostEditorModal');
    if (!modal) return;
    const h = hostUuid ? (panelState.hosts || []).find(x => String(x.uuid) === String(hostUuid)) : null;

    if ($('panelHostModalTitle')) {
      $('panelHostModalTitle').innerText = isClone ? 'ساخت هاست مشابه' : (h ? 'ویرایش هاست پنل' : 'افزودن هاست جدید');
    }
    if ($('panelHostUuid')) $('panelHostUuid').value = isClone ? '' : (h?.uuid || '');
    if ($('panelHostRemark')) $('panelHostRemark').value = h ? (isClone ? `${h.remark || 'Host'} Copy` : (h.remark || '')) : '';
    if ($('panelHostAddress')) $('panelHostAddress').value = h?.address || '';
    if ($('panelHostPort')) $('panelHostPort').value = h?.port || 443;
    if ($('panelHostSni')) $('panelHostSni').value = h?.sni || '';
    if ($('panelHostHeader')) $('panelHostHeader').value = h?.host || '';
    if ($('panelHostDisabled')) $('panelHostDisabled').checked = Boolean(h?.isDisabled);

    const curInb = h?.inbound?.configProfileInboundUuid || h?.inboundUuid || '';
    const curProf = h?.inbound?.configProfileUuid || '';
    _applySelectedHostInbound(curInb, curProf);

    const sqObj = (h?.internalSquads && typeof h.internalSquads === 'object') ? h.internalSquads : null;
    const sqMode = sqObj ? String(sqObj.mode || 'EXCLUDE').toUpperCase() : 'EXCLUDE';
    const sqUuids = sqObj
      ? (Array.isArray(sqObj.squads) ? sqObj.squads : [])
      : (Array.isArray(h?.excludedInternalSquads) ? h.excludedInternalSquads : []);
    _syncHostSquadDisplay(sqMode, sqUuids);

    modal.classList.remove('hidden');
    haptic('selection');
  }

  function closeHostModal() {
    $('panelHostEditorModal')?.classList.add('hidden');
  }

  async function saveHost() {
    const uuid = $('panelHostUuid')?.value?.trim() || '';
    const remark = $('panelHostRemark')?.value?.trim() || '';
    const address = $('panelHostAddress')?.value?.trim() || '';
    const port = parseInt($('panelHostPort')?.value || '443', 10);
    const sni = $('panelHostSni')?.value?.trim() ?? '';
    const host = $('panelHostHeader')?.value?.trim() ?? '';
    const is_disabled = Boolean($('panelHostDisabled')?.checked);
    const inbound_uuid = $('panelHostInboundSelect')?.value?.trim() || '';
    const config_profile_uuid = $('panelHostInboundProfileUuid')?.value?.trim() || '';

    if (!remark || !address) {
      toast('نام و آدرس هاست الزامی است.');
      return;
    }

    const payload = {
      uuid,
      remark,
      address,
      port,
      sni,
      host,
      is_disabled,
      inbound_uuid,
      config_profile_uuid,
    };
    const squadsAvailable = Array.isArray(panelState.internal_squads) && panelState.internal_squads.length > 0;
    const rawSqUuids = ($('panelHostSquadUuidsInput')?.value || '').split(',').map(x => x.trim()).filter(Boolean);
    if (squadsAvailable || rawSqUuids.length > 0) {
      payload.squad_mode = $('panelHostSquadModeSelect')?.value || 'EXCLUDE';
      payload.squad_uuids = rawSqUuids;
    }

    const res = await window.api?.savePanelHost?.(payload);
    if (res && res.ok) {
      toast(`✅ ${res.message}`);
      closeHostModal();
      haptic('success');
      await fetchOverview(true);
    } else {
      toast(`⚠️ ${res?.error || 'خطا در ذخیره هاست'}`);
    }
  }

  // --- 2. Subscription Settings & External Squads ---
  function renderSubscriptionSettings() {
    const s = panelState.subscription_settings || {};
    if ($('panelSubSettingsUuid')) $('panelSubSettingsUuid').value = s.uuid || '';
    if ($('panelSubProfileTitle')) $('panelSubProfileTitle').value = s.profileTitle || '';
    if ($('panelSubSupportLink')) $('panelSubSupportLink').value = s.supportLink || '';
    if ($('panelSubUpdateInterval')) $('panelSubUpdateInterval').value = s.profileUpdateInterval || 12;
    if ($('panelSubWebpageEnabled')) $('panelSubWebpageEnabled').checked = Boolean(s.isProfileWebpageUrlEnabled);
    if ($('panelSubServeJson')) $('panelSubServeJson').checked = Boolean(s.serveJsonAtBaseSubscription);
  }

  async function saveSubSettings() {
    const payload = {
      uuid: $('panelSubSettingsUuid')?.value?.trim() || undefined,
      profile_title: $('panelSubProfileTitle')?.value?.trim() || '',
      support_link: $('panelSubSupportLink')?.value?.trim() || '',
      profile_update_interval: parseInt($('panelSubUpdateInterval')?.value || '12', 10),
      is_profile_webpage_url_enabled: Boolean($('panelSubWebpageEnabled')?.checked),
      serve_json_at_base_subscription: Boolean($('panelSubServeJson')?.checked),
    };
    const res = await window.api?.savePanelSubSettings?.(payload);
    if (res && res.ok) {
      toast(`✅ ${res.message}`);
      haptic('success');
      await fetchOverview(true);
    } else {
      toast(`⚠️ ${res?.error || 'خطا در ذخیره تنظیمات ساب'}`);
    }
  }

  let activeSquadType = 'external';
  let selectedSquadUserMap = new Map();

  function renderInternalSquads() {
    const listEl = $('panelInternalSquadsList');
    if (!listEl) return;
    const squads = Array.isArray(panelState.internal_squads) ? panelState.internal_squads : [];
    if (!squads.length) {
      listEl.innerHTML = '<div class="p-4 text-center text-xs t-muted card-inset rounded-2xl border border-card-border">هیچ اسکواد داخلی در پنل یافت نشد.</div>';
      return;
    }
    listEl.innerHTML = squads.map(sq => {
      const uuid = String(sq.uuid || '');
      const members = sq.info?.membersCount ?? sq.membersCount ?? 0;
      const inboundsCnt = Array.isArray(sq.inbounds) ? sq.inbounds.length : 0;
      return `
        <div class="card p-3 rounded-2xl border border-card-border flex items-center justify-between gap-2">
          <div class="flex items-center gap-1 shrink-0">
            <button type="button" onclick="window.panelCtrl.openSquadUsersModal('internal', '${escapeHtml(uuid)}', '${escapeHtml(sq.name || '')}')" class="px-2 py-1 rounded-xl border border-card-border t-main hover:border-cyan-500/40 text-[10.5px] font-bold transition active:scale-95">اعضا</button>
            <button type="button" onclick="window.panelCtrl.openIntSquadModal('${escapeHtml(uuid)}')" class="p-1.5 rounded-xl border border-cyan-500/35 t-accent hover:bg-cyan-500/10 transition active:scale-95" title="ویرایش اسکواد داخلی">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
            </button>
            <button type="button" onclick="window.panelCtrl.deleteIntSquad('${escapeHtml(uuid)}', '${escapeHtml(sq.name || '')}')" class="p-1.5 rounded-xl border border-rose-500/35 t-danger hover:bg-rose-500/10 transition active:scale-95" title="حذف اسکواد داخلی">
              ${TRASH_ICON_SVG}
            </button>
          </div>
          <div class="min-w-0 flex-1 text-left" dir="ltr">
            <b class="text-xs t-main block truncate font-en">${escapeHtml(sq.name || 'Squad')}</b>
            <span class="text-[10.5px] t-muted block mt-0.5 text-right" dir="rtl"><span class="num-bidi font-bold">${Number(members)}</span> عضو • <span class="num-bidi font-bold">${Number(inboundsCnt)}</span> اینباند</span>
          </div>
        </div>
      `;
    }).join('');
  }

  function openIntSquadModal(squadUuid = '') {
    const modal = $('panelIntSquadEditorModal');
    if (!modal) return;
    const hit = squadUuid ? (panelState.internal_squads || []).find(s => String(s.uuid) === String(squadUuid)) : null;
    if ($('panelIntSquadModalTitle')) $('panelIntSquadModalTitle').innerText = hit ? 'ویرایش اسکواد داخلی' : 'ساخت اسکواد داخلی جدید';
    if ($('panelIntSquadUuid')) $('panelIntSquadUuid').value = hit?.uuid || '';
    if ($('panelIntSquadName')) $('panelIntSquadName').value = hit?.name || '';

    const selectedSet = new Set(
      (Array.isArray(hit?.inbounds) ? hit.inbounds : [])
        .map(x => String(typeof x === 'string' ? x : (x?.uuid || '')))
        .filter(Boolean)
    );
    const listEl = $('panelIntSquadInboundsList');
    if (listEl) {
      const inbounds = allProfileInbounds();
      if (!inbounds.length) {
        listEl.innerHTML = '<div class="col-span-2 p-3 text-center text-[11px] t-muted card-inset rounded-xl border border-card-border" dir="rtl">اینباندی در پروفایل‌های Xray یافت نشد.</div>';
      } else {
        listEl.innerHTML = inbounds.map(inb => {
          const checked = selectedSet.has(String(inb.uuid)) ? 'checked' : '';
          const titleText = `${inb.profileName} — ${inb.tag}`;
          return `
            <label class="card-inset px-2.5 py-1.5 rounded-xl border border-card-border text-[10.5px] font-en flex items-center gap-1.5 min-w-0 cursor-pointer hover:border-cyan-500/40 transition" title="${escapeHtml(titleText)}">
              <input type="checkbox" class="panel-int-squad-inb-chk accent-cyan-500 rounded shrink-0" value="${escapeHtml(inb.uuid)}" ${checked} />
              <span class="truncate min-w-0 flex-1">${escapeHtml(inb.tag || inb.uuid)}</span>
            </label>
          `;
        }).join('');
      }
    }
    modal.classList.remove('hidden');
    haptic('selection');
  }

  function closeIntSquadModal() {
    $('panelIntSquadEditorModal')?.classList.add('hidden');
  }

  async function saveIntSquad() {
    const uuid = $('panelIntSquadUuid')?.value?.trim() || '';
    const name = $('panelIntSquadName')?.value?.trim() || '';
    const inbounds = Array.from(document.querySelectorAll('#panelIntSquadInboundsList .panel-int-squad-inb-chk:checked'))
      .map(el => el.value)
      .filter(Boolean);
    if (!name) {
      toast('نام اسکواد داخلی الزامی است.');
      return;
    }
    const res = await window.api?.saveInternalSquad?.({ uuid, name, inbounds });
    if (res && res.ok) {
      toast(`✅ ${res.message}`);
      closeIntSquadModal();
      haptic('success');
      await fetchOverview(true);
    } else {
      toast(`⚠️ ${res?.error || 'خطا در ذخیره اسکواد داخلی'}`);
    }
  }

  function deleteIntSquad(uuid, name) {
    confirmAction({
      title: 'حذف اسکواد داخلی',
      message: `آیا از حذف اسکواد داخلی «${name || uuid}» از پنل مطمئن هستید؟`,
      btnText: 'حذف اسکواد',
      onConfirm: async () => {
        const res = await window.api?.deleteInternalSquad?.(uuid);
        if (res && res.ok) {
          toast(`✅ ${res.message}`);
          haptic('success');
          await fetchOverview(true);
        } else {
          toast(`⚠️ ${res?.error || 'خطا در حذف اسکواد داخلی'}`);
        }
      },
    });
  }

  function renderExternalSquads() {
    const listEl = $('panelExternalSquadsList');
    if (!listEl) return;
    const squads = Array.isArray(panelState.external_squads) ? panelState.external_squads : [];
    if (!squads.length) {
      listEl.innerHTML = '<div class="p-4 text-center text-xs t-muted card-inset rounded-2xl border border-card-border">هیچ External Squad فعالی در پنل یافت نشد.</div>';
      return;
    }
    listEl.innerHTML = squads.map(sq => {
      const uuid = String(sq.uuid || '');
      const count = sq.info?.membersCount ?? sq.membersCount ?? 0;
      return `
        <div class="card p-3 rounded-2xl border border-card-border flex items-center justify-between gap-2">
          <div class="flex items-center gap-1 shrink-0">
            <button type="button" onclick="window.panelCtrl.openSquadUsersModal('external', '${escapeHtml(uuid)}', '${escapeHtml(sq.name || '')}')" class="px-2 py-1 rounded-xl border border-card-border t-main hover:border-cyan-500/40 text-[10.5px] font-bold transition active:scale-95">اعضا</button>
            <button type="button" onclick="window.panelCtrl.openExtSquadModal('${escapeHtml(uuid)}')" class="p-1.5 rounded-xl border border-cyan-500/35 t-accent hover:bg-cyan-500/10 transition active:scale-95" title="ویرایش اسکواد خارجی">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
            </button>
            <button type="button" onclick="window.panelCtrl.deleteExtSquad('${escapeHtml(uuid)}', '${escapeHtml(sq.name || '')}')" class="p-1.5 rounded-xl border border-rose-500/35 t-danger hover:bg-rose-500/10 transition active:scale-95" title="حذف اسکواد خارجی">
              ${TRASH_ICON_SVG}
            </button>
          </div>
          <div class="min-w-0 flex-1 text-left" dir="ltr">
            <b class="text-xs t-main block truncate font-en">${escapeHtml(sq.name || 'Squad')}</b>
            <span class="text-[10.5px] t-muted block mt-0.5" dir="rtl"><span class="num-bidi">${Number(count)}</span> عضو در اسکواد</span>
          </div>
        </div>
      `;
    }).join('');
  }

  function openExtSquadModal(squadUuid = '') {
    const modal = $('panelExtSquadEditorModal');
    if (!modal) return;
    const hit = squadUuid ? (panelState.external_squads || []).find(s => String(s.uuid) === String(squadUuid)) : null;
    if ($('panelExtSquadEditTitle')) $('panelExtSquadEditTitle').innerText = hit ? 'ویرایش اسکواد خارجی' : 'ساخت اسکواد خارجی جدید';
    if ($('panelExtSquadEditUuid')) $('panelExtSquadEditUuid').value = hit?.uuid || '';
    if ($('panelExtSquadEditName')) $('panelExtSquadEditName').value = hit?.name || '';
    const hdrObj = hit?.responseHeadersAdd || hit?.responseHeaders || null;
    if ($('panelExtSquadHeadersJson')) {
      $('panelExtSquadHeadersJson').value = hdrObj && typeof hdrObj === 'object' ? JSON.stringify(hdrObj, null, 2) : '';
    }
    modal.classList.remove('hidden');
    haptic('selection');
  }

  function closeExtSquadModal() {
    $('panelExtSquadEditorModal')?.classList.add('hidden');
  }

  async function saveExtSquad() {
    const uuid = $('panelExtSquadEditUuid')?.value?.trim() || '';
    const name = $('panelExtSquadEditName')?.value?.trim() || '';
    const rawHdrs = $('panelExtSquadHeadersJson')?.value?.trim() || '';
    if (!name) {
      toast('نام اسکواد خارجی الزامی است.');
      return;
    }
    let headers_add = null;
    if (rawHdrs) {
      try {
        const parsed = JSON.parse(rawHdrs);
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('JSON آبجکت نیست');
        headers_add = parsed;
      } catch (_err) {
        toast('فرمت JSON هدرها معتبر نیست (مثلاً {"X-Custom": "1"}).');
        return;
      }
    }
    const res = await window.api?.saveExternalSquad?.({ uuid, name, headers_add });
    if (res && res.ok) {
      toast(`✅ ${res.message}`);
      closeExtSquadModal();
      haptic('success');
      await fetchOverview(true);
    } else {
      toast(`⚠️ ${res?.error || 'خطا در ذخیره اسکواد خارجی'}`);
    }
  }

  function deleteExtSquad(uuid, name) {
    confirmAction({
      title: 'حذف اسکواد خارجی',
      message: `آیا از حذف اسکواد خارجی «${name || uuid}» از پنل مطمئن هستید؟`,
      btnText: 'حذف اسکواد',
      onConfirm: async () => {
        const res = await window.api?.deleteExternalSquad?.(uuid);
        if (res && res.ok) {
          toast(`✅ ${res.message}`);
          haptic('success');
          await fetchOverview(true);
        } else {
          toast(`⚠️ ${res?.error || 'خطا در حذف اسکواد خارجی'}`);
        }
      },
    });
  }

  async function _loadSquadUserSearchResults() {
    const listEl = $('panelSquadUserPickerList');
    if (!listEl) return;
    const q = $('panelSquadUserSearchInput')?.value?.trim() || '';
    const plan_id = $('panelSquadPlanFilterSelect')?.value?.trim() || '';
    listEl.innerHTML = '<div class="p-3 text-center text-[11px] t-muted">در حال جستجو...</div>';
    try {
      const res = await window.api?.searchPanelUsers?.({ q, plan_id });
      const users = (res && res.ok && Array.isArray(res.users)) ? res.users : [];
      if (!users.length) {
        listEl.innerHTML = '<div class="p-3 text-center text-[11px] t-muted">کاربری با این مشخصات یافت نشد.</div>';
        return;
      }
      const targetSquadUuid = $('panelExtSquadUuid')?.value?.trim() || '';
      listEl.innerHTML = users.map(u => {
        const key = String(u.uuid || u.id || '');
        const checked = selectedSquadUserMap.has(key) ? 'checked' : '';
        const inSquad = activeSquadType === 'internal'
          ? (u.internal_squads || []).includes(targetSquadUuid)
          : String(u.external_squad_uuid || '') === targetSquadUuid;
        const memberStatusIcon = inSquad
          ? '<span class="inline-flex items-center justify-center w-4 h-4 rounded-full bg-emerald-500/15 border border-emerald-500/40 t-success shrink-0" title="عضو این اسکواد"><svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg></span>'
          : '<span class="inline-flex items-center justify-center w-4 h-4 rounded-full bg-slate-500/15 border border-card-border t-subtle shrink-0" title="عضو نیست"><svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M20 12H4"/></svg></span>';
        return `
          <label class="card-inset px-2.5 py-2 rounded-xl border border-card-border flex items-center justify-between gap-2 text-[11px] cursor-pointer hover:border-cyan-500/40 transition">
            <input type="checkbox" class="squad-user-chk accent-cyan-500 rounded shrink-0" value="${escapeHtml(key)}" data-id="${escapeHtml(String(u.id || ''))}" ${checked} onchange="window.panelCtrl.toggleSquadUserPick('${escapeHtml(key)}', '${escapeHtml(String(u.id || ''))}', this.checked)" />
            <div class="min-w-0 flex-1 text-left" dir="ltr">
              <div class="flex items-center justify-start gap-1.5 min-w-0">
                <span class="font-bold t-main truncate font-en">${escapeHtml(u.username || key)}</span>
                ${memberStatusIcon}
              </div>
              <span class="text-[10px] t-muted block">${u.telegram_id ? `TG:${escapeHtml(u.telegram_id)} • ` : ''}${escapeHtml(u.status || '')}</span>
            </div>
          </label>
        `;
      }).join('');
    } catch (_err) {
      listEl.innerHTML = '<div class="p-3 text-center text-[11px] t-danger">خطا در دریافت کاربران</div>';
    }
  }

  function toggleSquadUserPick(uuid, idStr, isChecked) {
    if (!uuid) return;
    if (isChecked) {
      selectedSquadUserMap.set(uuid, { uuid, id: idStr && /^\d+$/.test(idStr) ? Number(idStr) : undefined });
    } else {
      selectedSquadUserMap.delete(uuid);
    }
    if ($('panelSquadSelectedCount')) {
      $('panelSquadSelectedCount').innerHTML = `<span class="num-bidi font-bold">${selectedSquadUserMap.size}</span> <span>انتخاب</span>`;
    }
  }

  async function openSquadUsersModal(squadType, squadUuid, squadName) {
    const modal = $('panelExtSquadUsersModal');
    if (!modal) return;
    activeSquadType = squadType === 'internal' ? 'internal' : 'external';
    selectedSquadUserMap.clear();
    if ($('panelExtSquadUuid')) $('panelExtSquadUuid').value = squadUuid;
    if ($('panelExtSquadTitle')) {
      const kindLabel = activeSquadType === 'internal' ? 'اسکواد داخلی' : 'اسکواد خارجی';
      $('panelExtSquadTitle').innerText = `اعضای ${kindLabel}: ${squadName || squadUuid}`;
    }
    if ($('panelExtSquadUserUuids')) $('panelExtSquadUserUuids').value = '';
    if ($('panelSquadUserSearchInput')) $('panelSquadUserSearchInput').value = '';
    if ($('panelSquadSelectedCount')) {
      $('panelSquadSelectedCount').innerHTML = '<span class="num-bidi font-bold">0</span> <span>انتخاب</span>';
    }

    const planSel = $('panelSquadPlanFilterSelect');
    if (planSel && planSel.options.length <= 1) {
      try {
        const res = await window.api?.getPlans?.();
        const plans = (res && res.ok && Array.isArray(res.plans)) ? res.plans : [];
        planSel.innerHTML = '<option value="">همه تعرفه‌های ربات</option>' + plans.map(p => `<option value="${p.id}">${escapeHtml(p.name || p.title || '')}</option>`).join('');
      } catch (_e) {}
    } else if (planSel) {
      planSel.value = '';
    }

    modal.classList.remove('hidden');
    haptic('selection');
    _loadSquadUserSearchResults();
  }

  function openExtSquadUsersModal(squadUuid, squadName) {
    return openSquadUsersModal('external', squadUuid, squadName);
  }

  function closeExtSquadUsersModal() {
    selectedSquadUserMap.clear();
    $('panelExtSquadUsersModal')?.classList.add('hidden');
  }

  async function submitExtSquadUsers(action = 'add') {
    const squadUuid = $('panelExtSquadUuid')?.value?.trim();
    const raw = $('panelExtSquadUserUuids')?.value || '';
    const manualRefs = raw.split(/[\s,]+/).map(s => s.trim()).filter(Boolean).map(u => ({ uuid: u }));
    const merged = [...Array.from(selectedSquadUserMap.values()), ...manualRefs];
    const dedup = new Map();
    merged.forEach(item => { if (item?.uuid) dedup.set(item.uuid, item); });
    const userRefs = Array.from(dedup.values());
    const userUuids = userRefs.map(x => x.uuid);
    if (!squadUuid || !userRefs.length) {
      toast('حداقل یک کاربر انتخاب یا UUID وارد کنید.');
      return;
    }
    const apiCall = activeSquadType === 'internal'
      ? window.api?.updateInternalSquadUsers
      : window.api?.updateExternalSquadUsers;
    const res = await apiCall?.(squadUuid, userUuids, action, userRefs);
    if (res && res.ok) {
      toast(`✅ ${res.message}`);
      closeExtSquadUsersModal();
      haptic('success');
      await fetchOverview(true);
    } else {
      toast(`⚠️ ${res?.error || 'خطا در بروزرسانی اسکواد'}`);
    }
  }

  // --- 3. Config Profiles & Snippets ---
  function renderConfigProfiles() {
    const listEl = $('panelConfigProfilesList');
    if (!listEl) return;
    const profiles = Array.isArray(panelState.config_profiles) ? panelState.config_profiles : [];
    if (!profiles.length) {
      listEl.innerHTML = '<div class="p-4 text-center text-xs t-muted card-inset rounded-2xl border border-card-border">پروفایل کانفیگی یافت نشد.</div>';
      return;
    }
    listEl.innerHTML = profiles.map(p => {
      const uuid = String(p.uuid || '');
      const inbounds = Array.isArray(p.inbounds) ? p.inbounds : [];
      return `
        <div class="card p-3 rounded-2xl border border-card-border space-y-2">
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-1 shrink-0">
              <button type="button" onclick="window.panelCtrl.openConfigProfileModal('${escapeHtml(uuid)}')" class="p-1.5 rounded-xl border border-cyan-500/35 t-accent hover:bg-cyan-500/10 transition active:scale-95" title="ویرایش پروفایل">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
              </button>
              <button type="button" onclick="window.panelCtrl.deleteConfigProfile('${escapeHtml(uuid)}', '${escapeHtml(p.name || '')}')" class="p-1.5 rounded-xl border border-rose-500/35 t-danger hover:bg-rose-500/10 transition active:scale-95" title="حذف پروفایل">
                ${TRASH_ICON_SVG}
              </button>
            </div>
            <div class="flex items-center gap-2 min-w-0 flex-1 justify-end">
              <span class="badge badge-info text-[10px] shrink-0">${inbounds.length} اینباند</span>
              <b class="text-xs t-main truncate font-en text-left" dir="ltr">${escapeHtml(p.name || 'Profile')}</b>
            </div>
          </div>
          ${inbounds.length ? `
            <div class="flex flex-wrap gap-1.5" dir="ltr">
              ${inbounds.map(i => `<span class="badge badge-neutral text-[10px] font-en">${escapeHtml(i.tag || i.type || 'Inbound')} (${escapeHtml(i.type || '')}:${i.port || ''})</span>`).join('')}
            </div>
          ` : ''}
        </div>
      `;
    }).join('');
  }

  function openConfigProfileModal(profileUuid = '') {
    const modal = $('panelConfigProfileEditorModal');
    if (!modal) return;
    const hit = profileUuid ? (panelState.config_profiles || []).find(p => String(p.uuid) === String(profileUuid)) : null;
    if ($('panelConfigProfileModalTitle')) $('panelConfigProfileModalTitle').innerText = hit ? 'ویرایش پروفایل Xray' : 'ساخت پروفایل کانفیگ Xray';
    if ($('panelConfigProfileUuid')) $('panelConfigProfileUuid').value = hit?.uuid || '';
    if ($('panelConfigProfileName')) $('panelConfigProfileName').value = hit?.name || '';
    const starter = hit?.config || { log: { loglevel: 'warning' }, inbounds: hit?.inbounds || [], outbounds: [{ protocol: 'freedom', tag: 'direct' }] };
    if ($('panelConfigProfileJson')) {
      $('panelConfigProfileJson').value = typeof starter === 'string' ? starter : JSON.stringify(starter, null, 2);
    }
    modal.classList.remove('hidden');
    haptic('selection');
  }

  function closeConfigProfileModal() {
    $('panelConfigProfileEditorModal')?.classList.add('hidden');
  }

  async function saveConfigProfile() {
    const uuid = $('panelConfigProfileUuid')?.value?.trim() || '';
    const name = $('panelConfigProfileName')?.value?.trim() || '';
    const rawCfg = $('panelConfigProfileJson')?.value?.trim() || '';
    if (!name || !rawCfg) {
      toast('نام و محتوای JSON پروفایل الزامی است.');
      return;
    }
    let config;
    try {
      config = JSON.parse(rawCfg);
      if (!config || typeof config !== 'object' || Array.isArray(config)) throw new Error('Object required');
    } catch (_err) {
      toast('فرمت JSON پروفایل نامعتبر است.');
      return;
    }
    const res = await window.api?.saveConfigProfile?.({ uuid, name, config });
    if (res && res.ok) {
      toast(`✅ ${res.message}`);
      closeConfigProfileModal();
      haptic('success');
      await fetchOverview(true);
    } else {
      toast(`⚠️ ${res?.error || 'خطا در ذخیره پروفایل'}`);
    }
  }

  function deleteConfigProfile(uuid, name) {
    confirmAction({
      title: 'حذف پروفایل Xray',
      message: `پروفایل «${name || uuid}» از پنل حذف شود؟`,
      btnText: 'حذف پروفایل',
      onConfirm: async () => {
        const res = await window.api?.deleteConfigProfile?.(uuid);
        if (res && res.ok) {
          toast(`✅ ${res.message}`);
          haptic('success');
          await fetchOverview(true);
        } else {
          toast(`⚠️ ${res?.error || 'خطا در حذف پروفایل'}`);
        }
      },
    });
  }

  function renderSnippets() {
    const listEl = $('panelSnippetsList');
    if (!listEl) return;
    const snippets = Array.isArray(panelState.snippets) ? panelState.snippets : [];
    if (!snippets.length) {
      listEl.innerHTML = '<div class="p-4 text-center text-xs t-muted card-inset rounded-2xl border border-card-border">اسنیپتی تعریف نشده است.</div>';
      return;
    }
    listEl.innerHTML = snippets.map(s => {
      const name = String(s.name || '');
      const rawJson = typeof s.snippet === 'string' ? s.snippet : JSON.stringify(s.snippet ?? s.content ?? [], null, 2);
      const preview = rawJson.length > 110 ? `${rawJson.slice(0, 110)}...` : rawJson;
      return `
        <div class="card p-3 rounded-2xl border border-card-border space-y-1.5">
          <div class="flex items-center justify-between gap-2">
            <b class="text-xs t-main truncate font-en" dir="ltr">${escapeHtml(name)}</b>
            <div class="flex items-center gap-1 shrink-0">
              <button type="button" onclick="window.panelCtrl.openSnippetModal('${escapeHtml(name)}')" class="p-1.5 rounded-xl border border-cyan-500/35 t-accent hover:bg-cyan-500/10 transition active:scale-95" title="ویرایش اسنیپت">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
              </button>
              <button type="button" onclick="window.panelCtrl.deleteSnippet('${escapeHtml(name)}')" class="p-1.5 rounded-xl border border-rose-500/35 t-danger hover:bg-rose-500/10 transition active:scale-95" title="حذف اسنیپت">
                ${TRASH_ICON_SVG}
              </button>
            </div>
          </div>
          <pre class="text-[10px] t-muted card-inset p-2 rounded-xl overflow-x-auto font-sans font-en" dir="ltr">${escapeHtml(preview)}</pre>
        </div>
      `;
    }).join('');
  }

  function openSnippetModal(name = '') {
    const modal = $('panelSnippetEditorModal');
    if (!modal) return;
    const hit = name ? (panelState.snippets || []).find(s => String(s.name) === String(name)) : null;
    if ($('panelSnippetModalTitle')) $('panelSnippetModalTitle').innerText = hit ? 'ویرایش اسنیپت کانفیگ' : 'ساخت اسنیپت جدید';
    if ($('panelSnippetIsEdit')) $('panelSnippetIsEdit').value = hit ? '1' : '0';
    if ($('panelSnippetName')) {
      $('panelSnippetName').value = hit?.name || '';
      $('panelSnippetName').readOnly = Boolean(hit);
    }
    if ($('panelSnippetJson')) {
      const val = hit ? (typeof hit.snippet === 'string' ? hit.snippet : JSON.stringify(hit.snippet ?? [], null, 2)) : '[\n  {\n    "type": "field",\n    "domain": ["geosite:category-ads-all"],\n    "outboundTag": "block"\n  }\n]';
      $('panelSnippetJson').value = val;
    }
    modal.classList.remove('hidden');
    haptic('selection');
  }

  function closeSnippetModal() {
    $('panelSnippetEditorModal')?.classList.add('hidden');
  }

  async function saveSnippet() {
    const name = $('panelSnippetName')?.value?.trim() || '';
    const jsonStr = $('panelSnippetJson')?.value?.trim() || '';
    const isEdit = $('panelSnippetIsEdit')?.value === '1';
    if (!name || !jsonStr) {
      toast('نام و کد JSON اسنیپت الزامی است.');
      return;
    }
    let parsed;
    try {
      parsed = JSON.parse(jsonStr);
    } catch (e) {
      toast('فرمت JSON صحیح نیست!');
      return;
    }
    const res = await window.api?.savePanelSnippet?.(name, parsed, isEdit);
    if (res && res.ok) {
      toast(`✅ ${res.message}`);
      closeSnippetModal();
      haptic('success');
      await fetchOverview(true);
    } else {
      toast(`⚠️ ${res?.error || 'خطا در ذخیره اسنیپت'}`);
    }
  }

  function deleteSnippet(name) {
    confirmAction({
      title: 'حذف اسنیپت',
      message: `آیا از حذف اسنیپت «${name}» از پنل Remnawave مطمئن هستید؟`,
      btnText: 'حذف اسنیپت',
      onConfirm: async () => {
        const res = await window.api?.deletePanelSnippet?.(name);
        if (res && res.ok) {
          toast(`✅ ${res.message}`);
          haptic('success');
          await fetchOverview(true);
        } else {
          toast(`⚠️ ${res?.error || 'خطا در حذف اسنیپت'}`);
        }
      },
    });
  }

  // --- 4. Infra Providers CRUD & API Tokens ---
  function renderInfraProviders() {
    const listEl = $('panelProvidersManageList');
    if (!listEl) return;
    const providers = Array.isArray(panelState.infra_providers) ? panelState.infra_providers : [];
    const billingNodes = Array.isArray(panelState.infra_billing_nodes) ? panelState.infra_billing_nodes : [];

    if (!providers.length) {
      listEl.innerHTML = '<div class="p-4 text-center text-xs t-muted card-inset rounded-2xl border border-card-border">ارائه‌دهنده‌ای در پنل ثبت نشده است.</div>';
      return;
    }
    listEl.innerHTML = providers.map(p => {
      const uuid = String(p.uuid || '');
      const linkedCount = billingNodes.filter(bn => String(bn.providerUuid || bn.provider?.uuid || '') === uuid).length;
      const loginHref = window.safeHttpUrl ? window.safeHttpUrl(p.login) : '';
      const iconHref = window.safeHttpUrl ? window.safeHttpUrl(p.icon_url) : '';
      return `
        <div class="card p-3 rounded-2xl border border-card-border flex items-center justify-between gap-2">
          <div class="flex items-center gap-1 shrink-0">
            <button type="button" onclick="window.panelCtrl.openProviderModal('${escapeHtml(uuid)}')" class="p-1.5 rounded-xl border border-cyan-500/35 t-accent hover:bg-cyan-500/10 transition active:scale-95" title="ویرایش ارائه‌دهنده">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
            </button>
            <button type="button" onclick="window.panelCtrl.deleteProvider('${escapeHtml(uuid)}', '${escapeHtml(p.name || '')}')" class="p-1.5 rounded-xl border border-rose-500/35 t-danger hover:bg-rose-500/10 transition active:scale-95" title="حذف ارائه‌دهنده">
              ${TRASH_ICON_SVG}
            </button>
            ${loginHref ? `<button type="button" onclick="window.panelCtrl.openExternalUrl('${escapeHtml(loginHref)}')" class="px-2 py-1 rounded-xl border border-emerald-500/35 t-success hover:bg-emerald-500/10 text-[10.5px] font-bold transition active:scale-95" title="ورود به پنل ارائه‌دهنده">ورود</button>` : ''}
          </div>
          <div class="min-w-0 text-left flex-1" dir="ltr">
            <div class="flex items-center gap-1.5 min-w-0">
              ${iconHref ? `<img src="${escapeHtml(iconHref)}" alt="" class="w-4 h-4 rounded shrink-0 object-contain" onerror="this.style.display='none'" />` : ''}
              <b class="text-xs t-main block truncate font-en">${escapeHtml(p.name || '')}</b>
            </div>
            <span class="text-[10.5px] t-muted block mt-0.5 truncate" dir="rtl"><span class="num-bidi font-bold">${linkedCount}</span> سرور متصل</span>
          </div>
        </div>
      `;
    }).join('');
  }

  function openProviderModal(providerUuid = '', onSaved = null) {
    const modal = $('panelProviderEditorModal');
    if (!modal) return;
    onProviderSavedCallback = typeof onSaved === 'function' ? onSaved : null;
    const hit = providerUuid ? (panelState.infra_providers || []).find(p => String(p.uuid) === String(providerUuid)) : null;
    if ($('panelProviderModalTitle')) $('panelProviderModalTitle').innerText = hit ? 'ویرایش ارائه‌دهنده سرور' : 'افزودن ارائه‌دهنده جدید';
    if ($('panelProviderUuid')) $('panelProviderUuid').value = hit?.uuid || '';
    if ($('panelProviderName')) $('panelProviderName').value = hit?.name || '';
    if ($('panelProviderLoginUrl')) $('panelProviderLoginUrl').value = hit?.login || '';
    if ($('panelProviderFaviconUrl')) $('panelProviderFaviconUrl').value = hit?.icon_url || '';
    modal.classList.remove('hidden');
    haptic('selection');
  }

  function closeProviderModal() {
    $('panelProviderEditorModal')?.classList.add('hidden');
    onProviderSavedCallback = null;
  }

  async function saveProvider() {
    const uuid = $('panelProviderUuid')?.value?.trim() || '';
    const name = $('panelProviderName')?.value?.trim() || '';
    const login_url = $('panelProviderLoginUrl')?.value?.trim() || '';
    const favicon_link = $('panelProviderFaviconUrl')?.value?.trim() || '';
    if (!name) {
      toast('نام ارائه‌دهنده الزامی است.');
      return;
    }
    const res = await window.api?.saveInfraProvider?.({ uuid, name, login_url, favicon_link });
    if (res && res.ok) {
      toast(`✅ ${res.message}`);
      const cb = onProviderSavedCallback;
      if (window.adminActions) window.adminActions._cachedInfraProviders = null;
      closeProviderModal();
      haptic('success');
      await fetchOverview(true);
      if (cb) await cb(res.provider || {});
    } else {
      toast(`⚠️ ${res?.error || 'خطا در ثبت ارائه‌دهنده'}`);
    }
  }

  function deleteProvider(uuid, name) {
    confirmAction({
      title: 'حذف ارائه‌دهنده از پنل',
      message: `آیا از حذف «${name}» از پنل Remnawave مطمئن هستید؟`,
      btnText: 'حذف ارائه‌دهنده',
      onConfirm: async () => {
        const res = await window.api?.deleteInfraProvider?.(uuid);
        if (res && res.ok) {
          if (window.adminActions) window.adminActions._cachedInfraProviders = null;
          toast(`✅ ${res.message}`);
          haptic('success');
          await fetchOverview(true);
        } else {
          toast(`⚠️ ${res?.error || 'خطا در حذف ارائه‌دهنده'}`);
        }
      },
    });
  }

  function renderApiTokens() {
    const listEl = $('panelTokensList');
    const warnEl = $('panelTokensJwtNotice');
    if (!listEl) return;
    const info = panelState.api_tokens_info || {};
    if (warnEl) warnEl.classList.toggle('hidden', !info.jwt_required);
    if (info.jwt_required) {
      listEl.innerHTML = '';
      return;
    }
    const tokens = Array.isArray(info.tokens) ? info.tokens : [];
    if (!tokens.length) {
      listEl.innerHTML = '<div class="p-4 text-center text-xs t-muted card-inset rounded-2xl border border-card-border">توکنی یافت نشد.</div>';
      return;
    }
    listEl.innerHTML = tokens.map(t => `
      <div class="card p-2.5 rounded-2xl border border-card-border flex items-center justify-between gap-2">
        <div class="min-w-0 text-left flex-1" dir="ltr">
          <b class="text-xs t-main block truncate font-en">${escapeHtml(t.tokenName || t.name || 'API Token')}</b>
          <span class="text-[10px] t-muted block truncate">${escapeHtml(t.uuid || '')}</span>
        </div>
        <button type="button" onclick="window.panelCtrl.deleteToken('${escapeHtml(t.uuid || '')}', '${escapeHtml(t.tokenName || '')}')" class="p-1.5 rounded-xl border border-rose-500/35 t-danger hover:bg-rose-500/10 transition active:scale-95 shrink-0" title="ابطال توکن">
          ${TRASH_ICON_SVG}
        </button>
      </div>
    `).join('');
  }

  function openTokenModal() {
    if ($('panelTokenName')) $('panelTokenName').value = '';
    $('panelTokenSecretResultBox')?.classList.add('hidden');
    $('panelTokenCreateModal')?.classList.remove('hidden');
    haptic('selection');
  }

  function closeTokenModal() {
    $('panelTokenCreateModal')?.classList.add('hidden');
  }

  async function createToken() {
    const name = $('panelTokenName')?.value?.trim() || '';
    if (!name) {
      toast('نام توکن الزامی است.');
      return;
    }
    const res = await window.api?.createPanelApiToken?.(name);
    if (res && res.ok) {
      toast(`✅ ${res.message}`);
      const secret = res.token?.token || res.token?.apiKey || '';
      if (secret && $('panelTokenSecretOutput')) {
        $('panelTokenSecretOutput').innerText = secret;
        $('panelTokenSecretResultBox')?.classList.remove('hidden');
      } else {
        closeTokenModal();
      }
      haptic('success');
      await fetchOverview(true);
    } else {
      toast(`⚠️ ${res?.error || 'ساخت توکن نیازمند Admin JWT در پنل است'}`);
    }
  }

  function deleteToken(uuid, name) {
    confirmAction({
      title: 'حذف توکن API',
      message: `توکن «${name || uuid}» بلافاصله از پنل ابطال شود؟`,
      btnText: 'ابطال توکن',
      onConfirm: async () => {
        const res = await window.api?.deletePanelApiToken?.(uuid);
        if (res && res.ok) {
          toast(`✅ ${res.message}`);
          haptic('success');
          await fetchOverview(true);
        } else {
          toast(`⚠️ ${res?.error || 'خطا در حذف توکن'}`);
        }
      },
    });
  }

  let billsProviderFilter = '';

  function openExternalUrl(rawUrl) {
    const safe = window.safeHttpUrl ? window.safeHttpUrl(rawUrl) : '';
    if (!safe) return;
    if (window.Telegram?.WebApp?.openLink) window.Telegram.WebApp.openLink(safe);
    else window.open(safe, '_blank', 'noopener,noreferrer');
  }

  function setBillsProviderFilter(provUuid = '') {
    billsProviderFilter = provUuid || '';
    renderBillingHistory();
    haptic('selection');
  }

  function renderBillingHistory() {
    const listEl = $('panelBillsList');
    const filterEl = $('panelBillsFilterBar');
    const summaryEl = $('panelBillsSummaryBar');
    if (!listEl) return;
    const bills = Array.isArray(panelState.infra_billing_history) ? panelState.infra_billing_history : [];
    const providers = Array.isArray(panelState.infra_providers) ? panelState.infra_providers : [];
    const provMap = new Map(providers.map(p => [String(p.uuid), p.name]));
    const provCurrencies = panelState.provider_currencies || {};

    if (filterEl) {
      if (!providers.length || !bills.length) {
        filterEl.innerHTML = '';
      } else {
        const chipCls = (active) => active
          ? 'px-2.5 py-1 rounded-xl font-bold bg-cyan-600 text-white shadow shrink-0 whitespace-nowrap transition'
          : 'px-2.5 py-1 rounded-xl font-medium card-inset border border-card-border t-muted hover:t-main shrink-0 whitespace-nowrap transition';
        filterEl.innerHTML = `<button type="button" onclick="window.panelCtrl.setBillsProviderFilter('')" class="${chipCls(!billsProviderFilter)}">همه (${bills.length})</button>` +
          providers.map(p => {
            const pUid = String(p.uuid || '');
            return `<button type="button" onclick="window.panelCtrl.setBillsProviderFilter('${escapeHtml(pUid)}')" class="${chipCls(billsProviderFilter === pUid)} font-en" dir="ltr">${escapeHtml(p.name || pUid)}</button>`;
          }).join('');
      }
    }

    const filteredBills = billsProviderFilter
      ? bills.filter(b => String(b.providerUuid || b.provider?.uuid || '') === billsProviderFilter)
      : bills;

    if (summaryEl) {
      if (!filteredBills.length) {
        summaryEl.classList.add('hidden');
      } else {
        const totals = {};
        filteredBills.forEach(b => {
          const pUid = String(b.providerUuid || b.provider?.uuid || '');
          const curr = String(b.currency || b.provider?.currency || provCurrencies[pUid] || 'USD').toUpperCase();
          totals[curr] = (totals[curr] || 0) + Number(b.amount || 0);
        });
        const parts = Object.entries(totals).map(([curr, val]) => {
          const iconHtml = window.renderCurrencyIcon ? window.renderCurrencyIcon(curr) : curr;
          return `<span class="inline-flex items-center gap-1 font-sans num-bidi t-success font-bold" dir="ltr">${Number(val.toFixed(2)).toLocaleString('en-US')} ${iconHtml}</span>`;
        });
        summaryEl.innerHTML = `<span class="t-muted font-bold">مجموع (${filteredBills.length} مورد):</span><div class="flex items-center gap-2.5">${parts.join('<span class="t-subtle">|</span>')}</div>`;
        summaryEl.classList.remove('hidden');
      }
    }

    if (!filteredBills.length) {
      listEl.innerHTML = '<div class="p-4 text-center text-xs t-muted card-inset rounded-2xl border border-card-border">سابقه پرداختی ثبت نشده است.</div>';
      window.adminActions?.renderNodeBillingBillsHistory?.();
      return;
    }
    listEl.innerHTML = filteredBills.map(b => {
      const uuid = String(b.uuid || '');
      const provUuid = String(b.providerUuid || b.provider?.uuid || '');
      const provName = b.provider?.name || provMap.get(provUuid) || 'ارائه‌دهنده';
      const billedDate = b.billedAt ? String(b.billedAt).slice(0, 10) : '';
      const jalaliStr = billedDate && window.formatDateToJalali ? window.formatDateToJalali(billedDate) : billedDate;
      const billCurr = String(b.currency || b.provider?.currency || provCurrencies[provUuid] || 'USD').toUpperCase();
      const currIcon = window.renderCurrencyIcon ? window.renderCurrencyIcon(billCurr) : billCurr;
      return `
        <div class="card p-2.5 rounded-2xl border border-card-border flex items-center justify-between gap-2">
          <button type="button" onclick="window.panelCtrl.deleteBill('${escapeHtml(uuid)}')" class="p-1.5 rounded-xl border border-rose-500/35 t-danger hover:bg-rose-500/10 transition active:scale-95 shrink-0" title="حذف رکورد پرداخت" aria-label="حذف رکورد پرداخت">
            ${TRASH_ICON_SVG}
          </button>
          <div class="min-w-0 flex-1 text-left" dir="ltr">
            <div class="flex items-center justify-start gap-2 min-w-0">
              <b class="text-xs t-main truncate font-en">${escapeHtml(provName)}</b>
              <span class="badge badge-success text-[10px] inline-flex items-center gap-1 shrink-0" dir="ltr"><span class="num-bidi font-bold">${Number(b.amount || 0).toLocaleString('en-US')}</span>${currIcon}</span>
            </div>
            <span class="text-[10.5px] t-muted block mt-0.5 num-bidi">${escapeHtml(jalaliStr || billedDate || '—')}</span>
          </div>
        </div>
      `;
    }).join('');
    window.adminActions?.renderNodeBillingBillsHistory?.();
  }

  let activeBillNodeCtx = null;

  function _applySelectedBillProvider(uuidVal = '') {
    const providers = Array.isArray(panelState.infra_providers) ? panelState.infra_providers : [];
    const cleanUuid = String(uuidVal || '').trim();
    const hit = cleanUuid ? providers.find(p => String(p.uuid) === cleanUuid) : null;
    if ($('panelBillProviderSelect')) $('panelBillProviderSelect').value = hit ? String(hit.uuid) : '';
    const dispEl = $('panelBillProviderDisplay');
    if (dispEl) {
      if (hit) {
        dispEl.innerText = hit.name || hit.uuid;
        dispEl.setAttribute('dir', 'ltr');
      } else {
        dispEl.innerText = providers.length ? 'انتخاب ارائه‌دهنده...' : 'ابتدا ارائه‌دهنده تعریف کنید';
        dispEl.setAttribute('dir', 'rtl');
      }
    }
  }

  function _renderBillProviderPickerList() {
    const listEl = $('panelBillProviderPickerList');
    if (!listEl) return;
    const providers = Array.isArray(panelState.infra_providers) ? panelState.infra_providers : [];
    const curVal = $('panelBillProviderSelect')?.value || '';
    if (!providers.length) {
      listEl.innerHTML = '<div class="p-4 text-center text-xs t-muted card-inset rounded-2xl border border-card-border">ارائه‌دهنده‌ای در پنل ثبت نشده است.</div>';
      return;
    }
    listEl.innerHTML = providers.map(p => renderModalPickerRow({
      onClick: `window.panelCtrl.selectBillProvider('${escapeHtml(p.uuid)}')`,
      title: p.name || p.uuid,
      sub: p.login || '',
      selected: String(curVal) === String(p.uuid),
      isEnglish: true,
      rowDir: 'ltr',
      subDir: 'ltr',
    })).join('');
  }

  function openBillProviderModal() {
    const modal = $('panelBillProviderPickerModal');
    if (!modal) return;
    _renderBillProviderPickerList();
    modal.classList.remove('hidden');
    haptic('selection');
  }

  function closeBillProviderModal() {
    $('panelBillProviderPickerModal')?.classList.add('hidden');
  }

  function selectBillProvider(uuidVal = '') {
    _applySelectedBillProvider(uuidVal);
    closeBillProviderModal();
    haptic('selection');
  }

  async function openBillModal(prefillProviderUuid = '', prefillAmount = '', nodeCtx = null) {
    const modal = $('panelBillCreateModal');
    if (!modal) return;
    if (!panelState.loaded) await fetchOverview(false);
    const providers = Array.isArray(panelState.infra_providers) ? panelState.infra_providers : [];
    _applySelectedBillProvider(prefillProviderUuid || providers[0]?.uuid || '');
    if ($('panelBillAmount')) $('panelBillAmount').value = prefillAmount || '';
    const todayIso = new Date().toISOString().slice(0, 10);
    if ($('panelBillDate')) $('panelBillDate').value = todayIso;

    activeBillNodeCtx = (nodeCtx && nodeCtx.nodeUuid) ? nodeCtx : null;
    const extendWrap = $('panelBillExtendWrap');
    const extendChk = $('panelBillExtendNextMonth');
    const extendHint = $('panelBillExtendHint');
    if (extendWrap) {
      if (activeBillNodeCtx) {
        extendWrap.classList.remove('hidden');
        if (extendChk) extendChk.checked = true;
        if (extendHint) {
          extendHint.innerText = `برای سرور «${activeBillNodeCtx.nodeName || activeBillNodeCtx.nodeUuid}» و سینک در پنل`;
        }
      } else {
        extendWrap.classList.add('hidden');
        if (extendChk) extendChk.checked = false;
      }
    }

    modal.classList.remove('hidden');
    haptic('selection');
  }

  function closeBillModal() {
    activeBillNodeCtx = null;
    closeBillProviderModal();
    $('panelBillCreateModal')?.classList.add('hidden');
  }

  async function createBill() {
    const provider_uuid = $('panelBillProviderSelect')?.value?.trim() || '';
    const amount = parseFloat($('panelBillAmount')?.value || '0');
    const billed_at = $('panelBillDate')?.value?.trim() || '';
    if (!provider_uuid || isNaN(amount) || amount <= 0) {
      toast('ارائه‌دهنده و مبلغ معتبر الزامی است.');
      return;
    }
    const payload = { provider_uuid, amount, billed_at };
    if (activeBillNodeCtx?.nodeUuid && $('panelBillExtendNextMonth')?.checked) {
      payload.node_uuid = activeBillNodeCtx.nodeUuid;
      payload.extend_days = 30;
      if (activeBillNodeCtx.currentDueDate) payload.current_due_date = activeBillNodeCtx.currentDueDate;
    }
    const res = await window.api?.createInfraBill?.(payload);
    if (res && res.ok) {
      if (res.new_due_date) {
        const dueInput = $('nodeBillingDueDate');
        if (dueInput) {
          dueInput.value = res.new_due_date;
          dueInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
        const jalaliPreview = $('nodeBillingJalaliPreview');
        if (jalaliPreview) {
          jalaliPreview.innerText = window.formatDateToJalali ? window.formatDateToJalali(res.new_due_date) : res.new_due_date;
        }
      }
      if (res.panel_sync_warning) {
        toast(`✅ پرداخت ثبت شد اما سینک سررسید انجام نشد: ${res.panel_sync_warning}`);
      } else {
        toast(`✅ ${res.message}`);
      }
      closeBillModal();
      haptic('success');
      await fetchOverview(true);
      if (window.syncAdminOverview) window.syncAdminOverview(true);
    } else {
      toast(`⚠️ ${res?.error || 'خطا در ثبت پرداخت'}`);
    }
  }

  function deleteBill(uuid) {
    confirmAction({
      title: 'حذف سابقه پرداخت',
      message: 'آیا از حذف این رکورد پرداخت (Bill Record) از پنل مطمئن هستید؟',
      btnText: 'حذف رکورد',
      onConfirm: async () => {
        const res = await window.api?.deleteInfraBill?.(uuid);
        if (res && res.ok) {
          toast(`✅ ${res.message}`);
          haptic('success');
          await fetchOverview(true);
        } else {
          toast(`⚠️ ${res?.error || 'خطا در حذف رکورد'}`);
        }
      },
    });
  }

  window.panelCtrl = {
    fetchOverview,
    switchSubSection,
    filterHosts,
    setHostsPage,
    toggleHostSelection,
    toggleSelectAllHosts,
    toggleSingleHost,
    runBulkHosts,
    openHostModal,
    closeHostModal,
    openHostInboundModal,
    closeHostInboundModal,
    selectHostInbound,
    openHostSquadsModal,
    closeHostSquadsModal,
    setHostSquadMode,
    toggleHostSquadSelection,
    applyHostSquadsModal,
    saveHost,
    saveSubSettings,
    openIntSquadModal,
    closeIntSquadModal,
    saveIntSquad,
    deleteIntSquad,
    openExtSquadModal,
    closeExtSquadModal,
    saveExtSquad,
    deleteExtSquad,
    openSquadUsersModal,
    toggleSquadUserPick,
    searchSquadUsers: _loadSquadUserSearchResults,
    openExtSquadUsersModal,
    closeExtSquadUsersModal,
    submitExtSquadUsers,
    openConfigProfileModal,
    closeConfigProfileModal,
    saveConfigProfile,
    deleteConfigProfile,
    openSnippetModal,
    closeSnippetModal,
    saveSnippet,
    deleteSnippet,
    openProviderModal,
    closeProviderModal,
    saveProvider,
    deleteProvider,
    openBillModal,
    closeBillModal,
    openBillProviderModal,
    closeBillProviderModal,
    selectBillProvider,
    createBill,
    deleteBill,
    setBillsProviderFilter,
    openExternalUrl,
    openTokenModal,
    closeTokenModal,
    createToken,
    deleteToken,
    confirmAction,
    closeConfirmModal,
    executeConfirmAction,
    getConfigProfiles: () => panelState.config_profiles || [],
    getBillingHistory: () => panelState.infra_billing_history || [],
    getInfraBillingNodes: () => panelState.infra_billing_nodes || [],
    getProviderCurrency: (provUuid) => (panelState.provider_currencies || {})[String(provUuid || '')] || '',
  };
})(window);
