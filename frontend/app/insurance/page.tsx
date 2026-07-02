"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, Expandable, PageHeader, StatusBadge, TempBadge, TempFilter, useFetch, LoadState } from "@/components/ui";
import LeadHealth from "@/components/LeadHealth";

type Lead = {
  id: string;
  segment: string;
  category: string;
  company_name: string;
  owner_name: string;
  email: string;
  phone: string;
  industry: string;
  reason: string;
  score: number;
  status: string;
  cold_email: string | null;
  call_script: string | null;
  linkedin_msg: string | null;
  times_contacted: number;
  last_contacted_at: string | null;
  temperature: string;
  fit_score: number;
  line: string;
};
type Lines = { home: number; auto: number; life: number; commercial: number };
type Temp = { cold: number; warm: number; hot: number; dead: number; lines?: Lines };
type QuoteField = { key: string; label: string };
type QuoteTemplate = { key: string; label: string; line: string; fields: QuoteField[] };
type IntakeProfile = {
  lead_id: string; quote_type: string | null; quote_type_label: string | null;
  fields: QuoteField[]; answers: Record<string, string>;
  collected: number; total: number; complete: boolean;
};

const LINE_LABEL: Record<string, string> = { home: "Home", auto: "Auto", life: "Life", commercial: "Commercial" };
const LINE_BADGE: Record<string, string> = {
  home: "bg-sky-100 text-sky-700", auto: "bg-amber-100 text-amber-700",
  life: "bg-rose-100 text-rose-700", commercial: "bg-violet-100 text-violet-700",
};

