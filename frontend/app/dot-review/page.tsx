"use client";
import { useEffect, useState } from "react";
import { api, API_URL, getToken } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

type Case = { usdot: string; observations: { fields: Record<string, string> }[] };
function Workspace() {
  const [cases, setCases] = useState<Case[]>([]);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState("");
  const [from, setFrom] = useState("");
  const [through, setThrough] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [selected, setSelected] = useState("");
  const [evidence, setEvidence] = useState("");
  const [note, setNote] = useState("");
  const [ref, setRef] = useState("");
  const [kind, setKind] = useState("contact_reported");
  const [language, setLanguage] = useState("en");
  const [outcome, setOutcome] = useState("no_answer");
  const [due, setDue] = useState("");
  async function refresh() { setCases(await api.get<Case[]>("/dot-review")); }
  async function show(dot: string) { setSelected(dot); setDetail(await api.get<Record<string, unknown>>(`/dot-review/${dot}`)); }
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(""); try { await action(); } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  useEffect(() => { refresh().catch(e => setError(String(e))); }, []);
  return <div className="space-y-4">
    <PageHeader title="DOT research review" subtitle="Review source evidence and contact history before preparing outreach." />
    <p>No messages are sent from this workspace. Existing call and CRM controls remain in place.</p>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    <form className="card space-y-3" onSubmit={e => { e.preventDefault(); void perform(async () => {
      if (!file) throw new Error("Choose a CSV file");
      const body = new FormData(); body.append("file", file); body.append("source_ref", source);
      body.append("posted_from", new Date(from).toISOString()); body.append("posted_through", new Date(through).toISOString());
      const response = await fetch(`${API_URL}/dot-review/import-csv`, { method: "POST", body, headers: { Authorization: `Bearer ${getToken()}` } });
      if (!response.ok) throw new Error(await response.text()); await refresh();
    }); }}>
      <h2 className="font-semibold">Import an authorized New Ventures export</h2>
      <p className="text-sm">Up to 100 rows. Columns: usdot, source_record_id, posted_at (with timezone), legal_name, email, phone. Date filters use the source’s date posted, not import time. Map vendor columns to these names first.</p>
      <label className="block">Source/export reference <input required value={source} onChange={e => setSource(e.target.value)} className="border p-2 w-full" /></label>
      <label className="block">Posted from (your local time) <input required type="datetime-local" value={from} onChange={e => setFrom(e.target.value)} /></label>
      <label className="block">Posted through (your local time) <input required type="datetime-local" value={through} onChange={e => setThrough(e.target.value)} /></label>
      <input aria-label="Authorized CSV export" required type="file" accept=".csv" onChange={e => setFile(e.target.files?.[0] || null)} />
      <button disabled={busy} className="btn-primary">Import for research</button>
    </form>
    <div className="card"><h2 className="font-semibold">Recent research cases (up to 50)</h2>
      {cases.map(c => <button key={c.usdot} className="block underline p-2" disabled={busy} onClick={() => void perform(() => show(c.usdot))}>
        USDOT {c.usdot} — {c.observations[0]?.fields.legal_name || "Name unverified"}</button>)}
    </div>
    {detail && <section className="card space-y-4">
      <h2 className="font-semibold">USDOT {selected}: evidence, history and draft</h2>
      <p>Source differences are questions for review. A missing record is unverified. Drafts are not sent or delivered.</p>
      <pre className="whitespace-pre-wrap break-all text-sm">{JSON.stringify(detail, null, 2)}</pre>
      <form onSubmit={e => { e.preventDefault(); void perform(async () => {
        await api.post(`/dot-review/${selected}/evidence`, JSON.parse(evidence)); await show(selected); setEvidence("");
      }); }} className="space-y-2">
        <label className="block">Add registry/SAFER observation (normalized JSON; no credentials)
          <textarea required className="border p-2 w-full" value={evidence} onChange={e => setEvidence(e.target.value)} placeholder={'{"source_kind":"safer","source_name":"FMCSA SAFER","source_ref":"public lookup URL","source_record_id":"lookup identifier","fetched_at":"2026-11-06T15:00:00Z","fields":{"lookup_status":"not_found"}}'} />
        </label><button disabled={busy} className="btn-primary">Record evidence</button>
      </form>
      <form className="space-y-2" onSubmit={e => { e.preventDefault(); void perform(async () => {
        await api.post(`/dot-review/${selected}/events`, { event_id: crypto.randomUUID(), kind, note, evidence_ref: ref,
          occurred_at: new Date().toISOString(), ...(kind === "language_preference" ? {language} : {}),
          ...(kind === "outcome" ? {outcome} : {}), ...(kind === "next_action" ? {due_at: new Date(due).toISOString()} : {}) });
        await show(selected); setNote(""); setRef("");
      }); }}>
        <label className="block">Record type <select value={kind} onChange={e => setKind(e.target.value)}>
          <option value="contact_reported">Prior contact reported (not provider verified)</option><option value="opt_out">Opt-out reported: hold this case</option>
          <option value="language_preference">Actual language preference</option><option value="next_action">Next action assigned to me</option><option value="outcome">Call outcome</option>
        </select></label>
        {kind === "language_preference" && <select aria-label="Expressed language" value={language} onChange={e => setLanguage(e.target.value)}><option value="en">English</option><option value="pt">Português</option><option value="es">Español</option></select>}
        {kind === "outcome" && <select aria-label="Actual call outcome" value={outcome} onChange={e => setOutcome(e.target.value)}>{["answered", "voicemail_left", "voicemail_unavailable", "no_answer", "busy", "wrong_number"].map(o => <option key={o}>{o}</option>)}</select>}
        {kind === "next_action" && <input aria-label="Due date" required type="datetime-local" value={due} onChange={e => setDue(e.target.value)} />}
        <label className="block">Evidence reference <input required className="border p-2 w-full" value={ref} onChange={e => setRef(e.target.value)} /></label>
        <label className="block">Actual reply, outcome or next step <textarea required className="border p-2 w-full" value={note} onChange={e => setNote(e.target.value)} /></label>
        <button disabled={busy} className="btn-primary">Record for review</button>
      </form>
    </section>}
  </div>;
}
export default function Page() { return <AuthGate><Workspace /></AuthGate>; }
