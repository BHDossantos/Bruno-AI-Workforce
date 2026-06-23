"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, Expandable, PageHeader, StatusBadge, useFetch } from "@/components/ui";

type Lead = {
  id: string;
  segment: string;
  category: string;
  company_name: string;
  owner_name: string;
  email: string;
  phone: string;
  industry: string;
  reason: string;
  score: number;
  status: string;
  cold_email: string | null;
  call_script: string | null;
  linkedin_msg: string | null;
};

function Insurance() {
  const [segment, setSegment] = useState("");
  const { data, loading } = useFetch<Lead[]>(
    () => api.get<Lead[]>(`/leads?limit=200${segment ? `&segment=${segment}` : ""}`),
    [segment]
  );
  return (
    <div>
      <PageHeader
        title="Insurance Leads"
        subtitle="Commercial & personal prospects with outreach scripts"
        action={
          <div className="flex gap-2">
            <select value={segment} onChange={(e) => setSegment(e.target.value)} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
              <option value="">All segments</option>
              <option value="commercial">Commercial</option>
              <option value="personal">Personal</option>
            </select>
            <button className="btn-ghost" onClick={() => api.download("/export/leads.csv", "leads.csv")}>Export CSV</button>
          </div>
        }
      />
      {loading && <p className="text-gray-400">Loading…</p>}
      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">Score</th>
              <th className="th">Company / Owner</th>
              <th className="th">Segment</th>
              <th className="th">Contact</th>
              <th className="th">Reason</th>
              <th className="th">Status</th>
              <th className="th">Scripts</th>
            </tr>
          </thead>
          <tbody>
            {(data || []).map((l) => (
              <tr key={l.id} className="border-t border-gray-100">
                <td className="td"><span className="badge bg-brand/10 text-brand-dark">{l.score}</span></td>
                <td className="td"><div className="font-medium">{l.company_name}</div><div className="text-xs text-gray-400">{l.owner_name}</div></td>
                <td className="td capitalize">{l.segment}<div className="text-xs text-gray-400">{l.category}</div></td>
                <td className="td text-xs">{l.email}<br />{l.phone}</td>
                <td className="td max-w-xs text-xs">{l.reason}</td>
                <td className="td"><StatusBadge status={l.status} /></td>
                <td className="td space-y-1">
                  <Expandable label="Cold email" text={l.cold_email} />
                  <Expandable label="Call script" text={l.call_script} />
                  <Expandable label="LinkedIn msg" text={l.linkedin_msg} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Insurance /></AuthGate>;
}
