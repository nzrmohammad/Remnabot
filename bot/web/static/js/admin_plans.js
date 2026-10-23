/**
 * RemnaAdmin Pro - Plans & Coupons Module (admin_plans.js)
 * Service packages, plan categories, squads, duration/traffic limits and discount coupons.
 */
(function (window) {
  'use strict';

  const $ = id => document.getElementById(id);
  const api = window.api;
  const tg = window.Telegram?.WebApp;
  const formatNumber = window.formatNumber || (n => String(n));
  const formatDateToJalali = window.formatDateToJalali || (d => d);
  window.adminActions = window.adminActions || {};

  window.adminPlansData = window.adminPlansData || [];
  window.adminCouponsData = window.adminCouponsData || [];
  let adminPlansData = window.adminPlansData;
  let adminCouponsData = window.adminCouponsData;

  // Plans & Coupons Actions
  Object.assign(window.adminActions, {
// --- Plans Actions ---
    currentPlanFilter: 'all',
    filterPlans(cat = 'all') {
      this.currentPlanFilter = cat;
      const bar = $('adminPlanFilterBar');
      if (bar) {
        bar.querySelectorAll('.admin-plan-filter-btn').forEach(btn => {
          const match = btn.dataset.planFilter === cat;
          btn.className = match
            ? 'admin-plan-filter-btn flex-1 py-1 px-2.5 rounded-lg font-bold bg-blue-600 text-white shadow transition whitespace-nowrap text-center'
            : 'admin-plan-filter-btn flex-1 py-1 px-2.5 rounded-lg font-medium text-slate-400 hover:text-white transition whitespace-nowrap text-center';
        });
      }
      const cards = document.querySelectorAll('.admin-plan-card');
      cards.forEach(card => {
        const type = card.dataset.planType;
        const show = (cat === 'all' || type === cat);
        card.style.display = show ? '' : 'none';
      });
    },

    async fetchAdminPlans() {
      const container = $('adminPlansList');
      if (!container) return;
      if (!adminPlansData || adminPlansData.length === 0) {
        container.innerHTML = '<div class="p-8 text-center text-xs text-slate-400">در حال دریافت تعرفه‌ها...</div>';
      }
      try {
        const res = await window.api.getAdminPlans();
        if (!res || !res.ok) {
          container.innerHTML = `<div class="p-6 text-center text-rose-400 text-xs">${escapeHtml(res?.error || 'خطا در دریافت تعرفه‌ها')}</div>`;
          return;
        }
        adminPlansData = res.plans || [];
        if (adminPlansData.length === 0) {
          container.innerHTML = `
            <div class="bg-slate-900/50 border border-slate-800 rounded-2xl p-6 text-center text-slate-400 space-y-3">
              <div class="w-10 h-10 rounded-2xl bg-blue-500/15 text-blue-400 flex items-center justify-center mx-auto">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>
              </div>
              <p class="text-xs">هیچ سرویس یا تعرفه‌ای هنوز ثبت نشده است.</p>
              <button onclick="window.adminActions.openPlanModal()" class="bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold px-4 py-2 rounded-xl transition shadow active:scale-95">
                + ایجاد اولین سرویس
              </button>
            </div>
          `;
          return;
        }

        container.innerHTML = adminPlansData.map(p => {
          const statusBadge = p.is_active
            ? '<span class="text-[10px] bg-emerald-500/10 t-success border border-emerald-500/30 px-2 py-0.5 rounded-lg font-bold">فعال</span>'
            : '<span class="text-[10px] bg-slate-500/10 t-muted border border-slate-400/30 px-2 py-0.5 rounded-lg font-medium">غیرفعال</span>';

          const trafficHtml = p.traffic_gb > 0
            ? fmtTraffic(p.traffic_gb, { html: true })
            : '<span class="text-cyan-300 font-bold">نامحدود</span>';
          const durationText = p.duration_days > 0 ? `${p.duration_days} روز` : 'نامحدود';
          const hwidText = p.hwid_limit > 0 ? `${p.hwid_limit} کاربر` : 'پیش‌فرض';

          const rawName = (p.name || '').trim();
          const emojiRegex = /([\uD800-\uDBFF][\uDC00-\uDFFF]|[\u2600-\u27BF]|\p{Extended_Pictographic}|\p{Emoji_Presentation})/u;
          const emojiMatch = rawName.match(emojiRegex);
          const pkgIcon = emojiMatch ? emojiMatch[0] : '';
          const cleanName = pkgIcon ? rawName.replace(emojiRegex, '').trim() : rawName;

          const bKey = (p.badge || '').toLowerCase();
          const isExtraTraffic = (bKey === 'traffic' || (Number(p.duration_days) === 0 && Number(p.traffic_gb) > 0)) && bKey !== 'time';
          const isExtraTime = !isExtraTraffic && (bKey === 'time' || (Number(p.traffic_gb) === 0 && Number(p.duration_days) > 0 && bKey !== 'traffic'));
          let typeBadge = '<span class="text-[10px] bg-blue-500/15 t-info border border-blue-500/30 px-2 py-0.5 rounded-lg font-bold">💎 دوره کامل</span>';
          if (isExtraTraffic) {
            typeBadge = '<span class="text-[10px] bg-cyan-500/15 t-accent border border-cyan-500/30 px-2 py-0.5 rounded-lg font-bold">⚡️ بسته حجمی</span>';
          } else if (isExtraTime) {
            typeBadge = '<span class="text-[10px] bg-amber-500/15 t-warn border border-amber-500/30 px-2 py-0.5 rounded-lg font-bold">⏳ بسته زمانی</span>';
          }

          let tagBadge = '';
          if (bKey === 'bestseller') {
            tagBadge = '<span class="badge-bestseller text-[10px] bg-amber-500/15 t-warn border border-amber-500/30 px-1.5 py-0.5 rounded-lg font-bold">🔥 پرفروش‌ترین</span>';
          } else if (bKey === 'popular') {
            tagBadge = '<span class="text-[10px] bg-purple-500/15 t-purple border border-purple-500/30 px-1.5 py-0.5 rounded-lg font-bold">⭐️ پرطرفدار</span>';
          } else if (bKey === 'economic') {
            tagBadge = '<span class="text-[10px] bg-emerald-500/15 t-success border border-emerald-500/30 px-1.5 py-0.5 rounded-lg font-bold">💰 اقتصادی</span>';
          } else if (bKey === 'vip') {
            tagBadge = '<span class="badge-vip text-[10px] bg-rose-500/15 t-danger border border-rose-500/30 px-1.5 py-0.5 rounded-lg font-bold">👑 پیشنهاد ویژه</span>';
          }
          if (p.max_purchases) {
            const pCount = p.purchases_count || 0;
            tagBadge += ` <span class="text-[9.5px] bg-amber-500/15 text-amber-500 dark:text-amber-400 border border-amber-500/30 px-1.5 py-0.5 rounded-lg font-bold font-mono">سقف: ${pCount}/${p.max_purchases}</span>`;
          }

          let specsHtml = '';
          if (isExtraTraffic) {
            specsHtml = `
              <div class="grid grid-cols-1 text-center text-[10px] bg-slate-900/60 p-2 rounded-xl font-mono">
                <div>
                  <span class="text-slate-400 block text-[10px] font-sans">حجم اضافه</span>
                  ${trafficHtml}
                </div>
              </div>
            `;
          } else if (isExtraTime) {
            specsHtml = `
              <div class="grid grid-cols-1 text-center text-[10px] bg-slate-900/60 p-2 rounded-xl font-mono">
                <div>
                  <span class="text-slate-400 block text-[10px] font-sans">مدت زمان اضافه</span>
                  <b class="text-amber-300">${durationText}</b>
                </div>
              </div>
            `;
          } else {
            specsHtml = `
              <div class="grid grid-cols-3 gap-1.5 text-center text-[10px] bg-slate-900/60 p-2 rounded-xl font-mono">
                <div>
                  <span class="text-slate-400 block text-[10px] font-sans">حجم ترافیک</span>
                  ${trafficHtml}
                </div>
                <div>
                  <span class="text-slate-400 block text-[10px] font-sans">مدت زمان</span>
                  <b class="text-amber-300">${durationText}</b>
                </div>
                <div>
                  <span class="text-slate-400 block text-[10px] font-sans">محدودیت HWID</span>
                  <b class="text-purple-300">${hwidText}</b>
                </div>
              </div>
            `;
          }

          const descHtml = (!isExtraTraffic && !isExtraTime && p.description)
            ? `<p class="text-[11px] text-slate-400 line-clamp-1 pr-9">${escapeHtml(p.description)}</p>`
            : '';

          const planCategory = isExtraTraffic ? 'traffic' : (isExtraTime ? 'time' : 'full');
          return `
            <div data-plan-type="${planCategory}" class="plan-card admin-plan-card bg-slate-800/80 rounded-2xl p-4 border border-slate-700/80 space-y-3 shadow transition">
              <div class="space-y-1.5">
                <!-- Top Row: Name + statusBadge on Right, Price and تومان on Left (همراستا و چسبیده) -->
                <div class="flex items-center justify-between gap-2">
                  <div class="flex items-center gap-1.5 min-w-0">
                    <span class="w-7 h-7 rounded-xl bg-transparent text-blue-400 border border-blue-500/30 flex items-center justify-center flex-shrink-0" title="بسته">
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>
                    </span>
                    <b class="t-main text-xs font-bold truncate">${escapeHtml(cleanName)}</b>
                    ${pkgIcon ? `<span class="text-sm select-none leading-none flex-shrink-0" title="آیکون بسته">${pkgIcon}</span>` : ''}
                    <div class="flex-shrink-0">${statusBadge}</div>
                  </div>
                  <div class="flex flex-col items-center justify-center flex-shrink-0 text-center leading-tight min-w-[45px]">
                    <span class="text-sm font-black text-emerald-500 dark:text-emerald-400 font-mono num-bidi" dir="ltr">${formatNumber(p.price || 0)}</span>
                    <span class="text-[9px] font-sans font-medium text-slate-400 -mt-0.5">تومان</span>
                  </div>
                </div>

                <!-- Bottom Row: Badges on Right -->
                <div class="flex items-center gap-1.5 flex-wrap pt-0.5">
                  ${typeBadge}
                  ${tagBadge}
                </div>
              </div>

              ${descHtml}
              ${specsHtml}

              <!-- 3 Icon-Only Action Buttons: Edit, Toggle Active, Delete -->
              <div class="flex gap-2 pt-1">
                <button onclick="window.adminActions.openPlanModal(${p.id})" class="flex-1 bg-transparent hover:bg-blue-500/10 t-info border border-blue-500/30 hover:border-blue-400/60 py-2 rounded-xl transition flex items-center justify-center active:scale-95" title="ویرایش بسته" aria-label="ویرایش بسته">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
                </button>
                <button onclick="window.adminActions.togglePlan(${p.id}, ${p.is_active})" class="flex-1 bg-transparent hover:bg-slate-500/10 ${p.is_active ? 't-warn border border-amber-500/30 hover:border-amber-400/60' : 't-success border border-emerald-500/30 hover:border-emerald-400/60'} py-2 rounded-xl transition flex items-center justify-center active:scale-95" title="${p.is_active ? 'غیرفعال‌سازی بسته' : 'فعال‌سازی بسته'}" aria-label="${p.is_active ? 'غیرفعال‌سازی بسته' : 'فعال‌سازی بسته'}">
                  ${p.is_active
                    ? '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>'
                    : '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>'}
                </button>
                <button type="button" data-id="${p.id}" data-name="${escapeHtml(p.name)}" class="btn-delete-plan flex-1 bg-transparent hover:bg-rose-500/10 t-danger border border-rose-500/30 hover:border-rose-400/60 py-2 rounded-xl transition flex items-center justify-center active:scale-95" title="حذف بسته" aria-label="حذف بسته">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                </button>
              </div>
            </div>
          `;
        }).join('');
        if (typeof this.filterPlans === 'function') {
          this.filterPlans(this.currentPlanFilter || 'all');
        }
      } catch (e) {
        container.innerHTML = '<div class="p-6 text-center text-rose-400 text-xs">خطای شبکه در دریافت تعرفه‌ها</div>';
      }
    },

    setPlanType(type = 'full') {
      window._currentAdminPlanType = type;
      const fullBtn = $('planTypeBtn-full');
      const trafBtn = $('planTypeBtn-traffic');
      const timeBtn = $('planTypeBtn-time');
      const notice = $('planTypeNotice');
      const trafInp = $('planModalTraffic');
      const durInp = $('planModalDuration');
      const badgeSel = $('planModalBadge');

      const activeClass = 'py-1.5 px-1 rounded-lg font-bold bg-blue-600 text-white transition flex items-center justify-center gap-1 shadow';
      const inactiveClass = 'py-1.5 px-1 rounded-lg font-medium text-slate-400 hover:text-white transition flex items-center justify-center gap-1';

      if (fullBtn) fullBtn.className = (type === 'full') ? activeClass : inactiveClass;
      if (trafBtn) trafBtn.className = (type === 'traffic') ? activeClass : inactiveClass;
      if (timeBtn) timeBtn.className = (type === 'time') ? activeClass : inactiveClass;

      const hwidBox = $('planModalHwidContainer');
      const descBox = $('planModalDescContainer');
      const durBox = $('planModalDurationContainer');
      const trafBox = $('planModalTrafficContainer');
      const priceMetricRow = $('planModalPriceMetricRow');
      const durationHwidRow = $('planModalDurationHwidRow');

      if (type === 'traffic') {
        if (durationHwidRow && durBox && hwidBox) durationHwidRow.insertBefore(durBox, hwidBox);
        if (durInp) {
          durInp.value = '0';
          durInp.disabled = true;
        }
        if (durBox) durBox.classList.add('hidden');
        if (hwidBox) hwidBox.classList.add('hidden');
        if (descBox) descBox.classList.add('hidden');
        if (durationHwidRow) durationHwidRow.classList.add('hidden');
        if (trafBox) trafBox.classList.remove('hidden');
        if (trafInp) {
          trafInp.disabled = false;
          trafInp.classList.remove('opacity-50', 'bg-slate-950');
          if (trafInp.value === '0') trafInp.value = '';
        }
        if (badgeSel && (!badgeSel.value || badgeSel.value === 'time')) badgeSel.value = 'traffic';
        if (notice) {
          notice.className = 'text-[10.5px] text-cyan-300 mt-1.5 p-1.5 rounded-lg bg-cyan-950/40 border border-cyan-500/40 leading-relaxed';
          notice.innerHTML = '⚡️ <b>بسته افزایش حجم:</b> تاریخ انقضای سرویس فعلی کاربر تغییر نمی‌کند و صرفاً به سقف ترافیک اکانت اضافه می‌شود.';
          notice.classList.remove('hidden');
        }
      } else if (type === 'time') {
        if (priceMetricRow && durBox) priceMetricRow.appendChild(durBox);
        if (trafInp) {
          trafInp.value = '0';
          trafInp.disabled = true;
        }
        if (trafBox) trafBox.classList.add('hidden');
        if (hwidBox) hwidBox.classList.add('hidden');
        if (descBox) descBox.classList.add('hidden');
        if (durationHwidRow) durationHwidRow.classList.add('hidden');
        if (durBox) durBox.classList.remove('hidden');
        if (durInp) {
          durInp.disabled = false;
          durInp.classList.remove('opacity-50', 'bg-slate-950');
          if (durInp.value === '0') durInp.value = '';
        }
        if (badgeSel && (!badgeSel.value || badgeSel.value === 'traffic')) badgeSel.value = 'time';
        if (notice) {
          notice.className = 'text-[10.5px] text-amber-300 mt-1.5 p-1.5 rounded-lg bg-amber-950/40 border border-amber-500/40 leading-relaxed';
          notice.innerHTML = '⏳ <b>بسته افزایش زمان:</b> ترافیک اکانت بدون تغییر مانده و صرفاً مدت زمان اعتبار سرویس افزایش می‌یابد.';
          notice.classList.remove('hidden');
        }
      } else {
        if (durationHwidRow && durBox && hwidBox) durationHwidRow.insertBefore(durBox, hwidBox);
        if (durBox) durBox.classList.remove('hidden');
        if (trafBox) trafBox.classList.remove('hidden');
        if (hwidBox) hwidBox.classList.remove('hidden');
        if (descBox) descBox.classList.remove('hidden');
        if (durationHwidRow) durationHwidRow.classList.remove('hidden');
        if (durInp) {
          durInp.disabled = false;
          durInp.classList.remove('opacity-50', 'bg-slate-950');
        }
        if (trafInp) {
          trafInp.disabled = false;
          trafInp.classList.remove('opacity-50', 'bg-slate-950');
        }
        if (badgeSel && (badgeSel.value === 'traffic' || badgeSel.value === 'time')) badgeSel.value = '';
        if (notice) {
          notice.className = 'text-[10.5px] text-blue-300 mt-1.5 p-1.5 rounded-lg bg-blue-950/40 border border-blue-500/40 leading-relaxed';
          notice.innerHTML = '💎 <b>سرویس دوره کامل:</b> بسته دارای حجم مشخص و مدت زمان معین است.';
          notice.classList.remove('hidden');
        }
      }
    },

    openPlanModal(planOrId = null) {
      let plan = planOrId;
      if (typeof planOrId === 'number') {
        plan = adminPlansData.find(p => p.id === planOrId) || null;
      }
      const modal = $('planModal');
      if (modal) modal.classList.remove('hidden');
      $('planModalTitle').innerText = plan ? `ویرایش تعرفه: ${plan.name}` : 'ایجاد تعرفه جدید';
      $('planModalId').value = plan ? plan.id : '';
      $('planModalName').value = plan ? plan.name : '';
      $('planModalPrice').value = plan ? plan.price : '';
      $('planModalTraffic').value = plan ? plan.traffic_gb : '';
      $('planModalDuration').value = plan ? plan.duration_days : '';
      $('planModalHwid').value = plan ? (plan.hwid_limit || '') : '';
      $('planModalDesc').value = plan ? (plan.description || '') : '';
      if ($('planModalBadge')) $('planModalBadge').value = plan ? (plan.badge || '') : '';
      if ($('planModalMaxPurchases')) $('planModalMaxPurchases').value = (plan && plan.max_purchases) ? plan.max_purchases : '';
      $('planModalActive').checked = plan ? !!plan.is_active : true;

      if (plan) {
        const isTraffic = (Number(plan.duration_days) === 0 && Number(plan.traffic_gb) > 0) || (plan.badge === 'traffic');
        const isTime = (Number(plan.traffic_gb) === 0 && Number(plan.duration_days) > 0) || (plan.badge === 'time');
        if (isTraffic) this.setPlanType('traffic');
        else if (isTime) this.setPlanType('time');
        else this.setPlanType('full');
      } else {
        this.setPlanType('full');
      }
    },

    closePlanModal() {
      $('planModal')?.classList.add('hidden');
    },

    async savePlan() {
      const id = $('planModalId')?.value;
      const name = $('planModalName')?.value?.trim();
      const price = parseInt($('planModalPrice')?.value || '0', 10);
      let traffic_gb = parseInt($('planModalTraffic')?.value || '0', 10);
      let duration_days = parseInt($('planModalDuration')?.value || '0', 10);
      if (window._currentAdminPlanType === 'traffic') {
        duration_days = 0;
      } else if (window._currentAdminPlanType === 'time') {
        traffic_gb = 0;
      }
      const hwid_limit = parseInt($('planModalHwid')?.value || '0', 10) || null;
      const description = $('planModalDesc')?.value?.trim();
      const badge = $('planModalBadge')?.value || (window._currentAdminPlanType === 'traffic' ? 'traffic' : (window._currentAdminPlanType === 'time' ? 'time' : ''));
      const is_active = $('planModalActive')?.checked ?? true;
      const max_purchases = parseInt($('planModalMaxPurchases')?.value || '0', 10) || null;

      if (!name) {
        if (window.showToast) window.showToast('نام تعرفه الزامی است.');
        return;
      }

      const saveBtn = $('planModalSaveBtn');
      if (saveBtn) { saveBtn.disabled = true; saveBtn.innerText = 'در حال ذخیره...'; }

      try {
        const payload = { id: id ? parseInt(id, 10) : undefined, name, price, traffic_gb, duration_days, hwid_limit, description, badge, is_active, max_purchases };
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
        if (saveBtn) { saveBtn.disabled = false; saveBtn.innerText = 'ذخیره سرویس'; }
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
      const container = $('adminCouponsList');
      if (!container) return;
      if (!adminCouponsData || adminCouponsData.length === 0) {
        container.innerHTML = '<div class="p-8 text-center text-xs text-slate-400">در حال دریافت کدهای تخفیف...</div>';
      }
      try {
        const res = await window.api.getAdminCoupons();
        if (!res || !res.ok) {
          container.innerHTML = `<div class="p-6 text-center text-rose-400 text-xs">${escapeHtml(res?.error || 'خطا در دریافت کدهای تخفیف')}</div>`;
          return;
        }
        adminCouponsData = (res.coupons || []).filter(c => {
          if (!c.expires_at) return true;
          try {
            return new Date(c.expires_at).getTime() > Date.now();
          } catch(e) {
            return true;
          }
        });
        if (adminCouponsData.length === 0) {
          container.innerHTML = `
            <div class="bg-slate-900/50 border border-slate-800 rounded-2xl p-6 text-center text-slate-400 space-y-3">
              <div class="w-10 h-10 rounded-2xl bg-pink-500/15 text-pink-400 flex items-center justify-center mx-auto">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z"/></svg>
              </div>
              <p class="text-xs">هیچ کد تخفیفی ایجاد نشده است.</p>
              <button onclick="window.adminActions.openCouponModal()" class="bg-transparent hover:bg-pink-500/15 border border-pink-500/50 text-pink-400 hover:text-pink-300 text-xs font-bold px-4 py-2 rounded-xl transition active:scale-95">
                + ایجاد اولین کد تخفیف
              </button>
            </div>
          `;
          return;
        }

        container.innerHTML = adminCouponsData.map(c => {
          const usedCount = c.used_count || 0;
          const statusBadge = c.is_active
            ? '<span class="text-[10px] bg-transparent t-success border border-emerald-500/30 px-2 py-0.5 rounded-lg font-bold">فعال</span>'
            : (usedCount > 0
                ? '<span class="text-[10px] bg-transparent t-muted border border-slate-400/30 px-2 py-0.5 rounded-lg font-medium">غیرفعال (مصرف‌شده)</span>'
                : '<span class="text-[10px] bg-transparent text-amber-500 dark:text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-lg font-medium">غیرفعال (استفاده‌نشده)</span>');

          const discountHtml = c.discount_percent > 0
            ? `<div class="flex items-baseline gap-1 mt-1 leading-tight"><span class="text-xs font-bold text-emerald-500 dark:text-emerald-400 font-mono num-bidi" dir="ltr">${toEnglishDigits(c.discount_percent)}%</span><span class="text-[9px] font-sans text-slate-400">تخفیف</span></div>`
            : `<div class="flex items-baseline gap-1 mt-1 leading-tight"><span class="text-xs font-bold text-emerald-500 dark:text-emerald-400 font-mono num-bidi" dir="ltr">${formatNumber(c.discount_amount || 0)}</span><span class="text-[9px] font-sans text-slate-400">تومان</span></div>`;

          const maxText = c.max_uses > 0 ? `${toEnglishDigits(usedCount)} / ${toEnglishDigits(c.max_uses)}` : `${toEnglishDigits(usedCount)} (نامحدود)`;
          const expiryText = c.expires_at_jalali || (c.expires_at ? (window.formatDateToJalali ? window.formatDateToJalali(c.expires_at) : c.expires_at) : 'نامحدود (دائمی)');

          let remainingDaysHtml = '<b class="text-slate-400 font-sans">نامحدود</b>';
          if (c.expires_at) {
            const diffMs = new Date(c.expires_at).getTime() - Date.now();
            const daysLeft = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
            if (daysLeft > 0) {
              remainingDaysHtml = `<b class="text-amber-400 font-bold">${toEnglishDigits(daysLeft)} روز</b>`;
            } else {
              remainingDaysHtml = '<b class="text-rose-400 font-bold">منقضی</b>';
            }
          }

          const usagesBtnHtml = usedCount > 0
            ? `<button type="button" data-id="${c.id}" data-code="${escapeHtml(c.code)}" class="btn-coupon-usages flex-1 bg-transparent hover:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/30 hover:border-indigo-400/60 py-2 rounded-xl transition flex items-center justify-center active:scale-95 shadow-sm" title="استفاده‌کنندگان (${formatNumber(usedCount)})" aria-label="استفاده‌کنندگان (${formatNumber(usedCount)})">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
              </button>`
            : `<div class="flex-1 bg-transparent text-slate-500 border border-slate-700/40 py-2 rounded-xl flex items-center justify-center opacity-40 cursor-not-allowed select-none" title="فاقد استفاده">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
              </div>`;

          const toggleBtnHtml = `<button onclick="window.adminActions.toggleCoupon(${c.id}, ${c.is_active})" class="flex-1 bg-transparent hover:bg-slate-500/10 ${c.is_active ? 't-warn border border-amber-500/30 hover:border-amber-400/60' : 't-success border border-emerald-500/30 hover:border-emerald-400/60'} py-2 rounded-xl transition flex items-center justify-center active:scale-95 shadow-sm" title="${c.is_active ? 'غیرفعال‌سازی کد تخفیف' : 'فعال‌سازی کد تخفیف'}" aria-label="${c.is_active ? 'غیرفعال‌سازی کد تخفیف' : 'فعال‌سازی کد تخفیف'}">
            ${c.is_active
              ? '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>'
              : '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>'}
          </button>`;

          const deleteBtnHtml = `<button type="button" data-id="${c.id}" data-code="${escapeHtml(c.code)}" class="btn-delete-coupon flex-1 bg-transparent hover:bg-rose-500/10 t-danger border border-rose-500/30 hover:border-rose-400/60 py-2 rounded-xl transition flex items-center justify-center active:scale-95 shadow-sm" title="حذف کد تخفیف" aria-label="حذف کد تخفیف">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
          </button>`;

          return `
            <div class="coupon-card bg-slate-800/80 rounded-2xl p-4 border border-slate-700/80 space-y-3 shadow transition">
              <div class="flex items-start justify-between">
                <div>
                  <div class="flex items-center gap-2">
                    <button type="button" data-code="${escapeHtml(c.code)}" class="btn-quick-copy-coupon flex items-center gap-1.5 cursor-pointer bg-transparent hover:text-indigo-300 text-indigo-400 border-0 p-0 transition active:scale-95 group" title="کلیک جهت کپی کد تخفیف">
                      <span class="font-mono font-bold text-sm tracking-wider uppercase">${escapeHtml(c.code)}</span>
                      <svg class="w-3.5 h-3.5 text-indigo-400/70 group-hover:text-indigo-300 transition" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
                    </button>
                    ${statusBadge}
                  </div>
                  <span class="text-[11px] t-success font-bold block mt-1.5">${discountHtml}</span>
                </div>
              </div>

              <div class="grid grid-cols-3 gap-1.5 text-center text-[10px] bg-slate-900/60 p-2 rounded-xl font-mono">
                <div>
                  <span class="text-slate-400 block text-[10px] font-sans">دفعات استفاده:</span>
                  <b class="text-slate-200">${maxText}</b>
                </div>
                <div>
                  <span class="text-slate-400 block text-[10px] font-sans">تاریخ انقضا:</span>
                  <b class="text-slate-200 truncate block">${escapeHtml(expiryText)}</b>
                </div>
                <div>
                  <span class="text-slate-400 block text-[10px] font-sans">مهلت باقی‌مانده:</span>
                  ${remainingDaysHtml}
                </div>
              </div>

              <div class="flex gap-2 pt-1 text-[11px]">
                ${usagesBtnHtml}
                ${toggleBtnHtml}
                ${deleteBtnHtml}
              </div>
            </div>
          `;
        }).join('');
      } catch (e) {
        container.innerHTML = '<div class="p-6 text-center text-rose-400 text-xs">خطای شبکه در دریافت کدهای تخفیف</div>';
      }
    },

    openCouponModal() {
      $('couponModal')?.classList.remove('hidden');
      $('couponModalCode').value = '';
      $('couponModalPercent').value = '20';
      $('couponModalAmount').value = '0';
      $('couponModalMaxUses').value = '0';
      $('couponModalDays').value = '30';
    },

    closeCouponModal() {
      $('couponModal')?.classList.add('hidden');
    },

    openBatchVoucherModal() {
      $('batchVoucherResultsBox')?.classList.add('hidden');
      $('batchVoucherModal')?.classList.remove('hidden');
    },

    closeBatchVoucherModal() {
      $('batchVoucherModal')?.classList.add('hidden');
    },

    async generateBatchVouchers() {
      const amount = parseInt($('batchVoucherAmount')?.value || '0', 10);
      const count = parseInt($('batchVoucherCount')?.value || '10', 10);
      const prefix = $('batchVoucherPrefix')?.value?.trim() || 'GIFT-';
      const max_uses = parseInt($('batchVoucherMaxUses')?.value || '1', 10);
      const expire_days = parseInt($('batchVoucherExpireDays')?.value || '30', 10);

      if (amount <= 0) {
        if (window.showToast) window.showToast('مبلغ هر کارت شارژ باید بیشتر از صفر باشد.');
        return;
      }

      const btn = $('batchVoucherGenerateBtn');
      if (btn) { btn.disabled = true; btn.innerText = 'در حال تولید...'; }

      try {
        const res = await window.api.batchGenerateVouchers({
          amount,
          count,
          prefix,
          max_uses,
          expire_days,
        });
        if (res && res.ok) {
          if (window.showToast) window.showToast(`✅ ${res.message}`);
          if (window.hapticFeedback) window.hapticFeedback('success');
          const resultsBox = $('batchVoucherResultsBox');
          const codeArea = $('batchVoucherGeneratedCodes');
          if (resultsBox && codeArea) {
            codeArea.value = (res.codes || []).join('\n');
            resultsBox.classList.remove('hidden');
          }
          this.fetchAdminCoupons();
        } else {
          if (window.showToast) window.showToast(`⚠️ ${res?.error || 'خطا در تولید کارت شارژ'}`);
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطای شبکه در تولید کارت‌های شارژ');
      } finally {
        if (btn) { btn.disabled = false; btn.innerText = 'تولید و ثبت'; }
      }
    },

    copyBatchCodes() {
      const codeArea = $('batchVoucherGeneratedCodes');
      if (codeArea && codeArea.value) {
        if (typeof copyToClipboard === 'function') {
          copyToClipboard(codeArea.value, '📋 تمام کدها در کلیپ‌بورد کپی شدند.');
        } else if (window.copyToClipboard) {
          window.copyToClipboard(codeArea.value, '📋 تمام کدها در کلیپ‌بورد کپی شدند.');
        }
      }
    },

    async saveCoupon() {
      const code = $('couponModalCode')?.value?.trim();
      const discount_percent = parseInt($('couponModalPercent')?.value || '0', 10);
      const discount_amount = parseInt($('couponModalAmount')?.value || '0', 10);
      const max_uses = parseInt($('couponModalMaxUses')?.value || '0', 10);
      const expires_days = parseInt($('couponModalDays')?.value || '0', 10);

      if (!code) {
        if (window.showToast) window.showToast('کد تخفیف الزامی است.');
        return;
      }

      const saveBtn = $('couponModalSaveBtn');
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

    openDeleteCouponModal(id, code) {
      this._pendingDeleteCouponId = id;
      const el = $('deleteCouponModalCode');
      if (el) el.innerText = code || '';
      const modal = $('deleteCouponModal');
      if (modal) modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('selection');
    },

    closeDeleteCouponModal() {
      const modal = $('deleteCouponModal');
      if (modal) modal.classList.add('hidden');
      this._pendingDeleteCouponId = null;
    },

    async executeDeleteCoupon() {
      const id = this._pendingDeleteCouponId;
      if (!id) return;
      const btn = $('confirmDeleteCouponBtn');
      if (btn) btn.disabled = true;
      try {
        const res = await window.api.deleteAdminCoupon(id);
        if (res && res.ok) {
          if (window.showToast) window.showToast('✅ کد تخفیف با موفقیت حذف شد.');
          this.closeDeleteCouponModal();
          this.fetchAdminCoupons();
          if (window.hapticFeedback) window.hapticFeedback('success');
        } else {
          if (window.showToast) window.showToast(res?.error || 'خطا در حذف کد تخفیف');
        }
      } catch (e) {
        if (window.showToast) window.showToast('خطا در برقراری ارتباط با سرور');
      } finally {
        if (btn) btn.disabled = false;
      }
    },

    deleteCoupon(id, code) {
      this.openDeleteCouponModal(id, code);
    },

    async openCouponUsages(coupon_id, code) {
      const modal = $('couponUsagesModal');
      const subtitle = $('couponUsagesModalSubtitle');
      const list = $('couponUsagesList');
      const countStat = $('couponUsagesCountStat');
      const totalDiscStat = $('couponUsagesTotalDiscountStat');

      if (modal) modal.classList.remove('hidden');
      if (subtitle) subtitle.innerText = `کد تخفیف: ${code}`;
      if (countStat) countStat.innerText = '0 بار';
      if (totalDiscStat) totalDiscStat.innerText = '0 تومان';
      if (list) list.innerHTML = '<div class="p-6 text-center text-xs text-slate-400">در حال دریافت لیست استفاده‌کنندگان...</div>';
      if (window.hapticFeedback) window.hapticFeedback('impact');

      try {
        const res = await window.api.getAdminCouponUsages(coupon_id);
        if (!res || !res.ok) {
          if (list) list.innerHTML = `<div class="p-6 text-center text-xs text-rose-400">${escapeHtml(res?.error || 'خطا در دریافت لیست')}</div>`;
          return;
        }

        const usages = res.usages || [];
        const totalDiscountGranted = usages.reduce((sum, u) => sum + (Number(u.discount_applied) || 0), 0);

        if (subtitle) {
          subtitle.innerText = `کد: ${res.coupon?.code || code} | تعداد کل استفاده: ${formatNumber(usages.length)} بار`;
        }
        if (countStat) countStat.innerText = `${formatNumber(usages.length)} بار`;
        if (totalDiscStat) totalDiscStat.innerText = `${formatNumber(totalDiscountGranted)} تومان`;

        if (usages.length === 0) {
          list.innerHTML = `
            <div class="bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 text-center t-muted space-y-2">
              <div class="w-12 h-12 rounded-2xl bg-pink-500/15 text-pink-500 dark:text-pink-400 flex items-center justify-center mx-auto shadow-sm">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z"/></svg>
              </div>
              <b class="text-xs text-slate-800 dark:text-slate-300 block">بدون استفاده</b>
              <p class="text-[11px] t-muted">هیچ کاربری هنوز از این کد تخفیف استفاده نکرده است.</p>
            </div>
          `;
          return;
        }

        list.innerHTML = usages.map(u => {
          const hasUsername = Boolean(u.username);
          const displayName = u.full_name || (hasUsername ? `@${u.username}` : `کاربر ${u.telegram_id}`);
          const initial = (displayName.replace('@', '')[0] || 'U').toUpperCase();
          const avatarSrc = u.avatar_url || `/api/user/avatar?user_id=${u.telegram_id}`;
          const dateStr = u.created_at ? new Date(u.created_at).toLocaleDateString('fa-IR', { numberingSystem: 'latn', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }) : '—';
          const discountStr = u.discount_applied > 0 ? `${formatNumber(u.discount_applied)} تومان` : 'اعمال‌شده';

          return `
            <div class="coupon-usage-card bg-white dark:bg-slate-900/60 rounded-2xl p-3 border border-slate-200 dark:border-slate-700/60 space-y-2.5 shadow-sm hover:border-pink-500/40 transition">
              <!-- Top Row: Order on right, Date on top-left -->
              <div class="flex items-center justify-between border-b border-slate-200 dark:border-slate-800/80 pb-2">
                <div class="flex items-center gap-1.5 min-w-0">
                  ${u.order_id ? `<span class="text-[11px] font-mono t-accent font-medium">سفارش ${u.order_id}</span>` : `<span class="text-[11px] t-muted">ثبت تخفیف</span>`}
                </div>
                <div class="text-[10px] t-muted font-mono flex items-center gap-1" dir="ltr">
                  <svg class="w-3 h-3 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  <span>${dateStr}</span>
                </div>
              </div>

              <!-- Main Content: Name, Avatar & Price on right, Username & ID on top-left -->
              <div class="flex items-center justify-between gap-3">
                <div class="flex items-center gap-2.5 min-w-0">
                  <div class="w-10 h-10 rounded-full bg-gradient-to-tr from-pink-600 to-purple-600 text-white font-bold text-xs flex items-center justify-center flex-shrink-0 shadow-sm overflow-hidden relative">
                    <img src="${avatarSrc}" alt="Avatar" class="w-full h-full object-cover" onerror="this.classList.add('hidden'); if(this.nextElementSibling) this.nextElementSibling.classList.remove('hidden');" />
                    <span class="font-bold">${initial}</span>
                  </div>
                  <div class="min-w-0 space-y-0.5">
                    <b class="t-main text-xs font-bold block truncate max-w-[130px] sm:max-w-[160px] cursor-pointer hover:text-pink-400" data-copy="${escapeHtml(displayName)}" onclick="window.adminActions.quickCopy(this.dataset.copy, 'نام کاربر')" title="${escapeHtml(displayName)}">${escapeHtml(displayName)}</b>
                    <div class="flex items-baseline gap-1 t-success font-bold" dir="rtl">
                      <span class="text-xs font-black font-mono leading-none">${formatNumber(u.discount_applied || 0)}</span>
                      <span class="text-[10px] text-emerald-600/90 dark:text-emerald-500/90 font-sans">تومان</span>
                    </div>
                  </div>
                </div>

                <!-- Left column: Username on line 1, Numeric ID on line 2 (سمت چپ‌ترین نقطه، بالا و بدون ID:) -->
                <div class="flex flex-col items-start justify-center gap-0.5 font-mono text-[11px] t-muted flex-shrink-0 text-left" dir="ltr">
                  ${hasUsername ? `
                    <div class="text-[11px] text-pink-500 dark:text-pink-400 font-mono cursor-pointer hover:underline truncate max-w-[130px] leading-tight" onclick="window.adminActions.quickCopy('@${escapeHtml(u.username)}', 'نام کاربری')" title="@${escapeHtml(u.username)}">
                      @${escapeHtml(u.username)}
                    </div>
                  ` : ''}
                  <div class="cursor-pointer hover:text-cyan-500 dark:hover:text-cyan-300 t-muted font-mono leading-tight" onclick="window.adminActions.quickCopy('${u.telegram_id}', 'شناسه عددی')" title="شناسه عددی">
                    ${u.telegram_id}
                  </div>
                </div>
              </div>
            </div>
          `;
        }).join('');
      } catch (err) {
        if (list) list.innerHTML = '<div class="p-6 text-center text-xs text-rose-400">خطای شبکه در دریافت لیست استفاده‌کنندگان</div>';
      }
    },

    closeCouponUsagesModal() {
      $('couponUsagesModal')?.classList.add('hidden');
    }
  });


  const fetchAdminPlans = () => window.adminActions.fetchAdminPlans();
  const fetchAdminCoupons = () => window.adminActions.fetchAdminCoupons();

  $('openCreatePlanBtn')?.addEventListener('click', () => {
    window.adminActions.openPlanModal();
  });
  $('openCreateCouponBtn')?.addEventListener('click', () => {
    window.adminActions.openCouponModal();
  });


  // Global exports
  window.fetchAdminPlans = fetchAdminPlans;
  window.fetchAdminCoupons = fetchAdminCoupons;
})(window);
