"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

type QueueJob = {
  job_id: string; title: string; company: string; location?: string; remote: boolean;
  salary_min?: number; salary_max?: number; score: number;
  score_breakdown?: Record<string, number>; url?: string; source?: string;
  resume_match?: string; cover_letter?: string; status: string;
};

function ApplyQueue() {
  const [jobs, setJobs] = useState<QueueJob[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function load() {
    try { setJobs(await api.get<QueueJob[]>("/jobs/queue?limit=100")); }
    catch (e) { setMsg(`❌ ${e}`); }
  }
  useEffect(() => { load(); }, []);

  async function mark(job_id: string, status: string) {
    setBusy(job_id);
    try {
      await api.post("/jobs/queue/mark", { job_id, status });
      setJobs((j) => j.filter((x) => x.job_id !== job_id));  // drop from queue
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  function copy(text?: string) {
    if (text) navigator.clipboard.writeText(text);
  }

  return (
    <div>
      <PageHeader
        title="Job Apply Queue"
        subtitle="High-fit executive roles with your tailored materials — open, apply in one click, mark done. (No bot auto-submit — ToS-safe.)"
      />
      {msg && <p className="mb-4 rounded bg-gray-50 p-3 text-sm">{msg}</p>}
      {jobs.length === 0 ? (
        <p className="text-sm text-gray-500">Queue is empty. Run the Job Hunter agent to source roles.</p>
      ) : (
        <div className="space-y-3">
          {jobs.map((j) => (
            <div key={j.job_id} className="card">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="font-semibold">{j.title} <span className="text-gray-500">· {j.company}</span></div>
                  <div className="text-xs text-gray-500">
                    {j.location}{j.remote ? " · Remote" : ""}
                    {j.salary_min ? ` · $${(j.salary_min / 1000).toFixed(0)}k+` : ""}
                    {j.source ? ` · ${j.source}` : ""}
                  </div>
                </div>
                <span className="rounded-full bg-brand/10 px-2 py-0.5 text-xs font-semibold text-brand">
                  Fit {j.score}
                </span>
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                {j.url && (
                  <a href={j.url} target="_blank" rel="noreferrer" className="btn">
                    Open application ↗
                  </a>
                )}
                <button onClick={() => setOpen(open === j.job_id ? null : j.job_id)}
                        className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
                  {open === j.job_id ? "Hide materials" : "View materials"}
                </button>
                <button onClick={() => mark(j.job_id, "Applied")} disabled={busy === j.job_id}
                        className="rounded-lg bg-green-600 px-3 py-2 text-sm font-medium text-white hover:bg-green-700">
                  ✓ Applied
                </button>
                <button onClick={() => mark(j.job_id, "Skipped")} disabled={busy === j.job_id}
                        className="rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-600">
                  Skip
                </button>
              </div>

              {open === j.job_id && (
                <div className="mt-3 space-y-3 border-t border-gray-100 pt-3">
                  {j.resume_match && (
                    <div>
                      <div className="mb-1 flex items-center justify-between">
                        <span className="text-xs font-semibold text-gray-700">Resume match / talking points</span>
                        <button onClick={() => copy(j.resume_match)} className="text-xs text-brand hover:underline">Copy</button>
                      </div>
                      <pre className="whitespace-pre-wrap rounded bg-gray-50 p-3 text-sm">{j.resume_match}</pre>
                    </div>
                  )}
                  {j.cover_letter && (
                    <div>
                      <div className="mb-1 flex items-center justify-between">
                        <span className="text-xs font-semibold text-gray-700">Cover letter</span>
                        <button onClick={() => copy(j.cover_letter)} className="text-xs text-brand hover:underline">Copy</button>
                      </div>
                      <pre className="whitespace-pre-wrap rounded bg-gray-50 p-3 text-sm">{j.cover_letter}</pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><ApplyQueue /></AuthGate>;
}
