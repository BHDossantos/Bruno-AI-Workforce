"use client";
import { useEffect, useRef, useState } from "react";
import { api, API_URL, getToken } from "@/lib/api";
import DotPipeline from "@/components/DotPipeline";
import SenderSignaturePanel, { SignatureProfile } from "@/components/SenderSignaturePanel";
import { AuthGate, PageHeader } from "@/components/ui";

type Observation = { source_kind: string; source_name: string; source_ref: string; source_record_id: string; fetched_at: string; fields: Record<string, string> };
type ReviewEvent = { event_id: string; kind: string; occurred_at: string; note: string; evidence_ref: string; language?: string; due_at?: string; outcome?: string; owner_id: string };
type Draft = { to: string; bcc: string[]; subject: string; body: string; status: string };
type Detail = { usdot: string; observations: Observation[]; events: ReviewEvent[]; registry_status: string; safer_status: string;
  suppressed: boolean; prior_contact_review: boolean; evidence_digests: string[]; prepared_draft?: Draft;
  hooks: { topic: string; question: string; source_ref: string; observed_at: string }[];
  differences: { field: string; left?: string; right?: string; reason: string }[];
  crm_matches: { id: string; status: string; times_contacted: number }[];
  message_history: { id: string; channel: string; status: string; sent_at?: string; provider_id?: string }[];
  gmail_history?: { message_ids: string[]; truncated: boolean; checked_at: string };
  draft: { body: string | null } };
const fieldLabels: Record<string, string> = { legal_name: "Legal business name", dba: "DBA", physical_address: "Physical address",
  ma_entity_id: "MA entity ID", cargo: "Cargo listed", operation_scope: "Operating scope listed", email: "Contact email", phone: "Contact phone" };
