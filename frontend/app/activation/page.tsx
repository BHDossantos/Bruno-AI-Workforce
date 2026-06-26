"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type Item = { key: string; label: string; required: boolean; status: string; detail: string; action: string };
type Activation = { ready_pct: number; live: boolean; done: number; required_total: number; next_step: Item | null; checklist: Item[] };

const ICON: Record<string, string> = { done: "✅", todo: "⬜", optional: "○" };

function Activation() {
  const { data, loading, error, reload } = useFetch<Activation>(() => api.get<Activation>("/activation"));
  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;

  const required = data.checklist.filter((c) => c.required);
  const optional = data.checklist.filter((c) => !c.required);

  return (
    <div className="space-y-8">
      <PageHeader title="Go-Live Activation"
        subtitle="Everything needed to take the workforce from built to operating daily." />

      <div className="card">
        <div className="flex items-baseline justify-between">
          <div className="text-lg font-semibold">{data.live ? "🎉 You're live" : `${data.ready_pct}% ready to go live`}</div>
          <div className="text-sm text-gray-500">{data.done}/{data.required_total} essentials</div>
        </div>
        <div className="mt-3 h-3 overflow-hidden rounded bg-gray-100">
          <div className="h-full rounded bg-brand" style={{ width: `${data.ready_pct}%` }} />
        </div>
      </div>

      <Section title="Essentials" items={required} />
      <Section title="Recommended (optional)" items={optional} />
    </div>
  );
}

function Section({ title, items }: { title: string; items: Item[] }) {
  return (
    <div>
      <h2 className="mb-3 font-semibold">{title}</h2>
      <div className="space-y-2">
        {items.map((c) => (
          <div key={c.key} className={`card flex items-start justify-between gap-4 ${c.status === "done" ? "opacity-70" : ""}`}>
            <div className="flex items-start gap-3">
              <span className="text-lg">{ICON[c.status]}</span>
              <div>
                <div className={`font-medium ${c.status === "done" ? "line-through text-gray-400" : ""}`}>{c.label}</div>
                <div className="text-sm text-gray-500">{c.detail}</div>
              </div>
            </div>
            {c.status !== "done" && (
              <Link href={c.action} className="shrink-0 rounded-lg border border-gray-300 px-3 py-1.5 text-sm">Set up</Link>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Activation /></AuthGate>;
}
