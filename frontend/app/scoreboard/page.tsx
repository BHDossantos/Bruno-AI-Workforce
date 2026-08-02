"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, KpiCard, useFetch, LoadState } from "@/components/ui";

type Day = {
  date: string; calls: number; emails: number; texts: number; touches: number;
  conversations: number; quotes: number; followups: number; sales: number;
};
type Totals = Day & { answer_rate: number; quote_conversion: number };
type Board = {
  today: Totals; window_days: number; window_totals: Totals; trend: Day[];
};

const dow = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString(undefined, { weekday: "short" });

function Scoreboard() {
  const [days, setDays] = useState(14);
  const { data, loading, error, reload } = useFetch<Board>(() => api.get<Board>(`/conversations/scoreboard?days=${days}`), [days]);
  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;

  const t = data.today;
  const maxTouch = Math.max(1, ...data.trend.map((d) => d.touches));

  return (
    <div>
      <PageHeader title="🏆 Daily Scoreboard"
        subtitle="Today's numbers and the trend over time — so you can see at a glance whether your improvements are working." />

      {/* Today's headline numbers */}
      <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiCard label="📞 Calls made" value={t.calls} />
        <KpiCard label="📧 Emails sent" value={t.emails} />
        <KpiCard label="📬 Total touches" value={t.touches} hint={`${t.texts} texts`} />
        <KpiCard label="💬 Conversations" value={t.conversations} hint={`${t.answer_rate}% answer rate`} />
      </div>
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiCard label="📝 Quotes started" value={t.quotes} />
        <KpiCard label="📅 Follow-ups scheduled" value={t.followups} />
        <KpiCard label="💰 Sales" value={t.sales} />
        <KpiCard label="Quote conversion" value={t.quotes ? `${t.quote_conversion}%` : "In progress"}
          hint={t.quotes ? `${t.sales}/${t.quotes}` : "no quotes yet today"} />
      </div>

      {/* Window selector + totals */}
      <div className="mb-3 flex items-center gap-3">
        <span className="text-sm font-semibold text-gray-700">Trend</span>
        {[7, 14, 30].map((d) => (
          <button key={d} onClick={() => setDays(d)}
            className={`rounded-lg px-3 py-1 text-sm ${days === d ? "bg-brand text-white" : "bg-gray-100 text-gray-600"}`}>
            {d} days
          </button>
        ))}
        <span className="ml-auto text-xs text-gray-500">
          Last {data.window_days} days: <b>{data.window_totals.touches}</b> touches · <b>{data.window_totals.conversations}</b> conversations · <b>{data.window_totals.quotes}</b> quotes · <b>{data.window_totals.sales}</b> sales
        </span>
      </div>

      {/* Trend bars (touches) */}
      <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4">
        <div className="flex items-end gap-1.5" style={{ height: 130 }}>
          {data.trend.map((d) => (
            <div key={d.date} className="flex flex-1 flex-col items-center justify-end" title={`${d.date}: ${d.touches} touches, ${d.conversations} conversations, ${d.sales} sales`}>
              <div className="w-full rounded-t bg-brand/80" style={{ height: `${(d.touches / maxTouch) * 100}%`, minHeight: d.touches ? 3 : 0 }} />
              <div className="mt-1 text-[10px] text-gray-400">{dow(d.date)}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Detail table */}
      <div className="rounded-xl border border-gray-200 bg-white p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="p-3">Day</th><th className="p-3">Calls</th><th className="p-3">Emails</th>
              <th className="p-3">Touches</th><th className="p-3">Convos</th><th className="p-3">Quotes</th>
              <th className="p-3">Follow-ups</th><th className="p-3">Sales</th>
            </tr>
          </thead>
          <tbody>
            {[...data.trend].reverse().map((d) => (
              <tr key={d.date} className="border-t">
                <td className="p-3 font-medium">{d.date}</td>
                <td className="p-3">{d.calls}</td><td className="p-3">{d.emails}</td>
                <td className="p-3 font-medium">{d.touches}</td><td className="p-3">{d.conversations}</td>
                <td className="p-3">{d.quotes}</td><td className="p-3">{d.followups}</td>
                <td className="p-3 font-medium">{d.sales}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Scoreboard /></AuthGate>;
}
