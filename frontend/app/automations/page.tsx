"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Rule = { key: string; label: string; trigger: string; action: string; enabled: boolean };

function Automations() {
  const [tick, setTick] = useState(0);
  const { data } = useFetch<Rule[]>(() => api.get<Rule[]>("/automations"), [tick]);
  const [busy, setBusy] = useState<string | null>(null);

  async function toggle(r: Rule) {
    setBusy(r.key);
    try { await api.post("/automations/toggle", { key: r.key, on: !r.enabled }); setTick((t) => t + 1); }
    finally { setBusy(null); }
  }

  return (
    <div className="max-w-2xl">
      <PageHeader title="Automations"
        subtitle="When a prospect replies, the workforce branches automatically — create a task, suppress an unsubscribe, nurture a no, stop the drip. Toggle each rule on or off." />
      <div className="space-y-3">
        {data?.map((r) => (
          <div key={r.key} className="card flex items-center justify-between gap-4">
            <div>
              <div className="font-medium">{r.label}</div>
              <div className="text-xs text-gray-500">
                <span className="rounded bg-gray-100 px-1.5 py-0.5">{r.trigger}</span> → {r.action}
              </div>
            </div>
            <button onClick={() => toggle(r)} disabled={busy === r.key}
              className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold ${
                r.enabled ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-500"}`}>
              {r.enabled ? "ON" : "OFF"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Automations /></AuthGate>;
}
