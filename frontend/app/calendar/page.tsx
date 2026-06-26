"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, StatusBadge } from "@/components/ui";

type Item = {
  id: string; topic: string; business: string | null; channel: string;
  title: string | null; body: string | null; hashtags: string | null;
  status: string; scheduled_for: string | null;
};

// Channels shown on the calendar — social auto-posts + blog drafts to grab manually.
const SOCIAL = ["instagram", "facebook", "linkedin", "x", "blog"];

function fullText(i: Item): string {
  const tags = (i.hashtags || "").trim();
  const body = (i.body || "").trim();
  const head = i.channel === "blog" && i.title ? `${i.title}\n\n` : "";
  return `${head}${body}${tags && !body.includes(tags) ? `\n\n${tags}` : ""}`.trim();
}
const dayKey = (iso: string | null) => (iso ? iso.slice(0, 10) : "Unscheduled");

function dayLabel(day: string): string {
  if (day === "Unscheduled") return "Unscheduled";
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const d = new Date(day + "T00:00:00");
  const diff = Math.round((d.getTime() - today.getTime()) / 86_400_000);
  const nice = d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
  if (diff === 0) return `Today · ${nice}`;
  if (diff === 1) return `Tomorrow · ${nice}`;
  return nice;
}

function Calendar() {
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  async function copy(i: Item) {
    const text = fullText(i);
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Clipboard API blocked (non-HTTPS / permissions) — fall back to a prompt.
      window.prompt("Copy this post:", text);
    }
    setCopied(i.id);
    setTimeout(() => setCopied((c) => (c === i.id ? null : c)), 1500);
  }

  async function load() { setItems(await api.get<Item[]>("/content?limit=300")); }
  useEffect(() => { load().catch(() => {}); }, []);

  async function act(id: string, path: string, body?: unknown) {
    setBusy(id);
    try { await api.post(`/content/${id}/${path}`, body || {}); await load(); }
    finally { setBusy(null); }
  }

  async function regenerateAll() {
    if (!confirm("Clear the current unpublished drafts and have the engine rewrite fresh content at the new quality bar?")) return;
    setBusy("all"); setMsg(null);
    try {
      const r = await api.post<{ cleared: number; regenerated: number }>("/content/regenerate", {});
      setMsg(`✅ Cleared ${r.cleared} old draft(s), generated ${r.regenerated} fresh piece(s).`);
      await load();
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(null); }
  }

  // Show queued/upcoming social content (the stuff that will auto-post).
  const queued = items.filter((i) => SOCIAL.includes(i.channel) &&
    ["scheduled", "needs_approval", "ready", "generated"].includes(i.status));
  const groups: Record<string, Item[]> = {};
  for (const i of queued) (groups[dayKey(i.scheduled_for)] ||= []).push(i);
  const days = Object.keys(groups).sort();

  return (
    <div>
      <PageHeader title="Content Calendar"
        subtitle="Everything planned, by day. Click a post to read it, Copy to grab it for manual posting, or approve/reschedule/drop."
        action={<button className="btn" disabled={busy === "all"} onClick={regenerateAll}>
          {busy === "all" ? "Regenerating…" : "↻ Regenerate all"}
        </button>} />
      {msg && <p className="mb-3 text-sm text-gray-600">{msg}</p>}
      {days.length === 0 && <p className="text-sm text-gray-400">Nothing queued. Produce content in the Content Factory, or hit “Regenerate all”.</p>}
      <div className="space-y-5">
        {days.map((day) => (
          <div key={day}>
            <h2 className="mb-2 text-sm font-semibold text-gray-700">{dayLabel(day)}</h2>
            <div className="space-y-2">
              {groups[day].map((i) => (
                <div key={i.id} className="card">
                  <div className="flex items-center justify-between gap-3">
                    <button className="min-w-0 text-left" onClick={() => setOpenId(openId === i.id ? null : i.id)}>
                      <div className="truncate font-medium">{i.title || i.topic}</div>
                      <div className="text-xs text-gray-400">{i.channel} · {i.business}
                        {i.scheduled_for ? ` · ${new Date(i.scheduled_for).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : ""}
                        <span className="ml-1 text-gray-300">· {openId === i.id ? "hide" : "view"}</span></div>
                    </button>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={i.status} />
                      <button disabled={busy === i.id} onClick={() => copy(i)}
                        className="rounded border border-gray-300 px-2 py-1 text-xs">
                        {copied === i.id ? "Copied ✓" : "Copy"}</button>
                      {i.status !== "scheduled" &&
                        <button disabled={busy === i.id} onClick={() => act(i.id, "approve")}
                          className="rounded border border-gray-300 px-2 py-1 text-xs">Approve</button>}
                      <button disabled={busy === i.id} onClick={() => act(i.id, "regenerate")}
                        title="Rewrite at the new quality bar"
                        className="rounded border border-gray-300 px-2 py-1 text-xs">↻</button>
                      <input type="datetime-local" className="rounded border border-gray-300 px-1 py-1 text-xs"
                        onChange={(e) => e.target.value && act(i.id, "schedule", { when: new Date(e.target.value).toISOString() })} />
                      <button disabled={busy === i.id} onClick={() => act(i.id, "dismiss")}
                        className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-500">✕</button>
                    </div>
                  </div>
                  {openId === i.id && (
                    <pre className="mt-3 max-h-80 overflow-y-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-sm text-gray-700">{fullText(i) || "(empty)"}</pre>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Calendar /></AuthGate>;
}
