"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, KpiCard, LoadState } from "@/components/ui";

type Client = {
  id: string; business: string; name: string; email: string | null; phone: string | null;
  address: string | null; city: string | null; state: string | null; zip: string | null;
  line: string | null; carrier: string | null; policy_number: string | null;
  premium_monthly: number | null; quote_amount: number | null; services: string | null;
  status: string; signed_at: string | null; expires_at: string | null; notes: string | null;
  last_contacted_at: string | null; days_to_expiry: number | null; expiring_soon: boolean;
  timeline?: TimelineItem[]; emails?: EmailItem[];
};
type TimelineItem = { id: string; kind: string; body: string; author: string | null; created_at: string };
type EmailItem = { id: string; direction: string; subject: string | null; status: string; from_account: string; snippet: string; date: string | null };
type Summary = {
  clients: number; active: number; expiring_soon: number;
  monthly_premium: number; annual_premium: number;
  by_line: Record<string, number>; by_carrier: Record<string, number>;
  by_business: Record<string, { clients: number; monthly_premium: number }>;
};
type Business = { key: string; label: string };
type Options = { carriers: string[]; lines: string[]; states: string[]; statuses: string[]; note_kinds: string[]; businesses: Business[] };

const money = (n: number | null) => (n == null ? "—" : n >= 1000 ? `$${(n / 1000).toFixed(1)}k` : `$${n}`);
const LINE_BADGE: Record<string, string> = {
  home: "bg-sky-100 text-sky-700", auto: "bg-amber-100 text-amber-700",
  life: "bg-rose-100 text-rose-700", commercial: "bg-violet-100 text-violet-700",
};

const EMPTY: Partial<Client> = { business: "insurance", name: "", status: "Active", state: "MA", line: "auto" };

