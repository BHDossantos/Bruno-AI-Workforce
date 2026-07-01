"use client";

import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, KpiCard, LoadState } from "@/components/ui";

type Style = {
  style: string; description: string; sent: number; replied: number;
  rate: number; enough_data: boolean;
};
type Report = {
  styles: Style[]; min_sample: number; best: string | null;
  total_sent: number; total_replied: number;
};

function SubjectAB() {
  const { data, loading, error, reload } = useFetch<Report>(() => api.get<Report>("/analytics/subject-ab"));
  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;

  const overall = data.total_sent ? (data.total_replied / data.total_sent) : 0;
  const maxRate = Math.max(0.001, ...data.styles.map((s) => s.rate));

  return (
    <div>
      <PageHeader
        title="Subject A/B Testing"
        subtitle="The engine rotates through subject-line styles on every batch and learns which earn the most replies — then favors the winners automatically. Here's what's winning."
      />

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="Emails sent" value={data.total_sent.toLocaleString()} />
        <KpiCard label="Replies" value={data.total_replied.toLocaleString()} hint={`${(overall * 100).toFixed(1)}% overall`} />
        <KpiCard label="Current winner" value={data.best ? titel(data.best) : "—"} hint={data.best ? "being favored now" : "not enough data yet"} />
        <KpiCard label="Min sample" value={`${data.min_sample}`} hint="sends before a style is trusted" />
      </div>

      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="p-3">Subject style</th><th className="p-3">What it is</th>
              <th className="p-3">Sent</th><th className="p-3">Replies</th>
              <th className="p-3">Reply rate</th><th className="p-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.styles.map((s) => (
              <tr key={s.style} className={`border-t ${data.best === s.style ? "bg-emerald-50" : ""}`}>
                <td className="p-3 font-medium">{titel(s.style)}{data.best === s.style && <span className="ml-2 badge bg-emerald-100 text-emerald-700">winner</span>}</td>
                <td className="p-3 text-xs text-gray-500">{s.description}</td>
                <td className="p-3">{s.sent}</td>
                <td className="p-3">{s.replied}</td>
                <td className="p-3">
                  <div className="flex items-center gap-2">
                    <span className="w-10 tabular-nums">{(s.rate * 100).toFixed(1)}%</span>
                    <div className="h-1.5 w-24 overflow-hidden rounded bg-gray-100">
                      <div className="h-full rounded bg-brand" style={{ width: `${(s.rate / maxRate) * 100}%` }} />
                    </div>
                  </div>
                </td>
                <td className="p-3">
                  {s.enough_data
                    ? <span className="badge bg-green-100 text-green-700">trusted</span>
                    : <span className="badge bg-gray-100 text-gray-500">testing ({s.sent}/{data.min_sample})</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-4 text-xs text-gray-400">
        Styles with fewer than {data.min_sample} sends are still gathering data — the engine keeps
        rotating them evenly until each has a fair sample, then leans on the winners.
      </p>
    </div>
  );
}

function titel(s: string): string {
  return s.split(/[\/\s]/).map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" / ");
}

export default function Page() {
  return <AuthGate><SubjectAB /></AuthGate>;
}
