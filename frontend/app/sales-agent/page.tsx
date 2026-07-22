"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, KpiCard, useFetch, LoadState } from "@/components/ui";

type Status = {
  live: boolean; paused: boolean; autopilot_on: boolean;
  today: { emails: number; texts: number; calls: number };
  pipeline: { working: number; needs_you: number; won: number; lost: number };
  needs_you_count: number;
};
type NeedsYou = {
  leads: { id: string; name: string; email?: string | null; phone?: string | null;
    status: string; score: number; reason?: string | null }[];
};

function SalesAgent() {
  const [tick, setTick] = useState(0);
  const { data: st, loading, error, reload } = useFetch<Status>(() => api.get<Status>("/sales-agent/status"), [tick]);
  const { data: needs } = useFetch<NeedsYou>(() => api.get<NeedsYou>("/sales-agent/needs-you"), [tick]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function runNow() {
    setBusy(true); setMsg("Running the sales agent — emailing, texting, and calling your book…");
    try {
      const r = await api.post<Record<string, unknown>>("/sales-agent/run", {});
      const g = (o: unknown) => (o && typeof o === "object" ? o as Record<string, unknown> : {});
      const n = (o: Record<string, unknown>, k: string) => Number(o[k] ?? 0);
      setMsg(`✅ Pass complete — email sent ${n(g(r.email), "sent")}, texts ${n(g(r.text), "sent")}, calls ${n(g(r.calls), "placed")}.`);
      setTick((t) => t + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(false); }
  }

  if (!st) return <LoadState loading={loading} error={error} onRetry={reload} />;

  return (
    <div>
      <PageHeader title="🤖 Sales Agent"
        subtitle="Your autonomous outbound seller — it works every lead email → text → call, hands-free, and only surfaces the ones who reply or go hot."
        action={<button className="btn" disabled={busy} onClick={runNow}>{busy ? "Running…" : "▶ Run a selling pass now"}</button>} />

      {msg && <p className="mb-4 rounded bg-brand/10 p-3 text-sm text-brand-dark">{msg}</p>}

      {/* Live status */}
      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-gray-200 bg-white p-4 text-sm">
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${st.live ? "bg-emerald-100 text-emerald-800" : "bg-gray-100 text-gray-600"}`}>
          {st.live ? "● LIVE — selling hands-free" : st.paused ? "❚❚ Paused (Emergency Stop)" : "○ Idle — turn on Outreach Autopilot"}
        </span>
        <span className="text-gray-500">Today: <b className="text-gray-800">{st.today.emails}</b> emails · <b className="text-gray-800">{st.today.texts}</b> texts · <b className="text-gray-800">{st.today.calls}</b> calls</span>
      </div>

      {/* Pipeline split */}
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiCard label="Working (in cadence)" value={st.pipeline.working} />
        <KpiCard label="Needs you" value={st.pipeline.needs_you} hint="replied / interested" />
        <KpiCard label="Won" value={st.pipeline.won} />
        <KpiCard label="Lost" value={st.pipeline.lost} />
      </div>

      {/* Needs-you queue */}
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
        <div className="mb-2 text-sm font-semibold text-amber-900">🔥 Needs you ({needs?.leads.length || 0}) — engaged leads pulled out of the machine, hottest first</div>
        {needs && needs.leads.length > 0 ? (
          <div className="max-h-[28rem] overflow-y-auto">
            {needs.leads.map((l) => (
              <a key={l.id} href={`/leads/${l.id}`}
                className="flex items-center justify-between border-b border-amber-100 py-2 text-sm last:border-0 hover:bg-amber-100/50">
                <span>
                  <b>{l.name}</b> <span className="ml-1 rounded bg-white px-1.5 py-0.5 text-xs text-amber-800">{l.status}</span>
                  {l.reason && <span className="ml-2 text-xs text-amber-700">{l.reason}</span>}
                </span>
                <span className="text-xs text-amber-800">score {l.score}</span>
              </a>
            ))}
          </div>
        ) : <div className="text-sm text-amber-700">Nobody waiting — the agent is working the rest of the book.</div>}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><SalesAgent /></AuthGate>;
}
