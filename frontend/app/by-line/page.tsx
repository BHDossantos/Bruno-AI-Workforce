"use client";

import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, KpiCard, LoadState } from "@/components/ui";

type Line = {
  leads: number; contacted: number; replied: number; won: number;
  revenue_won: number; pipeline_value: number; reply_rate: number; win_rate: number;
};
type Report = {
  lines: Record<string, Line>;
  totals: { leads: number; contacted: number; replied: number; won: number; revenue_won: number; pipeline_value: number };
};

const money = (n: number) => (n >= 1000 ? `$${(n / 1000).toFixed(1)}k` : `$${n}`);
const pct = (n: number) => `${(n * 100).toFixed(1)}%`;
const BADGE: Record<string, string> = {
  Home: "bg-sky-100 text-sky-700", Auto: "bg-amber-100 text-amber-700",
  Life: "bg-rose-100 text-rose-700", Commercial: "bg-violet-100 text-violet-700",
};

function ByLine() {
  const { data, loading, error, reload } = useFetch<Report>(() => api.get<Report>("/analytics/by-line"));
  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;

  const entries = Object.entries(data.lines);
  const bestReply = entries.reduce<[string, number]>((b, [name, l]) =>
    l.contacted >= 5 && l.reply_rate > b[1] ? [name, l.reply_rate] : b, ["—", 0]);

  return (
    <div>
      <PageHeader
        title="Conversion by Line"
        subtitle="Which insurance line actually converts — Home, Auto, Life, Commercial — so you double down where the replies and clients are. Includes the referral partners feeding each line."
      />

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="Total leads" value={data.totals.leads.toLocaleString()} />
        <KpiCard label="Replied" value={data.totals.replied.toLocaleString()} />
        <KpiCard label="Clients won" value={data.totals.won.toLocaleString()} />
        <KpiCard label="Best-converting line" value={bestReply[0]} hint={bestReply[1] > 0 ? `${pct(bestReply[1])} reply rate` : "need more data"} />
      </div>

      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="p-3">Line</th><th className="p-3">Leads</th><th className="p-3">Contacted</th>
              <th className="p-3">Replied</th><th className="p-3">Won</th>
              <th className="p-3">Reply rate</th><th className="p-3">Win rate</th>
              <th className="p-3">Revenue</th><th className="p-3">Pipeline</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([name, l]) => (
              <tr key={name} className="border-t">
                <td className="p-3"><span className={`badge ${BADGE[name] || "bg-gray-100 text-gray-600"}`}>{name}</span></td>
                <td className="p-3">{l.leads}</td><td className="p-3">{l.contacted}</td>
                <td className="p-3">{l.replied}</td><td className="p-3">{l.won}</td>
                <td className="p-3">{pct(l.reply_rate)}</td><td className="p-3">{pct(l.win_rate)}</td>
                <td className="p-3 font-medium text-green-600">{money(l.revenue_won)}</td>
                <td className="p-3 text-gray-500">{money(l.pipeline_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-4 text-xs text-gray-400">
        Personal-lines clients (Home/Auto/Life) come through referral partners — realtors and lenders
        feed Home, auto dealers feed Auto, CPAs and advisors feed Life. This view rolls each partner
        into the line it feeds.
      </p>
    </div>
  );
}

export default function Page() {
  return <AuthGate><ByLine /></AuthGate>;
}
