"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

// A CRM contact that is a lead exposes its full profile at /leads/{id}.
function leadProfileHref(cid: string): string | null {
  return cid.startsWith("lead:") ? `/leads/${cid.slice(5)}` : null;
}

type Contact = {
  id: string; name: string; company: string | null; title: string | null;
  email: string | null; phone: string | null; status: string | null;
  source: string | null; link: string; kind?: string; subject?: string;
};
type Mem = { id: string; kind: string; content: string };
type Conn = { id: string; subject: string; relation: string; direction: string; type?: string | null };
type Detail = Contact & { memories: Mem[]; connections: Conn[] };

const EMPTY_FORM = { name: "", company: "", title: "", email: "", phone: "", kind: "contact" };

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
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [savedContact, setSavedContact] = useState<Contact | null>(null);
  const [listState, setListState] = useState<"loading" | "ready" | "error">("loading");
  const savingRef = useRef(false);
  const request = useRef(0);

  async function load(filterSource: string, filterQuery: string) {
    const current = ++request.current;
    const p = new URLSearchParams();
    if (filterQuery.trim()) p.set("q", filterQuery.trim());
    if (filterSource) p.set("source", filterSource);
    setItems([]);
    setListState("loading");
    try {
      const next = await api.get<Contact[]>(`/crm?${p.toString()}`);
      if (current !== request.current) return;
      setItems(next);
      setListState("ready");
    } catch {
      if (current === request.current) setListState("error");
    }
  }

  useEffect(() => {
    void load("", "");
    return () => { request.current++; };
  }, []); // Load the initial unfiltered list.

  function showSource(next: string) {
    setSource(next);
    setSavedContact(null);
    void load(next, q);
  }

  function search() {
    setSavedContact(null);
    void load(source, q);
  }

  const displayed = savedContact && source === "manual" && !q.trim()
    ? [savedContact, ...items.filter((item) => item.id !== savedContact.id)] : items;

  const [note, setNote] = useState("");
  const [savingNote, setSavingNote] = useState(false);

  async function expand(c: Contact) {
    if (open === c.id) { setOpen(null); setDetail(null); return; }
    setOpen(c.id); setDetail(null); setNote("");
    setDetail(await api.get<Detail>(`/crm/${encodeURIComponent(c.id)}`));
  }

  async function saveNote(cid: string) {
    if (!note.trim()) return;
    setSavingNote(true);
    try {
      const updated = await api.post<Detail>(`/crm/${encodeURIComponent(cid)}/note`, { content: note.trim() });
      setDetail(updated); setNote("");
    } finally { setSavingNote(false); }
  }

  const [link, setLink] = useState({ to: "", relation: "connected_to" });
  const [savingLink, setSavingLink] = useState(false);

  async function saveLink(cid: string) {
    if (!link.to.trim()) return;
    setSavingLink(true);
    try {
      const updated = await api.post<Detail>(`/crm/${encodeURIComponent(cid)}/link`,
        { to_subject: link.to.trim(), relation: link.relation });
      setDetail(updated); setLink({ to: "", relation: "connected_to" });
    } finally { setSavingLink(false); }
  }

  async function addContact() {
    const name = form.name.trim();
    if (!name || savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    setSaveError("");
    try {
      const created = await api.post<Contact>("/crm", { ...form, name });
      if (!created?.id?.startsWith("contact:")) {
        setSaveError("The app did not confirm the contact ID. Check Added contacts before retrying.");
        return;
      }
      setForm(EMPTY_FORM);
      setAdding(false);
      setSavedContact(created);
      setQ("");
      setSource("manual");
      setOpen(null);
      setDetail(null);
      void load("manual", "");
    } catch {
      setSaveError("The app could not confirm the save. Check Added contacts before retrying.");
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  return (
    <div>
      <PageHeader title="Universal CRM"
        subtitle="Every contact across every venture — joined to the memory graph. One search, one surface." />

      <div className="mb-4 flex flex-wrap gap-2">
        {SOURCES.map((s) => (
          <button key={s.key} onClick={() => showSource(s.key)} aria-pressed={source === s.key}
            className={`rounded-full px-3 py-1 text-sm ${source === s.key ? "bg-brand text-white" : "bg-gray-100 text-gray-600"}`}>
            {s.icon} {s.label}
          </button>
        ))}
      </div>

      <div className="mb-4 flex gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()}
          placeholder="Search name, company, email, phone…"
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        <button className="btn" onClick={search}>Search</button>
        <button className="rounded-lg border border-gray-300 px-3 py-2 text-sm" disabled={saving} onClick={() => { setAdding(!adding); setSaveError(""); }}>+ Add</button>
      </div>

      {savedContact && <p role="status" className="mb-4 text-sm font-medium text-green-800">{savedContact.name} saved. Showing Added contacts without a search filter.</p>}
      {adding && (
        <div className="card mb-4 grid gap-2 sm:grid-cols-3">
          {(["name", "company", "title", "email", "phone"] as const).map((f) => (
            <input key={f} aria-label={f} placeholder={f} value={form[f]} disabled={saving}
              onChange={(e) => setForm({ ...form, [f]: e.target.value })}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          ))}
          <select aria-label="Contact type" disabled={saving} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
            <option value="contact">Contact</option>
            <option value="recruiter">Recruiter</option>
            <option value="partner">Partner</option>
            <option value="advisor">Advisor</option>
            <option value="client">Client</option>
          </select>
          <button className="btn" disabled={saving || !form.name.trim()} onClick={addContact}>{saving ? "Saving…" : "Save contact"}</button>
          {saveError && <p role="alert" className="text-sm text-red-700 sm:col-span-3">{saveError}</p>}
        </div>
      )}

      {listState === "error" && (
        <div role="status" className="mb-3 flex flex-wrap items-center gap-3 text-sm text-red-700">
          <span>Contacts could not be loaded.</span>
          <button type="button" onClick={() => void load(source, q)} className="rounded border border-gray-300 px-2 py-1">Retry contacts</button>
        </div>
      )}
      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs text-gray-500">
            <tr><th className="p-3">Name</th><th className="p-3">Title / Company</th>
              <th className="p-3">Source</th><th className="p-3">Status</th><th className="p-3"></th></tr>
          </thead>
          <tbody>
            {displayed.map((c) => (
              <Fragment key={c.id}>
                <tr className="cursor-pointer border-t hover:bg-gray-50" onClick={() => expand(c)}>
                  <td className="p-3 font-medium">{c.name}</td>
                  <td className="p-3 text-gray-500">{[c.title, c.company].filter(Boolean).join(" · ")}</td>
                  <td className="p-3"><span className="rounded bg-gray-100 px-2 py-0.5 text-xs">{c.kind || c.source}</span></td>
                  <td className="p-3 text-gray-500">{c.status || "—"}</td>
                  <td className="p-3 text-right whitespace-nowrap">
                    {leadProfileHref(c.id) && (
                      <Link href={leadProfileHref(c.id)!} onClick={(e) => e.stopPropagation()}
                        className="mr-3 text-xs font-medium text-brand hover:underline">Open profile ↗</Link>
                    )}
                    <span className="text-gray-400">{open === c.id ? "▲" : "▼"}</span>
                  </td>
                </tr>
                {open === c.id && (
                  <tr className="border-t bg-gray-50/50">
                    <td colSpan={5} className="p-4">
                      <div className="flex flex-wrap gap-4 text-xs text-gray-600">
                        {c.email && <span>✉️ {c.email}</span>}
                        {c.phone && <span>📞 {c.phone}</span>}
                        {leadProfileHref(c.id) && (
                          <Link href={leadProfileHref(c.id)!} className="font-medium text-brand">
                            Open full CRM profile (email · text · call · timeline) ↗
                          </Link>
                        )}
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
                        {detail && (
                          <div className="mt-3 flex gap-2">
                            <input
                              value={open === c.id ? note : ""}
                              onChange={(e) => setNote(e.target.value)}
                              onKeyDown={(e) => e.key === "Enter" && saveNote(c.id)}
                              placeholder="Teach the AI something (e.g. prefers WhatsApp, met at conference)…"
                              className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm" />
                            <button onClick={() => saveNote(c.id)} disabled={savingNote || !note.trim()}
                              className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">
                              {savingNote ? "Saving…" : "Remember"}
                            </button>
                          </div>
                        )}
                      </div>

                      {detail && (
                        <div className="mt-4">
                          <div className="text-xs font-semibold text-gray-500">🔗 Connections</div>
                          {detail.connections.length === 0
                            ? <div className="text-xs text-gray-400">No connections yet.</div>
                            : <ul className="mt-1 space-y-1">
                                {detail.connections.map((cn) => (
                                  <li key={cn.id} className="text-sm">
                                    <span className="text-gray-500">{cn.relation.replace(/_/g, " ")}</span>{" "}
                                    <span className="font-medium">{cn.subject}</span>
                                  </li>
                                ))}
                              </ul>}
                          <div className="mt-2 flex flex-wrap gap-2">
                            <input value={open === c.id ? link.to : ""}
                              onChange={(e) => setLink({ ...link, to: e.target.value })}
                              onKeyDown={(e) => e.key === "Enter" && saveLink(c.id)}
                              placeholder="Connect to (name / company)…"
                              className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm" />
                            <select value={link.relation} onChange={(e) => setLink({ ...link, relation: e.target.value })}
                              className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm">
                              <option value="connected_to">connected to</option>
                              <option value="works_at">works at</option>
                              <option value="hiring_manager_for">hiring manager for</option>
                              <option value="reports_to">reports to</option>
                              <option value="referred_by">referred by</option>
                              <option value="introduced_by">introduced by</option>
                              <option value="colleague">colleague</option>
                            </select>
                            <button onClick={() => saveLink(c.id)} disabled={savingLink || !link.to.trim()}
                              className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">
                              {savingLink ? "Linking…" : "Link"}
                            </button>
                          </div>
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {displayed.length === 0 && listState !== "error" && <tr><td colSpan={5} className="p-6 text-center text-gray-500">{listState === "loading" ? "Loading contacts…" : "No matching contacts."}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><CRM /></AuthGate>;
}
