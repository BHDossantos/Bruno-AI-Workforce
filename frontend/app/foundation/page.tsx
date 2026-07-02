"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, Expandable, PageHeader, StatusBadge, TempBadge, TempFilter, useFetch, LoadState } from "@/components/ui";
import LeadHealth from "@/components/LeadHealth";

type Grant = {
  id: string; title: string; funder: string | null; source: string | null; url: string | null;
  amount: number | null; deadline: string | null; category: string | null; summary: string | null;
  match_score: number; status: string;
};
type Summary = { total: number; pipeline_amount: number; by_status: Record<string, number> };

type Lead = {
  id: string; company_name: string | null; owner_name: string | null; category: string | null;
  industry: string | null; email: string | null; phone: string | null;
  cold_email: string | null; linkedin_msg: string | null; call_script: string | null; status: string;
  temperature: string; fit_score: number;
};
type Temp = { cold: number; warm: number; hot: number; dead: number };

const STATUSES = ["New", "Reviewing", "Applying", "Submitted", "Won", "Lost", "Skipped"];

function money(n: number | null) {
  if (!n) return "—";
  return n >= 1000 ? `$${(n / 1000).toFixed(0)}k` : `$${n}`;
}

// ── Grants view (existing) ─────────────────────────────────────────────────
function GrantsView() {
  const [refresh, setRefresh] = useState(0);
  const [status, setStatus] = useState("");
  const { data, loading, error, reload } = useFetch<Grant[]>(
    () => api.get<Grant[]>(`/grants?limit=200${status ? `&status=${status}` : ""}`), [status, refresh]);
  const { data: sum } = useFetch<Summary>(() => api.get<Summary>("/grants/summary"), [refresh]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  async function sourceNow() {
    setBusy("source"); setMsg("Searching grants… this can take a minute.");
    try {
      const r = await api.post<{ result?: { summary?: string } }>("/grants/source", {});
      setMsg(`✅ ${r.result?.summary || "Done"}`); setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); } finally { setBusy(null); }
  }

  async function setGrantStatus(id: string, s: string) {
    setBusy(id);
    try { await api.post(`/grants/${id}/status`, { status: s }); setRefresh((n) => n + 1); }
    catch (e) { setMsg(`❌ ${e}`); } finally { setBusy(null); }
  }

  return (
    <div>
      <div className="mb-4 flex justify-end">
        <button className="btn" disabled={busy === "source"} onClick={sourceNow}>
          {busy === "source" ? "Searching…" : "Find grants now"}
        </button>
      </div>
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="card"><div className="text-xs text-gray-500">Opportunities</div><div className="text-3xl font-bold">{sum?.total ?? "—"}</div></div>
        <div className="card"><div className="text-xs text-gray-500">Pipeline (identified)</div><div className="text-3xl font-bold text-brand">{money(sum?.pipeline_amount ?? null)}</div></div>
        <div className="card"><div className="text-xs text-gray-500">In progress</div><div className="text-3xl font-bold">{(sum?.by_status?.Reviewing || 0) + (sum?.by_status?.Applying || 0)}</div></div>
        <div className="card"><div className="text-xs text-gray-500">Submitted / Won</div><div className="text-3xl font-bold">{(sum?.by_status?.Submitted || 0) + (sum?.by_status?.Won || 0)}</div></div>
      </div>

      {msg && <p className="mb-2 text-sm text-gray-600">{msg}</p>}

      <div className="mb-3">
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}

      <div className="space-y-2">
        {(data || []).map((g) => (
          <div key={g.id} className="card">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="badge bg-brand/10 text-brand-dark">{g.match_score}</span>
                  <span className="font-medium">{g.url ? <a href={g.url} target="_blank" rel="noreferrer" className="text-brand hover:underline">{g.title} ↗</a> : g.title}</span>
                </div>
                <div className="mt-1 text-xs text-gray-400">
                  {g.funder || "—"}{g.category ? ` · ${g.category}` : ""}{g.source ? ` · ${g.source}` : ""}
                  {g.amount ? ` · ${money(g.amount)}` : ""}{g.deadline ? ` · due ${g.deadline}` : ""}
                </div>
                {g.summary && <p className="mt-1 max-w-2xl text-xs text-gray-500">{g.summary}</p>}
              </div>
              <select value={g.status} disabled={busy === g.id}
                onChange={(e) => setGrantStatus(g.id, e.target.value)}
                className="rounded-lg border border-gray-300 px-2 py-1 text-sm">
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>
        ))}
        {data && data.length === 0 && (
          <div className="card text-sm text-gray-400">No grants yet — hit “Find grants now”.</div>
        )}
      </div>
    </div>
  );
}

