"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

type Contact = { id: string; name: string; company: string | null; title: string | null; source: string | null; link: string; kind?: string };
type Mem = { id: string; kind: string; subject: string | null; content: string };
type Results = { contacts: Contact[]; memories: Mem[] };

function Search() {
  const params = useSearchParams();
  const initial = params.get("q") || "";
  const [q, setQ] = useState(initial);
  const [res, setRes] = useState<Results | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  async function run(query: string) {
    if (!query.trim()) { setRes(null); return; }
    setLoading(true); setErr("");
    try { setRes(await api.get<Results>(`/search?q=${encodeURIComponent(query)}`)); }
    catch (e) { setErr(String(e)); }
    finally { setLoading(false); }
  }
  useEffect(() => { run(initial); }, [initial]);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <PageHeader title="Search" subtitle="One search across every contact and everything Bruno remembers." />
      <div className="mb-6 flex gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && run(q)}
          autoFocus placeholder="Search contacts and memory…"
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        <button className="btn" onClick={() => run(q)}>Search</button>
      </div>

      {loading && <p className="text-sm text-gray-400">Searching…</p>}
      {err && <p className="text-sm text-red-600">{err}</p>}
      {res && !loading && (
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <h2 className="mb-2 text-sm font-semibold text-gray-700">👥 Contacts ({res.contacts.length})</h2>
            <div className="space-y-2">
              {res.contacts.map((c) => (
                <Link key={c.id} href={c.link || "/crm"} className="card block hover:ring-2 hover:ring-brand/40">
                  <div className="font-medium">{c.name}</div>
                  <div className="text-xs text-gray-500">{[c.title, c.company, c.kind || c.source].filter(Boolean).join(" · ")}</div>
                </Link>
              ))}
              {res.contacts.length === 0 && <p className="text-sm text-gray-400">No contacts.</p>}
            </div>
          </div>
          <div>
            <h2 className="mb-2 text-sm font-semibold text-gray-700">🧠 Memory ({res.memories.length})</h2>
            <div className="space-y-2">
              {res.memories.map((m) => (
                <div key={m.id} className="card">
                  <div className="text-[10px] font-semibold uppercase text-brand">{m.kind}{m.subject ? ` · ${m.subject}` : ""}</div>
                  <p className="text-sm">{m.content}</p>
                </div>
              ))}
              {res.memories.length === 0 && <p className="text-sm text-gray-400">Nothing remembered.</p>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Page() {
  return (
    <AuthGate>
      <Suspense fallback={<p className="p-6 text-sm text-gray-400">Loading…</p>}>
        <Search />
      </Suspense>
    </AuthGate>
  );
}
