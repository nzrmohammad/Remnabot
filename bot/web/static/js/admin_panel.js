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
  let selectedHostUuids = new Set();
  let hostSearchQuery = '';
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
    const activeCls = 'flex-1 py-1.5 px-2 rounded-xl text-[11px] font-bold transition bg-cyan-600 text-white shadow whitespace-nowrap';
    const inactiveCls = 'flex-1 py-1.5 px-2 rounded-xl text-[11px] font-medium transition t-muted hover:t-main whitespace-nowrap';
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
    const icon = $('refreshPanelControlIcon');
    if (icon) icon.classList.add('animate-spin');

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
      if (icon) setTimeout(() => icon.classList.remove('animate-spin'), 300);
    }
    return null;
  }

  function renderAll() {
    renderHosts();
    renderSubscriptionSettings();
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

    if (filtered.length === 0) {
      listEl.innerHTML = '<div class="p-5 text-center text-xs t-muted card-inset rounded-2xl border border-card-border">هیچ هاستی یافت نشد.</div>';
      return;
    }

    listEl.innerHTML = filtered.map(h => {
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
          <div class="flex flex-wrap items-center justify-between gap-1.5 pt-1.5 border-t border-card-border text-[10.5px] t-muted">
            <div class="flex flex-wrap items-center gap-1">
              ${squadBadge}
              ${tags.map(t => `<span class="badge badge-info text-[10px] font-en" dir="ltr">${escapeHtml(t)}</span>`).join('')}
            </div>
            <span class="inline-flex items-center gap-1 font-en truncate max-w-full" dir="ltr"><span>SNI:</span><b class="t-main">${escapeHtml(h.sni || '—')}</b></span>
          </div>
        </div>
      `;
    }).join('');
  }

  function filterHosts(q = '') {
    hostSearchQuery = q;
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

  function openHostModal(hostUuid = '') {
    const modal = $('panelHostEditorModal');
    if (!modal) return;
    const h = hostUuid ? (panelState.hosts || []).find(x => String(x.uuid) === String(hostUuid)) : null;

    if ($('panelHostModalTitle')) $('panelHostModalTitle').innerText = h ? 'ویرایش هاست پنل' : 'افزودن هاست جدید';
    if ($('panelHostUuid')) $('panelHostUuid').value = h?.uuid || '';
    if ($('panelHostRemark')) $('panelHostRemark').value = h?.remark || '';
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
          <button type="button" onclick="window.panelCtrl.openExtSquadUsersModal('${escapeHtml(uuid)}', '${escapeHtml(sq.name || '')}')" class="btn btn-secondary px-2.5 py-1.5 text-[11px] rounded-xl font-bold shrink-0">مدیریت اعضا</button>
          <div class="min-w-0 flex-1 text-left" dir="ltr">
            <b class="text-xs t-main block truncate font-en">${escapeHtml(sq.name || 'Squad')}</b>
            <span class="text-[10.5px] t-muted block mt-0.5" dir="rtl"><span class="num-bidi">${Number(count)}</span> عضو در اسکواد</span>
          </div>
        </div>
      `;
    }).join('');
  }

  function openExtSquadUsersModal(squadUuid, squadName) {
    const modal = $('panelExtSquadUsersModal');
    if (!modal) return;
    if ($('panelExtSquadUuid')) $('panelExtSquadUuid').value = squadUuid;
    if ($('panelExtSquadTitle')) $('panelExtSquadTitle').innerText = `اعضای اسکواد: ${squadName || squadUuid}`;
    if ($('panelExtSquadUserUuids')) $('panelExtSquadUserUuids').value = '';
    modal.classList.remove('hidden');
    haptic('selection');
  }

  function closeExtSquadUsersModal() {
    $('panelExtSquadUsersModal')?.classList.add('hidden');
  }

  async function submitExtSquadUsers(action = 'add') {
    const squadUuid = $('panelExtSquadUuid')?.value?.trim();
    const raw = $('panelExtSquadUserUuids')?.value || '';
    const userUuids = raw.split(/[\s,]+/).map(s => s.trim()).filter(Boolean);
    if (!squadUuid || !userUuids.length) {
      toast('لطفاً حداقل یک UUID کاربر وارد کنید.');
      return;
    }
    const res = await window.api?.updateExternalSquadUsers?.(squadUuid, userUuids, action);
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
      const inbounds = Array.isArray(p.inbounds) ? p.inbounds : [];
      return `
        <div class="card p-3 rounded-2xl border border-card-border space-y-2">
          <div class="flex items-center justify-between gap-2">
            <span class="badge badge-info text-[10px] shrink-0">${inbounds.length} اینباند</span>
            <b class="text-xs t-main truncate font-en text-left" dir="ltr">${escapeHtml(p.name || 'Profile')}</b>
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
      return `
        <div class="card p-3 rounded-2xl border border-card-border flex items-center justify-between gap-2">
          <div class="flex items-center gap-1 shrink-0">
            <button type="button" onclick="window.panelCtrl.openProviderModal('${escapeHtml(uuid)}')" class="p-1.5 rounded-xl border border-cyan-500/35 t-accent hover:bg-cyan-500/10 transition active:scale-95" title="ویرایش ارائه‌دهنده">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
            </button>
            <button type="button" onclick="window.panelCtrl.deleteProvider('${escapeHtml(uuid)}', '${escapeHtml(p.name || '')}')" class="p-1.5 rounded-xl border border-rose-500/35 t-danger hover:bg-rose-500/10 transition active:scale-95" title="حذف ارائه‌دهنده">
              ${TRASH_ICON_SVG}
            </button>
          </div>
          <div class="min-w-0 text-left flex-1" dir="ltr">
            <b class="text-xs t-main block truncate font-en">${escapeHtml(p.name || '')}</b>
            <span class="text-[10.5px] t-muted block truncate">${linkedCount} سرور متصل${p.login ? ` • ${escapeHtml(p.login)}` : ''}</span>
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

  function renderBillingHistory() {
    const listEl = $('panelBillsList');
    if (!listEl) return;
    const bills = Array.isArray(panelState.infra_billing_history) ? panelState.infra_billing_history : [];
    const providers = Array.isArray(panelState.infra_providers) ? panelState.infra_providers : [];
    const provMap = new Map(providers.map(p => [String(p.uuid), p.name]));

    if (!bills.length) {
      listEl.innerHTML = '<div class="p-4 text-center text-xs t-muted card-inset rounded-2xl border border-card-border">سابقه پرداختی ثبت نشده است.</div>';
      return;
    }
    listEl.innerHTML = bills.map(b => {
      const uuid = String(b.uuid || '');
      const provName = b.provider?.name || provMap.get(String(b.providerUuid || '')) || 'ارائه‌دهنده';
      const billedDate = b.billedAt ? String(b.billedAt).slice(0, 10) : '';
      const jalaliStr = billedDate && window.formatDateToJalali ? window.formatDateToJalali(billedDate) : billedDate;
      return `
        <div class="card p-2.5 rounded-2xl border border-card-border flex items-center justify-between gap-2">
          <button type="button" onclick="window.panelCtrl.deleteBill('${escapeHtml(uuid)}')" class="p-1.5 rounded-xl border border-rose-500/35 t-danger hover:bg-rose-500/10 transition active:scale-95 shrink-0" title="حذف رکورد پرداخت">
            ${TRASH_ICON_SVG}
          </button>
          <div class="min-w-0 flex-1 text-left" dir="ltr">
            <div class="flex items-center justify-between gap-2">
              <b class="text-xs t-main truncate font-en">${escapeHtml(provName)}</b>
              <span class="badge badge-success text-[10px] num-bidi">${Number(b.amount || 0).toLocaleString('en-US')}</span>
            </div>
            <span class="text-[10.5px] t-muted block mt-0.5 num-bidi">${escapeHtml(jalaliStr || billedDate || '—')}</span>
          </div>
        </div>
      `;
    }).join('');
    window.adminActions?.renderNodeBillingBillsHistory?.();
  }

  let activeBillNodeCtx = null;

  async function openBillModal(prefillProviderUuid = '', prefillAmount = '', nodeCtx = null) {
    const modal = $('panelBillCreateModal');
    const provSel = $('panelBillProviderSelect');
    if (!modal || !provSel) return;
    if (!panelState.loaded) await fetchOverview(false);
    const providers = Array.isArray(panelState.infra_providers) ? panelState.infra_providers : [];
    provSel.innerHTML = providers.length
      ? providers.map(p => `<option value="${escapeHtml(p.uuid)}">${escapeHtml(p.name)}</option>`).join('')
      : '<option value="">ابتدا ارائه‌دهنده تعریف کنید</option>';
    if (prefillProviderUuid) provSel.value = prefillProviderUuid;
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
        if (!res.panel_sync_warning) {
          $('nodeBillingDueSourceBadge')?.classList.remove('hidden');
          window.adminActions?.updateNodeBillingDueSyncStatus?.('panel');
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
    openExtSquadUsersModal,
    closeExtSquadUsersModal,
    submitExtSquadUsers,
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
    createBill,
    deleteBill,
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
  };
})(window);
