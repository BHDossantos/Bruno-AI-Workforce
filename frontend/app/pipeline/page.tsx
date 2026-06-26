"use client";

import { api } from "@/lib/api";
import { AuthGate, PageHeader, KpiCard, useFetch, LoadState } from "@/components/ui";

type Stage = { stage: string; count: number };
type Named = { name: string; count: number };
type Biz = {
  total: number;
  funnel: Stage[];
  emailed: number;
  replied: number;
  won: number;
  scope: string;
  value?: number;
  avg_score?: number;
  top_industries?: Named[];
  top_cities?: Named[];
};
type Pipeline = { businesses: Record<string, Biz> };

const META: Record<string, { label: string; icon: string }> = {
  insurance: { label: "Insurance", icon: "🛡️" },
  consulting: { label: "BnB Global Consulting", icon: "💻" },
  savorymind: { label: "SavoryMind", icon: "🍽️" },
};

function Funnel({ stages }: { stages: Stage[] }) {
  const max = Math.max(1, ...stages.map((s) => s.count));
  return (
    <div className="space-y-1.5">
      {stages.map((s) => (
        <div key={s.stage} className="flex items-center gap-2">
          <div className="w-20 shrink-0 text-xs text-gray-600">{s.stage}</div>
          <div className="h-5 flex-1 overflow-hidden rounded bg-gray-100">
            <div className="flex h-full items-center justify-end rounded bg-brand px-2 text-[11px] font-medium text-white"
                 style={{ width: `${Math.max(6, (s.count / max) * 100)}%` }}>{s.count}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function Chips({ items }: { items: Named[] }) {
  if (!items?.length) return <p className="text-xs text-gray-400">No data yet.</p>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((i) => (
        <span key={i.name} className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700">
          {i.name} <span className="text-gray-400">{i.count}</span>
        </span>
      ))}
    </div>
  );
}

function PipelineView() {
  const { data, loading, error, reload } = useFetch<Pipeline>(() => api.get<Pipeline>("/analytics/pipeline"));
  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;
  const biz = data.businesses;
  const totalValue = Object.values(biz).reduce((s, b) => s + (b.value || 0), 0);
  const totalLeads = Object.values(biz).reduce((s, b) => s + b.total, 0);
  const totalReplied = Object.values(biz).reduce((s, b) => s + b.replied, 0);
  const totalWon = Object.values(biz).reduce((s, b) => s + b.won, 0);

  return (
    <div className="space-y-8">
      <PageHeader title="Sales Pipeline" subtitle="Insurance · BnB Global consulting · SavoryMind — sourcing → outreach → won" />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="Total prospects" value={totalLeads} />
        <KpiCard label="Replied" value={totalReplied} />
        <KpiCard label="Won" value={totalWon} />
        <KpiCard label="Pipeline value" value={`$${totalValue.toLocaleString()}`} hint="expected (value × probability)" />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {Object.entries(biz).map(([key, b]) => {
          const m = META[key] || { label: key, icon: "📈" };
          return (
            <div key={key} className="card">
              <div className="mb-1 flex items-center justify-between">
                <h2 className="font-semibold">{m.icon} {m.label}</h2>
                <span className="rounded bg-brand/10 px-2 py-0.5 text-[10px] font-medium text-brand-dark">{b.scope}</span>
              </div>
              <p className="mb-3 text-xs text-gray-500">
                {b.total} prospects · {b.emailed} emailed · {b.replied} replied · {b.won} won
                {b.value ? ` · $${b.value.toLocaleString()} pipeline` : ""}
                {b.avg_score ? ` · avg score ${b.avg_score}` : ""}
              </p>
              <Funnel stages={b.funnel} />
              {b.top_industries && (
                <div className="mt-4">
                  <div className="mb-1 text-[11px] uppercase tracking-wide text-gray-400">Top industries</div>
                  <Chips items={b.top_industries} />
                </div>
              )}
              {b.top_cities && (
                <div className="mt-4">
                  <div className="mb-1 text-[11px] uppercase tracking-wide text-gray-400">Top cities</div>
                  <Chips items={b.top_cities} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><PipelineView /></AuthGate>;
}
