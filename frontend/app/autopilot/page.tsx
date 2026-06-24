"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

type Job = { id: string; title: string; company: string; url: string | null };
type Task = {
  id: string; target_url: string | null; status: string; mode: string | null;
  field_map: Record<string, unknown> | null; result: Record<string, unknown> | null;
  automation_ready: boolean; created_at: string | null;
};

const BADGE: Record<string, string> = {
  prepared: "bg-gray-100 text-gray-600", running: "bg-blue-100 text-blue-700",
  needs_review: "bg-amber-100 text-amber-700", submitted: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
};

function Autopilot() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  async function load() {
    const [j, t] = await Promise.all([
      api.get<Job[]>("/jobs?limit=15").catch(() => []),
      api.get<Task[]>("/browser/tasks"),
    ]);
    setJobs(j); setTasks(t);
  }
  useEffect(() => { load().catch(() => {}); }, []);

  const ready = tasks[0]?.automation_ready;

  async function prepare(jobId: string) {
    setBusy(jobId); setMsg("");
    try { await api.post(`/browser/apply/${jobId}`, {}); setMsg("Prepared — see tasks below."); await load(); }
    catch (e) { setMsg(String(e)); } finally { setBusy(null); }
  }
  async function run(taskId: string) {
    setBusy(taskId); setMsg("");
    try {
      const t = await api.post<Task>(`/browser/tasks/${taskId}/run`, {});
      setMsg(`Task ${t.status}${t.mode ? ` (${t.mode})` : ""}.`); await load();
    } catch (e) { setMsg(String(e)); } finally { setBusy(null); }
  }

  return (
    <div>
      <PageHeader title="Application Autopilot"
        subtitle="The browser worker prepares each application (fields, screening answers, cover letter) and — when enabled — fills the form for your review." />

      <div className={`mb-4 rounded-lg px-3 py-2 text-sm ${ready ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"}`}>
        {ready ? "🤖 Browser automation is ON — tasks fill the form and stop for your review."
               : "📝 Assist mode — tasks prepare a ready-to-submit package (enable Playwright + BROWSER_AUTOMATION_ENABLED for full automation)."}
      </div>
      {msg && <p className="mb-3 text-sm text-gray-600">{msg}</p>}

      <h2 className="mb-2 text-sm font-semibold text-gray-700">Jobs ready to apply</h2>
      <div className="mb-6 space-y-2">
        {jobs.map((j) => (
          <div key={j.id} className="card flex items-center justify-between">
            <div><div className="font-medium">{j.title}</div><div className="text-xs text-gray-500">{j.company}</div></div>
            <button className="btn" disabled={busy === j.id} onClick={() => prepare(j.id)}>
              {busy === j.id ? "Preparing…" : "Prepare Autopilot"}
            </button>
          </div>
        ))}
        {jobs.length === 0 && <p className="text-sm text-gray-400">No jobs yet — run the Job Hunter agent.</p>}
      </div>

      <h2 className="mb-2 text-sm font-semibold text-gray-700">Autopilot tasks</h2>
      <div className="space-y-2">
        {tasks.map((t) => (
          <div key={t.id} className="card">
            <div className="flex items-center justify-between">
              <a href={t.target_url || "#"} target="_blank" rel="noreferrer" className="text-sm font-medium text-brand">
                {t.target_url || "application"} ↗
              </a>
              <div className="flex items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-xs ${BADGE[t.status] || "bg-gray-100"}`}>{t.status}{t.mode ? ` · ${t.mode}` : ""}</span>
                {["prepared", "needs_review", "failed"].includes(t.status) && (
                  <button className="rounded-lg border border-gray-300 px-3 py-1 text-sm" disabled={busy === t.id} onClick={() => run(t.id)}>
                    {busy === t.id ? "Running…" : t.status === "prepared" ? "Run" : "Re-run"}
                  </button>
                )}
              </div>
            </div>
            {t.field_map?.answers !== undefined && (
              <details className="mt-2 text-xs text-gray-600">
                <summary className="cursor-pointer">Prepared answers & cover letter</summary>
                <pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-2">
                  {JSON.stringify(t.field_map, null, 2)}
                </pre>
              </details>
            )}
            {t.result?.filled !== undefined && (
              <div className="mt-1 text-xs text-gray-500">Filled {(t.result.filled as string[]).length} fields.</div>
            )}
          </div>
        ))}
        {tasks.length === 0 && <p className="text-sm text-gray-400">No tasks yet — prepare one above.</p>}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Autopilot /></AuthGate>;
}
