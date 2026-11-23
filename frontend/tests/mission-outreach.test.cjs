const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const exportsUnderTest = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('components/MissionOutreach.tsx', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText, {
  exports: exportsUnderTest,
  require: (id) => id === 'next/link' ? { default: 'a' } : require(id),
});

const Panel = exportsUnderTest.default;
function view(props) {
  return renderToStaticMarkup(React.createElement(Panel, { onRetry() {}, ...props }));
}

const logged = {
  window: {
    today_start: '2026-11-23T00:00:00+00:00',
    seven_day_start: '2026-11-17T00:00:00+00:00',
    snapshot_at: '2026-11-23T16:09:00+00:00',
    timezone: 'UTC',
  },
  sent: { today: { email: 0, sms: 2, call: 3 }, week: { email: 7, sms: 11, call: 13 } },
  replies: { today: 1, week: 4 },
  actions: [],
  actions_count: 0,
};

test('logged zero is shown separately from unavailable, with date, window and limits', () => {
  const html = view({ data: logged, loading: false, error: null });
  assert.match(html, /Today: 2026-11-23 UTC\. Last 7 calendar days: 2026-11-17 to 2026-11-23 UTC\./);
  assert.match(html, /16:09 UTC/);
  assert.match(html, /Email records<\/dt><dd[^>]*>0<span/);
  assert.match(html, /Text records<\/dt><dd[^>]*>2<span/);
  assert.match(html, /Call records<\/dt><dd[^>]*>3<span/);
  assert.match(html, /do not show all attempts, provider acceptance, delivery or answered calls/);
  assert.match(html, /not a verified human-reply count/);
  assert.match(html, /No recent flagged records were returned/);
  assert.doesNotMatch(html, /all caught up|Outreach data unavailable/);
});

test('loading and failed data do not present zeros or a clean inbox', () => {
  const loading = view({ data: null, loading: true, error: null });
  const failed = view({ data: logged, loading: false, error: 'unavailable' });
  assert.match(loading, /Loading outreach records/);
  assert.match(failed, /Counts are unknown, not zero/);
  assert.match(failed, /Retry outreach data/);
  for (const html of [loading, failed]) assert.doesNotMatch(html, /<dd|No recent flagged records/);
});

test('flagged records link back to the thread without inventing a channel', () => {
  const html = view({ data: { ...logged, actions: [
    { name: 'Sample Lead', channel: 'unknown', status: 'Interested', snippet: 'Check thread', received_at: 'fixture', link: '/leads/42' },
  ] }, loading: false, error: null });
  assert.match(html, /Flagged for follow-up/);
  assert.match(html, /1 shown/);
  assert.match(html, /href="\/leads\/42"/);
  assert.match(html, /Channel not recorded/);
});
