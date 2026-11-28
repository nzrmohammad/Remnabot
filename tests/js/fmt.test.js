/**
 * Unit tests for fmtTraffic and fmtTrafficValue helper.
 * Run with: node tests/js/fmt.test.js
 */
const assert = require('assert');
const {
  fmtTraffic,
  fmtTrafficValue,
  formatPlanTitle,
  fmtMoney,
  fmtCompact,
  parseDeviceMeta,
  syncTelegramThemeParams,
  nativeConfirm,
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
    getElementById: () => null,
    querySelector: (sel) => (sel === '#customPlanDiscountRow > span:first-child' ? partialRow : null),
    querySelectorAll: (sel) => selectorMap[sel] || [],
  };
  global.window = { getAppLanguage };
  try {
    applyAppLocale('en');
    assert.strictEqual(isAppEn(), true);
    assert.strictEqual(trText('سلام', 'Hello'), 'Hello');
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
