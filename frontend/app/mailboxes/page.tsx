"use client";

import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, KpiCard, LoadState } from "@/components/ui";

type Warmup = { enabled: boolean; day: number | null; at_ceiling: boolean };
type Mailbox = {
  id: string; type: "gmail" | "sendgrid"; label: string;
  address: string | null; reply_to: string | null; connected: boolean;
  sent_today: number; daily_cap: number; shared_cap: boolean;
  remaining?: number; warmup: Warmup;
};
type Pool = {
  active_channel: string | null;
  mailboxes: Mailbox[];
  connected_count: number;
  totals: { daily_capacity: number; sent_today: number; remaining: number; sendgrid_shared_cap: number | null };
};

function warmLabel(w: Warmup): string {
  if (!w.enabled) return "—";
  if (w.at_ceiling) return "Full speed";
  return w.day != null ? `Warming · day ${w.day}` : "Warming";
}

function Mailboxes() {
  const { data, loading, error, reload } = useFetch<Pool>(() => api.get<Pool>("/deliverability/mailboxes"));

  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;

  return (
    <div>
      <PageHeader
        title="Mailbox Pool"
        subtitle="Every identity you can send from — Gmail mailboxes and SendGrid senders — with health, today's usage vs cap, and warmup. This is your total daily sending capacity."
      />

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="Daily capacity" value={data.totals.daily_capacity.toLocaleString()} />
        <KpiCard label="Sent today" value={data.totals.sent_today.toLocaleString()} />
        <KpiCard label="Remaining today" value={data.totals.remaining.toLocaleString()} />
        <KpiCard label="Connected mailboxes" value={String(data.connected_count)} />
      </div>

      {data.totals.sendgrid_shared_cap != null && (
        <p className="mb-4 text-xs text-gray-500">
          SendGrid senders share one account-wide daily limit of{" "}
          <b>{data.totals.sendgrid_shared_cap.toLocaleString()}</b> — counted once in capacity above.
        </p>
      )}

      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="p-3">Mailbox</th><th className="p-3">Channel</th>
              <th className="p-3">Address</th><th className="p-3">Status</th>
              <th className="p-3">Sent today</th><th className="p-3">Daily cap</th>
              <th className="p-3">Warmup</th>
            </tr>
          </thead>
          <tbody>
            {data.mailboxes.map((m) => {
              const pct = m.daily_cap ? Math.min(100, (m.sent_today / m.daily_cap) * 100) : 0;
              return (
                <tr key={m.id} className="border-t align-top">
                  <td className="p-3 font-medium">{m.label}</td>
                  <td className="p-3">
                    <span className={`badge ${m.type === "sendgrid" ? "bg-violet-100 text-violet-700" : "bg-sky-100 text-sky-700"}`}>
                      {m.type === "sendgrid" ? "SendGrid" : "Gmail"}
                    </span>
                  </td>
                  <td className="p-3 text-xs text-gray-500">{m.address || "—"}{m.reply_to && m.reply_to !== m.address && <div className="text-gray-400">↩ {m.reply_to}</div>}</td>
                  <td className="p-3">
                    {m.connected
                      ? <span className="badge bg-green-100 text-green-700">connected</span>
                      : <span className="badge bg-gray-100 text-gray-500">not connected</span>}
                  </td>
                  <td className="p-3">
                    <div className="font-medium">{m.sent_today}{m.shared_cap && <span className="text-xs font-normal text-gray-400"> (shared)</span>}</div>
                    <div className="mt-1 h-1.5 w-24 overflow-hidden rounded bg-gray-100">
                      <div className={`h-full rounded ${pct >= 100 ? "bg-amber-500" : "bg-brand"}`} style={{ width: `${pct}%` }} />
                    </div>
                  </td>
                  <td className="p-3">{m.daily_cap.toLocaleString()}</td>
                  <td className="p-3 text-xs text-gray-500">{warmLabel(m.warmup)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="mt-4 text-xs text-gray-400">
        Live send-tests and per-mailbox auth checks live on the Connect Email &amp; Data page.
      </p>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Mailboxes /></AuthGate>;
}
