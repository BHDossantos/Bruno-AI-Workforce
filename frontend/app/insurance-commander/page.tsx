"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type Tiles = {
  todays_leads: number; need_immediate_response: number; engaged_waiting_on_quote: number;
  need_follow_up_today: number; policies_bound_today: number; commission_today: number;
};
type Speed = {
  measured: number; avg_seconds: number | null; best_seconds: number | null;
  worst_seconds: number | null; target_seconds: number; over_target: boolean;
};
type Lifecycle = { stage_moves_today: number; speed_breaches: number; return_eligible: number };
type ReturnLead = { lead_id: string; name: string; email: string | null; phone: string | null;
  line: string; days_since_touch: number | null; angle: string };
type EqReturn = { lead_id: string; name: string; email: string | null; phone: string | null;
  state: string; vehicle: string; reason_code: string; reason_text: string };
type AskLead = { lead_id: string; name: string; email: string | null; phone: string | null;
  stage: string; reason: string };
type AskResult = { ok: boolean; intent: string; title: string; answer: string;
  leads: AskLead[]; count: number };
type Overview = { tiles: Tiles; speed: Speed; pipeline: { stage: string; count: number }[];
  commission_rate: number; lifecycle?: Lifecycle };

type TimelineEvent = { at: string | null; kind: string; label: string; detail?: string | null; status?: string };
type Timeline = {
  ok: boolean;
  lead?: { id: string; name: string; email: string | null; phone: string | null; source: string | null;
    status: string; stage: string; temperature: string; score: number | null; band?: string;
    times_contacted: number; received_at: string | null };
  timeline?: TimelineEvent[];
};
type Objection = { ok: boolean; objection: string; confidence: string; rebuttal: string;
  tailored: string | null; move: string; ai_used: boolean };
type Outreach = {
  ok: boolean; name: string; vehicle: string;
  email: { subject: string; body: string; tailored: string | null };
  sms: { body: string; tailored: string | null };
  voicemail: string; call_notes: string[];
};
type Coach = {
  ok: boolean; line: string; coverages: string; score: number; band: string;
  score_reasons: string[]; temperature: string; stage: string;
  history: { outbound_touches: number; last_touch: string | null; replied: boolean };
  goal: string; ask_next: string; opener: string; opener_tailored: string | null;
  likely_objections: { objection: string; rebuttal: string; move: string }[];
  lead: { phone: string | null };
};
type Estimate = { monthly_low: number; monthly_high: number; annual_low: number; annual_high: number; note: string };
type Quote = {
  ok: boolean; line: string; state: string | null; coverages: string; carriers: string[];
  estimate: Estimate; quote_type_label: string | null;
  intake: { collected: number; total: number; complete: boolean; missing: string[] };
  ready_to_send: boolean; summary: string; marked_sent?: boolean;
};

function money(n: number) { return n >= 1000 ? `$${(n / 1000).toFixed(1)}k` : `$${n.toFixed(0)}`; }
function secs(n: number | null) { return n == null ? "—" : n < 60 ? `${n}s` : `${Math.floor(n / 60)}m ${n % 60}s`; }

function Tile({ label, value, tone }: { label: string; value: React.ReactNode; tone?: "red" | "amber" | "green" }) {
  const color = tone === "red" ? "text-red-600" : tone === "amber" ? "text-amber-600" : tone === "green" ? "text-emerald-600" : "text-brand";
  return (
    <div className="card">
      <div className="text-xs uppercase tracking-wide text-gray-400">{label}</div>
      <div className={`mt-1 text-3xl font-bold ${color}`}>{value}</div>
    </div>
  );
}

