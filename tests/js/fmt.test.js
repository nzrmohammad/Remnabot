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
