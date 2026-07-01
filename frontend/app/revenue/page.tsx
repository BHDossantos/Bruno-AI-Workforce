"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, KpiCard } from "@/components/ui";

type Line = {
  leads: number; contacted: number; replied: number; won: number;
  revenue_won: number; pipeline_value: number; reply_rate: number; win_rate: number;
  actual_annual_revenue?: number;
};
type Report = {
  businesses: Record<string, Line>;
  totals: { leads: number; contacted: number; replied: number; won: number;
    revenue_won: number; pipeline_value: number; actual_annual_revenue?: number };
  cost_metrics: { spend: number; cost_per_lead: number | null; cost_per_won: number | null; roi: number | null } | null;
};

function money(n: number) {
  return n >= 1000 ? `$${(n / 1000).toFixed(1)}k` : `$${n}`;
}
const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

function Revenue() {
  const [cost, setCost] = useState("");
  const [applied, setApplied] = useState("");
  const { data } = useFetch<Report>(() => api.get<Report>(`/analytics/revenue${applied ? `?cost=${applied}` : ""}`), [applied]);

  return (
    <div>
      <PageHeader title="Revenue & ROI"
        subtitle="The money view — revenue won, weighted pipeline, win/reply rates per business. Enter your monthly spend to see cost-per-lead and ROI." />

      {data && (
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          <KpiCard label="Actual annual revenue" value={money(data.totals.actual_annual_revenue || 0)} />
          <KpiCard label="Estimated revenue won" value={money(data.totals.revenue_won)} />
          <KpiCard label="Weighted pipeline" value={money(data.totals.pipeline_value)} />
          <KpiCard label="Clients won" value={String(data.totals.won)} />
        </div>
      )}
      {data && (data.totals.actual_annual_revenue || 0) > 0 && (
        <p className="mb-4 text-xs text-gray-400">
          &ldquo;Actual annual revenue&rdquo; is real, from the Client Book (each client&apos;s monthly
          premium × 12) — not an estimate. &ldquo;Estimated revenue won&rdquo; is projected from lead
          status before a client record exists.
        </p>
      )}

      <div className="card mb-6 flex flex-wrap items-end gap-2">
        <div>
          <div className="text-xs text-gray-500">Your spend ($) — tools, ads, data</div>
          <input className="input mt-1 w-40" type="number" placeholder="e.g. 500" value={cost}
            onChange={(e) => setCost(e.target.value)} />
        </div>
        <button className="btn" onClick={() => setApplied(cost)}>Compute ROI</button>
        {data?.cost_metrics && (
          <div className="ml-auto flex gap-4 text-sm">
            <span>Cost/lead <b>{data.cost_metrics.cost_per_lead != null ? money(data.cost_metrics.cost_per_lead) : "—"}</b></span>
            <span>Cost/client <b>{data.cost_metrics.cost_per_won != null ? money(data.cost_metrics.cost_per_won) : "—"}</b></span>
            <span>ROI <b className={data.cost_metrics.roi != null && data.cost_metrics.roi >= 0 ? "text-green-600" : "text-red-600"}>
              {data.cost_metrics.roi != null ? `${(data.cost_metrics.roi * 100).toFixed(0)}%` : "—"}</b></span>
          </div>
        )}
      </div>

      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs text-gray-500">
            <tr><th className="p-3">Business</th><th className="p-3">Leads</th><th className="p-3">Contacted</th>
              <th className="p-3">Replied</th><th className="p-3">Won</th><th className="p-3">Reply rate</th>
              <th className="p-3">Win rate</th><th className="p-3">Est. revenue</th><th className="p-3">Actual annual (CRM)</th>
              <th className="p-3">Pipeline</th></tr>
          </thead>
          <tbody>
            {data && Object.entries(data.businesses).map(([name, b]) => (
              <tr key={name} className="border-t">
                <td className="p-3 font-medium">{name}</td>
                <td className="p-3">{b.leads}</td><td className="p-3">{b.contacted}</td>
                <td className="p-3">{b.replied}</td><td className="p-3">{b.won}</td>
                <td className="p-3">{pct(b.reply_rate)}</td><td className="p-3">{pct(b.win_rate)}</td>
                <td className="p-3 text-gray-500">{money(b.revenue_won)}</td>
                <td className="p-3 font-medium text-green-600">{money(b.actual_annual_revenue || 0)}</td>
                <td className="p-3 text-gray-500">{money(b.pipeline_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Revenue /></AuthGate>;
}
