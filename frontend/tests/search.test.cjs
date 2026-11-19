const { test } = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const vm = require('node:vm');
const fs = require('node:fs');
function setup() {
  const slots = []; let cursor = 0; const calls = [];
  const react = { ...require('react'), useEffect() {}, useState(value) { const i=cursor++; if (!(i in slots)) slots[i]=value; return [slots[i], v => slots[i]=v]; }, useRef(value) { const i=cursor++; return slots[i] ||= {current:value}; } };
  const exports = {};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync('app/search/page.tsx','utf8')+'\nexport { Search };', {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText, {exports, require(name) { if(name==='react') return react; if(name==='next/navigation') return {useSearchParams:()=>new URLSearchParams()}; if(name==='next/link') return {default:'a'}; if(name==='@/components/ui') return {PageHeader:()=>null,AuthGate:()=>null}; if(name==='@/lib/api') return {api:{get:url=>new Promise((resolve,reject)=>calls.push({url,resolve,reject}))}}; return require(name); },URLSearchParams});
  function nodes(t) { return !t || typeof t!=='object' ? [] : [t,...[t.props?.children].flat(Infinity).flatMap(nodes)]; }
  function render() { cursor=0; return nodes(exports.Search()); }
  function run(q) { render().find(n=>n.type==='input').props.onChange({target:{value:q}}); return render().find(n=>n.type==='button').props.onClick(); }
  return {calls,run,render};
}
test('latest search wins when an earlier request fails late',async()=>{const h=setup();const first=h.run(' old ');const second=h.run('new');h.calls[1].resolve({contacts:[],memories:[]});await second;h.calls[0].reject(Error('obsolete'));await first;assert.equal(h.calls[0].url,'/search?q=old');assert.ok(h.render().some(n=>n.props?.children==='No results. Try a name, email address, or a shorter search.'));assert.ok(!h.render().some(n=>n.props?.role==='alert'));});
test('clearing search invalidates in-flight results without another request',async()=>{const h=setup();const pending=h.run('old');await h.run('   ');h.calls[0].resolve({contacts:[{id:'x',name:'Stale'}],memories:[]});await pending;assert.equal(h.calls.length,1);assert.ok(!h.render().some(n=>n.props?.children==='Stale'));});
test('failed searches expose retry and clear the error on success',async()=>{const h=setup();const p=h.run('retry');h.calls[0].reject(Error('offline'));await p;const retry=h.render().find(n=>n.type==='button'&&n.props.children==='Try again').props.onClick();h.calls[1].resolve({contacts:[],memories:[]});await retry;assert.ok(!h.render().some(n=>n.props?.role==='alert'));});
