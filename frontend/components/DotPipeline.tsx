"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
const stages = ["new", "verified", "contacted", "qualified", "documents_pending", "quote_presented", "policy_issued"];
type Pipeline = { revision: number; stage: string; owner_id: string | null; next_action: string | null; due_at: string | null;
  history: { event_id: string; from_stage: string; to_stage: string; recorded_at: string; request: { note: string; evidence_ref: string } }[] };
type Summary = { stage_counts: Record<string, number>; total_cases: number; operator_reported_issued: number; operator_reported_conversion_rate: number };
type Reminder = { usdot: string; next_action: string; due_at: string };
export default function DotPipeline({ usdot, onUpdated }: { usdot: string; onUpdated: () => Promise<void> }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [pipeline, setPipeline] = useState<Pipeline | null>(null);
  const [stage, setStage] = useState("new"); const [note, setNote] = useState(""); const [evidence, setEvidence] = useState("");
  const [next, setNext] = useState(""); const [due, setDue] = useState(""); const [occurred, setOccurred] = useState("");
  const [policy, setPolicy] = useState(""); const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const [notice, setNotice] = useState("");
  const retry = useRef<{ key: string; id: string } | null>(null);
  async function refresh(dot: string) {
    const [s, r, d] = await Promise.all([api.get<Summary>("/dot-review/pipeline/summary"),
      api.get<Reminder[]>("/dot-review/pipeline/reminders"),
      dot ? api.get<{pipeline: Pipeline}>(`/dot-review/${dot}`) : Promise.resolve(null)]);
    setSummary(s); setReminders(r); setPipeline(d?.pipeline || null); setStage(d?.pipeline.stage || "new");
  }
  useEffect(() => { let active = true; setPipeline(null); setNotice(""); setError(""); setPolicy(""); setConfirmed(false);
    // Ignore a slow response after switching cases.
    Promise.all([api.get<Summary>("/dot-review/pipeline/summary"), api.get<Reminder[]>("/dot-review/pipeline/reminders"),
      usdot ? api.get<{pipeline: Pipeline}>(`/dot-review/${usdot}`) : Promise.resolve(null)]).then(([s,r,d]) => {
        if (active) { setSummary(s); setReminders(r); setPipeline(d?.pipeline || null); setStage(d?.pipeline.stage || "new"); }
      }).catch(e => { if (active) setError(String(e)); });
    return () => { active = false; };
  }, [usdot]);
  return <section className="card space-y-3">
    <h2 className="font-semibold">Commercial trucking pipeline</h2>
    {summary && <><div className="flex flex-wrap gap-3">{stages.map(s => <p key={s} className="border rounded p-2">{s.replaceAll("_", " ")}: {summary.stage_counts[s] || 0}</p>)}</div>
      <p>{summary.operator_reported_issued} operator-reported policies / {summary.total_cases} research cases ({(summary.operator_reported_conversion_rate * 100).toFixed(1)}%). Carrier verification is not connected. Call attempts and voicemails are not conversions.</p></>}
    <h3 className="font-semibold">My due actions (first 50)</h3>
    {reminders.length ? reminders.map(r => <p key={r.usdot}>USDOT {r.usdot}: {r.next_action} · {new Date(r.due_at).toLocaleString()}</p>) : <p>No overdue assigned actions.</p>}
    {error && <p role="alert" className="text-red-700">{error}</p>}{notice && <p role="status">{notice}</p>}
    {pipeline && <form className="space-y-2" onSubmit={e => { e.preventDefault(); void (async () => {
      setBusy(true); setError(""); setNotice("");
      try {
        const payload = {expected_revision: pipeline.revision, stage, note, evidence_ref: evidence, next_action: next,
          due_at: new Date(due).toISOString(), occurred_at: new Date(occurred).toISOString(),
          ...(stage === "policy_issued" ? {policy_reference: policy, issuance_confirmed: confirmed} : {})};
        const key = JSON.stringify([usdot, payload]); if (retry.current?.key !== key) retry.current = {key, id: crypto.randomUUID()};
        await api.post(`/dot-review/${usdot}/pipeline`, {...payload, event_id: retry.current.id}); retry.current = null;
        await refresh(usdot); await onUpdated(); setNotice("Pipeline saved and next action assigned to you. No outreach sent.");
      } catch (e) { setError(String(e)); } finally { setBusy(false); }
    })(); }}>
      <h3 className="font-semibold">USDOT {usdot} · {pipeline.stage.replaceAll("_", " ")}</h3>
      <p>Owner: {pipeline.owner_id || "Unassigned"}. Next: {pipeline.next_action || "Not recorded"}. {pipeline.due_at && `Due ${new Date(pipeline.due_at).toLocaleString()}`}</p>
      <p>“Verified” records human research progress. Missing registry or SAFER results remain uncertain and do not prevent a clarification call.</p>
      <label className="block">Stage <select value={stage} onChange={e => setStage(e.target.value)}>{stages.map(s => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}</select></label>
      <label className="block">What actually happened <textarea required maxLength={2000} value={note} onChange={e => setNote(e.target.value)} className="border rounded p-2 w-full" /></label>
      <label className="block">Evidence reference <input required maxLength={1000} value={evidence} onChange={e => setEvidence(e.target.value)} className="border rounded p-2 w-full" /></label>
      <label className="block">When it happened <input required type="datetime-local" value={occurred} onChange={e => setOccurred(e.target.value)} /></label>
      <label className="block">Next action <input required maxLength={1000} value={next} onChange={e => setNext(e.target.value)} className="border rounded p-2 w-full" /></label>
      <label className="block">Action due <input required type="datetime-local" value={due} onChange={e => setDue(e.target.value)} /></label>
      {stage === "policy_issued" && <><label className="block">Issued policy reference <input required value={policy} onChange={e => setPolicy(e.target.value)} /></label>
        <label className="block"><input required type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} /> I verified that this policy was actually issued; this is not a quote or voicemail.</label></>}
      <button disabled={busy} className="btn-primary">Save and assign next action to me</button>
      <h4 className="font-semibold">Recent stage history</h4>
      {pipeline.history.slice(-10).reverse().map(h => <p key={h.event_id}>{h.from_stage} → {h.to_stage}: {h.request.note} · {h.request.evidence_ref} · Recorded {new Date(h.recorded_at).toLocaleString()}</p>)}
    </form>}
  </section>;
}
