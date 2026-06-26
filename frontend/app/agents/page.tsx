"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type Health = {
  key: string; name: string; runs: number; successes: number; errors: number;
  success_rate: number | null; avg_duration_sec: number | null;
  last_run_at: string | null; last_status: string | null; last_error: string | null;
  suggestion: string;
};

function bar(rate: number | null) {
  if (rate === null) return "bg-gray-200";
  return rate >= 90 ? "bg-green-500" : rate >= 60 ? "bg-amber-500" : "bg-red-500";
}

function Agents() {
  const [refresh, setRefresh] = useState(0);
  const { data, loading, error, reload } = useFetch<Health[]>(() => api.get<Health[]>("/agents/health"), [refresh]);
  const [busy, setBusy] = useState<string | null>(null);

  async function run(key: string) {
    setBusy(key);
    try { await api.post(`/agents/${key}/run`, {}); setRefresh((n) => n + 1); }
    finally { setBusy(null); }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Agent Performance"
        subtitle="Each agent's self-report — success rate, speed, and what to fix. The workforce watches itself." />

      <div className="space-y-3">
        {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}
        {(data || []).map((a) => (
          <div key={a.key} className="card">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="font-semibold">{a.name}</div>
                <div className="text-xs text-gray-400">
                  {a.runs} runs · {a.successes} ok · {a.errors} errors
                  {a.avg_duration_sec !== null && ` · ~${a.avg_duration_sec}s avg`}
                  {a.last_run_at && ` · last ${a.last_run_at.slice(0, 10)}`}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <div className="text-2xl font-bold">{a.success_rate ?? "—"}<span className="text-sm text-gray-400">%</span></div>
                  <div className="text-[10px] text-gray-400">success</div>
                </div>
                <button onClick={() => run(a.key)} disabled={busy === a.key}
                  className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm disabled:opacity-40">
                  {busy === a.key ? "Running…" : "Run now"}
                </button>
              </div>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded bg-gray-100">
              <div className={`h-full ${bar(a.success_rate)}`} style={{ width: `${a.success_rate ?? 0}%` }} />
            </div>
            <p className="mt-2 text-sm text-gray-600">💡 {a.suggestion}</p>
            {a.last_error && <p className="mt-1 text-xs text-red-500">⚠ {a.last_error}</p>}
          </div>
        ))}
        {data && data.length === 0 && <div className="card text-sm text-gray-400">No agents have run yet.</div>}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Agents /></AuthGate>;
}
