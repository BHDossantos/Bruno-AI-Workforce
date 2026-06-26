"use client";

import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Metric = { key: string; label: string; this_week: number; last_week: number; delta_pct: number; trend: string };
type Rec = { action: string; rationale: string; confidence: number };
type Report = {
  generated_at: string; period: { from: string; to: string };
  metrics: Metric[]; expected_pipeline: number; headline: string | null;
  recommendations: Rec[]; challenge: string | null;
  top_actions: { title: string; value: number; probability: number }[];
};

function money(n: number) {
  return n >= 1000 ? `$${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}k` : `$${n}`;
}
function arrow(t: string) { return t === "up" ? "▲" : t === "down" ? "▼" : "▬"; }
function color(t: string) { return t === "up" ? "text-green-600" : t === "down" ? "text-red-500" : "text-gray-400"; }

function Board() {
  const { data } = useFetch<Report>(() => api.get<Report>("/board-report"));
  if (!data) return <div className="p-4 text-gray-400">Generating this week&apos;s board review…</div>;

  return (
    <div className="space-y-8">
      <PageHeader title="Weekly Board Report"
        subtitle={`Executive review · ${data.period.from} → ${data.period.to}`} />

      {data.headline && (
        <div className="card bg-brand/5">
          <p className="text-lg font-semibold">{data.headline}</p>
          <p className="mt-1 text-sm text-gray-500">Expected open pipeline: <b>{money(data.expected_pipeline)}</b></p>
        </div>
      )}

      <div>
        <h2 className="mb-3 font-semibold">This week vs last</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {data.metrics.map((m) => (
            <div key={m.key} className="card">
              <div className="text-xs text-gray-500">{m.label}</div>
              <div className="text-2xl font-bold">{m.this_week.toLocaleString()}</div>
              <div className={`text-xs ${color(m.trend)}`}>{arrow(m.trend)} {Math.abs(m.delta_pct)}% · was {m.last_week}</div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="mb-3 font-semibold">🎯 Recommendations</h2>
        <div className="space-y-3">
          {data.recommendations.map((r, i) => (
            <div key={i} className="card flex items-start justify-between gap-4">
              <div>
                <div className="font-semibold">{r.action}</div>
                <div className="text-sm text-gray-500">{r.rationale}</div>
              </div>
              <div className="shrink-0 text-right">
                <div className="text-lg font-bold text-brand">{r.confidence ?? "—"}%</div>
                <div className="text-[10px] text-gray-400">confidence</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {data.challenge && (
        <div className="card border-l-4 border-brand">
          <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">A question to sit with</div>
          <p className="mt-1 text-gray-800">{data.challenge}</p>
        </div>
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><Board /></AuthGate>;
}
