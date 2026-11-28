/**
 * Unit tests for fmtTraffic and fmtTrafficValue helper.
 * Run with: node tests/js/fmt.test.js
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const {
  fmtTraffic,
  fmtTrafficValue,
  formatPlanTitle,
  fmtMoney,
  fmtCompact,
  escapeHtml,
  parseDeviceMeta,
  syncTelegramThemeParams,
  nativeConfirm,
  formatDisplayMoneyParts,
  getEffectiveDisplayCurrency,
  setupAccordion,
  syncAccordionChevrons,
} = require('../../bot/web/static/js/utils.js');
const {
  normalizeAppLang,
  getAppLanguage,
  isAppEn,
  trText,
  applyAppLocale,
  translateUiPhrase,
  t: i18nT,
} = require('../../bot/web/static/js/i18n.js');

const testsQueue = [];
let passCount = 0;
function test(name, fn) {
  testsQueue.push({ name, fn });
}

console.log('Testing fmtTraffic & fmtTrafficValue:');

test('null and undefined return placeholder with num-bidi', () => {
  assert.strictEqual(fmtTraffic(null), '<span class="num-bidi">-- GB</span>');
  assert.strictEqual(fmtTraffic(undefined), '<span class="num-bidi">-- GB</span>');
  assert.strictEqual(fmtTraffic(null, { html: false }), '-- GB');
});

test('0 GB returns clean 0 GB', () => {
  assert.strictEqual(fmtTraffic(0, { html: false }), '0 GB');
  assert.strictEqual(fmtTraffic(0), '<span class="num-bidi">0 GB</span>');
});

test('decimal values without trailing zero', () => {
  assert.strictEqual(fmtTraffic(0.5, { html: false }), '0.5 GB');
  assert.strictEqual(fmtTraffic(25.0, { html: false }), '25 GB');
  assert.strictEqual(fmtTraffic(25.5, { html: false }), '25.5 GB');
  assert.strictEqual(fmtTraffic(25.543, { html: false }), '25.54 GB');
});

test('1023 GB stays GB', () => {
  assert.strictEqual(fmtTraffic(1023, { html: false }), '1023 GB');
});

test('1024 GB auto-converts to 1 TB', () => {
  assert.strictEqual(fmtTraffic(1024, { html: false }), '1 TB');
});

test('1500 GB auto-converts to 1.46 TB', () => {
  assert.strictEqual(fmtTraffic(1500, { html: false }), '1.46 TB');
});

test('Pre-formatted strings are safely parsed and wrapped', () => {
  assert.strictEqual(fmtTraffic('25.50 GB', { html: false }), '25.5 GB');
  assert.strictEqual(fmtTraffic('-- GB', { html: false }), '-- GB');
  assert.strictEqual(fmtTraffic('—', { html: false }), '-- GB');
});

test('Raw bytes formatting with isBytes: true', () => {
  assert.strictEqual(fmtTraffic(1073741824, { isBytes: true, html: false }), '1 GB');
  assert.strictEqual(fmtTraffic(524288000, { isBytes: true, html: false }), '500 MB');
  assert.strictEqual(fmtTraffic(1099511627776, { isBytes: true, html: false }), '1 TB');
});

test('English digits forced even when persianDigits option passed', () => {
  assert.strictEqual(fmtTraffic(25, { persianDigits: true, html: false }), '25 GB');
});

test('Persian unit translation with English digits', () => {
  assert.strictEqual(fmtTraffic(25, { persianDigits: true, persianUnit: true, html: false }), '25 گیگابایت');
  assert.strictEqual(fmtTraffic(1024, { persianUnit: true, html: false }), '1 ترابایت');
});

test('formatPlanTitle plainText mode for canvas and charts', () => {
  assert.strictEqual(formatPlanTitle('💎 پلن ویژه', { plainText: true }), '💎 پلن ویژه');
  assert.strictEqual(formatPlanTitle('💎 پلن ویژه', { plainText: true, iconPosition: 'left' }), 'پلن ویژه 💎');
  assert.strictEqual(formatPlanTitle('🚀 توربو 2 ماهه', { plainText: true }), '🚀 توربو 2 ماهه');
  assert.strictEqual(formatPlanTitle('پلن بدون آیکون', { plainText: true }), '💎 پلن بدون آیکون');
  assert.strictEqual(formatPlanTitle('', { plainText: true }), '💎 پلن');
});

test('Unicode LRI/PDI isolation mode for canvas and tooltips', () => {
  assert.strictEqual(fmtTraffic(25, { html: false, isolate: true }), '\u206625 GB\u2069');
});

test('fmtMoney formats amounts with currency', () => {
  assert.strictEqual(fmtMoney(50000), '50,000 تومان');
  assert.strictEqual(fmtMoney(1250000), '1,250,000 تومان');
  assert.strictEqual(fmtMoney(0), '0 تومان');
  assert.strictEqual(fmtMoney(null), '0 تومان');
});

test('fmtCompact formats large numbers concisely', () => {
  assert.strictEqual(fmtCompact(500), '500');
  assert.strictEqual(fmtCompact(1000), '1K');
  assert.strictEqual(fmtCompact(15000), '15K');
  assert.strictEqual(fmtCompact(1000000), '1.0M');
  assert.strictEqual(fmtCompact(2500000), '2.5M');
});

test('fmtTrafficValue strips server-side BiDi isolation from preformatted strings', () => {
  assert.deepStrictEqual(fmtTrafficValue('\u2066500.00 MB\u2069'), { num: 500, unit: 'MB' });
  assert.deepStrictEqual(fmtTrafficValue('\u20661.50 TB\u2069'), { num: 1.5, unit: 'TB' });
});

test('parseDeviceMeta removes redundant 10.0 from Windows 10 / 11 OS labels', () => {
  assert.strictEqual(parseDeviceMeta({ platform: 'Windows 10', osVersion: '10.0' }).resolvedOs, 'Windows 10');
  assert.strictEqual(parseDeviceMeta({ platform: 'windows 10', osVersion: '10.0' }).resolvedOs, 'windows 10');
  assert.strictEqual(parseDeviceMeta({ platform: 'Windows 10', osVersion: '10.0.19045' }).resolvedOs, 'Windows 10');
  assert.strictEqual(parseDeviceMeta({ platform: 'Windows 11', osVersion: '10.0' }).resolvedOs, 'Windows 11');
  assert.strictEqual(parseDeviceMeta({ platform: 'Windows 10 10.0' }).resolvedOs, 'Windows 10');
  assert.strictEqual(parseDeviceMeta({ platform: 'Windows', osVersion: '10.0' }).resolvedOs, 'Windows 10');
  assert.strictEqual(parseDeviceMeta({ platform: 'Android', osVersion: '14' }).resolvedOs, 'Android 14');
  assert.strictEqual(parseDeviceMeta({ platform: 'iOS', osVersion: '17.5' }).resolvedOs, 'iOS 17.5');
});

test('syncTelegramThemeParams validates hex colors and viewportStableHeight', () => {
  const props = {};
  global.document = {
    documentElement: {
      style: {
        setProperty: (k, v) => { props[k] = v; },
      },
    },
  };
  try {
    syncTelegramThemeParams({
      themeParams: {
        accent_text_color: '#38bdf8',
        button_color: 'javascript:evil()',
        button_text_color: '#ffffff',
      },
      viewportStableHeight: 742.4,
    });
    assert.strictEqual(props['--tg-accent-color'], '#38bdf8');
    assert.strictEqual(props['--tg-button-color'], undefined);
    assert.strictEqual(props['--tg-button-text-color'], '#ffffff');
    assert.strictEqual(props['--tg-viewport-stable-height'], '742px');
  } finally {
    delete global.document;
  }
});

test('nativeConfirm delegates to tg.showConfirm when supported else window.confirm', async () => {
  global.window = {
    Telegram: {
      WebApp: {
        isVersionAtLeast: (v) => v === '6.2',
        showConfirm: (_msg, cb) => cb(true),
      },
    },
    confirm: () => false,
  };
  try {
    assert.strictEqual(await nativeConfirm('Proceed?'), true);
    global.window.Telegram.WebApp = null;
    assert.strictEqual(await nativeConfirm('Fallback?'), false);
  } finally {
    delete global.window;
  }
});

test('i18n runtime normalizes locale codes, translates strings, and switches RTL/LTR', () => {
  assert.strictEqual(normalizeAppLang('en-US'), 'en');
  assert.strictEqual(normalizeAppLang('fa_IR'), 'fa');
  assert.strictEqual(normalizeAppLang('fr'), 'fa');

  const navDash = { dataset: {}, textContent: 'داشبورد' };
  const store = {};
  global.localStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
  };
  global.document = {
    documentElement: { lang: 'fa', dir: 'rtl' },
    getElementById: () => null,
    querySelector: (sel) => (sel.includes('tab-dashboard') ? navDash : null),
    querySelectorAll: () => [],
  };
  global.window = { getAppLanguage };
  try {
    applyAppLocale('en');
    assert.strictEqual(document.documentElement.lang, 'en');
    assert.strictEqual(document.documentElement.dir, 'ltr');
    assert.strictEqual(navDash.textContent, 'Dashboard');
    assert.strictEqual(i18nT('traffic_alert_sub', { percent: 85 }), 'Alert before quota ends (85%)');
    assert.strictEqual(translateUiPhrase('تنظیمات با موفقیت ذخیره شد.'), 'Settings saved successfully.');
    assert.strictEqual(fmtMoney(25000), '25,000 Toman');

    applyAppLocale('fa');
    assert.strictEqual(document.documentElement.lang, 'fa');
    assert.strictEqual(document.documentElement.dir, 'rtl');
    assert.strictEqual(navDash.textContent, 'داشبورد');
    assert.strictEqual(fmtMoney(25000), '25,000 تومان');
  } finally {
    delete global.window;
    delete global.document;
    delete global.localStorage;
  }
});

test('i18n round-trip restores data-i18n* attributes and partial compound labels cleanly', () => {
  const mkEl = (attrs = {}, textContent = '', innerHTML = '') => {
    const attrMap = { ...attrs };
    return {
      dataset: {},
      textContent,
      innerHTML,
      getAttribute: (k) => (k in attrMap ? attrMap[k] : null),
      setAttribute: (k, v) => { attrMap[k] = String(v); },
    };
  };
  const textEl = mkEl({ 'data-i18n': 'settings_wallet_title' }, 'تنظیمات و ظاهر کیف پول');
  const htmlEl = mkEl({ 'data-i18n-html': 'prof_ref_note_default' }, '', 'متن فارسی');
  const phEl = mkEl({ 'data-i18n-placeholder': 'voucher_placeholder', placeholder: 'کد هدیه' });
  const titleEl = mkEl({ 'data-i18n-title': 'refresh_title', title: 'به‌روزرسانی' });
  const ariaEl = mkEl({ 'data-i18n-aria': 'nav_shop_aria', 'aria-label': 'تب فروشگاه' });
  const partialRow = {
    dataset: {},
    firstChild: { nodeType: 3, nodeValue: 'تخفیف باشگاه مشتریان (' },
    lastChild: { nodeType: 3, nodeValue: '):' },
  };
  const headerUsername = { dataset: {}, textContent: 'ali_vip' };
  const chatInput = { dir: 'rtl' };
  const store = {};
  global.localStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
  };
  const selectorMap = {
    '[data-i18n]': [textEl],
    '[data-i18n-html]': [htmlEl],
    '[data-i18n-placeholder]': [phEl],
    '[data-i18n-title]': [titleEl],
    '[data-i18n-aria]': [ariaEl],
  };
  global.document = {
    documentElement: { lang: 'fa', dir: 'rtl' },
    getElementById: (id) => (id === 'chatInput' ? chatInput : null),
    querySelector: (sel) => {
      if (sel === '#customPlanDiscountRow > span:first-child') return partialRow;
      if (sel === '#headerUsername') return headerUsername;
      return null;
    },
    querySelectorAll: (sel) => selectorMap[sel] || [],
  };
  global.window = { getAppLanguage };
  try {
    applyAppLocale('en');
    assert.strictEqual(isAppEn(), true);
    assert.strictEqual(trText('سلام', 'Hello'), 'Hello');
    assert.strictEqual(headerUsername.textContent, 'ali_vip');
    assert.strictEqual(chatInput.dir, 'ltr');
    assert.strictEqual(textEl.textContent, 'Wallet Style & Appearance');
    assert.notStrictEqual(htmlEl.innerHTML, 'متن فارسی');
    assert.strictEqual(phEl.getAttribute('placeholder'), 'Enter gift or voucher code...');
    assert.strictEqual(titleEl.getAttribute('title'), 'Refresh');
    assert.strictEqual(ariaEl.getAttribute('aria-label'), 'Shop tab');
    assert.strictEqual(partialRow.firstChild.nodeValue, 'Loyalty Club Discount (');
    assert.strictEqual(partialRow.lastChild.nodeValue, '):');

    applyAppLocale('fa');
    assert.strictEqual(isAppEn(), false);
    assert.strictEqual(trText('سلام', 'Hello'), 'سلام');
    assert.strictEqual(headerUsername.textContent, 'ali_vip');
    assert.strictEqual(chatInput.dir, 'rtl');
    assert.strictEqual(textEl.textContent, 'تنظیمات و ظاهر کیف پول');
    assert.strictEqual(htmlEl.innerHTML, 'متن فارسی');
    assert.strictEqual(phEl.getAttribute('placeholder'), 'کد هدیه');
    assert.strictEqual(titleEl.getAttribute('title'), 'به‌روزرسانی');
    assert.strictEqual(ariaEl.getAttribute('aria-label'), 'تب فروشگاه');
    assert.strictEqual(partialRow.firstChild.nodeValue, 'تخفیف باشگاه مشتریان (');
    assert.strictEqual(partialRow.lastChild.nodeValue, '):');
  } finally {
    delete global.window;
    delete global.document;
    delete global.localStorage;
  }
});

test('SSOT display currency converts Toman cleanly for EN/TON and manual currency overrides', () => {
  const store = {};
  global.localStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
  };
  global.window = {
    isAppEn: () => true,
    getAppLanguage: () => 'en',
    storeSettings: { ton_rate_toman: 500000, usdt_rate_toman: 75000, stars_rate_toman: 1500 },
  };
  try {
    assert.strictEqual(getEffectiveDisplayCurrency(), 'ton');
    const tonZero = formatDisplayMoneyParts(0);
    assert.strictEqual(tonZero.fullText, '0 TON');
    const tonPlan = formatDisplayMoneyParts(150000);
    assert.strictEqual(tonPlan.valueText, '0.3');
    assert.strictEqual(tonPlan.unit, 'TON');
    assert.strictEqual(tonPlan.fullText, '0.3 TON');
    const tonWhole = formatDisplayMoneyParts(500000);
    assert.strictEqual(tonWhole.fullText, '1 TON');

    global.window.isAppEn = () => false;
    global.window.getAppLanguage = () => 'fa';
    assert.strictEqual(getEffectiveDisplayCurrency(), 'toman');
    assert.strictEqual(formatDisplayMoneyParts(150000).valueText, '150,000');
    assert.strictEqual(formatDisplayMoneyParts(150000).unit, 'تومان');

    store.user_wallet_currency_manual = '1';
    store.user_wallet_currency = 'usdt';
    assert.strictEqual(getEffectiveDisplayCurrency(), 'usdt');
    assert.strictEqual(formatDisplayMoneyParts(150000).fullText, '2 USDT');
  } finally {
    delete global.window;
    delete global.localStorage;
  }
});

test('Accordion chevrons point right in LTR and rotate down cleanly when expanded', () => {
  const mkClassList = (initiallyHidden) => {
    const set = new Set(initiallyHidden ? ['hidden'] : []);
    return {
      contains: (c) => set.has(c),
      toggle: (c) => (set.has(c) ? set.delete(c) : set.add(c)),
    };
  };
  let clickFn = null;
  const btn = { dataset: {}, addEventListener: (_e, fn) => { clickFn = fn; } };
  const body = { classList: mkClassList(true) };
  const chevron = { textContent: '◀', style: { transform: '' } };
  global.document = {
    documentElement: { dir: 'ltr', lang: 'en' },
    getElementById: (id) => ({ testBtn: btn, testBody: body, testChev: chevron }[id] || null),
  };
  try {
    setupAccordion('testBtn', 'testBody', 'testChev');
    assert.strictEqual(chevron.textContent, '▶');
    assert.strictEqual(chevron.style.transform, 'rotate(0deg)');
    clickFn();
    assert.strictEqual(chevron.style.transform, 'rotate(90deg)');
    global.document.documentElement.dir = 'rtl';
    syncAccordionChevrons();
    assert.strictEqual(chevron.textContent, '◀');
    assert.strictEqual(chevron.style.transform, 'rotate(-90deg)');
  } finally {
    delete global.document;
  }
});

test('wallet.js getTxPurchaseInfo & renderWalletTransactions render cleanly in EN without ReferenceError', () => {
  const walletCode = fs.readFileSync(path.join(__dirname, '../../bot/web/static/js/wallet.js'), 'utf8');
  const noop = () => {};
  const listEl = { innerHTML: '', parentNode: { appendChild: noop } };
  const tabEls = {
    txFilterAll: { className: '' },
    txFilterDeposits: { className: '' },
    txFilterOrders: { className: '' },
  };
  const sandboxWindow = {
    isAppEn: () => true,
    getAppLanguage: () => 'en',
    trText: (_fa, en) => en,
    escapeHtml,
    formatDisplayMoneyParts,
    toEnglishDigits: (v) => String(v ?? ''),
    uiEmojiIcon: (e) => `[${e}]`,
    uiIcon: (n) => `[icon:${n}]`,
    lastUserData: {
      transactions: [
        { type: 'order', id: 42, title: 'Gold VIP', amount: 150000, status: 'Paid', created_at: '2026-11-28T00:00:00Z' },
      ],
    },
  };
  const sandbox = {
    window: sandboxWindow,
    document: {
      head: { appendChild: noop },
      body: { appendChild: noop },
      documentElement: { lang: 'en', dir: 'ltr' },
      getElementById: (id) => (id === 'walletTransactionsList' ? listEl : (tabEls[id] || null)),
      querySelectorAll: () => [],
      querySelector: () => null,
      createElement: () => ({
        style: {},
        dataset: {},
        classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
        appendChild: noop,
        setAttribute: noop,
        addEventListener: noop,
        querySelectorAll: () => [],
      }),
      addEventListener: noop,
    },
    localStorage: { getItem: () => null, setItem: noop },
    escapeHtml,
    toEnglishDigits: (v) => String(v ?? ''),
    uiEmojiIcon: (e) => `[${e}]`,
    uiIcon: (n) => `[icon:${n}]`,
    console,
    setTimeout,
    clearTimeout,
  };
  sandboxWindow.window = sandboxWindow;
  vm.runInNewContext(walletCode, sandbox);
  assert.strictEqual(typeof sandboxWindow.renderWalletTransactions, 'function');
  sandboxWindow.renderWalletTransactions(sandboxWindow.lastUserData.transactions);
  assert(listEl.innerHTML.includes('Gold VIP'));
  assert(listEl.innerHTML.includes('[medal-gold]'));
});

test('user.bundle.min.js boots cleanly without recursion and keeps tabs, accordions, and TON display responsive', async () => {
  const bundleCode = fs.readFileSync(path.join(__dirname, '../../bot/web/static/js/dist/user.bundle.min.js'), 'utf8');
  const noop = () => {};
  const byId = new Map();
  const evMap = new Map();
  const docEv = {};
  const mkEl = (id = '') => {
    const cls = new Set();
    const el = {
      id,
      tagName: 'DIV',
      style: {},
      dataset: {},
      value: '',
      textContent: '',
      innerText: '',
      innerHTML: '',
      children: [],
      scrollTo: noop,
      remove: noop,
      focus: noop,
      click: () => {
        const key = `${id}:click`;
        const fn = evMap.get(key) || el.onclick;
        if (fn) fn({ target: el, currentTarget: el, preventDefault: noop, stopPropagation: noop });
      },
      classList: {
        add: (...a) => a.forEach((x) => cls.add(x)),
        remove: (...a) => a.forEach((x) => cls.delete(x)),
        toggle: (x, f) => {
          if (f === true) { cls.add(x); return true; }
          if (f === false) { cls.delete(x); return false; }
          return cls.has(x) ? (cls.delete(x), false) : (cls.add(x), true);
        },
        contains: (x) => cls.has(x),
      },
      getAttribute: () => null,
      setAttribute: noop,
      removeAttribute: noop,
      addEventListener: (ev, fn) => { evMap.set(`${id}:${ev}`, fn); },
      appendChild: noop,
      querySelector: () => null,
      querySelectorAll: () => [],
      closest: () => null,
    };
    return el;
  };
  const getEl = (id) => { if (!byId.has(id)) byId.set(id, mkEl(id)); return byId.get(id); };
  const navTabs = ['tab-dashboard', 'tab-reports', 'tab-shop', 'tab-wallet', 'tab-profile'];
  const navBtns = navTabs.map((t) => {
    const b = mkEl(`nav_${t}`);
    b.getAttribute = (k) => (k === 'data-tab' ? t : null);
    return b;
  });
  const panes = navTabs.map((t) => getEl(t));
  const store = {};
  const win = {
    location: { origin: 'http://localhost', href: 'http://localhost/', search: '', pathname: '/' },
    addEventListener: noop,
    removeEventListener: noop,
    matchMedia: () => ({ matches: false, addEventListener: noop }),
    scrollTo: noop,
    Telegram: {
      WebApp: {
        ready: noop,
        expand: noop,
        initData: 'auth=1',
        initDataUnsafe: { user: { id: 123, first_name: 'Ali' } },
        BackButton: { hide: noop, show: noop, onClick: noop },
        HapticFeedback: { impactOccurred: noop, selectionChanged: noop, notificationOccurred: noop },
        MainButton: { hide: noop },
      },
    },
    navigator: { userAgent: 'Mozilla' },
  };
  const doc = {
    readyState: 'loading',
    documentElement: Object.assign(mkEl('html'), { lang: 'fa', dir: 'rtl' }),
    head: mkEl('head'),
    body: mkEl('body'),
    getElementById: getEl,
    querySelector: () => null,
    querySelectorAll: (sel) => (sel === '.nav-btn' ? navBtns : (sel === '.tab-pane' ? panes : [])),
    createElement: () => mkEl(),
    addEventListener: (e, f) => { (docEv[e] = docEv[e] || []).push(f); },
  };
  const sandbox = {
    window: win,
    document: doc,
    localStorage: {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
      removeItem: (k) => { delete store[k]; },
    },
    navigator: win.navigator,
    performance: { now: () => Date.now() },
    MutationObserver: function () { this.observe = noop; },
    getComputedStyle: () => ({}),
    FormData: function () {},
    fetch: async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        ok: true,
        data: {
          user: { id: 123, first_name: 'Ali', wallet_balance: 500000, language: 'en', referral_earned_commission: 25000 },
          referral_commission_percent: 10,
          plans: [{ id: 1, name: 'Plan 1', price: 150000, traffic_gb: 30, duration_days: 30 }],
          wallet_transactions: [{ type: 'order', id: 1, title: 'Gold VIP', amount: 150000, status: 'Paid' }],
          has_active_sub: false,
          loyalty: { enabled: true, tier_id: 'gold', icon: '🥇', total_spent: 500000, discount_percent: 5 },
        },
      }),
    }),
    console,
    setTimeout,
    clearTimeout,
    setInterval: () => 0,
    clearInterval: noop,
    URLSearchParams,
    URL,
    CustomEvent: function () {},
    Event: function () {},
  };
  win.window = win;
  win.document = doc;
  win.localStorage = sandbox.localStorage;
  const ctx = vm.createContext(sandbox);
  vm.runInContext(bundleCode, ctx, { filename: 'user.bundle.min.js' });

  let localeCalls = 0;
  let syncCurrencyCalls = 0;
  const origApply = win.applyAppLocale;
  const origSync = win.syncAllCurrencyViews;
  win.applyAppLocale = (...a) => { localeCalls++; return origApply(...a); };
  win.syncAllCurrencyViews = (...a) => { syncCurrencyCalls++; return origSync(...a); };

  getEl('subAccordionBody').classList.add('hidden');
  for (const fn of (docEv.DOMContentLoaded || [])) fn();
  await new Promise((r) => setTimeout(r, 120));

  assert(localeCalls <= 5, `Unexpected excessive applyAppLocale calls: ${localeCalls}`);
  assert(syncCurrencyCalls <= 5, `Unexpected excessive syncAllCurrencyViews calls: ${syncCurrencyCalls}`);
  navBtns[2].click();
  assert.strictEqual(getEl('tab-shop').classList.contains('hidden'), false);
  getEl('toggleSubAccordionBtn').click();
  assert.strictEqual(getEl('subChevron').style.transform, 'rotate(90deg)');
  assert.strictEqual(getEl('shopWalletBalanceAmount').innerText, '1');
  assert.strictEqual(getEl('shopWalletBalanceUnit').innerText, 'TON');
  assert.strictEqual(getEl('profileReferralCommissionTotal').innerText, '0.05');
  assert.strictEqual(getEl('profileReferralCommissionUnit').innerText, 'TON');
});

(async () => {
  for (const t of testsQueue) {
    try {
      await t.fn();
      passCount++;
      console.log(`  ✓ ${t.name}`);
    } catch (err) {
      console.error(`  ✗ ${t.name}:`, err.message);
      process.exit(1);
    }
  }
  console.log(`\nAll ${passCount} tests passed successfully!`);
})();
