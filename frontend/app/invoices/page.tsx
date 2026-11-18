"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

type Line = { description: string; quantity: number; unit_price: number; amount?: number };
type Invoice = {
  id: string; number: string; business: string; client_name: string; client_email: string | null;
  status: string; currency: string; issue_date: string | null; due_date: string | null;
  subtotal: number; total: number; amount_paid: number; balance: number; notes: string | null;
};
type Summary = {
  outstanding: number; overdue: number; paid_this_month: number;
  total_invoices: number; counts: Record<string, number>;
};

const money = (n: number) => `$${(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const STATUS_STYLE: Record<string, string> = {
  Draft: "bg-gray-100 text-gray-600",
  Sent: "bg-sky-100 text-sky-700",
  Paid: "bg-emerald-100 text-emerald-700",
  Overdue: "bg-red-100 text-red-700",
  Void: "bg-gray-200 text-gray-400 line-through",
};

function Invoices() {
  const [list, setList] = useState<Invoice[]>([]);
  const [sum, setSum] = useState<Summary | null>(null);
  const [filter, setFilter] = useState<string>("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    client_name: "", client_email: "", business: "insurance", due_date: "", notes: "",
  });
  const [lines, setLines] = useState<Line[]>([{ description: "", quantity: 1, unit_price: 0 }]);
  const [busy, setBusy] = useState(false);

  async function load() {
    const [inv, s] = await Promise.all([
      api.get<Invoice[]>(`/invoices${filter ? `?status=${filter}` : ""}`),
      api.get<Summary>("/invoices/summary"),
    ]);
    setList(inv);
    setSum(s);
  }
  useEffect(() => { load().catch(() => {}); /* eslint-disable-next-line */ }, [filter]);

  const draftTotal = lines.reduce((t, l) => t + (Number(l.quantity) || 0) * (Number(l.unit_price) || 0), 0);

  async function create() {
    if (!form.client_name.trim()) { alert("Client name is required."); return; }
    const payload = {
      ...form,
      lines: lines
        .filter((l) => l.description.trim())
        .map((l) => ({ description: l.description, quantity: Number(l.quantity) || 1, unit_price: Number(l.unit_price) || 0 })),
    };
    setBusy(true);
    try {
      await api.post("/invoices", payload);
      setOpen(false);
      setForm({ client_name: "", client_email: "", business: "insurance", due_date: "", notes: "" });
      setLines([{ description: "", quantity: 1, unit_price: 0 }]);
      await load();
    } finally { setBusy(false); }
  }

  async function setStatus(id: string, status: string) {
    await api.post(`/invoices/${id}/status`, { status });
    await load();
  }
  async function recordPayment(inv: Invoice) {
    const raw = prompt(`Record a payment for ${inv.number} (balance ${money(inv.balance)}):`, String(inv.balance));
    if (raw == null) return;
    const amount = parseFloat(raw);
    if (!amount || amount <= 0) return;
    await api.post(`/invoices/${inv.id}/payments`, { amount });
    await load();
  }
  async function remove(id: string) {
    if (!confirm("Delete this invoice?")) return;
    await api.del(`/invoices/${id}`);
    await load();
  }

  const setLine = (i: number, k: keyof Line, v: string) =>
    setLines((ls) => ls.map((l, j) => (j === i ? { ...l, [k]: k === "description" ? v : Number(v) } : l)));

  const stat = (label: string, val: string, tone = "") => (
    <div className="card"><div className={`text-2xl font-bold ${tone}`}>{val}</div><div className="text-xs uppercase text-gray-400">{label}</div></div>
  );

  return (
    <div>
      <PageHeader
        title="Invoices"
        subtitle="Bill your book of business and track what's been paid — drafts, sends, payments, and overdue, all in one place."
        action={<button className="btn" onClick={() => setOpen((v) => !v)}>{open ? "Close" : "+ New invoice"}</button>}
      />

      {sum && (
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stat("Outstanding", money(sum.outstanding))}
          {stat("Overdue", money(sum.overdue), sum.overdue > 0 ? "text-red-600" : "")}
          {stat("Paid this month", money(sum.paid_this_month), "text-emerald-600")}
          {stat("Invoices", String(sum.total_invoices))}
        </div>
      )}

      {open && (
        <div className="card mb-4 space-y-3">
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder="Client name *" value={form.client_name}
                   onChange={(e) => setForm({ ...form, client_name: e.target.value })} />
            <input className="input" placeholder="Client email" value={form.client_email}
                   onChange={(e) => setForm({ ...form, client_email: e.target.value })} />
            <select className="input" value={form.business}
                    onChange={(e) => setForm({ ...form, business: e.target.value })}>
              <option value="insurance">Insurance</option>
              <option value="bnbglobal">B&B Global</option>
              <option value="savorymind">SavoryMind</option>
              <option value="music">Music</option>
              <option value="personal">Personal</option>
            </select>
            <label className="flex items-center gap-2 text-sm text-gray-500">
              Due<input type="date" className="input flex-1" value={form.due_date}
                        onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
            </label>
          </div>

          <div className="space-y-2">
            {lines.map((l, i) => (
              <div key={i} className="grid grid-cols-12 gap-2">
                <input className="input col-span-6" placeholder="Description" value={l.description}
                       onChange={(e) => setLine(i, "description", e.target.value)} />
                <input className="input col-span-2" type="number" placeholder="Qty" value={l.quantity}
                       onChange={(e) => setLine(i, "quantity", e.target.value)} />
                <input className="input col-span-3" type="number" placeholder="Unit price" value={l.unit_price}
                       onChange={(e) => setLine(i, "unit_price", e.target.value)} />
                <button className="col-span-1 text-gray-400 hover:text-red-500"
                        onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}>✕</button>
              </div>
            ))}
            <button className="text-sm text-brand" onClick={() => setLines((ls) => [...ls, { description: "", quantity: 1, unit_price: 0 }])}>
              + Add line
            </button>
          </div>

          <textarea className="input w-full" rows={2} placeholder="Notes (optional)" value={form.notes}
                    onChange={(e) => setForm({ ...form, notes: e.target.value })} />

          <div className="flex items-center justify-between">
            <div className="text-lg font-semibold">Total: {money(draftTotal)}</div>
            <button className="btn" onClick={create} disabled={busy}>{busy ? "Creating…" : "Create invoice"}</button>
          </div>
        </div>
      )}

      <div className="mb-3 flex flex-wrap gap-2 text-sm">
        {["", "Draft", "Sent", "Paid", "Overdue"].map((s) => (
          <button key={s} onClick={() => setFilter(s)}
                  className={`rounded-full px-3 py-1 ${filter === s ? "bg-brand text-white" : "bg-gray-100 text-gray-600"}`}>
            {s || "All"}{sum && s && sum.counts[s] ? ` (${sum.counts[s]})` : ""}
          </button>
        ))}
      </div>

      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs uppercase text-gray-400">
              <th className="p-3">Invoice</th><th className="p-3">Client</th><th className="p-3">Due</th>
              <th className="p-3 text-right">Total</th><th className="p-3 text-right">Balance</th>
              <th className="p-3">Status</th><th className="p-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {list.length === 0 && (
              <tr><td colSpan={7} className="p-6 text-center text-gray-400">No invoices yet. Create your first one above.</td></tr>
            )}
            {list.map((inv) => (
              <tr key={inv.id} className="border-b last:border-0">
                <td className="p-3 font-mono text-xs">{inv.number}</td>
                <td className="p-3">{inv.client_name}<div className="text-xs text-gray-400">{inv.business}</div></td>
                <td className="p-3 text-xs text-gray-500">{inv.due_date || "—"}</td>
                <td className="p-3 text-right">{money(inv.total)}</td>
                <td className="p-3 text-right">{inv.balance > 0 ? money(inv.balance) : <span className="text-emerald-600">paid</span>}</td>
                <td className="p-3"><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[inv.status] || "bg-gray-100"}`}>{inv.status}</span></td>
                <td className="p-3 text-right">
                  <div className="flex justify-end gap-2 text-xs">
                    {inv.status === "Draft" && <button className="text-sky-600" onClick={() => setStatus(inv.id, "Sent")}>Send</button>}
                    {(inv.status === "Sent" || inv.status === "Overdue") && <button className="text-emerald-600" onClick={() => recordPayment(inv)}>Record payment</button>}
                    {inv.status !== "Void" && inv.status !== "Paid" && <button className="text-gray-400" onClick={() => setStatus(inv.id, "Void")}>Void</button>}
                    <button className="text-gray-300 hover:text-red-500" onClick={() => remove(inv.id)}>Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Invoices /></AuthGate>;
}
