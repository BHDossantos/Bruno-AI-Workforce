"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type Goal = { target: number; won_today: number; on_track: boolean; deficit: number };
type ActionCard = {
  key: string; title: string; why: string; count: number; value: number;
  cta: string; action: "link" | "send-now" | "run-followups" | "nudge-bookings"; link: string;
};
type HotLead = {
  id: string; entity_type: string; name: string; business: string;
  line: string | null; email: string; status: string; temperature: string; value: number;
};
type Data = { goal: Goal; actions: ActionCard[]; hot_leads: HotLead[] };

const money = (n: number) => (n >= 1000 ? `$${(n / 1000).toFixed(1)}k` : `$${n}`);
const ENDPOINT: Record<string, string> = {
  "send-now": "/deliverability/send-now",
  "run-followups": "/followups/run",
  "nudge-bookings": "/followups/nudge-bookings",
};

function Today() {
  const [refresh, setRefresh] = useState(0);
  const { data, loading, error, reload } = useFetch<Data>(() => api.get<Data>("/mission/money-actions"), [refresh]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  async function run(card: ActionCard) {
    const ep = ENDPOINT[card.action];
    if (!ep) return;
    setBusy(card.key); setMsg("");
    try {
      const r = await api.post<Record<string, number>>(ep, {});
      const n = r.dispatched ?? r.sent ?? 0;
      setMsg(`✅ ${card.cta}: ${n} done.`);
      setRefresh((x) => x + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  async function reachOut(l: HotLead) {
    if (l.entity_type !== "lead") { setMsg("Open this one in the Unified Inbox to reply."); return; }
    setBusy(l.id); setMsg("");
    try {
      const r = await api.post<{ ok: boolean; status?: string; reason?: string }>(`/leads/${l.id}/send`, {});
      setMsg(r.ok ? `✅ Reached out to ${l.name}.` : `❌ ${r.reason || "failed"}`);
      setRefresh((x) => x + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;

  return (
    <div>
      <PageHeader
        title="Today's Money Actions"
        subtitle="The shortest path to new clients today — ranked. Do these and the goal takes care of itself."
      />
      {msg && <p className="mb-4 rounded bg-brand/10 p-3 text-sm text-brand-dark">{msg}</p>}

      {/* Goal */}
      <div className={`mb-6 rounded-xl border p-4 ${data.goal.on_track ? "border-emerald-300 bg-emerald-50" : "border-brand/30 bg-brand/5"}`}>
        <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">Today&apos;s client goal</div>
        <div className="mt-0.5 text-2xl font-bold">
          {data.goal.won_today}<span className="text-base font-normal text-gray-400"> / {data.goal.target} new clients</span>
          {data.goal.on_track
            ? <span className="ml-2 badge bg-green-100 text-green-700">on track 🎉</span>
            : <span className="ml-2 badge bg-amber-100 text-amber-700">{data.goal.deficit} to go</span>}
        </div>
      </div>

      {/* Ranked actions */}
      <h2 className="mb-3 text-lg font-semibold">Do these now</h2>
      <div className="mb-6 space-y-3">
        {data.actions.length === 0 && (
          <div className="card text-sm text-gray-500">
            Nothing queued right now — the engine is caught up. Source more leads or check back after the next agent run.
          </div>
        )}
        {data.actions.map((a) => (
          <div key={a.key} className="card flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="font-semibold">{a.title}</div>
              <div className="text-xs text-gray-500">{a.why}</div>
              {a.value > 0 && <div className="mt-1 text-xs font-medium text-green-600">~{money(a.value)} on the table</div>}
            </div>
            {a.action === "link"
              ? <Link href={a.link} className="btn">{a.cta}</Link>
              : <button className="btn" onClick={() => run(a)} disabled={busy === a.key}>{busy === a.key ? "…" : a.cta}</button>}
          </div>
        ))}
      </div>

      {/* Hot & warm leads */}
      {data.hot_leads.length > 0 && (
        <>
          <h2 className="mb-3 text-lg font-semibold">Warm &amp; hot leads to work</h2>
          <div className="card overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500">
                <tr><th className="p-3">Prospect</th><th className="p-3">Business</th><th className="p-3">Line</th>
                  <th className="p-3">Temp</th><th className="p-3">Status</th><th className="p-3">Value</th><th className="p-3"></th></tr>
              </thead>
              <tbody>
                {data.hot_leads.map((l) => (
                  <tr key={l.id} className="border-t">
                    <td className="p-3"><div className="font-medium">{l.name}</div><div className="text-xs text-gray-400">{l.email}</div></td>
                    <td className="p-3">{l.business}</td>
                    <td className="p-3">{l.line || "—"}</td>
                    <td className="p-3">
                      <span className={`badge ${l.temperature === "hot" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"}`}>{l.temperature}</span>
                    </td>
                    <td className="p-3 text-xs">{l.status}</td>
                    <td className="p-3 text-green-600">{money(l.value)}</td>
                    <td className="p-3">
                      <button className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
                        onClick={() => reachOut(l)} disabled={busy === l.id}>
                        {busy === l.id ? "…" : "Reach out"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><Today /></AuthGate>;
}
