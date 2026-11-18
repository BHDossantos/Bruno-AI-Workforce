"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

type Issue = { severity: string; message: string };
type Audit = {
  id: string; url: string; business: string | null; score: number; grade: string | null;
  status_code: number | null; title: string | null; meta_description: string | null;
  h1_count: number; word_count: number; issues: Issue[]; error: string | null; created_at: string | null;
};

const GRADE_CLR: Record<string, string> = {
  A: "text-emerald-600", B: "text-emerald-600", C: "text-amber-600", D: "text-orange-600", F: "text-red-600",
};
const SEV: Record<string, { dot: string; label: string }> = {
  critical: { dot: "bg-red-500", label: "Critical" },
  warn: { dot: "bg-amber-500", label: "Warning" },
  info: { dot: "bg-sky-400", label: "Info" },
};

function Seo() {
  const [url, setUrl] = useState("");
  const [business, setBusiness] = useState("");
  const [busy, setBusy] = useState(false);
  const [current, setCurrent] = useState<Audit | null>(null);
  const [recent, setRecent] = useState<Audit[]>([]);

  async function loadRecent() {
    setRecent(await api.get<Audit[]>("/seo/audits?limit=20"));
  }
  useEffect(() => { loadRecent().catch(() => {}); }, []);

  async function run() {
    if (!url.trim()) { alert("Enter a URL to audit."); return; }
    setBusy(true);
    try {
      const a = await api.post<Audit>("/seo/audit", { url, business: business || null });
      setCurrent(a);
      await loadRecent();
    } finally { setBusy(false); }
  }
  async function remove(id: string) {
    await api.del(`/seo/audits/${id}`);
    if (current?.id === id) setCurrent(null);
    await loadRecent();
  }

  const scoreColor = (s: number) => (s >= 80 ? "text-emerald-600" : s >= 60 ? "text-amber-600" : "text-red-600");

  return (
    <div>
      <PageHeader title="SEO Audit" subtitle="Grade any page's on-page SEO — title, meta, headings, alt text, content depth — and get a fix list." />

      <div className="card mb-4 space-y-3">
        <div className="flex flex-col gap-2 sm:flex-row">
          <input className="input flex-1" placeholder="https://example.com/page" value={url}
                 onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") run(); }} />
          <input className="input sm:w-44" placeholder="For (optional)" value={business}
                 onChange={(e) => setBusiness(e.target.value)} />
          <button className="btn" onClick={run} disabled={busy}>{busy ? "Auditing…" : "Run audit"}</button>
        </div>
      </div>

      {current && (
        <div className="card mb-4">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <a href={current.url} target="_blank" rel="noreferrer" className="truncate font-semibold text-brand hover:underline">{current.url}</a>
              <div className="mt-1 text-xs text-gray-400">
                {current.status_code ? `HTTP ${current.status_code}` : "no response"} · {current.word_count} words · {current.h1_count} H1
              </div>
            </div>
            <div className="text-right">
              <div className={`text-4xl font-bold ${scoreColor(current.score)}`}>{current.score}</div>
              <div className={`text-sm font-semibold ${GRADE_CLR[current.grade || "F"]}`}>Grade {current.grade}</div>
            </div>
          </div>

          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <div><dt className="text-xs uppercase text-gray-400">Title</dt><dd className="text-gray-800">{current.title || <span className="text-red-500">missing</span>} {current.title && <span className="text-gray-400">({current.title.length})</span>}</dd></div>
            <div><dt className="text-xs uppercase text-gray-400">Meta description</dt><dd className="text-gray-800">{current.meta_description ? `${current.meta_description.slice(0, 80)}${current.meta_description.length > 80 ? "…" : ""} (${current.meta_description.length})` : <span className="text-amber-500">missing</span>}</dd></div>
          </dl>

          <div className="mt-3">
            <div className="mb-1 text-xs font-semibold uppercase text-gray-400">Findings</div>
            <ul className="space-y-1">
              {current.issues.map((it, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <span className={`mt-1.5 h-2 w-2 flex-none rounded-full ${SEV[it.severity]?.dot || "bg-gray-300"}`} />
                  <span className="text-gray-700"><b className="text-gray-500">{SEV[it.severity]?.label || it.severity}:</b> {it.message}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <div className="card p-0">
        <div className="border-b p-3 text-xs font-semibold uppercase text-gray-400">Recent audits</div>
        {recent.length === 0 ? (
          <div className="p-6 text-center text-gray-400">No audits yet. Run one above.</div>
        ) : (
          <ul>
            {recent.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 border-b px-3 py-2 text-sm last:border-0">
                <button className="min-w-0 flex-1 text-left" onClick={() => setCurrent(a)}>
                  <div className="truncate text-gray-800">{a.url}</div>
                  <div className="text-xs text-gray-400">{a.created_at?.slice(0, 16).replace("T", " ")}{a.business ? ` · ${a.business}` : ""}</div>
                </button>
                <span className={`font-bold ${scoreColor(a.score)}`}>{a.score}</span>
                <span className={`text-xs font-semibold ${GRADE_CLR[a.grade || "F"]}`}>{a.grade}</span>
                <button className="text-gray-300 hover:text-red-500" onClick={() => remove(a.id)}>✕</button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Seo /></AuthGate>;
}
