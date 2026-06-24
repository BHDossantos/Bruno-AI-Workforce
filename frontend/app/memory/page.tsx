"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

type Mem = {
  id: string; kind: string; subject: string | null; content: string;
  source: string | null; created_at: string | null;
};

const KINDS = ["fact", "contact", "preference", "goal", "event", "note"];

function Memory() {
  const [items, setItems] = useState<Mem[]>([]);
  const [q, setQ] = useState("");
  const [content, setContent] = useState("");
  const [subject, setSubject] = useState("");
  const [kind, setKind] = useState("fact");
  const [busy, setBusy] = useState(false);

  async function load() {
    const path = q ? `/memory?q=${encodeURIComponent(q)}&limit=50` : "/memory?limit=50";
    setItems(await api.get<Mem[]>(path));
  }
  useEffect(() => { load().catch(() => {}); }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  async function addMem() {
    if (!content.trim()) return;
    setBusy(true);
    try {
      await api.post("/memory", { content, subject: subject || null, kind });
      setContent(""); setSubject("");
      await load();
    } finally { setBusy(false); }
  }

  return (
    <div>
      <PageHeader title="Memory / Knowledge Graph"
        subtitle="Everything your AI workforce remembers — people, companies, preferences, goals, events. Agents read this for context." />

      <div className="mb-6 flex gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load()}
          placeholder="Search memory (semantic when AI is on)…"
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        <button className="btn" onClick={load}>Search</button>
      </div>

      <div className="card mb-6 space-y-3">
        <h2 className="text-sm font-semibold text-gray-700">Teach Bruno something</h2>
        <textarea rows={2} value={content} onChange={(e) => setContent(e.target.value)}
          placeholder="e.g. Recruiter Jane at Acme is hiring a Director of SRE; prefers email."
          className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        <div className="flex flex-wrap gap-2">
          <input value={subject} onChange={(e) => setSubject(e.target.value)}
            placeholder="About (person/company)" className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <select value={kind} onChange={(e) => setKind(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
            {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <button className="btn" onClick={addMem} disabled={busy}>{busy ? "Saving…" : "Remember"}</button>
        </div>
      </div>

      <div className="space-y-2">
        {items.map((m) => (
          <div key={m.id} className="card">
            <div className="flex items-center justify-between">
              <span className="rounded bg-brand/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-brand">{m.kind}</span>
              <span className="text-xs text-gray-400">{m.subject || ""}{m.created_at ? ` · ${new Date(m.created_at).toLocaleDateString()}` : ""}</span>
            </div>
            <p className="mt-1 text-sm">{m.content}</p>
          </div>
        ))}
        {items.length === 0 && <p className="text-sm text-gray-400">No memories yet — add one above, or they fill in as leads reply.</p>}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Memory /></AuthGate>;
}
