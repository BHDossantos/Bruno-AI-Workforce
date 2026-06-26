"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Component = { label: string; annual_potential: number; current_pipeline: number; probability: number };
type Path = {
  name: string; description: string; projected_annual: number; current_expected: number;
  coverage: number; gap: number;
  probability: number; meets_target: boolean; score: number; components: Component[]; key_moves: string[];
};
type Sim = {
  target: number; recommended: string | null; assumptions: string;
  streams: { key: string; label: string; annual_potential: number; probability: number; key_move: string }[];
  paths: Path[];
};

function money(n: number) {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  return n >= 1000 ? `$${(n / 1000).toFixed(0)}k` : `$${n}`;
}

function Planning() {
  const [target, setTarget] = useState(1_000_000);
  const [applied, setApplied] = useState(1_000_000);
  const { data, error, loading } = useFetch<Sim>(() => api.get<Sim>(`/planning/simulate?target=${applied}`), [applied]);

  return (
    <div className="space-y-8">
      <PageHeader title="Predictive Planning"
        subtitle="Ask how to reach a yearly income target — the system simulates paths from your live pipeline." />

      <div className="card flex flex-wrap items-end gap-3">
        <label className="text-sm">Annual income target
          <div className="mt-1 flex items-center gap-2">
            <span className="text-gray-400">$</span>
            <input type="number" step="50000" value={target} onChange={(e) => setTarget(Number(e.target.value))}
              className="w-40 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          </div>
        </label>
        <button className="btn" onClick={() => setApplied(target)}>Simulate</button>
        {data?.recommended && <span className="text-sm text-gray-500">Recommended path: <b className="text-brand-dark">{data.recommended}</b></span>}
      </div>

      {error && <div className="card text-sm text-red-600">Couldn&apos;t simulate: {error}</div>}
      {loading && <div className="p-4 text-gray-400">Simulating…</div>}
      {!loading && !error && data && (
        <>
          <div className="space-y-4">
            {data.paths.map((p, i) => (
              <div key={p.name} className={`card ${i === 0 ? "ring-2 ring-brand" : ""}`}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold">
                      {i === 0 && "⭐ "}{p.name}
                      <span className={`ml-2 rounded px-2 py-0.5 text-xs ${p.meets_target ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
                        {p.meets_target ? "hits target" : "short of target"}
                      </span>
                    </div>
                    <div className="text-sm text-gray-500">{p.description}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold">{money(p.projected_annual)}<span className="text-sm text-gray-400">/yr potential</span></div>
                    <div className="text-xs text-gray-500">now: <b>{money(p.current_expected)}</b> expected pipeline</div>
                    <div className={`text-xs font-medium ${p.meets_target ? "text-green-600" : "text-amber-600"}`}>
                      {Math.round(p.coverage * 100)}% of {money(data.target)} target
                      {p.gap > 0 && <span className="text-gray-400"> · {money(p.gap)} gap</span>}
                    </div>
                    <div className="text-xs text-gray-400">{Math.round(p.probability * 100)}% feasibility</div>
                  </div>
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {p.components.map((c) => (
                    <div key={c.label} className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-1.5 text-sm">
                      <span>{c.label}</span>
                      <span className="text-gray-500">{money(c.annual_potential)} potential · now {money(c.current_pipeline)} · {Math.round(c.probability * 100)}%</span>
                    </div>
                  ))}
                </div>
                <ul className="mt-3 list-inside list-disc text-sm text-gray-600">
                  {p.key_moves.map((m, j) => <li key={j}>{m}</li>)}
                </ul>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-400">{data.assumptions}</p>
        </>
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><Planning /></AuthGate>;
}
