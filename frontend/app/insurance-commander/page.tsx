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
  const [leadId, setLeadId] = useState("");
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [tlErr, setTlErr] = useState("");
  const [running, setRunning] = useState(false);
  const [runMsg, setRunMsg] = useState("");

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
    setTlErr(""); setTimeline(null);
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
