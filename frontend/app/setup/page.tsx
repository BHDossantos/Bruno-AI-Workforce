"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type Area = { configured: boolean; address?: string };
type Status = {
  ai?: { configured: boolean; model: string };
  gmail_personal: Area; gmail_insurance: Area; gmail_insurance_backup?: Area;
  gmail_bnb?: Area; gmail_savorymind?: Area;
  apollo: Area; google_places: Area;
  sms?: Area & { via?: string | null }; whatsapp?: Area & { via?: string | null }; jobs_api?: Area;
  calling?: Area & { via?: string | null; browser?: boolean; recording?: boolean; callback_set?: boolean };
  instantly?: Area; smartlead?: Area; sendgrid?: Area; resend?: Area;
  meta_app?: { configured: boolean; app_id: string; redirect_uri: string };
  tiktok_app?: { configured: boolean; client_key: string; redirect_uri: string };
  booking?: { default: string; insurance: string; bnb: string; savorymind: string };
  contacts_outreach_exclude?: string;
  newsletter_banners?: { insurance: string; bnb: string; savorymind: string; music: string };
};
type MailboxHealth = {
  outbound_mode: string;
  accounts: { account: string; label: string; configured: boolean; can_send: boolean;
    method: string | null; address: string | null; reason: string | null;
    sent_today: number; daily_cap: number; remaining_today: number }[];
};
type TwoWayResult = {
  lead_id?: string; message?: string; error?: string;
  email?: { sent: boolean; status?: string; reason?: string } | null;
  sms?: { sent: boolean; reason?: string } | null;
};
type DncList = { entries: { id: string; value: string; kind: string; reason?: string | null }[] };

