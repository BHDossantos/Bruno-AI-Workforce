"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Scripts = {
  cold_email?: { subject?: string; body?: string };
  linkedin_dm?: string; follow_up_1?: string; breakup?: string;
};
type Blueprint = {
  id: string; url: string; business: string | null; offer: string | null;
  icp: string | null; industries: string | null; pain_points: string | null;
  angles: string | null; scripts: Scripts; created_at: string | null;
};
type BuildResult = (Blueprint & { ok: true }) | { ok: false; error: string };

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">{label}</div>
      <div className="mt-0.5 whitespace-pre-wrap text-sm text-gray-700">{value}</div>
    </div>
  );
}

function Card({ b }: { b: Blueprint }) {
  const s = b.scripts || {};
  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">{b.business || b.url}</h3>
        <a href={b.url.startsWith("http") ? b.url : `https://${b.url}`} target="_blank" rel="noreferrer"
           className="text-xs text-brand">{b.url} ↗</a>
      </div>
      <Field label="Offer" value={b.offer} />
      <Field label="Ideal customer" value={b.icp} />
      <Field label="Target industries" value={b.industries} />
      <Field label="Pain points" value={b.pain_points} />
      <Field label="Outreach angles" value={b.angles} />
      {(s.cold_email || s.linkedin_dm || s.follow_up_1 || s.breakup) && (
        <div className="rounded-lg bg-gray-50 p-3 space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">Generated scripts</div>
          {s.cold_email && (
            <div className="text-sm"><b>Cold email</b> — <i>{s.cold_email.subject}</i>
              <div className="mt-0.5 whitespace-pre-wrap text-gray-700">{s.cold_email.body}</div></div>
          )}
          {s.follow_up_1 && <div className="text-sm"><b>Follow-up</b><div className="whitespace-pre-wrap text-gray-700">{s.follow_up_1}</div></div>}
          {s.linkedin_dm && <div className="text-sm"><b>LinkedIn DM</b><div className="whitespace-pre-wrap text-gray-700">{s.linkedin_dm}</div></div>}
          {s.breakup && <div className="text-sm"><b>Breakup</b><div className="whitespace-pre-wrap text-gray-700">{s.breakup}</div></div>}
        </div>
      )}
    </div>
  );
}

function AgentBuilder() {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [tick, setTick] = useState(0);
  const { data: saved } = useFetch<Blueprint[]>(() => api.get<Blueprint[]>("/agents/blueprints"), [tick]);

  async function build() {
    if (!url.trim()) return;
    setBusy(true); setErr("");
    try {
      const r = await api.post<BuildResult>("/agents/blueprint", { url: url.trim() });
      if (!r.ok) setErr(r.error);
      else { setUrl(""); setTick((t) => t + 1); }
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="max-w-3xl">
      <PageHeader title="Create AI Agent from a URL"
        subtitle="Paste a business website — savorymind.net, bnbglobal.net, an insurance page — and the AI scans it and builds the offer, ideal customer, target industries, pain points, outreach angles and ready-to-use message scripts." />

      <div className="card mb-4 flex flex-wrap gap-2">
        <input value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === "Enter" && build()}
          placeholder="savorymind.net" className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        <button className="btn" onClick={build} disabled={busy || !url.trim()}>
          {busy ? "Scanning…" : "Create Agent"}
        </button>
      </div>
      {err && <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">❌ {err}</p>}

      <div className="space-y-4">
        {saved?.map((b) => <Card key={b.id} b={b} />)}
        {saved && saved.length === 0 && !busy && (
          <div className="card text-sm text-gray-500">No agents yet — paste a URL above to build your first.</div>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><AgentBuilder /></AuthGate>;
}
