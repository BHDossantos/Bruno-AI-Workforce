"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Item = {
  entity_type: string;
  entity_id: string;
  name: string;
  channel: string;
  profile_url: string | null;
  dm_url?: string | null;
  handle: string | null;
  message: string;
  status: string;
};

function Queue() {
  const [channel, setChannel] = useState("");
  const [tick, setTick] = useState(0);
  const { data, loading } = useFetch<Item[]>(
    () => api.get<Item[]>(`/outreach/social${channel ? `?channel=${channel}` : ""}`),
    [channel, tick]
  );
  const [copied, setCopied] = useState<string | null>(null);

  async function copy(id: string, text: string) {
    await navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied((c) => (c === id ? null : c)), 1500);
  }

  async function markSent(it: Item) {
    await api.post("/outreach/social/mark", { entity_type: it.entity_type, entity_id: it.entity_id, status: "Sent" });
    setTick((t) => t + 1);
  }

  async function skip(it: Item) {
    await api.post("/outreach/social/mark", { entity_type: it.entity_type, entity_id: it.entity_id, status: "Closed Lost" });
    setTick((t) => t + 1);
  }

  async function copyAndOpenDM(it: Item) {
    try { await navigator.clipboard.writeText(it.message); setCopied(it.entity_id); } catch { /* clipboard blocked */ }
    window.open(it.dm_url || it.profile_url || "#", "_blank", "noreferrer");
    setTimeout(() => setCopied((c) => (c === it.entity_id ? null : c)), 1500);
  }

  return (
    <div>
      <PageHeader
        title="Outreach Queue"
        subtitle="One-click LinkedIn & Instagram outreach — copy, open the profile, send, mark done"
        action={
          <select value={channel} onChange={(e) => setChannel(e.target.value)} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
            <option value="">All channels</option>
            <option value="linkedin">LinkedIn</option>
            <option value="instagram">Instagram</option>
          </select>
        }
      />
      <p className="mb-4 rounded bg-amber-50 p-3 text-sm text-amber-800">
        These are sent <b>manually</b> by you (platform rules forbid auto-DMs) — but the message and
        profile link are prepared, so it&apos;s ~2 clicks each: <b>Copy</b> → <b>Open profile</b> → paste &amp; send → <b>Mark sent</b>.
      </p>
      {loading && <p className="text-gray-400">Loading…</p>}
      <div className="space-y-3">
        {(data || []).map((it) => (
          <div key={it.entity_type + it.entity_id} className="card flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="mb-1 flex items-center gap-2">
                <span className={`badge ${it.channel === "linkedin" ? "bg-blue-100 text-blue-700" : "bg-pink-100 text-pink-700"}`}>
                  {it.channel}
                </span>
                <span className="font-medium">{it.name}</span>
                {it.handle && <span className="text-xs text-gray-400">@{it.handle.replace(/^@/, "")}</span>}
              </div>
              <p className="whitespace-pre-wrap rounded bg-gray-50 p-2 text-sm text-gray-700">{it.message}</p>
            </div>
            <div className="flex shrink-0 flex-col gap-2">
              {it.channel === "instagram" && (it.dm_url || it.profile_url) ? (
                <button className="btn" onClick={() => copyAndOpenDM(it)}>
                  {copied === it.entity_id ? "Copied ✓ — opening" : "Copy & open DM"}
                </button>
              ) : (
                <button className="btn-ghost" onClick={() => copy(it.entity_id, it.message)}>
                  {copied === it.entity_id ? "Copied ✓" : "Copy"}
                </button>
              )}
              {it.profile_url && (
                <a className="btn-ghost text-center" href={it.profile_url} target="_blank" rel="noreferrer">Open profile</a>
              )}
              <button className="btn" onClick={() => markSent(it)}>Mark sent</button>
              <button className="btn-ghost text-gray-400" onClick={() => skip(it)}>Skip</button>
            </div>
          </div>
        ))}
        {!loading && (data || []).length === 0 && (
          <p className="text-gray-400">Nothing pending — run the agents to generate outreach.</p>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Queue /></AuthGate>;
}
