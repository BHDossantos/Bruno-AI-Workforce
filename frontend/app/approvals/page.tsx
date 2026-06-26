"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, TempBadge, useFetch, LoadState } from "@/components/ui";

type Item = {
  type: string; id: string; risk: string; title: string;
  business: string | null; preview: string; to?: string; created_at: string | null;
  temperature?: string; fit?: number;
};
type Queue = { count: number; items: Item[] };

const RISK: Record<string, string> = {
  low: "bg-green-100 text-green-700", medium: "bg-amber-100 text-amber-700", high: "bg-red-100 text-red-700",
};

function Approvals() {
  const [refresh, setRefresh] = useState(0);
  const { data, loading, error, reload } = useFetch<Queue>(() => api.get<Queue>("/approvals"), [refresh]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  async function act(it: Item, action: "approve" | "reject") {
    setBusy(it.id); setMsg("");
    try {
      const r = await api.post<{ status?: string }>(`/approvals/${it.type}/${it.id}/${action}`, {});
      setMsg(action === "approve" ? `✅ Approved — ${r.status || "done"}.` : "🗑️ Rejected.");
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  const items = data?.items || [];
  return (
    <div>
      <PageHeader title="Approval Queue"
        subtitle="Everything the AI prepared, highest-priority first (replies → hot/warm → strongest leads). Approve to send/schedule, or reject to skip." />
      {msg && <p className="mb-3 text-sm text-gray-600">{msg}</p>}
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}

      {data && items.length === 0 && (
        <div className="card text-sm text-gray-500">🎉 Nothing waiting — the queue is clear.</div>
      )}

      <div className="space-y-3">
        {items.map((it) => (
          <div key={`${it.type}-${it.id}`} className="card">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`badge ${RISK[it.risk] || "bg-gray-100 text-gray-600"}`}>{it.risk}</span>
                  {it.temperature && <TempBadge t={it.temperature} />}
                  {typeof it.fit === "number" && <span className="badge bg-brand/10 text-brand-dark">fit {it.fit}</span>}
                  <span className="font-medium">{it.title}</span>
                </div>
                <div className="mt-1 text-xs text-gray-400">
                  {it.type}{it.business ? ` · ${it.business}` : ""}{it.to ? ` · ${it.to}` : ""}
                </div>
                <p className="mt-2 max-w-2xl text-sm text-gray-600">{it.preview || "(no preview)"}</p>
              </div>
              <div className="flex gap-2">
                <button onClick={() => act(it, "approve")} disabled={busy === it.id}
                  className="rounded-lg bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-40">
                  {busy === it.id ? "…" : "Approve"}
                </button>
                <button onClick={() => act(it, "reject")} disabled={busy === it.id}
                  className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-600 disabled:opacity-40">
                  Reject
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Approvals /></AuthGate>;
}
