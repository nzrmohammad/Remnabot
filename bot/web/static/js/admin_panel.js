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
    subscription_settings: {},
    infra_providers: [],
    infra_billing_nodes: [],
    api_tokens_info: { ok: false, tokens: [], jwt_required: false },
  };
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
    const filtered = q
      ? allHosts.filter(h =>
          String(h.remark || '').toLowerCase().includes(q)
          || String(h.address || '').toLowerCase().includes(q)
          || String(h.sni || '').toLowerCase().includes(q)
        )
      : allHosts;

    const bulkBar = $('panelHostsBulkBar');
    if (bulkBar) {
      bulkBar.classList.toggle('hidden', selectedHostUuids.size === 0);
      if ($('panelHostsSelectedCount')) $('panelHostsSelectedCount').innerText = `${selectedHostUuids.size} مورد انتخاب شده`;
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
      return `
        <div class="card p-3 rounded-2xl border border-card-border space-y-2">
          <div class="flex items-start justify-between gap-2">
            <label class="flex items-start gap-2 min-w-0 flex-1 cursor-pointer">
              <input type="checkbox" class="mt-0.5 rounded accent-cyan-500" ${checked ? 'checked' : ''} onchange="window.panelCtrl.toggleHostSelection('${escapeHtml(uuid)}', this.checked)" />
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5 flex-wrap">
                  <b class="text-xs t-main truncate" dir="ltr">${escapeHtml(h.remark || 'Host')}</b>
                  <span class="badge ${disabled ? 'badge-danger' : 'badge-success'} text-[10px]">${disabled ? 'غیرفعال' : 'فعال'}</span>
                </div>
                <div class="text-[11px] t-accent font-sans num-bidi truncate mt-0.5" dir="ltr">${escapeHtml(h.address || '—')}:${Number(h.port || 443)}</div>
              </div>
            </label>
            <div class="flex items-center gap-1 shrink-0">
              <button type="button" onclick="window.panelCtrl.toggleSingleHost('${escapeHtml(uuid)}', ${disabled ? 'true' : 'false'})" class="p-1.5 rounded-xl border ${disabled ? 'border-emerald-500/35 t-success hover:bg-emerald-500/10' : 'border-rose-500/35 t-danger hover:bg-rose-500/10'} transition active:scale-95" title="${disabled ? 'فعال‌سازی هاست' : 'غیرفعال‌سازی هاست'}">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5.636 5.636a9 9 0 1012.728 0M12 3v9"/></svg>
              </button>
              <button type="button" onclick="window.panelCtrl.openHostModal('${escapeHtml(uuid)}')" class="p-1.5 rounded-xl border border-cyan-500/35 t-accent hover:bg-cyan-500/10 transition active:scale-95" title="ویرایش هاست">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
              </button>
            </div>
          </div>
          <div class="flex flex-wrap items-center justify-between gap-1.5 pt-1.5 border-t border-card-border text-[10.5px] t-muted">
            <span class="truncate" dir="ltr">SNI: <b class="t-main">${escapeHtml(h.sni || '—')}</b></span>
            ${tags.length ? `<div class="flex flex-wrap gap-1">${tags.map(t => `<span class="badge badge-info text-[10px]">${escapeHtml(t)}</span>`).join('')}</div>` : ''}
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
    const hosts = panelState.hosts || [];
    if (selectedHostUuids.size === hosts.length) {
      selectedHostUuids.clear();
    } else {
      hosts.forEach(h => { if (h.uuid) selectedHostUuids.add(String(h.uuid)); });
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

    const inbSel = $('panelHostInboundSelect');
    if (inbSel) {
      const inbounds = allProfileInbounds();
      const curInb = h?.inbound?.configProfileInboundUuid || h?.inboundUuid || '';
      inbSel.innerHTML = '<option value="">انتخاب اینباند متصل (اختیاری در ویرایش)...</option>' + inbounds.map(inb => (
        `<option value="${escapeHtml(inb.uuid)}" data-profile="${escapeHtml(inb.profileUuid)}">${escapeHtml(inb.profileName)} — ${escapeHtml(inb.tag)} (${escapeHtml(inb.type || '')}:${inb.port || ''})</option>`
      )).join('');
      if (curInb) inbSel.value = curInb;
    }
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
    const inbSel = $('panelHostInboundSelect');
    const inbound_uuid = inbSel?.value || '';
    const config_profile_uuid = inbSel?.options?.[inbSel.selectedIndex]?.dataset?.profile || '';

    if (!remark || !address) {
      toast('نام و آدرس هاست الزامی است.');
      return;
    }

    const res = await window.api?.savePanelHost?.({
      uuid,
      remark,
      address,
      port,
      sni,
      host,
      is_disabled,
      inbound_uuid,
      config_profile_uuid,
    });
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
          <div class="min-w-0">
            <b class="text-xs t-main block truncate" dir="ltr">${escapeHtml(sq.name || 'Squad')}</b>
            <span class="text-[10.5px] t-muted block mt-0.5">${Number(count)} عضو در اسکواد</span>
          </div>
          <button type="button" onclick="window.panelCtrl.openExtSquadUsersModal('${escapeHtml(uuid)}', '${escapeHtml(sq.name || '')}')" class="btn btn-secondary px-2.5 py-1.5 text-[11px] rounded-xl font-bold shrink-0">مدیریت اعضا</button>
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
            <b class="text-xs t-main truncate" dir="ltr">${escapeHtml(p.name || 'Profile')}</b>
            <span class="badge badge-info text-[10px]">${inbounds.length} اینباند</span>
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
                <img src="/static/img/icons/trash.svg?v=fl2" class="ui-icon-img w-3.5 h-3.5 shrink-0" alt="" />
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
          <div class="min-w-0 text-left flex-1" dir="ltr">
            <b class="text-xs t-main block truncate font-en">${escapeHtml(p.name || '')}</b>
            <span class="text-[10.5px] t-muted block truncate">${linkedCount} سرور متصل${p.login ? ` • ${escapeHtml(p.login)}` : ''}</span>
          </div>
          <div class="flex items-center gap-1 shrink-0">
            <button type="button" onclick="window.panelCtrl.openProviderModal('${escapeHtml(uuid)}')" class="p-1.5 rounded-xl border border-cyan-500/35 t-accent hover:bg-cyan-500/10 transition active:scale-95" title="ویرایش ارائه‌دهنده">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
            </button>
            <button type="button" onclick="window.panelCtrl.deleteProvider('${escapeHtml(uuid)}', '${escapeHtml(p.name || '')}')" class="p-1.5 rounded-xl border border-rose-500/35 t-danger hover:bg-rose-500/10 transition active:scale-95" title="حذف ارائه‌دهنده">
              <img src="/static/img/icons/trash.svg?v=fl2" class="ui-icon-img w-3.5 h-3.5 shrink-0" alt="" />
            </button>
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
          <img src="/static/img/icons/trash.svg?v=fl2" class="ui-icon-img w-3.5 h-3.5 shrink-0" alt="" />
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
    openTokenModal,
    closeTokenModal,
    createToken,
    deleteToken,
    confirmAction,
    closeConfirmModal,
    executeConfirmAction,
    getConfigProfiles: () => panelState.config_profiles || [],
  };
})(window);
