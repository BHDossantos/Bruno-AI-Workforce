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
  const { data: counter } = useFetch<{ pending: number }>(() => api.get<{ pending: number }>("/approvals/count"), [refresh]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  async function act(it: Item, action: "approve" | "reject") {
    setBusy(it.id); setMsg("");
    try {
      const r = await api.post<{ status?: string; sent?: boolean; note?: string }>(
        `/approvals/${it.type}/${it.id}/${action}`, {});
      if (action === "reject") setMsg("🗑️ Rejected.");
      else if (r.sent) setMsg("✅ Approved & sent.");
      else setMsg(`✅ Approved. ${r.note || ""}`.trim());
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  const pending = counter?.pending ?? data?.count ?? 0;

  async function approveAll() {
    if (!confirm(`Approve all ${pending} item(s) and push them through? Content is scheduled, replies are sent, and outreach sends up to today's safe limit — the rest goes out automatically over the next days.`)) return;
    setBusy("all"); setMsg("Approving everything…");
    try {
      const r = await api.post<{ approved: number; outreach_sent_now: number; replies_sent: number; content_scheduled: number; outreach_queued: number; note: string }>("/approvals/approve-all", {});
      setMsg(`✅ Approved ${r.approved}. Scheduled ${r.content_scheduled} posts, sent ${r.outreach_sent_now + r.replies_sent} now. ${r.note}`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  const items = data?.items || [];
  return (
    <div>
      <PageHeader title="Approval Queue"
        subtitle="Everything the AI prepared, highest-priority first (replies → hot/warm → strongest leads). Approve to send/schedule, or reject to skip."
        action={
          <button onClick={approveAll} disabled={busy === "all" || pending === 0}
            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-40">
            {busy === "all" ? "Approving…" : `Approve all${pending ? ` (${pending})` : ""}`}
          </button>
        } />
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
