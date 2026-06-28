"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Funnel = {
  funnel: string; label: string; subscribers: number; total: number;
  unsubscribed: number; last_sent: string | null; last_subject: string | null;
};
type Send = { funnel: string; subject: string | null; sent_count: number; created_at: string | null };
type Overview = { funnels: Funnel[]; history: Send[] };

const ICON: Record<string, string> = { insurance: "🛡️", bnbglobal: "💻", savorymind: "🍽️", music: "🎵" };

type Preview = { funnel: string; label: string; subject: string; body: string; subscribers: number };

function Newsletters() {
  const [tick, setTick] = useState(0);
  const { data } = useFetch<Overview>(() => api.get<Overview>("/newsletters"), [tick]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);

  async function send(funnel: string) {
    if (!confirm(`Send the ${funnel} newsletter to its warm subscribers now?`)) return;
    setBusy(funnel); setMsg("");
    try {
      const r = await api.post<{ sent: number; subscribers: number }>(`/newsletters/${funnel}/send`, {});
      setMsg(`✅ ${funnel}: sent ${r.sent}/${r.subscribers}.`);
      setTick((t) => t + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  async function showPreview(funnel: string) {
    setBusy(funnel); setMsg("");
    try {
      setPreview(await api.get<Preview>(`/newsletters/${funnel}/preview`));
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  return (
    <div className="space-y-8">
      <PageHeader title="Newsletters"
        subtitle="One newsletter per funnel, sent 3×/week to people who replied (warm). Unsubscribe + send cap built in." />
      {msg && <p className="text-sm text-gray-600">{msg}</p>}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {(data?.funnels || []).map((f) => (
          <div key={f.funnel} className="card">
            <div className="flex items-center justify-between">
              <span className="font-semibold">{ICON[f.funnel] || "📰"} {f.label}</span>
            </div>
            <div className="mt-2 text-3xl font-bold text-brand">{f.subscribers}</div>
            <div className="text-xs text-gray-400">active subscribers · {f.unsubscribed} opted out</div>
            <div className="mt-1 text-xs text-gray-400">
              {f.last_sent ? `Last sent ${f.last_sent.slice(0, 10)}` : "Not sent yet"}
            </div>
            <div className="mt-3 flex gap-2">
              <button onClick={() => showPreview(f.funnel)} disabled={busy === f.funnel}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm disabled:opacity-40">
                {busy === f.funnel ? "…" : "Preview"}
              </button>
              <button onClick={() => send(f.funnel)} disabled={busy === f.funnel || f.subscribers === 0}
                className="btn flex-1 disabled:opacity-40">
                {busy === f.funnel ? "Sending…" : "Send now"}
              </button>
            </div>
          </div>
        ))}
      </div>

      {preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setPreview(null)}>
          <div className="max-h-[85vh] w-full max-w-xl overflow-y-auto rounded-xl bg-white p-6" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-semibold">{ICON[preview.funnel] || "📰"} {preview.label} — draft</h3>
              <button onClick={() => setPreview(null)} className="text-gray-400 hover:text-gray-700">✕</button>
            </div>
            <div className="text-xs text-gray-400">Subject</div>
            <div className="mb-3 font-medium">{preview.subject}</div>
            <div className="text-xs text-gray-400">Body</div>
            <pre className="mt-1 whitespace-pre-wrap rounded bg-gray-50 p-3 text-sm text-gray-700">{preview.body}</pre>
            <p className="mt-3 text-xs text-gray-400">
              {preview.subscribers} subscriber(s). This is a draft — “Send now” delivers it to everyone on this funnel’s list (each issue has an unsubscribe link).
            </p>
          </div>
        </div>
      )}

      <div>
        <h2 className="mb-3 font-semibold">Send history</h2>
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs text-gray-500">
              <tr><th className="p-3">Funnel</th><th className="p-3">Subject</th><th className="p-3">Recipients</th><th className="p-3">Date</th></tr>
            </thead>
            <tbody>
              {(data?.history || []).map((s, i) => (
                <tr key={i} className="border-t">
                  <td className="p-3">{ICON[s.funnel] || "📰"} {s.funnel}</td>
                  <td className="p-3">{s.subject || "—"}</td>
                  <td className="p-3">{s.sent_count}</td>
                  <td className="p-3 text-gray-500">{s.created_at?.slice(0, 10)}</td>
                </tr>
              ))}
              {data && data.history.length === 0 && (
                <tr><td colSpan={4} className="p-6 text-center text-gray-400">No newsletters sent yet — everyone you email gets added automatically.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Newsletters /></AuthGate>;
}
