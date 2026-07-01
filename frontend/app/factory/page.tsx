"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, Expandable, PageHeader, StatusBadge } from "@/components/ui";

type Item = {
  id: string; topic: string; business: string | null; channel: string;
  title: string | null; body: string | null; hashtags: string | null;
  status: string; scheduled_for: string | null;
  video_url: string | null; video_status: string | null;
};

const BUSINESSES = ["executive", "bnbglobal", "savorymind", "music", "insurance", "personal"];

function Factory() {
  const [items, setItems] = useState<Item[]>([]);
  const [topic, setTopic] = useState("");
  const [business, setBusiness] = useState("executive");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const [top, setTop] = useState<{ topic: string; channel: string; engagement: number }[]>([]);
  async function load() {
    setItems(await api.get<Item[]>("/content?limit=120"));
    const a = await api.get<{ top: typeof top }>("/content/analytics").catch(() => null);
    if (a) setTop(a.top);
  }
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
  async function copyCaption(i: Item) {
    const text = [i.title, i.body, i.hashtags].filter(Boolean).join("\n\n");
    try { await navigator.clipboard.writeText(text); setMsg("✅ Caption copied — paste it when you post manually."); }
    catch { setMsg("❌ Clipboard unavailable — copy from the expanded content instead."); }
  }
  async function makeVideo(id: string) {
    setMsg("Producing media…");
    try {
      const r = await api.post<{ ok: boolean; available?: Record<string, boolean> }>(`/content/${id}/video`, {});
      const a = r.available || {};
      setMsg(r.ok
        ? `🎬 Started. Voiceover:${a.voiceover ? "✓" : "—"} Video:${a.video ? "✓" : "—"} Hosting:${a.hosting ? "✓" : "—"}${!a.video ? " (add ELEVENLABS/VIDEO keys to enable)" : ""}`
        : "❌ failed");
    } catch (e) { setMsg(String(e)); }
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

      {top.length > 0 && (
        <div className="card mb-4">
          <h2 className="mb-2 text-sm font-semibold text-gray-700">🔥 Top performing content</h2>
          <div className="flex flex-wrap gap-2">
            {top.map((t, i) => (
              <span key={i} className="rounded-full bg-green-50 px-3 py-1 text-xs text-green-700">
                {t.topic} · {t.channel} · {t.engagement} eng
              </span>
            ))}
          </div>
          <p className="mt-2 text-xs text-gray-400">The factory makes more in the categories that perform best.</p>
        </div>
      )}

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
                  {["instagram", "tiktok", "youtube"].includes(i.channel) && !i.video_url &&
                    <button onClick={() => makeVideo(i.id)} className="ml-1 rounded border border-gray-300 px-2 py-1 text-xs">🎬 Video</button>}
                  {i.video_url && (
                    <a href={i.video_url} target="_blank" rel="noreferrer"
                       className="ml-1 rounded border border-emerald-300 bg-emerald-50 px-2 py-1 text-xs text-emerald-700"
                       title="Download the video to post manually">⬇ Video</a>
                  )}
                  <button onClick={() => copyCaption(i)} className="ml-1 rounded border border-gray-300 px-2 py-1 text-xs" title="Copy caption + hashtags">📋 Copy</button>
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
