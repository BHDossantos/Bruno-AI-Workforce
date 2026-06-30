"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type Card = {
  id: string; name: string; company: string | null; segment: string | null;
  score: number; temperature: string; email: string | null;
  last_contacted: string | null; expected_value: number; next_action: string;
};
type Stage = { stage: string; next_action: string; count: number; value: number; cards: Card[] };
type Board = { stages: Stage[]; pipeline_value: number };

const STAGES_ORDER = ["New", "Contacted", "Replied", "Qualified", "Meeting", "Won", "Lost", "Nurture"];
const TEMP_COLOR: Record<string, string> = {
  hot: "bg-red-100 text-red-700", warm: "bg-amber-100 text-amber-700",
  cold: "bg-gray-100 text-gray-500", dead: "bg-gray-200 text-gray-400",
};
const SEG: Record<string, string> = {
  commercial: "🛡️", personal: "🏠", consulting: "💻", restaurant: "🍽️",
};

function money(n: number) {
  return n >= 1000 ? `$${(n / 1000).toFixed(1)}k` : `$${n}`;
}

function Deals() {
  const [segment, setSegment] = useState("");
  const [tick, setTick] = useState(0);
  const { data, loading, error, reload } = useFetch<Board>(
    () => api.get<Board>(`/crm/pipeline${segment ? `?segment=${segment}` : ""}`), [segment, tick]);
  const [moving, setMoving] = useState<string | null>(null);

  async function move(card: Card, stage: string) {
    setMoving(card.id);
    try {
      await api.post("/crm/pipeline/move", { lead_id: card.id, stage });
      setTick((t) => t + 1);
    } finally { setMoving(null); }
  }

  return (
    <div>
      <PageHeader title="Deal Pipeline"
        subtitle="Every lead as a deal card — score, next action, and expected value — moving from New to Won. Drag through the stages (or use the menu on a card)."
        action={
          <select value={segment} onChange={(e) => setSegment(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
            <option value="">All businesses</option>
            <option value="commercial">Insurance — Commercial</option>
            <option value="personal">Insurance — Home/Auto</option>
            <option value="consulting">BnB Global</option>
          </select>
        } />

      {data && (
        <div className="mb-4 text-sm text-gray-600">
          Weighted pipeline value: <b className="text-gray-900">{money(data.pipeline_value)}</b>
        </div>
      )}
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}

      {data && (
        <div className="flex gap-3 overflow-x-auto pb-4">
          {data.stages.map((col) => (
            <div key={col.stage} className="w-64 shrink-0">
              <div className="mb-2 flex items-center justify-between px-1">
                <span className="text-sm font-semibold">{col.stage}</span>
                <span className="text-xs text-gray-400">{col.count} · {money(col.value)}</span>
              </div>
              <div className="space-y-2 rounded-lg bg-gray-50 p-2 min-h-[80px]">
                {col.cards.length === 0 && <div className="px-1 py-3 text-center text-xs text-gray-300">—</div>}
                {col.cards.map((c) => (
                  <div key={c.id} className="rounded-lg border border-gray-200 bg-white p-2.5 shadow-sm">
                    <div className="flex items-start justify-between gap-1">
                      <span className="text-sm font-medium leading-tight">{SEG[c.segment || ""] || "•"} {c.name}</span>
                      <span className="shrink-0 text-[11px] font-semibold text-green-600">{money(c.expected_value)}</span>
                    </div>
                    {c.company && <div className="truncate text-xs text-gray-500">{c.company}</div>}
                    <div className="mt-1.5 flex items-center gap-1">
                      <span className={`badge ${TEMP_COLOR[c.temperature] || ""}`}>{c.temperature}</span>
                      <span className="text-[11px] text-gray-400">score {c.score}</span>
                    </div>
                    <div className="mt-1 text-[11px] text-gray-500">→ {c.next_action}</div>
                    <select disabled={moving === c.id} value={col.stage}
                      onChange={(e) => move(c, e.target.value)}
                      className="mt-2 w-full rounded border border-gray-200 px-1.5 py-1 text-[11px] text-gray-600">
                      {STAGES_ORDER.map((s) => <option key={s} value={s}>Move to: {s}</option>)}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><Deals /></AuthGate>;
}
