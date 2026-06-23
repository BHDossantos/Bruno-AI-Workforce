"use client";

import { api } from "@/lib/api";
import { AuthGate, Expandable, PageHeader, StatusBadge, useFetch } from "@/components/ui";

type Restaurant = {
  id: string;
  name: string;
  owner_manager: string;
  cuisine: string;
  city: string;
  email: string;
  instagram: string;
  pain_points: string;
  menu_analysis: Record<string, unknown> | null;
  pitch_email: string | null;
  linkedin_msg: string | null;
  follow_up: string | null;
  status: string;
};

function SavoryMind() {
  const { data, loading } = useFetch<Restaurant[]>(() => api.get<Restaurant[]>("/restaurants?kind=prospect&limit=200"));
  return (
    <div>
      <PageHeader title="SavoryMind Leads" subtitle="Restaurant prospects with AI menu analysis and pitch" />
      {loading && <p className="text-gray-400">Loading…</p>}
      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">Restaurant</th>
              <th className="th">Cuisine / City</th>
              <th className="th">Contact</th>
              <th className="th">Pain points</th>
              <th className="th">Menu analysis</th>
              <th className="th">Status</th>
              <th className="th">Pitch</th>
            </tr>
          </thead>
          <tbody>
            {(data || []).map((r) => (
              <tr key={r.id} className="border-t border-gray-100">
                <td className="td"><div className="font-medium">{r.name}</div><div className="text-xs text-gray-400">{r.owner_manager}</div></td>
                <td className="td">{r.cuisine}<div className="text-xs text-gray-400">{r.city}</div></td>
                <td className="td text-xs">{r.email}<br />{r.instagram}</td>
                <td className="td text-xs">{r.pain_points}</td>
                <td className="td"><Expandable label="Analysis" text={r.menu_analysis ? JSON.stringify(r.menu_analysis, null, 2) : null} /></td>
                <td className="td"><StatusBadge status={r.status} /></td>
                <td className="td space-y-1">
                  <Expandable label="Pitch email" text={r.pitch_email} />
                  <Expandable label="LinkedIn msg" text={r.linkedin_msg} />
                  <Expandable label="Demo invite" text={r.follow_up} />
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
  return <AuthGate><SavoryMind /></AuthGate>;
}
