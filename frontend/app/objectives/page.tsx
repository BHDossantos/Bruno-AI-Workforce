"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

type Obj = {
  key: string; name: string; command_center: string; metric: string;
  target_value: number; current_value: number; rank: number; weight: number; status: string;
};

const CENTER: Record<string, string> = {
  wealth: "💰", business: "🏢", influence: "📣", personal: "💪", life_ops: "🗂️",
};

function Objectives() {
  const [items, setItems] = useState<Obj[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  async function load() { setItems(await api.get<Obj[]>("/objectives")); }
  useEffect(() => { load().catch(() => {}); }, []);

  async function save(key: string, patch: Partial<Obj>) {
    setBusy(key); setMsg("");
    try { await api.patch(`/objectives/${key}`, patch); setMsg("Saved — priorities updated."); await load(); }
    catch (e) { setMsg(String(e)); }
    finally { setBusy(null); }
  }

  return (
    <div>
      <PageHeader title="Objectives"
        subtitle="Tune what your workforce optimizes for. Weight controls how much attention each outcome's actions get in the Daily Brief." />
      {msg && <p className="mb-3 text-sm text-gray-600">{msg}</p>}

      <div className="space-y-3">
        {items.map((o) => {
          const pct = o.target_value ? Math.min(100, (o.current_value / o.target_value) * 100) : 0;
          return (
            <div key={o.key} className="card">
              <div className="flex items-center justify-between">
                <div className="font-semibold">{CENTER[o.command_center] || "•"} {o.name}</div>
                <span className="text-xs text-gray-400">{o.command_center} · {o.metric}</span>
              </div>

              <div className="mt-2 h-2 overflow-hidden rounded bg-gray-100">
                <div className="h-full rounded bg-brand" style={{ width: `${Math.max(2, pct)}%` }} />
              </div>
              <div className="mt-1 text-xs text-gray-400">
                {Math.round(o.current_value).toLocaleString()} / {o.target_value.toLocaleString()}
              </div>

              <div className="mt-3 flex flex-wrap items-end gap-4">
                <label className="text-xs text-gray-600">
                  Weight: <span className="font-semibold">{o.weight.toFixed(2)}</span>
                  <input type="range" min={0} max={1} step={0.05} defaultValue={o.weight}
                    onMouseUp={(e) => save(o.key, { weight: parseFloat((e.target as HTMLInputElement).value) })}
                    onTouchEnd={(e) => save(o.key, { weight: parseFloat((e.target as HTMLInputElement).value) })}
                    className="ml-2 align-middle" />
                </label>
                <label className="text-xs text-gray-600">
                  Target
                  <input type="number" defaultValue={o.target_value}
                    onBlur={(e) => { const v = parseFloat(e.target.value); if (v !== o.target_value) save(o.key, { target_value: v }); }}
                    className="ml-2 w-28 rounded border border-gray-300 px-2 py-1" />
                </label>
                {busy === o.key && <span className="text-xs text-gray-400">Saving…</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Objectives /></AuthGate>;
}