function CRM() {
  const initExpiring = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("expiring") === "1";
  const [f, setF] = useState({ business: "", line: "", carrier: "", state: "", status: "", q: "", expiring: initExpiring });
  const [refresh, setRefresh] = useState(0);
  const qs = new URLSearchParams(
    Object.entries(f).filter(([, v]) => v !== "" && v !== false).map(([k, v]) => [k, String(v)])
  ).toString();
  const { data: opts } = useFetch<Options>(() => api.get<Options>("/book/carriers"));
  const { data: summary } = useFetch<Summary>(() => api.get<Summary>("/book/summary"), [refresh]);
  const { data, loading, error, reload } = useFetch<Client[]>(
    () => api.get<Client[]>(`/book/clients${qs ? `?${qs}` : ""}`), [qs, refresh]);

  const [editing, setEditing] = useState<Partial<Client> | null>(null); // add/edit form
  const [detail, setDetail] = useState<Client | null>(null);            // detail + timeline
  const [msg, setMsg] = useState("");
  const bizLabel = (k: string) => opts?.businesses.find((b) => b.key === k)?.label || k;

  async function openDetail(id: string) {
    try { setDetail(await api.get<Client>(`/book/clients/${id}`)); }
    catch (e) { setMsg(`❌ ${e}`); }
  }

  async function save(c: Partial<Client>) {
    try {
      if (c.id) await api.patch(`/book/clients/${c.id}`, c);
      else await api.post("/book/clients", c);
      setEditing(null); setRefresh((n) => n + 1); setMsg("✅ Saved.");
    } catch (e) { setMsg(`❌ ${e}`); }
  }

  async function remove(id: string) {
    if (!confirm("Delete this client and their history?")) return;
    try { await api.del(`/book/clients/${id}`); setDetail(null); setRefresh((n) => n + 1); }
    catch (e) { setMsg(`❌ ${e}`); }
  }

  return (
    <div>
      <PageHeader title="Client Book (CRM)"
        subtitle="Your won insurance clients — carrier, line, premium, renewal dates and full communication history. The post-sale book of business."
        action={
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={() => api.download(`/export/clients.csv${f.business ? `?business=${f.business}` : ""}`, "clients.csv")}>Export CSV</button>
            <button className="btn" onClick={() => setEditing({ ...EMPTY })}>+ Add client</button>
          </div>
        } />
      {msg && <p className="mb-3 text-sm text-gray-600">{msg}</p>}

      {summary && (
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-5">
          <KpiCard label="Clients" value={summary.clients.toLocaleString()} />
          <KpiCard label="Active" value={summary.active.toLocaleString()} />
          <KpiCard label="Renewing ≤30d" value={summary.expiring_soon.toLocaleString()} />
          <KpiCard label="Monthly premium" value={money(summary.monthly_premium)} />
          <KpiCard label="Annual premium" value={money(summary.annual_premium)} />
        </div>
      )}

      {/* Per-business breakdown — click to filter */}
      {summary?.by_business && Object.keys(summary.by_business).length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {Object.entries(summary.by_business).map(([k, v]) => (
            <button key={k} onClick={() => setF({ ...f, business: f.business === k ? "" : k })}
              className={`rounded-lg border px-3 py-1.5 text-sm ${f.business === k ? "border-brand bg-brand/10 font-semibold" : "border-gray-200 bg-white"}`}>
              {bizLabel(k)} · <b>{v.clients}</b>
              {v.monthly_premium > 0 && <span className="text-gray-400"> · {money(v.monthly_premium)}/mo</span>}
            </button>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="mb-4 flex flex-wrap gap-2">
        <input className="input" placeholder="Search name/email/policy…" value={f.q}
          onChange={(e) => setF({ ...f, q: e.target.value })} />
        <select className="input" value={f.business} onChange={(e) => setF({ ...f, business: e.target.value })}>
          <option value="">All businesses</option>{opts?.businesses.map((b) => <option key={b.key} value={b.key}>{b.label}</option>)}
        </select>
        <select className="input" value={f.line} onChange={(e) => setF({ ...f, line: e.target.value })}>
          <option value="">All lines</option>{opts?.lines.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
        <select className="input" value={f.state} onChange={(e) => setF({ ...f, state: e.target.value })}>
          <option value="">All states</option>{opts?.states.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="input" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
          <option value="">Any status</option>{opts?.statuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <label className="flex items-center gap-1 text-sm text-gray-600">
          <input type="checkbox" checked={f.expiring} onChange={(e) => setF({ ...f, expiring: e.target.checked })} />
          Renewing soon
        </label>
      </div>

      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}
      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs text-gray-500">
            <tr><th className="p-3">Client</th><th className="p-3">Business</th><th className="p-3">Carrier</th><th className="p-3">Line</th>
              <th className="p-3">State</th><th className="p-3">Premium/mo</th><th className="p-3">Status</th>
              <th className="p-3">Renews</th><th className="p-3">Last contact</th></tr>
          </thead>
          <tbody>
            {(data || []).map((c) => (
              <tr key={c.id} className="cursor-pointer border-t hover:bg-gray-50" onClick={() => openDetail(c.id)}>
                <td className="p-3"><div className="font-medium">{c.name}</div><div className="text-xs text-gray-400">{c.email}</div></td>
                <td className="p-3"><span className="badge bg-gray-100 text-gray-600">{bizLabel(c.business)}</span></td>
                <td className="p-3">{c.carrier || "—"}</td>
                <td className="p-3">{c.line ? <span className={`badge ${LINE_BADGE[c.line] || "bg-gray-100"}`}>{c.line}</span> : "—"}</td>
                <td className="p-3">{c.state || "—"}</td>
                <td className="p-3">{money(c.premium_monthly)}</td>
                <td className="p-3"><span className="badge bg-gray-100 text-gray-600">{c.status}</span></td>
                <td className="p-3 text-xs">
                  {c.expires_at ? new Date(c.expires_at + "T00:00:00").toLocaleDateString() : "—"}
                  {c.expiring_soon && <span className="ml-1 badge bg-amber-100 text-amber-700">{c.days_to_expiry}d</span>}
                </td>
                <td className="p-3 text-xs text-gray-400">{c.last_contacted_at ? new Date(c.last_contacted_at).toLocaleDateString() : "—"}</td>
              </tr>
            ))}
            {!loading && (data || []).length === 0 && (
              <tr><td colSpan={9} className="p-6 text-center text-gray-400">No clients yet — add your first won client, or convert a won lead.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {editing && <EditModal c={editing} opts={opts} onClose={() => setEditing(null)} onSave={save} />}
      {detail && <DetailModal c={detail} opts={opts} onClose={() => setDetail(null)}
        onEdit={() => { setEditing(detail); setDetail(null); }} onDelete={() => remove(detail.id)}
        onNote={() => openDetail(detail.id)} onMsg={setMsg} />}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block text-sm"><span className="text-gray-600">{label}</span>{children}</label>;
}

function EditModal({ c, opts, onClose, onSave }: {
  c: Partial<Client>; opts: Options | null; onClose: () => void; onSave: (c: Partial<Client>) => void;
}) {
  const [form, setForm] = useState<Partial<Client>>(c);
  const set = (k: keyof Client, v: unknown) => setForm((p) => ({ ...p, [k]: v }));
  const num = (v: string) => (v === "" ? null : Number(v));
  return (
    <Modal onClose={onClose} title={c.id ? "Edit client" : "Add client"}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Business"><select className="input w-full" value={form.business || "insurance"} onChange={(e) => set("business", e.target.value)}>
          {(opts?.businesses || []).map((b) => <option key={b.key} value={b.key}>{b.label}</option>)}</select></Field>
        <Field label="Name *"><input className="input w-full" value={form.name || ""} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Email"><input className="input w-full" value={form.email || ""} onChange={(e) => set("email", e.target.value)} /></Field>
        <Field label="Phone"><input className="input w-full" value={form.phone || ""} onChange={(e) => set("phone", e.target.value)} /></Field>
        <Field label="Policy #"><input className="input w-full" value={form.policy_number || ""} onChange={(e) => set("policy_number", e.target.value)} /></Field>
        <Field label="Address"><input className="input w-full" value={form.address || ""} onChange={(e) => set("address", e.target.value)} /></Field>
        <Field label="City"><input className="input w-full" value={form.city || ""} onChange={(e) => set("city", e.target.value)} /></Field>
        <Field label="State"><select className="input w-full" value={form.state || ""} onChange={(e) => set("state", e.target.value)}>
          <option value="">—</option>{opts?.states.map((s) => <option key={s}>{s}</option>)}</select></Field>
        <Field label="ZIP"><input className="input w-full" value={form.zip || ""} onChange={(e) => set("zip", e.target.value)} /></Field>
        <Field label="Line"><select className="input w-full" value={form.line || ""} onChange={(e) => set("line", e.target.value)}>
          <option value="">—</option>{opts?.lines.map((l) => <option key={l}>{l}</option>)}</select></Field>
        <Field label="Carrier"><input className="input w-full" list="carriers" value={form.carrier || ""} onChange={(e) => set("carrier", e.target.value)} />
          <datalist id="carriers">{opts?.carriers.map((c2) => <option key={c2} value={c2} />)}</datalist></Field>
        <Field label="Premium / month ($)"><input type="number" className="input w-full" value={form.premium_monthly ?? ""} onChange={(e) => set("premium_monthly", num(e.target.value))} /></Field>
        <Field label="Quote ($)"><input type="number" className="input w-full" value={form.quote_amount ?? ""} onChange={(e) => set("quote_amount", num(e.target.value))} /></Field>
        <Field label="Status"><select className="input w-full" value={form.status || "Active"} onChange={(e) => set("status", e.target.value)}>
          {opts?.statuses.map((s) => <option key={s}>{s}</option>)}</select></Field>
        <Field label="Signed up"><input type="date" className="input w-full" value={form.signed_at || ""} onChange={(e) => set("signed_at", e.target.value)} /></Field>
        <Field label="Expires / renews"><input type="date" className="input w-full" value={form.expires_at || ""} onChange={(e) => set("expires_at", e.target.value)} /></Field>
        <div className="sm:col-span-2"><Field label="Services / coverage"><textarea className="input w-full" rows={2} value={form.services || ""} onChange={(e) => set("services", e.target.value)} /></Field></div>
        <div className="sm:col-span-2"><Field label="Notes"><textarea className="input w-full" rows={2} value={form.notes || ""} onChange={(e) => set("notes", e.target.value)} /></Field></div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn" onClick={() => onSave(form)} disabled={!form.name?.trim()}>Save</button>
      </div>
    </Modal>
  );
}

function DetailModal({ c, opts, onClose, onEdit, onDelete, onNote, onMsg }: {
  c: Client; opts: Options | null; onClose: () => void; onEdit: () => void; onDelete: () => void;
  onNote: () => void; onMsg: (s: string) => void;
}) {
  const [kind, setKind] = useState("note");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  async function addNote() {
    if (!body.trim()) return;
    setBusy(true);
    try { await api.post(`/book/clients/${c.id}/notes`, { kind, body }); setBody(""); onNote(); onMsg("✅ Logged."); }
    catch (e) { onMsg(`❌ ${e}`); }
    finally { setBusy(false); }
  }
  const row = (label: string, val: React.ReactNode) => (
    <div><div className="text-xs text-gray-400">{label}</div><div>{val || "—"}</div></div>
  );
  return (
    <Modal onClose={onClose} title={c.name}>
      <div className="mb-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
        {row("Carrier", c.carrier)}{row("Line", c.line)}{row("Status", c.status)}
        {row("Premium/mo", money(c.premium_monthly))}{row("Quote", money(c.quote_amount))}{row("Policy #", c.policy_number)}
        {row("Email", c.email)}{row("Phone", c.phone)}{row("State", c.state)}
        {row("Address", [c.address, c.city, c.zip].filter(Boolean).join(", "))}
        {row("Signed", c.signed_at)}{row("Renews", c.expires_at + (c.expiring_soon ? ` (${c.days_to_expiry}d)` : ""))}
        <div className="col-span-full">{row("Services", c.services)}</div>
      </div>

      {/* Log a communication */}
      <div className="mb-3 rounded-lg border border-gray-200 p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Log communication</div>
        <div className="flex gap-2">
          <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
            {(opts?.note_kinds || ["note", "call", "email", "sms", "meeting"]).map((k) => <option key={k}>{k}</option>)}
          </select>
          <input className="input flex-1" placeholder="What happened?" value={body}
            onChange={(e) => setBody(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addNote()} />
          <button className="btn" onClick={addNote} disabled={busy || !body.trim()}>Add</button>
        </div>
      </div>

      {/* Timeline */}
      <div className="max-h-56 space-y-2 overflow-y-auto">
        {(c.timeline || []).map((t) => (
          <div key={t.id} className="rounded-lg bg-gray-50 p-2 text-sm">
            <div className="flex justify-between text-xs text-gray-400">
              <span className="uppercase">{t.kind}</span>
              <span>{new Date(t.created_at).toLocaleString()}</span>
            </div>
            <div>{t.body}</div>
          </div>
        ))}
        {(c.timeline || []).length === 0 && <p className="text-sm text-gray-400">No communication logged yet.</p>}
      </div>

      {/* Email history — outreach + replies tied to this contact's address */}
      <div className="mt-4">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Email history</div>
        <div className="max-h-56 space-y-2 overflow-y-auto">
          {(c.emails || []).map((e) => (
            <div key={e.id} className="rounded-lg border border-gray-100 p-2 text-sm">
              <div className="flex justify-between text-xs text-gray-400">
                <span>{e.direction === "inbound" ? "⬅ received" : "➡ sent"} · {e.status}{e.from_account ? ` · ${e.from_account}` : ""}</span>
                <span>{e.date ? new Date(e.date).toLocaleString() : ""}</span>
              </div>
              {e.subject && <div className="font-medium">{e.subject}</div>}
              {e.snippet && <div className="text-gray-600">{e.snippet}</div>}
            </div>
          ))}
          {(c.emails || []).length === 0 && <p className="text-sm text-gray-400">No emails linked to this address yet.</p>}
        </div>
      </div>

      <div className="mt-4 flex justify-between">
        <button className="text-sm text-red-500" onClick={onDelete}>Delete</button>
        <div className="flex gap-2"><button className="btn-ghost" onClick={onClose}>Close</button>
          <button className="btn" onClick={onEdit}>Edit</button></div>
      </div>
    </Modal>
  );
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/40 p-4" onClick={onClose}>
      <div className="mt-8 w-full max-w-2xl rounded-xl bg-white p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">{title}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><CRM /></AuthGate>;
}
