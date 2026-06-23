"use client";

import { api } from "@/lib/api";
import { AuthGate, KpiCard, PageHeader, useFetch } from "@/components/ui";
import { useState } from "react";

type Summary = {
  date: string;
  jobs_found: number;
  insurance_leads: number;
  restaurant_prospects: number;
  music_playlists: number;
  instagram_targets: number;
  totals: { jobs: number; leads: number; restaurants: number };
};

type Agent = { key: string; name: string; schedule_cron: string; last_run_at: string | null };

const TARGETS: Record<string, number> = {
  jobs_found: 25,
  insurance_leads: 200,
  restaurant_prospects: 100,
  music_playlists: 50,
  instagram_targets: 100,
};

function Dashboard() {
  const { data: s, loading } = useFetch<Summary>(() => api.get<Summary>("/dashboard/summary"));
  const { data: agents } = useFetch<Agent[]>(() => api.get<Agent[]>("/agents"));
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState("");

  async function runAll() {
    setRunning(true);
    setMsg("");
    try {
      await api.post("/agents/run-all");
      setMsg("All agents executed. Refresh to see updated KPIs.");
    } catch (e) {
      setMsg(String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Home Dashboard"
        subtitle={s ? `Daily KPI summary — ${s.date}` : "Daily KPI summary"}
        action={
          <button className="btn" onClick={runAll} disabled={running}>
            {running ? "Running…" : "Run all agents now"}
          </button>
        }
      />
      {msg && <p className="mb-4 rounded bg-brand/10 p-3 text-sm text-brand-dark">{msg}</p>}
      {loading && <p className="text-gray-400">Loading KPIs…</p>}
      {s && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <KpiCard label="Jobs today" value={s.jobs_found} hint={`Goal ${TARGETS.jobs_found}`} />
          <KpiCard label="Insurance leads" value={s.insurance_leads} hint={`Goal ${TARGETS.insurance_leads}`} />
          <KpiCard label="Restaurants" value={s.restaurant_prospects} hint={`Goal ${TARGETS.restaurant_prospects}`} />
          <KpiCard label="Playlists" value={s.music_playlists} hint={`Goal ${TARGETS.music_playlists}`} />
          <KpiCard label="IG targets" value={s.instagram_targets} hint={`Goal ${TARGETS.instagram_targets}`} />
        </div>
      )}

      <h2 className="mb-3 mt-8 text-lg font-semibold">Agents</h2>
      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">Agent</th>
              <th className="th">Schedule (cron)</th>
              <th className="th">Last run</th>
            </tr>
          </thead>
          <tbody>
            {(agents || []).map((a) => (
              <tr key={a.key} className="border-t border-gray-100">
                <td className="td font-medium">{a.name}</td>
                <td className="td font-mono text-xs">{a.schedule_cron}</td>
                <td className="td">{a.last_run_at ? new Date(a.last_run_at).toLocaleString() : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function HomePage() {
  return (
    <AuthGate>
      <Dashboard />
    </AuthGate>
  );
}
