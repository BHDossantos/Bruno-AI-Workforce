"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Plan = {
  id: string; brief: string; business: string | null; status: string;
  leads_sourced: number; restaurants_sourced: number;
  plan: {
    audience?: string; summary?: string; schedule?: string; success_metric?: string;
    channels?: string[]; filters?: Record<string, string>;
    sequence?: { step: number; purpose: string }[];
  };
};
type BuildResult = (Plan & { ok: true }) | { ok: false; error: string };

function PlanCard({ p, onLaunch, busy }: { p: Plan; onLaunch: (id: string) => void; busy: boolean }) {
  const pl = p.plan || {};
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <div className="font-semibold">{p.business || "Campaign"} <span className="text-xs font-normal text-gray-400">· {p.status}</span></div>
        <button onClick={() => onLaunch(p.id)} disabled={busy || p.status === "launched"}
          className="rounded-lg bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50">
          {p.status === "launched" ? "Launched ✓" : busy ? "Launching…" : "🚀 Launch"}
        </button>
      </div>
      <div className="mt-1 text-sm text-gray-700">{pl.summary || p.brief}</div>
      {pl.audience && <div className="mt-2 text-xs text-gray-500"><b>Audience:</b> {pl.audience}</div>}
      {pl.filters && Object.keys(pl.filters).length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {Object.entries(pl.filters).map(([k, v]) => (
            <span key={k} className="rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-600">{k}: {String(v)}</span>
          ))}
        </div>
      )}
      {pl.channels && <div className="mt-1 text-xs text-gray-500"><b>Channels:</b> {pl.channels.join(", ")}</div>}
      {pl.sequence && pl.sequence.length > 0 && (
        <div className="mt-2 text-xs text-gray-500">
          <b>Sequence ({pl.sequence.length}):</b> {pl.sequence.map((s) => `${s.step}. ${s.purpose}`).join(" → ")}
        </div>
      )}
      {pl.schedule && <div className="mt-1 text-xs text-gray-500"><b>Schedule:</b> {pl.schedule}</div>}
      {pl.success_metric && <div className="mt-1 text-xs text-gray-500"><b>Success:</b> {pl.success_metric}</div>}
      {p.status === "launched" && (
        <div className="mt-2 text-xs font-medium text-green-700">
          ✅ Sourced {p.leads_sourced + p.restaurants_sourced} matching {p.leads_sourced ? "leads" : "restaurants"} for this campaign
        </div>
      )}
    </div>
  );
}

function CampaignBuilder() {
  const [brief, setBrief] = useState("");
  const [busy, setBusy] = useState(false);
  const [launching, setLaunching] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [tick, setTick] = useState(0);
  const { data: plans } = useFetch<Plan[]>(() => api.get<Plan[]>("/campaigns"), [tick]);

  async function build() {
    if (!brief.trim()) return;
    setBusy(true); setErr("");
    try {
      const r = await api.post<BuildResult>("/campaigns/plan", { brief: brief.trim() });
      if (!r.ok) setErr(r.error); else { setBrief(""); setTick((t) => t + 1); }
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }

  async function launch(id: string) {
    setLaunching(id); setErr("");
    try {
      const r = await api.post<{ ok: boolean; error?: string }>(`/campaigns/${id}/launch`, {});
      if (!r.ok) setErr(r.error || "Launch failed"); else setTick((t) => t + 1);
    } catch (e) { setErr(String(e)); } finally { setLaunching(null); }
  }

  return (
    <div className="max-w-3xl">
      <PageHeader title="Campaign Builder"
        subtitle="Describe the campaign in plain English — the AI turns it into a structured plan (audience, filters, sequence, schedule) you can review and launch." />
      <div className="card mb-4">
        <textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={3}
          placeholder="e.g. Find Boston restaurants under 4.3 stars with 300+ reviews, pitch SavoryMind to the owner, follow up 6 times, stop after a reply."
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        <div className="mt-2 flex justify-end">
          <button className="btn" onClick={build} disabled={busy || !brief.trim()}>{busy ? "Building…" : "Build campaign"}</button>
        </div>
      </div>
      {err && <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">❌ {err}</p>}
      <div className="space-y-3">
        {plans?.map((p) => <PlanCard key={p.id} p={p} onLaunch={launch} busy={launching === p.id} />)}
        {plans && plans.length === 0 && !busy && (
          <div className="card text-sm text-gray-500">No campaigns yet — describe one above.</div>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><CampaignBuilder /></AuthGate>;
}