function InsuranceCommander() {
  const { data, loading, error, reload } = useFetch<Overview>(() => api.get<Overview>("/mission/insurance-commander"));
  const { data: returns, reload: reloadReturns } = useFetch<ReturnLead[]>(() => api.get<ReturnLead[]>("/mission/return-queue"));
  const { data: eqReturns } = useFetch<EqReturn[]>(() => api.get<EqReturn[]>("/leads/everquote/return-candidates"));
  const [leadId, setLeadId] = useState("");
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [tlErr, setTlErr] = useState("");
  const [running, setRunning] = useState(false);
  const [runMsg, setRunMsg] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoteBusy, setQuoteBusy] = useState(false);
  const [coach, setCoach] = useState<Coach | null>(null);
  const [coachBusy, setCoachBusy] = useState(false);
  const [outreach, setOutreach] = useState<Outreach | null>(null);
  const [outreachBusy, setOutreachBusy] = useState(false);
  const [outreachMsg, setOutreachMsg] = useState("");
  const [importCsv, setImportCsv] = useState("");
  const [importMsg, setImportMsg] = useState("");
  const [importBusy, setImportBusy] = useState(false);

  async function loadOutreach(id: string) {
    setOutreach(null); setOutreachMsg(""); setOutreachBusy(true);
    try { setOutreach(await api.get<Outreach>(`/leads/${id}/personalized-outreach`)); }
    catch (e) { setOutreachMsg(String(e)); }
    finally { setOutreachBusy(false); }
  }
  async function queueOutreach(id: string) {
    setOutreachBusy(true);
    try {
      const q = await api.post<{ subject: string; status: string }>(`/leads/${id}/personalized-outreach/queue`, {});
      setOutreachMsg(`Queued as ${q.status}: "${q.subject}" — review it in the approvals queue.`);
    } catch (e) { setOutreachMsg(String(e)); }
    finally { setOutreachBusy(false); }
  }
  async function importEverquote() {
    if (!importCsv.trim()) return;
    setImportBusy(true); setImportMsg("");
    try {
      const r = await api.post<{ imported: number; updated: number; skipped: number; total: number }>(
        "/leads/import-everquote", { csv_text: importCsv });
      setImportMsg(`Imported ${r.imported} new · ${r.updated} updated · ${r.skipped} skipped (of ${r.total}). Now click “Personalize & queue all”, or paste a lead id below.`);
      setImportCsv(""); reload();
    } catch (e) { setImportMsg(String(e)); }
    finally { setImportBusy(false); }
  }
  async function personalizeAll() {
    setImportBusy(true);
    try {
      const r = await api.post<{ queued: number; skipped: number; failed: number; considered: number }>(
        "/leads/everquote/personalize-batch", {});
      setImportMsg(`Queued ${r.queued} personalized email drafts · ${r.skipped} skipped (already contacted or no email)${r.failed ? ` · ${r.failed} failed` : ""}. Review them in the approvals queue.`);
    } catch (e) { setImportMsg(String(e)); }
    finally { setImportBusy(false); }
  }

  async function loadCoach(id: string) {
    setCoach(null); setCoachBusy(true);
    try { setCoach(await api.get<Coach>(`/leads/${id}/call-coach`)); }
    catch (e) { setTlErr(String(e)); }
    finally { setCoachBusy(false); }
  }

  const [ask, setAsk] = useState("");
  const [askRes, setAskRes] = useState<AskResult | null>(null);
  const [askBusy, setAskBusy] = useState(false);
  async function runAsk(q: string) {
    const question = q.trim();
    if (!question) return;
    setAsk(question); setAskBusy(true);
    try { setAskRes(await api.post<AskResult>("/mission/ask", { question })); }
    catch { /* leave prior result */ }
    finally { setAskBusy(false); }
  }

  const [returning, setReturning] = useState("");
  async function returnLead(id: string) {
    setReturning(id);
    try { await api.post(`/mission/return/${id}`, {}); reloadReturns(); reload(); }
    catch { /* row stays; user can retry */ }
    finally { setReturning(""); }
  }
  const [objText, setObjText] = useState("");
  const [objection, setObjection] = useState<Objection | null>(null);
  const [objBusy, setObjBusy] = useState(false);

  async function handleObjection() {
    if (!objText.trim()) return;
    setObjBusy(true); setObjection(null);
    try {
      setObjection(await api.post<Objection>("/mission/objection",
        { text: objText.trim(), lead_id: timeline?.lead?.id || null }));
      if (timeline?.lead?.id) loadTimeline(timeline.lead.id);
    } catch { /* surfaced by empty result */ }
    finally { setObjBusy(false); }
  }

  async function buildQuote(id: string) {
    setQuote(null); setQuoteBusy(true);
    try { setQuote(await api.get<Quote>(`/leads/${id}/quote`)); }
    catch (e) { setTlErr(String(e)); }
    finally { setQuoteBusy(false); }
  }
  async function markQuoteSent(id: string) {
    setQuoteBusy(true);
    try {
      setQuote(await api.post<Quote>(`/leads/${id}/quote/sent`, {}));
      loadTimeline(id); reload();
    } catch (e) { setTlErr(String(e)); }
    finally { setQuoteBusy(false); }
  }

  async function runLifecycle() {
    setRunning(true); setRunMsg("");
    try {
      const r = await api.post<{ stage_transitions: number; status_advanced: number;
        speed_breaches: number; return_eligible: number }>("/mission/lifecycle/run", {});
      setRunMsg(`Moved ${r.stage_transitions} stages · advanced ${r.status_advanced} · ` +
        `${r.speed_breaches} speed flags · ${r.return_eligible} to re-engage`);
      reload();
    } catch (e) { setRunMsg(String(e)); }
    finally { setRunning(false); }
  }

  async function loadTimeline(id: string) {
    if (!id.trim()) return;
    setTlErr(""); setTimeline(null); setQuote(null); setCoach(null); setOutreach(null); setOutreachMsg("");
    try {
      const t = await api.get<Timeline>(`/mission/lead-timeline/${id.trim()}`);
      if (!t.ok) setTlErr("Lead not found — paste a valid lead id."); else setTimeline(t);
    } catch (e) { setTlErr(String(e)); }
  }

  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;
  const s = data.speed;
  const maxStage = Math.max(1, ...data.pipeline.map((p) => p.count));

  return (
    <div className="space-y-6">
      <PageHeader title="🎖️ Insurance Commander"
        subtitle="Your sales operating system — the day's leads, the speed scoreboard, and where every deal sits. Speed wins: first touch under 60 seconds." />

      {/* Ask your book */}
      <div className="card">
        <h2 className="font-semibold">💬 Ask your book</h2>
        <div className="mt-2 flex gap-2">
          <input value={ask} onChange={(e) => setAsk(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runAsk(ask)}
            placeholder="Who needs follow-up today? · Hottest leads · Who's waiting on a quote?"
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <button className="btn" onClick={() => runAsk(ask)} disabled={askBusy}>{askBusy ? "…" : "Ask"}</button>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {["Who should I call today?", "Hottest leads", "Who's waiting on a quote?", "Dead-ends to revive", "Who did we respond to too slowly?"].map((s) => (
            <button key={s} className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600 hover:bg-gray-200"
              onClick={() => runAsk(s)}>{s}</button>
          ))}
        </div>
        {askRes && (
          <div className="mt-3">
            <p className="text-sm font-medium text-gray-800">{askRes.answer}</p>
            <ul className="mt-2 divide-y divide-gray-100">
              {askRes.leads.map((l) => (
                <li key={l.lead_id} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 py-1.5">
                  <button className="font-medium text-brand hover:underline"
                    onClick={() => { setLeadId(l.lead_id); loadTimeline(l.lead_id); }}>{l.name}</button>
                  <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">{l.stage}</span>
                  <span className="flex-1 text-xs text-gray-600">{l.reason}</span>
                  {l.phone && <span className="text-xs text-gray-400">☎ {l.phone}</span>}
                </li>
              ))}
              {askRes.count === 0 && askRes.intent !== "help" && <li className="py-1.5 text-sm text-gray-400">Nothing matches right now.</li>}
            </ul>
          </div>
        )}
      </div>

      {/* Import EverQuote leads */}
      <div className="card">
        <h2 className="font-semibold">📥 Import EverQuote leads</h2>
        <p className="mb-2 text-xs text-gray-500">Paste your EverQuote CSV export. Every field is parsed (vehicle, current carrier, credit, coverage), leads are created with a pre-filled quote intake, and each gets a personalized email + SMS + voicemail + call notes — 500 leads take the same effort as 5.</p>
        <textarea value={importCsv} onChange={(e) => setImportCsv(e.target.value)}
          placeholder='Paste EverQuote CSV here (including the header row: "created_at","eqLeadUUID",…)'
          className="h-24 w-full rounded-lg border border-gray-300 px-3 py-2 font-mono text-xs" />
        <div className="mt-2 flex items-center gap-3">
          <button className="btn" onClick={importEverquote} disabled={importBusy || !importCsv.trim()}>
            {importBusy ? "Working…" : "Import leads"}
          </button>
          <button className="btn-ghost" onClick={personalizeAll} disabled={importBusy}>
            Personalize &amp; queue all →
          </button>
        </div>
        {importMsg && <p className="mt-2 text-sm text-gray-600">{importMsg}</p>}
      </div>

      {/* Today's tiles */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Tile label="Today's Leads" value={data.tiles.todays_leads} />
        <Tile label="Need Immediate Response" value={data.tiles.need_immediate_response}
          tone={data.tiles.need_immediate_response > 0 ? "red" : "green"} />
        <Tile label="Engaged / Waiting on Quote" value={data.tiles.engaged_waiting_on_quote} tone="amber" />
        <Tile label="Follow-ups Due Today" value={data.tiles.need_follow_up_today}
          tone={data.tiles.need_follow_up_today > 0 ? "amber" : "green"} />
        <Tile label="Policies Bound Today" value={data.tiles.policies_bound_today} tone="green" />
        <Tile label="Commission Today" value={money(data.tiles.commission_today)} tone="green" />
      </div>

      {/* Speed scoreboard */}
      <div className={`card ${s.over_target ? "border-2 border-red-300 bg-red-50" : ""}`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold">⚡ Speed — first response time</h2>
            <p className="text-xs text-gray-500">Goal: under {s.target_seconds}s. {s.measured} recent leads measured.</p>
          </div>
          {s.over_target && <span className="rounded-lg bg-red-600 px-3 py-1 text-sm font-bold text-white">🚨 RED ALERT — too slow</span>}
        </div>
        <div className="mt-3 grid grid-cols-3 gap-3 text-center">
          <div><div className="text-xs text-gray-400">Average</div><div className={`text-2xl font-bold ${s.over_target ? "text-red-600" : "text-emerald-600"}`}>{secs(s.avg_seconds)}</div></div>
          <div><div className="text-xs text-gray-400">Best</div><div className="text-2xl font-bold text-emerald-600">{secs(s.best_seconds)}</div></div>
          <div><div className="text-xs text-gray-400">Worst</div><div className="text-2xl font-bold text-gray-700">{secs(s.worst_seconds)}</div></div>
        </div>
      </div>

      {/* Pipeline funnel */}
      <div className="card">
        <h2 className="mb-3 font-semibold">Pipeline — where every lead sits</h2>
        <div className="space-y-1.5">
          {data.pipeline.map((p) => (
            <div key={p.stage} className="flex items-center gap-2">
              <div className="w-40 shrink-0 text-sm text-gray-600">{p.stage}</div>
              <div className="h-5 flex-1 rounded bg-gray-100">
                <div className="h-5 rounded bg-brand/70" style={{ width: `${(p.count / maxStage) * 100}%` }} />
              </div>
              <div className="w-12 text-right text-sm font-medium">{p.count}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Lifecycle engine — the pipeline moves itself */}
      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold">🔄 Lifecycle engine — the pipeline moves itself</h2>
            <p className="text-xs text-gray-500">Every few hours it repairs statuses, logs each stage move into the lead&apos;s AI timeline, and flags slow starts + dead-ends to re-engage. Nobody moves cards by hand.</p>
          </div>
          <button className="btn" onClick={runLifecycle} disabled={running}>
            {running ? "Running…" : "Run a pass now"}
          </button>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-3 text-center">
          <div><div className="text-xs text-gray-400">Stage moves today</div><div className="text-2xl font-bold text-brand">{data.lifecycle?.stage_moves_today ?? 0}</div></div>
          <div><div className="text-xs text-gray-400">Speed flags</div><div className="text-2xl font-bold text-amber-600">{data.lifecycle?.speed_breaches ?? 0}</div></div>
          <div><div className="text-xs text-gray-400">Ready to re-engage</div><div className="text-2xl font-bold text-emerald-600">{data.lifecycle?.return_eligible ?? 0}</div></div>
        </div>
        {runMsg && <p className="mt-2 text-sm text-gray-600">{runMsg}</p>}
      </div>

      {/* Lead Return Assistant */}
      {returns && returns.length > 0 && (
        <div className="card">
          <h2 className="font-semibold">♻️ Lead Return Assistant — {returns.length} dead-end{returns.length === 1 ? "" : "s"} worth reviving</h2>
          <p className="mb-2 text-xs text-gray-500">Contacted, never replied, whole sequence burned. Return one to re-arm a fresh short cadence with a new angle — nobody gets nagged twice.</p>
          <ul className="divide-y divide-gray-100">
            {returns.slice(0, 12).map((r) => (
              <li key={r.lead_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                <span className="font-medium">{r.name}</span>
                <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">{r.line}</span>
                {r.days_since_touch != null && <span className="text-xs text-gray-400">{r.days_since_touch}d cold</span>}
                <span className="flex-1 basis-full text-xs text-gray-600 sm:basis-0">💡 {r.angle}</span>
                <button className="btn-ghost text-sm" onClick={() => returnLead(r.lead_id)} disabled={returning === r.lead_id}>
                  {returning === r.lead_id ? "…" : "Return →"}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* EverQuote-valid returns */}
      {eqReturns && eqReturns.length > 0 && (
        <div className="card">
          <h2 className="font-semibold">↩️ EverQuote Return Assistant — {eqReturns.length} eligible for a valid return</h2>
          <p className="mb-2 text-xs text-gray-500">Only EverQuote-valid reasons: invalid/disconnected phone, invalid email, duplicate, or out-of-footprint. (A consumer saying &quot;I didn&apos;t request this&quot; is <span className="font-medium">not</span> a valid return — that&apos;s an objection to verify, not a return.)</p>
          <ul className="divide-y divide-gray-100">
            {eqReturns.slice(0, 15).map((r) => (
              <li key={r.lead_id} className="py-2">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
                  <span className="font-medium">{r.name}</span>
                  {r.state && <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">{r.state}</span>}
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">{r.reason_code.replace(/_/g, " ")}</span>
                  {r.vehicle && <span className="text-xs text-gray-400">{r.vehicle}</span>}
                </div>
                <p className="mt-0.5 text-xs text-gray-600">Return reason: {r.reason_text}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Objection handler */}
      <div className="card">
        <h2 className="font-semibold">🛡️ Objection AI — what do I say back?</h2>
        <p className="mb-2 text-xs text-gray-500">Paste what the prospect said (&quot;it&apos;s too expensive&quot;, &quot;I&apos;ll think about it&quot;, &quot;already have insurance&quot;) and get the proven rebuttal + next move. Tailors to the loaded lead when the OpenAI key is connected.</p>
        <div className="flex gap-2">
          <input value={objText} onChange={(e) => setObjText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleObjection()}
            placeholder="e.g. It's too expensive right now"
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <button className="btn" onClick={handleObjection} disabled={objBusy}>
            {objBusy ? "…" : "Get rebuttal"}
          </button>
        </div>
        {objection?.ok && (
          <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-brand/10 px-2.5 py-1 text-xs font-medium text-brand-dark">{objection.objection}</span>
              <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-500">{objection.confidence} confidence</span>
              {objection.ai_used && <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs text-emerald-700">AI-tailored</span>}
            </div>
            {objection.tailored && (
              <p className="mt-2 text-sm font-medium text-gray-800">&ldquo;{objection.tailored}&rdquo;</p>
            )}
            <p className={`${objection.tailored ? "mt-2 text-xs text-gray-500" : "mt-2 text-sm text-gray-800"}`}>
              {objection.tailored ? "Proven script: " : ""}&ldquo;{objection.rebuttal}&rdquo;
            </p>
            <p className="mt-2 text-xs text-brand-dark"><span className="font-medium">Next move:</span> {objection.move}</p>
          </div>
        )}
      </div>

      {/* Per-lead AI timeline */}
      <div className="card">
        <h2 className="mb-2 font-semibold">🧠 Lead AI Timeline</h2>
        <p className="mb-2 text-xs text-gray-500">Paste a lead id to see everything the workforce did for it, in order — received, scored, called, texted, emailed, follow-ups scheduled.</p>
        <div className="flex gap-2">
          <input value={leadId} onChange={(e) => setLeadId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && loadTimeline(leadId)}
            placeholder="Lead id" className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <button className="btn" onClick={() => loadTimeline(leadId)}>View timeline</button>
        </div>
        {tlErr && <p className="mt-2 text-sm text-red-600">{tlErr}</p>}
        {timeline?.lead && (
          <div className="mt-4">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-lg font-semibold">{timeline.lead.name}</span>
              <span className="rounded-full bg-brand/10 px-2.5 py-1 text-xs text-brand-dark">Score {timeline.lead.score}/100 · {timeline.lead.band}</span>
              <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600">{timeline.lead.stage}</span>
              <span className="text-xs text-gray-400">{timeline.lead.source}</span>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button className="btn" onClick={() => loadCoach(timeline.lead!.id)} disabled={coachBusy}>
                📞 Call Coach
              </button>
              <button className="btn" onClick={() => loadOutreach(timeline.lead!.id)} disabled={outreachBusy}>
                ✉️ Personalized outreach
              </button>
              <button className="btn" onClick={() => buildQuote(timeline.lead!.id)} disabled={quoteBusy}>
                🧮 Build quote
              </button>
              {quote?.ok && (
                <button className="btn-ghost" onClick={() => markQuoteSent(timeline.lead!.id)} disabled={quoteBusy}>
                  Mark quote sent →
                </button>
              )}
            </div>

            {coach?.ok && (
              <div className="mt-3 rounded-lg border border-brand/30 bg-brand/5 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-brand/10 px-2.5 py-1 text-xs font-medium text-brand-dark">{coach.line.toUpperCase()}</span>
                  <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600">{coach.stage}</span>
                  <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600">Score {coach.score}/100 · {coach.band}</span>
                  <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600">{coach.history.outbound_touches} touches · {coach.history.replied ? "replied" : "no reply yet"}</span>
                  {coach.lead.phone && <span className="text-xs text-gray-500">☎ {coach.lead.phone}</span>}
                </div>
                <p className="mt-2 text-sm"><span className="font-medium">🎯 Goal:</span> {coach.goal}</p>
                <p className="mt-1 text-sm"><span className="font-medium">➡️ Ask for:</span> {coach.ask_next}</p>
                <p className="mt-2 text-sm font-medium text-gray-800">Opener:</p>
                <p className="text-sm text-gray-700">&ldquo;{coach.opener_tailored || coach.opener}&rdquo;</p>
                {coach.opener_tailored && <p className="text-[11px] text-gray-400">Template: &ldquo;{coach.opener}&rdquo;</p>}
                <p className="mt-2 text-sm"><span className="font-medium">Coverages:</span> {coach.coverages}</p>
                {coach.likely_objections.length > 0 && (
                  <div className="mt-2">
                    <p className="text-sm font-medium">Likely objections + what to say:</p>
                    <ul className="mt-1 space-y-1.5">
                      {coach.likely_objections.map((o, i) => (
                        <li key={i} className="text-xs text-gray-600">
                          <span className="font-medium text-gray-800">{o.objection}:</span> &ldquo;{o.rebuttal}&rdquo;
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {outreachMsg && <p className="mt-2 text-sm text-emerald-700">{outreachMsg}</p>}
            {outreach?.ok && (
              <div className="mt-3 space-y-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium text-gray-800">✉️ Personalized for {outreach.name} · {outreach.vehicle}</span>
                  <button className="btn-ghost text-sm" onClick={() => queueOutreach(timeline.lead!.id)} disabled={outreachBusy}>Queue email as draft →</button>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">Email</p>
                  <p className="text-sm font-medium">{outreach.email.subject}</p>
                  <pre className="mt-1 whitespace-pre-wrap font-sans text-sm text-gray-700">{outreach.email.tailored || outreach.email.body}</pre>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">SMS</p>
                  <p className="text-sm text-gray-700">{outreach.sms.tailored || outreach.sms.body}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">Voicemail script</p>
                  <p className="text-sm text-gray-700">{outreach.voicemail}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">Call notes</p>
                  <ul className="mt-1 list-disc pl-5 text-sm text-gray-700">
                    {outreach.call_notes.map((n, i) => <li key={i}>{n}</li>)}
                  </ul>
                </div>
              </div>
            )}

            {quote?.ok && (
              <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-brand/10 px-2.5 py-1 text-xs font-medium text-brand-dark">{quote.line.toUpperCase()}{quote.state ? ` · ${quote.state}` : ""}</span>
                  {quote.quote_type_label && <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600">{quote.quote_type_label}</span>}
                  <span className={`rounded-full px-2.5 py-1 text-xs ${quote.ready_to_send ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                    {quote.ready_to_send ? "Ready to quote" : `${quote.intake.collected}/${quote.intake.total} intake collected`}
                  </span>
                  {quote.marked_sent && <span className="rounded-full bg-emerald-600 px-2.5 py-1 text-xs font-bold text-white">✓ Marked sent</span>}
                </div>
                <div className="mt-2 text-2xl font-bold text-emerald-700">
                  ${quote.estimate.monthly_low}–${quote.estimate.monthly_high}<span className="text-sm font-normal text-gray-400">/mo est.</span>
                </div>
                <p className="text-xs text-gray-500">{quote.estimate.note}</p>
                <p className="mt-2 text-sm"><span className="font-medium">Coverages:</span> {quote.coverages}</p>
                <p className="mt-1 text-sm"><span className="font-medium">Carriers to shop:</span> {quote.carriers.join(", ")}</p>
                {!quote.ready_to_send && quote.intake.missing.length > 0 && (
                  <p className="mt-1 text-sm text-amber-700"><span className="font-medium">Still needed:</span> {quote.intake.missing.join(", ")}</p>
                )}
              </div>
            )}

            <ol className="mt-3 space-y-2 border-l-2 border-gray-200 pl-4">
              {(timeline.timeline || []).map((e, i) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-brand" />
                  <div className="text-sm font-medium">{e.label}</div>
                  {e.detail && <div className="text-xs text-gray-500">{e.detail}</div>}
                  <div className="text-[11px] text-gray-400">{e.at ? new Date(e.at).toLocaleString() : ""}{e.status ? ` · ${e.status}` : ""}</div>
                </li>
              ))}
              {(timeline.timeline || []).length === 0 && <li className="text-sm text-gray-400">No activity recorded yet.</li>}
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><InsuranceCommander /></AuthGate>;
}
