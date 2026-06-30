"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Item = {
  sender: string; business: string; label: string; intent: string;
  summary: string | null; subject: string | null; account: string | null;
  received_at: string | null; draft_id: string | null; draft_body: string | null;
};
type Feed = { items: Item[]; by_business: Record<string, number>; by_label: Record<string, number>; total: number };

const LABEL_COLOR: Record<string, string> = {
  Interested: "bg-emerald-100 text-emerald-700", Question: "bg-blue-100 text-blue-700",
  Objection: "bg-amber-100 text-amber-700", "Not interested": "bg-gray-100 text-gray-500",
  Unsubscribe: "bg-red-100 text-red-700", Neutral: "bg-gray-100 text-gray-500",
};

function Inbox() {
  const [business, setBusiness] = useState("");
  const [label, setLabel] = useState("");
  const [tick, setTick] = useState(0);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const qs = new URLSearchParams();
  if (business) qs.set("business", business);
  if (label) qs.set("label", label);
  const { data } = useFetch<Feed>(() => api.get<Feed>(`/messages/inbox?${qs.toString()}`), [business, label, tick]);

  async function send(it: Item) {
    if (!it.draft_id) return;
    setBusy(it.sender); setMsg("");
    try {
      await api.post(`/messages/${it.draft_id}/send`);
      setMsg(`✅ Reply sent to ${it.sender}`); setTick((t) => t + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  return (
    <div>
      <PageHeader title="Unified Inbox"
        subtitle="Every prospect reply across all your businesses, in one place — AI-labeled and summarized, with a reply drafted for one-click send." />
      {msg && <p className="mb-3 rounded bg-brand/10 p-3 text-sm text-brand-dark">{msg}</p>}

      <div className="mb-4 flex flex-wrap gap-2">
        {["", "Insurance", "BnB Global", "SavoryMind", "Other"].map((b) => (
          <button key={b || "all"} onClick={() => setBusiness(b)}
            className={`rounded-full px-3 py-1 text-sm ${business === b ? "bg-brand text-white" : "bg-gray-100 text-gray-600"}`}>
            {b || "All"}{b && data?.by_business[b] ? ` (${data.by_business[b]})` : ""}
          </button>
        ))}
        <span className="mx-1 w-px bg-gray-200" />
        {["", "Interested", "Question", "Objection", "Not interested", "Unsubscribe"].map((l) => (
          <button key={l || "any"} onClick={() => setLabel(l)}
            className={`rounded-full px-3 py-1 text-sm ${label === l ? "bg-brand-dark text-white" : "bg-gray-100 text-gray-600"}`}>
            {l || "Any label"}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {data?.items.map((it) => (
          <div key={it.sender} className="card">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className={`badge ${LABEL_COLOR[it.label] || ""}`}>{it.label}</span>
                  <span className="text-sm font-medium">{it.sender}</span>
                  <span className="text-xs text-gray-400">· {it.business}</span>
                </div>
                {it.subject && <div className="mt-0.5 text-xs text-gray-500">Re: {it.subject}</div>}
                {it.summary && <div className="mt-1 text-sm text-gray-700">{it.summary}</div>}
              </div>
            </div>
            {it.draft_body && (
              <div className="mt-3 rounded-lg bg-gray-50 p-3">
                <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">Suggested reply</div>
                <div className="mt-1 whitespace-pre-wrap text-sm text-gray-700">{it.draft_body}</div>
                <button onClick={() => send(it)} disabled={busy === it.sender}
                  className="mt-2 rounded-lg bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50">
                  {busy === it.sender ? "Sending…" : "✓ Approve & send"}
                </button>
              </div>
            )}
          </div>
        ))}
        {data && data.items.length === 0 && (
          <div className="card text-sm text-gray-500">No replies yet — they appear here as prospects respond (run “Sync replies” on the Outbox).</div>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Inbox /></AuthGate>;
}
