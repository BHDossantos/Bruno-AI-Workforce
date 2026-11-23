const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

const e = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('lib/importReceipt.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText, { exports: e });
const counts = (receipt) => Object.fromEntries(receipt.rows.map(({ label, count }) => [label, count]));

test('contact zero/duplicate response is a no-op, not a success or automatic intro', () => {
  const s = e.importReceipt('contacts', { ok: false, imported: 0, leads_added: 0, skipped: 4 });
  assert.equal(s.status, 'no-changes');
  assert.deepEqual(counts(s), { Created: 0, 'Skipped (duplicate or unusable)': 4, 'Also added as Personal leads': 0 });
  assert.doesNotMatch(s.message, /sent|intro/i);
  assert.equal(e.DESTINATIONS.contacts.href, '/crm');
});

test('uses supported counts and does not interpret queued as sent', () => {
  const s = e.importReceipt('leads', { imported: 2, updated: 3, queued: 2, sent: 0, skipped_no_contact: 5, skipped_no_email: 5 });
  assert.equal(s.status, 'confirmed');
  assert.deepEqual(counts(s), { Created: 2, 'Matched existing / updated': 3, 'Skipped (no email or phone)': 5 });
  const duplicateOnly = e.importReceipt('bnb', { imported: 0, updated: 2, skipped_no_email: 3 });
  assert.equal(duplicateOnly.status, 'confirmed');
  assert.deepEqual(counts(duplicateOnly), { Created: 0, 'Matched existing / updated': 2, 'Skipped (no email)': 3 });
  const contacts = e.importReceipt('contacts', { ok: true, imported: 1, skipped: 0, leads_added: 0 });
  assert.ok(!Object.keys(counts(contacts)).join(' ').includes('updated'));
});

test('invalid or ambiguous receipts never assume zero', () => {
  const absent = e.importReceipt('leads', null);
  assert.equal(absent.status, 'unconfirmed');
  assert.equal(absent.rows.length, 0);
  assert.equal(e.importReceipt('leads', { imported: 4 }).status, 'unconfirmed');
  assert.equal(e.importError(422, { detail: 'Malformed CSV quoting' }), 'Malformed CSV quoting');
  assert.match(e.importError(500, { detail: 'internal detail' }), /Check the destination/);
  assert.match(e.fileProblem('sheet.xml', 8), /XML is not supported/);
  assert.match(e.fileProblem('sheet.csv', 0), /empty/);
  assert.equal(e.fileProblem('CONTACTS.VCF', 8), null);
});

test('import screen handles a synthetic contact no-op with one request and a CRM link', async () => {
  let cursor = 0;
  const slots = [];
  const calls = [];
  let finish;
  const jsx = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync('app/import/page.tsx', 'utf8') + '\nexport { Importer };', {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, {
    exports: jsx,
    FormData: class { append() {} },
    fetch: (url) => { calls.push(url); return new Promise(resolve => { finish = resolve; }); },
    require(id) {
      if (id === 'react') return { useRef(value) { return slots[cursor++] ||= { current: value }; },
        useState(value) { const i = cursor++; if (!(i in slots)) slots[i] = value; return [slots[i], (next) => { slots[i] = next; }]; } };
      if (id === 'next/link') return { default: 'a' };
      if (id === '@/lib/api') return { API_URL: 'fixture', getToken: () => null };
      if (id === '@/lib/importReceipt') return e;
      if (id === '@/components/ui') return { AuthGate() {}, PageHeader() {} };
      return require(id);
    },
  });
  const render = () => { cursor = 0; return jsx.Importer(); };
  function nodes(x) { return !x || typeof x !== 'object' ? [] : [x, ...[x.props?.children].flat(Infinity).flatMap(nodes)]; }
  nodes(render()).find(x => x.type === 'select').props.onChange({ target: { value: 'contacts' } });
  nodes(render()).find(x => x.props?.id === 'import-file').props.onChange({ target: { files: [{ name: 'fixture.csv', size: 12 }] } });
  const click = nodes(render()).find(x => x.type === 'button').props.onClick;
  const first = click();
  await click();
  assert.deepEqual(calls, ['fixture/import/contacts']);
  finish({ ok: true, json: async () => ({ ok: false, imported: 0, leads_added: 0, skipped: 1 }) });
  await first;
  assert.ok(nodes(render()).some(x => x.props?.role === 'status' && x.props.children.includes('No records were created')));
  assert.ok(nodes(render()).some(x => x.props?.href === '/crm'));
});
