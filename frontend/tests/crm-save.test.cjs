const { test } = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const vm = require('node:vm');
const fs = require('node:fs');

function setup() {
  const slots = [];
  let cursor = 0;
  const requests = [];
  const makeRequest = (method, url, body) => new Promise((resolve, reject) => requests.push({ method, url, body, resolve, reject }));
  const react = { ...require('react'), useEffect() {},
    useRef(value) { const i = cursor++; return slots[i] ||= { current: value }; },
    useState(value) {
      const i = cursor++;
      if (!(i in slots)) slots[i] = value;
      return [slots[i], v => { slots[i] = typeof v === 'function' ? v(slots[i]) : v; }];
    },
  };
  const e = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync('app/crm/page.tsx', 'utf8') + '\nexport { CRM };', {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, { exports: e, URLSearchParams, require(id) {
    if (id === 'react') return react;
    if (id === 'next/link') return { default: 'a' };
    if (id === '@/components/ui') return { PageHeader() {}, AuthGate() {} };
    if (id === '@/lib/api') return { api: { get: url => makeRequest('GET', url), post: (url, body) => makeRequest('POST', url, body) } };
    return require(id);
  } });
  function nodes(x) {
    return !x || typeof x !== 'object' ? [] : [x, ...[x.props?.children].flat(Infinity).flatMap(nodes)];
  }
  function render() { cursor = 0; return nodes(e.CRM()); }
  function button(label) {
    return render().find(n => n.type === 'button' && [n.props.children].flat(Infinity).join('').includes(label));
  }
  function setField(placeholder, value) {
    const n = render().find(n => n.type === 'input' && n.props.placeholder.startsWith(placeholder));
    n.props.onChange({ target: { value } });
  }
  return { requests, button, setField, render };
}

const saved = { id: 'contact:fixture-1', name: 'Synthetic contact', source: 'manual', link: '/crm' };

test('save uses canonical response, clears stale filters, and ignores older list responses', async () => {
  const h = setup();
  h.setField('Search', 'Old filter');
  h.button('Insurance').props.onClick();
  assert.equal(h.requests[0].url, '/crm?q=Old+filter&source=insurance');
  h.button('+ Add').props.onClick();
  h.setField('name', ' Synthetic contact ');
  const save = h.button('Save contact').props.onClick();
  assert.equal(h.requests[1].body.name, 'Synthetic contact');
  h.requests[1].resolve(saved);
  await save;
  assert.equal(h.requests[2].url, '/crm?source=manual');
  assert.equal(h.button('Added').props['aria-pressed'], true);
  assert.equal(h.render().find(n => n.props?.placeholder?.startsWith('Search')).props.value, '');
  h.requests[2].resolve([]); // A capped list can omit the new row.
  await new Promise(setImmediate);
  h.requests[0].resolve([{ ...saved, id: 'lead:stale', name: 'Stale result' }]);
  await new Promise(setImmediate);
  assert.equal(h.render().filter(n => n.type === 'td' && n.props.children === 'Synthetic contact').length, 1);
  assert.ok(!h.render().some(n => n.props?.children === 'Stale result'));
});

test('failed save keeps the form and makes uncertainty visible, without resubmitting', async () => {
  const h = setup();
  h.button('+ Add').props.onClick();
  h.setField('name', 'Synthetic contact');
  const handler = h.button('Save contact').props.onClick;
  const save = handler();
  await handler();
  assert.equal(h.requests.length, 1);
  h.requests[0].reject(Error('offline'));
  await save;
  assert.ok(h.render().some(n => n.props?.role === 'alert' && n.props.children.includes('could not confirm')));
  assert.equal(h.render().find(n => n.props?.placeholder === 'name').props.value, 'Synthetic contact');
});

test('failed list requests show retry rather than no contacts', async () => {
  const h = setup();
  h.button('Search').props.onClick();
  h.requests[0].reject(Error('offline'));
  await new Promise(setImmediate);
  assert.ok(h.button('Retry contacts'));
  assert.ok(!h.render().some(n => n.props?.children === 'No matching contacts.'));
});
