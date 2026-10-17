/**
 * Unit tests for fmtTraffic and fmtTrafficValue helper.
 * Run with: node tests/js/fmt.test.js
 */
const assert = require('assert');
const { fmtTraffic, fmtTrafficValue } = require('../../bot/web/static/js/utils.js');

let passCount = 0;
function test(name, fn) {
  try {
    fn();
    passCount++;
    console.log(`  ✓ ${name}`);
  } catch (err) {
    console.error(`  ✗ ${name}:`, err.message);
    process.exit(1);
  }
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

test('Persian digits conversion', () => {
  assert.strictEqual(fmtTraffic(25, { persianDigits: true, html: false }), '۲۵ GB');
});

test('Persian unit translation', () => {
  assert.strictEqual(fmtTraffic(25, { persianDigits: true, persianUnit: true, html: false }), '۲۵ گیگابایت');
  assert.strictEqual(fmtTraffic(1024, { persianUnit: true, html: false }), '1 ترابایت');
});

console.log(`\nAll ${passCount} tests passed successfully!`);
