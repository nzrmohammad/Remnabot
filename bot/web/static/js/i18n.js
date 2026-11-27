/**
 * RemnaStore Pro - Frontend Mini App i18n Runtime (Single Source of Truth)
 * Supports seamless live switching between Persian ('fa', RTL) and English ('en', LTR)
 * while preserving original Persian markup without duplication.
 */
(function (global) {
  'use strict';

  const SUPPORTED_LANGS = ['fa', 'en'];
  const DEFAULT_LANG = 'fa';
  const STORAGE_KEY = 'remna_user_lang';

  function normalizeAppLang(lang) {
    if (typeof lang !== 'string') return DEFAULT_LANG;
    const base = lang.trim().toLowerCase().replace(/_/g, '-').split('-')[0];
    return SUPPORTED_LANGS.includes(base) ? base : DEFAULT_LANG;
  }

  function getAppLanguage() {
    if (typeof window !== 'undefined') {
      if (window.__remnaAppLang && SUPPORTED_LANGS.includes(window.__remnaAppLang)) {
        return window.__remnaAppLang;
      }
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored && SUPPORTED_LANGS.includes(stored)) return stored;
      } catch (e) {}
    }
    if (typeof document !== 'undefined' && document.documentElement?.lang) {
      return normalizeAppLang(document.documentElement.lang);
    }
    return DEFAULT_LANG;
  }

  const I18N_EN = {
    // Bottom Navigation & Chrome
    nav_dashboard: 'Dashboard',
    nav_reports: 'Reports',
    nav_shop: 'Shop',
    nav_wallet: 'Wallet',
    nav_profile: 'Account',
    close_app: 'Close',

    // Splash & System Overlays
    splash_subtitle: 'Dedicated Subscription & Proxy Manager',
    splash_loading: 'Loading your account and sessions...',
    maint_title: 'Infrastructure Upgrade',
    maint_desc: 'To ensure maximum stability and speed, the platform is temporarily undergoing maintenance.',
    maint_pill: 'Back online shortly',
    maint_support: 'Contact Support',
    invite_title: 'Private — Invite Only',
    invite_desc: 'Registration requires an exclusive invitation link from an existing member.',
    join_gate_title: 'Channel Membership Required',
    join_gate_desc: 'Please join our official channel first to unlock purchases and account management.',
    join_gate_btn: 'Join Channel',
    join_gate_recheck: 'Verify Membership & Enter',
    join_gate_help: 'Need help? Contact Support',
    banned_title: 'Account Suspended',

    // Dashboard
    no_sub_pill: 'No Active Subscription',
    no_sub_desc: 'You do not have an active subscription yet. Pick a plan in the shop to get started.',
    chip_fast: 'High Speed',
    chip_antifilter: 'Anti-Censorship',
    chip_support: '24/7 Support',
    no_sub_cta: 'Browse & Buy Plans',
    total_traffic_label: 'Total Service Traffic',
    remaining_word: 'left',
    status_checking: 'Checking...',
    sub_link_label: 'Your Subscription Link',
    copy_btn: 'Copy',
    configs_btn: 'Get Configs',
    revoke_btn: 'Regenerate',
    qr_btn: 'QR Code',

    // Reports Subtabs
    rep_daily: 'Daily',
    rep_nightly: 'Nightly',
    rep_weekly: 'Weekly',
    rep_monthly: 'Monthly',
    rep_analytics: 'Analytics',

    // Profile & Settings
    app_lang_title: 'App Language',
    app_lang_desc: 'Default bot & dashboard language',
    lang_saved_fa: 'زبان به فارسی تغییر یافت.',
    lang_saved_en: 'Language changed to English.',
    lang_save_error: 'Failed to save language preference.',
    settings_saved: 'Settings saved.',
    settings_save_error: 'Failed to save settings.',
    network_error: 'Unable to connect to the server.',
    auto_renew_on: 'Auto-renew enabled.',
    auto_renew_off: 'Auto-renew disabled.',
    auto_renew_error: 'Failed to update auto-renew status.',
    traffic_alert_sub: 'Alert before quota ends ({percent}%)',
    expire_alert_sub: 'Notify {days} days before expiration',
    expire_days_badge: '{days} days',
    target_account_prefix: 'Target Account:',
    configs_empty_title: 'No configs found in Remnawave panel.',
    configs_loading: 'Fetching configs from panel...',
    retry_btn: 'Retry',
    currency_unit_toman: 'Toman',
    primary_unit_prefix: 'Primary unit:',
    cur_toman_name: 'Toman',
    cur_toman_full: 'Toman (IRT)',
    cur_ton_name: 'TON',
    cur_ton_full: 'Toncoin (TON)',
    cur_usdt_name: 'USDT',
    cur_usdt_full: 'Tether (USDT)',
    cur_trx_name: 'TRX',
    cur_trx_full: 'TRON (TRX)',
    cur_pol_name: 'POL',
    cur_pol_full: 'Polygon (POL / MATIC)',
    cur_stars_name: 'Stars',
    cur_stars_full: 'Telegram Stars',

    // Wallet & Topup
    card_auto_title: 'Instant Auto Card Transfer',
    card_auto_badge: 'Smart SMS Verification',
    card_auto_create: 'Create Instant Payment Invoice',
    card_auto_waiting: 'Waiting for bank transfer...',
    card_holder_label: 'Account Holder:',
    card_number_label: 'Destination Card Number:',

    // Loyalty Tiers
    loyalty_modal_title: 'Loyalty Levels & VIP Tiers',

    // Modals & Engagement
    revoke_title: 'Regenerate subscription link?',
    revoke_confirm_btn: 'Confirm & Regenerate',
    cancel_btn: 'Cancel',
    close_btn: 'Close',
    charge_wallet_btn: 'Top Up',
    send_gift_btn: 'Gift',
    transfer_wallet_btn: 'Transfer',
    weekly_quests_title: 'Weekly Quests',
    weekly_quests_subtitle: 'Complete quests to earn free Lucky Wheel spin tickets',
    transfer_modal_title: 'Direct Money Transfer',
    transfer_modal_subtitle: 'Instant P2P Toman transfer to another user',
    story_theme_title: 'Card & Story Visual Theme:',
    red_packet_tab: 'Red Packet',
  };

  // Automatic lookup for legacy Persian notifications / alerts when user switches UI to English
  const TOAST_FA_TO_EN = {
    'تنظیمات با موفقیت ذخیره شد.': 'Settings saved successfully.',
    'خطا در ذخیره تنظیمات': 'Failed to save settings.',
    'خطا در ذخیره تنظیمات زبان.': 'Failed to save language setting.',
    'خطا در برقراری ارتباط با سرور.': 'Server connection error.',
    'تمدید خودکار فعال شد.': 'Auto-renew enabled.',
    'تمدید خودکار غیرفعال شد.': 'Auto-renew disabled.',
    'خطا در تغییر وضعیت تمدید خودکار': 'Failed to toggle auto-renew.',
    'لینک اشتراک با موفقیت در کلیپ‌بورد کپی شد.': 'Subscription link copied to clipboard.',
    'شناسه عددی تلگرام در کلیپ‌بورد کپی شد.': 'Telegram ID copied to clipboard.',
    'کد معرف در کلیپ‌بورد کپی شد.': 'Referral code copied to clipboard.',
    'لینک اختصاصی دعوت با موفقیت کپی شد.': 'Invite link copied to clipboard.',
    'کانفیگی برای کپی یافت نشد.': 'No configs available to copy.',
    'تاریخ تولد شما قبلاً ثبت شده و قابل تغییر نیست.': 'Your birth date is already locked.',
    'پرداخت شما با موفقیت تأیید شد و کیف پول شارژ گردید!': 'Payment verified and wallet credited!',
    'آدرس معتبری برای تست یافت نشد.': 'No valid host address found for testing.',
  };

  // DOM selector -> key map for static HTML template labels (preserves Persian DOM text cleanly for fa restoration)
  const SELECTOR_I18N_MAP = [
    ['#splashScreen > p', 'splash_subtitle'],
    ['#splashScreen > span', 'splash_loading'],
    ['#systemMaintenanceScreen h2', 'maint_title'],
    ['#systemMaintenanceScreen p', 'maint_desc'],
    ['.status-pill-maint > span', 'maint_pill'],
    ['#maintSupportBox button span', 'maint_support'],
    ['#systemInviteOnlyScreen h2', 'invite_title'],
    ['#systemJoinGateScreen h2', 'join_gate_title'],
    ['#systemJoinGateScreen p', 'join_gate_desc'],
    ['#joinGateChannelLinkBtn span', 'join_gate_btn'],
    ['#joinGateRecheckBtn span', 'join_gate_recheck'],
    ['#joinGateSupportBox button span', 'join_gate_help'],
    ['#systemBannedScreen h2', 'banned_title'],
    ['#closeBtn', 'close_app'],
    ['#navBottom .nav-btn[data-tab="tab-dashboard"] span:last-child', 'nav_dashboard'],
    ['#navBottom .nav-btn[data-tab="tab-reports"] span:last-child', 'nav_reports'],
    ['#navBottom .nav-btn[data-tab="tab-shop"] span:last-child', 'nav_shop'],
    ['#navBottom .nav-btn[data-tab="tab-wallet"] span:last-child', 'nav_wallet'],
    ['#navBottom .nav-btn[data-tab="tab-profile"] span:last-child', 'nav_profile'],
    ['#dashboardNoSubCard .rounded-full > span:last-child', 'no_sub_pill'],
    ['#dashboardNoSubCard p', 'no_sub_desc'],
    ['#noSubGoToShopBtn span:nth-of-type(1)', 'no_sub_cta'],
    ['#dashboardSubGaugeCard > div:first-child > span:first-child > span', 'total_traffic_label'],
    ['#dashboardSubGaugeCard > div:first-child > span:last-child > span:last-child', 'remaining_word'],
    ['#repSubDaily', 'rep_daily'],
    ['#repSubNightly', 'rep_nightly'],
    ['#repSubWeekly', 'rep_weekly'],
    ['#repSubMonthly', 'rep_monthly'],
    ['#repSubAnalytics', 'rep_analytics'],
    ['#revokeModal h3', 'revoke_title'],
    ['#cancelRevokeBtn', 'cancel_btn'],
    ['#cardAutoInitialBox button > span', 'card_auto_create'],
    ['#chargeWalletBtn span:last-child', 'charge_wallet_btn'],
    ['#walletSendGiftBtn span:last-child', 'send_gift_btn'],
    ['#transferWalletBtn span:last-child', 'transfer_wallet_btn'],
    ['#weeklyQuestsTitle', 'weekly_quests_title'],
    ['#weeklyQuestsModalSubtitle', 'weekly_quests_subtitle'],
    ['#walletTransferModalTitle', 'transfer_modal_title'],
    ['#walletTransferModalSubtitle', 'transfer_modal_subtitle'],
    ['#storyThemePickerLabel', 'story_theme_title'],
    ['#giftTypeBtn-redpacket span:last-child', 'red_packet_tab'],
  ];

  function translateUiPhrase(text) {
    if (getAppLanguage() !== 'en' || typeof text !== 'string') return text;
    const trimmed = text.trim();
    if (TOAST_FA_TO_EN[trimmed]) return TOAST_FA_TO_EN[trimmed];
    return text;
  }

  function t(key, varsOrFallback = null, fallback = null) {
    const lang = getAppLanguage();
    let template = '';
    if (lang === 'en' && Object.prototype.hasOwnProperty.call(I18N_EN, key)) {
      template = I18N_EN[key];
    } else if (typeof fallback === 'string') {
      template = fallback;
    } else if (typeof varsOrFallback === 'string') {
      template = varsOrFallback;
    } else {
      template = I18N_EN[key] || key;
    }
    if (varsOrFallback && typeof varsOrFallback === 'object') {
      return String(template).replace(/\{([a-zA-Z0-9_]+)\}/g, (_, k) =>
        varsOrFallback[k] !== undefined && varsOrFallback[k] !== null ? String(varsOrFallback[k]) : `{${k}}`
      );
    }
    return String(template);
  }

  function applyAppLocale(lang) {
    const norm = normalizeAppLang(lang);
    const isEn = norm === 'en';
    if (typeof window !== 'undefined') window.__remnaAppLang = norm;
    try { localStorage.setItem(STORAGE_KEY, norm); } catch (e) {}

    if (typeof document === 'undefined') return norm;
    const root = document.documentElement;
    if (root) {
      root.lang = norm;
      root.dir = isEn ? 'ltr' : 'rtl';
    }

    // Update language toggle pill buttons cleanly using design system tokens
    const langFaBtn = document.getElementById?.('langFaBtn');
    const langEnBtn = document.getElementById?.('langEnBtn');
    const activeCls = 'px-2.5 py-1 text-xs rounded-md font-bold transition bg-blue-600 text-white';
    const inactiveCls = 'px-2.5 py-1 text-xs rounded-md font-medium transition t-muted hover:t-main';
    if (langFaBtn) langFaBtn.className = isEn ? inactiveCls : activeCls;
    if (langEnBtn) langEnBtn.className = isEn ? activeCls : inactiveCls;

    // 1. Apply selector-mapped labels while preserving original Persian DOM copy in dataset
    for (const [selector, key] of SELECTOR_I18N_MAP) {
      const el = document.querySelector(selector);
      if (!el) continue;
      if (el.dataset.i18nFa === undefined) {
        el.dataset.i18nFa = el.textContent;
      }
      el.textContent = isEn ? (I18N_EN[key] || el.dataset.i18nFa) : el.dataset.i18nFa;
    }

    // 2. Apply explicit [data-i18n] attributes when declared on any DOM node
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
      if (!key) return;
      if (el.dataset.i18nFa === undefined) el.dataset.i18nFa = el.textContent;
      el.textContent = isEn ? (I18N_EN[key] || el.dataset.i18nFa) : el.dataset.i18nFa;
    });

    // 3. Flip directional arrow hint inside #noSubGoToShopBtn without touching LTR numbers
    const ctaArrow = document.querySelector('#noSubGoToShopBtn span:last-child');
    if (ctaArrow) {
      if (ctaArrow.dataset.i18nFa === undefined) ctaArrow.dataset.i18nFa = ctaArrow.textContent;
      ctaArrow.textContent = isEn ? '→' : ctaArrow.dataset.i18nFa;
    }

    return norm;
  }

  if (typeof window !== 'undefined') {
    window.normalizeAppLang = normalizeAppLang;
    window.getAppLanguage = getAppLanguage;
    window.applyAppLocale = applyAppLocale;
    window.translateUiPhrase = translateUiPhrase;
    window.t = t;
    if (typeof document !== 'undefined') {
      const bootLocale = () => applyAppLocale(getAppLanguage());
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootLocale, { once: true });
      } else {
        bootLocale();
      }
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      SUPPORTED_LANGS,
      normalizeAppLang,
      getAppLanguage,
      applyAppLocale,
      translateUiPhrase,
      t,
      I18N_EN,
    };
  }
})(typeof window !== 'undefined' ? window : globalThis);
