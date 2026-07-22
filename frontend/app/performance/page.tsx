"use client";

import { api } from "@/lib/api";
import { AuthGate, PageHeader, KpiCard, useFetch, LoadState } from "@/components/ui";

type Stage = { key: string; label: string; count: number };
type Report = {
  funnel: {
    stages: Stage[];
    current: { new: number; contacted: number; engaged: number; won: number; lost: number; total: number };
    rates: { contact_rate: number; response_rate: number; close_rate: number; win_from_contacted: number };
  };
  revenue: {
    commission_pct: number; active_clients: number; book_annual_premium: number;
    book_commission: number; avg_annual_premium: number; mtd_new_clients: number;
    mtd_annual_premium: number; mtd_commission: number; monthly_goal: number;
    goal_pct: number | null; goal_remaining: number | null;
  };
  trend: { month: string; clients: number; annual_premium: number; commission: number }[];
};

const money = (n: number) => `$${Math.round(n).toLocaleString()}`;

function Performance() {
  const { data, loading, error, reload } = useFetch<Report>(() => api.get<Report>("/performance"));
  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;

  const { funnel, revenue, trend } = data;
  const top = funnel.stages[0]?.count || 1;
  const maxCommission = Math.max(1, ...trend.map((t) => t.commission));

  return (
    <div>
      <PageHeader title="📊 Performance"
        subtitle="Your sales funnel and real revenue — leads → contacted → engaged → won, conversion at each step, and commission from signed clients." />

      {/* Revenue KPIs */}
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiCard label="This-month commission" value={money(revenue.mtd_commission)}
          hint={`${revenue.mtd_new_clients} new client${revenue.mtd_new_clients === 1 ? "" : "s"}`} />
        <KpiCard label="Book commission (annual)" value={money(revenue.book_commission)}
          hint={`${revenue.commission_pct}% of premium`} />
        <KpiCard label="Active clients" value={revenue.active_clients} />
        <KpiCard label="Avg annual premium" value={money(revenue.avg_annual_premium)} />
      </div>

      {/* Goal vs actual */}
      {revenue.monthly_goal > 0 && (
        <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4">
          <div className="mb-1 flex justify-between text-sm text-gray-600">
            <span>Monthly commission goal</span>
            <span><b>{money(revenue.mtd_commission)}</b> of {money(revenue.monthly_goal)}
              {revenue.goal_remaining ? ` · ${money(revenue.goal_remaining)} to go` : " · goal hit! 🎉"}</span>
          </div>
          <div className="h-3 overflow-hidden rounded bg-gray-100">
            <div className={`h-full rounded ${(revenue.goal_pct || 0) >= 100 ? "bg-emerald-500" : "bg-brand"}`}
              style={{ width: `${Math.min(100, revenue.goal_pct || 0)}%` }} />
          </div>
        </div>
      )}

      {/* Funnel */}
      <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4">
        <div className="mb-3 text-sm font-semibold text-gray-700">Sales funnel</div>
        <div className="space-y-2">
          {funnel.stages.map((s) => (
            <div key={s.key} className="flex items-center gap-3">
              <div className="w-32 text-sm text-gray-600">{s.label}</div>
              <div className="h-7 flex-1 overflow-hidden rounded bg-gray-100">
                <div className="flex h-full items-center rounded bg-brand px-2 text-xs font-medium text-white"
                  style={{ width: `${Math.max(4, (s.count / top) * 100)}%` }}>{s.count}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
          <div><div className="text-xs text-gray-500">Contact rate</div><b>{funnel.rates.contact_rate}%</b></div>
          <div><div className="text-xs text-gray-500">Response rate</div><b>{funnel.rates.response_rate}%</b></div>
          <div><div className="text-xs text-gray-500">Close rate (of decided)</div><b>{funnel.rates.close_rate}%</b></div>
          <div><div className="text-xs text-gray-500">Win from contacted</div><b>{funnel.rates.win_from_contacted}%</b></div>
        </div>
      </div>

      {/* Trend */}
      <div className="rounded-xl border border-gray-200 bg-white p-4">
        <div className="mb-3 text-sm font-semibold text-gray-700">New business — last 6 months (commission)</div>
        <div className="flex items-end gap-3" style={{ height: 140 }}>
          {trend.map((t) => (
            <div key={t.month} className="flex flex-1 flex-col items-center justify-end">
              <div className="text-xs font-medium text-gray-600">{t.commission ? money(t.commission) : ""}</div>
              <div className="w-full rounded-t bg-brand/80"
                style={{ height: `${(t.commission / maxCommission) * 100}%`, minHeight: t.commission ? 4 : 0 }} />
              <div className="mt-1 text-[11px] text-gray-400">{t.month.slice(5)}</div>
              <div className="text-[11px] text-gray-400">{t.clients ? `${t.clients}c` : ""}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Performance /></AuthGate>;
}
