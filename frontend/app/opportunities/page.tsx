"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Opp = {
  id: string; kind: string; title: string; value: number; probability: number;
  urgency: number; effort: number; objective: string | null; command_center: string;
  status: string; link: string | null; notes: string | null; expected_value: number;
};

const KINDS = ["investor", "podcast", "collab", "speaking", "partnership", "brand_deal", "press", "conference", "other"];
const OBJECTIVES = ["", "music", "consulting", "insurance", "savorymind", "exec_role", "brand"];

function money(n: number) {
  return n >= 1000 ? `$${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}k` : `$${n}`;
}

function Opportunities() {
  const [refresh, setRefresh] = useState(0);
  const { data } = useFetch<Opp[]>(() => api.get<Opp[]>("/opportunities"), [refresh]);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ title: "", kind: "investor", value: 0, probability: 0.3, urgency: 1, effort: 2, objective: "", link: "", notes: "" });

  async function create() {
    if (!f.title.trim()) return;
    setBusy(true);
    try {
      await api.post("/opportunities", { ...f, objective: f.objective || undefined });
      setF({ title: "", kind: "investor", value: 0, probability: 0.3, urgency: 1, effort: 2, objective: "", link: "", notes: "" });
      setOpen(false); setRefresh((n) => n + 1);
    } finally { setBusy(false); }
  }

  async function setStatus(id: string, status: string) {
    await api.post(`/opportunities/${id}/status`, { status });
    setRefresh((n) => n + 1);
  }

  const openOpps = (data || []).filter((o) => o.status === "Open");
  const pipeline = openOpps.reduce((s, o) => s + o.expected_value, 0);

  return (
    <div>
      <PageHeader title="Opportunities"
        subtitle="Every opportunity — investors, podcasts, collabs, speaking, brand deals — scored and ranked into your daily brief."
        action={<button className="btn" onClick={() => setOpen(!open)}>{open ? "Close" : "+ Add opportunity"}</button>} />

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-3">
        <div className="card"><div className="text-xs text-gray-500">Open opportunities</div><div className="text-3xl font-bold text-brand">{openOpps.length}</div></div>
        <div className="card"><div className="text-xs text-gray-500">Expected pipeline value</div><div className="text-3xl font-bold">{money(pipeline)}</div></div>
        <div className="card"><div className="text-xs text-gray-500">Won</div><div className="text-3xl font-bold text-green-600">{(data || []).filter((o) => o.status === "Won").length}</div></div>
      </div>

      {open && (
        <div className="card mb-6 grid gap-3 sm:grid-cols-2">
          <input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Title (e.g. Pitch to Acme Ventures)" className="rounded-lg border border-gray-300 px-3 py-2 text-sm sm:col-span-2" />
          <label className="text-sm">Kind
            <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
              {KINDS.map((k) => <option key={k} value={k}>{k.replace(/_/g, " ")}</option>)}
            </select>
          </label>
          <label className="text-sm">Objective
            <select value={f.objective} onChange={(e) => setF({ ...f, objective: e.target.value })} className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
              {OBJECTIVES.map((o) => <option key={o} value={o}>{o || "—"}</option>)}
            </select>
          </label>
          <label className="text-sm">Value ($)
            <input type="number" value={f.value} onChange={(e) => setF({ ...f, value: Number(e.target.value) })} className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          </label>
          <label className="text-sm">Probability (0–1)
            <input type="number" step="0.05" min="0" max="1" value={f.probability} onChange={(e) => setF({ ...f, probability: Number(e.target.value) })} className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          </label>
          <input value={f.link} onChange={(e) => setF({ ...f, link: e.target.value })} placeholder="Link (optional)" className="rounded-lg border border-gray-300 px-3 py-2 text-sm sm:col-span-2" />
          <button className="btn sm:col-span-2" onClick={create} disabled={busy || !f.title.trim()}>{busy ? "Saving…" : "Save opportunity"}</button>
        </div>
      )}

      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs text-gray-500">
            <tr><th className="p-3">Opportunity</th><th className="p-3">Value</th><th className="p-3">Win %</th><th className="p-3">Expected</th><th className="p-3">Status</th><th className="p-3"></th></tr>
          </thead>
          <tbody>
            {(data || []).map((o) => (
              <tr key={o.id} className="border-t">
                <td className="p-3">
                  <div className="font-medium">{o.link ? <a href={o.link} target="_blank" rel="noreferrer" className="hover:underline">{o.title}</a> : o.title}</div>
                  <div className="text-xs text-gray-400">{o.kind.replace(/_/g, " ")}{o.objective ? ` · ${o.objective}` : ""}</div>
                </td>
                <td className="p-3">{money(o.value)}</td>
                <td className="p-3">{Math.round(o.probability * 100)}%</td>
                <td className="p-3 font-semibold text-green-600">{money(o.expected_value)}</td>
                <td className="p-3"><span className={`rounded px-2 py-0.5 text-xs ${o.status === "Won" ? "bg-green-100 text-green-700" : o.status === "Open" ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-500"}`}>{o.status}</span></td>
                <td className="p-3 text-right">
                  {o.status === "Open" && (
                    <span className="flex justify-end gap-1">
                      <button onClick={() => setStatus(o.id, "Won")} className="rounded bg-green-600 px-2 py-1 text-xs text-white">Won</button>
                      <button onClick={() => setStatus(o.id, "Lost")} className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-500">Lost</button>
                      <button onClick={() => setStatus(o.id, "Dismissed")} className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-400">Dismiss</button>
                    </span>
                  )}
                </td>
              </tr>
            ))}
            {data && data.length === 0 && <tr><td colSpan={6} className="p-6 text-center text-gray-400">No opportunities yet — add one and it&apos;ll rank into your daily brief.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Opportunities /></AuthGate>;
}
