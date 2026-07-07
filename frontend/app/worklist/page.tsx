"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, TempBadge, StatusBadge, useFetch, LoadState } from "@/components/ui";

// The Call List — the one place to WORK your leads. Hottest leads sort first
// (EverQuote/in-market at the top), and every lead is one tap from a call, text,
// email, and a logged outcome. This is where you live after importing a list.

type Lead = {
  id: string;
  owner_name?: string | null;
  company_name?: string | null;
  phone?: string | null;
  email?: string | null;
  category?: string | null;
  reason?: string | null;   // e.g. "EverQuote auto lead — 2007 Ford Focus, currently with GEICO"
  status: string;
  temperature?: string | null;
  times_contacted?: number;
  last_contacted_at?: string | null;
};

const STATUSES = ["New", "Contacted", "Quoted", "Closed Won", "Closed Lost"];
const FILTERS: { key: string; label: string }[] = [
  { key: "", label: "All" },
  { key: "hot", label: "🔥 Hot" },
  { key: "warm", label: "🌤️ Warm" },
  { key: "cold", label: "❄️ Cold" },
];

function leadName(l: Lead) {
  return l.owner_name || l.company_name || l.email || "Lead";
}

function since(iso?: string | null) {
  if (!iso) return "never contacted";
  const d = new Date(iso);
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (days <= 0) return "contacted today";
  if (days === 1) return "contacted yesterday";
  return `contacted ${days}d ago`;
}

export default function WorkListPage() {
  const [temp, setTemp] = useState("");
  const [q, setQ] = useState("");
  const [tick, setTick] = useState(0);
  const { data, loading, error, reload } = useFetch<Lead[]>(
    () => api.get<Lead[]>(`/leads?limit=300${temp ? `&temperature=${temp}` : ""}`),
    [temp, tick]
  );

  // Per-lead action state: a status message + a busy flag, keyed by lead id.
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [note, setNote] = useState<Record<string, string>>({});

  const leads = useMemo(() => {
    const rows = data || [];
    const needle = q.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((l) =>
      leadName(l).toLowerCase().includes(needle) ||
      (l.phone || "").includes(needle) ||
      (l.reason || "").toLowerCase().includes(needle)
    );
  }, [data, q]);

  async function act(id: string, label: string, fn: () => Promise<unknown>) {
    setBusy((b) => ({ ...b, [id]: true }));
    setNote((n) => ({ ...n, [id]: `${label}…` }));
    try {
      await fn();
      setNote((n) => ({ ...n, [id]: `✅ ${label}` }));
    } catch (e) {
      setNote((n) => ({ ...n, [id]: `❌ ${e instanceof Error ? e.message : label + " failed"}` }));
    } finally {
      setBusy((b) => ({ ...b, [id]: false }));
    }
  }

  const call = (id: string) => act(id, "Ringing your phone", () => api.post(`/calls/lead/${id}`, {}));
  const text = (id: string) => act(id, "Text sent", () => api.post(`/leads/${id}/send-text`, {}));
  const email = (id: string) => act(id, "Email sent", () => api.post(`/leads/${id}/send-email`, {}));
  const logCall = (id: string, outcome: string) =>
    act(id, `Logged: ${outcome}`, () => api.post(`/leads/${id}/log-call`, { outcome }));
  const setStatus = (id: string, status: string) =>
    act(id, `Status → ${status}`, () => api.post(`/leads/${id}/status`, { status }).then(reload));

  return (
    <AuthGate>
      <PageHeader
        title="📞 Call List"
        subtitle="Your leads to work — hottest first. Call, text, email, and log every outcome right here."
        action={
          <Link href="/insurance-commander" className="rounded-lg bg-brand-dark px-3 py-2 text-sm font-medium text-white hover:opacity-90">
            + Import leads
          </Link>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setTemp(f.key)}
            className={`rounded-full px-3 py-1.5 text-sm font-medium ${
              temp === f.key ? "bg-brand-dark text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {f.label}
          </button>
        ))}
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search name, phone, vehicle…"
          className="ml-auto w-64 max-w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
        <button onClick={reload} className="rounded-lg border border-gray-300 px-3 py-2 text-sm hover:bg-gray-50" title="Refresh">↻</button>
      </div>

      <LoadState loading={loading} error={error} onRetry={reload}
        empty={!loading && !error && !leads.length
          ? "No leads yet — import a CSV on the Insurance Commander page and they'll appear here, hottest first."
          : undefined} />

      <div className="space-y-3">
        {leads.map((l) => (
          <div key={l.id} className="card">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Link href={`/leads/${l.id}`} className="font-semibold text-brand-dark hover:underline">
                    {leadName(l)}
                  </Link>
                  <TempBadge t={l.temperature} />
                  <StatusBadge status={l.status} />
                </div>
                <p className="mt-1 text-sm text-gray-600">{l.reason || l.category || "Lead"}</p>
                <p className="mt-0.5 text-xs text-gray-400">
                  {l.phone ? (
                    <a href={`tel:${l.phone}`} className="font-medium text-gray-600 hover:underline">{l.phone}</a>
                  ) : "no phone"}
                  {" · "}{l.times_contacted || 0} touches · {since(l.last_contacted_at)}
                </p>
              </div>
              {note[l.id] && <span className="text-xs text-gray-500">{note[l.id]}</span>}
            </div>

            {/* Reach out — one tap each, auto-personalized */}
            <div className="mt-3 flex flex-wrap gap-2">
              <button disabled={busy[l.id] || !l.phone} onClick={() => call(l.id)}
                className="rounded-lg bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-40">
                📞 Call
              </button>
              <button disabled={busy[l.id] || !l.phone} onClick={() => text(l.id)}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40">
                💬 Text
              </button>
              <button disabled={busy[l.id] || !l.email} onClick={() => email(l.id)}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40">
                📧 Email
              </button>
            </div>

            {/* Log the call outcome + move the deal */}
            <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-2">
              <span className="text-xs font-medium text-gray-400">Log call:</span>
              {["No answer", "Left voicemail", "Reached"].map((o) => (
                <button key={o} disabled={busy[l.id]} onClick={() => logCall(l.id, o)}
                  className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-700 hover:bg-gray-200 disabled:opacity-40">
                  {o}
                </button>
              ))}
              <span className="ml-2 text-xs font-medium text-gray-400">Status:</span>
              <select value={l.status} disabled={busy[l.id]} onChange={(e) => setStatus(l.id, e.target.value)}
                className="rounded-lg border border-gray-300 px-2 py-1 text-xs">
                {(STATUSES.includes(l.status) ? STATUSES : [l.status, ...STATUSES]).map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          </div>
        ))}
      </div>
    </AuthGate>
  );
}
