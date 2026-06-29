"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type Item = {
  id: string; entity_type: string; name: string; to: string; step: number;
  due_date: string | null; due: boolean; replied: boolean; last_sent: string | null;
};
type Data = { due: number; total: number; items: Item[] };

function Followups() {
  const [refresh, setRefresh] = useState(0);
  const { data, loading, error, reload } = useFetch<Data>(() => api.get<Data>("/followups"), [refresh]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function runDue() {
    setBusy(true); setMsg("Sending all due follow-ups…");
    try {
      const r = await api.post<{ sent: number; due: number; skipped_replied: number }>("/followups/run", {});
      setMsg(`✅ Sent ${r.sent} follow-up(s); skipped ${r.skipped_replied} who already replied.`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(false); }
  }

  const items = data?.items || [];
  const dueItems = items.filter((i) => i.due && !i.replied);
  const upcoming = items.filter((i) => !i.due && !i.replied);

  const Row = (i: Item) => (
    <tr key={i.id} className="border-t border-gray-100">
      <td className="td"><div className="font-medium">{i.name}</div><div className="text-xs text-gray-400">{i.to}</div></td>
      <td className="td capitalize text-xs">{i.entity_type}</td>
      <td className="td text-xs">Touch #{i.step}</td>
      <td className="td text-xs">{i.due_date ? new Date(i.due_date + "T00:00:00").toLocaleDateString() : "—"}</td>
      <td className="td text-xs text-gray-400">{i.last_sent ? new Date(i.last_sent).toLocaleDateString() : "—"}</td>
      <td className="td">{i.replied ? <span className="badge bg-green-100 text-green-700">replied</span>
        : i.due ? <span className="badge bg-amber-100 text-amber-700">due now</span>
        : <span className="badge bg-gray-100 text-gray-500">scheduled</span>}</td>
    </tr>
  );

  return (
    <div>
      <PageHeader title="Follow-ups"
        subtitle="Everyone you've reached out to and their next touch. Follow-ups auto-send on schedule (and stop the moment they reply) — or send all due now."
        action={<button className="btn" onClick={runDue} disabled={busy || (data?.due ?? 0) === 0}>
          {busy ? "Sending…" : `Send ${data?.due ?? 0} due now`}</button>} />
      {msg && <p className="mb-2 text-sm text-gray-600">{msg}</p>}
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}

      {data && items.length === 0 && (
        <div className="card text-sm text-gray-500">
          No follow-ups scheduled yet. They&apos;re created automatically when an agent emails a
          prospect — so connect Gmail and send/approve outreach, and contacted leads will appear here.
        </div>
      )}

      {dueItems.length > 0 && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-amber-700">Due now ({dueItems.length})</h2>
          <div className="card overflow-x-auto"><table className="w-full"><thead><tr>
            <th className="th">Prospect</th><th className="th">Type</th><th className="th">Step</th>
            <th className="th">Due</th><th className="th">Last sent</th><th className="th">Status</th>
          </tr></thead><tbody>{dueItems.map(Row)}</tbody></table></div>
        </div>
      )}

      {upcoming.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-gray-700">Upcoming ({upcoming.length})</h2>
          <div className="card overflow-x-auto"><table className="w-full"><thead><tr>
            <th className="th">Prospect</th><th className="th">Type</th><th className="th">Step</th>
            <th className="th">Due</th><th className="th">Last sent</th><th className="th">Status</th>
          </tr></thead><tbody>{upcoming.map(Row)}</tbody></table></div>
        </div>
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><Followups /></AuthGate>;
}