// ── Partners & Donors view (new) ───────────────────────────────────────────
// Two lead segments the foundation agents produce:
//  - "foundation"     → corporate / CSR sponsors + donor prospects
//  - "school_partner" → schools, universities, conservatories, community centers
const PARTNER_KINDS = [
  { key: "foundation", label: "Corporate & Donor partners", agent: "foundation_outreach",
    blurb: "CSR sponsors and donor prospects — mission-aligned partnership outreach, drafted for your approval." },
  { key: "school_partner", label: "Education partners", agent: "school_partner",
    blurb: "Schools, universities, conservatories & community centers — workshops, performances, scholarships & mentorship." },
] as const;

function PartnersView() {
  const [kind, setKind] = useState<(typeof PARTNER_KINDS)[number]>(PARTNER_KINDS[0]);
  const [temp, setTemp] = useState("");
  const [refresh, setRefresh] = useState(0);
  const { data, loading, error, reload } = useFetch<Lead[]>(
    () => api.get<Lead[]>(`/leads?segment=${kind.key}&limit=200&sort=fit${temp ? `&temperature=${temp}` : ""}`),
    [kind.key, temp, refresh]);
  const { data: counts } = useFetch<Temp>(
    () => api.get<Temp>(`/leads/summary?segment=${kind.key}`), [kind.key, refresh]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [sourcing, setSourcing] = useState(false);

  async function sourceNow() {
    setSourcing(true); setMsg("Sourcing partners… this can take a minute.");
    try {
      const r = await api.post<{ result?: { summary?: string } }>(`/agents/${kind.agent}/run`, {});
      setMsg(`✅ ${r.result?.summary || "Done"}`); setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); } finally { setSourcing(false); }
  }

  async function dispatchAll() {
    if (!confirm(`Send the outreach email to all pending ${kind.label.toLowerCase()} now?`)) return;
    setBusy("all"); setMsg("Dispatching all pending…");
    try {
      const r = await api.post<{ dispatched: number; pending: number; failed: number }>(
        `/leads/dispatch?segment=${kind.key}`, {});
      setMsg(`✅ Dispatched ${r.dispatched}/${r.pending} pending${r.failed ? `, ${r.failed} failed` : ""}.`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); } finally { setBusy(null); }
  }

  async function send(id: string) {
    setBusy(id); setMsg("");
    try {
      const r = await api.post<{ ok: boolean; status?: string; reason?: string }>(`/leads/${id}/send`, {});
      setMsg(r.ok ? `✅ ${r.status?.toLowerCase() || "queued"}` : `❌ ${r.reason || "failed"}`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(String(e)); } finally { setBusy(null); }
  }

  return (
    <div>
      {/* Which kind of partner */}
      <div className="mb-3 flex flex-wrap gap-2">
        {PARTNER_KINDS.map((k) => (
          <button key={k.key} onClick={() => { setKind(k); setTemp(""); }}
            className={`rounded-lg border px-3 py-1.5 text-sm ${k.key === kind.key
              ? "border-brand bg-brand/10 font-semibold" : "border-gray-200 bg-white text-gray-600"}`}>
            {k.label}
          </button>
        ))}
      </div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-xl text-xs text-gray-500">{kind.blurb}</p>
        <div className="flex gap-2">
          <button className="btn" onClick={sourceNow} disabled={sourcing}>
            {sourcing ? "Sourcing…" : "Source partners now"}
          </button>
          <button className="btn" onClick={dispatchAll} disabled={busy === "all"}>
            {busy === "all" ? "Sending…" : "Send all pending"}
          </button>
        </div>
      </div>
      {msg && <p className="mb-2 text-sm text-gray-600">{msg}</p>}
      <LeadHealth refresh={refresh} />
      <div className="mb-3"><TempFilter counts={counts} value={temp} onChange={setTemp} /></div>
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}
      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead><tr>
            <th className="th">Fit</th><th className="th">Organization</th><th className="th">Type</th>
            <th className="th">Temp</th><th className="th">Contact</th><th className="th">Status</th>
            <th className="th">Outreach</th><th className="th">Action</th>
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
                  <Expandable label="Outreach email" text={l.cold_email} />
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
              <tr><td colSpan={8} className="td text-center text-gray-400">
                No {kind.label.toLowerCase()} yet — hit “Source partners now” (or let the daily cycle run).
              </td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Foundation() {
  const [tab, setTab] = useState<"partners" | "grants">("partners");
  return (
    <div>
      <PageHeader title="Foundation"
        subtitle="Esposito–Dossantos Foundation · Empowering Lives. Inspiring Futures. — grants, corporate/donor partners and education partnerships." />
      <div className="mb-4 flex gap-2 border-b border-gray-200">
        {([["partners", "🤝 Partners & Donors"], ["grants", "🎓 Grants"]] as const).map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${tab === t
              ? "border-brand text-brand" : "border-transparent text-gray-500 hover:text-gray-700"}`}>
            {label}
          </button>
        ))}
      </div>
      {tab === "partners" ? <PartnersView /> : <GrantsView />}
    </div>
  );
}

export default function Page() {
  return <AuthGate><Foundation /></AuthGate>;
}
