/**
 * RemnaAdmin Pro - Settings, Support & Campaigns Module (admin_settings.js)
 * Global configs, maintenance toggle, database backup, broadcast messages, support tickets and app versions.
 */
(function (window) {
  'use strict';

  const $ = id => document.getElementById(id);
  const api = window.api;
  const tg = window.Telegram?.WebApp;
  const formatNumber = window.formatNumber || (n => String(n));
  const formatChatTimestamp = window.formatChatTimestamp || (() => '');
  window.adminActions = window.adminActions || {};

  let currentBroadcastTarget = 'all';
  let activeChatTelegramId = null;
  let activeChatUserName = '';

  const DEFAULT_BIRTHDAY_TEMPLATE = `🎂 <b>زادروزتان فرخنده و همایون باد!</b> 🎉\n\nکاربر گرامی {first_name}، فرا رسیدن سالروز تولدتان را صمیمانه تبریک عرض می‌کنیم! 🌸\n\nبه مناسبت روز زادروز شما، پکیج هدیه اختصاصی VIP تقدیم حضورتان می‌گردد:\n{traffic_msg}\n🎟 <b>کد تخفیف اختصاصی {discount_pct}٪ برای سفارش یا تمدید بعدی:</b>\n<code>{coupon_code}</code>\n⏱ <i>(مهلت استفاده: ۷ روز در مینی‌اپ و ربات)</i>\n\nبا آرزوی بهترین‌ها و لحظاتی سرشار از سلامتی و شادی برای شما! 💫`;

  // Support Chat, Campaigns, App Recommendations & Settings Actions
  Object.assign(window.adminActions, {
    openCardTemplateModal() {
      const modal = $('cardTemplateModal');
      if (!modal) return;
      const curVal = $('settingCardTemplate')?.value || 'blubank';
      const isMin = curVal === 'minimal';
      const optBlu = $('cardTplOpt_blubank');
      const optMin = $('cardTplOpt_minimal');
      const chkBlu = $('cardTplCheck_blubank');
      const chkMin = $('cardTplCheck_minimal');
      if (optBlu && optMin) {
        optBlu.className = isMin ? 'p-3 rounded-2xl border transition cursor-pointer flex items-center justify-between gap-3 card-inset border-card-border hover:border-slate-500' : 'p-3 rounded-2xl border transition cursor-pointer flex items-center justify-between gap-3 bg-blue-600/15 border-blue-500 shadow-sm';
        optMin.className = isMin ? 'p-3 rounded-2xl border transition cursor-pointer flex items-center justify-between gap-3 bg-blue-600/15 border-blue-500 shadow-sm' : 'p-3 rounded-2xl border transition cursor-pointer flex items-center justify-between gap-3 card-inset border-card-border hover:border-slate-500';
        chkBlu?.classList.toggle('hidden', isMin);
        chkMin?.classList.toggle('hidden', !isMin);
      }
      modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },
    closeCardTemplateModal() {
      $('cardTemplateModal')?.classList.add('hidden');
    },
    selectCardTemplate(val, name, icon = '💳') {
      const input = $('settingCardTemplate');
      if (input) input.value = val;
      if ($('settingCardTemplateLabel')) $('settingCardTemplateLabel').innerText = name;
      if ($('settingCardTemplateIcon')) $('settingCardTemplateIcon').innerText = icon;
      this.closeCardTemplateModal();
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    openCardColorModal() {
      const modal = $('cardColorModal');
      const list = $('cardColorList');
      if (!modal || !list) return;
      modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('selection');

      const currentVal = $('settingBluBankColor')?.value || 'red';
      const colors = [
        { id: 'blue', name: 'آبی کلاسیک', icon: '🔵', desc: 'Blue' },
        { id: 'green', name: 'سبز چمنی', icon: '🟢', desc: 'Green' },
        { id: 'red', name: 'قرمز گیلاسی', icon: '🔴', desc: 'Red' },
        { id: 'yellow', name: 'زرد لیمویی', icon: '🟡', desc: 'Yellow' },
        { id: 'purple', name: 'بنفش شاه‌توتی', icon: '🟣', desc: 'Purple' },
        { id: 'rose', name: 'رز صورتی', icon: '🌸', desc: 'Rose' },
        { id: 'black', name: 'مشکی مات', icon: '⚫️', desc: 'Black Matte' },
      ];

      list.innerHTML = colors.map(c => `
        <div onclick="window.adminActions.selectCardColor('${c.id}', '${c.name}', '${c.icon}')" class="p-3 rounded-2xl border transition cursor-pointer flex items-center justify-between gap-3 ${currentVal === c.id ? 'bg-blue-600/15 border-blue-500 shadow-sm' : 'card-inset hover:border-slate-500/50'}">
          <div class="flex items-center gap-2.5">
            <span class="text-base">${c.icon}</span>
            <div>
              <span class="text-xs font-bold ${currentVal === c.id ? 't-info' : 't-main'} block">${c.name}</span>
              <span class="text-[10px] t-muted block">${c.desc}</span>
            </div>
          </div>
          ${currentVal === c.id ? '<span class="text-xs text-blue-400 font-bold">✓</span>' : ''}
        </div>
      `).join('');
    },
    closeCardColorModal() {
      $('cardColorModal')?.classList.add('hidden');
    },
    selectCardColor(val, name, icon) {
      const input = $('settingBluBankColor');
      if (input) input.value = val;
      if ($('settingBluBankColorLabel')) $('settingBluBankColorLabel').innerText = name;
      if ($('settingBluBankColorIcon')) $('settingBluBankColorIcon').innerText = icon;
      this.closeCardColorModal();
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    async openDefaultSquadPickerModal() {
      const modal = $('defaultSquadPickerModal');
      const list = $('defaultSquadPickerList');
      if (!modal || !list) return;
      modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('selection');

      const currentVal = $('settingDefaultSquadUuid')?.value || '';
      list.innerHTML = '<div class="p-4 text-center t-muted text-xs">در حال بارگذاری اسکوادها...</div>';

      let squads = window._adminInternalSquads || [];
      if (!squads.length && window.api && window.api.getAdminRemnawaveSquads) {
        try {
          const res = await window.api.getAdminRemnawaveSquads();
          if (res && res.ok && Array.isArray(res.squads)) {
            squads = res.squads;
            window._adminInternalSquads = squads;
          }
        } catch (e) {
          console.error('Failed to load squads', e);
        }
      }

      let html = `
        <div onclick="window.adminActions.selectDefaultSquad('', 'انتخاب کنید', '🧩')" class="p-3 rounded-2xl border transition cursor-pointer flex items-center justify-between gap-3 ${currentVal === '' ? 'bg-blue-600/15 border-blue-500 shadow-sm' : 'card-inset hover:border-slate-500/50'}">
          <div class="flex items-center gap-2.5 min-w-0">
            <span class="text-base">🧩</span>
            <div>
              <span class="text-xs font-bold ${currentVal === '' ? 't-info' : 't-main'} block">انتخاب کنید</span>
              <span class="text-[10px] t-muted block">بدون تعیین اسکواد اختصاصی پیش‌فرض</span>
            </div>
          </div>
          ${currentVal === '' ? '<span class="text-xs text-blue-400 font-bold">✓</span>' : ''}
        </div>
      `;

      squads.forEach(sq => {
        const uuid = sq.uuid || sq.id;
        const name = sq.name || uuid;
        const isSelected = currentVal === uuid;
        html += `
          <div onclick="window.adminActions.selectDefaultSquad('${escapeHtml(uuid)}', '${escapeHtml(name)}', '🧩')" class="p-3 rounded-2xl border transition cursor-pointer flex items-center justify-between gap-3 ${isSelected ? 'bg-blue-600/15 border-blue-500 shadow-sm' : 'card-inset hover:border-slate-500/50'}">
            <div class="flex items-center gap-2.5 min-w-0">
              <span class="text-base">🧩</span>
              <span class="text-xs font-bold ${isSelected ? 't-info' : 't-main'} truncate block">${escapeHtml(name)}</span>
            </div>
            ${isSelected ? '<span class="text-xs text-blue-400 font-bold">✓</span>' : ''}
          </div>
        `;
      });

      list.innerHTML = html;
    },
    closeDefaultSquadPickerModal() {
      $('defaultSquadPickerModal')?.classList.add('hidden');
    },
    selectDefaultSquad(uuid, name, icon = '🧩') {
      const input = $('settingDefaultSquadUuid');
      if (input) input.value = uuid;
      if ($('settingDefaultSquadLabel')) $('settingDefaultSquadLabel').innerText = uuid ? name : 'انتخاب کنید';
      if ($('settingDefaultSquadIcon')) $('settingDefaultSquadIcon').innerText = icon;
      this.closeDefaultSquadPickerModal();
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },
    async updateDefaultSquadDisplay(uuid) {
      if (!uuid) {
        if ($('settingDefaultSquadLabel')) $('settingDefaultSquadLabel').innerText = 'انتخاب کنید';
        return;
      }
      let squads = window._adminInternalSquads || [];
      if (!squads.length && window.api && window.api.getAdminRemnawaveSquads) {
        try {
          const res = await window.api.getAdminRemnawaveSquads();
          if (res && res.ok && Array.isArray(res.squads)) {
            squads = res.squads;
            window._adminInternalSquads = squads;
          }
        } catch (e) {}
      }
      const match = squads.find(s => (s.uuid || s.id) === uuid);
      if ($('settingDefaultSquadLabel')) {
        $('settingDefaultSquadLabel').innerText = match ? (match.name || match.uuid) : 'انتخاب کنید';
      }
    },
    resetBirthdayTemplate() {
      const el = $('settingBirthdayMessage');
      if (el) el.value = DEFAULT_BIRTHDAY_TEMPLATE;
      if (window.showToast) window.showToast('متن پیش‌فرض بارگذاری شد.', 'info');
    },
    insertBirthdayTag(tag) {
      const el = $('settingBirthdayMessage');
      if (!el) return;
      const start = el.selectionStart ?? el.value.length;
      const end = el.selectionEnd ?? el.value.length;
      el.value = el.value.substring(0, start) + tag + el.value.substring(end);
      el.focus();
      el.selectionStart = el.selectionEnd = start + tag.length;
    },
openUserChat(telegram_id, name, tag, topup_id) {
      activeChatTelegramId = telegram_id;
      activeChatUserName = name || String(telegram_id);
      const inputId = $('directTicketUserId');
      if (inputId) inputId.value = String(telegram_id);

      const chatContainer = $('adminChatContainer');
      if (chatContainer) chatContainer.classList.remove('hidden');

      const badgeEl = $('activeChatReceiptBadge');
      if (badgeEl) badgeEl.style.display = 'none';

      const statusBadgeEl = $('activeChatStatusBadge');
      if (statusBadgeEl) {
        if (topup_id) {
          statusBadgeEl.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30';
          statusBadgeEl.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>فیش ${topup_id}`;
        } else {
          statusBadgeEl.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-bold bg-blue-500/15 text-blue-400 border border-blue-500/30';
          statusBadgeEl.innerText = 'پشتیبانی کاربر';
        }
      }

      const nameEl = $('activeChatUserName');
      if (nameEl) nameEl.textContent = name || `کاربر ${telegram_id}`;

      const avatarEl = $('activeChatUserAvatar');
      if (avatarEl) {
        const initial = ((name || 'U').replace('@', '')[0] || 'U').toUpperCase();
        avatarEl.innerHTML = `<img src="/api/user/avatar?user_id=${telegram_id}" alt="Avatar" class="w-full h-full object-cover" onerror="this.classList.add('hidden'); if(this.nextElementSibling) this.nextElementSibling.classList.remove('hidden');" /><span class="font-bold">${initial}</span>`;
      }

      const tagEl = $('activeChatUserTag');
      if (tagEl) {
        const cleanTag = tag && tag.startsWith('@') ? tag : (name && name.startsWith('@') ? name : '');
        tagEl.textContent = cleanTag || '';
        tagEl.style.display = cleanTag ? 'block' : 'none';
      }

      const idEl = $('activeChatUserId');
      if (idEl) idEl.innerHTML = `<span onclick="window.adminActions.quickCopy('${telegram_id}', 'شناسه عددی')" class="cursor-pointer hover:text-cyan-300 transition">${telegram_id}</span>`;

      loadUserChatMessages(telegram_id);

      const msgInput = $('directTicketMsg');
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
      const chatContainer = $('adminChatContainer');
      if (chatContainer) chatContainer.classList.add('hidden');
      if (window.hapticFeedback) window.hapticFeedback('light');
    },

    toggleSettingsBox(targetId) {
      if (!targetId) return;
      const targetBody = $(targetId);
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

// --- Campaign Detail & Financial Analysis Modal ---
    openCampaignDetailModal(id) {
      const campaigns = window._adminCampaignsData || [];
      const c = campaigns.find(item => item.id === id);
      if (!c) return;

      const modal = $('campaignDetailModal');
      const titleEl = $('campaignDetailTitle');
      const linkEl = $('campaignDetailLink');
      const copyBtn = $('campaignDetailCopyBtn');
      const costEl = $('campaignDetailCost');
      const revEl = $('campaignDetailRevenue');
      const profEl = $('campaignDetailProfit');
      const roiEl = $('campaignDetailRoi');
      const usersEl = $('campaignDetailUsers');
      const buyersEl = $('campaignDetailBuyers');

      if (titleEl) titleEl.innerText = `تحلیل کمپین: ${c.name}`;
      const link = c._resolvedLink || c.deep_link || '';
      if (linkEl) linkEl.innerText = link;

      if (copyBtn) {
        copyBtn.onclick = () => window.adminActions.copyCampaignLink(link);
      }

      const cost = Number(c.cost || 0);
      const rev = Number(c.total_revenue || 0);
      const profit = rev - cost;
      const convRate = c.users_count > 0 ? ((c.buyers_count / c.users_count) * 100).toFixed(1) : '0';

      if (costEl) costEl.innerText = cost > 0 ? `${formatNumber(cost)} تومان` : '0 تومان (بدون هزینه)';
      if (revEl) revEl.innerText = `${formatNumber(rev)} تومان`;
      if (profEl) {
        const sign = profit > 0 ? '+' : (profit < 0 ? '-' : '');
        const absFmt = formatNumber(Math.abs(profit));
        profEl.innerHTML = `<span dir="ltr">${sign}${absFmt}</span> <span class="text-[11px] font-sans">تومان</span>`;
        profEl.className = profit > 0 ? 'text-emerald-400 font-mono text-sm block' : (profit < 0 ? 'text-rose-400 font-mono text-sm block' : 'text-slate-300 font-mono text-sm block');
      }
      if (roiEl) {
        const roiText = c.roi !== null && c.roi !== undefined ? `${c.roi > 0 ? '+' : ''}${toEnglishDigits(c.roi)}%` : '—';
        roiEl.innerText = roiText;
        roiEl.className = c.roi !== null && c.roi > 0 ? 'text-emerald-400 font-mono text-sm block' : (c.roi !== null && c.roi < 0 ? 'text-rose-400 font-mono text-sm block' : 'text-slate-400 font-mono text-sm block');
      }
      if (usersEl) usersEl.innerHTML = `${formatNumber(c.users_count)} <span class="font-sans text-[11px]">نفر</span>`;
      if (buyersEl) {
        const enRate = toEnglishDigits(convRate);
        buyersEl.innerHTML = `${formatNumber(c.buyers_count)} <span class="font-sans text-[11px]">نفر</span> <span dir="ltr" class="font-mono text-xs">(${enRate}%)</span>`;
      }

      if (modal) modal.classList.remove('hidden');
    },

    closeCampaignDetailModal() {
      const modal = $('campaignDetailModal');
      if (modal) modal.classList.add('hidden');
    },

    // --- Ad Campaigns & Deep-link Tracking Actions ---
    openCreateCampaignModal() {
      const modal = $('createCampaignModal');
      if (!modal) return;
      const n = $('campaignNameInput');
      const c = $('campaignCodeInput');
      const co = $('campaignCostInput');
      if (n) n.value = '';
      if (c) c.value = '';
      if (co) co.value = '';
      modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    closeCreateCampaignModal() {
      const modal = $('createCampaignModal');
      if (modal) modal.classList.add('hidden');
    },

    async submitCreateCampaign(e) {
      if (e) e.preventDefault();
      const name = $('campaignNameInput')?.value?.trim();
      const code = $('campaignCodeInput')?.value?.trim().toLowerCase();
      const cost = parseInt($('campaignCostInput')?.value || '0', 10);

      if (!name || !code) {
        if (window.showToast) window.showToast('⚠️ نام و شناسه کمپین الزامی است.');
        return;
      }

      const submitBtn = $('createCampaignSubmitBtn');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = 'در حال ساخت...';
      }

      try {
        const res = await window.api.createAdminCampaign({ name, code, cost });
        if (res && res.ok) {
          if (window.showToast) window.showToast('✅ کمپین و لینک با موفقیت ایجاد شد.');
          if (window.hapticFeedback) window.hapticFeedback('success');
          this.closeCreateCampaignModal();
          this.fetchAdminCampaigns();
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ساخت کمپین'}`);
          if (window.hapticFeedback) window.hapticFeedback('error');
        }
      } catch (err) {
        if (window.showToast) window.showToast('خطای شبکه در ارتباط با سرور.');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerText = 'ساخت لینک';
        }
      }
    },

    async deleteCampaign(id, name) {
      if (!confirm(`آیا از حذف کمپین «${name}» اطمینان دارید؟`)) return;
      try {
        const res = await window.api.deleteAdminCampaign(id);
        if (res && res.ok) {
          if (window.showToast) window.showToast('🗑 کمپین با موفقیت حذف شد.');
          if (window.hapticFeedback) window.hapticFeedback('success');
          this.fetchAdminCampaigns();
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در حذف کمپین'}`);
        }
      } catch (err) {
        if (window.showToast) window.showToast('خطای شبکه در حذف کمپین.');
      }
    },

    async copyCampaignLink(deepLink) {
      if (!deepLink) return;
      let finalLink = deepLink;
      const botUser = window.botUsername || window.Telegram?.WebApp?.initDataUnsafe?.bot?.username || '';
      if (botUser && finalLink.includes('t.me/?start=')) {
        finalLink = finalLink.replace('t.me/?start=', `t.me/${botUser}?start=`);
      }
      if (!finalLink.startsWith('https://') && !finalLink.startsWith('http://')) {
        finalLink = 'https://' + finalLink;
      }
      const copyFn = typeof copyToClipboard === 'function' ? copyToClipboard : window.copyToClipboard;
      const ok = copyFn ? await copyFn(finalLink, '📋 لینک تبلیغاتی کپی شد: ' + finalLink) : false;
      if (!ok) {
        prompt('لینک تبلیغاتی:', finalLink);
      }
    },

    async fetchAdminCampaigns() {
      const container = $('adminCampaignsList');
      if (!container) return;

      container.innerHTML = `
        <div class="p-6 rounded-2xl bg-transparent border border-slate-700/50 text-center text-xs text-slate-400">
          در حال بارگذاری لیست کمپین‌ها...
        </div>
      `;

      try {
        const res = await window.api.getAdminCampaigns();
        if (!res || !res.ok) {
          container.innerHTML = '<div class="p-6 text-center text-xs text-rose-400">خطا در بارگذاری لیست کمپین‌ها</div>';
          return;
        }

        if (res.bot_username) window.botUsername = res.bot_username;
        const botUser = window.botUsername || window.Telegram?.WebApp?.initDataUnsafe?.bot?.username || '';
        const campaigns = res.campaigns || [];
        if (campaigns.length === 0) {
          container.innerHTML = `
            <div class="p-8 rounded-2xl bg-slate-800/40 border border-slate-700/60 text-center space-y-2">
              <div class="w-12 h-12 mx-auto rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z"/></svg>
              </div>
              <p class="text-xs text-white font-bold">هنوز هیچ کمپین یا لینکی ساخته نشده است</p>
              <p class="text-[11px] text-slate-400">با ساخت اولین لینک تبلیغاتی، می‌توانید ورودی‌ها و خرید کاربران از کانال‌ها و افراد مختلف را ردیابی کنید.</p>
            </div>
          `;
          return;
        }

        window._adminCampaignsData = campaigns;
        container.innerHTML = campaigns.map(c => {
          let link = c.deep_link || '';
          if (botUser && link.includes('t.me/?start=')) {
            link = link.replace('t.me/?start=', `t.me/${botUser}?start=`);
          }
          if (!link.startsWith('https://') && !link.startsWith('http://')) {
            link = 'https://' + link;
          }
          c._resolvedLink = link;
          const roiText = c.roi !== null && c.roi !== undefined ? `${c.roi > 0 ? '+' : ''}${c.roi}%` : null;
          const roiColor = c.roi !== null && c.roi > 0 ? 'text-emerald-400' : (c.roi !== null && c.roi < 0 ? 'text-rose-400' : 'text-slate-400');

          return `
            <div class="bg-slate-800/80 p-3.5 rounded-2xl border border-slate-700/80 space-y-3 transition hover:border-slate-600">
              <!-- Top Row: Name & Action Icons -->
              <div class="flex items-center justify-between gap-2">
                <div class="flex items-center gap-2 min-w-0">
                  <div class="w-8 h-8 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-400 flex items-center justify-center flex-shrink-0">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z"/></svg>
                  </div>
                  <div class="min-w-0">
                    <div class="flex items-center gap-1.5">
                      <b class="text-xs t-main truncate">${escapeHtml(c.name)}</b>
                      ${roiText ? `<span class="px-1.5 py-0.5 rounded text-[9px] font-mono ${roiColor} bg-slate-900/80 border border-slate-700/60" dir="ltr">${roiText}</span>` : ''}
                    </div>
                    <span class="text-[10px] font-mono text-cyan-400 dir-ltr block mt-0.5">ad_${escapeHtml(c.code)}</span>
                  </div>
                </div>
                <div class="flex items-center gap-1.5 flex-shrink-0">
                  <!-- Copy Link Icon Button -->
                  <button type="button" data-link="${escapeHtml(link)}" class="btn-copy-campaign-link w-8 h-8 min-w-[32px] min-h-[32px] bg-transparent hover:bg-cyan-500/10 text-cyan-400 border border-cyan-500/40 rounded-xl flex items-center justify-center transition active:scale-95 shadow-sm" title="کپی لینک اختصاصی" aria-label="کپی لینک اختصاصی">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
                  </button>
                  <!-- Details / Modal Icon Button -->
                  <button type="button" onclick="window.adminActions.openCampaignDetailModal(${c.id})" class="w-8 h-8 min-w-[32px] min-h-[32px] bg-transparent hover:bg-blue-500/10 text-blue-400 border border-blue-500/40 rounded-xl flex items-center justify-center transition active:scale-95 shadow-sm" title="جزئیات و تحلیل مالی" aria-label="جزئیات و تحلیل مالی">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>
                  </button>
                  <!-- Delete Campaign Button -->
                  <button type="button" data-id="${c.id}" data-name="${escapeHtml(c.name)}" class="btn-delete-campaign w-8 h-8 min-w-[32px] min-h-[32px] bg-transparent hover:bg-rose-500/10 text-rose-400 border border-rose-500/40 rounded-xl flex items-center justify-center transition active:scale-95 shadow-sm" title="حذف کمپین" aria-label="حذف کمپین">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                  </button>
                </div>
              </div>

              <!-- Stats Grid: 4 symmetric boxes including Cost -->
              <div class="grid grid-cols-4 gap-1.5 sm:gap-2 pt-1 border-t border-slate-700/50 text-center">
                <div class="p-1.5 sm:p-2 rounded-xl card-inset">
                  <span class="text-[10px] t-muted block mb-0.5 whitespace-nowrap">ورودی</span>
                  <b class="text-xs font-mono t-main">${formatNumber(c.users_count)}</b>
                </div>
                <div class="p-1.5 sm:p-2 rounded-xl card-inset">
                  <span class="text-[10px] t-muted block mb-0.5 whitespace-nowrap">خریداران</span>
                  <b class="text-xs font-mono text-cyan-600 dark:text-cyan-300">${formatNumber(c.buyers_count)}</b>
                </div>
                <div class="p-1.5 sm:p-2 rounded-xl card-inset">
                  <span class="text-[10px] t-muted block mb-0.5 whitespace-nowrap">درآمد فروش</span>
                  <b class="text-xs font-mono text-emerald-600 dark:text-emerald-400">${formatNumber(c.total_revenue)}</b>
                </div>
                <div class="p-1.5 sm:p-2 rounded-xl card-inset">
                  <span class="text-[10px] t-muted block mb-0.5 whitespace-nowrap">هزینه تبلیغ</span>
                  <b class="text-xs font-mono text-amber-600 dark:text-amber-300">${c.cost ? formatNumber(c.cost) : '۰'}</b>
                </div>
              </div>
            </div>
          `;
        }).join('');
      } catch (e) {
        container.innerHTML = '<div class="p-6 text-center text-xs text-rose-400">خطای شبکه در بارگذاری کمپین‌ها</div>';
      }
    },

    calcStarsRate(mode = 'lossless') {
      const usdtInp = $('settingUsdtRate');
      const usdtVal = parseInt(usdtInp?.value || '0', 10) || window.currentUsdRate || 95000;
      const multiplier = mode === 'fragment' ? 0.015 : 0.013;
      const calculated = Math.round(usdtVal * multiplier);
      const starsInp = $('settingStarsRate');
      if (starsInp) {
        starsInp.value = calculated;
        if (window.hapticFeedback) window.hapticFeedback('success');
        const modeLabel = mode === 'fragment' ? 'فرگمنت (۰.۰۱۵$)' : 'بدون ضرر (۰.۰۱۳$)';
        if (window.showToast) window.showToast(`✅ نرخ استارز بر اساس دلار ${formatNumber(usdtVal)} تومان روی ${formatNumber(calculated)} ت (${modeLabel}) تنظیم شد`);
      }
      this.updateStarsHint();
    },

    updateStarsHint() {},

    // --- Access Mode Modal (حالت دسترسی ربات) ---
    openAccessModeModal() {
      const modal = $('accessModeModal');
      if (modal) modal.classList.remove('hidden');
      const curMode = $('settingAccessMode')?.value || 'open';
      this.highlightAccessModeOption(curMode);
      if (window.hapticFeedback) window.hapticFeedback('impact');
    },

    closeAccessModeModal() {
      $('accessModeModal')?.classList.add('hidden');
    },

    highlightAccessModeOption(mode) {
      document.querySelectorAll('.access-mode-opt').forEach(el => {
        el.classList.remove('border-emerald-500', 'border-cyan-500', 'border-rose-500', 'bg-emerald-500/10', 'bg-cyan-500/10', 'bg-rose-500/10');
        const dot = el.querySelector('.radio-dot');
        if (dot) dot.classList.add('hidden');
        const radio = el.querySelector('.radio-check');
        if (radio) radio.classList.remove('border-emerald-400', 'border-cyan-400', 'border-rose-400');
      });

      const activeEl = $(`accessOpt-${mode}`);
      if (activeEl) {
        const modeClasses = {
          open: { border: 'border-emerald-500', bg: 'bg-emerald-500/10', radio: 'border-emerald-400' },
          invite_only: { border: 'border-cyan-500', bg: 'bg-cyan-500/10', radio: 'border-cyan-400' },
          closed: { border: 'border-rose-500', bg: 'bg-rose-500/10', radio: 'border-rose-400' },
        };
        const cls = modeClasses[mode] || modeClasses.closed;
        activeEl.classList.add(cls.border, cls.bg);
        const dot = activeEl.querySelector('.radio-dot');
        if (dot) dot.classList.remove('hidden');
        const radio = activeEl.querySelector('.radio-check');
        if (radio) radio.classList.add(cls.radio);
      }
    },

    async selectAccessMode(mode) {
      const inp = $('settingAccessMode');
      if (inp) inp.value = mode;
      this.renderAccessModeUI(mode);
      this.closeAccessModeModal();
      if (window.hapticFeedback) window.hapticFeedback('success');

      const isMaint = (mode === 'closed');
      const maintSwitch = $('settingMaintSwitch');
      if (maintSwitch) maintSwitch.checked = isMaint;

      try {
        const res = await window.api.saveAdminSettings({ access_mode: mode, maintenance: isMaint });
        if (res && res.ok) {
          const names = { open: 'عمومی (آزاد)', invite_only: 'فقط با دعوت', closed: 'بسته / تعمیرات' };
          if (window.showToast) window.showToast(`✓ حالت دسترسی به «${names[mode] || mode}» تغییر یافت`);
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ذخیره حالت دسترسی'}`);
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطا در ذخیره حالت دسترسی');
      }
    },

    renderAccessModeUI(mode) {
      const badge = $('accessModeBadge');
      const sub = $('accessModeSubtext');
      const icon = $('accessModeIconBox');
      const inp = $('settingAccessMode');
      if (inp) inp.value = mode;

      if (mode === 'invite_only') {
        if (badge) {
          badge.textContent = 'فقط با دعوت';
          badge.className = 'badge badge-info rounded-full text-[10px] font-bold px-2 py-0.5';
        }
        if (sub) sub.textContent = 'کاربران جدید نیازمند لینک دعوت/رفرال هستند';
        if (icon) {
          icon.textContent = '🎟️';
          icon.className = 'w-8 h-8 rounded-xl bg-cyan-500/15 border border-cyan-500/30 text-cyan-700 dark:text-cyan-400 flex items-center justify-center text-sm flex-shrink-0';
        }
      } else if (mode === 'closed') {
        if (badge) {
          badge.textContent = 'بسته (تعمیرات)';
          badge.className = 'badge badge-danger rounded-full text-[10px] font-bold px-2 py-0.5';
        }
        if (sub) sub.textContent = 'ثبت‌نام متوقف شده است؛ سرویس‌های فعلی فعالند';
        if (icon) {
          icon.textContent = '🔒';
          icon.className = 'w-8 h-8 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-700 dark:text-rose-400 flex items-center justify-center text-sm flex-shrink-0';
        }
      } else {
        if (badge) {
          badge.textContent = 'عمومی (آزاد)';
          badge.className = 'badge badge-success rounded-full text-[10px] font-bold px-2 py-0.5';
        }
        if (sub) sub.textContent = 'ورود و ثبت‌نام برای تمامی کاربران آزاد است';
        if (icon) {
          icon.textContent = '🌐';
          icon.className = 'w-8 h-8 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-700 dark:text-emerald-400 flex items-center justify-center text-sm flex-shrink-0';
        }
      }
    },

    openRecommendedAppModal(os) {
      const modal = $('recommendedAppPickerModal');
      const list = $('recommendedAppPickerList');
      const title = $('recommendedAppPickerTitle');
      if (!modal || !list) return;

      const osNames = { ios: 'iOS', android: 'اندروید', windows: 'ویندوز', macos: 'مک', linux: 'لینوکس' };
      if (title) title.innerHTML = `<span>⭐️</span><span>انتخاب برنامه پیشنهادی (${osNames[os] || os})</span>`;

      const currentVal = $(`appRecommended_${os}`)?.value || '';
      const osApps = {
        ios: ['shadowrocket', 'streisand', 'v2box', 'incy', 'happ', 'onexray'],
        android: ['v2rayng', 'happ', 'hiddify', 'incy'],
        windows: ['v2rayn', 'hiddify', 'happ', 'incy'],
        macos: ['hiddify', 'happ', 'incy', 'v2box'],
        linux: ['hiddify', 'incy', 'nekoray', 'v2raya']
      };
      const appNames = {
        shadowrocket: 'Shadowrocket',
        streisand: 'Streisand',
        v2box: 'V2Box',
        incy: 'Incy',
        happ: 'Happ',
        onexray: 'OneXray',
        v2rayng: 'v2rayNG',
        v2rayn: 'v2rayN',
        hiddify: 'Hiddify',
        nekoray: 'NekoRay',
        v2raya: 'v2rayA'
      };

      const appIds = osApps[os] || [];
      let html = `
        <button type="button" onclick="window.adminActions.selectRecommendedApp('${os}', '', 'بدون برنامه پیشنهادی')" class="w-full text-right p-3 rounded-2xl border transition flex items-center justify-between ${!currentVal ? 'bg-cyan-500/15 border-cyan-500/40 text-cyan-700 dark:text-cyan-300 font-bold' : 'card-inset border-slate-700/50 t-muted hover:t-main'} active:scale-95">
          <div class="flex items-center gap-2">
            <span class="text-base">🚫</span>
            <span>بدون برنامه پیشنهادی</span>
          </div>
          ${!currentVal ? '<span class="text-cyan-600 dark:text-cyan-400 font-bold">✓</span>' : ''}
        </button>
      `;

      appIds.forEach(appId => {
        const appName = appNames[appId] || appId;
        const isSelected = currentVal === appId;
        html += `
          <button type="button" onclick="window.adminActions.selectRecommendedApp('${os}', '${appId}', '${escapeHtml(appName)}')" class="w-full text-right p-3 rounded-2xl border transition flex items-center justify-between ${isSelected ? 'bg-cyan-500/15 border-cyan-500/40 text-cyan-700 dark:text-cyan-300 font-bold' : 'card-inset border-slate-700/50 t-muted hover:t-main'} active:scale-95">
            <div class="flex items-center gap-2">
              <span class="text-base">📱</span>
              <span class="font-medium">${escapeHtml(appName)}</span>
            </div>
            ${isSelected ? '<span class="text-cyan-600 dark:text-cyan-400 font-bold">✓</span>' : ''}
          </button>
        `;
      });

      list.innerHTML = html;
      modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    selectRecommendedApp(os, appId, appName) {
      const inp = $(`appRecommended_${os}`);
      if (inp) inp.value = appId;
      this.updateRecommendedAppButton(os, appId);
      this.closeRecommendedAppModal();
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    closeRecommendedAppModal() {
      $('recommendedAppPickerModal')?.classList.add('hidden');
    },

    updateRecommendedAppButton(os, appId) {
      const lbl = $(`appRecommendedLabel_${os}`);
      if (lbl) {
        const appNames = {
          shadowrocket: 'Shadowrocket',
          streisand: 'Streisand',
          v2box: 'V2Box',
          incy: 'Incy',
          happ: 'Happ',
          onexray: 'OneXray',
          v2rayng: 'v2rayNG',
          v2rayn: 'v2rayN',
          hiddify: 'Hiddify',
          nekoray: 'NekoRay',
          v2raya: 'v2rayA'
        };
        lbl.innerText = appId ? (appNames[appId] || appId) : 'بدون برنامه پیشنهادی';
      }
    }
  });

  async function fetchTicketThreads() {
    // Active chat threads list was removed from UI; refresh active chat if one is open
    if (activeChatTelegramId) {
      loadUserChatMessages(activeChatTelegramId);
    }
  }

  async function loadUserChatMessages(telegram_id) {
    const streamEl = $('ticketChatStream');
    if (!streamEl) return;
    streamEl.innerHTML = '<div class="p-6 text-center text-slate-400 text-[11px]">در حال بارگذاری پیام‌ها...</div>';
    try {
      const res = await window.api.getAdminTicketMessages(telegram_id);
      if (!res || !res.ok) {
        streamEl.innerHTML = `<div class="p-4 text-center text-rose-400 text-[11px]">${escapeHtml(res?.error || 'خطا در دریافت پیام‌ها')}</div>`;
        return;
      }
      const messages = res.messages || [];
      const user = res.user || {};

      // Update header
      const nameEl = $('activeChatUserName');
      if (nameEl) nameEl.innerText = user.full_name || `کاربر ${telegram_id}`;
      const tagEl = $('activeChatUserTag');
      if (tagEl) {
        tagEl.innerText = user.username ? `@${user.username}` : '';
        tagEl.style.display = user.username ? 'block' : 'none';
      }
      const idEl = $('activeChatUserId');
      if (idEl) idEl.innerHTML = `<span onclick="window.adminActions.quickCopy('${telegram_id}', 'شناسه عددی')" class="cursor-pointer hover:text-cyan-300 transition">${telegram_id}</span>`;
      const avatarEl = $('activeChatUserAvatar');
      if (avatarEl) {
        const initial = ((user.full_name || user.username || String(telegram_id)).replace('@', '')[0] || 'U').toUpperCase();
        avatarEl.innerHTML = `<img src="/api/user/avatar?user_id=${telegram_id}" alt="Avatar" class="w-full h-full object-cover" onerror="this.classList.add('hidden'); if(this.nextElementSibling) this.nextElementSibling.classList.remove('hidden');" /><span class="font-bold">${initial}</span>`;
      }

      const badgeEl = $('activeChatStatusBadge');
      if (badgeEl) {
        if (user.pending_topup_id) {
          badgeEl.className = 'text-[10px] bg-transparent text-amber-500 border border-amber-500/30 px-2 py-0.5 rounded-lg font-bold flex items-center gap-1';
          badgeEl.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>فیش ${user.pending_topup_id}`;
        } else {
          badgeEl.className = 'text-[10px] bg-transparent t-success border border-emerald-500/30 px-2 py-0.5 rounded-lg font-bold';
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
              <div class="flex items-center justify-between gap-3 text-[10px] ${isAdmin ? 'text-blue-700 dark:text-blue-300 font-bold' : 't-muted font-bold'}">
                <span>${isAdmin ? '🛡️ پشتیبانی' : '👤 کاربر'}</span>
                <span class="font-mono ${isAdmin ? 't-info' : 't-muted'}" dir="ltr">${timeDisplay}</span>
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
  $('sendDirectTicketReplyBtn')?.addEventListener('click', async () => {
    const uid = $('directTicketUserId')?.value?.trim() || activeChatTelegramId;
    const txtEl = $('directTicketMsg');
    const txt = txtEl?.value?.trim();
    if (!uid) {
      if (window.showToast) window.showToast('لطفاً ابتدا یک کاربر را از لیست بالا انتخاب کنید.');
      return;
    }
    if (!txt) {
      if (window.showToast) window.showToast('لطفاً متن پیام را وارد کنید.');
      return;
    }
    const sendBtn = $('sendDirectTicketReplyBtn');
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
      const input = $('directTicketMsg');
      if (input && msg) {
        input.value = msg;
        input.focus();
      }
      if (window.hapticFeedback) window.hapticFeedback('impact');
    });
  });

  $('refreshChatThreadsBtn')?.addEventListener('click', () => {
    fetchTicketThreads();
    if (activeChatTelegramId) loadUserChatMessages(activeChatTelegramId);
    if (window.showToast) window.showToast('🔄 گفتگوها به‌روزرسانی شد');
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  $('directTicketMsg')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      $('sendDirectTicketReplyBtn')?.click();
    }
  });


  // --- 8. System Settings ---
  function formatTopicVal(inputEl, val) {
    if (!inputEl) return;
    const num = String(val ?? '').match(/\d+/)?.[0];
    if (num) {
      const label = inputEl.getAttribute('data-topic-label') || '';
      inputEl.value = label ? `${num} (${label})` : num;
    } else {
      inputEl.value = '';
    }
  }

  function parseTopicVal(val) {
    const num = String(val ?? '').match(/\d+/)?.[0];
    return num ? parseInt(num, 10) : null;
  }

  const topicInputIds = [
    'settingTopicTopups',
    'settingTopicOrders',
    'settingTopicSupport',
    'settingTopicAlerts',
    'settingTopicBackups',
    'settingTopicNodes',
    'settingTopicReports',
    'settingTopicCrypto',
    'settingTopicErrors',
    'settingTopicSmsManual'
  ];

  function updateSmsWebhookUrlDisplay(secret) {
    const el = $('settingSmsWebhookUrlDisplay');
    if (!el) return;
    const origin = window.location.origin || '';
    const tokenPart = secret && String(secret).trim() ? `?token=${encodeURIComponent(String(secret).trim())}` : '';
    el.value = `${origin}/api/webhooks/sms${tokenPart}`;
  }

  window.copySmsWebhookUrl = function () {
    const el = $('settingSmsWebhookUrlDisplay');
    const val = el?.value?.trim() || '';
    if (!val) return;
    const copyFn = typeof copyToClipboard === 'function' ? copyToClipboard : window.copyToClipboard;
    if (copyFn) {
      copyFn(val, '📋 آدرس وب‌هوک در کلیپ‌بورد کپی شد.');
    } else {
      prompt('آدرس وب‌هوک SMS:', val);
    }
  };

  async function fetchAdminSettings() {
    try {
      const res = await window.api.getAdminSettings();
      if (!res || !res.ok || !res.settings) return;
      window._adminSettingsLoaded = true;
      const s = res.settings;

      // Access Mode & Maintenance Sync
      const isMaint = !!s.maintenance;
      const curMode = s.access_mode || (isMaint ? 'closed' : 'open');
      const finalMode = isMaint ? 'closed' : curMode;

      const maintSwitch = $('settingMaintSwitch');
      if (maintSwitch) maintSwitch.checked = (finalMode === 'closed');

      const accessMode = $('settingAccessMode');
      if (accessMode) accessMode.value = finalMode;
      window.adminActions.renderAccessModeUI(finalMode);
      if (s.bot_username) window.botUsername = s.bot_username;

      // Other Switches
      const cardSwitch = $('settingCardSwitch');
      if (cardSwitch) cardSwitch.checked = !!s.card_enabled;

      const cryptoSwitch = $('settingCryptoSwitch');
      if (cryptoSwitch) cryptoSwitch.checked = !!s.crypto_enabled;

      const trxSwitch = $('settingTrxSwitch');
      if (trxSwitch) trxSwitch.checked = s.trx_enabled !== false;

      const trialSwitch = $('settingTrialSwitch');
      if (trialSwitch) trialSwitch.checked = !!s.trial_enabled;

      const refSwitch = $('settingRefSwitch');
      if (refSwitch) refSwitch.checked = !!s.referral_enabled;

      const supDirectSwitch = $('settingSupportDirectSwitch');
      if (supDirectSwitch) supDirectSwitch.checked = !!s.support_direct_enabled;

      // Telegram Stars Gateway
      const starsSwitch = $('settingStarsSwitch');
      if (starsSwitch) starsSwitch.checked = !!s.stars_enabled;

      const starsRate = $('settingStarsRate');
      if (starsRate) starsRate.value = s.stars_rate_toman ?? 1600;

      // Auto Clean Previous Reports
      const autoCleanSwitch = $('settingAutoCleanReportsSwitch');
      if (autoCleanSwitch) autoCleanSwitch.checked = (s.auto_clean_reports !== false);

      // Bank & Topup
      const cardNum = $('settingCardNumber');
      if (cardNum) cardNum.value = s.card_number || '';

      const cardHolder = $('settingCardHolder');
      if (cardHolder) cardHolder.value = s.card_holder || '';

      const minTopup = $('settingMinTopup');
      if (minTopup) minTopup.value = s.topup_min_amount ?? 20000;

      const cardPhoneSwitch = $('settingCardRequirePhoneSwitch');
      if (cardPhoneSwitch) cardPhoneSwitch.checked = s.card_require_phone_verification ?? true;

      const cardIranSwitch = $('settingCardPhoneIranSwitch');
      if (cardIranSwitch) cardIranSwitch.checked = s.card_phone_iran_only ?? true;

      const cardAutoSwitch = $('settingCardAutoSwitch');
      if (cardAutoSwitch) cardAutoSwitch.checked = !!s.card_auto_enabled;

      const smsSecretInput = $('settingSmsWebhookSecret');
      if (smsSecretInput) {
        smsSecretInput.value = s.sms_webhook_secret || '';
        smsSecretInput.oninput = () => updateSmsWebhookUrlDisplay(smsSecretInput.value);
      }
      updateSmsWebhookUrlDisplay(s.sms_webhook_secret || '');

      // Birthday Rewards
      const bdaySwitch = $('settingBirthdayRewardSwitch');
      if (bdaySwitch) bdaySwitch.checked = s.birthday_reward_enabled ?? true;

      const bdayTraffic = $('settingBirthdayRewardTraffic');
      if (bdayTraffic) bdayTraffic.value = s.birthday_reward_traffic_gb ?? 2;

      const bdayDiscount = $('settingBirthdayRewardDiscount');
      if (bdayDiscount) bdayDiscount.value = s.birthday_reward_discount_percent ?? 20;

      const bdayMsg = $('settingBirthdayMessage');
      if (bdayMsg) bdayMsg.value = s.birthday_custom_message || DEFAULT_BIRTHDAY_TEMPLATE;

      const bluColor = $('settingBluBankColor');
      if (bluColor) {
        const cVal = s.card_blubank_color || 'red';
        bluColor.value = cVal;
        const colorMap = {
          blue: { name: 'آبی کلاسیک', icon: '🔵' },
          green: { name: 'سبز چمنی', icon: '🟢' },
          red: { name: 'قرمز گیلاسی', icon: '🔴' },
          yellow: { name: 'زرد لیمویی', icon: '🟡' },
          purple: { name: 'بنفش شاه‌توتی', icon: '🟣' },
          rose: { name: 'رز صورتی', icon: '🌸' },
          black: { name: 'مشکی مات', icon: '⚫️' }
        };
        const cMeta = colorMap[cVal] || colorMap.red;
        if ($('settingBluBankColorLabel')) $('settingBluBankColorLabel').innerText = cMeta.name;
        if ($('settingBluBankColorIcon')) $('settingBluBankColorIcon').innerText = cMeta.icon;
      }

      const cardGraphicalSwitch = $('settingCardGraphicalSwitch');
      if (cardGraphicalSwitch) cardGraphicalSwitch.checked = s.card_graphical_view_enabled !== false;

      const cardTemplate = $('settingCardTemplate');
      if (cardTemplate) {
        cardTemplate.value = s.card_template || 'blubank';
        const isMin = s.card_template === 'minimal';
        if ($('settingCardTemplateLabel')) $('settingCardTemplateLabel').innerText = isMin ? 'ساده و مینیمال' : 'بلوبانک';
        if ($('settingCardTemplateIcon')) $('settingCardTemplateIcon').innerText = isMin ? '📄' : '💳';
      }

      const defSquadEl = $('settingDefaultSquadUuid');
      if (defSquadEl) {
        const sqUuid = s.default_squad_uuid || '';
        defSquadEl.value = sqUuid;
        window.adminActions.updateDefaultSquadDisplay(sqUuid);
      }

      // Join Gate
      const jgSwitch = $('settingJoinGateSwitch');
      if (jgSwitch) jgSwitch.checked = s.join_gate_enabled ?? false;

      const jgChannel = $('settingJoinGateChannel');
      if (jgChannel) jgChannel.value = s.join_gate_channel || '';

      // Crypto & Rates
      const usdtRate = $('settingUsdtRate');
      if (usdtRate) {
        usdtRate.value = s.usdt_rate_toman ?? 95000;
        if (!usdtRate._hasStarsListener) {
          usdtRate.addEventListener('input', () => window.adminActions.updateStarsHint());
          usdtRate._hasStarsListener = true;
        }
      }
      if (s.usdt_rate_toman) window.currentUsdRate = s.usdt_rate_toman;
      window.adminActions.updateStarsHint();

      const eurRate = $('settingEurRate');
      if (eurRate) eurRate.value = s.eur_rate_toman ?? 105000;
      if (s.eur_rate_toman) window.currentEurRate = s.eur_rate_toman;

      const tonRate = $('settingTonRate');
      if (tonRate) tonRate.value = s.ton_rate_toman ?? 0;

      const tonWallet = $('settingTonWallet');
      if (tonWallet) tonWallet.value = s.ton_wallet_address || '';

      const trxRate = $('settingTrxRate');
      if (trxRate) trxRate.value = s.trx_rate_toman ?? 0;

      const trxWallet = $('settingTrxWallet');
      if (trxWallet) trxWallet.value = s.trx_wallet_address || '';

      // Trial & Referral
      const trialTraffic = $('settingTrialTraffic');
      if (trialTraffic) trialTraffic.value = s.trial_traffic_gb ?? 1;

      const trialDays = $('settingTrialDays');
      if (trialDays) trialDays.value = s.trial_duration_days ?? 1;

      const refReward = $('settingRefReward');
      if (refReward) refReward.value = s.referral_reward_gb ?? 5;

      const supContact = $('settingSupportContact');
      if (supContact) supContact.value = s.support_contact || '';

      // Tutorial Channel URL, Routing Tutorial URL & Client App Overrides
      const tutChannelInp = $('settingTutorialChannelUrl');
      if (tutChannelInp) tutChannelInp.value = s.tutorial_channel_url || '';

      const routingTutInp = $('settingRoutingTutorialUrl');
      if (routingTutInp) routingTutInp.value = s.routing_tutorial_url || '';

      const OS_APPS_MAP = {
        ios: ['shadowrocket', 'streisand', 'v2box', 'incy', 'happ', 'onexray'],
        android: ['v2rayng', 'happ', 'hiddify', 'incy'],
        windows: ['v2rayn', 'hiddify', 'happ', 'incy'],
        macos: ['hiddify', 'happ', 'incy', 'v2box'],
        linux: ['hiddify', 'incy', 'nekoray', 'v2raya']
      };

      if (s.client_apps_json) {
        try {
          const appOverrides = typeof s.client_apps_json === 'string' ? JSON.parse(s.client_apps_json) : s.client_apps_json;
          if (appOverrides && typeof appOverrides === 'object') {
            for (const [os, appIds] of Object.entries(OS_APPS_MAP)) {
              const recSelect = $(`appRecommended_${os}`);
              if (recSelect) {
                const recVal = appOverrides.recommended?.[os] || (os === 'windows' ? appOverrides.recommended?.desktop : '') || '';
                recSelect.value = recVal;
                window.adminActions.updateRecommendedAppButton(os, recVal);
              }
              const osSource = appOverrides[os] || (os === 'windows' ? appOverrides.desktop : null);
              for (const appId of appIds) {
                const item = osSource?.[appId] || (appOverrides[appId] ? { enabled: true, download_url: appOverrides[appId], tutorial_url: '' } : null);
                const downloadEl = $(`appDownload_${os}_${appId}`);
                const downloadPortableEl = $(`appDownloadPortable_${os}_${appId}`);
                const downloadExtraEl = $(`appDownloadExtra_${os}_${appId}`);
                const tutorialEl = $(`appTutorial_${os}_${appId}`);
                const versionEl = $(`appVersion_${os}_${appId}`);
                if (downloadEl) downloadEl.value = item?.download_url || '';
                if (downloadPortableEl) downloadPortableEl.value = item?.download_portable_url || '';
                if (downloadExtraEl) downloadExtraEl.value = item?.download_extra_url || '';
                if (tutorialEl) tutorialEl.value = item?.tutorial_url || '';
                if (versionEl) versionEl.value = item?.version || '';
              }
            }
          }
        } catch (e) {}
      }

      // Telegram Supergroup Forum Topics
      const topicSettings = {
        settingTopicTopups: s.topic_topups,
        settingTopicOrders: s.topic_orders,
        settingTopicSupport: s.topic_support,
        settingTopicAlerts: s.topic_alerts,
        settingTopicBackups: s.topic_backups,
        settingTopicNodes: s.topic_nodes,
        settingTopicReports: s.topic_reports,
        settingTopicCrypto: s.topic_crypto,
        settingTopicErrors: s.topic_errors,
        settingTopicSmsManual: s.topic_sms_manual,
      };
      topicInputIds.forEach(id => {
        const inp = $(id);
        if (inp) {
          formatTopicVal(inp, topicSettings[id]);
          if (!inp._hasTopicListeners) {
            inp.addEventListener('focus', () => {
              const num = String(inp.value).match(/\d+/)?.[0] || '';
              inp.value = num;
            });
            inp.addEventListener('blur', () => {
              formatTopicVal(inp, inp.value);
            });
            inp._hasTopicListeners = true;
          }
        }
      });
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

  $('settingMaintSwitch')?.addEventListener('change', async (e) => {
    const isMaint = e.target.checked;
    const newMode = isMaint ? 'closed' : 'open';
    const accInp = $('settingAccessMode');
    if (accInp) accInp.value = newMode;
    window.adminActions.renderAccessModeUI(newMode);
    try {
      const res = await window.api.saveAdminSettings({ maintenance: isMaint, access_mode: newMode });
      if (res && res.ok) {
        if (window.showToast) window.showToast(isMaint ? '🔒 حالت تعمیرات فعال شد (دسترسی ربات بسته شد)' : '✅ حالت تعمیرات غیرفعال شد (دسترسی عمومی)');
        if (window.hapticFeedback) window.hapticFeedback('success');
      }
    } catch (err) {
      if (window.showToast) window.showToast('خطا در ذخیره وضعیت تعمیرات');
    }
  });
  $('settingCardSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('card_enabled', e.target.checked);
  });
  $('settingCryptoSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('crypto_enabled', e.target.checked);
  });
  $('settingTrialSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('trial_enabled', e.target.checked);
  });
  $('settingRefSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('referral_enabled', e.target.checked);
  });
  $('settingSupportDirectSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('support_direct_enabled', e.target.checked);
  });
  $('settingStarsSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('stars_enabled', e.target.checked);
  });
  $('settingCardRequirePhoneSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('card_require_phone_verification', e.target.checked);
  });
  $('settingCardPhoneIranSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('card_phone_iran_only', e.target.checked);
  });
  $('settingBirthdayRewardSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('birthday_reward_enabled', e.target.checked);
  });
  $('settingJoinGateSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('join_gate_enabled', e.target.checked);
  });
  $('settingAccessMode')?.addEventListener('change', (e) => {
    updateSettingToggle('access_mode', e.target.value);
  });
  $('settingAutoCleanReportsSwitch')?.addEventListener('change', (e) => {
    updateSettingToggle('auto_clean_reports', e.target.checked);
  });

  async function handleSaveAllSettings() {
    const isMaint = $('settingMaintSwitch')?.checked ?? false;
    let accessModeVal = $('settingAccessMode')?.value || 'open';
    if (isMaint) {
      accessModeVal = 'closed';
    } else if (accessModeVal === 'closed') {
      accessModeVal = 'open';
    }

    const payload = {
      maintenance: isMaint,
      access_mode: accessModeVal,
      card_enabled: $('settingCardSwitch')?.checked ?? true,
      card_auto_enabled: $('settingCardAutoSwitch')?.checked ?? false,
      sms_webhook_secret: $('settingSmsWebhookSecret')?.value?.trim() || '',
      card_require_phone_verification: $('settingCardRequirePhoneSwitch')?.checked ?? true,
      card_phone_iran_only: $('settingCardPhoneIranSwitch')?.checked ?? true,
      auto_clean_reports: $('settingAutoCleanReportsSwitch')?.checked ?? true,
      birthday_reward_enabled: $('settingBirthdayRewardSwitch')?.checked ?? true,
      birthday_reward_traffic_gb: parseInt($('settingBirthdayRewardTraffic')?.value || '2', 10),
      birthday_reward_discount_percent: parseInt($('settingBirthdayRewardDiscount')?.value || '20', 10),
      birthday_custom_message: $('settingBirthdayMessage')?.value?.trim() || '',
      card_blubank_color: $('settingBluBankColor')?.value || 'blue',
      card_graphical_view_enabled: $('settingCardGraphicalSwitch')?.checked ?? true,
      card_template: $('settingCardTemplate')?.value || 'blubank',
      default_squad_uuid: $('settingDefaultSquadUuid')?.value || '',
      join_gate_enabled: $('settingJoinGateSwitch')?.checked ?? false,
      join_gate_channel: $('settingJoinGateChannel')?.value?.trim() || '',
      crypto_enabled: $('settingCryptoSwitch')?.checked ?? false,
      stars_enabled: $('settingStarsSwitch')?.checked ?? false,
      stars_rate_toman: parseInt($('settingStarsRate')?.value || '1600', 10),
      trial_enabled: $('settingTrialSwitch')?.checked ?? true,
      referral_enabled: $('settingRefSwitch')?.checked ?? true,
      support_direct_enabled: $('settingSupportDirectSwitch')?.checked ?? true,
      card_number: $('settingCardNumber')?.value?.trim() || '',
      card_holder: $('settingCardHolder')?.value?.trim() || '',
      topup_min_amount: parseInt($('settingMinTopup')?.value || '20000', 10),
      usdt_rate_toman: parseInt($('settingUsdtRate')?.value || '95000', 10),
      eur_rate_toman: parseInt($('settingEurRate')?.value || '105000', 10),
      ton_rate_toman: parseInt($('settingTonRate')?.value || '0', 10),
      ton_wallet_address: $('settingTonWallet')?.value?.trim() || '',
      trx_enabled: $('settingTrxSwitch')?.checked ?? true,
      xrocket_enabled: false,
      trx_rate_toman: parseInt($('settingTrxRate')?.value || '0', 10),
      trx_wallet_address: $('settingTrxWallet')?.value?.trim() || '',
      xrocket_api_key: '',
      trial_traffic_gb: parseInt($('settingTrialTraffic')?.value || '1', 10),
      trial_duration_days: parseInt($('settingTrialDays')?.value || '1', 10),
      referral_reward_gb: parseInt($('settingRefReward')?.value || '5', 10),
      support_contact: $('settingSupportContact')?.value?.trim() || '',
      topic_topups: parseTopicVal($('settingTopicTopups')?.value),
      topic_orders: parseTopicVal($('settingTopicOrders')?.value),
      topic_support: parseTopicVal($('settingTopicSupport')?.value),
      topic_alerts: parseTopicVal($('settingTopicAlerts')?.value),
      topic_backups: parseTopicVal($('settingTopicBackups')?.value),
      topic_nodes: parseTopicVal($('settingTopicNodes')?.value),
      topic_reports: parseTopicVal($('settingTopicReports')?.value),
      topic_crypto: parseTopicVal($('settingTopicCrypto')?.value),
      topic_errors: parseTopicVal($('settingTopicErrors')?.value),
      topic_sms_manual: parseTopicVal($('settingTopicSmsManual')?.value),
      tutorial_channel_url: $('settingTutorialChannelUrl')?.value?.trim() || '',
      routing_tutorial_url: $('settingRoutingTutorialUrl')?.value?.trim() || '',
      client_apps_json: (() => {
        const OS_APPS_MAP = {
          ios: ['shadowrocket', 'streisand', 'v2box', 'incy', 'happ', 'onexray'],
          android: ['v2rayng', 'happ', 'hiddify', 'incy'],
          windows: ['v2rayn', 'hiddify', 'happ', 'incy'],
          macos: ['hiddify', 'happ', 'incy', 'v2box'],
          linux: ['hiddify', 'incy', 'nekoray', 'v2raya']
        };
        const clientAppsObj = {
          recommended: {
            ios: $('appRecommended_ios')?.value || '',
            android: $('appRecommended_android')?.value || '',
            windows: $('appRecommended_windows')?.value || '',
            desktop: $('appRecommended_windows')?.value || '',
            macos: $('appRecommended_macos')?.value || '',
            linux: $('appRecommended_linux')?.value || ''
          }
        };
        for (const [os, appIds] of Object.entries(OS_APPS_MAP)) {
          clientAppsObj[os] = {};
          for (const appId of appIds) {
            const downloadEl = $(`appDownload_${os}_${appId}`);
            const downloadPortableEl = $(`appDownloadPortable_${os}_${appId}`);
            const downloadExtraEl = $(`appDownloadExtra_${os}_${appId}`);
            const tutorialEl = $(`appTutorial_${os}_${appId}`);
            const versionEl = $(`appVersion_${os}_${appId}`);
            const downloadUrl = downloadEl?.value?.trim() || '';
            const downloadPortableUrl = downloadPortableEl?.value?.trim() || '';
            const downloadExtraUrl = downloadExtraEl?.value?.trim() || '';
            clientAppsObj[os][appId] = {
              enabled: Boolean(downloadUrl || downloadPortableUrl || downloadExtraUrl),
              download_url: downloadUrl,
              download_portable_url: downloadPortableUrl,
              download_extra_url: downloadExtraUrl,
              tutorial_url: tutorialEl?.value?.trim() || '',
              version: versionEl?.value?.trim() || ''
            };
          }
        }
        clientAppsObj.desktop = clientAppsObj.windows;
        return JSON.stringify(clientAppsObj);
      })(),
    };

    const saveBtns = [$('saveAllSettingsBtn'), $('saveAllSettingsTopBtn')];
    saveBtns.forEach(b => { if (b) { b.disabled = true; b.innerText = 'در حال ذخیره...'; } });

    try {
      const res = await window.api.saveAdminSettings(payload);
      if (res && res.ok) {
        topicInputIds.forEach(id => {
          const inp = $(id);
          if (inp) formatTopicVal(inp, inp.value);
        });
        if (window.showToast) window.showToast('✅ تمامی تنظیمات با موفقیت ذخیره شدند.');
        if (window.hapticFeedback) window.hapticFeedback('success');
      } else {
        if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در ثبت تنظیمات'}`);
        if (window.hapticFeedback) window.hapticFeedback('error');
      }
    } catch (e) {
      if (window.showToast) window.showToast('خطای شبکه در ذخیره تنظیمات');
    } finally {
      saveBtns.forEach(b => { if (b) { b.disabled = false; b.innerText = '💾 ذخیره تنظیمات'; } });
      const mainBtn = $('saveAllSettingsBtn');
      if (mainBtn) mainBtn.innerHTML = '<span>💾</span> ذخیره تنظیمات';
    }
  }

  $('saveAllSettingsBtn')?.addEventListener('click', handleSaveAllSettings);
  $('saveAllSettingsTopBtn')?.addEventListener('click', handleSaveAllSettings);

  // Settings Accordion Boxes toggle handled by window.adminActions.toggleSettingsBox

  // Crypto rates modal trigger in settings
  $('openCryptoRatesModalBtn')?.addEventListener('click', () => {
    window.adminActions.openCryptoRatesModal();
  });


  // --- 9. Broadcast Modal & Live Report Modal ---
  const broadcastModal = $('broadcastModal');
  const broadcastReportModal = $('broadcastReportModal');
  const openBroadcastModalBtn = $('openBroadcastModalBtn');
  const closeBroadcastBtn = $('closeBroadcastBtn');
  const sendBroadcastBtn = $('sendBroadcastBtn');
  const closeBroadcastReportBtn = $('closeBroadcastReportBtn');
  const dismissReportModalBtn = $('dismissReportModalBtn');

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
        b.className = 'broadcast-audience-btn px-2.5 py-1 rounded-xl card-inset t-muted hover:t-main text-[10.5px] font-medium transition border border-slate-700/50';
      });
      btn.className = 'broadcast-audience-btn px-2.5 py-1 rounded-xl bg-blue-600 text-white font-bold text-[10.5px] transition border border-blue-500 shadow-sm';
      currentBroadcastTarget = btn.getAttribute('data-target') || 'all';

      const labelMap = {
        all: 'کل کاربران ربات',
        active: 'کاربران با سرویس فعال',
        expired: 'کاربران منقضی شده',
        buyers: 'خریداران قبلی',
        balance: 'کاربران دارای موجودی کیف پول',
      };
      const targetLabel = $('broadcastTargetLabel');
      if (targetLabel) targetLabel.innerText = labelMap[currentBroadcastTarget] || 'کاربران';

      if (window.hapticFeedback) window.hapticFeedback('impact');
    });
  });

  sendBroadcastBtn?.addEventListener('click', async () => {
    const txt = $('broadcastTextArea')?.value?.trim();
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
        const txtEl = $('broadcastTextArea');
        if (txtEl) txtEl.value = '';

        // Open Live Progress Report Modal
        if (broadcastReportModal) {
          broadcastReportModal.classList.remove('hidden');
          const targetEl = $('reportTargetLabel');
          if (targetEl) targetEl.innerText = res.stats?.target_label || 'همه کاربران';
          const totalEl = $('reportTotalCount');
          if (totalEl) totalEl.innerText = `${formatNumber(res.stats?.total || 0)} نفر`;
          const sentEl = $('reportSentCount');
          if (sentEl) sentEl.innerText = '0 پیام';
          const failEl = $('reportFailedCount');
          if (failEl) failEl.innerText = '0';
          const statusEl = $('reportStatusText');
          if (statusEl) statusEl.innerText = 'در حال ارسال پیام‌ها...';
          const pBar = $('reportProgressBar');
          if (pBar) pBar.style.width = '10%';
          const pText = $('reportPercentText');
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


  async function fetchGithubAppVersion(appId, os) {
    if (!appId) return;
    try {
      if (window.hapticFeedback) window.hapticFeedback('selection');
      const res = await window.api.getGithubReleases(appId);
      if (res && res.ok && res.versions && res.versions[appId]) {
        const ver = res.versions[appId];
        const versionEl = $(`appVersion_${os}_${appId}`);
        if (versionEl) {
          versionEl.value = ver;
          versionEl.focus();
        }
        if (window.showToast) window.showToast(`✅ نسخه ${ver} از GitHub دریافت شد.`);
        if (window.hapticFeedback) window.hapticFeedback('success');
      } else {
        if (window.showToast) window.showToast('⚠️ نسخه‌ای در گیت‌هاب برای این برنامه یافت نشد.');
      }
    } catch (e) {
      if (window.showToast) window.showToast('❌ خطا در ارتباط با گیت‌هاب.');
    }
  }

  async function syncAllGithubVersions() {
    const btn = $('syncAllGithubVersionsBtn');
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span>⏳</span><span>در حال دریافت نسخه‌ها از GitHub...</span>';
    }
    try {
      if (window.hapticFeedback) window.hapticFeedback('impact');
      const res = await window.api.getGithubReleases();
      if (res && res.ok && res.versions) {
        let count = 0;
        const OS_APPS_MAP = {
          ios: ['shadowrocket', 'streisand', 'v2box', 'incy', 'happ', 'onexray'],
          android: ['v2rayng', 'happ', 'hiddify', 'incy'],
          windows: ['v2rayn', 'hiddify', 'happ', 'incy'],
          macos: ['hiddify', 'happ', 'incy', 'v2box'],
          linux: ['hiddify', 'incy', 'nekoray', 'v2raya']
        };
        for (const [os, appIds] of Object.entries(OS_APPS_MAP)) {
          for (const appId of appIds) {
            if (res.versions[appId]) {
              const versionEl = $(`appVersion_${os}_${appId}`);
              if (versionEl) {
                versionEl.value = res.versions[appId];
                count++;
              }
            }
          }
        }
        if (window.showToast) window.showToast(`✅ تعداد ${count} نسخه از GitHub بروزرسانی شدند. برای اعمال «ذخیره تغییرات» را بزنید.`);
        if (window.hapticFeedback) window.hapticFeedback('success');
      } else {
        if (window.showToast) window.showToast('⚠️ خطا در دریافت نسخه‌ها از گیت‌هاب.');
      }
    } catch (e) {
      if (window.showToast) window.showToast('❌ خطا در ارتباط با گیت‌هاب.');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = origHtml;
      }
    }
  }

  window.fetchGithubAppVersion = fetchGithubAppVersion;
  window.syncAllGithubVersions = syncAllGithubVersions;

  // Explicit event listeners for Admin App Tabs and Due Date buttons
  document.querySelectorAll('.admin-app-os-tab').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const id = btn.id || '';
      const os = id.replace('adminAppTab_', '');
      if (os) window.switchAdminAppsTab(os);
    });
  });


  // Global exports
  window.fetchAdminSettings = fetchAdminSettings;
  window.fetchTicketThreads = fetchTicketThreads;
  window.loadUserChatMessages = loadUserChatMessages;
})(window);
