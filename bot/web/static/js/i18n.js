/**
 * RemnaStore Pro - Frontend Mini App i18n Runtime (Single Source of Truth)
 * Supports seamless live switching between Persian ('fa', RTL) and English ('en', LTR)
 * while preserving original Persian DOM markup without duplication.
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

  function isAppEn() {
    return getAppLanguage() === 'en';
  }

  function trText(faText, enText) {
    return getAppLanguage() === 'en' ? enText : faText;
  }

  const I18N_EN = {
    // Bottom Navigation & Top Header Chrome
    nav_dashboard: 'Dashboard',
    nav_reports: 'Reports',
    nav_shop: 'Shop',
    nav_wallet: 'Wallet',
    nav_profile: 'Account',
    nav_dashboard_aria: 'Dashboard tab',
    nav_reports_aria: 'Reports tab',
    nav_shop_aria: 'Shop tab',
    nav_wallet_aria: 'Wallet tab',
    nav_profile_aria: 'Account tab',
    header_avatar_title: 'User Profile (tap repeatedly for VIP)',
    default_user_name: 'User',
    default_dear_user: 'Dear User',
    header_loyalty_title: 'Your Loyalty Tier',
    switch_account_title: 'Switch Account',
    support_title: 'Online Support',
    theme_toggle_title: 'Toggle Theme',
    theme_toggle_aria: 'Toggle theme (light/dark)',
    close_app: 'Close',
    close_btn: 'Close',
    cancel_btn: 'Cancel',
    refresh_title: 'Refresh',

    // Splash & System Overlays
    splash_subtitle: 'Dedicated Subscription & Proxy Manager',
    splash_loading: 'Loading your account and sessions...',
    maint_title: 'Infrastructure Upgrade',
    maint_desc: 'To ensure maximum stability and speed, the platform is temporarily undergoing maintenance.',
    maint_pill: 'Back online shortly',
    maint_support: 'Contact Support',
    invite_title: 'Private — Invite Only',
    invite_desc: 'Registration requires an exclusive invitation link from an existing member.',
    invite_pill: 'Invitation required',
    join_gate_title: 'Channel Membership Required',
    join_gate_desc: 'Please join our official channel first to unlock purchases and account management.',
    join_gate_btn: 'Join Channel',
    join_gate_recheck: 'Verify Membership & Enter',
    join_gate_help: 'Need help? Contact Support',
    banned_title: 'Account Suspended',
    banned_desc: 'Your access to the bot and panel has been restricted by the administrator.',
    banned_pill: 'Account disabled / suspended',

    // Dashboard Tab
    dash_wheel_card: 'Lucky Wheel',
    dash_guide_card: 'Setup Guide',
    tutorial_badge_title: 'New app updates available',
    bday_card_title: 'Birthday Countdown',
    bday_card_box_title: 'View Birthday Countdown',
    day_unit: 'day(s)',
    days_unit: 'days',
    no_sub_pill: 'No Active Subscription',
    no_sub_hello: 'Hello',
    no_sub_dear: '!',
    no_sub_desc: 'You do not have an active subscription yet. Pick a plan in the shop to get started.',
    chip_fast: 'High Speed',
    chip_antifilter: 'Anti-Censorship',
    chip_support: '24/7 Support',
    no_sub_cta: 'Browse & Buy Plans',
    total_traffic_label: 'Total Service Traffic',
    remaining_word: 'left',
    remaining_full: 'Remaining',
    status_checking: 'Checking...',
    expiry_box_title: 'View live expiry countdown',
    service_expiry_label: 'Service Expiry',
    today_usage_label: 'Used Today',
    today_nodes_title: 'Usage Breakdown',
    today_nodes_loading: 'Loading usage breakdown...',
    sub_link_label: 'Subscription Link',
    view_btn: 'View',
    tools_actions_label: 'Tools & Actions:',
    copy_sub_title: 'Copy subscription link',
    qr_sub_title: 'QR Code',
    revoke_sub_title: 'Regenerate subscription link',
    scan_qr_hint: 'Scan directly with your phone camera or VPN client',
    auto_connect_hint: '1-Click Auto Import to Client',
    configs_btn: 'View Configs',
    copy_btn: 'Copy',
    revoke_btn: 'Regenerate',
    qr_btn: 'QR Code',

    // Reports & Analytics Tab
    active_sessions_title: 'Active Sessions',
    devices_zero_badge: '0 devices',
    active_devices_hint: 'Active devices linked to this account (HWID):',
    kill_all_btn: 'Disconnect All',
    loading_devices: 'Loading connected devices...',
    speedtest_banner_title: 'Internet Speed Test',
    start_btn: 'Start',
    rep_daily: 'Daily',
    rep_nightly: 'Nightly',
    rep_weekly: 'Weekly',
    rep_monthly: 'Monthly',
    rep_analytics: 'Analytics',
    rep_daily_title: 'Daily Report',
    rep_nightly_title: 'Nightly Report',
    rep_total_traffic: 'Total Plan Traffic:',
    rep_used_traffic: 'Traffic Used:',
    rep_remain_traffic: 'Remaining Traffic:',
    rep_today_total: "Today's Total Usage:",
    rep_yesterday_total: "Yesterday's Total Usage:",
    rep_expiry_label: 'Expires:',
    rep_daily_chart_title: "Today's Hourly Usage (24h):",
    rep_daily_empty: 'No active subscription to display today’s chart.',
    rep_nodes_breakdown: 'Server Usage Breakdown:',
    rep_loading_data: 'Fetching data...',
    rep_nightly_chart_title: "Last Night's Hourly Usage (24h):",
    rep_nightly_empty: 'No active subscription to display nightly chart.',
    rep_weekly_title: 'Past 7 Days Report',
    rep_weekly_badge: 'Last 7 days',
    rep_weekly_total: 'Total Usage This Week:',
    rep_weekly_busiest: 'Your Busiest Day:',
    rep_weekly_chart_title: 'Weekly Usage Chart (Last 7 Days):',
    rep_weekly_empty: 'No active subscription to display 7-day chart.',
    rep_weekly_nodes_title: 'Server Usage Breakdown (Last 7 Days):',
    rep_monthly_title: 'Monthly Report',
    rep_current_month: 'Current Month',
    rep_prev_month: 'Prev Month',
    rep_next_month: 'Next Month',
    rep_monthly_total: 'Total Monthly Account Usage:',
    rep_monthly_chart_title: 'Weekly Usage This Month:',
    rep_monthly_empty: 'No active subscription to display this month’s chart.',
    ach_card_title: 'My Gifts & Achievements',
    ach_won_traffic: 'Bonus Data Won',
    ach_coupons: 'Promo Codes',
    ach_birthday: 'Birthday Gift',
    ach_streak: 'Daily Wheel Streak:',
    ach_tickets: 'Spin Tickets:',
    not_registered: 'Not set',
    register_date_btn: 'Set Date',
    quests_card_title: 'Weekly Quests',
    burn_title: 'Smart Quota Forecast',
    burn_avg_label: '3-Day Daily Average:',
    burn_est_label: 'Est. Remaining Days:',
    lb_title: 'Top Consumers',
    lb_tab_daily: 'Daily',
    lb_tab_nightly: 'Nightly',
    lb_tab_7d: '7 Days',
    lb_tab_30d: '30 Days',
    lb_tab_monthly: 'Monthly',
    lb_week_all: 'Full Month',
    lb_week_1: 'Week 1',
    lb_week_2: 'Week 2',
    lb_week_3: 'Week 3',
    lb_week_4: 'Week 4',
    lb_loading: 'Loading leaderboard...',
    lb_empty_title: 'No leaderboard data recorded yet',
    lb_empty_desc: 'Usage rankings will appear once traffic is recorded in this period.',
    peak_title: 'Peak Usage Hours',
    peak_today: 'Today',
    peak_yesterday: 'Yesterday',
    peak_compare: 'Compare',
    peak_empty_title: 'No peak hours data recorded',
    peak_empty_desc: 'The peak curve will appear once daily traffic is recorded.',
    peak_bar_title: 'Time-Slot Distribution',
    peak_bar_unit: 'Usage (GB)',
    diurnal_dawn: 'Late Night',
    diurnal_morning: 'Morning',
    diurnal_afternoon: 'Afternoon',
    diurnal_night: 'Night',
    country_share_title: 'Regions & Countries',
    country_share_sub: 'Geo Share',
    country_share_empty_t: 'No regional usage recorded yet',
    country_share_empty_d: 'Server country distribution will appear after connecting.',
    device_share_title: 'Platforms & Devices',
    device_share_sub: 'Session Share',
    device_share_empty_t: 'No active devices registered',
    device_share_empty_d: 'Platform share appears once devices connect to your subscription.',

    // Shop Tab
    shop_header_title: 'Buy or Renew Plan',
    balance_label: 'Balance:',
    currency_unit_toman: 'Toman',
    shop_tab_full: 'Full Plans',
    shop_tab_traffic: 'Extra Data',
    shop_tab_time: 'Extra Time',
    shop_tab_custom: 'Custom Plan',
    custom_disabled_title: 'Custom Plan Builder is Currently Disabled',
    custom_disabled_desc: 'Custom volume/duration orders are temporarily disabled. Please choose from standard plans.',
    custom_builder_title: 'Custom Plan Builder',
    custom_builder_sub: 'Customize your own data, duration & devices',
    custom_gb_label: 'Traffic Quota:',
    custom_days_label: 'Validity Duration:',
    custom_hwid_label: 'Device Slots:',
    custom_hwid_unit: 'devices',
    custom_vol_badge_lbl: 'Volume Discount:',
    custom_loyalty_badge_lbl: 'Loyalty Discount:',
    custom_base_rate_label: 'Base + Data & Duration:',
    custom_final_price_label: 'Final Payable Amount:',
    custom_submit_btn: 'Buy & Activate Custom Plan',
    shop_loading_plans: 'Loading active plans...',
    apply_btn: 'Apply',
    coupon_placeholder: 'Enter your promo code...',
    won_coupons_title: 'Your Lucky Wheel Promo Codes:',

    // Wallet Tab
    wallet_card_flip_title: 'Tap card to flip',
    wallet_currency_title: 'Change Display Currency',
    wallet_copy_id_title: 'Copy Telegram ID (to receive gifts)',
    charge_wallet_btn: 'Top Up',
    send_gift_btn: 'Send Gift',
    transfer_wallet_btn: 'Transfer',
    wallet_classic_title: 'Your Wallet Balance',
    wallet_classic_desc: 'Usable for purchasing, renewing subscriptions, and add-on packs',
    voucher_box_title: 'Redeem Voucher / Gift Code',
    voucher_placeholder: 'Enter gift or voucher code...',
    active_pending_title: 'Active Pending Invoice',
    pending_amount_prefix: 'Amount:',
    view_and_pay_btn: 'View & Pay',
    tx_history_title: 'Transactions & Orders',
    tx_history_sub: 'Recent Activity',
    tx_loading: 'Loading transaction history...',

    // Profile & Settings Tab
    profile_avatar_aria: 'User Avatar',
    prof_badges_title: 'Achievements & Badges',
    phone_card_title: 'Boost Security & Unlock Rewards',
    phone_card_badge: 'Fast',
    phone_card_desc: 'Verify your phone number to unlock verified status, Bank Card Top-ups, and exclusive rewards.',
    phone_verify_now: 'Verify Phone Number Now',
    prof_identity_title: 'Account Identity',
    prof_identity_sub: 'Telegram ID, phone number & profile info',
    prof_tg_id_label: 'Telegram User ID',
    prof_copy_id_title: 'Copy ID',
    prof_ref_code_label: 'Your Referral Code',
    prof_copy_ref_title: 'Copy Referral Code',
    prof_phone_label: 'Phone Number',
    prof_not_set: 'Not linked',
    prof_verify_btn: 'Verify',
    prof_join_date_label: 'Member Since',
    prof_view_milestone_title: 'View Membership Card',
    prof_bday_label: 'Birthday',
    prof_bday_title: 'Register Birthday',
    prof_sub_status_label: 'Service Status',
    prof_sub_active: 'Active',
    prof_loyalty_label: 'Your Tier:',
    prof_loyalty_bronze: 'Bronze',
    prof_loyalty_sub: 'VIP Club & Loyalty Discounts',
    no_discount: 'No Discount',
    prof_loyalty_next: 'Next tier (Silver):',
    prof_loyalty_spent: 'Total Spent: 0 Toman',
    prof_loyalty_target: 'Next Target: 1,000,000 Toman',
    prof_loyalty_hint: 'Upgrade your VIP tier by purchasing plans and unlock permanent discounts across the shop.',
    prof_loyalty_cta: 'View All 7 Tiers & Perks',
    prof_ref_title: 'Invite Friends & Earn Rewards',
    prof_ref_badge_default: '1 GB Bonus per successful referral',
    prof_ref_invites: 'Total Invites',
    prof_ref_traffic: 'Traffic',
    prof_ref_commission: 'Commission',
    prof_ref_link_label: 'Your Invite Link:',
    prof_ref_copy_title: 'Copy Invite Link',
    prof_ref_share_btn: 'Share with Friends on Telegram',
    prof_ref_note_default: '<b>Note:</b> Referral traffic rewards are credited once your invited friend completes their <b>first purchase</b>.',
    settings_section_title: 'Telegram Notifications & Settings',
    settings_reports_title: 'Telegram Alerts & Reports',
    settings_reports_sub: 'Nightly, weekly, monthly usage & auto-cleanup',
    set_nightly_t: 'Nightly Report (23:59)',
    set_nightly_d: 'Daily summary of yesterday’s usage',
    set_weekly_t: 'Weekly Report (Friday Nights)',
    set_weekly_d: 'Summary of the past 7 days',
    set_monthly_t: 'Monthly Report (Month End)',
    set_monthly_d: 'Comprehensive monthly traffic report',
    set_clean_t: 'Auto-Clean Old Reports',
    set_clean_d: 'Delete previous report before sending a new one',
    settings_alerts_title: 'Traffic & Expiry Warnings',
    settings_alerts_sub: 'Low-quota and expiration reminders',
    set_low_traffic_t: 'Low Traffic Alert',
    set_expire_t: 'Expiry Reminder',
    settings_prefs_title: 'Lucky Wheel & App Preferences',
    settings_prefs_sub: 'Daily reminders, haptics & language',
    set_wheel_t: 'Lucky Wheel Reminder',
    set_wheel_d: 'Notify when your 24h free spin resets',
    set_sound_t: 'Sound Effects',
    set_sound_d: 'Play subtle sounds on clicks & rewards',
    set_autorenew_t: 'Auto-Renew Subscription',
    set_autorenew_d: 'Automatically renew before expiry using wallet balance',
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
    settings_wallet_title: 'Wallet Style & Appearance',
    settings_wallet_sub: '3D card style & primary display currency',
    set_wallet_graphic_t: 'Graphic 3D Wallet Card',
    set_wallet_graphic_d: 'Show metallic 3D card instead of classic view',
    set_currency_t: 'Wallet Display Currency',
    set_wallet_color_t: 'Wallet Card Color',
    settings_sec_title: 'Security & Link Reset',
    settings_sec_sub: 'Revoke compromised links & generate new ones',
    settings_sec_desc: 'If your subscription link was leaked or stops updating, revoke it immediately and issue a fresh private link.',
    settings_sec_btn: 'Regenerate Current Link',

    // Currency & Wallet Config
    target_account_prefix: 'Target Account:',
    configs_empty_title: 'No configs found in Remnawave panel.',
    configs_loading: 'Fetching configs from panel...',
    retry_btn: 'Retry',
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

    // Wallet & Topup Modal
    topup_badge: 'Wallet Top Up',
    topup_title: 'Add Credit & Top Up Wallet',
    topup_tab_card: 'Card',
    topup_tab_trx: 'TRON',
    topup_tab_pol: 'Polygon',
    topup_tab_stars: 'Stars',
    topup_amt_label: 'Top-Up Amount (Toman):',
    topup_amt_placeholder: 'Enter custom amount (Toman)',
    topup_none_title: 'No Payment Methods Enabled',
    topup_none_desc: 'Wallet top-up is temporarily unavailable. Please check back later or contact support.',
    topup_phone_title: 'Phone Verification Required',
    topup_phone_desc: 'To prevent fraud, phone number verification is required for bank card transfers.',
    topup_phone_btn: 'Verify Phone Number',
    card_auto_title: 'Instant Auto Card Transfer',
    card_auto_badge: 'Smart SMS Verification',
    card_auto_desc: 'Generate a unique exact-amount invoice. Once transferred via mobile banking, your wallet credits within seconds with no receipt upload needed.',
    card_auto_create: 'Create Instant Payment Invoice',
    card_auto_waiting: 'Waiting for bank transfer...',
    card_holder_label: 'Account Holder:',
    card_number_label: 'Destination Card Number:',
    card_rial_label: 'Exact Amount in Rials (Mobile Bank):',
    card_toman_label: 'Amount in Toman:',
    card_no_round_t: 'Do NOT round the amount!',
    card_no_round_d: 'This exact amount is reserved for you. Do not alter digits so auto-credit works instantly.',
    card_rule_paya: 'PAYA / POL transfers are NOT allowed! Use Card-to-Card transfer only.',
    card_auto_guide_t: 'Auto Verification Guide:',
    card_auto_guide_d: 'This invoice stays valid for <b>1 hour</b>. If bank SMS is delayed past expiry, upload your receipt manually below.',
    check_status_btn: 'Check Status',
    manual_toggle_btn: 'Manual Receipt Upload (Optional)',
    card_lock_title: 'Manual Receipt Upload Temporarily Locked',
    card_lock_desc: 'For 1 hour after creating or using an auto card invoice, manual receipt submission is locked.',
    card_manual_amt_label: 'Deposit Amount:',
    receipt_img_label: 'Payment Receipt Photo:',
    required_badge: 'Required',
    optional_badge: 'Optional',
    receipt_upload_btn: 'Select & Upload Receipt Photo',
    receipt_selected_def: 'Receipt image selected',
    remove_btn: '✕ Remove',
    receipt_ref_label: 'Tracking Code / Notes:',
    receipt_ref_ph: 'Reference ID, last 4 digits, or optional note',
    receipt_guide_html: '<b>Note:</b> A clear receipt photo is required. Including the tracking code speeds up admin approval.',
    submit_card_btn: 'Submit & Send Payment Receipt',
    ton_intro: 'Fast automated payment via TON blockchain network',
    ton_create_btn: 'Create TON Payment Invoice',
    pay_deadline_label: 'Time Limit:',
    pay_amount_label: 'Amount Due:',
    ton_wallet_label: 'Destination TON Address:',
    ton_copy_hint: 'Copy the address and send via Tonkeeper or Telegram Wallet.',
    ton_memo_label: 'Transfer Memo / Comment:',
    ton_memo_warn: 'You MUST include this exact Memo in your transfer comment for instant credit.',
    ton_guide_title: 'TON Deposit Guide & Common Mistakes:',
    ton_guide_1: '<b>Network:</b> Use <b>TON Mainnet</b> only (do NOT send on BEP-20 or BSC).',
    ton_guide_2: '<b>Memo/Comment:</b> Entering the Memo above is mandatory to match your account.',
    ton_guide_3: '<b>Recommended Wallet:</b> Tonkeeper or Telegram Wallet.',
    ton_pay_tg_btn: 'Pay with Telegram Wallet',
    ton_pay_tk_btn: 'Pay in Tonkeeper',
    cancel_new_btn: 'Cancel & New',
    trx_intro: 'Direct TRON (TRX) payment on TRC-20 with zero gateway fees',
    trx_create_btn: 'Create TRX Payment Invoice',
    trx_wallet_label: 'Destination TRON (TRX) Address:',
    trx_copy_hint: 'Copy the address and send via Trust Wallet or TronLink.',
    txid_label: 'Transaction ID (TxID):',
    trx_txid_ph: 'Paste TxID after sending',
    trx_guide_title: 'TRON Deposit Guide & Common Mistakes:',
    trx_guide_1: '<b>Asset & Network:</b> Send <b>TRX</b> on <b>TRC-20</b> only (do not send USDT or other tokens).',
    trx_guide_2: '<b>Exchange Fees:</b> Make sure net received amount covers the exact invoice.',
    trx_guide_3: '<b>Verify:</b> Paste your TxID below and tap Check Status.',
    trx_pay_tl_btn: 'Pay Directly with TronLink',
    pol_intro: 'Direct Polygon (POL) payment on Polygon network',
    pol_create_btn: 'Create POL Payment Invoice',
    pol_wallet_label: 'Destination Polygon Address:',
    pol_copy_hint: 'Send POL over Polygon network (Chain ID 137) only.',
    txhash_label: 'Transaction Hash (TxHash):',
    pol_txhash_ph: 'Paste TxHash (0x...) after transfer',
    pol_guide_title: 'Polygon Deposit Guide & Common Mistakes:',
    pol_guide_1: '<b>Supported Network:</b> <b>Polygon Mainnet (Chain ID 137)</b> ONLY! Sending via Ethereum ERC-20, Arbitrum or zkEVM will result in permanent loss.',
    pol_guide_2: '<b>Supported Token:</b> Native <b>POL</b> (formerly MATIC).',
    pol_guide_3: '<b>Payment:</b> Tap MetaMask below to pay directly, or send manually and paste your TxHash.',
    pol_pay_mm_btn: 'Pay Directly with MetaMask',
    stars_instant_label: 'Instant Telegram Payment:',
    stars_needed_label: 'Stars Required:',
    stars_rate_label: 'Approx. Exchange Rate:',
    stars_hint: 'Tapping pay opens Telegram’s official Stars checkout and credits your wallet immediately.',
    stars_pay_btn: 'Pay with Telegram Stars',

    // Modals: Revoke, QR, Configs, Switch, Sessions, Checkout, Guidance
    revoke_title: 'Regenerate subscription link?',
    revoke_desc: 'Generating a new link will <b>immediately invalidate your old link</b> across all devices and apps.',
    revoke_confirm_btn: 'Confirm & Regenerate',
    qr_badge: 'Direct Scan',
    qr_title: 'Config Connection QR Code',
    qr_sub: 'Scan with your phone camera or VPN app',
    configs_title: 'Subscription Configs',
    configs_sub: 'Per-protocol configs for routers and VPN apps',
    configs_wait: 'Fetching and parsing configs...',
    copy_all_configs_btn: 'Copy All Configs',
    switch_acc_title: 'Select Active Account',
    switch_acc_desc: 'Choose one of your active subscriptions:',
    switch_acc_loading: 'Loading accounts...',
    sessions_title: 'Active Sessions & Devices',
    sessions_sub: 'Connected HWID devices on this subscription',
    sessions_loading: 'Fetching active sessions...',
    checkout_badge: 'Confirm Order',
    checkout_title: 'Plan Order Summary',
    plan_label: 'Selected Plan:',
    traffic_label: 'Data Quota:',
    duration_label: 'Duration:',
    hwid_label: 'Max Devices:',
    payable_label: 'Amount Due:',
    wallet_curr_label: 'Your Wallet Balance:',
    wallet_after_label: 'Balance After Order:',
    new_acc_toggle: 'Buy as a brand-new subscription (do not renew current)',
    custom_uname_label: 'New Account Username:',
    random_suggest_btn: '🎲 Random',
    custom_uname_ph: 'e.g. ali_vpn',
    custom_uname_hint: 'English letters, digits, and _ only (3–32 chars) — auto-generated if empty',
    squad_switch_title: 'Server Group Switch Notice',
    squad_switch_desc: 'Confirming this purchase switches your current server group and starts a fresh cycle immediately.',
    squad_switch_b1: '• Existing remaining data & days will be replaced by the new plan.',
    squad_switch_b2: '• Your subscription URL stays unchanged — just tap Update Subscription in your app.',
    shortage_label: 'Wallet Shortage:',
    shortage_desc: 'Please top up your wallet first to complete this purchase.',
    confirm_buy_btn: 'Confirm & Purchase Now',
    guidance_badge: 'Smart Suggestion',
    guidance_title: 'Plan Selection Guide',
    guidance_confirm_btn: 'Confirm & Proceed',

    // Lucky Wheel & Results
    wheel_badge: 'Daily Lucky Wheel',
    wheel_title: 'Win Free Traffic & Exclusive Coupons',
    wheel_sub: 'Available for users with an active subscription',
    wheel_quests_btn: 'Quests',
    wheel_empty_slice: 'Empty',
    wheel_again_slice: 'Again',
    wheel_spin_btn: 'Spin!',
    wheel_init_hint: 'Tap the center button to spin the Lucky Wheel and try your luck!',
    wheel_cooldown_hint: 'Time left until your next free spin:',
    wheel_need_sub_warn: 'An active panel subscription is required to spin the Lucky Wheel.',
    wheel_res_congrats: 'Congratulations!',
    wheel_res_coupon_label: 'Your Exclusive Promo Code:',
    wheel_res_coupon_ttl: 'Valid for 7 days in the Shop tab',
    understood_btn: 'Got It',

    // Story Card & Purchase Success
    story_metric_remain: 'Remaining Plan Traffic:',
    story_uptime: '100% Uptime',
    story_promo_title: 'Fast & Unrestricted Internet',
    story_promo_sub: 'Claim <span id="storyCardRewardGb" class="font-sans">5</span> GB bonus via this card',
    story_theme_title: 'Card & Story Visual Theme:',
    story_banner_title: 'Story & Referral Reward:',
    story_banner_desc: 'Share this poster to your Telegram Story and earn <b id="storyRewardBannerGb" class="text-amber-700 dark:text-amber-300 font-sans">5</b> GB bonus traffic after your friend’s first purchase!',
    save_poster_btn: 'Save Poster',
    send_tg_btn: 'Share on Telegram',
    psvc_title: 'Order Completed Successfully!',
    psvc_sub: 'Your subscription is active and ready to connect.',
    psvc_plan: 'Purchased Plan:',
    psvc_uname: 'Username:',
    psvc_paid: 'Amount Paid:',
    psvc_new_bal: 'New Balance:',
    psvc_squad_t: 'Connection Update Notice:',
    psvc_squad_d: 'Your server group has been upgraded. <b>Your subscription link stays identical</b>; simply tap <b>Update Subscription</b> in your VPN client to reload servers.',
    psvc_url_label: 'Your Subscription Link:',
    open_link_btn: 'Open Link',
    official_invoice_btn: 'Invoice',
    view_dash_btn: 'Go to Dashboard',
    send_receipt_img_btn: 'Send Receipt Image to Telegram',

    // Support Chat & Setup Guide & Speed Test
    support_header: 'RemnaStore Dedicated Support',
    support_loading: 'Loading support history...',
    support_empty_t: 'Direct Support Chat',
    support_empty_d: 'Ask any question or report an issue here. Support replies appear right inside this window.',
    support_typing: 'Support agent is typing...',
    support_input_ph: 'Write your message to support...',
    tutorial_title: 'Connection Guide & Client Apps',
    os_android: 'Android',
    os_windows: 'Windows',
    os_mac: 'macOS',
    os_linux: 'Linux',
    os_tv: 'Smart TV',
    os_prereqs: 'Prerequisites',
    copy_sub_link_btn: 'Copy Subscription Link',
    speedtest_title: 'Internet Speed Test',
    speedtest_sub: 'Measure real-time download, upload & ping latency',
    your_ip_label: 'Your IP Address:',
    speed_ready: 'Ready',
    data_used_label: 'Data Used:',
    mb_unit: 'MB',
    dl_label: 'Download',
    ul_label: 'Upload',
    ping_label: 'Ping',
    jitter_label: 'Jitter',
    speed_start_btn: 'Start Speed Test',
    speed_res_title: 'Network Speed Test Results',
    speed_res_rating_ok: '🟢 Excellent Connection',
    speed_res_dl: 'Download',
    speed_res_ul: 'Upload',
    speed_res_ping: 'Ping',
    speed_res_jitter: '〰️ Jitter',
    speed_res_data: 'Test Data Used:',
    retest_btn: 'Test Again',

    // Modals: Birthday, Thresholds, Currency, Expiry, Membership, Kill
    bday_modal_title: 'Set Your Birthday',
    bday_modal_desc: 'Register your birthday once to unlock annual bonus traffic & VIP discount perks.',
    bday_selected_label: 'Selected Date:',
    bday_day_tab: 'Day:',
    bday_month_tab: 'Month:',
    bday_year_tab: 'Year:',
    bday_save_btn: 'Save Birthday',
    threshold_title: 'Set Alert Threshold',
    threshold_sub: 'Percentage or days before receiving alerts',
    currency_modal_title: 'Select Wallet Display Currency',
    currency_modal_sub: 'Primary currency shown on your 3D wallet card',
    expiry_badge_title: 'Live Service Expiry Countdown',
    expiry_default_acc: 'Active Subscription Status',
    hours_unit: 'Hours',
    mins_unit: 'Minutes',
    secs_unit: 'Seconds',
    daily_allowance_lbl: 'Recommended Daily Budget:',
    exact_expiry_lbl: 'Exact Expiration Date:',
    pace_status_lbl: 'Consumption Pace:',
    pace_optimal: 'Optimal',
    autorenew_short: 'Auto-Renew',
    autorenew_short_d: 'Auto-renew on expiry using wallet credit',
    renew_now_btn: 'Renew or Buy New Plan',
    bday_cd_badge: 'Your Birthday Countdown',
    bday_cd_sub: 'Birthday Celebration & Special Gifts',
    birth_month_lbl: 'Birth Month:',
    bday_gifts_title: 'Your Birthday Gifts:',
    bday_gifts_desc: 'On your birthday, bonus high-speed traffic and an exclusive VIP discount coupon will be granted to your account.',
    member_badge: 'Membership Milestone',
    member_hero_sub: 'Glorious days with us',
    member_total_spent: 'Total Spent',
    member_total_traffic: 'Lifetime Traffic',
    member_tier_lbl: 'Current Loyalty Tier:',
    member_thanks: 'Thank you for choosing us for fast, reliable, unrestricted access! 💙',
    kill_all_title: 'Disconnect All Active Sessions',
    kill_all_sub: 'Terminate sessions & issue new secure subscription link',
    kill_all_q: 'Are you sure you want to disconnect all active devices linked to this account?',
    kill_all_warn: 'All active sessions will stop immediately, your previous subscription link will expire, and a fresh link will be generated.',
    kill_all_confirm: 'Yes, Disconnect All',
    kill_one_title: 'Disconnect Device',
    kill_one_sub: 'Revoke this device’s access to your subscription',
    device_lbl: 'Device:',
    ip_lbl: 'IP Address:',
    kill_one_warn: 'This device will be disconnected immediately and requires updating the subscription link to reconnect.',
    kill_one_confirm: 'Yes, Disconnect',

    // Modals: Gift, Red Packet, Invoice, Loyalty, P2P Transfer, Quests
    gift_title: 'Send Gift to Friends',
    gift_sub: 'Gift a subscription plan or wallet credit to others',
    gift_tab_new: 'New Gift',
    gift_tab_history: 'History',
    gift_type_label: 'Gift Type:',
    gift_wallet_type: 'Wallet Top-up',
    gift_plan_type: 'Subscription',
    red_packet_tab: 'Red Packet',
    gift_bal_amt_lbl: 'Gift Amount (Toman):',
    gift_amt_ph: 'e.g. 50,000',
    gift_plan_lbl: 'Gift Plan:',
    select_btn: 'Select',
    gift_select_plan_t: 'Select Subscription Plan...',
    gift_select_plan_d: 'Tap here to choose a plan to gift',
    rp_amt_lbl: 'Total Red Packet Pool (Toman):',
    rp_amt_ph: 'Min 5,000 per person',
    rp_slots_lbl: 'Recipients (2 to 50):',
    rp_split_lbl: 'Split Mode:',
    rp_random: 'Random',
    rp_equal: 'Equal',
    gift_delivery_lbl: 'Delivery Method:',
    gift_direct_btn: 'Direct Telegram Send',
    gift_link_btn: 'Create Gift Link',
    recipient_input_lbl: 'Recipient Username or Telegram ID:',
    recipient_input_ph: '@username or 123456789',
    gift_direct_hint: 'The bot immediately delivers the gift and greeting message to your friend.',
    gift_note_lbl: 'Greeting Message:',
    gift_note_ph: 'e.g. Hope this helps you stay connected! 🌹',
    gift_cost_lbl: 'Wallet Deduction:',
    your_balance_lbl: 'Your Wallet Balance:',
    gift_submit_btn: 'Create & Send Gift',
    gift_created_t: 'Gift created successfully!',
    gift_code_lbl: 'Gift Code:',
    copy_code_btn: 'Copy Code',
    gift_link_hint: 'Share this link so your friend can claim with one tap:',
    copy_link_btn: 'Copy Link',
    rp_history_lbl: 'Your Group Red Packets:',
    gift_history_lbl: 'Your Sent Gifts History:',
    gift_select_modal_t: 'Choose Gift Subscription',
    gift_select_modal_d: 'Select one of the plans below to gift:',
    gift_select_loading: 'Loading plans...',
    inv_header_title: 'Official Digital Invoice',
    inv_header_sub: 'Verified Digital Transaction Receipt',
    inv_seller_lbl: '🏢 Provider:',
    inv_buyer_lbl: '👤 Buyer:',
    inv_col_desc: 'Service Description',
    inv_col_amt: 'Amount (Toman)',
    inv_total_lbl: 'Total Paid:',
    inv_status_lbl: 'Transaction Status:',
    inv_paid_badge: 'Paid',
    inv_wallet_st_lbl: 'Wallet Impact:',
    inv_tracking_lbl: 'Tracking ID:',
    inv_send_img_btn: 'Send Official Receipt Image to Chat',
    inv_send_tg_btn: 'Send Official Receipt to My Telegram',
    inv_close_btn: 'Close Invoice',
    loyalty_modal_title: 'Loyalty Club & VIP Tiers',
    loyalty_modal_sub: 'Your exclusive discounts & tier progression',
    loyalty_curr_lbl: 'Your Current Tier:',
    loyalty_spent_lbl: 'Total Verified Purchases:',
    loyalty_disc_lbl: 'Your Active Discount:',
    loyalty_all_tiers: '7 Loyalty Club Tiers:',
    loyalty_from_zero: 'From 0 Toman',
    loyalty_tier_silver: 'Silver',
    loyalty_tier_gold: 'Gold',
    loyalty_tier_platinum: 'Platinum',
    loyalty_tier_ruby: 'Ruby',
    loyalty_tier_emerald: 'Emerald',
    loyalty_tier_diamond: 'Diamond',
    loyalty_tier_bronze_desc: 'Default starting tier upon registration (no discount)',
    discount_word: 'discount',
    loyalty_priority_support: '+ Priority Support',
    transfer_modal_title: 'Direct Money Transfer',
    transfer_modal_subtitle: 'Instant zero-fee P2P Toman transfer',
    transfer_amt_lbl: 'Transfer Amount (Min 5,000 Toman):',
    transfer_note_lbl: 'Note (Optional):',
    transfer_note_ph: 'Subscription share or friendly transfer...',
    transfer_curr_bal_lbl: 'Current Balance:',
    transfer_submit_btn: 'Confirm & Send Now',
    weekly_quests_title: 'Weekly Quests',
    weekly_quests_subtitle: 'Complete quests to earn free Lucky Wheel spin tickets',
  };

  // Automatic lookup for Persian notifications / alerts when user switches UI to English
  const TOAST_FA_TO_EN = {
    'تنظیمات با موفقیت ذخیره شد.': 'Settings saved successfully.',
    'خطا در ذخیره تنظیمات': 'Failed to save settings.',
    'خطا در ذخیره تنظیمات زبان.': 'Failed to save language setting.',
    'خطا در برقراری ارتباط با سرور.': 'Server connection error.',
    'خطا در ارتباط با سرور.': 'Server connection error.',
    'تمدید خودکار فعال شد.': 'Auto-renew enabled.',
    'تمدید خودکار غیرفعال شد.': 'Auto-renew disabled.',
    'خطا در تغییر وضعیت تمدید خودکار': 'Failed to toggle auto-renew.',
    'لینک اشتراک با موفقیت در کلیپ‌بورد کپی شد.': 'Subscription link copied to clipboard.',
    'لینک اشتراک در کلیپ‌بورد کپی شد.': 'Subscription link copied to clipboard.',
    'لینک اشتراکی برای کپی یافت نشد.': 'No subscription link found to copy.',
    'اشتراک فعالی برای اتصال یافت نشد.': 'No active subscription found to connect.',
    'شناسه عددی تلگرام در کلیپ‌بورد کپی شد.': 'Telegram ID copied to clipboard.',
    'شناسه تلگرام یافت نشد.': 'Telegram ID not found.',
    'کد معرف در کلیپ‌بورد کپی شد.': 'Referral code copied to clipboard.',
    'لینک اختصاصی دعوت با موفقیت کپی شد.': 'Invite link copied to clipboard.',
    'کانفیگی برای کپی یافت نشد.': 'No configs available to copy.',
    'کانفیگ اختصاصی با موفقیت در کلیپ‌بورد کپی شد.': 'Config copied to clipboard.',
    'تاریخ تولد شما قبلاً ثبت شده و قابل تغییر نیست.': 'Your birth date is already locked.',
    'تاریخ زادروز شما با موفقیت ثبت گردید.': 'Your birthday was saved successfully.',
    'خطا در ثبت تاریخ تولد': 'Failed to save birthday.',
    'خطای شبکه در ذخیره تاریخ زادروز': 'Network error saving birthday.',
    'پرداخت شما با موفقیت تأیید شد و کیف پول شارژ گردید!': 'Payment verified and wallet credited!',
    'پرداخت تایید شد و حساب شما شارژ گردید!': 'Payment approved and wallet credited!',
    'آدرس معتبری برای تست یافت نشد.': 'No valid host address found for testing.',
    'کد تخفیف حذف گردید.': 'Promo code removed.',
    'لطفاً کد تخفیف را وارد فرمایید.': 'Please enter a promo code.',
    'کد تخفیف نامعتبر است.': 'Invalid promo code.',
    'خطا در بررسی کد تخفیف.': 'Failed to validate promo code.',
    'نام کاربری باید بین 3 تا 32 کاراکتر (فقط حروف انگلیسی، اعداد و _) باشد.': 'Username must be 3–32 chars (A-Z, 0-9, _).',
    'خطا در ثبت خرید': 'Purchase failed.',
    'خرید شما با موفقیت انجام شد!': 'Purchase completed successfully!',
    'فاکتور این سفارش در بخش کیف پول ثبت گردید.': 'Invoice saved in your Wallet history.',
    'لینک اشتراک قبلی ابطال و لینک جدید با موفقیت صادر شد.': 'Old link revoked and fresh subscription link issued.',
    'خطا در تغییر لینک اشتراک.': 'Failed to regenerate subscription link.',
    'حالت نمایش کارت گرافیکی فعال شد.': '3D Graphic Wallet Card enabled.',
    'حالت نمایش کادر ساده فعال شد.': 'Classic Wallet View enabled.',
    'افکت‌های صوتی لمسی فعال شد.': 'Sound effects enabled.',
    'افکت‌های صوتی لمسی غیرفعال شد.': 'Sound effects disabled.',
    'لطفاً ابتدا مبلغ شارژ مورد نظر خود را وارد یا انتخاب نمایید.': 'Please enter or pick a top-up amount first.',
    'شماره کارت در کلیپ‌بورد کپی شد.': 'Card number copied to clipboard.',
    'شماره کارتی برای کپی کردن یافت نشد.': 'No card number available to copy.',
    'مبلغ در کلیپ‌بورد کپی شد.': 'Amount copied to clipboard.',
    'فاکتور پرداخت هوشمند با موفقیت ایجاد شد.': 'Smart payment invoice created.',
    'خطا در ایجاد فاکتور': 'Failed to create invoice.',
    'مهلت پرداخت این فاکتور به پایان رسیده است.': 'This payment invoice has expired.',
    'هنوز پیامی مبنی بر واریز دریافت نشده است؛ لطفاً پس از واریز صبور باشید.': 'No bank transfer detected yet; please wait shortly after paying.',
    'امکان لغو این فاکتور وجود ندارد.': 'Cannot cancel this invoice.',
    'فاکتور پرداخت لغو گردید.': 'Payment invoice cancelled.',
    'فاکتور لغو شد. می‌توانید فاکتور جدید صادر فرمایید.': 'Invoice cancelled. You can create a new one.',
    'فاکتور قبلی لغو شد. می‌توانید فاکتور جدید صادر فرمایید.': 'Previous invoice cancelled.',
    'حداکثر حجم مجاز تصویر 10 مگابایت است.': 'Max image size allowed is 10 MB.',
    'خطا در پردازش تصویر فیش.': 'Error processing receipt image.',
    'لطفاً تصویر فیش واریزی را بارگذاری فرمایید.': 'Please upload a payment receipt image.',
    'رسید با موفقیت ثبت شد و پس از بررسی ادمین حساب شارژ می‌گردد.': 'Receipt submitted! Your balance will be credited once approved.',
    'خطا در ارسال درخواست.': 'Failed to submit request.',
    'پرداخت استارز با موفقیت تایید شد و کیف پول شارژ گردید!': 'Telegram Stars payment confirmed and wallet credited!',
    'پرداخت استارز لغو شد.': 'Telegram Stars payment cancelled.',
    'پرداخت استارز انجام نشد.': 'Telegram Stars payment did not complete.',
    'مقدار TON کپی شد.': 'TON amount copied.',
    'آدرس ولت TON کپی شد.': 'TON wallet address copied.',
    'کامنت (Memo) کپی شد.': 'Memo comment copied.',
    'پرداخت تایید شد و کیف پول شارژ گردید!': 'Payment confirmed and wallet credited!',
    'تراکنش هنوز تایید نشده است.': 'Transaction not confirmed yet.',
    'خطا در استعلام پرداخت.': 'Payment verification error.',
    'لطفاً کد شارژ را وارد نمایید.': 'Please enter a voucher or gift code.',
    'کیف پول با موفقیت شارژ گردید!': 'Wallet topped up successfully!',
    'کد شارژ نامعتبر است.': 'Invalid voucher code.',
    'ابتدا فاکتور پرداخت TON را ایجاد فرمایید.': 'Please create a TON invoice first.',
    'آدرس ولت ترون کپی شد.': 'TRON wallet address copied.',
    'مقدار TRX کپی شد.': 'TRX amount copied.',
    'فاکتور ترون لغو شد.': 'TRX invoice cancelled.',
    'ابتدا فاکتور ترون را ایجاد فرمایید.': 'Please create a TRX invoice first.',
    'لطفاً شناسه تراکنش (TxID) را وارد فرمایید.': 'Please enter transaction ID (TxID).',
    'واریز TRX در شبکه تأیید شد و کیف پول شارژ گردید!': 'TRX deposit verified and wallet credited!',
    'آدرس ولت پلیگان کپی شد.': 'Polygon wallet address copied.',
    'مقدار POL کپی شد.': 'POL amount copied.',
    'فاکتور پلیگان لغو شد.': 'Polygon invoice cancelled.',
    'ابتدا فاکتور پلیگان را ایجاد فرمایید.': 'Please create a Polygon invoice first.',
    'لطفاً هش تراکنش (TxHash) را وارد فرمایید.': 'Please enter transaction hash (TxHash).',
    'تراکنش در متامسک ثبت شد! در حال تأیید خودکار...': 'MetaMask transaction sent! Verifying automatically...',
    'تراکنش در متامسک لغو شد.': 'MetaMask transaction cancelled.',
    'واریز POL در شبکه پلیگان تأیید شد و کیف پول شارژ گردید!': 'POL deposit verified on Polygon and wallet credited!',
    'شماره تماس با موفقیت ثبت شد. در حال به‌روزرسانی...': 'Phone number verified! Updating...',
    'اشتراک‌گذاری شماره تماس لغو گردید.': 'Phone verification cancelled.',
    'نام کاربری ربات در دسترس نیست.': 'Bot username is unavailable.',
    'اکانت فعال تغییر یافت.': 'Active subscription switched.',
    'موجودی کیف پول شما به‌روزرسانی شد!': 'Your wallet balance was updated!',
    'عضویت شما با موفقیت تأیید شد. خوش آمدید!': 'Channel membership verified. Welcome!',
    'هنوز در کانال عضو نشده‌اید. لطفاً ابتدا در کانال عضو شوید.': 'You haven’t joined the channel yet.',
    'خطا در کپی خودکار؛ لطفاً متن را دستی انتخاب و کپی فرمایید.': 'Auto-copy failed; please select and copy manually.',
    'نشست کاربری تلگرام منقضی شد. لطفاً صفحه را مجدداً باز کنید.': 'Telegram session expired. Please reopen the Mini App.',
    'این دکمه در تلگرام واقعی، پنجره مینی‌اپ را می‌بندد.': 'In Telegram, this button closes the Mini App window.',
    'لینک دعوت کپی شد و صفحه اشتراک‌گذاری در استوری باز گردید.': 'Invite link copied and Story share opened.',
    'پوستر استوری با بالاترین کیفیت در گالری ذخیره شد.': 'Story poster saved to your device!',
    'امکان ذخیره مستقیم پوستر به دلیل سیاست مرورگر نبود.': 'Could not save poster due to browser restrictions.',
    'تمام نشست‌های فعال مسدود و لینک اشتراک امن جدید صادر شد.': 'All active sessions terminated and new secure link issued.',
    'دستگاه با موفقیت قطع شد.': 'Device disconnected successfully.',
    'کارت هدیه با موفقیت صادر شد!': 'Gift card created successfully!',
    'لینک هدیه در کلیپ‌بورد کپی شد!': 'Gift link copied to clipboard!',
    'کد اختصاصی هدیه کپی شد!': 'Gift code copied!',
    'لینک کپی شد!': 'Link copied!',
    'کد کپی شد!': 'Code copied!',
    'لطفاً کد هدیه را وارد فرمایید.': 'Please enter a gift code.',
    'کد تخفیف فعالی برای کپی وجود ندارد': 'No active promo code to copy.',
    'حداقل مبلغ هدیه اعتبار 10,000 تومان می‌باشد.': 'Minimum gift amount is 10,000 Toman.',
    'لطفاً بسته مورد نظر را انتخاب فرمایید.': 'Please select a subscription plan.',
    'لطفاً آیدی یا شناسه عددی تلگرام گیرنده را وارد فرمایید.': 'Please enter the recipient’s Telegram @username or ID.',
    'اطلاعات فاکتور در دسترس نیست.': 'Invoice details unavailable.',
    'فاکتور رسمی به پیوی تلگرام شما ارسال شد!': 'Official invoice sent to your Telegram chat!',
    'تصویر فاکتور با موفقیت به چت تلگرام شما ارسال شد!': 'Official invoice image sent to your Telegram!',
    'تصویر باکیفیت فاکتور رسمی ذخیره گردید.': 'High-res invoice image saved!',
    'تصویر رسید سفارش ذخیره شد.': 'Order receipt image saved!',
  };

  // Fallback regex translation for parameterized backend/legacy Persian toasts
  const REGEX_FA_TO_EN = [
    [/^حداقل مبلغ شارژ ([\d,]+) تومان است\.$/, (_, amt) => `Minimum top-up amount is ${amt} Toman.`],
    [/^حداکثر مبلغ شارژ ([\d,]+) تومان است\.$/, (_, amt) => `Maximum top-up amount is ${amt} Toman.`],
    [/^شما حداکثر (\d+) درخواست در انتظار بررسی دارید\..*$/, (_, n) => `You already have ${n} pending review requests.`],
    [/^شما یک فاکتور فعال کارت‌به‌کارت به مبلغ ([\d,]+) تومان دارید\..*$/, (_, amt) => `You have an active card invoice (${amt} Toman). Please pay or cancel it first.`],
    [/^شما یک فاکتور (?:فعال )?در جریان (.+?) دارید\..*$/, (_, cur) => `You have an active ${cur} invoice. Please pay or cancel it first.`],
    [/^در حال انتقال به (.+?) \(لینک در کلیپ‌بورد کپی شد\)$/, (_, app) => `Opening ${app} (subscription link copied).`],
    [/^لینک اشتراک کپی شد\. لطفاً آن را داخل نرم‌افزار (.*?) وارد کنید\.$/, (_, app) => `Link copied. Import it into ${app || 'your client'}.`],
    [/^🎨 رنگ کارت به (.+?) تغییر یافت\.$/, (_, col) => `🎨 Card theme changed to ${col}.`],
    [/^کد تخفیف کپی شد:\s*(.+)$/, (_, code) => `Promo code copied:\n${code}`],
    [/^کپی شد:\s*(.+)$/, (_, txt) => `Copied:\n${txt}`],
  ];

  // Pure leaf selectors or structural-preserving hooks (NEVER target nodes with child <img>/<svg> elements!)
  const SELECTOR_I18N_MAP = [
    ['#splashScreen > p', 'splash_subtitle'],
    ['#splashScreen > span', 'splash_loading'],
    ['#systemMaintenanceScreen h2', 'maint_title'],
    ['#systemMaintenanceScreen p', 'maint_desc'],
    ['.status-pill-maint > span', 'maint_pill'],
    ['#maintSupportBox button span', 'maint_support'],
    ['#systemInviteOnlyScreen h2', 'invite_title'],
    ['#systemInviteOnlyScreen p', 'invite_desc'],
    ['#systemJoinGateScreen h2', 'join_gate_title'],
    ['#systemJoinGateScreen p', 'join_gate_desc'],
    ['#joinGateChannelLinkBtn span', 'join_gate_btn'],
    ['#joinGateRecheckBtn span', 'join_gate_recheck'],
    ['#joinGateSupportBox button span', 'join_gate_help'],
    ['#systemBannedScreen h2', 'banned_title'],
    ['#systemBannedScreen p', 'banned_desc'],
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
    ['#transferCurrentBalance + span', 'currency_unit_toman'],
    ['#storyThemePickerLabel', 'story_theme_title'],
    ['#giftTypeBtn-redpacket span:last-child', 'red_packet_tab'],
  ];

  // Helper to update leading/trailing text nodes inside compound spans without recreating inner counter <span>s
  const PARTIAL_TEXT_MAP = [
    ['#customPlanVolumeDiscountRow > span:first-child', 0, 'Volume Discount (', '):'],
    ['#customPlanDiscountRow > span:first-child', 0, 'Loyalty Club Discount (', '):'],
    ['#customPlanHwidCostRow > span:first-child', 0, 'Extra Device Slot Fee (', ' users):'],
  ];

  function _readStore(el, dataKey, attrFallback) {
    if (el && el.dataset && el.dataset[dataKey] !== undefined) return el.dataset[dataKey];
    if (el && typeof el.getAttribute === 'function') return el.getAttribute(attrFallback);
    return undefined;
  }

  function _writeStore(el, dataKey, attrFallback, val) {
    if (el && el.dataset) {
      el.dataset[dataKey] = val;
    } else if (el && typeof el.setAttribute === 'function') {
      el.setAttribute(attrFallback, val);
    }
  }

  function _applyBatchAttr(selector, keyAttr, targetAttr, dsKey, attrFallback, isEn, isHtml = false) {
    if (typeof document === 'undefined' || typeof document.querySelectorAll !== 'function') return;
    document.querySelectorAll(selector).forEach((el) => {
      const key = typeof el.getAttribute === 'function' ? el.getAttribute(keyAttr) : null;
      if (!key) return;
      const curVal = targetAttr === 'textContent' ? el.textContent : (isHtml ? el.innerHTML : el.getAttribute(targetAttr));
      let faVal = _readStore(el, dsKey, attrFallback);
      if (faVal === undefined || faVal === null) {
        faVal = curVal || '';
        _writeStore(el, dsKey, attrFallback, faVal);
      }
      const nextVal = isEn ? (I18N_EN[key] !== undefined ? I18N_EN[key] : faVal) : faVal;
      if (targetAttr === 'textContent') {
        el.textContent = nextVal;
      } else if (isHtml) {
        el.innerHTML = nextVal;
      } else if (typeof el.setAttribute === 'function') {
        el.setAttribute(targetAttr, nextVal);
      }
    });
  }

  function _applyPartialRowLabels(isEn) {
    if (typeof document === 'undefined' || typeof document.querySelector !== 'function') return;
    for (const [selector, _nodeIdx, enPrefix, enSuffix] of PARTIAL_TEXT_MAP) {
      const el = document.querySelector(selector);
      if (!el || !el.firstChild) continue;
      if (el.firstChild.nodeType === 3) {
        if (el.dataset.i18nPfxFa === undefined) el.dataset.i18nPfxFa = el.firstChild.nodeValue;
        el.firstChild.nodeValue = isEn ? enPrefix : el.dataset.i18nPfxFa;
      }
      if (enSuffix && el.lastChild && el.lastChild.nodeType === 3) {
        if (el.dataset.i18nSfxFa === undefined) el.dataset.i18nSfxFa = el.lastChild.nodeValue;
        el.lastChild.nodeValue = isEn ? enSuffix : el.dataset.i18nSfxFa;
      }
    }
  }

  function translateUiPhrase(text) {
    if (getAppLanguage() !== 'en' || typeof text !== 'string') return text;
    const trimmed = text.trim();
    if (TOAST_FA_TO_EN[trimmed]) return TOAST_FA_TO_EN[trimmed];
    for (const [re, replacer] of REGEX_FA_TO_EN) {
      const m = trimmed.match(re);
      if (m) return replacer(...m);
    }
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
    document.documentElement.lang = norm;
    document.documentElement.dir = isEn ? 'ltr' : 'rtl';

    const faBtn = document.getElementById('langFaBtn');
    const enBtn = document.getElementById('langEnBtn');
    if (faBtn && enBtn) {
      if (norm === 'fa') {
        faBtn.className = 'lang-opt-btn px-2.5 py-1 text-xs rounded-md font-bold transition bg-blue-600 text-white shadow-sm';
        enBtn.className = 'lang-opt-btn px-2.5 py-1 text-xs rounded-md font-medium transition t-muted hover:t-main';
      } else {
        enBtn.className = 'lang-opt-btn px-2.5 py-1 text-xs rounded-md font-bold transition bg-blue-600 text-white shadow-sm';
        faBtn.className = 'lang-opt-btn px-2.5 py-1 text-xs rounded-md font-medium transition t-muted hover:t-main';
      }
    }

    // 1. Apply selector-mapped labels while preserving original Persian DOM copy
    for (const [selector, key] of SELECTOR_I18N_MAP) {
      const el = document.querySelector(selector);
      if (!el) continue;
      if (el.dataset.i18nFa === undefined) {
        el.dataset.i18nFa = el.textContent;
      }
      el.textContent = isEn ? (I18N_EN[key] || el.dataset.i18nFa) : el.dataset.i18nFa;
    }

    // 2. Apply explicit [data-i18n*] DOM attributes across text, HTML, placeholders, titles & aria-labels
    _applyBatchAttr('[data-i18n]', 'data-i18n', 'textContent', 'i18nFa', 'data-i18n-fa', isEn, false);
    _applyBatchAttr('[data-i18n-html]', 'data-i18n-html', 'innerHTML', 'i18nHtmlFa', 'data-i18n-html-fa', isEn, true);
    _applyBatchAttr('[data-i18n-placeholder]', 'data-i18n-placeholder', 'placeholder', 'i18nPlaceholderFa', 'data-i18n-placeholder-fa', isEn, false);
    _applyBatchAttr('[data-i18n-title]', 'data-i18n-title', 'title', 'i18nTitleFa', 'data-i18n-title-fa', isEn, false);
    _applyBatchAttr('[data-i18n-aria]', 'data-i18n-aria', 'aria-label', 'i18nAriaFa', 'data-i18n-aria-fa', isEn, false);
    _applyPartialRowLabels(isEn);

    // 3. Flip directional arrows, month nav arrows, tutorial tabs bar, accordions & currency views
    const noSubArrow = document.querySelector('#noSubGoToShopBtn span:last-child');
    if (noSubArrow && (noSubArrow.textContent === '←' || noSubArrow.textContent === '→')) {
      noSubArrow.textContent = isEn ? '→' : '←';
    }
    const chatInputEl = document.getElementById('chatInput');
    if (chatInputEl) chatInputEl.dir = isEn ? 'ltr' : 'rtl';
    const couponInputEl = document.getElementById('couponInput');
    if (couponInputEl) couponInputEl.dir = isEn ? 'ltr' : 'auto';
    const transferCurBalEl = document.getElementById('transferCurrentBalance');
    if (transferCurBalEl && transferCurBalEl.parentElement) {
      transferCurBalEl.parentElement.dir = isEn ? 'ltr' : 'rtl';
    }
    const tutorialTabsBar = document.getElementById('tutorialOsTabsBar');
    if (tutorialTabsBar) tutorialTabsBar.dir = isEn ? 'ltr' : 'rtl';

    const repPrevArrow = document.querySelector('#repMonthPrevBtn > span:first-child');
    if (repPrevArrow) repPrevArrow.textContent = isEn ? '◀' : '▶';
    const repNextArrow = document.querySelector('#repMonthNextBtn > span:last-child');
    if (repNextArrow) repNextArrow.textContent = isEn ? '▶' : '◀';
    const lbPrevArrow = document.querySelector('#userLbMonthPrevBtn > span:first-child');
    if (lbPrevArrow) lbPrevArrow.textContent = isEn ? '◀' : '▶';
    const lbNextArrow = document.querySelector('#userLbMonthNextBtn > span:last-child');
    if (lbNextArrow) lbNextArrow.textContent = isEn ? '▶' : '◀';

    if (typeof window.syncAccordionChevrons === 'function') {
      try { window.syncAccordionChevrons(); } catch (_) {}
    }
    if (typeof window.syncAllCurrencyViews === 'function') {
      try { window.syncAllCurrencyViews(); } catch (_) {}
    }

    return norm;
  }

  if (typeof window !== 'undefined') {
    window.normalizeAppLang = normalizeAppLang;
    window.getAppLanguage = getAppLanguage;
    window.isAppEn = isAppEn;
    window.trText = trText;
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
      isAppEn,
      trText,
      applyAppLocale,
      translateUiPhrase,
      t,
      I18N_EN,
    };
  }
})(typeof window !== 'undefined' ? window : globalThis);
