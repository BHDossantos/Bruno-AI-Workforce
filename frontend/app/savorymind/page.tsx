"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { AuthGate, Expandable, PageHeader, StatusBadge, TempBadge, TempFilter, useFetch, LoadState } from "@/components/ui";

type Restaurant = {
  id: string;
  name: string;
  owner_manager: string;
  cuisine: string;
  city: string;
  email: string;
  instagram: string;
  pain_points: string;
  menu_analysis: Record<string, unknown> | null;
  pitch_email: string | null;
  linkedin_msg: string | null;
  follow_up: string | null;
  status: string;
  temperature: string;
  fit_score: number;
};
type Temp = { cold: number; warm: number; hot: number; dead: number };

function SavoryMind() {
  const [refresh, setRefresh] = useState(0);
  const [temp, setTemp] = useState("");
  const { data, loading, error, reload } = useFetch<Restaurant[]>(
    () => api.get<Restaurant[]>(`/restaurants?kind=prospect&limit=200${temp ? `&temperature=${temp}` : ""}`), [temp, refresh]);
  const { data: counts } = useFetch<Temp>(() => api.get<Temp>("/restaurants/summary"), [refresh]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [sourcing, setSourcing] = useState(false);

  async function sourceNow() {
    setSourcing(true); setMsg("Sourcing restaurants… this can take a minute.");
    try {
      const r = await api.post<{ result?: { summary?: string } }>("/agents/savorymind/run", {});
      setMsg(`✅ ${r.result?.summary || "Done"}`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setSourcing(false); }
  }

  async function dispatchAll() {
    if (!confirm("Send the SavoryMind pitch to all pending restaurants now?")) return;
    setBusy("all"); setMsg("Dispatching all pending restaurants…");
    try {
      const r = await api.post<{ dispatched: number; pending: number; failed: number }>("/restaurants/dispatch", {});
      setMsg(`✅ Dispatched ${r.dispatched}/${r.pending} pending${r.failed ? `, ${r.failed} failed` : ""}.`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  async function send(id: string) {
    setBusy(id); setMsg("");
    try {
      const r = await api.post<{ ok: boolean; status?: string; reason?: string }>(`/restaurants/${id}/send`, {});
      setMsg(r.ok ? `✅ Pitch ${r.status?.toLowerCase() || "queued"}` : `❌ ${r.reason || "failed"}`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(String(e)); }
    finally { setBusy(null); }
  }

  return (
    <div>
      <PageHeader title="SavoryMind Leads" subtitle="Restaurant prospects with AI menu analysis and pitch"
        action={<div className="flex gap-2">
          <Link href="/restaurants/new" className="btn">+ Add Restaurant</Link>
          <button className="btn" onClick={sourceNow} disabled={sourcing}>{sourcing ? "Sourcing…" : "Source restaurants now"}</button>
          <button className="btn" onClick={dispatchAll} disabled={busy === "all"}>{busy === "all" ? "Sending…" : "Send all pending"}</button>
        </div>} />
      {msg && <p className="mb-2 text-sm text-gray-600">{msg}</p>}
      <div className="mb-3"><TempFilter counts={counts} value={temp} onChange={setTemp} /></div>
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}
      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">Fit</th>
              <th className="th">Restaurant</th>
              <th className="th">Cuisine / City</th>
              <th className="th">Temp</th>
              <th className="th">Contact</th>
              <th className="th">Pain points</th>
              <th className="th">Menu analysis</th>
              <th className="th">Status</th>
              <th className="th">Pitch</th>
              <th className="th">Action</th>
            </tr>
          </thead>
          <tbody>
            {(data || []).map((r) => (
              <tr key={r.id} className="border-t border-gray-100">
                <td className="td"><span className="badge bg-brand/10 text-brand-dark">{r.fit_score}</span></td>
                <td className="td"><Link href={`/restaurants/${r.id}`} className="font-medium text-brand hover:underline">{r.name}</Link><div className="text-xs text-gray-400">{r.owner_manager}</div></td>
                <td className="td">{r.cuisine}<div className="text-xs text-gray-400">{r.city}</div></td>
                <td className="td"><TempBadge t={r.temperature} /></td>
                <td className="td text-xs">{r.email}<br />{r.instagram}</td>
                <td className="td text-xs">{r.pain_points}</td>
                <td className="td"><Expandable label="Analysis" text={r.menu_analysis ? JSON.stringify(r.menu_analysis, null, 2) : null} /></td>
                <td className="td"><StatusBadge status={r.status} /></td>
                <td className="td space-y-1">
                  <Expandable label="Pitch email" text={r.pitch_email} />
                  <Expandable label="LinkedIn msg" text={r.linkedin_msg} />
                  <Expandable label="Demo invite" text={r.follow_up} />
                </td>
                <td className="td">
                  <button onClick={() => send(r.id)} disabled={busy === r.id || !r.email}
                    className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">
                    {busy === r.id ? "Sending…" : "Reach out"}
                  </button>
                </td>
              </tr>
            ))}
            {!loading && (data || []).length === 0 && (
              <tr><td colSpan={10} className="td text-center text-gray-400">No restaurants yet — hit “Source restaurants now” to find prospects.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><SavoryMind /></AuthGate>;
}
