"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { AuthGate, KpiCard, PageHeader } from "@/components/ui";

type Contact = { phone: string; name: string; role: string; status: "unverified" | "verified" | "wrong_number" | "disconnected"; evidence_ref: string; checked_at: string };
type Review = {
  source_kind: "customer_report" | "authorized_agency" | "public_business_record" | "massachusetts_public_record";
  source_ref: string; observed_at: string; contacts: Contact[]; renewal_date: string | null;
  renewal_basis: "unknown" | "customer_confirmed" | "authorized_policy_record";
  renewal_evidence_ref: string | null; notes: string;
};
type Prospect = { lead_id: string; name: string; segment: string; phone: string; email: string; source: string; review_revision: number; review: Review | null; review_flags: string[]; suppressed: boolean };
type Counts = { call_attempts: number; answered_leads: number; quoted_leads: number; sold_leads: number };
type Overview = {
  mode: "review_only";
  funnel: Counts & { days: number; period_start: string; period_end: string; answered_and_quoted_leads: number; quoted_and_sold_leads: number; answer_to_quote_rate: number | null; quote_to_sale_rate: number | null; invalid_number_attempts: number; by_source: (Counts & { source: string })[] };
  prospects: { total: number; limit: number; items: Prospect[] };
  cross_sell: { total_records: number; limit: number; items: { client_id: string; name: string; lead_id: string | null; recorded_lines: string[]; questions: string[]; expires_at: string | null; suppressed: boolean }[] };
};
const inputClass = "mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm";
const freshReview = (): Review => ({ source_kind: "customer_report", source_ref: "", observed_at: "", contacts: [], renewal_date: null, renewal_basis: "unknown", renewal_evidence_ref: null, notes: "" });
const percent = (n: number | null) => n === null ? "N/A" : `${(n * 100).toFixed(1)}%`;
const localDateTime = (s: string) => {
  if (!s) return "";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? "" : new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};

