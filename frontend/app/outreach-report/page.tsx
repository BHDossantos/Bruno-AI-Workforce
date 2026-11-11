"use client";

import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, KpiCard, LoadState } from "@/components/ui";

type Day = { date: string; sent: number; replies: number };
type Report = {
  days: number;
  totals: { delivery_confirmed: number; delivery_unconfirmed: number; legacy_replied_outbound_undated: number; sent: number; replies: number; reply_rate: number; warm: number; hot: number; actionable: number };
  funnel: { cold: number; warm: number; hot: number; dead: number };
  daily: Day[];
};

function OutreachReport() {
  const { data, loading, error, reload } = useFetch<Report>(() => api.get<Report>("/analytics/outreach?days=30"));

  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;

  const maxSent = Math.max(1, ...data.daily.map((d) => d.sent));

  return (
    <div>
      <PageHeader
        title="Outreach Performance"
        subtitle="Is the client machine working and trending up? The daily send→reply trend, your cold/warm/hot funnel, and reply rate over the last 30 days."
      />

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="Recorded sends (30d)" value={data.totals.sent.toLocaleString()} />
        <KpiCard label="Replies (30d)" value={data.totals.replies.toLocaleString()} hint="Observed inbound responses; mailbox coverage may be incomplete" />
        <KpiCard label="Hot leads" value={data.totals.hot.toLocaleString()} hint="buying signals — act now" />
        <KpiCard label="Warm leads" value={data.totals.warm.toLocaleString()} hint="engaged / replied" />
      </div>

      <div className="card mb-6 text-sm">
        <p>{data.totals.delivery_confirmed ?? 0} sends have recorded delivery evidence; {data.totals.delivery_unconfirmed ?? data.totals.sent} remain unconfirmed.</p>
        <p>{data.totals.legacy_replied_outbound_undated ?? 0} legacy outbound records are marked replied without a reply timestamp. They are not assigned to this reporting window.</p>
        <p>Zero observed replies is not proof that nobody replied. <a className="underline" href="/mailboxes">Check mailbox connections</a> and review sync health before relying on this count.</p>
      </div>
      {/* Funnel */}
      <div className="card mb-6">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Lead funnel (all businesses)</div>
        <div className="flex flex-wrap gap-2 text-sm">
          <span className="badge bg-gray-100 text-gray-600">Cold {data.funnel.cold.toLocaleString()}</span>
          <span className="badge bg-amber-100 text-amber-700">Warm {data.funnel.warm.toLocaleString()}</span>
          <span className="badge bg-rose-100 text-rose-700">Hot {data.funnel.hot.toLocaleString()}</span>
          <span className="badge bg-gray-100 text-gray-400">Dead {data.funnel.dead.toLocaleString()}</span>
        </div>
        {data.totals.actionable > 0 && (
          <p className="mt-2 text-xs text-gray-500">
            <b>{data.totals.actionable}</b> warm/hot lead{data.totals.actionable === 1 ? "" : "s"} worth acting on now — see the Unified Inbox or Follow-ups.
          </p>
        )}
      </div>

      {/* Daily send/reply trend */}
      <div className="card">
        <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400">Daily sends &amp; replies</div>
        <div className="flex items-end gap-[3px] overflow-x-auto" style={{ height: 160 }}>
          {data.daily.map((d) => (
            <div key={d.date} className="flex flex-1 flex-col items-center justify-end" style={{ minWidth: 8 }} title={`${d.date}: ${d.sent} sent, ${d.replies} replies`}>
              <div className="w-full rounded-t bg-emerald-400" style={{ height: `${(d.replies / maxSent) * 140}px` }} />
              <div className="w-full rounded-t bg-brand" style={{ height: `${(d.sent / maxSent) * 140}px` }} />
            </div>
          ))}
        </div>
        <div className="mt-2 flex gap-4 text-xs text-gray-500">
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-brand" /> Sent</span>
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-emerald-400" /> Replies</span>
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><OutreachReport /></AuthGate>;
}
