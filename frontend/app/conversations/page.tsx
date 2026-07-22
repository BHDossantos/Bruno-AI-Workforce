"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, KpiCard, useFetch } from "@/components/ui";

type Schema = { schema: Record<string, string[]>; objection_responses: Record<string, string> };
type Dashboard = {
  by_status: Record<string, number>; today: number; total: number; answered: number;
  contact_rate: number; top_carriers: { carrier: string; count: number }[];
};
type Lead = { id: string; name?: string; owner_name?: string; email?: string | null; phone?: string | null };
type Renewal = { lead_id: string; name: string; current_carrier?: string | null; renewal_month?: string | null; remind_at?: string | null };
type Insights = {
  total: number; answered?: number; sold?: number; contact_rate?: number; close_rate?: number;
  best_hours?: { hour: number; calls: number; answered_rate: number }[];
  by_carrier?: { carrier: string; seen: number; won: number; win_rate: number }[];
  by_renewal_month?: { month: string; count: number }[];
  top_objections?: { objection: string; count: number }[];
};

const pretty = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
const hour12 = (h: number) => `${((h + 11) % 12) + 1} ${h < 12 ? "AM" : "PM"}`;

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-gray-500">{label}</span>
      {children}
    </label>
  );
}

function ConversationEngine() {
  const { data: schema } = useFetch<Schema>(() => api.get<Schema>("/conversations/schema"));
  const { data: dash, reload: reloadDash } = useFetch<Dashboard>(() => api.get<Dashboard>("/conversations/dashboard"));
  const { data: leads } = useFetch<Lead[]>(() => api.get<Lead[]>("/leads?limit=300&sort=score"));
  const { data: renewals } = useFetch<{ renewals: Renewal[] }>(() => api.get("/conversations/renewals"));
  const { data: insights } = useFetch<Insights>(() => api.get("/conversations/insights"));

  const [leadId, setLeadId] = useState("");
  const [opp, setOpp] = useState<Record<string, number> | null>(null);
  const [form, setForm] = useState<Record<string, unknown>>({ method: "call", outcome: "answered" });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [result, setResult] = useState<{ ai_summary?: string; suggested_response?: string | null } | null>(null);

  const opts = schema?.schema || {};
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));
  const answered = form.outcome === "answered";

  useEffect(() => {
    if (!leadId) { setOpp(null); return; }
    api.get<{ opportunity: Record<string, number> }>(`/leads/${leadId}/opportunity`)
      .then((r) => setOpp(r.opportunity)).catch(() => setOpp(null));
  }, [leadId]);

  const suggested = useMemo(() => {
    const objection = form.objection as string | undefined;
    const status = form.conversation_status as string | undefined;
    return (objection && schema?.objection_responses[objection]) ||
           (status && schema?.objection_responses[status]) || "";
  }, [form.objection, form.conversation_status, schema]);

  async function submit() {
    if (!leadId) { setMsg("Pick a lead first."); return; }
    setBusy(true); setMsg(""); setResult(null);
    try {
      const r = await api.post<{ ai_summary?: string; suggested_response?: string | null }>(
        `/leads/${leadId}/conversation`, form);
      setResult(r);
      setMsg("✅ Logged — timeline, follow-up, and dashboard updated.");
      setForm({ method: "call", outcome: "answered" });
      reloadDash();
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(false); }
  }

  const Select = ({ k, blank = "—" }: { k: string; blank?: string }) => (
    <select className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
      value={(form[k] as string) || ""} onChange={(e) => set(k, e.target.value || undefined)}>
      <option value="">{blank}</option>
      {(opts[k] || []).map((o) => <option key={o} value={o}>{pretty(o)}</option>)}
    </select>
  );
  const Check = ({ k, label }: { k: string; label: string }) => (
    <label className="flex items-center gap-2 text-sm text-gray-700">
      <input type="checkbox" checked={!!form[k]} onChange={(e) => set(k, e.target.checked)} /> {label}
    </label>
  );

  return (
    <div>
      <PageHeader title="🧠 Conversation Engine"
        subtitle="Every call becomes structured data. Log the outcome — the CRM segments your book and gets smarter every week." />

      {/* Dashboard — segment the book by outcome */}
      {dash && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <KpiCard label="Conversations logged" value={dash.total} hint={`${dash.today} today`} />
            <KpiCard label="Answered" value={dash.answered} />
            <KpiCard label="Contact rate" value={`${dash.contact_rate}%`} />
            <KpiCard label="Carriers we face" value={dash.top_carriers.length} />
          </div>
          {Object.keys(dash.by_status).length > 0 && (
            <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4">
              <div className="mb-2 text-sm font-semibold text-gray-700">Your book by conversation status</div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(dash.by_status).sort((a, b) => b[1] - a[1]).map(([s, n]) => (
                  <span key={s} className="rounded-lg bg-brand/10 px-3 py-1 text-sm text-brand-dark">
                    {pretty(s)} <b>{n}</b>
                  </span>
                ))}
              </div>
              {dash.top_carriers.length > 0 && (
                <div className="mt-3 text-xs text-gray-500">
                  Competing against: {dash.top_carriers.map((c) => `${c.carrier} (${c.count})`).join(" · ")}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Renewal pipeline — money hiding in your book */}
      {renewals && renewals.renewals.length > 0 && (
        <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <div className="mb-2 text-sm font-semibold text-amber-900">🔔 Renewal pipeline ({renewals.renewals.length}) — work these before renewal</div>
          <div className="max-h-52 overflow-y-auto">
            {renewals.renewals.map((r) => (
              <div key={r.lead_id} className="flex items-center justify-between border-b border-amber-100 py-1.5 text-sm last:border-0">
                <span>{r.name} <span className="text-xs text-amber-700">{r.current_carrier || "—"} · renews {r.renewal_month}</span></span>
                <span className="text-xs text-amber-800">remind {r.remind_at}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Learning loop — what actually works (gets smarter every week) */}
      {insights && insights.total > 0 && (
        <div className="mb-6 rounded-xl border border-indigo-200 bg-indigo-50/40 p-4">
          <div className="mb-2 text-sm font-semibold text-indigo-900">📈 What's working — learned from {insights.total} calls</div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3 text-sm">
            <div>
              <div className="text-xs font-medium text-gray-500">Rates</div>
              <div>Contact <b>{insights.contact_rate}%</b> · Close <b>{insights.close_rate}%</b></div>
            </div>
            <div>
              <div className="text-xs font-medium text-gray-500">Best times to call</div>
              {(insights.best_hours || []).length ? (insights.best_hours || []).map((h) => (
                <div key={h.hour}>{hour12(h.hour)} — <b>{h.answered_rate}%</b> answered <span className="text-xs text-gray-400">({h.calls})</span></div>
              )) : <div className="text-gray-400">need more calls</div>}
            </div>
            <div>
              <div className="text-xs font-medium text-gray-500">Carriers you face (win rate)</div>
              {(insights.by_carrier || []).slice(0, 4).map((c) => (
                <div key={c.carrier}>{c.carrier} — <b>{c.win_rate}%</b> <span className="text-xs text-gray-400">({c.won}/{c.seen})</span></div>
              ))}
            </div>
          </div>
          {(insights.top_objections || []).length > 0 && (
            <div className="mt-3 text-xs text-gray-600">Top objections: {(insights.top_objections || []).map((o) => `${pretty(o.objection)} (${o.count})`).join(" · ")}</div>
          )}
        </div>
      )}

      {/* Structured log form */}
      <div className="rounded-xl border border-gray-200 bg-white p-4">
        <div className="mb-3 text-sm font-semibold text-gray-700">Log a conversation</div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Field label="Lead">
            <select className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              value={leadId} onChange={(e) => setLeadId(e.target.value)}>
              <option value="">Pick a lead…</option>
              {(leads || []).map((l) => (
                <option key={l.id} value={l.id}>{l.owner_name || l.name || l.email || l.id}</option>
              ))}
            </select>
          </Field>
          <Field label="Method"><Select k="method" /></Field>
          <Field label="Outcome"><Select k="outcome" /></Field>
        </div>

        {opp && (
          <div className="mt-3 rounded-lg bg-gray-50 p-3">
            <div className="mb-2 text-xs font-medium text-gray-500">Cross-sell opportunity for this lead</div>
            <div className="flex flex-wrap gap-3">
              {Object.entries(opp).map(([line, pct]) => (
                <div key={line} className="min-w-[110px] flex-1">
                  <div className="flex justify-between text-xs text-gray-600"><span>{pretty(line)}</span><b>{pct}%</b></div>
                  <div className="mt-1 h-2 w-full rounded bg-gray-200">
                    <div className="h-2 rounded bg-brand" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {!answered && (
          <div className="mt-3 flex flex-wrap gap-4 rounded-lg bg-gray-50 p-3">
            <Check k="voicemail_left" label="Voicemail left" />
            <Check k="text_sent" label="Text sent" />
            <Check k="email_sent" label="Email sent" />
          </div>
        )}

        {answered && (
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
            <Field label="Reason for calling"><Select k="reason_for_calling" /></Field>
            <Field label="Conversation status"><Select k="conversation_status" /></Field>
            <Field label="Objection"><Select k="objection" /></Field>
            <Field label="Next action"><Select k="next_action" /></Field>
            <Field label="Current carrier"><Select k="current_carrier" /></Field>
            <Field label="Renewal month"><Select k="renewal_month" /></Field>
            <Field label="Biggest concern"><Select k="biggest_concern" /></Field>
            <div className="flex items-end gap-4 md:col-span-3">
              <Check k="future_review" label="Wants a review at renewal" />
              <Check k="quote_started" label="Quote started" />
              <Check k="quote_completed" label="Quote completed" />
              <Check k="quote_sent" label="Quote sent" />
            </div>
          </div>
        )}

        {suggested && (
          <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
            <b>💬 AI — say this:</b> {suggested}
          </div>
        )}

        <div className="mt-4 flex items-center gap-3">
          <button className="btn" disabled={busy} onClick={submit}>{busy ? "Logging…" : "Log conversation"}</button>
          {msg && <span className="text-sm text-gray-600">{msg}</span>}
        </div>

        {result?.ai_summary && (
          <div className="mt-3 rounded-lg bg-gray-50 p-3 text-sm">
            <div><b>AI summary:</b> {result.ai_summary}</div>
            {result.suggested_response && <div className="mt-1 text-emerald-800"><b>Suggested next line:</b> {result.suggested_response}</div>}
          </div>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><ConversationEngine /></AuthGate>;
}
