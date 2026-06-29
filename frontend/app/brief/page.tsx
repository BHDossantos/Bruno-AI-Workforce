"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type Report = {
  report_date: string;
  summary: string;
  emailed: boolean;
  metrics: Record<string, number> | null;
  top_actions: {
    summary?: string;
    top_actions?: { action: string; why: string; area: string }[];
    urgent_follow_ups?: string[];
    recommended_focus?: string;
  } | null;
};
type Item = {
  type: string; id: string; risk: string; title: string;
  business: string | null; preview: string; to?: string;
};
type Queue = { count: number; items: Item[] };

function Brief() {
  const { data: report, loading, error, reload } = useFetch<Report | null>(() => api.get<Report | null>("/reports/latest"));
  const [tick, setTick] = useState(0);
  const { data: queue } = useFetch<Queue>(() => api.get<Queue>("/approvals?limit=5"), [tick]);
  const [busy, setBusy] = useState<string | null>(null);
  const [actMsg, setActMsg] = useState("");

  async function act(it: Item, action: "approve" | "reject") {
    setBusy(it.id); setActMsg("");
    try {
      const r = await api.post<{ sent?: boolean; note?: string }>(`/approvals/${it.type}/${it.id}/${action}`, {});
      setActMsg(action === "reject" ? "🗑️ Rejected." : r.sent ? "✅ Approved & sent." : `✅ Approved. ${r.note || ""}`.trim());
      setTick((t) => t + 1);
    } catch (e) { setActMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  if (loading || error) return <LoadState loading={loading} error={error} onRetry={reload} />;
  if (!report) return <div><PageHeader title="Daily Brief" /><p className="text-gray-500">No report yet. Run the CEO Dashboard agent.</p></div>;

  const b = report.top_actions;
  const pending = queue?.items || [];
  return (
    <div className="space-y-6">
      <PageHeader
        title="Daily Brief"
        subtitle={`Executive brief — ${report.report_date}`}
        action={<span className={`badge ${report.emailed ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"}`}>{report.emailed ? "Emailed" : "Not emailed"}</span>}
      />

      <div className="card">
        <h2 className="mb-2 font-semibold">Summary</h2>
        <p className="text-sm text-gray-700">{report.summary || b?.summary}</p>
        {b?.recommended_focus && <p className="mt-3 rounded bg-brand/10 p-3 text-sm font-medium text-brand-dark">🎯 {b.recommended_focus}</p>}
      </div>

      {/* Act now — approve/send the highest-priority queued items right here */}
      <div className="card">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold">Approve &amp; send — top of the queue</h2>
          <a href="/approvals" className="text-sm text-brand">Open full queue{queue?.count ? ` (${queue.count})` : ""} ↗</a>
        </div>
        {actMsg && <p className="mb-2 text-sm text-gray-600">{actMsg}</p>}
        {pending.length === 0 ? (
          <p className="text-sm text-gray-500">🎉 Nothing waiting — the queue is clear.</p>
        ) : (
          <div className="space-y-2">
            {pending.map((it) => (
              <div key={`${it.type}-${it.id}`} className="flex items-start justify-between gap-3 rounded-lg border border-gray-100 p-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium">{it.title}</p>
                  <p className="truncate text-xs text-gray-500">{it.type}{it.to ? ` · ${it.to}` : ""} — {it.preview}</p>
                </div>
                <div className="flex shrink-0 gap-2">
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
            ))}
          </div>
        )}
      </div>

      {b?.top_actions && b.top_actions.length > 0 && (
        <div className="card">
          <h2 className="mb-3 font-semibold">Top ROI actions today</h2>
          <ol className="space-y-2">
            {b.top_actions.map((a, i) => (
              <li key={i} className="flex gap-3">
                <span className="font-bold text-brand">{i + 1}.</span>
                <div>
                  <p className="text-sm font-medium">{a.action} <span className="badge bg-gray-100 text-gray-600">{a.area}</span></p>
                  <p className="text-xs text-gray-500">{a.why}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      {report.metrics && (
        <div className="card">
          <h2 className="mb-3 font-semibold">KPIs</h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {Object.entries(report.metrics).map(([k, v]) => (
              <div key={k} className="rounded-lg bg-gray-50 p-3">
                <p className="text-xs uppercase text-gray-500">{k.replace(/_/g, " ")}</p>
                <p className="text-xl font-bold text-brand-dark">{v}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><Brief /></AuthGate>;
}
