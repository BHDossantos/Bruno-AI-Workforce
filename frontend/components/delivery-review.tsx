"use client";

import { useState } from "react";
import { api } from "@/lib/api";

type Attempt = {
  key: string; channel: string; state: "pending" | "unknown" | "rejected";
  recipient: string | null; account: string | null; operation_ref: string | null;
  created_at: string;
};
type Evidence = { id: number; actor: string; decision: string; evidence: string; provider_reference: string; created_at: string };

export function DeliveryReview() {
  const [items, setItems] = useState<Attempt[] | null>(null);
  const [selected, setSelected] = useState<Attempt | null>(null);
  const [history, setHistory] = useState<Evidence[]>([]);
  const [decision, setDecision] = useState("keep_held");
  const [evidence, setEvidence] = useState("");
  const [reference, setReference] = useState("");
  const [receipt, setReceipt] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true); setNote("");
    try { setItems(await api.get<Attempt[]>("/messages/delivery-attempts")); }
    catch (err) { setNote(String(err)); }
    finally { setBusy(false); }
  }
  async function select(item: Attempt) {
    setSelected(item); setDecision("keep_held"); setEvidence(""); setReference(""); setReceipt(""); setHistory([]);
    try { setHistory(await api.get<Evidence[]>(`/messages/delivery-attempts/${item.key}/history`)); }
    catch (err) { setNote(String(err)); }
  }
  async function resolve() {
    if (!selected) return;
    if (decision !== "keep_held" && !confirm("Record this provider-confirmed outcome? This releases the recipient hold for future actions but never retries this message. A missing provider record is not proof of non-acceptance.")) return;
    setBusy(true); setNote("");
    try {
      await api.post(`/messages/delivery-attempts/${selected.key}/resolve`, {
        decision, expected_state: selected.state, evidence, provider_reference: reference,
        provider_id: receipt || null,
      });
      setNote("Evidence recorded. No message was sent or retried. Refresh the Outbox to see reconciled status.");
      setSelected(null);
      setItems(await api.get<Attempt[]>("/messages/delivery-attempts"));
    } catch (err) { setNote(String(err)); }
    finally { setBusy(false); }
  }
  return <section className="card mb-4 space-y-3" aria-label="Delivery reconciliation">
    <button className="btn-ghost" disabled={busy} onClick={load}>Review held deliveries (operators)</button>
    <p className="text-xs text-gray-600">Verify the recipient, time and provider records. Uncertain outcomes remain held. Pending workers may still send; their holds cannot be released here. Never use absence of a receipt as proof that nothing was sent.</p>
    {note && <p role="status" className="text-sm">{note}</p>}
    {items && <div className="max-h-64 overflow-auto">
      {items.length === 0 && <p>No held deliveries to review.</p>}
      {items.map(item => <button key={item.key} className="block w-full border-b p-2 text-left text-sm" onClick={() => select(item)}>
        {item.recipient || "Unknown recipient"} · {item.channel} · {item.account} · {item.state} · {new Date(item.created_at).toLocaleString()}
      </button>)}
    </div>}
    {selected && <div className="space-y-3 border-t pt-3">
      <p className="break-all text-xs">Attempt: {selected.key}{selected.operation_ref ? ` · ${selected.operation_ref}` : ""}</p>
      <label className="block text-sm">Outcome
        <select className="ml-2 rounded border p-2" value={decision} onChange={e => setDecision(e.target.value)}>
          <option value="keep_held">Keep held — outcome uncertain</option>
          <option value="accepted" disabled={selected.state === "pending"}>Provider confirms acceptance</option>
          <option value="not_accepted" disabled={selected.state === "pending"}>Provider confirms never accepted</option>
        </select>
      </label>
      <label className="block text-sm">Provider record or support-case reference
        <input className="block w-full rounded border p-2" value={reference} maxLength={200} onChange={e => setReference(e.target.value)} />
      </label>
      {decision === "accepted" && <label className="block text-sm">Provider receipt ID
        <input className="block w-full rounded border p-2" value={receipt} maxLength={200} onChange={e => setReceipt(e.target.value)} />
      </label>}
      <label className="block text-sm">Evidence supporting this outcome (no credentials)
        <textarea className="block w-full rounded border p-2" value={evidence} maxLength={2000} onChange={e => setEvidence(e.target.value)} />
      </label>
      <button className="btn" disabled={busy || evidence.trim().length < 20 || reference.trim().length < 5 || (decision === "accepted" && !receipt.trim())} onClick={resolve}>Record evidence — do not send</button>
      {history.map(entry => <p key={entry.id} className="text-xs">{new Date(entry.created_at).toLocaleString()} · {entry.decision} · {entry.provider_reference}: {entry.evidence}</p>)}
    </div>}
  </section>;
}