function Badge({ ok }: { ok: boolean }) {
  return (
    <span className={`badge ${ok ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
      {ok ? "Connected" : "Not connected"}
    </span>
  );
}

function Setup() {
  const { data, loading, error, reload } = useFetch<Status>(() => api.get<Status>("/setup"));
  const [health, setHealth] = useState<MailboxHealth | null>(null);
  const [checking, setChecking] = useState(false);
  const { data: control, reload: reloadControl } = useFetch<{ insurance_relay?: boolean }>(() => api.get<{ insurance_relay?: boolean }>("/control/status"));
  const [form, setForm] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [tw, setTw] = useState({ email: "", phone: "" });
  const [twRes, setTwRes] = useState<TwoWayResult | null>(null);
  const [twBusy, setTwBusy] = useState(false);
  const [dnc, setDnc] = useState({ email: "", phone: "" });
  const [dncMsg, setDncMsg] = useState("");
  const [dncBusy, setDncBusy] = useState(false);
  const { data: dncList, reload: reloadDnc } = useFetch<DncList>(() => api.get<DncList>("/compliance/dnc"));
  const { data: bizData, reload: reloadBiz } = useFetch<{ businesses: { key: string; label: string; on: boolean }[] }>(
    () => api.get("/control/businesses"));
  const [bizBusy, setBizBusy] = useState<string | null>(null);
  type ApRow = { enabled: boolean; connected: boolean; ready: boolean; blockers: string[]; schedule: string };
  type Autopilot = { paused: boolean; mode: string; outreach_autopilot: boolean;
    email: ApRow; sms: ApRow; call: ApRow };
  const { data: ap, reload: reloadAp } = useFetch<Autopilot>(() => api.get<Autopilot>("/control/autopilot"));
  const [apBusy, setApBusy] = useState(false);
  const armAutopilot = async () => {
    setApBusy(true);
    try { await api.post("/control/autopilot/on", {}); await reloadAp(); }
    finally { setApBusy(false); }
  };

  async function toggleBiz(key: string, on: boolean) {
    setBizBusy(key);
    try { await api.post("/control/businesses", { key, on }); reloadBiz(); }
    catch (e) { setMsg(`❌ ${e}`); }
    finally { setBizBusy(null); }
  }
  const [sipMsg, setSipMsg] = useState("");
  const [sipBusy, setSipBusy] = useState(false);

  async function testSip() {
    setSipBusy(true); setSipMsg("Testing the softswitch connection…");
    try {
      const r = await api.get<{ ok: boolean; registered?: boolean; reason?: string }>("/calls/sip/health");
      setSipMsg(`${r.ok && r.registered ? "✅" : r.ok ? "⚠️" : "❌"} ${r.reason || (r.ok ? "Connected." : "Not reachable.")}`);
    } catch (e) { setSipMsg(`❌ ${e}`); }
    finally { setSipBusy(false); }
  }

  const [callTestMsg, setCallTestMsg] = useState("");
  const [callTestBusy, setCallTestBusy] = useState(false);
  async function testCall() {
    setCallTestBusy(true); setCallTestMsg("Placing a test call to your phone…");
    try {
      const r = await api.post<{ ok: boolean; message: string }>("/calls/test", {});
      setCallTestMsg(`✅ ${r.message}`);
    } catch (e) { setCallTestMsg(`❌ ${e instanceof Error ? e.message : e}`); }
    finally { setCallTestBusy(false); }
  }

  async function addDnc() {
    const email = dnc.email.trim();
    const phone = dnc.phone.trim();
    if (!email && !phone) { setDncMsg("Enter an email or phone to suppress."); return; }
    setDncBusy(true); setDncMsg("");
    try {
      const reqs = [];
      if (email) reqs.push(api.post("/compliance/dnc", { value: email, kind: "email", reason: "opt-out request" }));
      if (phone) reqs.push(api.post("/compliance/dnc", { value: phone, kind: "phone", reason: "opt-out request" }));
      await Promise.all(reqs);
      setDncMsg("✅ Added to Do Not Contact. They're blocked on email, text, and calls immediately.");
      setDnc({ email: "", phone: "" });
      reloadDnc();
    } catch (e) { setDncMsg(`❌ ${e}`); }
    finally { setDncBusy(false); }
  }

  async function removeDnc(id: string, value: string) {
    if (!confirm(`Un-suppress ${value}? They can be contacted again.`)) return;
    setDncMsg("");
    try {
      await api.del(`/compliance/dnc/${id}`);
      setDncMsg(`✅ Removed ${value} from Do Not Contact.`);
      reloadDnc();
    } catch (e) { setDncMsg(`❌ ${e}`); }
  }

  async function runTwoWay() {
    setTwBusy(true); setTwRes(null);
    try {
      setTwRes(await api.post<TwoWayResult>("/leads/two-way-test", tw));
    } catch (e) {
      setTwRes({ error: String(e) });
    } finally { setTwBusy(false); }
  }

  async function checkMailboxes() {
    setChecking(true);
    try { setHealth(await api.get<MailboxHealth>("/setup/mailbox-health")); }
    catch (e) { setMsg(`❌ ${e}`); }
    finally { setChecking(false); }
  }

  function set(k: string, v: string) { setForm((f) => ({ ...f, [k]: v })); }

  async function toggleRelay(on: boolean) {
    try { await api.post("/control/insurance-relay", { on }); reloadControl(); }
    catch (e) { setMsg(`❌ ${e}`); }
  }

  async function save() {
    setBusy(true); setMsg("");
    try {
      const r = await api.post<{ saved: string[] }>("/setup", form);
      setMsg(r.saved.length ? `✅ Saved: ${r.saved.join(", ")}. It's live now.` : "Nothing to save — fill a field first.");
      setForm({});
      reload();
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(false); }
  }

  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;

  return (
    <div className="max-w-2xl">
      <PageHeader title="Connect Email & Data"
        subtitle="The agents need a mailbox to send outreach and read replies, and a data source for high-quality leads. Connect them here — it takes effect immediately, no redeploy." />
      {msg && <p className="mb-3 text-sm text-gray-700">{msg}</p>}

      {/* Daily Autopilot — is the machine set up to EMAIL, TEXT and CALL on its own? */}
      {ap && (
        <div className="card mb-4 border-l-4 border-brand">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🟢 Daily Autopilot</h2>
            <button className="btn text-xs" disabled={apBusy} onClick={armAutopilot}>
              {apBusy ? "Arming…" : "Arm daily autopilot"}
            </button>
          </div>
          <p className="mt-1 mb-3 text-xs text-gray-500">
            Every day the agents source leads and automatically <b>email</b>, <b>text</b> and{" "}
            <b>call</b> them — on a schedule, within the daily caps and quiet-hours rules. Each
            channel needs its automation switched on <i>and</i> a carrier/mailbox connected. This
            shows what&apos;s live and what&apos;s left. {ap.paused && (
              <b className="text-red-600">Autopilot is PAUSED — click Arm to resume.</b>
            )}
          </p>
          <div className="grid gap-2">
            {([["email", "📧 Email"], ["sms", "💬 Texting"], ["call", "📞 Calling"]] as const).map(([k, label]) => {
              const row = ap[k];
              return (
                <div key={k} className="flex items-start justify-between rounded-lg border border-gray-100 px-3 py-2">
                  <div>
                    <span className="text-sm font-medium">{label}</span>
                    <span className="ml-2 text-xs text-gray-400">{row.schedule}</span>
                    {!row.ready && row.blockers.length > 0 && (
                      <p className="mt-0.5 text-xs text-amber-600">Needs: {row.blockers.join("; ")}</p>
                    )}
                  </div>
                  <span className={`badge ${row.ready ? "bg-green-100 text-green-700"
                    : row.enabled ? "bg-amber-100 text-amber-700" : "bg-gray-100 text-gray-500"}`}>
                    {row.ready ? "Live" : row.enabled ? "Needs setup" : "Off"}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Do Not Contact — honor opt-out requests instantly (blocks email/text/calls) */}
      <div className="card mb-4 border-l-4 border-red-500">
        <h2 className="font-semibold">🚫 Do Not Contact (opt-out)</h2>
        <p className="mt-1 mb-3 text-xs text-gray-500">
          Someone asked not to be contacted? Add their email and/or phone here. The compliance
          gate blocks them on <strong>email, text, and calls</strong> immediately — no redeploy.
        </p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <input className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
            placeholder="Email (e.g. person@example.com)" value={dnc.email}
            onChange={(e) => setDnc((d) => ({ ...d, email: e.target.value }))} />
          <input className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
            placeholder="Phone (e.g. 6178772608)" value={dnc.phone}
            onChange={(e) => setDnc((d) => ({ ...d, phone: e.target.value }))} />
        </div>
        <button className="btn mt-3 bg-red-600 hover:bg-red-700" onClick={addDnc} disabled={dncBusy}>
          {dncBusy ? "Adding…" : "🚫 Add to Do Not Contact"}
        </button>
        {dncMsg && <p className="mt-2 text-sm text-gray-700">{dncMsg}</p>}
        {dncList && dncList.entries.length > 0 && (
          <div className="mt-3 border-t border-gray-100 pt-3">
            <p className="mb-1 text-xs font-medium text-gray-500">
              Suppressed ({dncList.entries.length})
            </p>
            <ul className="max-h-40 overflow-y-auto text-xs text-gray-600">
              {dncList.entries.map((d) => (
                <li key={d.id} className="flex items-center gap-2 py-0.5">
                  <span className="badge bg-red-100 text-red-700">{d.kind}</span>
                  <span className="font-mono">{d.value}</span>
                  {d.reason && <span className="text-gray-400">— {d.reason}</span>}
                  <button onClick={() => removeDnc(d.id, d.value)}
                    className="ml-auto text-gray-400 hover:text-red-600" title="Un-suppress (allow contact again)">✕</button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Businesses — turn each engine on/off */}
      <div className="card mb-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-semibold">🏢 Businesses</h2>
          {bizData && (
            <div className="flex gap-2">
              <button className="btn-ghost text-xs" disabled={!!bizBusy} onClick={() => toggleBiz("all", true)}>Turn all on</button>
              <button className="btn-ghost text-xs" disabled={!!bizBusy} onClick={() => toggleBiz("all", false)}>All off</button>
            </div>
          )}
        </div>
        <p className="mt-1 mb-3 text-xs text-gray-500">
          Each engine runs its own agents &amp; scheduled jobs when ON. Insurance is on by default;
          the rest are off to keep AI spend lean. Flip one on to test it end-to-end. Takes effect on
          the next scheduled run — no redeploy.
        </p>
        <div className="grid gap-2">
          {(bizData?.businesses || []).map((b) => (
            <label key={b.key} className="flex items-center justify-between rounded-lg border border-gray-200 px-3 py-2 text-sm">
              <span>{b.label}</span>
              <button
                className={`badge ${b.on ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}
                disabled={bizBusy === b.key || bizBusy === "all"}
                onClick={() => toggleBiz(b.key, !b.on)}>
                {bizBusy === b.key ? "…" : b.on ? "ON" : "OFF"}
              </button>
            </label>
          ))}
        </div>
      </div>

      {/* Outreach automation toggles (opt-in) */}
      <div className="card mb-4">
        <h2 className="font-semibold">⚡ Outreach automation</h2>
        <p className="mt-1 mb-3 text-xs text-gray-500">
          Optional hands-off boosters. Both are OFF until you turn them on here and hit Save.
        </p>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1"
            checked={(form.auto_reply_enabled ?? "") === "true"}
            onChange={(e) => set("auto_reply_enabled", e.target.checked ? "true" : "false")} />
          <span><strong>Auto-reply to interested leads.</strong> When a lead replies that they&apos;re
            interested, instantly send the AI reply with your booking link (instead of only drafting it).
            Only fires on clearly-interested replies; still respects opt-outs and the daily cap.</span>
        </label>
        <label className="mt-3 flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1"
            checked={(form.sms_followup_enabled ?? "") === "true"}
            onChange={(e) => set("sms_followup_enabled", e.target.checked ? "true" : "false")} />
          <span><strong>SMS follow-up to non-repliers.</strong> Text leads who were emailed but never
            replied, a couple days later. <em>Requires A2P&nbsp;10DLC registration with your texting
            provider first</em>, or carriers block the texts.</span>
        </label>
      </div>

      {/* Mailbox send diagnostic — confirm outreach can ACTUALLY go out */}
      <div className="card mb-4">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">📤 Is my email actually sending?</h2>
          <button className="btn" onClick={checkMailboxes} disabled={checking}>
            {checking ? "Checking…" : "Test sending"}
          </button>
        </div>
        {!health && <p className="mt-2 text-xs text-gray-500">Click “Test sending” to verify each mailbox can send right now (no email is sent — it just checks the login).</p>}
        {health && (
          <div className="mt-3 space-y-2">
            <div className="text-xs text-gray-400">Outbound mode: <b>{health.outbound_mode}</b></div>
            {health.accounts.map((a) => (
              <div key={a.account} className="rounded-lg border border-gray-100 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{a.label}{a.address ? ` · ${a.address}` : ""}</span>
                  <span className={`badge ${a.can_send ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                    {a.can_send ? `✅ Sending (${a.method})` : "❌ Not sending"}
                  </span>
                </div>
                {a.can_send ? (
                  <div className="mt-1 text-xs text-gray-500">Sent today {a.sent_today}/{a.daily_cap} · {a.remaining_today} left today</div>
                ) : (
                  <div className="mt-1 text-xs text-red-600">{a.reason}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Two-way test — create a CRM profile for yourself and send a real test
          email + text, then reply to confirm inbound saves back to the profile. */}
      <div className="card mb-4">
        <h2 className="font-semibold">🔁 Test two-way (email + text)</h2>
        <p className="mt-1 text-xs text-gray-500">
          Creates a CRM profile for you and sends it a real test email + text. Reply to both —
          your replies should appear on that profile. (Inbound texts also need the Twilio number&apos;s
          webhook set to <code>&lt;app&gt;/sms/inbound</code>; inbound email needs Gmail connected via OAuth.)
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <input placeholder="your email" value={tw.email}
            onChange={(e) => setTw({ ...tw, email: e.target.value })}
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <input placeholder="your cell #" value={tw.phone}
            onChange={(e) => setTw({ ...tw, phone: e.target.value })}
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <button className="btn" disabled={twBusy || (!tw.email && !tw.phone)} onClick={runTwoWay}>
            {twBusy ? "Sending…" : "Create profile & send tests"}
          </button>
        </div>
        {twRes && (
          <div className="mt-3 space-y-1 text-xs">
            {twRes.error && <div className="text-red-600">❌ {twRes.error}</div>}
            {twRes.email && (
              <div className={twRes.email.sent ? "text-green-700" : "text-red-600"}>
                📧 Email: {twRes.email.sent ? "sent — reply to it" : `not sent — ${twRes.email.reason || twRes.email.status}`}
              </div>
            )}
            {twRes.sms && (
              <div className={twRes.sms.sent ? "text-green-700" : "text-red-600"}>
                💬 Text: {twRes.sms.sent ? "sent — reply to it" : `not sent — ${twRes.sms.reason}`}
              </div>
            )}
            {twRes.lead_id && (
              <a href={`/leads/${twRes.lead_id}`} className="inline-block text-brand underline">
                Open the test profile →
              </a>
            )}
          </div>
        )}
      </div>

      <div className="space-y-4">
        {/* AI brain (OpenAI) — without this, every AI draft is stub text */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🧠 AI brain (OpenAI)</h2>
            <Badge ok={!!data.ai?.configured} />
          </div>
          <p className="mb-2 text-xs text-gray-500">
            Powers <b>every</b> AI draft — cold emails, quote-intake replies, content, newsletters,
            lead scoring. Without it the system still runs but writes clearly-marked placeholder text
            instead of real copy. Paste an <a className="underline" href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer">OpenAI API key</a> — it takes effect immediately.
          </p>
          {!data.ai?.configured && (
            <div className="mb-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-900">
              ⚠️ Not connected — AI drafts are currently placeholder text. Connect a key to turn on real generation.
            </div>
          )}
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" type="password" placeholder="OpenAI API key (sk-…)"
              value={form.openai_api_key || ""} onChange={(e) => set("openai_api_key", e.target.value)} />
            <input className="input" placeholder={data.ai?.model || "Model (default gpt-4o)"}
              value={form.openai_model || ""} onChange={(e) => set("openai_model", e.target.value)} />
          </div>
        </div>

        {/* Gmail personal */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📧 Gmail — personal mailbox</h2>
            <Badge ok={data.gmail_personal.configured} />
          </div>
          <p className="mb-2 text-xs text-gray-500">
            Used for BnB Global + SavoryMind + (relayed) insurance outreach and to read replies.
            You must use a Google <b>App Password</b> — your normal login password will be rejected
            (that&apos;s the <code>534 5.7.9 application-specific password required</code> error).
          </p>
          <div className="mb-3 rounded-lg bg-blue-50 p-3 text-xs text-blue-900">
            <b>How to get one (≈2 min):</b>
            <ol className="ml-4 mt-1 list-decimal space-y-0.5">
              <li>Turn on <a className="underline" href="https://myaccount.google.com/signinoptions/two-step-verification" target="_blank" rel="noreferrer">2-Step Verification</a> (required, or App passwords won&apos;t appear).</li>
              <li>Open <a className="underline" href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer">Google App passwords</a>, name it &quot;Bruno AI&quot;, click Create.</li>
              <li>Paste the 16-character code below (the spaces Google shows are fine — we strip them).</li>
            </ol>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder={data.gmail_personal.address || "you@gmail.com"}
              value={form.gmail_address || ""} onChange={(e) => set("gmail_address", e.target.value)} />
            <input className="input" type="password" placeholder="16-character App Password"
              value={form.gmail_app_password || ""} onChange={(e) => set("gmail_app_password", e.target.value)} />
          </div>
        </div>

        {/* Gmail insurance — PRIMARY */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🛡️ Gmail — insurance mailbox (primary)</h2>
            <Badge ok={data.gmail_insurance.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Your main insurance sending address — type <b>your own</b> address here (e.g. <code>bruno@dossantosinsurance.org</code>); the greyed-out text is only an example.
            Use a Google <b>App Password</b> generated from <b>that same account</b> (not your personal Gmail).
            Note: some Google Workspace accounts block App Passwords (the <code>535 5.7.8</code> error) — if yours does, either enable App Passwords in the Workspace Admin console, or use the toggle below to relay through your personal mailbox.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder={data.gmail_insurance.address || "you@youragency.com"}
              value={form.insurance_gmail_address || ""} onChange={(e) => set("insurance_gmail_address", e.target.value)} />
            <input className="input" type="password" placeholder="16-character App Password"
              value={form.insurance_gmail_app_password || ""} onChange={(e) => set("insurance_gmail_app_password", e.target.value)} />
          </div>
          <label className="mt-3 flex items-start gap-2 rounded-lg bg-gray-50 p-3 text-xs text-gray-600">
            <input type="checkbox" className="mt-0.5" checked={!!control?.insurance_relay}
              onChange={(e) => toggleRelay(e.target.checked)} />
            <span>
              <b>Send insurance through my personal mailbox</b> (Reply-To set to the insurance address). Use this only if you don&apos;t have a working insurance App Password — emails still go out and replies land in the insurance inbox.
              {control?.insurance_relay ? <span className="ml-1 font-medium text-green-700">ON</span> : null}
            </span>
          </label>
        </div>

        {/* Gmail insurance — BACKUP (second mailbox) */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🛡️ Gmail — insurance mailbox #2 (backup)</h2>
            <Badge ok={!!data.gmail_insurance_backup?.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            A <b>second</b> insurance sending address (e.g. a different agency domain like <code>bruno@thrustinsurance.com</code>). It&apos;s used automatically only when the primary mailbox above can&apos;t send. Leave blank if you only use one.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder={data.gmail_insurance_backup?.address || "you@second-agency.com"}
              value={form.insurance_backup_gmail_address || ""} onChange={(e) => set("insurance_backup_gmail_address", e.target.value)} />
            <input className="input" type="password" placeholder="16-character App Password"
              value={form.insurance_backup_gmail_app_password || ""} onChange={(e) => set("insurance_backup_gmail_app_password", e.target.value)} />
          </div>
        </div>

        {/* BnB Global mailbox */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">💻 Gmail — BnB Global mailbox</h2>
            <Badge ok={!!data.gmail_bnb?.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Dedicated mailbox for BnB Global consulting outreach (keeps it off your personal Gmail).
            Use a Google <b>App Password</b> (not your login password). Note: a single Gmail still has
            a low safe cold-volume limit — for real volume, route BnB through Smartlead/SendGrid.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder={data.gmail_bnb?.address || "braxandbrie@gmail.com"}
              value={form.bnb_gmail_address || ""} onChange={(e) => set("bnb_gmail_address", e.target.value)} />
            <input className="input" type="password" placeholder="16-character App Password"
              value={form.bnb_gmail_app_password || ""} onChange={(e) => set("bnb_gmail_app_password", e.target.value)} />
          </div>
        </div>

        {/* SavoryMind mailbox */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🍽️ Gmail — SavoryMind mailbox</h2>
            <Badge ok={!!data.gmail_savorymind?.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Dedicated mailbox for SavoryMind restaurant outreach. Use a Google <b>App Password</b>.
            For real volume, route SavoryMind through Smartlead/SendGrid instead of a single Gmail.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder={data.gmail_savorymind?.address || "taste@savorymindfood.com"}
              value={form.savorymind_gmail_address || ""} onChange={(e) => set("savorymind_gmail_address", e.target.value)} />
            <input className="input" type="password" placeholder="16-character App Password"
              value={form.savorymind_gmail_app_password || ""} onChange={(e) => set("savorymind_gmail_app_password", e.target.value)} />
          </div>
        </div>

        {/* Cold-email engine: Instantly / Smartlead */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🚀 Cold-email engine (Instantly / Smartlead)</h2>
            <Badge ok={!!(data.instantly?.configured || data.smartlead?.configured)} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            The durable way to send cold outreach at volume — many warmed inboxes + deliverability,
            instead of a personal Gmail (which Google revokes at volume). Connect EITHER: paste the
            API key + the campaign ID to send into. The app hands every lead to that campaign and
            passes our AI-written copy as <code>{`{{personalization}}`}</code> — set your campaign&apos;s
            email step to use it. When connected, this replaces Gmail sending automatically.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" type="password" placeholder="Instantly API key"
              value={form.instantly_api_key || ""} onChange={(e) => set("instantly_api_key", e.target.value)} />
            <input className="input" placeholder="Instantly campaign ID"
              value={form.instantly_campaign_id || ""} onChange={(e) => set("instantly_campaign_id", e.target.value)} />
            <input className="input" type="password" placeholder="Smartlead API key"
              value={form.smartlead_api_key || ""} onChange={(e) => set("smartlead_api_key", e.target.value)} />
            <input className="input" placeholder="Smartlead campaign ID"
              value={form.smartlead_campaign_id || ""} onChange={(e) => set("smartlead_campaign_id", e.target.value)} />
          </div>
        </div>

        {/* Resend — preferred modern email delivery */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">✉️ Resend (recommended email delivery)</h2>
            <Badge ok={!!data.resend?.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Modern email API with excellent deliverability on your own domain — <b>preferred over
            SendGrid/Gmail</b> when connected. From resend.com: create an <b>API key</b>, then add
            &amp; verify your domain (Resend → Domains → add the DNS records it shows) so you can send
            AS <code>b@dossantosinsurance.org</code>. Set a <b>reply-to</b> inbox you actually read so
            replies reach you.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" type="password" placeholder="Resend API key (re_…)"
              value={form.resend_api_key || ""} onChange={(e) => set("resend_api_key", e.target.value)} />
            <input className="input" placeholder="From (verified domain, e.g. b@dossantosinsurance.org)"
              value={form.resend_from_insurance || ""} onChange={(e) => set("resend_from_insurance", e.target.value)} />
            <input className="input" placeholder="Reply-to inbox (where replies land)"
              value={form.resend_reply_to || ""} onChange={(e) => set("resend_reply_to", e.target.value)} />
            <input className="input" type="password" placeholder="Webhook signing secret (whsec_… — optional)"
              value={form.resend_webhook_secret || ""} onChange={(e) => set("resend_webhook_secret", e.target.value)} />
          </div>
          <p className="mt-2 text-xs text-gray-500">
            <b>Two-way email (auto-save replies to the CRM):</b> in Resend → <b>Webhooks</b>, add an
            endpoint pointing at <code>{`{API}/resend/inbound`}</code> and select the delivery events
            (delivered / bounced / complained); to also capture inbound replies, enable inbound
            receiving on your domain and point it at the same URL. Paste the webhook’s{" "}
            <b>signing secret</b> above to verify posts (optional but recommended). Replies then land
            on the contact’s profile automatically, with an AI-drafted response ready to send.
          </p>
        </div>

        {/* SendGrid — reliable delivery */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📨 SendGrid (reliable email delivery)</h2>
            <Badge ok={!!data.sendgrid?.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Sends your outreach through SendGrid instead of Gmail (which Google revokes at volume) —
            you keep all your copy, sequences and automation. Paste your <b>API key</b> and a{" "}
            <b>verified sender</b> email (verify it first in SendGrid → Sender Authentication; full
            domain auth with SPF/DKIM gives the best inbox placement). When connected, outreach
            sends via SendGrid automatically at a higher daily cap.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" type="password" placeholder="SendGrid API key"
              value={form.sendgrid_api_key || ""} onChange={(e) => set("sendgrid_api_key", e.target.value)} />
            <input className="input" placeholder="Default verified sender (from)"
              value={form.sendgrid_from_email || ""} onChange={(e) => set("sendgrid_from_email", e.target.value)} />
          </div>
          <div className="mt-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Verified sender per business</div>
          <div className="mt-1 grid gap-2 sm:grid-cols-3">
            <input className="input" placeholder="Insurance from"
              value={form.sendgrid_from_insurance || ""} onChange={(e) => set("sendgrid_from_insurance", e.target.value)} />
            <input className="input" placeholder="BnB Global from"
              value={form.sendgrid_from_bnb || ""} onChange={(e) => set("sendgrid_from_bnb", e.target.value)} />
            <input className="input" placeholder="SavoryMind from"
              value={form.sendgrid_from_savorymind || ""} onChange={(e) => set("sendgrid_from_savorymind", e.target.value)} />
          </div>
          <div className="mt-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Reply-To per business (optional — where replies land)</div>
          <div className="mt-1 grid gap-2 sm:grid-cols-3">
            <input className="input" placeholder="Insurance reply-to"
              value={form.sendgrid_replyto_insurance || ""} onChange={(e) => set("sendgrid_replyto_insurance", e.target.value)} />
            <input className="input" placeholder="BnB reply-to"
              value={form.sendgrid_replyto_bnb || ""} onChange={(e) => set("sendgrid_replyto_bnb", e.target.value)} />
            <input className="input" placeholder="SavoryMind reply-to"
              value={form.sendgrid_replyto_savorymind || ""} onChange={(e) => set("sendgrid_replyto_savorymind", e.target.value)} />
          </div>
        </div>

        {/* Meta app — powers the one-click Facebook/Instagram connect button */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📘 Facebook / Instagram app (one-click connect)</h2>
            <Badge ok={!!data.meta_app?.configured} />
          </div>
          <p className="mb-2 text-xs text-gray-500">
            Enables the <b>&ldquo;Connect with Facebook/Instagram&rdquo;</b> button on the Connections
            page — one click instead of pasting tokens, with a long-lived token that auto-refreshes
            (no more surprise disconnects). From your Meta app (developers.facebook.com): App ID,
            App Secret, and add the redirect URI below as a <b>Valid OAuth Redirect URI</b>.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder={data.meta_app?.app_id || "Facebook App ID"}
              value={form.facebook_app_id || ""} onChange={(e) => set("facebook_app_id", e.target.value)} />
            <input className="input" type="password" placeholder="Facebook App Secret"
              value={form.facebook_app_secret || ""} onChange={(e) => set("facebook_app_secret", e.target.value)} />
            <input className="input sm:col-span-2" placeholder={data.meta_app?.redirect_uri || "Redirect URI — https://<backend>/connections/meta/oauth/callback"}
              value={form.meta_redirect_uri || ""} onChange={(e) => set("meta_redirect_uri", e.target.value)} />
          </div>
        </div>

        {/* TikTok app — powers the one-click Connect with TikTok button */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🎵 TikTok app (one-click connect)</h2>
            <Badge ok={!!data.tiktok_app?.configured} />
          </div>
          <p className="mb-2 text-xs text-gray-500">
            Enables the <b>&ldquo;Connect with TikTok&rdquo;</b> button on the Connections page. From your
            TikTok app (developers.tiktok.com): Client Key, Client Secret, and add the redirect URI below
            as a registered redirect URI. Note: until TikTok audits your app, posts publish as private
            (SELF_ONLY) — that&apos;s a TikTok review step, not a setting.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder={data.tiktok_app?.client_key || "TikTok Client Key"}
              value={form.tiktok_client_key || ""} onChange={(e) => set("tiktok_client_key", e.target.value)} />
            <input className="input" type="password" placeholder="TikTok Client Secret"
              value={form.tiktok_client_secret || ""} onChange={(e) => set("tiktok_client_secret", e.target.value)} />
            <input className="input sm:col-span-2" placeholder={data.tiktok_app?.redirect_uri || "Redirect URI — https://<backend>/connections/tiktok/oauth/callback"}
              value={form.tiktok_redirect_uri || ""} onChange={(e) => set("tiktok_redirect_uri", e.target.value)} />
          </div>
        </div>

        {/* Booking links — turn an interested reply into a booked call */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📅 Booking links (Calendly / Cal.com)</h2>
            <Badge ok={!!(data.booking && (data.booking.default || data.booking.insurance || data.booking.bnb || data.booking.savorymind))} />
          </div>
          <p className="mb-2 text-xs text-gray-500">
            Paste a scheduling link and a <b>&ldquo;Book a time&rdquo;</b> button is added to every outreach
            email and AI-drafted reply — so an interested prospect books a call instead of trading emails.
            Set a link per business; the default is used for anything without its own.
          </p>
          <input className="input w-full" placeholder={data.booking?.default || "Default booking link (https://calendly.com/…)"}
            value={form.calendar_link || ""} onChange={(e) => set("calendar_link", e.target.value)} />
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            <input className="input" placeholder={data.booking?.insurance || "Insurance booking link"}
              value={form.calendar_link_insurance || ""} onChange={(e) => set("calendar_link_insurance", e.target.value)} />
            <input className="input" placeholder={data.booking?.bnb || "BnB Global booking link"}
              value={form.calendar_link_bnb || ""} onChange={(e) => set("calendar_link_bnb", e.target.value)} />
            <input className="input" placeholder={data.booking?.savorymind || "SavoryMind booking link"}
              value={form.calendar_link_savorymind || ""} onChange={(e) => set("calendar_link_savorymind", e.target.value)} />
          </div>
        </div>

        {/* Newsletter banner photos — a nice default gradient is used if left blank */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🖼️ Newsletter banner photos</h2>
          </div>
          <p className="mb-2 text-xs text-gray-500">
            Every newsletter is already designed (banner, card layout, CTA button) — this just lets you
            swap the default color banner for a real photo per business. Paste a hosted image URL
            (e.g. from your website); leave blank to keep the designed gradient banner.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder={data.newsletter_banners?.insurance || "Insurance banner image URL"}
              value={form.newsletter_banner_insurance || ""} onChange={(e) => set("newsletter_banner_insurance", e.target.value)} />
            <input className="input" placeholder={data.newsletter_banners?.bnb || "BnB Global banner image URL"}
              value={form.newsletter_banner_bnb || ""} onChange={(e) => set("newsletter_banner_bnb", e.target.value)} />
            <input className="input" placeholder={data.newsletter_banners?.savorymind || "SavoryMind banner image URL"}
              value={form.newsletter_banner_savorymind || ""} onChange={(e) => set("newsletter_banner_savorymind", e.target.value)} />
            <input className="input" placeholder={data.newsletter_banners?.music || "Music banner image URL"}
              value={form.newsletter_banner_music || ""} onChange={(e) => set("newsletter_banner_music", e.target.value)} />
          </div>
        </div>

        {/* Imported-contacts warm outreach — who to never auto-email */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🚫 Never auto-email these (imported contacts)</h2>
          </div>
          <p className="mb-2 text-xs text-gray-500">
            When you import a personal contact list, every address on it EXCEPT these gets one warm
            &ldquo;free insurance review&rdquo; intro. Add family, close friends, and anyone who
            shouldn&apos;t get an automated email — comma-separated. This REPLACES the current list
            when saved, so include everyone you want excluded, not just new additions.
          </p>
          <textarea className="input w-full" rows={2}
            placeholder={data.contacts_outreach_exclude || "family@example.com, friend@example.com, …"}
            value={form.contacts_outreach_exclude ?? ""}
            onChange={(e) => set("contacts_outreach_exclude", e.target.value)} />
          {data.contacts_outreach_exclude && (
            <p className="mt-1 text-xs text-gray-400">Currently excluded: {data.contacts_outreach_exclude}</p>
          )}
        </div>

        {/* Apollo */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🚀 Apollo API key (high-volume B2B leads)</h2>
            <Badge ok={data.apollo.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Best source for BnB Global + commercial insurance volume: real companies with verified emails and firmographics.
            Get a key at apollo.io → Settings → API.
          </p>
          <input className="input w-full" type="password" placeholder="Apollo API key"
            value={form.apollo_api_key || ""} onChange={(e) => set("apollo_api_key", e.target.value)} />
        </div>

        {/* Google Places */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📍 Google Places API key (local businesses)</h2>
            <Badge ok={data.google_places.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Adds real local businesses with contact data (free $200/mo credit). Google Cloud Console → enable Places API → create a key.
          </p>
          <input className="input w-full" type="password" placeholder="Google Places API key"
            value={form.google_places_api_key || ""} onChange={(e) => set("google_places_api_key", e.target.value)} />
        </div>

        {/* Carrier routing — texting and calling choose their carrier INDEPENDENTLY */}
        <div className="card border-l-4 border-brand">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📶 Carrier routing (texting vs calling)</h2>
            <span className="text-xs text-gray-500">
              texts via <b>{data.sms?.via || "—"}</b> · calls via <b>{data.calling?.via || "—"}</b>
            </span>
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Texting and calling pick their carrier <b>separately</b> — so you can keep <b>texting on
            Twilio</b> (already A2P-registered and working) while <b>calling goes through SignalWire</b>
            {" "}(if Twilio blocked your outbound calls). <b>Auto</b> uses SignalWire when it&apos;s
            connected, otherwise Twilio. Fill in each carrier&apos;s credentials in the cards below.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-xs font-medium text-gray-600">
              Texting (SMS) carrier
              <select className="input mt-1" value={form.sms_provider || "auto"}
                onChange={(e) => set("sms_provider", e.target.value)}>
                <option value="auto">Auto (prefer SignalWire, else Twilio)</option>
                <option value="twilio">Twilio</option>
                <option value="signalwire">SignalWire</option>
                <option value="plivo">Plivo</option>
              </select>
            </label>
            <label className="text-xs font-medium text-gray-600">
              Calling (Voice) carrier
              <select className="input mt-1" value={form.voice_provider || "auto"}
                onChange={(e) => set("voice_provider", e.target.value)}>
                <option value="auto">Auto (prefer SignalWire, else Twilio)</option>
                <option value="signalwire">SignalWire</option>
                <option value="twilio">Twilio</option>
                <option value="plivo">Plivo</option>
                <option value="vonage">Vonage</option>
                <option value="sip">Self-hosted SIP</option>
              </select>
            </label>
          </div>
        </div>

        {/* Twilio (SMS) */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">💬 Twilio (two-way SMS / texting)</h2>
            <Badge ok={!!data.sms?.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Powers the Texts page. From twilio.com → Console: Account SID, Auth Token, and your Twilio phone number (E.164, e.g. +16175551234). The insurance number is optional — leave it blank to text from the main number.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" type="password" placeholder="Account SID"
              value={form.twilio_account_sid || ""} onChange={(e) => set("twilio_account_sid", e.target.value)} />
            <input className="input" type="password" placeholder="Auth Token"
              value={form.twilio_auth_token || ""} onChange={(e) => set("twilio_auth_token", e.target.value)} />
            <input className="input" placeholder="Main number +1 555 123 4567"
              value={form.twilio_from_number || ""} onChange={(e) => set("twilio_from_number", e.target.value)} />
            <input className="input" placeholder="Insurance number (optional)"
              value={form.twilio_insurance_number || ""} onChange={(e) => set("twilio_insurance_number", e.target.value)} />
          </div>
        </div>

        {/* Plivo — voice + SMS provider (Twilio alternative) */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🔁 Plivo (voice + SMS)</h2>
            <Badge ok={data.sms?.via === "plivo" || data.calling?.via === "plivo"} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            A full Twilio/SignalWire alternative that powers <b>both calling and texting</b> —
            useful when another carrier&apos;s number is being filtered to voicemail. From plivo.com →
            Console: <b>Auth ID</b>, <b>Auth Token</b>, and a <b>Voice + SMS</b> number (E.164). Once
            connected it&apos;s used automatically for calls (auto-dial, voicemail drop, transfer) and
            texts. For inbound replies point your Plivo app&apos;s <b>Message URL</b> at{" "}
            <code>&lt;app&gt;/sms/plivo-inbound</code>. New number → register at{" "}
            <b>freecallerregistry.com</b> so it isn&apos;t flagged.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder="Plivo number +1 555 123 4567 (Voice + SMS)"
              value={form.plivo_from_number || ""} onChange={(e) => set("plivo_from_number", e.target.value)} />
            <input className="input" type="password" placeholder="Plivo Auth ID"
              value={form.plivo_auth_id || ""} onChange={(e) => set("plivo_auth_id", e.target.value)} />
            <input className="input" type="password" placeholder="Plivo Auth Token"
              value={form.plivo_auth_token || ""} onChange={(e) => set("plivo_auth_token", e.target.value)} />
          </div>
        </div>

        {/* Vonage (Nexmo) — third voice provider */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📞 Vonage (voice provider)</h2>
            <Badge ok={data.calling?.via === "vonage"} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Another carrier for calling. In the Vonage dashboard: create a <b>Voice application</b>,
            link a <b>number</b>, and copy the <b>Application ID</b> + download the{" "}
            <b>private.key</b> (paste the whole PEM). Set <b>Voice provider</b> to <code>vonage</code>
            {" "}(or leave <code>auto</code>) to route calls here. New number → register at{" "}
            <b>freecallerregistry.com</b> so it isn&apos;t filtered.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder="Vonage number +1 555 123 4567"
              value={form.vonage_from_number || ""} onChange={(e) => set("vonage_from_number", e.target.value)} />
            <input className="input" placeholder="Vonage Application ID"
              value={form.vonage_application_id || ""} onChange={(e) => set("vonage_application_id", e.target.value)} />
            <textarea className="input sm:col-span-2" rows={3} placeholder="Vonage private key (paste the full -----BEGIN PRIVATE KEY----- … PEM)"
              value={form.vonage_private_key || ""} onChange={(e) => set("vonage_private_key", e.target.value)} />
          </div>
        </div>

        {/* Self-hosted SIP softswitch — our own FreeSWITCH + BYOC trunk */}
        <div className="card border-l-4 border-brand">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🛠️ Our own softswitch (self-hosted SIP)</h2>
            <Badge ok={data.calling?.via === "sip"} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Run our <b>own</b> FreeSWITCH server + a <b>bring-your-own-carrier SIP trunk</b> —
            full control, lowest per-minute cost, no provider account to get shut off. Stand up
            the server first: see <code>deploy/softswitch/README.md</code>. Then set{" "}
            <b>Voice provider</b> to <code>sip</code> and fill these in.{" "}
            <b>Heads-up:</b> a brand-new trunk number is still filtered to voicemail until you
            register it at <b>freecallerregistry.com</b> and pick an A-attestation carrier — the
            softswitch controls the call, not the carrier&apos;s reputation.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder="ESL host (server's private IP)"
              value={form.sip_esl_host || ""} onChange={(e) => set("sip_esl_host", e.target.value)} />
            <input className="input" placeholder="ESL port (default 8021)"
              value={form.sip_esl_port || ""} onChange={(e) => set("sip_esl_port", e.target.value)} />
            <input className="input" type="password" placeholder="ESL password (from event_socket.conf)"
              value={form.sip_esl_password || ""} onChange={(e) => set("sip_esl_password", e.target.value)} />
            <input className="input" placeholder="Gateway name (bruno_trunk)"
              value={form.sip_gateway || ""} onChange={(e) => set("sip_gateway", e.target.value)} />
            <input className="input sm:col-span-2" placeholder="Caller-ID / trunk number +1 978 679 8009"
              value={form.sip_from_number || ""} onChange={(e) => set("sip_from_number", e.target.value)} />
          </div>
          <div className="mt-3 flex items-center gap-3">
            <button type="button" className="btn-ghost" onClick={testSip} disabled={sipBusy}>
              {sipBusy ? "Testing…" : "Test connection"}
            </button>
            <span className="text-xs text-gray-500">Save first, then test — checks the app can reach FreeSWITCH and the trunk is registered.</span>
          </div>
          {sipMsg && <p className="mt-2 text-sm text-gray-700">{sipMsg}</p>}
        </div>

        {/* SignalWire — Twilio-compatible carrier (drop-in) for BOTH voice + SMS */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📡 SignalWire (voice + SMS — Twilio replacement)</h2>
            <Badge ok={!!data.calling?.configured || data.sms?.via === "signalwire"} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            A drop-in Twilio replacement that powers <b>both calling and texting</b> with your
            existing voicemail-drop / transfer logic. From your SignalWire Space → <b>API</b>:
            the <b>Space URL</b>, a <b>Project ID</b>, and an <b>API token</b> (starts with
            <code>PT…</code>); buy at least one SMS+Voice <b>number</b> in the Space. When connected
            it&apos;s used automatically for voice + SMS. Point your number&apos;s webhooks at{" "}
            <code>&lt;app&gt;/sms/inbound</code> (SMS) and the call TwiML at <code>&lt;app&gt;/calls/…</code>.
            <b> SMS also needs A2P 10DLC registration in SignalWire</b> before high-volume texting;
            voice/calling has no such gate and works immediately.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder="Space URL (e.g. yourname.signalwire.com)"
              value={form.signalwire_space_url || ""} onChange={(e) => set("signalwire_space_url", e.target.value)} />
            <input className="input" placeholder="Project ID (UUID)"
              value={form.signalwire_project_id || ""} onChange={(e) => set("signalwire_project_id", e.target.value)} />
            <input className="input" type="password" placeholder="API token (PT…)"
              value={form.signalwire_api_token || ""} onChange={(e) => set("signalwire_api_token", e.target.value)} />
            <input className="input" placeholder="Number +1 978 824 4228 (SMS + Voice)"
              value={form.signalwire_from_number || ""} onChange={(e) => set("signalwire_from_number", e.target.value)} />
          </div>
        </div>

        {/* Calling — Twilio Voice (bridge + browser softphone) */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📞 Calling (Twilio Voice)</h2>
            <Badge ok={!!data.calling?.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Click “Call” on a lead → Twilio rings <b>your phone</b>, then connects the lead (recorded, with a consent notice; AI notes post to the timeline). Uses your Twilio account above. Enter <b>your cell</b> as the callback number. For browser calling (when your phone’s dead), add a Twilio <b>API Key</b> (SID + Secret) and a <b>TwiML App SID</b> whose Voice URL is <code>…/calls/twiml/outbound</code>.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder="Your cell to ring +1 617 555 1234"
              value={form.producer_callback || ""} onChange={(e) => set("producer_callback", e.target.value)} />
            <input className="input" placeholder="Caller-ID / Voice number (optional)"
              value={form.twilio_voice_number || ""} onChange={(e) => set("twilio_voice_number", e.target.value)} />
            <input className="input" placeholder="API Key SID (browser calling)"
              value={form.twilio_api_key_sid || ""} onChange={(e) => set("twilio_api_key_sid", e.target.value)} />
            <input className="input" type="password" placeholder="API Key Secret (browser calling)"
              value={form.twilio_api_key_secret || ""} onChange={(e) => set("twilio_api_key_secret", e.target.value)} />
            <input className="input" placeholder="TwiML App SID (browser calling)"
              value={form.twilio_twiml_app_sid || ""} onChange={(e) => set("twilio_twiml_app_sid", e.target.value)} />
          </div>
          <div className="mt-3 flex items-center gap-3">
            <button type="button" className="btn" onClick={testCall} disabled={callTestBusy}>
              {callTestBusy ? "Calling…" : "📞 Test call to my phone"}
            </button>
            <span className="text-xs text-gray-500">Save first, then tap — your phone should ring within seconds. Proves your carrier + caller-ID + cell all work.</span>
          </div>
          {callTestMsg && <p className="mt-2 text-sm text-gray-700">{callTestMsg}</p>}
        </div>

        {/* WhatsApp — Meta Cloud API (preferred, no Twilio) or Twilio WhatsApp */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📲 WhatsApp</h2>
            <Badge ok={!!data.whatsapp?.configured} />
          </div>
          {data.whatsapp?.configured && (
            <p className="mb-2 text-xs text-emerald-700">
              Active via {data.whatsapp.via === "meta_cloud" ? "Meta's Cloud API (no Twilio)" : "Twilio"}.
            </p>
          )}
          <p className="mb-3 text-xs text-gray-500">
            A legitimate, official channel for messaging clients — unlike consumer-WhatsApp
            automation, which risks account bans. If both are filled in, Meta&apos;s Cloud API is
            used (no reseller markup).
          </p>
          <div className="mb-3 rounded-lg border border-gray-100 p-3">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Meta Cloud API (recommended — no Twilio)
            </div>
            <p className="mb-2 text-xs text-gray-500">
              Reuses your Facebook Developer app: add the <b>WhatsApp</b> product, verify a phone
              number, then copy its Phone Number ID and a permanent access token from Business Settings.
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              <input className="input" placeholder="Phone Number ID"
                value={form.whatsapp_cloud_phone_number_id || ""} onChange={(e) => set("whatsapp_cloud_phone_number_id", e.target.value)} />
              <input className="input" type="password" placeholder="Access token"
                value={form.whatsapp_cloud_token || ""} onChange={(e) => set("whatsapp_cloud_token", e.target.value)} />
            </div>
          </div>
          <div className="rounded-lg border border-gray-100 p-3">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Twilio WhatsApp (fallback)
            </div>
            <p className="mb-2 text-xs text-gray-500">
              Uses the Twilio account above. From twilio.com → Messaging → Try WhatsApp: sandbox
              number to test, or an approved WhatsApp Sender for production.
            </p>
            <input className="input w-full" placeholder="WhatsApp number, e.g. +14155238886"
              value={form.twilio_whatsapp_number || ""} onChange={(e) => set("twilio_whatsapp_number", e.target.value)} />
          </div>
        </div>

        {/* Jobs API (JSearch) */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">💼 Jobs API key (LinkedIn / Indeed / Glassdoor)</h2>
            <Badge ok={!!data.jobs_api?.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Live roles from the top job boards via JSearch. Get a free key at rapidapi.com → JSearch → subscribe → copy the X-RapidAPI-Key. Without it, only free remote boards are searched.
          </p>
          <input className="input w-full" type="password" placeholder="JSearch / RapidAPI key"
            value={form.jobs_api_key || ""} onChange={(e) => set("jobs_api_key", e.target.value)} />
        </div>

        <button className="btn" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save & connect"}</button>
        <p className="text-xs text-gray-400">
          Stored securely server-side and never shown again. After connecting Gmail, the Lead Pipeline Health panel
          on the Insurance/BnB pages will turn green and outreach will start flowing.
        </p>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Setup /></AuthGate>;
}
