"use client";

import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Obj = { key: string; name: string; current_value: number; target_value: number };
type Commander = {
  center: string; name: string; agents: string[];
  objectives: Obj[]; open_actions: number; pipeline_value: number;
};

const ICON: Record<string, string> = {
  wealth: "💰", business: "🏢", influence: "📣", personal: "💪", life_ops: "🗂️",
};

function money(n: number) {
  return n >= 1000 ? `$${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}k` : `$${n}`;
}

function Centers() {
  const { data } = useFetch<Commander[]>(() => api.get<Commander[]>("/commanders"));
  return (
    <div>
      <PageHeader title="Command Centers"
        subtitle="Your AI commanders — each directs its agents toward an outcome. CEO → Commander → Agent." />
      <div className="grid gap-4 md:grid-cols-2">
        {(data || []).map((c) => (
          <div key={c.center} className="card">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">{ICON[c.center]} {c.name}</h2>
              <span className="text-sm text-gray-500">{c.open_actions} open · {money(c.pipeline_value)} pipeline</span>
            </div>
            <div className="mt-1 text-xs text-gray-400">
              Agents: {c.agents.length ? c.agents.join(", ") : "—"}
            </div>
            <div className="mt-3 space-y-3">
              {c.objectives.map((o) => {
                const pct = o.target_value ? Math.min(100, (o.current_value / o.target_value) * 100) : 0;
                return (
                  <div key={o.key}>
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-700">{o.name}</span>
                      <span className="text-gray-400">{money(Math.round(o.current_value))} / {money(o.target_value)}</span>
                    </div>
                    <div className="mt-1 h-2 overflow-hidden rounded bg-gray-100">
                      <div className="h-full rounded bg-brand" style={{ width: `${Math.max(2, pct)}%` }} />
                    </div>
                  </div>
                );
              })}
              {c.objectives.length === 0 && <p className="text-xs text-gray-400">No objectives yet.</p>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Centers /></AuthGate>;
}
