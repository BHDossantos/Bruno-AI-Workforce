const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");
const source = fs.readFileSync(path.join(__dirname, "../lib/workforceControl.ts"), "utf8");
const compiled = ts.transpile(source, { module: ts.ModuleKind.CommonJS });
const exportsObject = {};
new Function("exports", compiled)(exportsObject);
const { describeWorkforceControl } = exportsObject;

test("semi and manual with outreach autopilot warn even when legacy flag says approve", () => {
  for (const mode of ["semi", "manual"]) {
    const result = describeWorkforceControl({ mode, autopilot: true, paused: false, approve_from_phone: true });
    assert.equal(result.warning, true);
    assert.match(result.text, /can send without individual approval/);
  }
});
test("full auto takes effect even when the outreach toggle is off", () => {
  assert.match(describeWorkforceControl({ mode: "auto", autopilot: false, paused: false }).text, /Full auto mode is on/);
});
test("emergency stop takes precedence without claiming prior sends were canceled", () => {
  const text = describeWorkforceControl({ mode: "auto", autopilot: true, paused: true }).text;
  assert.match(text, /Emergency Stop is on/);
  assert.match(text, /does not confirm/);
});
test("missing or corrupt settings do not imply safe behavior", () => {
  for (const state of [undefined, { mode: "unexpected", autopilot: false, paused: false }, { mode: "semi", paused: false }])
    assert.match(describeWorkforceControl(state).text, /unavailable/);
});
test("manual with both auto settings off reports settings, not delivery", () => {
  const result = describeWorkforceControl({ mode: "manual", autopilot: false, paused: false });
  assert.equal(result.warning, false);
  assert.match(result.text, /not a delivery record/);
});
