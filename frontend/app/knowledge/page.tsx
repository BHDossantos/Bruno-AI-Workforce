"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type Doc = { id: string; title: string; content: string; tags: string[]; source: string | null; created_at: string | null };
type Source = { id: string; title: string; snippet: string; tags: string[] };
type Answer = { ok: boolean; answer: string; sources: Source[]; ai_used: boolean };

function KnowledgeBase() {
  const { data, loading, error, reload } = useFetch<Doc[]>(() => api.get<Doc[]>("/knowledge"));
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [saving, setSaving] = useState(false);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [asking, setAsking] = useState(false);

  async function addDoc() {
    if (!title.trim() || !content.trim()) return;
    setSaving(true);
    try {
      await api.post("/knowledge", { title, content, tags: tags.split(",").map((t) => t.trim()).filter(Boolean) });
      setTitle(""); setContent(""); setTags(""); reload();
    } finally { setSaving(false); }
  }
  async function del(id: string) {
    await api.del(`/knowledge/${id}`); reload();
  }
  async function ask() {
    if (!q.trim()) return;
    setAsking(true); setAnswer(null);
    try { setAnswer(await api.post<Answer>("/knowledge/ask", { question: q })); }
    finally { setAsking(false); }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="📚 Insurance Knowledge Base"
        subtitle="Store carrier guidelines, discount rules, coverage FAQs, claims notes and training — then ask plain-English questions and get answers cited from your own docs." />

      {/* Ask */}
      <div className="card">
        <h2 className="font-semibold">Ask the knowledge base</h2>
        <div className="mt-2 flex gap-2">
          <input value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask()}
            placeholder="e.g. What discounts apply to a homeowner bundling auto in MA?"
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <button className="btn" onClick={ask} disabled={asking}>{asking ? "…" : "Ask"}</button>
        </div>
        {answer && (
          <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
            <p className="whitespace-pre-wrap text-sm text-gray-800">{answer.answer}</p>
            {answer.ai_used && <span className="mt-1 inline-block rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700">AI-summarized</span>}
            {answer.sources.length > 0 && (
              <div className="mt-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">Sources</p>
                <ul className="mt-1 space-y-1">
                  {answer.sources.map((s) => (
                    <li key={s.id} className="text-xs text-gray-600"><span className="font-medium text-gray-800">{s.title}:</span> {s.snippet}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Add doc */}
      <div className="card">
        <h2 className="font-semibold">Add a doc</h2>
        <div className="mt-2 space-y-2">
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title (e.g. MA auto discounts)"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <textarea value={content} onChange={(e) => setContent(e.target.value)}
            placeholder="Paste the guideline, rule, FAQ or training note…"
            className="h-28 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="Tags, comma-separated (auto, discounts, MA)"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <button className="btn" onClick={addDoc} disabled={saving || !title.trim() || !content.trim()}>
            {saving ? "Saving…" : "Add to knowledge base"}
          </button>
        </div>
      </div>

      {/* Docs list */}
      <div className="card">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 className="font-semibold">Docs</h2>
          {data && data.length === 0 && (
            <button className="btn-ghost text-sm" onClick={async () => { await api.post("/knowledge/seed", {}); reload(); }}>
              Load starter docs
            </button>
          )}
        </div>
        {!data ? <LoadState loading={loading} error={error} onRetry={reload} /> : data.length === 0 ? (
          <p className="text-sm text-gray-400">No docs yet — add carrier guidelines, discount rules and FAQs above.</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {data.map((d) => (
              <li key={d.id} className="py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{d.title}</span>
                  <button className="btn-ghost text-xs" onClick={() => del(d.id)}>Delete</button>
                </div>
                <p className="mt-0.5 line-clamp-2 text-xs text-gray-500">{d.content}</p>
                {d.tags.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {d.tags.map((t) => <span key={t} className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">{t}</span>)}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><KnowledgeBase /></AuthGate>;
}
