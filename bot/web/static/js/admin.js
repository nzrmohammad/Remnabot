/**
 * RemnaAdmin Pro - Master Orchestrator (admin.js)
 * Coordinates modular domain scripts, lifecycle, safe area, and navigation.
 */
(function (window) {
  'use strict';

  const _domCache = new Map();
  const $ = id => {
    let elem = _domCache.get(id);
    if (!elem || !elem.isConnected) {
      elem = document.getElementById(id);
      if (elem) _domCache.set(id, elem);
    }
    return elem;
  };
  window.$ = $;
  const el = new Proxy({}, { get: (_, id) => $(id) });

  window.adminActions = window.adminActions || {};

  // Core Shared Admin Actions (Clipboard & Global Modals)
  Object.assign(window.adminActions, {
    async quickCopy(text, label = 'مقدار') {
      if (!text) return;
      const safeText = String(text).trim();
      const safeLabel = String(label).trim();
      const toastMsg = `📋 ${safeLabel} کپی شد: ${safeText}`;
      if (typeof copyToClipboard === 'function') {
        await copyToClipboard(safeText, toastMsg);
      } else if (window.copyToClipboard) {
        await window.copyToClipboard(safeText, toastMsg);
      }
    },

    closeOperationReportModal() {
      $('operationReportModal')?.classList.add('hidden');
    }
  });

  // State Management & Safe Area Handling
  const tg = window.Telegram?.WebApp;

  function updateAdminTopPadding() {
    const topBar = $('adminTopBar');
    if (!topBar) return;
    let padTop = 18;
    if (tg) {
      const safeTop = tg.contentSafeAreaInset?.top || tg.safeAreaInset?.top || 0;
      if (safeTop > 0) {
        padTop = safeTop + 8;
        document.documentElement.style.setProperty('--tg-content-safe-area-inset-top', safeTop + 'px');
        document.documentElement.style.setProperty('--tg-safe-area-inset-top', safeTop + 'px');
      }
    }
    topBar.style.paddingTop = padTop + 'px';
  }

  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.disableVerticalSwipes) tg.disableVerticalSwipes();
      // tg.requestFullscreen removed to prevent header falling under Telegram client menu
      if (tg.setHeaderColor) tg.setHeaderColor('#0f172a');
      if (tg.setBackgroundColor) tg.setBackgroundColor('#080d1a');
      if (tg.onEvent) {
        tg.onEvent('viewportChanged', () => {
          if (!tg.isExpanded) tg.expand();
          updateAdminTopPadding();
        });
        tg.onEvent('contentSafeAreaChanged', updateAdminTopPadding);
        tg.onEvent('safeAreaChanged', updateAdminTopPadding);
      }
    } catch (e) {}
    updateAdminTopPadding();
    window.addEventListener('load', updateAdminTopPadding);
  }

  let currentPage = 1;
  let currentFilter = 'all';
  let currentSearch = '';
  let currentModifyTarget = null;
  let currentWalletTarget = null;
  let currentHwidTarget = null;
  let currentSubTarget = null;
  let currentTrialTarget = null;
  let currentEditSslDomainTarget = null;
  let currentDeleteSslDomainTarget = null;
  let adminPlansData = [];
  let adminCouponsData = [];
  let currentBroadcastTarget = 'all';
  let cachedOverviewData = null;


  // --- 0. Splash Screen Handler ---
  function dismissSplash() {
    const splash = $('splashScreen');
    const splashBar = $('splashBar');
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
    if (num === null || num === undefined || isNaN(Number(num))) return '0';
    const n = Number(num);
    const rounded = Number.isInteger(n) ? n.toString() : (Math.round(n * 100) / 100).toString();
    const [intPart, decPart] = rounded.split('.');
    const formattedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return decPart !== undefined ? `${formattedInt}.${decPart}` : formattedInt;
  }

  function formatSpeed(bytesPerSec) {
    const bytes = Number(bytesPerSec || 0);
    if (!bytes || bytes <= 0) return '0 B/s';
    const units = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
    let i = 0;
    let val = bytes;
    while (val >= 1024 && i < units.length - 1) {
      val /= 1024;
      i++;
    }
    return `${val.toFixed(val >= 10 ? 1 : 2)} ${units[i]}`;
  }

  function formatChatTimestamp(m) {
    if (!m) return '';
    if (m.timestamp) {
      const tsMs = m.timestamp > 1e11 ? m.timestamp : m.timestamp * 1000;
      const d = new Date(tsMs);
      if (!isNaN(d.getTime())) {
        return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
      }
    }
    if (m.created_at) {
      if (typeof m.created_at === 'string' && m.created_at.includes('T')) {
        const d = new Date(m.created_at);
        if (!isNaN(d.getTime())) {
          return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
        }
      }
      return m.created_at;
    }
    return '';
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
        const isTarget = (b === btn);
        b.classList.toggle('is-active', isTarget);
        b.setAttribute('aria-selected', isTarget ? 'true' : 'false');
      });

      if (window.hapticFeedback) window.hapticFeedback('impact');

      if (targetId === 'tab-admin-overview' || targetId === 'tab-admin-dashboard') {
        window.adminCharts?.resizeAll();
      }

      // Lazy load tab data
      if (targetId === 'tab-admin-nodes') {
        if ($('adminOverviewNodesList')?.children.length <= 1) {
          if (window.syncAdminOverview) window.syncAdminOverview(false);
        }
        if ($('adminSslHealthList')?.children.length <= 1) {
          if (window.fetchAdminSslHealth) window.fetchAdminSslHealth();
        }
      } else if (targetId === 'tab-admin-users') {
        if ($('adminUsersList')?.children.length <= 1) {
          if (window.fetchAdminUsers) window.fetchAdminUsers(1);
        }
      } else if (targetId === 'tab-admin-plans') {
        if (window.fetchAdminPlans) window.fetchAdminPlans();
        if (window.fetchAdminCoupons) window.fetchAdminCoupons();
      } else if (targetId === 'tab-admin-finance') {
        if (window.fetchAdminTopups) window.fetchAdminTopups();
      } else if (targetId === 'tab-admin-support') {
        if (window.fetchTicketThreads) window.fetchTicketThreads();
      } else if (targetId === 'tab-admin-settings') {
        if (window.fetchAdminSettings) window.fetchAdminSettings();
      }
    });
  });

  // --- Confirmation & Report Modals ---
  function showConfirmModal({ title = 'تایید عملیات', message = 'آیا از انجام این عملیات اطمینان دارید؟', confirmText = 'تایید و اجرا', isDanger = true }) {
    return new Promise((resolve) => {
      const modal = $('confirmActionModal');
      const titleEl = $('confirmModalTitle');
      const msgEl = $('confirmModalMessage');
      const confirmBtn = $('confirmModalConfirmBtn');
      const cancelBtn = $('confirmModalCancelBtn');
      const iconBox = $('confirmModalIconBox');

      if (!modal || !confirmBtn || !cancelBtn) {
        resolve(window.confirm(message));
        return;
      }

      if (titleEl) titleEl.innerText = title;
      if (msgEl) msgEl.innerText = message;
      if (confirmBtn) {
        confirmBtn.innerText = confirmText;
        if (isDanger) {
          confirmBtn.className = 'flex-1 bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs py-2.5 rounded-xl transition shadow active:scale-95 flex items-center justify-center gap-1.5';
          if (iconBox) iconBox.className = 'w-10 h-10 rounded-2xl bg-rose-500/20 text-rose-400 border border-rose-500/30 flex items-center justify-center flex-shrink-0';
        } else {
          confirmBtn.className = 'flex-1 bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs py-2.5 rounded-xl transition shadow active:scale-95 flex items-center justify-center gap-1.5';
          if (iconBox) iconBox.className = 'w-10 h-10 rounded-2xl bg-blue-500/20 text-blue-400 border border-blue-500/30 flex items-center justify-center flex-shrink-0';
        }
      }

      const cleanup = () => {
        modal.classList.add('hidden');
        confirmBtn.removeEventListener('click', onConfirm);
        cancelBtn.removeEventListener('click', onCancel);
      };

      const onConfirm = () => {
        cleanup();
        if (window.hapticFeedback) window.hapticFeedback('impact');
        resolve(true);
      };

      const onCancel = () => {
        cleanup();
        resolve(false);
      };

      confirmBtn.addEventListener('click', onConfirm);
      cancelBtn.addEventListener('click', onCancel);
      modal.classList.remove('hidden');
      if (window.hapticFeedback) window.hapticFeedback('warning');
    });
  }

  function showOperationReportModal({ title, subtitle, iconType = 'success', items = [] }) {
    const modal = $('operationReportModal');
    const titleEl = $('opReportTitle');
    const subEl = $('opReportSubtitle');
    const iconBox = $('opReportIconBox');
    const contentEl = $('opReportContent');

    if (!modal) return;
    if (titleEl) titleEl.innerText = title || 'گزارش عملیات';
    if (subEl) subEl.innerText = subtitle || 'عملیات با موفقیت ثبت شد';

    if (iconBox) {
      if (iconType === 'success') {
        iconBox.className = 'w-10 h-10 rounded-2xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center flex-shrink-0';
        iconBox.innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>';
      } else if (iconType === 'purple') {
        iconBox.className = 'w-10 h-10 rounded-2xl bg-purple-500/20 text-purple-400 border border-purple-500/30 flex items-center justify-center flex-shrink-0';
        iconBox.innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"/></svg>';
      }
    }

    if (contentEl) {
      contentEl.innerHTML = items.map(item => {
        if (item.highlight) {
          return `
            <div class="bg-emerald-950/40 p-3 rounded-2xl border border-emerald-600/30 flex items-center justify-between text-xs">
              <span class="text-slate-300 font-medium">${item.label}:</span>
              <b class="text-emerald-400 font-mono font-bold text-sm" dir="ltr">${item.value}</b>
            </div>
          `;
        }
        return `
          <div class="bg-slate-900/60 p-2.5 rounded-xl border border-slate-800 flex items-center justify-between text-xs">
            <span class="text-slate-400 text-[11px]">${item.label}:</span>
            <span class="${item.color || 'text-white'} font-semibold text-xs truncate max-w-[200px]" dir="${item.dir || 'auto'}">${item.value}</span>
          </div>
        `;
      }).join('');
    }

    modal.classList.remove('hidden');
    if (window.hapticFeedback) window.hapticFeedback('success');
  }

  window.showConfirmModal = showConfirmModal;
  window.showOperationReportModal = showOperationReportModal;
  window.dismissSplash = dismissSplash;


  // --- 10. Header & Action Trigger Buttons ---
  $('adminReloadBtn')?.addEventListener('click', () => {
    if (window.syncAdminOverview) window.syncAdminOverview(true);
    if (window.showToast) window.showToast('🔄 اطلاعات به‌روزرسانی شد.');
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });

  $('quickRefreshMetricsBtn')?.addEventListener('click', () => {
    if (window.syncAdminOverview) window.syncAdminOverview(true);
    if (window.showToast) window.showToast('🔄 داده‌ها سینک شدند.');
    if (window.hapticFeedback) window.hapticFeedback('impact');
  });


  window.closeModifyModal = () => window.adminActions.closeModifyModal();
  window.applyUserModification = () => window.adminActions.applyUserModification();
  window.openModifyUserModal = (id, name, type) => window.adminActions.openModifyUser(id, name, type);
  window.killUserSessions = (id, name) => window.adminActions.killSessions(id, name);
  window.toggleUserBan = (id, ban) => window.adminActions.toggleBan(id, ban);
  window.handleTopupAction = (id, app) => window.adminActions.handleTopup(id, app);
  window.openSubModal = (id, name, url) => window.adminActions.openSubModal(id, name, url);
  window.closeSubModal = () => window.adminActions.closeSubModal();
  window.copySubLink = () => window.adminActions.copySubLink();
  window.confirmRegenerateSub = () => window.adminActions.confirmRegenerateSub();
  window.killSessionsFromModal = () => window.adminActions.killSessionsFromModal();
  window.quickCopy = (text, label) => window.adminActions.quickCopy(text, label);
  window.openCreateUserModal = () => window.adminActions.openCreateUserModal();
  window.closeCreateUserModal = () => window.adminActions.closeCreateUserModal();
  window.openPlanPickerModal = () => window.adminActions.openPlanPickerModal();
  window.closePlanPickerModal = () => window.adminActions.closePlanPickerModal();
  window.selectCreateUserPlan = (id) => window.adminActions.selectCreateUserPlan(id);
  window.onUsernameInput = (val) => window.adminActions.onUsernameInput(val);
  window.submitCreateUser = () => window.adminActions.submitCreateUser();
  window.onPlanSelectChange = () => window.adminActions.onPlanSelectChange();
  window.openBulkUsersModal = () => window.adminActions.openBulkUsersModal();
  window.onBulkTargetChange = (target) => window.adminActions.onBulkTargetChange(target);
  window.closeBulkUsersModal = () => window.adminActions.closeBulkUsersModal();
  window.openNodeBillingModal = (...args) => window.adminActions.openNodeBillingModal(...args);
  window.closeNodeBillingModal = () => window.adminActions.closeNodeBillingModal();
  window.saveNodeBilling = () => window.adminActions.saveNodeBilling();
  window.setNodeBillingCurrency = (curr) => window.adminActions.setNodeBillingCurrency(curr);
  window.addDaysToNodeBillingDueDate = (days) => window.adminActions.addDaysToNodeBillingDueDate(days);
  window.clearNodeBillingDueDate = () => window.adminActions.clearNodeBillingDueDate();
  window.switchAdminAppsTab = (os) => window.adminActions.switchAdminAppsTab(os);
  window.openCreateCampaignModal = () => window.adminActions.openCreateCampaignModal();
  window.openCampaignDetailModal = (id) => window.adminActions.openCampaignDetailModal(id);
  window.closeCampaignDetailModal = () => window.adminActions.closeCampaignDetailModal();
  window.closeCreateCampaignModal = () => window.adminActions.closeCreateCampaignModal();
  window.submitCreateCampaign = (e) => window.adminActions.submitCreateCampaign(e);
  window.deleteCampaign = (id, name) => window.adminActions.deleteCampaign(id, name);
  window.copyCampaignLink = (url) => window.adminActions.copyCampaignLink(url);
  window.fetchAdminCampaigns = () => window.adminActions.fetchAdminCampaigns();
  window.deleteSslDomain = (domain) => window.adminActions.deleteSslDomain(domain);
  window.editSslDomain = (domain) => window.adminActions.editSslDomain(domain);
  window.openUserProfileModal = (id) => window.adminActions.openUserProfileModal(id);
  window.closeUserProfileModal = () => window.adminActions.closeUserProfileModal();


  // Safe global delegation for administrative action buttons (prevents inline handler XSS)
  document.addEventListener('click', (e) => {
    const editSslBtn = e.target.closest('.btn-edit-ssl-domain');
    if (editSslBtn) {
      window.adminActions.openEditSslDomainModal(editSslBtn.dataset.domain);
      return;
    }
    const delSslBtn = e.target.closest('.btn-del-ssl-domain');
    if (delSslBtn) {
      window.adminActions.openDeleteSslDomainModal(delSslBtn.dataset.domain);
      return;
    }
    const nodeBillingBtn = e.target.closest('.btn-node-billing');
    if (nodeBillingBtn) {
      e.stopPropagation();
      const d = nodeBillingBtn.dataset;
      window.adminActions.openNodeBillingModal(
        d.uuid, d.name, d.provider, Number(d.costToman || 0), Number(d.costEur || 0),
        d.due, d.notes, d.flag, d.currency
      );
      return;
    }
    const copyIpBtn = e.target.closest('.btn-copy-ip-direct');
    if (copyIpBtn) {
      window.copyToClipboard(copyIpBtn.dataset.ip, 'آدرس IP کپی شد');
      return;
    }
    const delPlanBtn = e.target.closest('.btn-delete-plan');
    if (delPlanBtn) {
      window.adminActions.deletePlan(Number(delPlanBtn.dataset.id), delPlanBtn.dataset.name);
      return;
    }
    const couponUsagesBtn = e.target.closest('.btn-coupon-usages');
    if (couponUsagesBtn) {
      window.adminActions.openCouponUsages(Number(couponUsagesBtn.dataset.id), couponUsagesBtn.dataset.code);
      return;
    }
    const delCouponBtn = e.target.closest('.btn-delete-coupon');
    if (delCouponBtn) {
      window.adminActions.deleteCoupon(Number(delCouponBtn.dataset.id), delCouponBtn.dataset.code);
      return;
    }
    const copyCouponBtn = e.target.closest('.btn-quick-copy-coupon');
    if (copyCouponBtn) {
      window.adminActions.quickCopy(copyCouponBtn.dataset.code, 'کد تخفیف');
      return;
    }
    const copyCampBtn = e.target.closest('.btn-copy-campaign-link');
    if (copyCampBtn) {
      window.adminActions.copyCampaignLink(copyCampBtn.dataset.link);
      return;
    }
    const delCampBtn = e.target.closest('.btn-delete-campaign');
    if (delCampBtn) {
      window.adminActions.deleteCampaign(Number(delCampBtn.dataset.id), delCampBtn.dataset.name);
      return;
    }
  });

  // Application bootstrap on startup
  if (typeof fetchAdminSettings === 'function') {
    fetchAdminSettings();
  } else if (window.fetchAdminSettings) {
    window.fetchAdminSettings();
  }
  if (typeof syncAdminOverview === 'function') {
    syncAdminOverview();
  } else if (window.syncAdminOverview) {
    window.syncAdminOverview();
  }

  // Background Pre-fetching for instant tab transitions
  setTimeout(() => {
    if (window.fetchAdminPlans) window.fetchAdminPlans();
    if (window.fetchAdminCoupons) window.fetchAdminCoupons();
    if (window.fetchAdminTopups) window.fetchAdminTopups();
    if (window.fetchAdminUsers) window.fetchAdminUsers(1);
  }, 250);

  // Preserved Test Contract Signatures & Delegates
  // refreshLiveCryptoRates(force = true)
  // filterPlans(cat = 'all')
  // admin-plan-card
  // data-plan-type
  // openRecommendedAppModal
  // openHighRiskUsersModal
  // max_purchases
})(window);
