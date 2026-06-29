"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Goal = {
  target: number; won_today: number; won_total: number; on_track: boolean; deficit: number;
  conversion_rate: number; conversion_measured: boolean; prospects_contacted: number;
  needed_touches_per_day: number; sent_today: number;
};
type Scale = {
  enabled: boolean; target?: number; rate?: number; measured?: boolean;
  needed_touches?: number; changed?: Record<string, number>; constraint?: string | null;
};

function Clients() {
  const [refresh, setRefresh] = useState(0);
  const { data: g } = useFetch<Goal>(() => api.get<Goal>("/clients/goal"), [refresh]);
  const [target, setTarget] = useState<number | "">("");
  const [scale, setScale] = useState<Scale | null>(null);
  const [busy, setBusy] = useState(false);

  async function saveTarget() {
    if (!target || target < 1) return;
    setBusy(true);
    try {
      const r = await api.post<Scale>("/clients/target", { target });
      setScale(r); setRefresh((n) => n + 1);
    } finally { setBusy(false); }
  }

  async function rescale() {
    setBusy(true);
    try {
      const r = await api.post<Scale>("/clients/autoscale", {});
      setScale(r); setRefresh((n) => n + 1);
    } finally { setBusy(false); }
  }

  return (
    <div>
      <PageHeader title="Client Acquisition Engine"
        subtitle="The standing order: bring in new clients 24/7. The engine sizes outreach volume to hit your daily target at the funnel's measured conversion rate." />

      {g && (
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          <div className="card">
            <div className="text-xs text-gray-500">Clients today</div>
            <div className="text-3xl font-bold">{g.won_today}<span className="text-base text-gray-400">/ {g.target}</span></div>
            <div className={`mt-1 text-xs ${g.on_track ? "text-green-600" : "text-amber-600"}`}>
              {g.on_track ? "On track 🎉" : `${g.deficit} to go`}
            </div>
          </div>
          <div className="card">
            <div className="text-xs text-gray-500">Conversion rate</div>
            <div className="text-3xl font-bold">{(g.conversion_rate * 100).toFixed(1)}%</div>
            <div className="mt-1 text-xs text-gray-400">{g.conversion_measured ? "measured" : "assumed (default)"}</div>
          </div>
          <div className="card">
            <div className="text-xs text-gray-500">Touches needed / day</div>
            <div className="text-3xl font-bold">{g.needed_touches_per_day.toLocaleString()}</div>
            <div className="mt-1 text-xs text-gray-400">{g.sent_today.toLocaleString()} sent today</div>
          </div>
          <div className="card">
            <div className="text-xs text-gray-500">Prospects contacted</div>
            <div className="text-3xl font-bold">{g.prospects_contacted.toLocaleString()}</div>
            <div className="mt-1 text-xs text-gray-400">{g.won_total.toLocaleString()} won all-time</div>
          </div>
        </div>
      )}

      <div className="card mb-6">
        <div className="mb-2 text-sm font-semibold">Daily client target</div>
        <div className="flex flex-wrap items-center gap-2">
          <input type="number" min={1} max={500} placeholder={String(g?.target ?? 15)}
            value={target} onChange={(e) => setTarget(e.target.value ? Number(e.target.value) : "")}
            className="w-28 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <button className="btn" onClick={saveTarget} disabled={busy || !target}>Set target & resize</button>
          <button className="rounded-lg border border-gray-300 px-3 py-2 text-sm" onClick={rescale} disabled={busy}>
            {busy ? "Working…" : "Re-size outreach now"}
          </button>
        </div>
        <p className="mt-2 text-xs text-gray-500">
          Resizing raises lead sourcing + the daily send cap toward the volume needed to hit your target,
          staying within safe mailbox limits. It runs automatically every morning.
        </p>
      </div>

      {scale && (
        <div className="card">
          <div className="mb-1 text-sm font-semibold">Last resize</div>
          {scale.changed && Object.keys(scale.changed).length > 0 ? (
            <ul className="list-inside list-disc text-sm text-gray-700">
              {Object.entries(scale.changed).map(([k, v]) => (
                <li key={k}>{k.replace(/_/g, " ")} → <b>{v}</b></li>
              ))}
            </ul>
          ) : <p className="text-sm text-gray-500">Already sized correctly — no change needed.</p>}
          {scale.constraint && (
            <p className="mt-2 rounded bg-amber-50 p-3 text-sm text-amber-800">⚠️ {scale.constraint}</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><Clients /></AuthGate>;
}
