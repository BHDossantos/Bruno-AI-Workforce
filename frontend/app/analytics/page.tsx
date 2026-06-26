"use client";

import { api } from "@/lib/api";
import { AuthGate, PageHeader, KpiCard, useFetch, LoadState } from "@/components/ui";

type Stage = { stage: string; count: number };
type Overview = {
  kpis: Record<string, number>;
  funnel: Stage[];
  channels: Record<string, Stage[]>;
  activity_14d: { date: string; sent: number; replied: number }[];
};

function Funnel({ stages }: { stages: Stage[] }) {
  const max = Math.max(1, ...stages.map((s) => s.count));
  return (
    <div className="space-y-2">
      {stages.map((s) => (
        <div key={s.stage} className="flex items-center gap-3">
          <div className="w-24 shrink-0 text-sm text-gray-600">{s.stage}</div>
          <div className="h-6 flex-1 overflow-hidden rounded bg-gray-100">
            <div className="flex h-full items-center justify-end rounded bg-brand px-2 text-xs font-medium text-white"
                 style={{ width: `${Math.max(6, (s.count / max) * 100)}%` }}>
              {s.count}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function Analytics() {
  const { data, loading, error, reload } = useFetch<Overview>(() => api.get<Overview>("/analytics/overview"));
  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;
  const k = data.kpis;
  const maxAct = Math.max(1, ...data.activity_14d.map((a) => Math.max(a.sent, a.replied)));

  return (
    <div className="space-y-8">
      <PageHeader title="Funnel Analytics" subtitle="How your outreach is performing across every channel" />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="Leads sourced" value={k.leads_total + k.restaurant_prospects} />
        <KpiCard label="Emails sent" value={k.emails_sent} hint={`${k.emails_drafted} drafted`} />
        <KpiCard label="Replies" value={k.replies} hint={`${k.reply_rate_pct}% reply rate`} />
        <KpiCard label="Interested" value={k.interested} hint={`${k.won} won`} />
        <KpiCard label="SMS sent" value={k.sms_sent} />
        <KpiCard label="Jobs queued" value={k.jobs_queued} hint={`${k.jobs_applied} applied`} />
      </div>

      <div className="card">
        <h2 className="mb-3 font-semibold">Overall funnel</h2>
        <Funnel stages={data.funnel} />
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="card">
          <h2 className="mb-3 font-semibold">Insurance</h2>
          <Funnel stages={data.channels.insurance || []} />
        </div>
        <div className="card">
          <h2 className="mb-3 font-semibold">SavoryMind (restaurants)</h2>
          <Funnel stages={data.channels.savorymind || []} />
        </div>
      </div>

      <div className="card">
        <h2 className="mb-3 font-semibold">Last 14 days</h2>
        <div className="flex items-end gap-1" style={{ height: 120 }}>
          {data.activity_14d.map((a) => (
            <div key={a.date} className="flex flex-1 flex-col items-center justify-end gap-0.5" title={`${a.date}: ${a.sent} sent, ${a.replied} replies`}>
              <div className="w-full rounded-t bg-brand/30" style={{ height: `${(a.sent / maxAct) * 90}px` }} />
              <div className="w-full rounded-t bg-green-500" style={{ height: `${(a.replied / maxAct) * 90}px` }} />
            </div>
          ))}
        </div>
        <div className="mt-2 flex gap-4 text-xs text-gray-500">
          <span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-brand/30" />Sent</span>
          <span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-green-500" />Replies</span>
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Analytics /></AuthGate>;
}
