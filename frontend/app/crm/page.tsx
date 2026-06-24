"use client";

import { Fragment, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

type Contact = {
  id: string; name: string; company: string | null; title: string | null;
  email: string | null; phone: string | null; status: string | null;
  source: string | null; link: string; kind?: string; subject?: string;
};
type Mem = { id: string; kind: string; content: string };
type Detail = Contact & { memories: Mem[] };

const SOURCES: { key: string; label: string; icon: string }[] = [
  { key: "", label: "All", icon: "👥" },
  { key: "insurance", label: "Insurance", icon: "🛡️" },
  { key: "savorymind", label: "Restaurants", icon: "🍽️" },
  { key: "career", label: "Employers", icon: "💼" },
  { key: "music", label: "Music", icon: "🎵" },
  { key: "influence", label: "Influence", icon: "📣" },
  { key: "manual", label: "Added", icon: "✋" },
];

function CRM() {
  const [items, setItems] = useState<Contact[]>([]);
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", company: "", title: "", email: "", phone: "", kind: "recruiter" });

  async function load() {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (source) p.set("source", source);
    setItems(await api.get<Contact[]>(`/crm?${p.toString()}`));
  }
  useEffect(() => { load().catch(() => {}); }, [source]);  // eslint-disable-line react-hooks/exhaustive-deps

  async function expand(c: Contact) {
    if (open === c.id) { setOpen(null); setDetail(null); return; }
    setOpen(c.id); setDetail(null);
    setDetail(await api.get<Detail>(`/crm/${encodeURIComponent(c.id)}`));
  }

  async function addContact() {
    if (!form.name.trim()) return;
    await api.post("/crm", form);
    setForm({ name: "", company: "", title: "", email: "", phone: "", kind: "recruiter" });
    setAdding(false); setSource("manual"); await load();
  }

  return (
    <div>
      <PageHeader title="Universal CRM"
        subtitle="Every contact across every venture — joined to the memory graph. One search, one surface." />

      <div className="mb-4 flex flex-wrap gap-2">
        {SOURCES.map((s) => (
          <button key={s.key} onClick={() => setSource(s.key)}
            className={`rounded-full px-3 py-1 text-sm ${source === s.key ? "bg-brand text-white" : "bg-gray-100 text-gray-600"}`}>
            {s.icon} {s.label}
          </button>
        ))}
      </div>

      <div className="mb-4 flex gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()}
          placeholder="Search name, company, email, phone…"
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        <button className="btn" onClick={load}>Search</button>
        <button className="rounded-lg border border-gray-300 px-3 py-2 text-sm" onClick={() => setAdding(!adding)}>+ Add</button>
      </div>

      {adding && (
        <div className="card mb-4 grid gap-2 sm:grid-cols-3">
          {(["name", "company", "title", "email", "phone"] as const).map((f) => (
            <input key={f} placeholder={f} value={form[f]}
              onChange={(e) => setForm({ ...form, [f]: e.target.value })}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          ))}
          <button className="btn" onClick={addContact}>Save contact</button>
        </div>
      )}

      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs text-gray-500">
            <tr><th className="p-3">Name</th><th className="p-3">Title / Company</th>
              <th className="p-3">Source</th><th className="p-3">Status</th><th className="p-3"></th></tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <Fragment key={c.id}>
                <tr className="cursor-pointer border-t hover:bg-gray-50" onClick={() => expand(c)}>
                  <td className="p-3 font-medium">{c.name}</td>
                  <td className="p-3 text-gray-500">{[c.title, c.company].filter(Boolean).join(" · ")}</td>
                  <td className="p-3"><span className="rounded bg-gray-100 px-2 py-0.5 text-xs">{c.kind || c.source}</span></td>
                  <td className="p-3 text-gray-500">{c.status || "—"}</td>
                  <td className="p-3 text-right text-gray-400">{open === c.id ? "▲" : "▼"}</td>
                </tr>
                {open === c.id && (
                  <tr className="border-t bg-gray-50/50">
                    <td colSpan={5} className="p-4">
                      <div className="flex flex-wrap gap-4 text-xs text-gray-600">
                        {c.email && <span>✉️ {c.email}</span>}
                        {c.phone && <span>📞 {c.phone}</span>}
                        <a href={c.link} className="text-brand">Open in {c.source} ↗</a>
                      </div>
                      <div className="mt-3">
                        <div className="text-xs font-semibold text-gray-500">🧠 What Bruno remembers</div>
                        {!detail && <div className="text-xs text-gray-400">Loading…</div>}
                        {detail && detail.memories.length === 0 && <div className="text-xs text-gray-400">Nothing yet.</div>}
                        <ul className="mt-1 space-y-1">
                          {detail?.memories.map((m) => (
                            <li key={m.id} className="text-sm">• {m.content}</li>
                          ))}
                        </ul>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {items.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-gray-400">No contacts.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><CRM /></AuthGate>;
}