function Growth() {
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Prospect | null>(null);
  const [draft, setDraft] = useState<Review>(freshReview);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [conflict, setConflict] = useState(false);
  const requestId = useRef(0);
  const saveLock = useRef(false);
  const alive = useRef(true);

  async function refresh() {
    const id = ++requestId.current;
    setLoading(true); setError(""); setSelected(null); setConflict(false);
    try {
      const result = await api.get<Overview>("/insurance-growth/overview?days=30");
      if (alive.current && id === requestId.current) setData(result);
    } catch {
      if (alive.current && id === requestId.current) { setData(null); setError("Could not load the growth review. Please retry."); }
    } finally {
      if (alive.current && id === requestId.current) setLoading(false);
    }
  }
  useEffect(() => {
    alive.current = true;
    void refresh();
    return () => { alive.current = false; requestId.current++; };
  }, []);

  function select(prospect: Prospect) {
    if (saveLock.current) return;
    setSelected(prospect);
    setDraft(prospect.review ? { ...prospect.review, contacts: prospect.review.contacts.map(c => ({ ...c })) } : freshReview());
    setMessage(""); setConflict(false);
  }
  function updateContact(index: number, patch: Partial<Contact>) {
    setDraft(d => ({ ...d, contacts: d.contacts.map((c, i) => i === index ? { ...c, ...patch } : c) }));
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!selected || saveLock.current || conflict) return;
    if (new Date(draft.observed_at).getTime() > Date.now() || draft.contacts.some(c => new Date(c.checked_at).getTime() > Date.now())) {
      setMessage("Observation and contact checks cannot be in the future."); return;
    }
    if (new Set(draft.contacts.map(c => c.phone)).size !== draft.contacts.length) {
      setMessage("Each contact must have a different phone number."); return;
    }
    saveLock.current = true; setSaving(true); setMessage("");
    try {
      await api.post(`/insurance-growth/leads/${encodeURIComponent(selected.lead_id)}/review`, { expected_revision: selected.review_revision, review: draft });
      if (!alive.current) return;
      setMessage("Review saved. No outreach was queued. Refreshing recorded results.");
      await refresh();
    } catch (e) {
      if (!alive.current) return;
      const isConflict = e instanceof Error && e.message.startsWith("API 409:");
      const isValidation = e instanceof Error && e.message.startsWith("API 422:");
      setConflict(isConflict);
      setMessage(isConflict ? "Another review changed this lead. Reload the latest data and select the lead again before saving. Your changes have not been saved." : isValidation ? "Review was not saved. Check phone format, evidence references, dates, and name and role for verified contacts." : "Save was not confirmed. Reload the latest data before retrying.");
      // A network failure can follow a successful write. Require reload, not a blind retry.
      if (!isConflict && !isValidation) setConflict(true);
    } finally {
      saveLock.current = false;
      if (alive.current) setSaving(false);
    }
  }
  const f = data?.funnel;
  return <div className="space-y-6">
    <PageHeader title="Insurance Growth Review" subtitle="Review evidence, contact quality, and recorded outcomes. This workspace never sends or calls." action={<Link className="btn-ghost" href="/insurance">Back to insurance</Link>} />
    <div className="card space-y-2 border border-amber-200 bg-amber-50 text-sm">
      <p><strong>Review only.</strong> Saving evidence does not authorize contact, change suppression, or update the phone used for live dialing.</p>
      <p>Mass.gov automation is not connected. Massachusetts public records require manual evidence; public records do not establish renewal dates or permission to contact.</p>
      <p>The existing single-producer transfer path is implemented, but operational setup is unverified. No new live routing is enabled here.</p>
    </div>
    <div className="flex items-center gap-3"><button className="btn-ghost" disabled={loading || saving} onClick={() => { setMessage(""); void refresh(); }}>Reload latest data</button><span className="text-xs text-gray-500">Reload closes the editor and discards unsaved changes.</span></div>
    {message && <p role="status" className="rounded-lg border border-gray-200 p-3 text-sm">{message}</p>}
    {loading && <p role="status">Loading growth review…</p>}
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {!loading && data && f && <>
      <section className="space-y-3" aria-labelledby="funnel-title">
        <h2 id="funnel-title" className="text-lg font-semibold">Recorded outcomes · last {f.days} days</h2>
        <p className="text-xs text-gray-500">{new Date(f.period_start).toLocaleString()} to {new Date(f.period_end).toLocaleString()}. Operator-reported outcomes, not carrier-verified sales. Attempts include repeat calls; lead counts are distinct insurance leads within this period.</p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard label="Call attempts" value={f.call_attempts} hint={`${f.invalid_number_attempts} invalid-number attempts`} />
          <KpiCard label="Answered leads" value={f.answered_leads} />
          <KpiCard label="Quoted leads" value={f.quoted_leads} />
          <KpiCard label="Sold leads" value={f.sold_leads} />
          <KpiCard label="Answered + quoted / answered" value={percent(f.answer_to_quote_rate)} hint={`${f.answered_and_quoted_leads} / ${f.answered_leads} distinct leads`} />
          <KpiCard label="Quoted + sold / quoted" value={percent(f.quote_to_sale_rate)} hint={`${f.quoted_and_sold_leads} / ${f.quoted_leads} distinct leads`} />
        </div>
        <p className="text-xs text-gray-500">Sources reflect the current review source, not historical acquisition. These are overlaps of recorded outcomes, not proof of ordered conversion or campaign attribution. N/A means no denominator.</p>
        <div className="card overflow-x-auto"><table className="w-full"><thead><tr>{["Current review source", "Attempts", "Answered leads", "Quoted leads", "Sold leads"].map(h => <th className="th" key={h}>{h}</th>)}</tr></thead><tbody>{f.by_source.map(s => <tr key={s.source}><td className="td">{s.source || "Unknown"}</td><td className="td">{s.call_attempts}</td><td className="td">{s.answered_leads}</td><td className="td">{s.quoted_leads}</td><td className="td">{s.sold_leads}</td></tr>)}{!f.by_source.length && <tr><td className="td" colSpan={5}>No recorded outcomes in this period.</td></tr>}</tbody></table></div>
      </section>
      <section className="space-y-3" aria-labelledby="prospect-title">
        <h2 id="prospect-title" className="text-lg font-semibold">Prospect evidence review</h2>
        <p className="text-sm text-gray-500">Showing {data.prospects.items.length} of {data.prospects.total} prospects (limit {data.prospects.limit}). Contact verification is operator-reported, not independent verification or consent.</p>
        <div className="card overflow-x-auto"><table className="w-full"><thead><tr>{["Prospect", "Recorded contact", "Source / flags", "Review"].map(h => <th key={h} className="th">{h}</th>)}</tr></thead><tbody>{data.prospects.items.map(p => <tr key={p.lead_id} className="border-t border-gray-100"><td className="td">{p.name || "Unnamed prospect"}<div className="text-xs text-gray-500">{p.segment}</div>{p.suppressed && <strong className="text-red-700">Suppressed: do not contact</strong>}</td><td className="td text-xs">{p.phone || "No phone"}<br />{p.email || "No email"}</td><td className="td text-xs">{p.source || "Unknown source"}<div>{p.review_flags.map(flag => flag.replaceAll("_", " ")).join(" · ") || "No review flags reported"}</div></td><td className="td"><button className="btn-ghost" disabled={saving} onClick={() => select(p)}>Review evidence</button></td></tr>)}{!data.prospects.items.length && <tr><td colSpan={4} className="td">No prospects available for review.</td></tr>}</tbody></table></div>
        {selected && <form onSubmit={save} className="card space-y-4" aria-label="Prospect evidence editor">
          <div className="flex items-center justify-between"><h3 className="font-semibold">Review: {selected.name || "Unnamed prospect"} · revision {selected.review_revision}</h3><button type="button" className="btn-ghost" disabled={saving} onClick={() => setSelected(null)}>Close editor</button></div>
          {selected.suppressed && <p className="text-sm font-semibold text-red-700">Suppressed. Evidence may be corrected, but this does not remove the do-not-contact restriction.</p>}
          <p className="text-sm text-gray-500">Record references and business contact details only. Do not enter policy numbers, government IDs, passwords, health details, or payment information.</p>
          <fieldset disabled={saving || conflict} className="space-y-4 disabled:opacity-60">
            <div className="grid gap-3 md:grid-cols-2">
              <label className="text-sm">Source type<select className={inputClass} value={draft.source_kind} onChange={e => setDraft(d => ({ ...d, source_kind: e.target.value as Review["source_kind"] }))}><option value="customer_report">Customer report</option><option value="authorized_agency">Authorized agency record</option><option value="public_business_record">Public business record</option><option value="massachusetts_public_record">Massachusetts public record (manual)</option></select></label>
              <label className="text-sm">Source reference (required)<input required maxLength={1000} className={inputClass} value={draft.source_ref} onChange={e => setDraft(d => ({ ...d, source_ref: e.target.value }))} /></label>
              <label className="text-sm">Observed at (local time, required)<input required type="datetime-local" className={inputClass} value={localDateTime(draft.observed_at)} onChange={e => setDraft(d => ({ ...d, observed_at: e.target.value ? new Date(e.target.value).toISOString() : "" }))} /></label>
              <label className="text-sm">Renewal basis<select className={inputClass} value={draft.renewal_basis} onChange={e => setDraft(d => ({ ...d, renewal_basis: e.target.value as Review["renewal_basis"], ...(e.target.value === "unknown" ? { renewal_date: null, renewal_evidence_ref: null } : {}) }))}><option value="unknown">Unknown (do not infer)</option><option value="customer_confirmed">Customer confirmed</option><option value="authorized_policy_record">Authorized policy record</option></select></label>
              <label className="text-sm">Renewal date<input type="date" required={draft.renewal_basis !== "unknown"} disabled={draft.renewal_basis === "unknown"} className={inputClass} value={draft.renewal_date || ""} onChange={e => setDraft(d => ({ ...d, renewal_date: e.target.value || null }))} /></label>
              <label className="text-sm">Renewal evidence reference<input required={draft.renewal_basis !== "unknown"} disabled={draft.renewal_basis === "unknown"} maxLength={1000} className={inputClass} value={draft.renewal_evidence_ref || ""} onChange={e => setDraft(d => ({ ...d, renewal_evidence_ref: e.target.value || null }))} /></label>
            </div>
            <h4 className="font-medium">Business contacts ({draft.contacts.length}/5)</h4>
            {draft.contacts.map((c, index) => <div className="space-y-3 rounded-lg border border-gray-200 p-3" key={index}><div className="grid gap-3 md:grid-cols-2">
              <label className="text-sm">Phone (+country code, digits only)<input required type="tel" pattern="\+[1-9][0-9]{7,14}" maxLength={16} className={inputClass} value={c.phone} onChange={e => updateContact(index, { phone: e.target.value })} /></label>
              <label className="text-sm">Contact name<input required={c.status === "verified"} maxLength={200} className={inputClass} value={c.name} onChange={e => updateContact(index, { name: e.target.value })} /></label>
              <label className="text-sm">Role<input required={c.status === "verified"} maxLength={100} className={inputClass} value={c.role} onChange={e => updateContact(index, { role: e.target.value })} /></label>
              <label className="text-sm">Reported status<select className={inputClass} value={c.status} onChange={e => updateContact(index, { status: e.target.value as Contact["status"] })}><option value="unverified">Unverified</option><option value="verified">Verified by operator</option><option value="wrong_number">Wrong number</option><option value="disconnected">Disconnected</option></select></label>
              <label className="text-sm">Evidence reference<input required maxLength={1000} className={inputClass} value={c.evidence_ref} onChange={e => updateContact(index, { evidence_ref: e.target.value })} /></label>
              <label className="text-sm">Checked at (local time)<input required type="datetime-local" className={inputClass} value={localDateTime(c.checked_at)} onChange={e => updateContact(index, { checked_at: e.target.value ? new Date(e.target.value).toISOString() : "" })} /></label>
            </div><button className="btn-ghost" type="button" onClick={() => setDraft(d => ({ ...d, contacts: d.contacts.filter((_, i) => i !== index) }))}>Remove contact {index + 1}</button></div>)}
            <button type="button" className="btn-ghost" disabled={draft.contacts.length >= 5} onClick={() => setDraft(d => ({ ...d, contacts: [...d.contacts, { phone: "", name: "", role: "", status: "unverified", evidence_ref: "", checked_at: "" }] }))}>Add contact</button>
            <label className="block text-sm">Review notes<textarea rows={3} maxLength={2000} className={inputClass} value={draft.notes} onChange={e => setDraft(d => ({ ...d, notes: e.target.value }))} /></label>
            <button className="btn" type="submit" disabled={saving || conflict}>{saving ? "Saving…" : "Save review only"}</button>
          </fieldset>
        </form>}
      </section>
      <section className="space-y-3" aria-labelledby="coverage-title"><h2 id="coverage-title" className="text-lg font-semibold">Client coverage review questions</h2><p className="text-sm text-gray-500">Showing {data.cross_sell.items.length} client groups from up to {data.cross_sell.limit} policy records; {data.cross_sell.total_records} active records total. Based on recorded active client policies, not complete coverage. A missing record is not proof of missing insurance. Confirm coverage with the client or authorized records before making a recommendation.</p><div className="grid gap-3 md:grid-cols-2">{data.cross_sell.items.map((c, i) => <article key={`${c.client_id}-${i}`} className="card space-y-2"><h3 className="font-semibold">{c.name || "Unnamed client"}</h3>{c.suppressed && <p className="font-semibold text-red-700">Suppressed: do not contact</p>}<p className="text-sm">Recorded lines: {c.recorded_lines.join(", ") || "None recorded"}</p>{c.expires_at && <p className="text-xs text-gray-500">Recorded expiration: {c.expires_at}</p>}<ul className="list-disc space-y-1 pl-5 text-sm">{c.questions.map((q, j) => <li key={j}>{q}</li>)}</ul>{!c.questions.length && <p className="text-sm text-gray-500">No review questions reported.</p>}</article>)}</div>{!data.cross_sell.items.length && <p className="text-sm text-gray-500">No active client policy records available.</p>}</section>
    </>}
  </div>;
}

export default function Page() {
  return <AuthGate><Growth /></AuthGate>;
}
