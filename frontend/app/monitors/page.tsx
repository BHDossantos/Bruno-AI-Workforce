"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

type Monitor = {
  id: string; name: string; url: string; business: string | null; method: string;
  interval_minutes: number; enabled: boolean; last_status: string; last_code: number | null;
  last_latency_ms: number | null; last_error: string | null; last_checked_at: string | null;
  consecutive_failures: number; uptime_pct: number; checks_total: number;
};
type Summary = { total: number; up: number; down: number; unknown: number };

const DOT: Record<string, string> = { up: "bg-emerald-500", down: "bg-red-500", unknown: "bg-gray-300" };
const LABEL: Record<string, string> = { up: "Up", down: "Down", unknown: "Not checked" };

function Monitors() {
  const [list, setList] = useState<Monitor[]>([]);
  const [sum, setSum] = useState<Summary | null>(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", url: "", business: "", interval_minutes: 5 });
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    const [m, s] = await Promise.all([
      api.get<Monitor[]>("/monitors"),
      api.get<Summary>("/monitors/summary"),
    ]);
    setList(m); setSum(s);
  }
  useEffect(() => { load().catch(() => {}); }, []);

  async function create() {
    if (!form.name.trim() || !form.url.trim()) { alert("Name and URL are required."); return; }
    await api.post("/monitors", { ...form, interval_minutes: Number(form.interval_minutes) || 5 });
    setOpen(false);
    setForm({ name: "", url: "", business: "", interval_minutes: 5 });
    await load();
  }
  async function checkNow(id: string) {
    setBusyId(id);
    try { await api.post(`/monitors/${id}/check`, {}); await load(); }
    finally { setBusyId(null); }
  }
  async function toggle(m: Monitor) { await api.patch(`/monitors/${m.id}`, { enabled: !m.enabled }); await load(); }
  async function remove(id: string) {
    if (!confirm("Delete this monitor?")) return;
    await api.del(`/monitors/${id}`); await load();
  }

  const stat = (label: string, val: string, tone = "") => (
    <div className="card"><div className={`text-2xl font-bold ${tone}`}>{val}</div><div className="text-xs uppercase text-gray-400">{label}</div></div>
  );

  return (
    <div>
      <PageHeader
        title="Uptime Monitors"
        subtitle="Watch your live apps and client sites — Bruno probes each one on its own schedule and flags outages."
        action={<button className="btn" onClick={() => setOpen((v) => !v)}>{open ? "Close" : "+ New monitor"}</button>}
      />

      {sum && (
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stat("Monitors", String(sum.total))}
          {stat("Up", String(sum.up), "text-emerald-600")}
          {stat("Down", String(sum.down), sum.down > 0 ? "text-red-600" : "")}
          {stat("Not checked", String(sum.unknown), "text-gray-400")}
        </div>
      )}

      {open && (
        <div className="card mb-4 space-y-3">
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder="Name (e.g. Backend API)" value={form.name}
                   onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input className="input" placeholder="https://…" value={form.url}
                   onChange={(e) => setForm({ ...form, url: e.target.value })} />
            <input className="input" placeholder="For (optional)" value={form.business}
                   onChange={(e) => setForm({ ...form, business: e.target.value })} />
            <label className="flex items-center gap-2 text-sm text-gray-500">
              Every<input type="number" min={1} className="input w-20" value={form.interval_minutes}
                          onChange={(e) => setForm({ ...form, interval_minutes: Number(e.target.value) })} />min
            </label>
          </div>
          <div className="text-right"><button className="btn" onClick={create}>Add monitor</button></div>
        </div>
      )}

      <div className="space-y-2">
        {list.length === 0 && <div className="card text-center text-gray-400">No monitors yet. Add your first URL above.</div>}
        {list.map((m) => (
          <div key={m.id} className={`card ${!m.enabled ? "opacity-60" : ""}`}>
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <span className={`h-2.5 w-2.5 flex-none rounded-full ${DOT[m.last_status] || DOT.unknown} ${m.last_status === "up" ? "animate-pulse" : ""}`} />
                <div className="min-w-0">
                  <div className="truncate font-semibold text-gray-900">{m.name}</div>
                  <a href={m.url} target="_blank" rel="noreferrer" className="truncate text-xs text-gray-400 hover:underline">{m.url}</a>
                </div>
              </div>
              <div className="flex items-center gap-4 text-right text-xs">
                <div>
                  <div className={`font-semibold ${m.last_status === "down" ? "text-red-600" : m.last_status === "up" ? "text-emerald-600" : "text-gray-400"}`}>{LABEL[m.last_status] || "—"}</div>
                  <div className="text-gray-400">{m.last_code ? `HTTP ${m.last_code}` : ""}{m.last_latency_ms != null ? ` · ${m.last_latency_ms}ms` : ""}</div>
                </div>
                <div className="hidden sm:block">
                  <div className="font-semibold text-gray-700">{m.uptime_pct}%</div>
                  <div className="text-gray-400">{m.checks_total} checks</div>
                </div>
                <div className="flex gap-2">
                  <button className="text-brand" onClick={() => checkNow(m.id)} disabled={busyId === m.id}>{busyId === m.id ? "…" : "Check"}</button>
                  <button className="text-gray-400" onClick={() => toggle(m)}>{m.enabled ? "Pause" : "Resume"}</button>
                  <button className="text-gray-300 hover:text-red-500" onClick={() => remove(m.id)}>✕</button>
                </div>
              </div>
            </div>
            {m.last_status === "down" && m.last_error && (
              <div className="mt-2 rounded bg-red-50 px-2 py-1 text-xs text-red-600">
                {m.consecutive_failures}× failing · {m.last_error}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Monitors /></AuthGate>;
}
