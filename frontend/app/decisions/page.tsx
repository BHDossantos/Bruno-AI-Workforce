"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Decision = {
  id: string; title: string; category: string; decision: string | null;
  reasoning: string | null; expected_outcome: string | null; confidence: number;
  status: string; outcome: string | null; outcome_note: string | null; decided_at: string | null;
};
type Patterns = {
  reviewed: number; overall_win_rate: number | null;
  by_category: { category: string; count: number; win_rate: number | null }[];
  calibration: { high_confidence_win_rate: number | null; high_confidence_n: number; low_confidence_win_rate: number | null; low_confidence_n: number };
};

const CATEGORIES = ["career", "business", "insurance", "music", "financial", "personal", "other"];
const OUTCOME_COLOR: Record<string, string> = { success: "bg-green-100 text-green-700", failure: "bg-red-100 text-red-600", mixed: "bg-amber-100 text-amber-700" };

function Decisions() {
  const [refresh, setRefresh] = useState(0);
  const { data } = useFetch<Decision[]>(() => api.get<Decision[]>("/decisions"), [refresh]);
  const { data: pat } = useFetch<Patterns>(() => api.get<Patterns>("/decisions/patterns"), [refresh]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ title: "", category: "business", decision: "", reasoning: "", expected_outcome: "", confidence: 60 });

  async function create() {
    if (!f.title.trim()) return;
    setBusy(true);
    try {
      await api.post("/decisions", f);
      setF({ title: "", category: "business", decision: "", reasoning: "", expected_outcome: "", confidence: 60 });
      setOpen(false); setRefresh((n) => n + 1);
    } finally { setBusy(false); }
  }

  async function record(id: string, outcome: string) {
    const note = window.prompt(`Outcome note for this decision (${outcome}):`) || undefined;
    await api.post(`/decisions/${id}/outcome`, { outcome, outcome_note: note });
    setRefresh((n) => n + 1);
  }

  return (
    <div className="space-y-8">
      <PageHeader title="Decision Journal"
        subtitle="Log major decisions + your reasoning, record the real outcome later, and watch the patterns emerge."
        action={<button className="btn" onClick={() => setOpen(!open)}>{open ? "Close" : "+ Log decision"}</button>} />

      {pat && pat.reviewed > 0 && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div className="card"><div className="text-xs text-gray-500">Reviewed</div><div className="text-3xl font-bold">{pat.reviewed}</div></div>
          <div className="card"><div className="text-xs text-gray-500">Win rate</div><div className="text-3xl font-bold text-brand">{pat.overall_win_rate ?? "—"}%</div></div>
          <div className="card"><div className="text-xs text-gray-500">High-confidence wins</div><div className="text-3xl font-bold">{pat.calibration.high_confidence_win_rate ?? "—"}%<span className="text-xs text-gray-400"> ({pat.calibration.high_confidence_n})</span></div></div>
          <div className="card"><div className="text-xs text-gray-500">Low-confidence wins</div><div className="text-3xl font-bold">{pat.calibration.low_confidence_win_rate ?? "—"}%<span className="text-xs text-gray-400"> ({pat.calibration.low_confidence_n})</span></div></div>
        </div>
      )}

      {pat && pat.by_category.length > 0 && (
        <div className="card">
          <h2 className="mb-2 text-sm font-semibold text-gray-600">Win rate by category</h2>
          <div className="flex flex-wrap gap-2">
            {pat.by_category.map((c) => (
              <span key={c.category} className="rounded-full bg-gray-100 px-3 py-1 text-sm">
                {c.category}: <b>{c.win_rate ?? "—"}%</b> <span className="text-gray-400">({c.count})</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {open && (
        <div className="card grid gap-3 sm:grid-cols-2">
          <input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Decision (e.g. Take the CVS offer over consulting)" className="rounded-lg border border-gray-300 px-3 py-2 text-sm sm:col-span-2" />
          <label className="text-sm">Category
            <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label className="text-sm">Confidence: {f.confidence}%
            <input type="range" min={0} max={100} step={5} value={f.confidence} onChange={(e) => setF({ ...f, confidence: Number(e.target.value) })} className="mt-2 block w-full" />
          </label>
          <textarea value={f.reasoning} onChange={(e) => setF({ ...f, reasoning: e.target.value })} placeholder="Reasoning — why this call?" rows={2} className="rounded-lg border border-gray-300 px-3 py-2 text-sm sm:col-span-2" />
          <textarea value={f.expected_outcome} onChange={(e) => setF({ ...f, expected_outcome: e.target.value })} placeholder="Expected outcome" rows={2} className="rounded-lg border border-gray-300 px-3 py-2 text-sm sm:col-span-2" />
          <button className="btn sm:col-span-2" onClick={create} disabled={busy || !f.title.trim()}>{busy ? "Saving…" : "Log decision"}</button>
        </div>
      )}

      <div className="space-y-3">
        {(data || []).map((d) => (
          <div key={d.id} className="card">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="font-semibold">{d.title}</div>
                <div className="text-xs text-gray-400">{d.category} · {d.confidence}% confidence · {d.decided_at?.slice(0, 10)}</div>
              </div>
              {d.outcome
                ? <span className={`rounded px-2 py-0.5 text-xs ${OUTCOME_COLOR[d.outcome] || "bg-gray-100"}`}>{d.outcome}</span>
                : <span className="flex gap-1">
                    <button onClick={() => record(d.id, "success")} className="rounded bg-green-600 px-2 py-1 text-xs text-white">Win</button>
                    <button onClick={() => record(d.id, "mixed")} className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-500">Mixed</button>
                    <button onClick={() => record(d.id, "failure")} className="rounded border border-gray-300 px-2 py-1 text-xs text-red-500">Loss</button>
                  </span>}
            </div>
            {d.reasoning && <p className="mt-2 text-sm text-gray-600">{d.reasoning}</p>}
            {d.outcome_note && <p className="mt-1 text-xs text-gray-400">Outcome: {d.outcome_note}</p>}
          </div>
        ))}
        {data && data.length === 0 && <div className="card text-sm text-gray-400">No decisions logged yet — the journal teaches the AI how you decide over time.</div>}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Decisions /></AuthGate>;
}
