"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Row = {
  id: string; company: string | null; name: string | null; email: string | null;
  phone: string | null; industry: string | null; segment: string | null;
  status: string | null; score: number; band: string; reasons: string[];
};

const BAND: Record<string, string> = {
  hot: "bg-red-100 text-red-700", warm: "bg-amber-100 text-amber-700", cold: "bg-gray-100 text-gray-500",
};

function LeadFinder() {
  const [f, setF] = useState({ segment: "", temperature: "", industry: "", min_score: "", q: "", has_email: true });
  const [params, setParams] = useState("has_email=true");

  const { data, loading } = useFetch<Row[]>(() => api.get<Row[]>(`/leads/search?${params}`), [params]);

  function search() {
    const p = new URLSearchParams();
    if (f.segment) p.set("segment", f.segment);
    if (f.temperature) p.set("temperature", f.temperature);
    if (f.industry) p.set("industry", f.industry);
    if (f.min_score) p.set("min_score", f.min_score);
    if (f.q) p.set("q", f.q);
    if (f.has_email) p.set("has_email", "true");
    setParams(p.toString());
  }

  return (
    <div>
      <PageHeader title="Lead Finder"
        subtitle="Search every sourced lead, filtered and ranked by an explainable 0–100 fit score. Work the highest-scoring prospects first." />

      <div className="card mb-4 grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <select value={f.segment} onChange={(e) => setF({ ...f, segment: e.target.value })} className="input">
          <option value="">All segments</option>
          <option value="commercial">Commercial insurance</option>
          <option value="personal">Home/Auto</option>
          <option value="consulting">Consulting</option>
          <option value="referral_partner">Referral partners</option>
        </select>
        <select value={f.temperature} onChange={(e) => setF({ ...f, temperature: e.target.value })} className="input">
          <option value="">Any temperature</option>
          <option value="hot">🔥 Hot</option>
          <option value="warm">🌤️ Warm</option>
          <option value="cold">Cold</option>
        </select>
        <input className="input" placeholder="Industry" value={f.industry}
          onChange={(e) => setF({ ...f, industry: e.target.value })} />
        <input className="input" placeholder="Min score" type="number" value={f.min_score}
          onChange={(e) => setF({ ...f, min_score: e.target.value })} />
        <input className="input" placeholder="Search name/company/email" value={f.q}
          onChange={(e) => setF({ ...f, q: e.target.value })} onKeyDown={(e) => e.key === "Enter" && search()} />
        <button className="btn" onClick={search}>Search</button>
      </div>

      <label className="mb-3 flex items-center gap-2 text-sm text-gray-600">
        <input type="checkbox" checked={f.has_email} onChange={(e) => setF({ ...f, has_email: e.target.checked })} />
        Only leads with an email (sendable)
      </label>

      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs text-gray-500">
            <tr><th className="p-3">Score</th><th className="p-3">Lead</th><th className="p-3">Segment</th>
              <th className="p-3">Why</th><th className="p-3">Contact</th></tr>
          </thead>
          <tbody>
            {data?.map((r) => (
              <tr key={r.id} className="border-t">
                <td className="p-3"><span className={`badge ${BAND[r.band] || ""}`}>{r.score}</span></td>
                <td className="p-3"><div className="font-medium">{r.company || r.name || "—"}</div>
                  <div className="text-xs text-gray-400">{r.name && r.company ? r.name : (r.industry || "")}</div></td>
                <td className="p-3 text-gray-500">{r.segment}</td>
                <td className="p-3 text-xs text-gray-500">{r.reasons.join(" · ")}</td>
                <td className="p-3 text-xs text-gray-500">{r.email || r.phone || "—"}</td>
              </tr>
            ))}
            {data && data.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-gray-400">No leads match.</td></tr>}
            {loading && <tr><td colSpan={5} className="p-6 text-center text-gray-400">Loading…</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><LeadFinder /></AuthGate>;
}