function Insurance() {
  const [segment, setSegment] = useState("");
  const [temp, setTemp] = useState("");
  const [status, setStatus] = useState("");
  const [line, setLine] = useState("");
  const [refresh, setRefresh] = useState(0);
  const { data, loading, error, reload } = useFetch<Lead[]>(
    () => api.get<Lead[]>(`/leads?limit=200&sort=fit${segment ? `&segment=${segment}` : ""}${temp ? `&temperature=${temp}` : ""}${status ? `&status=${status}` : ""}${line ? `&line=${line}` : ""}`),
    [segment, temp, status, line, refresh]
  );
  const { data: counts } = useFetch<Temp>(
    () => api.get<Temp>(`/leads/summary${segment ? `?segment=${segment}` : ""}`), [segment, refresh]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [sourcing, setSourcing] = useState(false);
  const [profileLead, setProfileLead] = useState<{ id: string; name: string } | null>(null);
  const [profile, setProfile] = useState<IntakeProfile | null>(null);
  const [selectedType, setSelectedType] = useState("");
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [profileBusy, setProfileBusy] = useState(false);
  const { data: templates } = useFetch<QuoteTemplate[]>(() => api.get<QuoteTemplate[]>("/book/quote-templates"));

  async function openProfile(id: string, name: string) {
    setProfileLead({ id, name });
    setProfile(null); setDraft({}); setSelectedType("");
    const p = await api.get<IntakeProfile>(`/leads/${id}/intake`);
    setProfile(p);
    setDraft(p.answers || {});
    setSelectedType(p.quote_type || "");
  }

  async function saveProfile() {
    if (!profileLead || !selectedType) return;
    setProfileBusy(true);
    try {
      const p = await api.post<IntakeProfile>(`/leads/${profileLead.id}/intake`,
        { quote_type: selectedType, answers: draft });
      setProfile(p);
      setDraft(p.answers || {});
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setProfileBusy(false); }
  }

  async function sourceNow() {
    setSourcing(true); setMsg("Sourcing insurance leads… this can take a minute.");
    try {
      const r = await api.post<{ result?: { summary?: string } }>("/agents/insurance/run", {});
      setMsg(`✅ ${r.result?.summary || "Done"}`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setSourcing(false); }
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

  async function addToCrm(id: string) {
    setBusy(id); setMsg("");
    try {
      await api.post(`/book/from-lead/${id}`, {});
      setMsg("✅ Added to the Client Book (CRM).");
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  async function syncReplies() {
    setBusy("sync"); setMsg("Checking your inbox for replies…");
    try {
      const r = await api.post<{ scanned?: number; matched?: number }>("/leads/sync-replies", {});
      const matched = r.matched ?? 0;
      setMsg(`✅ Scanned ${r.scanned ?? 0} inbox message(s); ${matched} lead(s) warmed up from replies.`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  async function dispatchAll() {
    if (!confirm("Send the cold email to all pending leads now?")) return;
    setBusy("all"); setMsg("Dispatching all pending leads…");
    try {
      const r = await api.post<{ dispatched: number; pending: number; failed: number }>("/leads/dispatch", {});
      setMsg(`✅ Dispatched ${r.dispatched}/${r.pending} pending leads${r.failed ? `, ${r.failed} failed` : ""}.`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  return (
    <div>
      <PageHeader
        title="Insurance Leads"
        subtitle="Home · Auto · Life · Commercial — direct prospects and the referral partners (realtors, lenders, CPAs) who feed your personal lines in NH/MA/FL"
        action={
          <div className="flex gap-2">
            <select value={line} onChange={(e) => setLine(e.target.value)} className="rounded-lg border border-gray-300 px-3 py-2 text-sm" title="Filter by line of business">
              <option value="">All lines</option>
              <option value="home">🏠 Home</option>
              <option value="auto">🚗 Auto</option>
              <option value="life">🛡️ Life</option>
              <option value="commercial">🏢 Commercial</option>
            </select>
            <select value={segment} onChange={(e) => setSegment(e.target.value)} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
              <option value="">All segments</option>
              <option value="commercial">Commercial</option>
              <option value="personal">Personal</option>
              <option value="referral_partner">Referral partners</option>
            </select>
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-lg border border-gray-300 px-3 py-2 text-sm" title="Filter by stage">
              <option value="">Any stage</option>
              <option value="New">New (not contacted)</option>
              <option value="Drafted">Drafted (awaiting send)</option>
              <option value="Sent">Sent (emailed)</option>
              <option value="Replied">Replied</option>
              <option value="Interested">Interested</option>
            </select>
            <button className="btn-ghost" onClick={() => api.download("/export/leads.csv", "leads.csv")}>Export CSV</button>
            <button className="btn" onClick={sourceNow} disabled={sourcing}>{sourcing ? "Sourcing…" : "Source leads now"}</button>
            <button className="btn" onClick={dispatchAll} disabled={busy === "all"}>{busy === "all" ? "Sending…" : "Send all pending"}</button>
            <button className="btn-ghost" onClick={syncReplies} disabled={busy === "sync"} title="Pull inbox replies — turns repliers into warm/hot leads">{busy === "sync" ? "Syncing…" : "Sync replies now"}</button>
          </div>
        }
      />
      {msg && <p className="mb-2 text-sm text-gray-600">{msg}</p>}
      <LeadHealth refresh={refresh} />
      {/* Book of business by line — Home / Auto / Life / Commercial. Click to filter. */}
      {counts?.lines && (
        <div className="mb-3 flex flex-wrap gap-2">
          {(["home", "auto", "life", "commercial"] as const).map((ln) => (
            <button key={ln} onClick={() => setLine(line === ln ? "" : ln)}
              className={`rounded-lg border px-3 py-1.5 text-sm ${line === ln ? "border-brand bg-brand/10 font-semibold" : "border-gray-200 bg-white"}`}>
              <span className={`badge mr-1 ${LINE_BADGE[ln]}`}>{LINE_LABEL[ln]}</span>
              {counts.lines![ln].toLocaleString()}
            </button>
          ))}
        </div>
      )}
      <div className="mb-3"><TempFilter counts={counts} value={temp} onChange={setTemp} /></div>
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}
      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">Fit</th>
              <th className="th">Score</th>
              <th className="th">Company / Owner</th>
              <th className="th">Segment</th>
              <th className="th">Temp</th>
              <th className="th">Contact</th>
              <th className="th">Reason</th>
              <th className="th">Status</th>
              <th className="th">Touches</th>
              <th className="th">Scripts</th>
              <th className="th">Action</th>
            </tr>
          </thead>
          <tbody>
            {(data || []).map((l) => (
              <tr key={l.id} className="border-t border-gray-100">
                <td className="td"><span className="badge bg-brand/10 text-brand-dark">{l.fit_score}</span></td>
                <td className="td"><span className="badge bg-gray-100 text-gray-600">{l.score}</span></td>
                <td className="td"><div className="font-medium">{l.company_name}</div><div className="text-xs text-gray-400">{l.owner_name}</div></td>
                <td className="td">
                  {l.line && <span className={`badge ${LINE_BADGE[l.line] || "bg-gray-100 text-gray-600"}`}>{LINE_LABEL[l.line] || l.line}</span>}
                  <div className="text-xs capitalize text-gray-500">{l.segment.replace("_", " ")}</div>
                  <div className="text-xs text-gray-400">{l.category}</div>
                </td>
                <td className="td"><TempBadge t={l.temperature} /></td>
                <td className="td text-xs">{l.email}<br />{l.phone}</td>
                <td className="td max-w-xs text-xs">{l.reason}</td>
                <td className="td"><StatusBadge status={l.status} /></td>
                <td className="td text-xs">
                  <span className="font-medium">{l.times_contacted || 0}×</span>
                  {l.last_contacted_at && (
                    <div className="text-gray-400">{new Date(l.last_contacted_at).toLocaleDateString()}</div>
                  )}
                </td>
                <td className="td space-y-1">
                  <Expandable label="Cold email" text={l.cold_email} />
                  <Expandable label="Call script" text={l.call_script} />
                  <Expandable label="LinkedIn msg" text={l.linkedin_msg} />
                </td>
                <td className="td">
                  <button onClick={() => send(l.id)} disabled={busy === l.id || !l.email}
                    className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">
                    {busy === l.id ? "Sending…" : "Reach out"}
                  </button>
                  <button onClick={() => addToCrm(l.id)} disabled={busy === l.id}
                    className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-1 text-xs text-gray-600 hover:bg-gray-50"
                    title="Add this lead to the Client Book (CRM)">→ CRM</button>
                  <button onClick={() => openProfile(l.id, l.company_name || l.owner_name || l.email)}
                    className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-1 text-xs text-gray-600 hover:bg-gray-50"
                    title="Quote-intake profile — track what's been collected">📋 Profile</button>
                </td>
              </tr>
            ))}
            {!loading && (data || []).length === 0 && (
              <tr><td colSpan={11} className="td text-center text-gray-400">No leads yet — hit “Source leads now” to find prospects.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {profileLead && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setProfileLead(null)}>
          <div className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6"
            onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-semibold">📋 Profile — {profileLead.name}</h3>
              <button onClick={() => setProfileLead(null)} className="text-gray-400 hover:text-gray-700">✕</button>
            </div>
            {!profile ? (
              <p className="text-sm text-gray-500">Loading…</p>
            ) : (
              <>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-400">
                  Quote type
                </label>
                <select value={selectedType} onChange={(e) => setSelectedType(e.target.value)}
                  className="mb-4 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                  <option value="">Choose a quote type…</option>
                  {(templates || []).map((t) => (
                    <option key={t.key} value={t.key}>{t.label}</option>
                  ))}
                </select>

                {selectedType && (
                  <>
                    {profile.quote_type === selectedType && (
                      <div className="mb-3 text-xs text-gray-500">
                        {profile.collected}/{profile.total} collected
                        {profile.complete && <span className="ml-1 font-medium text-green-600">✓ Complete</span>}
                      </div>
                    )}
                    <div className="space-y-3">
                      {(templates || []).find((t) => t.key === selectedType)?.fields.map((f) => (
                        <div key={f.key}>
                          <label className="mb-1 block text-xs text-gray-500">{f.label}</label>
                          <input value={draft[f.key] || ""}
                            onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
                        </div>
                      ))}
                    </div>
                    <button onClick={saveProfile} disabled={profileBusy}
                      className="btn mt-4 w-full disabled:opacity-40">
                      {profileBusy ? "Saving…" : "Save profile"}
                    </button>
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><Insurance /></AuthGate>;
}
