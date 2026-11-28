/**
 * RemnaStore Pro - Engagement Features Engine
 * Covers:
 * 1. Smart Renewal Advisor -> Custom Plan Slider Sync
 * 2. Loyalty-Tiered Card & Story Themes
 * 3. Weekly Interactive Quests (Spin Tickets & Badges ONLY)
 * 4. Group Gift / Red Packet (Create, Share, History, Refund, Claim)
 * 5. Leaderboard Champion Badge
 * 6. Direct P2P Wallet Transfer
 */
(function (global) {
  'use strict';

  const THEME_STORAGE_KEY = 'remna_card_theme';
  const _recordedWeekEvents = new Set();

  const DEFAULT_THEMES = [
    {
      id: 'ocean',
      name: 'اقیانوس نئون',
      nameEn: 'Neon Ocean',
      min_tier: 'bronze',
      min_tier_label: 'برنزی',
      min_tier_label_en: 'Bronze',
      unlocked: true,
      selected: true,
      accent: '#38bdf8',
      secondary: '#6366f1',
      bg_from: '#0b0f19',
      bg_mid: '#131b2e',
      bg_to: '#1e1b4b',
      border_rgba: 'rgba(99, 102, 241, 0.45)',
    },
  ];

  function _esc(val) {
    if (typeof escapeHtml === 'function') return escapeHtml(String(val ?? ''));
    return String(val ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function _isEn() {
    return typeof getAppLanguage === 'function' && getAppLanguage() === 'en';
  }

  function _fmtNum(n) {
    const val = Number(n || 0);
    return Number.isFinite(val) ? val.toLocaleString('en-US') : '0';
  }

  function _haptic(type = 'selection') {
    const fn = window.api?.haptic || window.hapticFeedback || global.hapticFeedback;
    if (typeof fn === 'function') fn(type);
  }

  // ------------------------------------------------------------------
  // 1. Smart Renewal Advisor
  // ------------------------------------------------------------------
  function applySmartRenewalAdvisor(recGb, recDays) {
    _haptic('selection');
    if (typeof window.switchTab === 'function') {
      window.switchTab('tab-shop');
    }
    if (typeof window.switchShopCategory === 'function') {
      window.switchShopCategory('custom');
    }
    const gbSlider = document.getElementById('customPlanGbSlider');
    const daysSlider = document.getElementById('customPlanDaysSlider');
    if (gbSlider && Number.isFinite(Number(recGb))) {
      const minG = Number(gbSlider.min || 5);
      const maxG = Number(gbSlider.max || 300);
      gbSlider.value = String(Math.max(minG, Math.min(maxG, Math.round(Number(recGb)))));
    }
    if (daysSlider && Number.isFinite(Number(recDays))) {
      const minD = Number(daysSlider.min || 10);
      const maxD = Number(daysSlider.max || 180);
      daysSlider.value = String(Math.max(minD, Math.min(maxD, Math.round(Number(recDays)))));
    }
    if (typeof window.initCustomPlanBuilder === 'function') {
      window.initCustomPlanBuilder();
    } else if (typeof window.updateCustomPlanCalculation === 'function') {
      window.updateCustomPlanCalculation();
    }
    const builder = document.getElementById('customPlanBuilderContainer');
    if (builder && typeof builder.scrollIntoView === 'function') {
      setTimeout(() => builder.scrollIntoView({ behavior: 'smooth', block: 'center' }), 80);
    }
    if (typeof showToast === 'function') {
      showToast(
        _isEn()
          ? `Suggested custom plan (${recGb} GB / ${recDays} days) applied.`
          : `پیشنهاد هوشمند (${recGb} GB / ${recDays} روز) روی بسته دلخواه تنظیم شد.`,
        'success'
      );
    }
  }
  window.applySmartRenewalAdvisor = applySmartRenewalAdvisor;

  function renderSmartRenewalAdvisor(data) {
    const advisor = data?.active_sub?.burn_rate?.advisor;
    const analyticsBox = document.getElementById('smartRenewalAdvisorBox');
    const dashChip = document.getElementById('dashboardRenewalAdvisorChip');

    if (!advisor || !data?.has_active_sub) {
      if (analyticsBox) analyticsBox.classList.add('hidden');
      if (dashChip) dashChip.classList.add('hidden');
      return;
    }

    const recGb = Number(advisor.recommended_gb || 30);
    const recDays = Number(advisor.recommended_days || 30);
    const canCustom = advisor.custom_plan_enabled !== false;

    if (analyticsBox) {
      analyticsBox.classList.remove('hidden');
      analyticsBox.innerHTML = `
        <div class="space-y-1 min-w-0">
          <b class="text-xs t-main flex items-center gap-1.5">
            ${typeof uiIcon === 'function' ? uiIcon('sparkles', 'w-3.5 h-3.5 text-cyan-500 shrink-0') : ''}
            <span>${_esc(advisor.title)}</span>
          </b>
          <p class="text-[11px] t-muted leading-relaxed">${_esc(advisor.summary)}</p>
        </div>
        ${canCustom ? `
          <button type="button" onclick="window.applySmartRenewalAdvisor(${recGb}, ${recDays})" class="btn btn-primary w-full py-2 rounded-xl text-[11px] font-bold flex items-center justify-center gap-1.5 active:scale-[0.98] transition mt-2">
            ${typeof uiIcon === 'function' ? uiIcon('zap', 'w-3.5 h-3.5 shrink-0') : ''}
            <span>${_esc(advisor.cta_label)}</span>
          </button>
        ` : ''}
      `;
    }

    if (dashChip) {
      const showDashAlert = canCustom && (advisor.status === 'fast' || advisor.status === 'exhausted');
      dashChip.classList.toggle('hidden', !showDashAlert);
      if (showDashAlert) {
        const recTraffic = typeof fmtTraffic === 'function' ? fmtTraffic(recGb, { html: false }) : `${recGb}`;
        dashChip.innerHTML = `
          <button type="button" onclick="window.applySmartRenewalAdvisor(${recGb}, ${recDays})" class="w-full s-warn-soft border border-amber-500/35 rounded-xl px-3 py-2 text-[11px] font-bold flex items-center justify-between gap-2 active:scale-[0.99] transition">
            <span class="flex items-center gap-1.5 truncate">
              ${typeof uiIcon === 'function' ? uiIcon('sparkles', 'w-3.5 h-3.5 shrink-0') : ''}
              <span class="truncate">${_esc(advisor.title)}: <b class="font-sans num-bidi" dir="ltr">${_esc(recTraffic)}</b></span>
            </span>
            <span class="underline shrink-0">${_isEn() ? 'Configure →' : 'تنظیم ←'}</span>
          </button>
        `;
      }
    }
  }

  // ------------------------------------------------------------------
  // 2. Loyalty-Tiered Card & Story Themes
  // ------------------------------------------------------------------
  function getActiveCardThemeObj(data = window.lastUserData) {
    const payload = data?.card_themes;
    const list = Array.isArray(payload?.themes) && payload.themes.length ? payload.themes : DEFAULT_THEMES;
    const savedId = payload?.selected || data?.user?.card_theme || localStorage.getItem(THEME_STORAGE_KEY) || 'ocean';
    return list.find(t => t.id === savedId && t.unlocked !== false) || list[0];
  }

  function applyCardThemeStyles(data = window.lastUserData) {
    const theme = getActiveCardThemeObj(data);
    if (!theme) return;
    try { localStorage.setItem(THEME_STORAGE_KEY, theme.id); } catch (e) {}

    const storyCard = document.getElementById('exportableStoryCard');
    if (storyCard) {
      storyCard.style.backgroundImage = `linear-gradient(160deg, ${theme.bg_from} 0%, ${theme.bg_mid} 50%, ${theme.bg_to} 100%)`;
      storyCard.style.borderColor = theme.border_rgba;
    }

    const storyAvatarRing = document.getElementById('storyAvatarBorder');
    if (storyAvatarRing) {
      storyAvatarRing.style.backgroundImage = `linear-gradient(135deg, ${theme.accent}, ${theme.secondary})`;
    }

    const storyGlow1 = document.getElementById('storyGlow1');
    if (storyGlow1) storyGlow1.style.backgroundColor = theme.accent;
    const storyGlow2 = document.getElementById('storyGlow2');
    if (storyGlow2) storyGlow2.style.backgroundColor = theme.secondary;

    const dashGauge = document.getElementById('dashboardSubGaugeCard');
    if (dashGauge) {
      dashGauge.style.borderColor = theme.id === 'ocean' ? '' : theme.border_rgba;
    }
  }

  window.getActiveStoryCanvasTheme = function () {
    return getActiveCardThemeObj(window.lastUserData);
  };

  function renderCardThemePicker(data) {
    const bar = document.getElementById('storyThemePickerBar');
    if (!bar) return;
    const payload = data?.card_themes;
    const themes = Array.isArray(payload?.themes) ? payload.themes : DEFAULT_THEMES;
    const selectedId = getActiveCardThemeObj(data)?.id || 'ocean';

    bar.innerHTML = themes.map(t => {
      const isSelected = t.id === selectedId;
      const isLocked = t.unlocked === false;
      const dispName = (_isEn() && t.nameEn) ? t.nameEn : t.name;
      const dispMinTier = (_isEn() && t.min_tier_label_en) ? t.min_tier_label_en : t.min_tier_label;
      const lockBadge = isLocked
        ? `<span class="text-[9px] leading-none">🔒</span>`
        : (isSelected ? `<span class="text-[9px] leading-none text-white">✓</span>` : '');
      const titleText = isLocked
        ? (_isEn() ? `${dispName} (Requires ${dispMinTier})` : `${dispName} (نیازمند سطح ${dispMinTier})`)
        : dispName;
      return `
        <button type="button" onclick="window.selectUserCardTheme('${_esc(t.id)}')" title="${_esc(titleText)}" class="flex flex-col items-center gap-1 p-1 rounded-xl border transition active:scale-95 ${isSelected ? 'border-cyan-400 s-accent-soft' : 'border-card-border card-inset'} ${isLocked ? 'opacity-65' : ''}">
          <span class="w-7 h-7 rounded-full border border-white/40 shadow-sm flex items-center justify-center" style="background: linear-gradient(135deg, ${_esc(t.accent)}, ${_esc(t.secondary)});">${lockBadge}</span>
          <span class="text-[10px] t-muted truncate max-w-[54px] font-medium">${_esc(dispName)}</span>
        </button>
      `;
    }).join('');

    applyCardThemeStyles(data);
  }

  async function selectUserCardTheme(themeId) {
    const themes = window.lastUserData?.card_themes?.themes || DEFAULT_THEMES;
    const chosen = themes.find(t => t.id === themeId);
    if (!chosen) return;
    if (chosen.unlocked === false) {
      _haptic('error');
      const dispName = (_isEn() && chosen.nameEn) ? chosen.nameEn : chosen.name;
      const dispMinTier = (_isEn() && chosen.min_tier_label_en) ? chosen.min_tier_label_en : chosen.min_tier_label;
      if (typeof showToast === 'function') {
        showToast(
          _isEn()
            ? `Unlock ${dispName} with ${dispMinTier} Loyalty tier!`
            : `برای استفاده از تم «${dispName}»، باید به سطح وفاداری ${dispMinTier} برسید.`,
          'warning'
        );
      }
      return;
    }

    _haptic('selection');
    if (window.lastUserData?.card_themes) {
      window.lastUserData.card_themes.selected = themeId;
      window.lastUserData.card_themes.themes.forEach(t => { t.selected = (t.id === themeId); });
    }
    if (window.lastUserData?.user) window.lastUserData.user.card_theme = themeId;
    renderCardThemePicker(window.lastUserData);

    try {
      const res = await window.api.setCardTheme(themeId);
      if (res && res.ok) {
        if (window.lastUserData && res.card_themes) {
          window.lastUserData.card_themes = res.card_themes;
        }
        renderCardThemePicker(window.lastUserData);
      } else if (res && res.message && typeof showToast === 'function') {
        showToast(res.message, 'warning');
      }
    } catch (err) {
      console.warn('Theme sync error:', err);
    }
  }
  window.selectUserCardTheme = selectUserCardTheme;

  // ------------------------------------------------------------------
  // 3. Weekly Interactive Quests (Strictly Spin Tickets + Badges ONLY)
  // ------------------------------------------------------------------
  const QUEST_I18N_MAP = {
    weekly_speedtest: {
      fa: { title: 'تست سرعت شبکه', desc: 'یک تست سرعت کامل انجام دهید' },
      en: { title: 'Network Speed Test', desc: 'Run one complete speed test' },
    },
    weekly_wallet_card: {
      fa: { title: 'شخصی‌سازی کارت گرافیکی', desc: 'حالت گرافیکی کارت کیف پول را فعال و رنگ یا پشت کارت را بررسی کنید' },
      en: { title: 'Graphic Wallet Card', desc: 'Enable the graphic wallet card and inspect its color or back' },
    },
    weekly_wallet_boost: {
      fa: { title: 'انتقال یا شارژ رمزارز', desc: 'یک انتقال مستقیم پول انجام دهید یا کیف پول را با TON/TRX/POL شارژ کنید' },
      en: { title: 'Transfer or Crypto Top-Up', desc: 'Make a direct transfer or top up with TON/TRX/POL' },
    },
    weekly_spin_3: {
      fa: { title: 'چرخش سه‌گانه هفتگی', desc: '3 بار در این هفته گردونه شانس را بچرخانید' },
      en: { title: 'Weekly Spin Trio', desc: 'Spin the Lucky Wheel 3 times this week' },
    },
  };

  function navigateToQuest(eventType) {
    if (typeof window.closeModal === 'function') window.closeModal('weeklyQuestsModal');
    _haptic('selection');
    if (eventType === 'speedtest') {
      if (typeof window.openSpeedTestModal === 'function') window.openSpeedTestModal();
    } else if (eventType === 'wallet_card_check') {
      if (typeof window.switchTab === 'function') window.switchTab('tab-profile');
      const walletBox = document.getElementById('userBoxWalletSettings');
      if (walletBox && walletBox.classList.contains('hidden') && typeof window.toggleSettingsBox === 'function') {
        window.toggleSettingsBox('userBoxWalletSettings');
      }
      const colorRow = document.getElementById('userWalletColorRow');
      if (colorRow && typeof colorRow.scrollIntoView === 'function') {
        setTimeout(() => colorRow.scrollIntoView({ behavior: 'smooth', block: 'center' }), 80);
      }
    } else if (eventType === 'wallet_boost') {
      if (typeof window.switchTab === 'function') window.switchTab('tab-wallet');
      if (typeof window.scrollTo === 'function') window.scrollTo({ top: 0, behavior: 'smooth' });
    } else if (eventType === 'spin') {
      if (typeof window.openLuckyWheel === 'function') window.openLuckyWheel();
    }
  }

  function _bindQuestNavigation(container) {
    if (!container) return;
    container.querySelectorAll('.quest-nav-card').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target && e.target.closest && e.target.closest('button')) return;
        const ev = card.getAttribute('data-quest-event');
        if (ev) navigateToQuest(ev);
      });
    });
  }

  function buildQuestsListHtml(questsData) {
    const list = questsData?.quests;
    if (!Array.isArray(list) || !list.length) {
      return `<div class="p-3 card-inset rounded-xl text-center text-xs t-muted">${_isEn() ? 'No quests active this week.' : 'مأموریت فعالی برای این هفته ثبت نشده است.'}</div>`;
    }
    const langKey = _isEn() ? 'en' : 'fa';
    return list.map(q => {
      const prog = Number(q.progress || 0);
      const target = Math.max(1, Number(q.target || 1));
      const pct = Math.min(100, Math.round((prog / target) * 100));
      const localized = QUEST_I18N_MAP[q.id]?.[langKey];
      const titleText = localized?.title || q.title;
      const descText = localized?.desc || q.description;
      let actionHtml = '';
      if (q.is_claimed) {
        actionHtml = `<span class="px-2 py-1 rounded-lg s-success-soft border border-emerald-500/30 text-[10px] font-bold shrink-0">✓ ${_isEn() ? 'Claimed' : 'دریافت شد'}</span>`;
      } else if (q.can_claim) {
        actionHtml = `<button type="button" onclick="window.claimWeeklyQuest('${_esc(q.id)}')" class="px-2.5 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-black text-[11px] shadow-sm active:scale-95 transition shrink-0 inline-flex items-center gap-1"><span dir="ltr" class="inline-block font-sans num-bidi font-black">+${_esc(q.reward_tickets)}</span><span>🎟</span></button>`;
      } else {
        actionHtml = `<span class="px-2 py-1 rounded-lg card-inset border border-card-border text-[10px] font-sans font-bold t-muted shrink-0 num-bidi" dir="ltr">${prog}/${target}</span>`;
      }

      return `
        <div role="button" tabindex="0" data-quest-event="${_esc(q.event)}" class="quest-nav-card cursor-pointer hover:border-cyan-500/40 active:scale-[0.99] card-inset p-2.5 rounded-xl border border-card-border space-y-1.5 transition">
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2 min-w-0">
              <span class="w-7 h-7 rounded-lg s-accent-soft border flex items-center justify-center shrink-0">
                ${typeof uiIcon === 'function' ? uiIcon(q.icon || 'sparkles', 'w-3.5 h-3.5') : ''}
              </span>
              <div class="min-w-0">
                <b class="text-xs t-main block truncate">${_esc(titleText)}</b>
                <span class="text-[11px] t-muted block truncate">${_esc(descText)}</span>
              </div>
            </div>
            ${actionHtml}
          </div>
          <div class="w-full h-1.5 rounded-full bg-slate-500/15 overflow-hidden">
            <div class="h-full rounded-full bg-gradient-to-r from-amber-400 to-cyan-400 transition-all duration-300" style="width: ${pct}%;"></div>
          </div>
        </div>
      `;
    }).join('');
  }

  function renderWeeklyQuests(data) {
    const quests = data?.quests;
    const inlineContainer = document.getElementById('userWeeklyQuestsList');
    const modalContainer = document.getElementById('weeklyQuestsModalList');
    const countBadge = document.getElementById('userWeeklyQuestsCount');
    const wheelQuestsBadge = document.getElementById('wheelQuestsBadge');

    if (quests && countBadge) {
      countBadge.innerText = `${Number(quests.completed_count || 0)} / ${Number(quests.total_count || 4)}`;
    }
    if (wheelQuestsBadge) {
      wheelQuestsBadge.innerText = _isEn() ? 'Quests' : 'مأموریت‌ها';
    }
    const html = buildQuestsListHtml(quests);
    if (inlineContainer) {
      inlineContainer.innerHTML = html;
      _bindQuestNavigation(inlineContainer);
    }
    if (modalContainer) {
      modalContainer.innerHTML = html;
      _bindQuestNavigation(modalContainer);
    }
  }

  async function recordWeeklyQuestEvent(eventName) {
    const clean = String(eventName || '').trim().toLowerCase();
    if (!clean || !window.api?.recordQuestEvent) return;

    // Avoid redundant network requests once the weekly quest is already fulfilled or claimed
    const existingQuests = window.lastUserData?.quests?.quests;
    const prevReadyIds = new Set(
      Array.isArray(existingQuests)
        ? existingQuests.filter(q => q.can_claim || q.is_claimed).map(q => q.id)
        : []
    );
    if (Array.isArray(existingQuests)) {
      const matching = existingQuests.filter(q => q.event === clean);
      if (matching.length && matching.every(q => q.is_completed || q.is_claimed)) {
        return;
      }
    }
    if (_recordedWeekEvents.has(clean)) return;
    _recordedWeekEvents.add(clean);

    try {
      const res = await window.api.recordQuestEvent(clean);
      if (res && res.ok && res.quests && window.lastUserData) {
        window.lastUserData.quests = res.quests;
        renderWeeklyQuests(window.lastUserData);
        const newlyReady = (res.quests.quests || []).some(q => q.can_claim && !prevReadyIds.has(q.id));
        if (newlyReady) {
          _haptic('success');
          if (typeof window.playSubtleSound === 'function') window.playSubtleSound('coin_success');
          if (typeof showToast === 'function') {
            showToast(_isEn() ? '🎉 Quest completed! Claim your wheel ticket.' : '🎉 مأموریت تکمیل شد! بلیت گردونه آماده دریافت است.', 'success');
          }
        }
      }
    } catch (e) {
      _recordedWeekEvents.delete(clean);
    }
  }
  window.recordWeeklyQuestEvent = recordWeeklyQuestEvent;

  async function claimWeeklyQuest(questId) {
    _haptic('impact');
    try {
      const res = await window.api.claimWeeklyQuest(questId);
      if (!res || !res.ok) {
        _haptic('error');
        if (typeof showToast === 'function') {
          showToast(res?.message || (_isEn() ? 'Error claiming quest.' : 'خطا در دریافت پاداش مأموریت.'), 'warning');
        }
        return;
      }
      _haptic('success');
      if (typeof window.playSubtleSound === 'function') window.playSubtleSound('coin_success');
      if (typeof window.launchCelebrationConfetti === 'function') window.launchCelebrationConfetti();
      if (window.lastUserData) {
        if (res.quests) window.lastUserData.quests = res.quests;
        if (typeof res.spin_tickets === 'number') {
          window.lastUserData.achievements = window.lastUserData.achievements || {};
          window.lastUserData.achievements.spin_tickets = res.spin_tickets;
          window.lastUserData.wheel_status = window.lastUserData.wheel_status || {};
          window.lastUserData.wheel_status.spin_tickets = res.spin_tickets;
          if (typeof window.renderUserAchievements === 'function') window.renderUserAchievements(window.lastUserData);
          if (typeof window.updateWheelUIState === 'function' && window.lastUserData.wheel_status) {
            const ws = window.lastUserData.wheel_status;
            window.updateWheelUIState(ws.can_spin || res.spin_tickets > 0, ws.has_active_sub, ws.next_spin_seconds || 0, ws.streak || 0, ws.streak_multiplier || 1, res.spin_tickets);
          }
        }
        renderWeeklyQuests(window.lastUserData);
      }
      if (typeof showToast === 'function') showToast(res.message, 'success');
    } catch (err) {
      if (typeof showToast === 'function') showToast(_isEn() ? 'Server error.' : 'خطا در ارتباط با سرور.', 'error');
    }
  }
  window.claimWeeklyQuest = claimWeeklyQuest;

  const _celebratedQuestIds = new Set();
  function celebrateReadyQuestsIfAny(data = window.lastUserData) {
    const list = data?.quests?.quests;
    if (!Array.isArray(list) || !list.length) return;
    const freshReady = list.filter(q => q.can_claim && !_celebratedQuestIds.has(q.id));
    if (!freshReady.length) return;
    freshReady.forEach(q => _celebratedQuestIds.add(q.id));
    _haptic('success');
    if (typeof window.playSubtleSound === 'function') window.playSubtleSound('coin_success');
  }
  window.celebrateReadyQuestsIfAny = celebrateReadyQuestsIfAny;

  window.openWeeklyQuestsModal = function () {
    renderWeeklyQuests(window.lastUserData);
    celebrateReadyQuestsIfAny(window.lastUserData);
    if (typeof openModal === 'function') openModal('weeklyQuestsModal');
    if (typeof syncTelegramBackButton === 'function') syncTelegramBackButton();
  };
  window.closeWeeklyQuestsModal = function () {
    if (typeof closeModal === 'function') closeModal('weeklyQuestsModal');
    if (typeof syncTelegramBackButton === 'function') syncTelegramBackButton();
  };

  // ------------------------------------------------------------------
  // 4. Leaderboard Champion Badge
  // ------------------------------------------------------------------
  function renderChampionBadges(data) {
    const badge = data?.leaderboard_badge || data?.user?.leaderboard_badge;
    const profEl = document.getElementById('profileChampionBadge');
    const storyEl = document.getElementById('storyChampionBadge');

    [profEl, storyEl].forEach(el => {
      if (!el) return;
      if (!badge || !badge.title) {
        el.classList.add('hidden');
        el.textContent = '';
        return;
      }
      el.classList.remove('hidden');
      el.textContent = badge.title;
    });
  }

  window.getActiveChampionBadge = function () {
    return window.lastUserData?.leaderboard_badge || window.lastUserData?.user?.leaderboard_badge || null;
  };

  // ------------------------------------------------------------------
  // 5. Group Gift Red Packet
  // ------------------------------------------------------------------
  let _redPacketSplitMode = 'RANDOM';
  window.setRedPacketSplitMode = function (mode) {
    _redPacketSplitMode = mode === 'EQUAL' ? 'EQUAL' : 'RANDOM';
    const rBtn = document.getElementById('rpSplitBtn-random');
    const eBtn = document.getElementById('rpSplitBtn-equal');
    const act = 'py-2 px-3 rounded-xl bg-amber-500 text-slate-950 font-bold text-xs transition shadow-sm';
    const inact = 'py-2 px-3 rounded-xl card-inset border border-card-border t-muted hover:t-main font-medium text-xs transition';
    if (rBtn) rBtn.className = _redPacketSplitMode === 'RANDOM' ? act : inact;
    if (eBtn) eBtn.className = _redPacketSplitMode === 'EQUAL' ? act : inact;
  };

  window.setRedPacketAmountPreset = function (amt) {
    const inp = document.getElementById('redPacketAmountInput');
    if (inp) {
      inp.value = String(amt);
      if (typeof window.updateGiftCostDisplay === 'function') window.updateGiftCostDisplay();
    }
  };

  window.submitCreateRedPacket = async function () {
    const btn = document.getElementById('submitCreateGiftBtn');
    const totalAmt = Number(document.getElementById('redPacketAmountInput')?.value || 0);
    const maxClaims = Number(document.getElementById('redPacketSlotsInput')?.value || 0);
    const message = document.getElementById('giftMessageInput')?.value.trim() || '';

    if (!Number.isInteger(maxClaims) || maxClaims < 2 || maxClaims > 50) {
      if (typeof showToast === 'function') showToast(_isEn() ? 'Participants must be 2 to 50.' : 'تعداد نفرات پاکت باید بین 2 تا 50 نفر باشد.', 'warning');
      return;
    }
    const minTotal = maxClaims * 5000;
    if (!Number.isInteger(totalAmt) || totalAmt < minTotal || totalAmt > 50000000) {
      if (typeof showToast === 'function') showToast(_isEn() ? `Minimum total is ${_fmtNum(minTotal)} Toman.` : `حداقل مبلغ کل باید ${_fmtNum(minTotal)} تومان باشد.`, 'warning');
      return;
    }

    if (btn) btn.disabled = true;
    try {
      const res = await window.api.createRedPacket({
        total_amount: totalAmt,
        max_claims: maxClaims,
        split_mode: _redPacketSplitMode,
        message,
      });
      if (!res || !res.ok) {
        _haptic('error');
        if (typeof showToast === 'function') {
          showToast(res?.message || (_isEn() ? 'Error creating Red Packet.' : 'خطا در ایجاد پاکت گروهی.'), 'error');
        }
        return;
      }
      _haptic('success');
      if (typeof showToast === 'function') {
        showToast(res.message || (_isEn() ? 'Group Red Packet created!' : 'پاکت گروهی ایجاد شد!'), 'success');
      }

      const box = document.getElementById('giftCreatedSuccessBox');
      const codeInp = document.getElementById('giftCreatedCodeInput');
      const linkInp = document.getElementById('giftCreatedLinkInput');
      const notice = document.getElementById('giftCreatedNotice');
      if (box) box.classList.remove('hidden');
      if (codeInp) codeInp.value = res.code || '';
      if (linkInp) linkInp.value = res.share_url || res.code || '';
      if (notice) {
        notice.innerText = _isEn()
          ? `Share this link in your group! ${maxClaims} people can claim from ${_fmtNum(totalAmt)} Toman (expires in 48h).`
          : `این لینک را در گروه دوستان ارسال کنید! حداکثر ${maxClaims} نفر می‌توانند از مبلغ ${_fmtNum(totalAmt)} تومان سهم خود را دریافت کنند (مهلت 48 ساعت).`;
      }
      if (typeof res.new_balance === 'number') {
        const balDisp = document.getElementById('giftCurrentBalanceDisplay');
        if (balDisp) balDisp.innerText = _fmtNum(res.new_balance);
      }
      if (typeof window.syncUserDataWithApi === 'function') window.syncUserDataWithApi(window.currentAccountId);
    } catch (e) {
      if (typeof showToast === 'function') showToast(_isEn() ? 'Server error.' : 'خطا در ارتباط با سرور.', 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  };

  window.renderRedPacketsHistory = async function () {
    const box = document.getElementById('giftRedPacketsHistoryList');
    if (!box || !window.api?.getRedPacketsHistory) return;
    box.innerHTML = `<div class="p-2.5 rounded-xl card-inset text-center text-[11px] t-muted">${_isEn() ? 'Loading Red Packets...' : 'در حال دریافت پاکت‌های گروهی...'}</div>`;
    try {
      const res = await window.api.getRedPacketsHistory();
      const sent = res?.red_packets?.sent || [];
      if (!sent.length) {
        box.innerHTML = `<div class="p-2.5 rounded-xl card-inset text-center text-[11px] t-muted">${_isEn() ? 'No group Red Packets created yet.' : 'هنوز پاکت شانس گروهی نساخته‌اید.'}</div>`;
        return;
      }
      box.innerHTML = sent.map(rp => {
        const refundBtn = rp.can_refund
          ? `<button type="button" onclick="window.refundRedPacketItem(${Number(rp.id)})" class="px-2 py-0.5 rounded-lg s-warn-soft border border-amber-500/30 text-[10px] font-bold active:scale-95 transition">${_isEn() ? 'Refund' : 'استرداد'}</button>`
          : '';
        return `
          <div class="card-inset p-2.5 rounded-xl border border-card-border space-y-1 text-xs">
            <div class="flex items-center justify-between gap-2">
              <b class="text-[11px] t-main font-sans num-bidi">${_fmtNum(rp.total_amount)} ${_isEn() ? 'Toman' : 'تومان'}</b>
              <div class="flex items-center gap-1.5">
                <span class="text-[10px] font-sans font-bold px-2 py-0.5 rounded-full card-inset border border-card-border num-bidi" dir="ltr">${rp.claimed_count}/${rp.max_claims}</span>
                ${refundBtn}
              </div>
            </div>
            <div class="flex items-center justify-between text-[11px] pt-1 border-t border-card-border">
              <button type="button" data-rp-link="${_esc(rp.share_url)}" class="rp-copy-link-btn t-accent font-bold hover:underline bg-transparent border-0 p-0">${_isEn() ? 'Copy Group Link' : 'کپی لینک گروهی'}</button>
              <code class="font-sans t-muted text-[10px] select-all" dir="ltr">${_esc(rp.code)}</code>
            </div>
          </div>
        `;
      }).join('');
      box.querySelectorAll('.rp-copy-link-btn').forEach(btn => {
        btn.onclick = () => {
          if (btn.dataset.rpLink && typeof copyToClipboard === 'function') {
            copyToClipboard(btn.dataset.rpLink);
            if (typeof showToast === 'function') showToast(_isEn() ? 'Copied!' : 'لینک کپی شد!');
          }
        };
      });
    } catch (e) {
      box.innerHTML = '';
    }
  };

  window.refundRedPacketItem = async function (packetId) {
    try {
      const res = await window.api.refundRedPacket(packetId);
      if (res && res.ok) {
        _haptic('success');
        if (typeof showToast === 'function') showToast(res.message, 'success');
        window.renderRedPacketsHistory();
        if (typeof window.syncUserDataWithApi === 'function') window.syncUserDataWithApi(window.currentAccountId);
      } else if (typeof showToast === 'function') {
        showToast(res?.message || (_isEn() ? 'Error' : 'خطا'), 'warning');
      }
    } catch (e) {}
  };

  let _checkedDropStartParam = false;
  async function checkStartParamRedPacket() {
    if (_checkedDropStartParam) return;
    const rawStart =
      window.Telegram?.WebApp?.initDataUnsafe?.start_param
      || new URLSearchParams(window.location.search).get('startapp')
      || '';
    if (!rawStart || !rawStart.startsWith('drop_')) return;
    _checkedDropStartParam = true;
    const code = rawStart.replace(/^drop_/, '').trim().toUpperCase();
    if (!code || !window.api?.claimRedPacket) return;
    try {
      const res = await window.api.claimRedPacket(code);
      if (res && res.ok) {
        _haptic('success');
        if (typeof window.launchCelebrationConfetti === 'function') window.launchCelebrationConfetti();
        if (typeof showToast === 'function') showToast(res.message, 'success', 5000);
        if (typeof window.syncUserDataWithApi === 'function') window.syncUserDataWithApi(window.currentAccountId);
      } else if (res && res.message && typeof showToast === 'function') {
        showToast(res.message, 'warning', 4500);
      }
    } catch (e) {}
  }

  // ------------------------------------------------------------------
  // 6. Direct P2P Wallet Transfer
  // ------------------------------------------------------------------
  window.openWalletTransferModal = function () {
    _haptic('selection');
    const balEl = document.getElementById('transferCurrentBalance');
    const curBal = Number(window.lastUserData?.user?.wallet_balance || 0);
    if (balEl) balEl.innerText = _fmtNum(curBal);
    const recEl = document.getElementById('transferRecipientInput');
    const amtEl = document.getElementById('transferAmountInput');
    const noteEl = document.getElementById('transferNoteInput');
    if (recEl) recEl.value = '';
    if (amtEl) amtEl.value = '';
    if (noteEl) noteEl.value = '';
    if (typeof openModal === 'function') openModal('walletTransferModal');
    if (typeof syncTelegramBackButton === 'function') syncTelegramBackButton();
  };

  window.closeWalletTransferModal = function () {
    if (typeof closeModal === 'function') closeModal('walletTransferModal');
    if (typeof syncTelegramBackButton === 'function') syncTelegramBackButton();
  };

  window.setTransferAmountPreset = function (amt) {
    const el = document.getElementById('transferAmountInput');
    if (el) el.value = String(amt);
    _haptic('selection');
  };

  window.submitWalletTransfer = async function () {
    const rec = document.getElementById('transferRecipientInput')?.value.trim() || '';
    const amt = Number(document.getElementById('transferAmountInput')?.value || 0);
    const note = document.getElementById('transferNoteInput')?.value.trim() || '';
    const btn = document.getElementById('submitWalletTransferBtn');

    if (!rec) {
      if (typeof showToast === 'function') showToast(_isEn() ? 'Enter @username or Telegram ID.' : 'لطفاً آیدی یا شناسه عددی گیرنده را وارد کنید.', 'warning');
      return;
    }
    if (!Number.isInteger(amt) || amt < 5000 || amt > 50000000) {
      if (typeof showToast === 'function') showToast(_isEn() ? 'Amount must be between 5,000 and 50,000,000 Toman.' : 'مبلغ انتقال باید بین 5,000 تا 50,000,000 تومان باشد.', 'warning');
      return;
    }

    if (btn) btn.disabled = true;
    try {
      const res = await window.api.transferWalletBalance({ recipient: rec, amount: amt, note });
      if (!res || !res.ok) {
        _haptic('error');
        if (typeof showToast === 'function') {
          showToast(res?.message || (_isEn() ? 'Transfer failed.' : 'خطا در انتقال موجودی.'), 'error');
        }
        return;
      }
      _haptic('success');
      if (typeof showToast === 'function') showToast(res.message, 'success', 4500);
      window.closeWalletTransferModal();
      if (typeof window.syncUserDataWithApi === 'function') window.syncUserDataWithApi(window.currentAccountId);
    } catch (e) {
      if (typeof showToast === 'function') showToast(_isEn() ? 'Server error.' : 'خطا در ارتباط با سرور.', 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  };

  // Master entry point called by applySyncedUserData(data)
  window.renderEngagementFeatures = function (data) {
    renderSmartRenewalAdvisor(data);
    renderCardThemePicker(data);
    renderWeeklyQuests(data);
    renderChampionBadges(data);
    checkStartParamRedPacket();
  };
})(window);
