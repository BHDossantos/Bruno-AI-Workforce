"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, KpiCard } from "@/components/ui";

type Channel = { channel: string | null; label: string; kind: string; paced_externally: boolean };
type Account = { account: string; label: string; connected: boolean; sent_today: number; sendgrid_sender: string | null };
type Snapshot = {
  status: string; tone: "good" | "warn" | "bad";
  channel: Channel;
  sent_today: number; sent_week: number;
  daily_cap: number; remaining_today: number | null;
  backlog: number; lead_backlog: number; restaurant_backlog: number;
  accounts: Account[];
  failures: Record<string, number>;
  paused: boolean; autopilot: boolean; can_send: boolean;
};

const TONE: Record<string, string> = {
  good: "border-emerald-300 bg-emerald-50 text-emerald-800",
  warn: "border-amber-300 bg-amber-50 text-amber-800",
  bad: "border-red-300 bg-red-50 text-red-700",
};
const FAIL_LABEL: Record<string, string> = {
  send_skipped_duplicate: "Skipped — already emailed today",
  send_skipped_synthetic: "Skipped — placeholder/sample address",
  send_skipped_paused: "Skipped — Emergency Stop on",
  provider_handoff_failed: "Provider hand-off failed",
};

function Deliverability() {
  const [refresh, setRefresh] = useState(0);
  const { data, error } = useFetch<Snapshot>(() => api.get<Snapshot>("/deliverability"), [refresh]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function sendNow() {
    setBusy(true); setMsg("Draining the outbox — sending every queued prospect now…");
    try {
      const r = await api.post<{ dispatched: number; sent_today: number }>("/deliverability/send-now", {});
      setMsg(`✅ Sent ${r.dispatched} now — ${r.sent_today} total sent today.`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(false); }
  }

  const capPct = data && data.daily_cap ? Math.min(100, (data.sent_today / data.daily_cap) * 100) : 0;

  return (
    <div>
      <PageHeader
        title="Email Deliverability"
        subtitle="Are emails actually going out? See your sending channel, today's sends vs the daily cap, the queued backlog, and push it all out with one click."
        action={
          <button className="btn" onClick={sendNow} disabled={busy || !data?.can_send}>
            {busy ? "Sending…" : "📤 Send all pending now"}
          </button>
        }
      />

      {msg && <p className="mb-4 rounded bg-brand/10 p-3 text-sm text-brand-dark">{msg}</p>}
      {error && <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">Couldn&apos;t load — {String(error)}</p>}

      {data && (
        <>
          <div className={`mb-6 rounded-xl border p-4 text-sm font-medium ${TONE[data.tone]}`}>
            {data.status}
            <span className="ml-2 font-normal opacity-80">
              Channel: <b>{data.channel.label}</b>
              {data.channel.paced_externally && " — paces itself across its own inboxes"}
            </span>
          </div>

          <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard label="Sent today" value={data.sent_today.toLocaleString()} />
            <KpiCard label="Daily cap" value={data.daily_cap ? data.daily_cap.toLocaleString() : "—"} />
            <KpiCard label="Remaining today" value={data.remaining_today != null ? data.remaining_today.toLocaleString() : "—"} />
            <KpiCard label="Sent (7 days)" value={data.sent_week.toLocaleString()} />
          </div>

          {/* Cap usage bar */}
          {data.daily_cap > 0 && (
            <div className="card mb-6">
              <div className="mb-1 flex justify-between text-xs text-gray-500">
                <span>Today&apos;s send budget</span>
                <span>{data.sent_today} / {data.daily_cap}</span>
              </div>
              <div className="h-2 overflow-hidden rounded bg-gray-100">
                <div className={`h-full rounded ${capPct >= 100 ? "bg-amber-500" : "bg-brand"}`} style={{ width: `${capPct}%` }} />
              </div>
            </div>
          )}

          {/* Backlog */}
          <div className="card mb-6 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">Queued backlog</div>
              <div className="mt-0.5 text-2xl font-bold">
                {data.backlog.toLocaleString()}
                <span className="ml-2 text-sm font-normal text-gray-400">
                  prospects waiting ({data.lead_backlog} leads · {data.restaurant_backlog} restaurants)
                </span>
              </div>
            </div>
            {data.backlog > 0 && (
              <button className="btn" onClick={sendNow} disabled={busy || !data.can_send}>
                {busy ? "Sending…" : "Send them now"}
              </button>
            )}
          </div>

          {/* Per-mailbox breakdown */}
          <h2 className="mb-3 text-lg font-semibold">Per-business sends today</h2>
          <div className="card mb-6 overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500">
                <tr><th className="p-3">Business</th><th className="p-3">Mailbox</th>
                  <th className="p-3">SendGrid sender</th><th className="p-3">Sent today</th></tr>
              </thead>
              <tbody>
                {data.accounts.map((a) => (
                  <tr key={a.account} className="border-t">
                    <td className="p-3 font-medium">{a.label}</td>
                    <td className="p-3">
                      {a.connected
                        ? <span className="badge bg-green-100 text-green-700">connected</span>
                        : <span className="badge bg-gray-100 text-gray-500">not connected</span>}
                    </td>
                    <td className="p-3 text-gray-500">{a.sendgrid_sender || "—"}</td>
                    <td className="p-3 font-medium">{a.sent_today}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Recent failures */}
          {Object.keys(data.failures).length > 0 && (
            <>
              <h2 className="mb-3 text-lg font-semibold">Skipped / failed today</h2>
              <div className="card mb-6 space-y-2">
                {Object.entries(data.failures).map(([k, n]) => (
                  <div key={k} className="flex items-center justify-between text-sm">
                    <span className="text-gray-600">{FAIL_LABEL[k] || k}</span>
                    <b>{n}</b>
                  </div>
                ))}
              </div>
            </>
          )}

          {(data.paused || !data.can_send) && (
            <p className="text-sm text-gray-500">
              {data.paused
                ? "Agents are paused (Emergency Stop). Resume from the sidebar to send."
                : "No sender is connected. Connect SendGrid or a Gmail mailbox on the Setup page first."}
            </p>
          )}
        </>
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><Deliverability /></AuthGate>;
}
