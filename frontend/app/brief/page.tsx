"use client";

import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

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

function Brief() {
  const { data: report, loading } = useFetch<Report | null>(() => api.get<Report | null>("/reports/latest"));

  if (loading) return <p className="text-gray-400">Loading…</p>;
  if (!report) return <div><PageHeader title="Daily Brief" /><p className="text-gray-500">No report yet. Run the CEO Dashboard agent.</p></div>;

  const b = report.top_actions;
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
