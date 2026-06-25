"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, Expandable, PageHeader, StatusBadge } from "@/components/ui";

type Item = {
  id: string; topic: string; business: string | null; channel: string;
  title: string | null; body: string | null; hashtags: string | null;
  status: string; scheduled_for: string | null;
};

const BUSINESSES = ["executive", "bnbglobal", "savorymind", "music", "insurance", "personal"];

function Factory() {
  const [items, setItems] = useState<Item[]>([]);
  const [topic, setTopic] = useState("");
  const [business, setBusiness] = useState("executive");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function load() { setItems(await api.get<Item[]>("/content?limit=120")); }
  useEffect(() => { load().catch(() => {}); }, []);

  async function run() {
    if (!topic.trim()) return;
    setBusy(true); setMsg("");
    try {
      const r = await api.post<{ ok: boolean; channels?: string[]; reason?: string; fresh_angle?: boolean }>(
        "/content/factory", { topic, business });
      setMsg(r.ok ? `✅ Created ${r.channels?.length || 0} pieces${r.fresh_angle ? " (fresh angle — topic seen before)" : ""}.` : `❌ ${r.reason}`);
      setTopic(""); await load();
    } catch (e) { setMsg(String(e)); } finally { setBusy(false); }
  }

  async function act(id: string, path: string) {
    await api.post(`/content/${id}/${path}`, {}); await load();
  }

  return (
    <div>
      <PageHeader title="Content Factory"
        subtitle="One idea → channel-ready content for every platform. Dedup-checked against what you've already posted; auto-scheduled to connected accounts." />

      <div className="card mb-6 flex flex-wrap items-end gap-2">
        <input value={topic} onChange={(e) => setTopic(e.target.value)} onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder="A topic or idea (e.g. cutting cloud spend without downtime)"
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        <select value={business} onChange={(e) => setBusiness(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
          {BUSINESSES.map((b) => <option key={b} value={b}>{b}</option>)}
        </select>
        <button className="btn" onClick={run} disabled={busy}>{busy ? "Producing…" : "Produce"}</button>
      </div>
      {msg && <p className="mb-3 text-sm text-gray-600">{msg}</p>}

      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs text-gray-500">
            <tr><th className="p-3">Topic</th><th className="p-3">Channel</th><th className="p-3">Business</th>
              <th className="p-3">Content</th><th className="p-3">Status</th><th className="p-3"></th></tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id} className="border-t">
                <td className="p-3">{i.topic}</td>
                <td className="p-3"><span className="rounded bg-gray-100 px-2 py-0.5 text-xs">{i.channel}</span></td>
                <td className="p-3 text-gray-500">{i.business}</td>
                <td className="p-3"><Expandable label={i.title || "view"} text={[i.body, i.hashtags].filter(Boolean).join("\n\n")} /></td>
                <td className="p-3"><StatusBadge status={i.status} /></td>
                <td className="p-3 text-right">
                  {(i.status === "needs_approval" || i.status === "ready") &&
                    <button onClick={() => act(i.id, "approve")} className="rounded border border-gray-300 px-2 py-1 text-xs">Approve</button>}
                  {i.status !== "dismissed" && i.status !== "published" &&
                    <button onClick={() => act(i.id, "dismiss")} className="ml-1 rounded border border-gray-300 px-2 py-1 text-xs text-gray-500">✕</button>}
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={6} className="p-6 text-center text-gray-400">No content yet — produce some above, or let the Influence Commander run daily.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Factory /></AuthGate>;
}
