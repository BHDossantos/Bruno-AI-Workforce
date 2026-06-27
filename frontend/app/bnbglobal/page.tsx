"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, Expandable, PageHeader, StatusBadge, TempBadge, TempFilter, useFetch, LoadState } from "@/components/ui";
import LeadHealth from "@/components/LeadHealth";

type Lead = {
  id: string; company_name: string | null; owner_name: string | null; category: string | null;
  industry: string | null; email: string | null; phone: string | null;
  cold_email: string | null; linkedin_msg: string | null; call_script: string | null; status: string;
  temperature: string; fit_score: number;
};
type Temp = { cold: number; warm: number; hot: number; dead: number };

function BnbGlobal() {
  const [refresh, setRefresh] = useState(0);
  const [temp, setTemp] = useState("");
  const { data, loading, error, reload } = useFetch<Lead[]>(
    () => api.get<Lead[]>(`/leads?segment=consulting&limit=200&sort=fit${temp ? `&temperature=${temp}` : ""}`), [temp, refresh]);
  const { data: counts } = useFetch<Temp>(
    () => api.get<Temp>("/leads/summary?segment=consulting"), [refresh]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [sourcing, setSourcing] = useState(false);

  async function sourceNow() {
    setSourcing(true); setMsg("Sourcing prospects… this can take a minute.");
    try {
      const r = await api.post<{ result?: { summary?: string } }>("/agents/bnbglobal/run", {});
      setMsg(`✅ ${r.result?.summary || "Done"}`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setSourcing(false); }
  }

  async function dispatchAll() {
    if (!confirm("Send the cold email to all pending consulting prospects now?")) return;
    setBusy("all"); setMsg("Dispatching all pending prospects…");
    try {
      const r = await api.post<{ dispatched: number; pending: number; failed: number }>("/leads/dispatch?segment=consulting", {});
      setMsg(`✅ Dispatched ${r.dispatched}/${r.pending} pending${r.failed ? `, ${r.failed} failed` : ""}.`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  async function send(id: string) {
    setBusy(id); setMsg("");
    try {
      const r = await api.post<{ ok: boolean; status?: string; reason?: string }>(`/leads/${id}/send`, {});
      setMsg(r.ok ? `✅ ${r.status?.toLowerCase() || "queued"}` : `❌ ${r.reason || "failed"}`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(String(e)); }
    finally { setBusy(null); }
  }

  return (
    <div>
      <PageHeader title="BnB Global — Tech Consulting"
        subtitle="B2B prospects for cloud, SRE, security, AI & managed IT. Founder-led outreach + follow-ups, auto-sent daily."
        action={<div className="flex gap-2">
          <button className="btn" onClick={sourceNow} disabled={sourcing}>{sourcing ? "Sourcing…" : "Source prospects now"}</button>
          <button className="btn" onClick={dispatchAll} disabled={busy === "all"}>{busy === "all" ? "Sending…" : "Send all pending"}</button>
        </div>} />
      {msg && <p className="mb-2 text-sm text-gray-600">{msg}</p>}
      <LeadHealth refresh={refresh} />
      <div className="mb-3"><TempFilter counts={counts} value={temp} onChange={setTemp} /></div>
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}
      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead><tr>
            <th className="th">Fit</th><th className="th">Company</th><th className="th">Industry</th><th className="th">Temp</th><th className="th">Contact</th>
            <th className="th">Status</th><th className="th">Outreach</th><th className="th">Action</th>
          </tr></thead>
          <tbody>
            {(data || []).map((l) => (
              <tr key={l.id} className="border-t border-gray-100">
                <td className="td"><span className="badge bg-brand/10 text-brand-dark">{l.fit_score}</span></td>
                <td className="td"><div className="font-medium">{l.company_name}</div><div className="text-xs text-gray-400">{l.owner_name}</div></td>
                <td className="td">{l.industry || l.category}</td>
                <td className="td"><TempBadge t={l.temperature} /></td>
                <td className="td text-xs">{l.email}<br />{l.phone}</td>
                <td className="td"><StatusBadge status={l.status} /></td>
                <td className="td space-y-1">
                  <Expandable label="Cold email" text={l.cold_email} />
                  <Expandable label="LinkedIn msg" text={l.linkedin_msg} />
                  <Expandable label="Call script" text={l.call_script} />
                </td>
                <td className="td">
                  <button onClick={() => send(l.id)} disabled={busy === l.id || !l.email}
                    className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">
                    {busy === l.id ? "Sending…" : "Reach out"}
                  </button>
                </td>
              </tr>
            ))}
            {!loading && (data || []).length === 0 &&
              <tr><td colSpan={8} className="td text-center text-gray-400">No prospects yet — run the BnB Global agent (or the daily cycle).</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><BnbGlobal /></AuthGate>;
}