const inputClass = "border rounded p-2 w-full";
function SourceLink({ value }: { value: string }) {
  return /^https:\/\//i.test(value) ? <a className="underline" href={value} target="_blank" rel="noopener noreferrer">Open source</a> : <span>{value}</span>;
}
function Workspace() {
  const [cases, setCases] = useState<{ usdot: string; legal_name: string | null }[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  const [source, setSource] = useState(""); const [from, setFrom] = useState(""); const [through, setThrough] = useState("");
  const [file, setFile] = useState<File | null>(null); const [selected, setSelected] = useState("");
  const [sourceKind, setSourceKind] = useState("safer"); const [lookup, setLookup] = useState("not_found");
  const [sourceRef, setSourceRef] = useState(""); const [sourceId, setSourceId] = useState(""); const [observed, setObserved] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [note, setNote] = useState(""); const [ref, setRef] = useState(""); const [kind, setKind] = useState("contact_reported");
  const [language, setLanguage] = useState(""); const [outcome, setOutcome] = useState(""); const [due, setDue] = useState(""); const [occurred, setOccurred] = useState("");
  const eventRetry = useRef<{ key: string; id: string } | null>(null);
  const [to, setTo] = useState(""); const [bcc, setBcc] = useState(""); const [subject, setSubject] = useState("Trucking insurance options"); const [body, setBody] = useState("");
  const [signatureProfile, setSignatureProfile] = useState<SignatureProfile>({configured: false});
  const [includeSignature, setIncludeSignature] = useState(false);
  const [mailbox, setMailbox] = useState(""); const [blockers, setBlockers] = useState<string[]>([]);
  async function refresh() { setCases(await api.get("/dot-review")); }
  async function show(dot: string, loadDraft = false) {
    const data = await api.get<Detail>(`/dot-review/${dot}`);
    setSelected(dot); setDetail(data);
    const readiness = await api.get<{ blockers: string[] }>(`/dot-review/${dot}/readiness`); setBlockers(readiness.blockers);
    if (loadDraft) {
      setTo(data.prepared_draft?.to || data.observations.find(o => o.fields.email)?.fields.email || "");
      setBcc(data.prepared_draft?.bcc.join(", ") || ""); setSubject(data.prepared_draft?.subject || "Trucking insurance options");
      setBody(data.prepared_draft?.body || data.draft.body || "");
    }
  }
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(""); setNotice(""); try { await action(); } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  useEffect(() => { refresh().catch(e => setError(String(e))); }, []);
  const expressed = detail?.events.filter(e => e.kind === "language_preference").sort((a, b) => b.occurred_at.localeCompare(a.occurred_at))[0];
  return <div className="space-y-4">
    <PageHeader title="DOT research review" subtitle="Check evidence and contact history, then prepare a message for review." />
    <p>No messages are sent from this workspace. Existing call and CRM controls remain in place.</p>
    <p className="text-sm"><a className="underline" href="https://dot-leads.com/search/index" target="_blank" rel="noopener noreferrer">Open DOT Leads in your existing session</a>. Sign in directly with the vendor. Never enter passwords or session cookies here.</p>
    {error && <p role="alert" className="text-red-700">{error}</p>}{notice && <p role="status">{notice}</p>}
    <form className="card space-y-3" onSubmit={e => { e.preventDefault(); void perform(async () => {
      if (!file) throw new Error("Choose a CSV file");
      const data = new FormData(); data.append("file", file); data.append("source_ref", source);
      data.append("posted_from", new Date(from).toISOString()); data.append("posted_through", new Date(through).toISOString());
      const response = await fetch(`${API_URL}/dot-review/import-csv`, { method: "POST", body: data, headers: { Authorization: `Bearer ${getToken()}` } });
      if (!response.ok) throw new Error(await response.text()); const result = await response.json(); await refresh();
      setNotice(`${result.usdots.length} research cases in the selected date-posted range. No outreach queued.`);
    }); }}>
      <h2 className="font-semibold">Import an authorized New Ventures export</h2>
      <p className="text-sm">Up to 100 rows. Required columns: usdot, source_record_id, posted_at (with timezone). Optional: legal_name, email, phone. Map the export’s columns first. These filters use date posted, not company formation or application date.</p>
      <label className="block">Source/export reference <input required value={source} onChange={e => setSource(e.target.value)} className={inputClass} /></label>
      <label className="block">Posted from (your local time) <input required type="datetime-local" value={from} onChange={e => setFrom(e.target.value)} /></label>
      <label className="block">Posted through (your local time) <input required type="datetime-local" value={through} onChange={e => setThrough(e.target.value)} /></label>
      <input aria-label="Authorized CSV export" required type="file" accept=".csv" onChange={e => setFile(e.target.files?.[0] || null)} />
      <button disabled={busy} className="btn-primary">Import for research</button>
    </form>
    <div className="card"><h2 className="font-semibold">Recent cases (up to 50)</h2>
      {cases.map(c => <button key={c.usdot} className="block underline p-2" disabled={busy} onClick={() => void perform(() => show(c.usdot, true))}>USDOT {c.usdot} — {c.legal_name || "Name unverified"}</button>)}
    </div>
    <DotPipeline key={selected} usdot={selected} onUpdated={async () => { if (selected) await show(selected); }} />
    <SenderSignaturePanel onChange={setSignatureProfile} />
    {detail && <section className="space-y-4">
      <div className="card space-y-2"><h2 className="font-semibold">USDOT {selected}</h2>
        <p>State registry: {detail.registry_status.replaceAll("_", " ")} · SAFER: {detail.safer_status.replaceAll("_", " ")}</p>
        <p>Language: {expressed?.language || "Unknown — ask the prospect"}</p>
        {detail.suppressed && <p role="alert" className="text-red-700">Do not contact: suppression recorded.</p>}
        {detail.prior_contact_review && <p>Prior activity needs reconciliation before preparing another message.</p>}
        <h3 className="font-semibold">Source observations</h3>
        {detail.observations.map((o, i) => <div key={i} className="border rounded p-3"><p>{o.source_name} · {new Date(o.fetched_at).toLocaleString()} · <SourceLink value={o.source_ref} /></p>
          <dl>{Object.entries(o.fields).map(([key, value]) => <div key={key}><dt className="inline font-medium">{fieldLabels[key] || key.replaceAll("_", " ")}: </dt><dd className="inline">{value}</dd></div>)}</dl></div>)}
        <h3 className="font-semibold">Questions to clarify</h3>
        {detail.hooks.map((h, i) => <p key={i}>{h.question} <span className="text-sm">({new Date(h.observed_at).toLocaleDateString()}, <SourceLink value={h.source_ref} />)</span></p>)}
        {detail.differences.map((d, i) => <p key={i}>{d.field.replaceAll("_", " ")}: “{d.left || "not listed"}” / “{d.right || "not listed"}” — confirm with the client.</p>)}
      </div>
      <form className="card space-y-3" onSubmit={e => { e.preventDefault(); void perform(async () => {
        await api.post(`/dot-review/${selected}/evidence`, { source_kind: sourceKind, source_name: sourceKind === "safer" ? "FMCSA SAFER" : "Massachusetts registry",
          source_ref: sourceRef, source_record_id: sourceId, fetched_at: new Date(observed).toISOString(),
          fields: { ...Object.fromEntries(Object.entries(fields).filter(([, value]) => value.trim())), lookup_status: lookup } });
        await show(selected); setNotice("Evidence recorded. Missing results remain unverified.");
      }); }}>
        <h3 className="font-semibold">Record a registry lookup</h3>
        <label className="block">Source <select value={sourceKind} onChange={e => setSourceKind(e.target.value)}><option value="safer">FMCSA SAFER</option><option value="ma_registry">Massachusetts registry</option></select></label>
        <label className="block">Result <select value={lookup} onChange={e => setLookup(e.target.value)}><option value="not_found">No match — unverified</option><option value="found">Record found</option><option value="unavailable">Lookup unavailable</option></select></label>
        <label className="block">Source URL/reference <input required className={inputClass} value={sourceRef} onChange={e => setSourceRef(e.target.value)} /></label>
        <label className="block">Record or lookup identifier <input required className={inputClass} value={sourceId} onChange={e => setSourceId(e.target.value)} /></label>
        <label className="block">Time checked (your local time) <input required type="datetime-local" value={observed} onChange={e => setObserved(e.target.value)} /></label>
        {Object.entries({ usdot: "USDOT in this source (if shown)", ...fieldLabels }).map(([key, label]) => <label key={key} className="block">{label}<input className={inputClass} value={fields[key] || ""} onChange={e => setFields({ ...fields, [key]: e.target.value })} /></label>)}
        <button disabled={busy} className="btn-primary">Record evidence</button>
      </form>
      <div className="card space-y-2"><h3 className="font-semibold">Contact history</h3>
        {detail.crm_matches.map(l => <p key={l.id}>CRM lead: {l.status} · {l.times_contacted} recorded contacts</p>)}
        {detail.message_history.map(m => <p key={m.id}>{m.channel}: {m.status} · {m.sent_at ? new Date(m.sent_at).toLocaleString() : "No sent timestamp"} · {m.provider_id ? "Provider reference stored" : "No provider reference"}</p>)}
        {detail.events.map(e => <p key={e.event_id}>{e.kind.replaceAll("_", " ")} · {new Date(e.occurred_at).toLocaleString()}: {e.note}{e.due_at && ` · Due ${new Date(e.due_at).toLocaleString()} · Owner ${e.owner_id}`}</p>)}
        <p>Operator reports and stored CRM statuses are not independent proof of delivery.</p>
        <label className="block">Expected authorized Gmail address <input type="email" className={inputClass} value={mailbox} onChange={e => setMailbox(e.target.value)} /></label>
        <button disabled={busy || !mailbox} className="btn-secondary" onClick={() => void perform(async () => {
          await api.post("/dot-review/gmail/verify", {expected_address: mailbox}); setNotice("OAuth mailbox identity verified. Sending remains disabled.");
        })}>Verify mailbox (no email sent)</button>
        <button disabled={busy || !mailbox} className="btn-secondary" onClick={() => void perform(async () => {
          await api.post(`/dot-review/${selected}/gmail-history`, {expected_address: mailbox}); await show(selected); setNotice("Gmail Sent history checked. No email sent.");
        })}>Check prior Gmail contact</button>
        {detail.gmail_history && <p>Gmail: {detail.gmail_history.message_ids.length} matching sent-message references{detail.gmail_history.truncated ? " (more results exist)" : ""}, checked {new Date(detail.gmail_history.checked_at).toLocaleString()}.</p>}
      </div>
      <form className="card space-y-2" onSubmit={e => { e.preventDefault(); void perform(async () => {
        const payload = {kind, note, evidence_ref: ref, occurred_at: new Date(occurred).toISOString(),
          ...(kind === "language_preference" ? {language} : {}), ...(kind === "outcome" ? {outcome} : {}), ...(kind === "next_action" ? {due_at: new Date(due).toISOString()} : {})};
        const key = JSON.stringify([selected, payload]); if (eventRetry.current?.key !== key) eventRetry.current = {key, id: crypto.randomUUID()};
        await api.post(`/dot-review/${selected}/events`, {...payload, event_id: eventRetry.current.id});
        eventRetry.current = null; await show(selected); setNote(""); setRef(""); setNotice("Event recorded. No follow-up was sent.");
      }); }}>
        <h3 className="font-semibold">Record an outcome or next step</h3>
        <label className="block">Record type <select value={kind} onChange={e => setKind(e.target.value)}><option value="contact_reported">Prior contact reported</option><option value="opt_out">Opt-out: suppress known contacts</option><option value="language_preference">Actual language preference</option><option value="next_action">Next action assigned to me</option><option value="outcome">Call outcome</option></select></label>
        {kind === "language_preference" && <select required aria-label="Expressed language" value={language} onChange={e => setLanguage(e.target.value)}><option value="">Choose the actual preference</option><option value="en">English</option><option value="pt">Português</option><option value="es">Español</option></select>}
        {kind === "outcome" && <select required aria-label="Actual call outcome" value={outcome} onChange={e => setOutcome(e.target.value)}><option value="">Choose the actual outcome</option>{["answered", "voicemail_left", "voicemail_unavailable", "no_answer", "busy", "wrong_number"].map(o => <option key={o}>{o}</option>)}</select>}
        {kind === "next_action" && <label className="block">Due date <input required type="datetime-local" value={due} onChange={e => setDue(e.target.value)} /></label>}
        <label className="block">When this occurred (your local time) <input required type="datetime-local" value={occurred} onChange={e => setOccurred(e.target.value)} /></label>
        <label className="block">Evidence reference <input required className={inputClass} value={ref} onChange={e => setRef(e.target.value)} /></label>
        <label className="block">Actual reply, outcome or next step <textarea required className={inputClass} value={note} onChange={e => setNote(e.target.value)} /></label>
        <button disabled={busy} className="btn-primary">Record for review</button>
      </form>
      <form className="card space-y-2" onSubmit={e => { e.preventDefault(); void perform(async () => {
        await api.post(`/dot-review/${selected}/draft`, {to, bcc: bcc.split(",").map(v => v.trim()).filter(Boolean), subject, body, evidence_digests: detail.evidence_digests.slice(-10), include_signature: includeSignature});
        await show(selected); setNotice("Draft saved locally for review. Not created or sent in Gmail.");
      }); }}>
        <h3 className="font-semibold">Prepare a truthful message</h3><p>Use the source questions above. Review the sender’s name, agency, contact details, language and opt-out wording. Do not promise coverage or approval.</p>
        <label className="block">To (must match evidence) <input required type="email" className={inputClass} value={to} onChange={e => setTo(e.target.value)} /></label>
        <label className="block">Optional proposed BCC (Bruno/Lucas; comma separated) <input className={inputClass} value={bcc} onChange={e => setBcc(e.target.value)} /></label>
        <p className="text-sm">BCC identities must be verified before dispatch. No default recipients are added.</p>
        <label className="block">Subject <input required className={inputClass} value={subject} onChange={e => setSubject(e.target.value)} /></label>
        <label className="block">Message <textarea required rows={9} className={inputClass} value={body} onChange={e => setBody(e.target.value)} /></label>
        <label className="block"><input type="checkbox" disabled={!signatureProfile.configured} checked={includeSignature} onChange={e => setIncludeSignature(e.target.checked)} /> Include my saved signature{signatureProfile.mailbox ? ` (${signatureProfile.mailbox})` : " — upload it above first"}</label>
        <button disabled={busy || detail.suppressed || detail.prior_contact_review} className="btn-primary">Save review-only draft</button>
        {detail.prepared_draft && <><p>Saved draft: {detail.prepared_draft.status.replaceAll("_", " ")}</p>
          <button type="button" disabled={busy || detail.suppressed || detail.prior_contact_review} className="btn-secondary" onClick={() => void perform(async () => {
            await api.download(`/dot-review/${selected}/draft-preview`, "review-only-draft.eml"); setNotice("Review-only email downloaded. No email sent.");
          })}>Download email preview with embedded signature</button></>}
        <p>Sending is disabled. Remaining checks:</p><ul className="list-disc ml-6">{blockers.map(b => <li key={b}>{b.replaceAll("_", " ")}</li>)}</ul>
      </form>
    </section>}
  </div>;
}
export default function Page() { return <AuthGate><Workspace /></AuthGate>; }
