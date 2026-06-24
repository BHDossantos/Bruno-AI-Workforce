"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

type Field = { key: string; label: string; secret: boolean; required: boolean; placeholder?: string };
type Provider = {
  key: string; name: string; category: string; icon: string; auth_type: string;
  fields: Field[]; capabilities: string[]; stages: string[]; compliance: string; goals: string[];
};
type Connection = {
  id: string; provider: string; display_name: string; account_ref?: string;
  status: string; funnel_enabled: boolean; goal?: string;
};
type Action = { title: string; mode: string; description: string; capability: string };
type Stage = { stage: string; label: string; actions: Action[] };
type Plan = {
  provider: string; provider_name: string; icon: string; goal: string;
  stages: Stage[]; auto_actions: number; assist_actions: number; summary: string;
};

const CATEGORY_LABEL: Record<string, string> = {
  social: "Social media", email: "Email", crm: "CRM", ads: "Advertising",
  commerce: "Stores & payments", messaging: "Messaging", scheduling: "Scheduling",
};

function Connections() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [conns, setConns] = useState<Connection[]>([]);
  const [selected, setSelected] = useState<Provider | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [goal, setGoal] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function reload() {
    const [p, c] = await Promise.all([
      api.get<Provider[]>("/connections/providers"),
      api.get<Connection[]>("/connections"),
    ]);
    setProviders(p);
    setConns(c);
  }
  useEffect(() => { reload().catch((e) => setMsg(`❌ ${e}`)); }, []);

  async function openProvider(p: Provider) {
    setSelected(p);
    setForm({});
    setDisplayName(p.name);
    setGoal(p.goals[0] || "leads");
    setMsg(null);
    try {
      setPlan(await api.get<Plan>(`/connections/funnel/preview/${p.key}`));
    } catch { setPlan(null); }
  }

  async function connect() {
    if (!selected) return;
    setBusy(true);
    setMsg(null);
    try {
      await api.post("/connections", {
        provider: selected.key,
        display_name: displayName,
        goal,
        credentials: form,
      });
      setSelected(null);
      setPlan(null);
      await reload();
      setMsg("✅ Connected. Its funnel is now active.");
    } catch (e) {
      setMsg(`❌ ${e}`);
    } finally {
      setBusy(false);
    }
  }

  async function disconnect(id: string) {
    if (!confirm("Disconnect this account?")) return;
    await api.del(`/connections/${id}`);
    await reload();
  }

  const byCat: Record<string, Provider[]> = {};
  providers.forEach((p) => { (byCat[p.category] ||= []).push(p); });

  return (
    <div>
      <PageHeader
        title="Connections"
        subtitle="Connect any app or social account — Bruno runs the full marketing & sales funnel for it automatically"
      />

      {msg && <p className="mb-4 rounded bg-gray-50 p-3 text-sm">{msg}</p>}

      {/* Connected accounts */}
      <div className="card mb-6">
        <h2 className="mb-3 text-sm font-semibold text-gray-700">Your connected accounts</h2>
        {conns.length === 0 ? (
          <p className="text-sm text-gray-500">Nothing connected yet. Pick an account below to start.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {conns.map((c) => {
              const p = providers.find((x) => x.key === c.provider);
              return (
                <div key={c.id} className="rounded-lg border border-gray-200 p-3">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{p?.icon} {c.display_name}</span>
                    <span className={`rounded-full px-2 py-0.5 text-xs ${
                      c.status === "connected" ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
                      {c.status}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-gray-500">Goal: {c.goal || "—"}{c.account_ref ? ` · ${c.account_ref}` : ""}</p>
                  <button onClick={() => disconnect(c.id)}
                          className="mt-2 text-xs text-red-600 hover:underline">Disconnect</button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Catalog */}
      {Object.entries(byCat).map(([cat, items]) => (
        <div key={cat} className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-gray-700">{CATEGORY_LABEL[cat] || cat}</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {items.map((p) => (
              <button key={p.key} onClick={() => openProvider(p)}
                      className="card flex items-center gap-3 text-left hover:ring-2 hover:ring-brand/40">
                <span className="text-2xl">{p.icon}</span>
                <div>
                  <div className="font-medium">{p.name}</div>
                  <div className="text-xs text-gray-500">{p.capabilities.length} capabilities</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      ))}

      {/* Connect modal */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
             onClick={() => setSelected(null)}>
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-6"
               onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold">{selected.icon} Connect {selected.name}</h3>
              <button onClick={() => setSelected(null)} className="text-gray-400 hover:text-gray-700">✕</button>
            </div>

            <p className="mb-4 rounded bg-blue-50 p-3 text-xs text-blue-800">{selected.compliance}</p>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className="text-sm font-medium text-gray-700">Account label</label>
                <input value={displayName} onChange={(e) => setDisplayName(e.target.value)}
                       className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2" />
              </div>
              <div className="sm:col-span-2">
                <label className="text-sm font-medium text-gray-700">Goal</label>
                <select value={goal} onChange={(e) => setGoal(e.target.value)}
                        className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2">
                  {selected.goals.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </div>
              {selected.fields.map((f) => (
                <div key={f.key} className="sm:col-span-2">
                  <label className="text-sm font-medium text-gray-700">
                    {f.label}{f.required && <span className="text-red-500"> *</span>}
                  </label>
                  <input
                    type={f.secret ? "password" : "text"}
                    placeholder={f.placeholder}
                    value={form[f.key] || ""}
                    onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                    className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 font-mono text-sm"
                  />
                </div>
              ))}
            </div>

            {/* Funnel preview */}
            {plan && plan.stages.length > 0 && (
              <div className="mt-5">
                <h4 className="text-sm font-semibold text-gray-700">
                  What Bruno will run for this account
                </h4>
                <p className="mb-2 text-xs text-gray-500">{plan.summary}</p>
                <div className="space-y-2">
                  {plan.stages.map((s) => (
                    <div key={s.stage} className="rounded-lg border border-gray-200 p-3">
                      <div className="text-xs font-semibold uppercase tracking-wide text-brand">{s.label}</div>
                      <ul className="mt-1 space-y-1">
                        {s.actions.map((a, i) => (
                          <li key={i} className="text-sm">
                            <span className={`mr-2 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                              a.mode === "auto" ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
                              {a.mode === "auto" ? "AUTO" : "1-CLICK"}
                            </span>
                            <b>{a.title}</b> — <span className="text-gray-600">{a.description}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setSelected(null)}
                      className="rounded-lg border border-gray-300 px-4 py-2 text-sm">Cancel</button>
              <button onClick={connect} disabled={busy} className="btn">
                {busy ? "Connecting…" : "Connect & activate funnel"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><Connections /></AuthGate>;
}
