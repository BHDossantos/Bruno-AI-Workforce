"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

type Field = { key: string; label: string; secret: boolean; required: boolean; placeholder?: string; help?: string };
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
  social: "Social media", content: "Content & blogs", email: "Email", crm: "CRM",
  ads: "Advertising", commerce: "Stores & payments", messaging: "Messaging",
  scheduling: "Scheduling",
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
  useEffect(() => {
    reload().catch((e) => setMsg(`❌ ${e}`));
    const params = new URLSearchParams(window.location.search);
    const tk = params.get("tiktok");
    if (tk === "connected") setMsg("✅ TikTok connected via official login. Click Test to verify.");
    else if (tk === "error") setMsg("❌ TikTok connection failed — try again or paste a token manually.");
    const meta = params.get("meta");
    if (meta === "connected") setMsg("✅ Facebook & Instagram connected via official login. Click Test to verify.");
    else if (meta === "error") setMsg("❌ Facebook/Instagram connection failed — try again or paste a token manually.");
  }, []);

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

  async function tiktokOauth() {
    try {
      const { url } = await api.get<{ url: string }>("/connections/tiktok/oauth/start");
      window.location.href = url;
    } catch (e) {
      setMsg(`❌ TikTok OAuth isn't configured yet (${e}). Set TIKTOK_CLIENT_KEY / SECRET / REDIRECT_URI, or paste a token below.`);
    }
  }

  async function metaOauth() {
    try {
      const { url } = await api.get<{ url: string }>("/connections/meta/oauth/start");
      window.location.href = url;
    } catch (e) {
      setMsg(`❌ Facebook/Instagram OAuth isn't configured yet (${e}). Set FACEBOOK_APP_ID / FACEBOOK_APP_SECRET / META_REDIRECT_URI, or paste a token below.`);
    }
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

  async function test(id: string) {
    setMsg("Testing connection…");
    try {
      const r = await api.post<{ ok: boolean | null; detail: string }>(`/connections/${id}/test`, {});
      setMsg(r.ok === true ? `✅ Live: ${r.detail}`
        : r.ok === false ? `❌ Not working: ${r.detail}`
        : `ℹ️ ${r.detail}`);
      await reload();
    } catch (e) {
      setMsg(`❌ ${e}`);
    }
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

      <TokenHealth />

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
                  <div className="mt-2 flex gap-3">
                    <button onClick={() => test(c.id)}
                            className="text-xs text-brand hover:underline">Test</button>
                    <button onClick={() => disconnect(c.id)}
                            className="text-xs text-red-600 hover:underline">Disconnect</button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* New Connection Setup — self-service, user-named connections */}
      <NewConnectionSetup />

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

            {selected.key === "tiktok" && (
              <div className="mb-4 rounded-lg border border-gray-200 p-3">
                <button onClick={tiktokOauth} className="btn w-full">
                  Connect with TikTok (recommended)
                </button>
                <p className="mt-2 text-xs text-gray-500">
                  Authorizes via TikTok&apos;s official login. Or paste a token manually below.
                </p>
              </div>
            )}

            {(selected.key === "facebook" || selected.key === "instagram") && (
              <div className="mb-4 rounded-lg border border-gray-200 p-3">
                <button onClick={metaOauth} className="btn w-full">
                  Connect with Facebook/Instagram (recommended)
                </button>
                <p className="mt-2 text-xs text-gray-500">
                  One click via Facebook&apos;s official login — connects your Page and its linked
                  Instagram together, with a long-lived token that auto-refreshes (no more
                  surprise disconnects). Or paste a token manually below.
                </p>
              </div>
            )}

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
                  {f.help && <p className="mt-0.5 text-xs text-gray-500">Where to get it: {f.help}</p>}
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

type Health = { provider: string; label: string; connected: boolean; days_left: number | null; note: string; warn: boolean };

function TokenHealth() {
  const [rows, setRows] = useState<Health[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function load() {
    try { setRows(await api.get<Health[]>("/connections/health")); } catch { /* */ }
  }
  useEffect(() => { load(); }, []);

  async function refresh() {
    setBusy(true); setMsg("");
    try {
      await api.post("/connections/refresh", {});
      setMsg("✅ Refreshed — tokens extended.");
      await load();
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(false); }
  }

  if (!rows || rows.length === 0) return null;
  return (
    <div className="card mb-6">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">🔌 Connection health</h2>
        <button onClick={refresh} disabled={busy}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm disabled:opacity-50">
          {busy ? "Refreshing…" : "Refresh tokens now"}
        </button>
      </div>
      {msg && <p className="mb-2 text-sm text-gray-600">{msg}</p>}
      <div className="space-y-2">
        {rows.map((r) => (
          <div key={r.provider} className="flex items-center justify-between rounded-lg border border-gray-100 px-3 py-2">
            <span className="text-sm font-medium">{r.label}</span>
            <span className="flex items-center gap-3 text-xs">
              {r.days_left != null && (
                <span className={r.days_left <= 7 ? "text-amber-600" : "text-gray-400"}>
                  {r.days_left}d left
                </span>
              )}
              <span className="text-gray-500">{r.note}</span>
              <span className={`badge ${r.connected && !r.warn ? "bg-green-100 text-green-700"
                : r.connected ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"}`}>
                {r.connected ? (r.warn ? "Expiring soon" : "Healthy") : "Reconnect"}
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── New Connection Setup ─────────────────────────────────────────────────────
type CCField = { label: string; secret: boolean; value: string; has_value: boolean };
type CustomConn = { id: string; category: string; name: string; notes: string | null; status: string; fields: CCField[] };
type CCCategory = { key: string; label: string };
type EditState = { id: string | null; category: string; name: string; notes: string; fields: CCField[] };

function NewConnectionSetup() {
  const [cats, setCats] = useState<CCCategory[]>([]);
  const [conns, setConns] = useState<CustomConn[]>([]);
  const [edit, setEdit] = useState<EditState | null>(null);
  const [busy, setBusy] = useState(false);

  async function reload() {
    try {
      const r = await api.get<{ categories: CCCategory[]; connections: CustomConn[] }>("/custom-connections");
      setCats(r.categories || []);
      setConns(r.connections || []);
    } catch { /* keep last */ }
  }
  useEffect(() => { reload(); }, []);

  function openNew(category: string) {
    setEdit({ id: null, category, name: "", notes: "",
      fields: [{ label: "API Key", secret: true, value: "", has_value: false }] });
  }
  function openEdit(c: CustomConn) {
    setEdit({ id: c.id, category: c.category, name: c.name, notes: c.notes || "",
      fields: c.fields.map((f) => ({ ...f, value: f.secret ? "" : f.value })) });
  }

  async function save() {
    if (!edit) return;
    setBusy(true);
    try {
      const body = { category: edit.category, name: edit.name, notes: edit.notes,
        fields: edit.fields.filter((f) => f.label.trim()).map((f) => ({ label: f.label, value: f.value, secret: f.secret })) };
      if (edit.id) await api.put(`/custom-connections/${edit.id}`, body);
      else await api.post("/custom-connections", body);
      setEdit(null);
      await reload();
    } finally { setBusy(false); }
  }
  async function remove(id: string) {
    if (!confirm("Delete this connection?")) return;
    await api.del(`/custom-connections/${id}`);
    setEdit(null);
    await reload();
  }

  const byCat: Record<string, CustomConn[]> = {};
  conns.forEach((c) => { (byCat[c.category] ||= []).push(c); });

  return (
    <div className="card mb-6 border-brand/30">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">🧩 New Connection Setup</h2>
      </div>
      <p className="mb-4 text-xs text-gray-500">
        Add any app yourself — pick a category, <b>name it</b>, and add whatever fields it needs
        (mark a field 🔒 to encrypt it). Rename or edit anytime. Your existing connections above are
        untouched; we&apos;ll migrate them here over time.
      </p>

      <div className="space-y-5">
        {cats.map((cat) => (
          <div key={cat.key}>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">{cat.label}</h3>
              <button onClick={() => openNew(cat.key)} className="text-xs text-brand hover:underline">+ Add connection</button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {(byCat[cat.key] || []).map((c) => (
                <button key={c.id} onClick={() => openEdit(c)}
                        className="rounded-lg border border-gray-200 p-3 text-left hover:ring-2 hover:ring-brand/40">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{c.name}</span>
                    <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">{c.status}</span>
                  </div>
                  <p className="mt-1 truncate text-xs text-gray-500">
                    {c.fields.length} field{c.fields.length === 1 ? "" : "s"}
                    {c.fields.some((f) => f.secret) ? " · 🔒 secured" : ""}
                  </p>
                </button>
              ))}
              {!(byCat[cat.key] || []).length && (
                <button onClick={() => openNew(cat.key)}
                        className="rounded-lg border border-dashed border-gray-300 p-3 text-left text-xs text-gray-400 hover:border-brand hover:text-brand">
                  + Add your first {cat.label} app
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {edit && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setEdit(null)}>
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold">{edit.id ? "Edit connection" : "New connection"}</h3>
              <button onClick={() => setEdit(null)} className="text-gray-400 hover:text-gray-700">✕</button>
            </div>
            <div className="grid gap-3">
              <label className="text-xs font-medium text-gray-600">App name
                <input className="input mt-1" placeholder="e.g. Facebook, Klaviyo, Cal.com"
                       value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />
              </label>
              <label className="text-xs font-medium text-gray-600">Category
                <select className="input mt-1" value={edit.category} onChange={(e) => setEdit({ ...edit, category: e.target.value })}>
                  {cats.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                </select>
              </label>

              <div className="text-xs font-medium text-gray-600">Fields</div>
              {edit.fields.map((f, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input className="input flex-1" placeholder="Label (e.g. API Key)" value={f.label}
                         onChange={(e) => { const fs = [...edit.fields]; fs[i] = { ...f, label: e.target.value }; setEdit({ ...edit, fields: fs }); }} />
                  <input className="input flex-1" type={f.secret ? "password" : "text"}
                         placeholder={f.secret && f.has_value ? "•••• (leave blank to keep)" : "Value"} value={f.value}
                         onChange={(e) => { const fs = [...edit.fields]; fs[i] = { ...f, value: e.target.value }; setEdit({ ...edit, fields: fs }); }} />
                  <label className="flex shrink-0 items-center gap-1 text-xs text-gray-500" title="Encrypt this value">
                    <input type="checkbox" checked={f.secret}
                           onChange={(e) => { const fs = [...edit.fields]; fs[i] = { ...f, secret: e.target.checked }; setEdit({ ...edit, fields: fs }); }} />🔒
                  </label>
                  <button onClick={() => setEdit({ ...edit, fields: edit.fields.filter((_, j) => j !== i) })}
                          className="shrink-0 text-gray-400 hover:text-red-600">✕</button>
                </div>
              ))}
              <button onClick={() => setEdit({ ...edit, fields: [...edit.fields, { label: "", secret: false, value: "", has_value: false }] })}
                      className="text-left text-xs text-brand hover:underline">+ Add field</button>

              <label className="text-xs font-medium text-gray-600">Notes (optional)
                <textarea className="input mt-1" rows={2} value={edit.notes}
                          onChange={(e) => setEdit({ ...edit, notes: e.target.value })} />
              </label>

              <div className="mt-2 flex items-center justify-between">
                <div>{edit.id && <button onClick={() => remove(edit.id!)} className="text-sm text-red-600 hover:underline">Delete</button>}</div>
                <div className="flex gap-2">
                  <button onClick={() => setEdit(null)} className="btn-ghost">Cancel</button>
                  <button onClick={save} disabled={busy || !edit.name.trim()} className="btn">{busy ? "Saving…" : "Save"}</button>
                </div>
              </div>
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
