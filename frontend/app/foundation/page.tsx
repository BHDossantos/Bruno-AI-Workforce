"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type Grant = {
  id: string; title: string; funder: string | null; source: string | null; url: string | null;
  amount: number | null; deadline: string | null; category: string | null; summary: string | null;
  match_score: number; status: string;
};
type Summary = { total: number; pipeline_amount: number; by_status: Record<string, number> };
type Deadline = { id: string; title: string; kind: string; due_date: string | null; status: string; notes: string | null };

const STATUSES = ["New", "Reviewing", "Applying", "Submitted", "Won", "Lost", "Skipped"];

function money(n: number | null) {
  if (!n) return "—";
  return n >= 1000 ? `$${(n / 1000).toFixed(0)}k` : `$${n}`;
}

function Foundation() {
  const [refresh, setRefresh] = useState(0);
  const [status, setStatus] = useState("");
  const { data, loading, error, reload } = useFetch<Grant[]>(
    () => api.get<Grant[]>(`/grants?limit=200${status ? `&status=${status}` : ""}`), [status, refresh]);
  const { data: sum } = useFetch<Summary>(() => api.get<Summary>("/grants/summary"), [refresh]);
  const { data: deadlines } = useFetch<Deadline[]>(() => api.get<Deadline[]>("/grants/deadlines"), [refresh]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  async function doneDeadline(id: string) {
    setBusy(id);
    try { await api.post(`/grants/deadlines/${id}/done`, {}); setRefresh((n) => n + 1); }
    catch (e) { setMsg(`❌ ${e}`); } finally { setBusy(null); }
  }

  async function sourceNow() {
    setBusy("source"); setMsg("Searching grants… this can take a minute.");
    try {
      const r = await api.post<{ result?: { summary?: string } }>("/grants/source", {});
      setMsg(`✅ ${r.result?.summary || "Done"}`); setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); } finally { setBusy(null); }
  }

  async function setGrantStatus(id: string, s: string) {
    setBusy(id);
    try { await api.post(`/grants/${id}/status`, { status: s }); setRefresh((n) => n + 1); }
    catch (e) { setMsg(`❌ ${e}`); } finally { setBusy(null); }
  }

  return (
    <div>
      <PageHeader title="Foundation — Grants"
        subtitle="Esposito–Dossantos Foundation · Empowering Lives. Inspiring Futures. Opportunities scored by mission fit."
        action={<button className="btn" disabled={busy === "source"} onClick={sourceNow}>
          {busy === "source" ? "Searching…" : "Find grants now"}
        </button>} />

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="card"><div className="text-xs text-gray-500">Opportunities</div><div className="text-3xl font-bold">{sum?.total ?? "—"}</div></div>
        <div className="card"><div className="text-xs text-gray-500">Pipeline (identified)</div><div className="text-3xl font-bold text-brand">{money(sum?.pipeline_amount ?? null)}</div></div>
        <div className="card"><div className="text-xs text-gray-500">In progress</div><div className="text-3xl font-bold">{(sum?.by_status?.Reviewing || 0) + (sum?.by_status?.Applying || 0)}</div></div>
        <div className="card"><div className="text-xs text-gray-500">Submitted / Won</div><div className="text-3xl font-bold">{(sum?.by_status?.Submitted || 0) + (sum?.by_status?.Won || 0)}</div></div>
      </div>

      {msg && <p className="mb-2 text-sm text-gray-600">{msg}</p>}

      {deadlines && deadlines.length > 0 && (
        <div className="card mb-4">
          <h2 className="mb-2 text-sm font-semibold text-gray-700">⏰ Upcoming deadlines</h2>
          <div className="space-y-1">
            {deadlines.slice(0, 8).map((d) => (
              <div key={d.id} className="flex items-center justify-between gap-3 text-sm">
                <span className="min-w-0">
                  <span className="truncate">{d.title}</span>
                  <span className="ml-2 text-xs text-gray-400">{d.kind}{d.due_date ? ` · due ${d.due_date}` : " · no date set"}</span>
                </span>
                <button onClick={() => doneDeadline(d.id)} disabled={busy === d.id}
                  className="rounded border border-gray-300 px-2 py-0.5 text-xs text-gray-500">Done</button>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-gray-400">Tracking + alerts only — confirm and file with your accountant/attorney.</p>
        </div>
      )}

      <div className="mb-3">
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}

      <div className="space-y-2">
        {(data || []).map((g) => (
          <div key={g.id} className="card">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="badge bg-brand/10 text-brand-dark">{g.match_score}</span>
                  <span className="font-medium">{g.url ? <a href={g.url} target="_blank" rel="noreferrer" className="text-brand hover:underline">{g.title} ↗</a> : g.title}</span>
                </div>
                <div className="mt-1 text-xs text-gray-400">
                  {g.funder || "—"}{g.category ? ` · ${g.category}` : ""}{g.source ? ` · ${g.source}` : ""}
                  {g.amount ? ` · ${money(g.amount)}` : ""}{g.deadline ? ` · due ${g.deadline}` : ""}
                </div>
                {g.summary && <p className="mt-1 max-w-2xl text-xs text-gray-500">{g.summary}</p>}
              </div>
              <select value={g.status} disabled={busy === g.id}
                onChange={(e) => setGrantStatus(g.id, e.target.value)}
                className="rounded-lg border border-gray-300 px-2 py-1 text-sm">
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>
        ))}
        {data && data.length === 0 && (
          <div className="card text-sm text-gray-400">No grants yet — hit “Find grants now”.</div>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Foundation /></AuthGate>;
}
