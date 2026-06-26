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

function Newsletters() {
  const [tick, setTick] = useState(0);
  const { data } = useFetch<Overview>(() => api.get<Overview>("/newsletters"), [tick]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

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
            <button onClick={() => send(f.funnel)} disabled={busy === f.funnel || f.subscribers === 0}
              className="btn mt-3 w-full disabled:opacity-40">
              {busy === f.funnel ? "Sending…" : "Send now"}
            </button>
          </div>
        ))}
      </div>

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
                <tr><td colSpan={4} className="p-6 text-center text-gray-400">No newsletters sent yet — warm repliers get added automatically.</td></tr>
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
