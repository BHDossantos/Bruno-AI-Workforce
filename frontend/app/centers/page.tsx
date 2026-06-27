"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Obj = { key: string; name: string; current_value: number; target_value: number };
type Commander = {
  center: string; name: string; agents: string[];
  objectives: Obj[]; open_actions: number; pipeline_value: number;
};

const ICON: Record<string, string> = {
  wealth: "💰", business: "🏢", influence: "📣", personal: "💪", life_ops: "🗂️",
  foundation: "🎓",
};

function money(n: number) {
  return n >= 1000 ? `$${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}k` : `$${n}`;
}

function CommanderCard({ c, onChanged }: { c: Commander; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [order, setOrder] = useState("");
  const [amount, setAmount] = useState<string>(c.objectives[0]?.target_value?.toString() || "");
  const [objKey, setObjKey] = useState(c.objectives[0]?.key || "");

  async function run() {
    setBusy(true); setMsg(null);
    try {
      await api.post(`/commanders/${c.center}/run`, {});
      setMsg("✅ Ran the commander's agents. Numbers refreshed.");
      onChanged();
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(false); }
  }

  async function giveOrder() {
    if (!order.trim()) { setMsg("Write an order first."); return; }
    setBusy(true); setMsg(null);
    try {
      const amt = amount ? Number(amount) : null;
      const r = await api.post<{ plan?: string }>(`/commanders/${c.center}/order`, {
        order, amount: amt, objective_key: objKey || null, run_now: true,
      });
      setMsg(r.plan ? `✅ Plan: ${r.plan}` : "✅ Order received — the commander is acting on it now.");
      setOrder("");
      onChanged();
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(false); }
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">{ICON[c.center]} {c.name}</h2>
        <span className="text-sm text-gray-500">{c.open_actions} open · {money(c.pipeline_value)} pipeline</span>
      </div>
      <div className="mt-1 text-xs text-gray-400">
        Agents: {c.agents.length ? c.agents.join(", ") : "—"}
      </div>

      <div className="mt-3 space-y-3">
        {c.objectives.map((o) => {
          const pct = o.target_value ? Math.min(100, (o.current_value / o.target_value) * 100) : 0;
          return (
            <div key={o.key}>
              <div className="flex justify-between text-xs">
                <span className="text-gray-700">{o.name}</span>
                <span className="text-gray-400">{money(Math.round(o.current_value))} / {money(o.target_value)}</span>
              </div>
              <div className="mt-1 h-2 overflow-hidden rounded bg-gray-100">
                <div className="h-full rounded bg-brand" style={{ width: `${Math.max(2, pct)}%` }} />
              </div>
            </div>
          );
        })}
        {c.objectives.length === 0 && <p className="text-xs text-gray-400">No objectives yet.</p>}
      </div>

      {/* Give this commander an order + pick the amount */}
      <div className="mt-4 rounded-lg border border-gray-200 p-3">
        <div className="text-xs font-semibold text-gray-600">Give an order</div>
        <textarea value={order} onChange={(e) => setOrder(e.target.value)} rows={2}
          placeholder={`e.g. "Source 50 new ${c.center} leads and start outreach today"`}
          className="mt-2 w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm" />
        {c.objectives.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            <span className="text-gray-500">Target</span>
            <select value={objKey} onChange={(e) => setObjKey(e.target.value)}
              className="rounded border border-gray-300 px-1 py-1">
              {c.objectives.map((o) => <option key={o.key} value={o.key}>{o.name}</option>)}
            </select>
            <span className="text-gray-400">$</span>
            <input type="number" step="10000" value={amount} onChange={(e) => setAmount(e.target.value)}
              className="w-28 rounded border border-gray-300 px-2 py-1" />
          </div>
        )}
        <div className="mt-2 flex gap-2">
          <button onClick={giveOrder} disabled={busy} className="btn flex-1 disabled:opacity-40">
            {busy ? "Working…" : "Give order"}
          </button>
          <button onClick={run} disabled={busy}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm disabled:opacity-40">
            Run now
          </button>
        </div>
        {msg && <p className="mt-2 text-xs text-gray-600">{msg}</p>}
      </div>
    </div>
  );
}

function Centers() {
  const [tick, setTick] = useState(0);
  const { data } = useFetch<Commander[]>(() => api.get<Commander[]>("/commanders"), [tick]);
  return (
    <div>
      <PageHeader title="Command Centers"
        subtitle="Your AI commanders — give each an order and a target, or let them run on the daily cycle. CEO → Commander → Agent." />
      <div className="grid gap-4 md:grid-cols-2">
        {(data || []).map((c) => (
          <CommanderCard key={c.center} c={c} onChanged={() => setTick((t) => t + 1)} />
        ))}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Centers /></AuthGate>;
}
