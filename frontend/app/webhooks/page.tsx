"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type EventDef = { key: string; label: string };
type WebhookRow = {
  id: string; name: string; url: string; has_secret: boolean; events: string[];
  enabled: boolean; last_triggered_at: string | null; last_status: string | null;
};
type Form = { name: string; url: string; secret: string; events: string[]; enabled: boolean };

const EMPTY: Form = { name: "", url: "", secret: "", events: [], enabled: true };

function Webhooks() {
  const { data: events } = useFetch<EventDef[]>(() => api.get<EventDef[]>("/webhooks/events"));
  const [refresh, setRefresh] = useState(0);
  const { data, loading, error, reload } = useFetch<WebhookRow[]>(() => api.get<WebhookRow[]>("/webhooks"), [refresh]);
  const [form, setForm] = useState<Form | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  function toggleEvent(key: string) {
    if (!form) return;
    setForm({ ...form, events: form.events.includes(key) ? form.events.filter((e) => e !== key) : [...form.events, key] });
  }

  async function save() {
    if (!form) return;
    setBusy("save");
    try {
      await api.post("/webhooks", { name: form.name, url: form.url, secret: form.secret || undefined, events: form.events, enabled: form.enabled });
      setForm(null); setRefresh((n) => n + 1); setMsg("✅ Webhook added.");
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  async function toggle(w: WebhookRow) {
    setBusy(w.id);
    try {
      await api.patch(`/webhooks/${w.id}`, { name: w.name, url: w.url, events: w.events, enabled: !w.enabled });
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  async function test(id: string) {
    setBusy(id);
    try {
      const r = await api.post<{ ok: boolean; status: string }>(`/webhooks/${id}/test`, {});
      setMsg(r.ok ? `✅ Test delivered (${r.status})` : `❌ Test failed (${r.status})`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  async function remove(id: string) {
    if (!confirm("Delete this webhook?")) return;
    setBusy(id);
    try { await api.del(`/webhooks/${id}`); setRefresh((n) => n + 1); }
    catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  const eventLabel = (k: string) => (k === "*" ? "All events" : events?.find((e) => e.key === k)?.label || k);

  return (
    <div>
      <PageHeader title="Webhooks"
        subtitle="Notify n8n, Make, Zapier, or any URL when things happen in Bruno — build custom automations outside the app."
        action={<button className="btn" onClick={() => setForm({ ...EMPTY })}>+ Add webhook</button>} />
      {msg && <p className="mb-3 text-sm text-gray-600">{msg}</p>}
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}

      {form && (
        <div className="card mb-6">
          <h2 className="mb-3 font-semibold">New webhook</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <input className="input" placeholder="Name (e.g. n8n — new clients)"
              value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input className="input" placeholder="https://your-n8n-instance/webhook/..."
              value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
            <input className="input sm:col-span-2" type="password" placeholder="Secret (optional — signs payloads with HMAC-SHA256)"
              value={form.secret} onChange={(e) => setForm({ ...form, secret: e.target.value })} />
          </div>
          <div className="mt-3">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">Events</div>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => toggleEvent("*")}
                className={`rounded-full px-3 py-1 text-sm ${form.events.includes("*") ? "bg-brand text-white" : "bg-gray-100 text-gray-600"}`}>
                All events
              </button>
              {(events || []).map((e) => (
                <button key={e.key} onClick={() => toggleEvent(e.key)} disabled={form.events.includes("*")}
                  className={`rounded-full px-3 py-1 text-sm disabled:opacity-40 ${form.events.includes(e.key) ? "bg-brand text-white" : "bg-gray-100 text-gray-600"}`}
                  title={e.label}>
                  {e.key}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <button className="btn-ghost" onClick={() => setForm(null)}>Cancel</button>
            <button className="btn" onClick={save} disabled={busy === "save" || !form.name.trim() || !form.url.trim() || form.events.length === 0}>Save</button>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {(data || []).map((w) => (
          <div key={w.id} className="card">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold">{w.name}</span>
                  {w.enabled
                    ? <span className="badge bg-green-100 text-green-700">enabled</span>
                    : <span className="badge bg-gray-100 text-gray-500">disabled</span>}
                  {w.has_secret && <span className="badge bg-violet-100 text-violet-700">signed</span>}
                </div>
                <div className="mt-0.5 break-all text-xs text-gray-500">{w.url}</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {w.events.map((e) => <span key={e} className="badge bg-gray-100 text-gray-600">{eventLabel(e)}</span>)}
                </div>
                {w.last_triggered_at && (
                  <div className="mt-1 text-xs text-gray-400">
                    Last fired {new Date(w.last_triggered_at).toLocaleString()} — {w.last_status}
                  </div>
                )}
              </div>
              <div className="flex gap-2">
                <button className="btn-ghost text-sm" onClick={() => test(w.id)} disabled={busy === w.id}>Test</button>
                <button className="btn-ghost text-sm" onClick={() => toggle(w)} disabled={busy === w.id}>{w.enabled ? "Disable" : "Enable"}</button>
                <button className="text-sm text-red-500" onClick={() => remove(w.id)} disabled={busy === w.id}>Delete</button>
              </div>
            </div>
          </div>
        ))}
        {!loading && (data || []).length === 0 && (
          <div className="card text-sm text-gray-500">
            No webhooks yet — add one to notify n8n, Make, Zapier or any URL when a client is added, a communication is logged, or a lead replies.
          </div>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Webhooks /></AuthGate>;
}
