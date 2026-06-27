"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useFetch } from "@/components/ui";

/** Lead Pipeline Health — explains why warm/hot leads aren't flowing yet and the
 * exact next action to fix it. Collapsible; auto-hides the detail when healthy. */
type Step = { key: string; label: string; ok: boolean; detail: string };
type Source = { name: string; ok: boolean; detail: string };
type Health = {
  healthy: boolean;
  summary: string;
  counts: { leads: number; warm: number; hot: number; sent: number; drafted: number; replies: number };
  by_brand: Record<string, { total: number; warm: number; hot: number }>;
  sources: Source[];
  steps: Step[];
  blockers: string[];
};

export default function LeadHealth({ refresh = 0 }: { refresh?: number }) {
  const { data } = useFetch<Health>(() => api.get<Health>("/leads/pipeline-health"), [refresh]);
  const [open, setOpen] = useState(false);
  if (!data) return null;
  const c = data.counts;

  return (
    <div className={`mb-4 rounded-xl border p-4 ${data.healthy ? "border-green-200 bg-green-50" : "border-amber-300 bg-amber-50"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-lg">{data.healthy ? "✅" : "⚠️"}</span>
          <span className="font-semibold">{data.healthy ? "Lead pipeline is live" : "Lead pipeline needs setup"}</span>
          <span className="text-xs text-gray-500">{data.summary}</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-600">
          <span>🔥 {c.hot} hot</span><span>🌤️ {c.warm} warm</span>
          <span>{c.sent} sent</span><span>{c.replies} replies</span>
          <button onClick={() => setOpen((o) => !o)} className="font-medium text-brand-dark underline">
            {open ? "Hide" : "What to fix"}
          </button>
        </div>
      </div>

      {data.blockers.length > 0 && (
        <ul className="mt-2 space-y-1">
          {data.blockers.slice(0, open ? data.blockers.length : 1).map((b, i) => (
            <li key={i} className="text-sm text-gray-800">→ {b}</li>
          ))}
        </ul>
      )}

      {open && (
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">The chain</div>
            <ul className="space-y-1">
              {data.steps.map((s) => (
                <li key={s.key} className="text-sm">
                  <span className={s.ok ? "text-green-600" : "text-amber-600"}>{s.ok ? "✓" : "✗"}</span>{" "}
                  <span className="font-medium">{s.label}</span>
                  <div className="ml-4 text-xs text-gray-500">{s.detail}</div>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">Data sources</div>
            <ul className="space-y-1">
              {data.sources.map((s) => (
                <li key={s.name} className="text-sm">
                  <span className={s.ok ? "text-green-600" : "text-gray-400"}>{s.ok ? "✓" : "○"}</span>{" "}
                  <span className="font-medium">{s.name}</span>
                  <div className="ml-4 text-xs text-gray-500">{s.detail}</div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
