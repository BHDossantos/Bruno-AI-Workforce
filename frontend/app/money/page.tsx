"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

type Account = { id: string; name: string; kind: string; category: string | null; balance: number; institution: string | null };
type Summary = {
  net_worth: number; liquid: number; monthly_income: number; monthly_expenses: number;
  monthly_cashflow: number; runway_months: number | null;
  accounts: Account[]; top_categories: { category: string; spent: number }[];
};

const money = (n: number) => `$${Math.round(n).toLocaleString()}`;

function Money() {
  const [s, setS] = useState<Summary | null>(null);
  const [form, setForm] = useState({ name: "", kind: "asset", category: "checking", balance: "" });
  const [tx, setTx] = useState({ amount: "", category: "", description: "" });
  const [plaid, setPlaid] = useState<{ configured: boolean; linked: boolean } | null>(null);

  async function load() {
    setS(await api.get<Summary>("/finance/summary"));
    setPlaid(await api.get<{ configured: boolean; linked: boolean }>("/finance/plaid/status").catch(() => null));
  }
  useEffect(() => { load().catch(() => {}); }, []);

  async function connectBank() {
    const { link_token } = await api.post<{ link_token?: string }>("/finance/plaid/link-token", {});
    if (!link_token) { alert("Plaid isn't configured yet (set PLAID_CLIENT_ID / PLAID_SECRET)."); return; }
    // Load the Plaid Link SDK on demand.
    await new Promise<void>((resolve) => {
      if ((window as unknown as { Plaid?: unknown }).Plaid) return resolve();
      const sc = document.createElement("script");
      sc.src = "https://cdn.plaid.com/link/v2/stable/link-initialize.js";
      sc.onload = () => resolve();
      document.body.appendChild(sc);
    });
    const Plaid = (window as unknown as { Plaid: { create: (o: unknown) => { open: () => void } } }).Plaid;
    Plaid.create({
      token: link_token,
      onSuccess: async (public_token: string) => { await api.post("/finance/plaid/exchange", { public_token }); await load(); },
    }).open();
  }

  async function addAccount() {
    if (!form.name || !form.balance) return;
    await api.post("/finance/accounts", { ...form, balance: parseFloat(form.balance) });
    setForm({ name: "", kind: "asset", category: "checking", balance: "" });
    await load();
  }
  async function delAccount(id: string) { await api.del(`/finance/accounts/${id}`); await load(); }
  async function addTx() {
    if (!tx.amount) return;
    await api.post("/finance/transactions", { ...tx, amount: parseFloat(tx.amount) });
    setTx({ amount: "", category: "", description: "" });
    await load();
  }

  const stat = (label: string, val: string, tone = "") => (
    <div className="card"><div className={`text-2xl font-bold ${tone}`}>{val}</div><div className="text-xs uppercase text-gray-400">{label}</div></div>
  );

  return (
    <div>
      <PageHeader title="Money / Net Worth" subtitle="Accounts, cash flow, and net worth — feeds the Wealth Commander." />
      {plaid && (
        <div className="mb-4">
          {plaid.linked
            ? <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-700">🏦 Bank linked — balances sync daily</span>
            : <button onClick={connectBank} className="btn">🏦 Connect bank (Plaid)</button>}
          {!plaid.configured && !plaid.linked && <span className="ml-2 text-xs text-gray-400">set PLAID_CLIENT_ID / PLAID_SECRET to enable</span>}
        </div>
      )}
      {s && (
        <>
          <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
            {stat("Net worth", money(s.net_worth))}
            {stat("Monthly income", money(s.monthly_income), "text-green-600")}
            {stat("Monthly expenses", money(s.monthly_expenses), "text-red-500")}
            {stat("Cash flow", money(s.monthly_cashflow), s.monthly_cashflow >= 0 ? "text-green-600" : "text-red-500")}
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <div>
              <h2 className="mb-2 text-sm font-semibold text-gray-700">Accounts</h2>
              <div className="space-y-2">
                {s.accounts.map((a) => (
                  <div key={a.id} className="card flex items-center justify-between">
                    <div><div className="font-medium">{a.name}</div><div className="text-xs text-gray-400">{a.kind} · {a.category}</div></div>
                    <div className="flex items-center gap-3">
                      <span className={a.kind === "liability" ? "text-red-500" : ""}>{money(a.balance)}</span>
                      <button onClick={() => delAccount(a.id)} className="text-xs text-gray-400 hover:text-red-500">✕</button>
                    </div>
                  </div>
                ))}
              </div>
              <div className="card mt-3 grid grid-cols-2 gap-2">
                <input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded border border-gray-300 px-2 py-1 text-sm" />
                <input placeholder="Balance" type="number" value={form.balance} onChange={(e) => setForm({ ...form, balance: e.target.value })} className="rounded border border-gray-300 px-2 py-1 text-sm" />
                <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} className="rounded border border-gray-300 px-2 py-1 text-sm">
                  <option value="asset">Asset</option><option value="liability">Liability</option>
                </select>
                <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="rounded border border-gray-300 px-2 py-1 text-sm">
                  {["checking", "savings", "investment", "cash", "credit", "loan", "property"].map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
                <button onClick={addAccount} className="btn col-span-2">Add account</button>
              </div>
            </div>

            <div>
              <h2 className="mb-2 text-sm font-semibold text-gray-700">Add income / expense</h2>
              <div className="card grid grid-cols-2 gap-2">
                <input placeholder="Amount (+income / −expense)" type="number" value={tx.amount} onChange={(e) => setTx({ ...tx, amount: e.target.value })} className="col-span-2 rounded border border-gray-300 px-2 py-1 text-sm" />
                <input placeholder="Category" value={tx.category} onChange={(e) => setTx({ ...tx, category: e.target.value })} className="rounded border border-gray-300 px-2 py-1 text-sm" />
                <input placeholder="Description" value={tx.description} onChange={(e) => setTx({ ...tx, description: e.target.value })} className="rounded border border-gray-300 px-2 py-1 text-sm" />
                <button onClick={addTx} className="btn col-span-2">Add transaction</button>
              </div>
              {s.top_categories.length > 0 && (
                <div className="card mt-3">
                  <h3 className="mb-2 text-xs font-semibold text-gray-500">Top spend this month</h3>
                  {s.top_categories.map((c) => (
                    <div key={c.category} className="flex justify-between text-sm"><span>{c.category}</span><span className="text-gray-500">{money(c.spent)}</span></div>
                  ))}
                </div>
              )}
              <p className="mt-2 text-xs text-gray-400">Runway: {s.runway_months != null ? `${s.runway_months} months` : "—"}. Bank-feed (Plaid) import can be added later.</p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><Money /></AuthGate>;
}
