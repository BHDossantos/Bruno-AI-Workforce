"use client";

import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Check = { ok: boolean; detail: string };
type SelfTest = { ready: number; total: number; checks: Record<string, Check> };

const LABELS: Record<string, string> = {
  openai: "OpenAI (AI engine)", gmail_personal: "Gmail — personal", gmail_insurance: "Gmail — insurance (Thrust)",
  jobs_api: "Jobs API (LinkedIn/Indeed)", gcs_bucket: "Image hosting (GCS)",
  instagram: "Instagram", facebook: "Facebook", linkedin: "LinkedIn", x: "X (Twitter)", spotify: "Spotify",
};

function Status() {
  const { data, loading } = useFetch<SelfTest>(() => api.get<SelfTest>("/admin/selftest"));
  return (
    <div>
      <PageHeader title="System Status" subtitle="Live health of every service. Green = working; amber = not connected/needs a key." />
      {loading && <p className="text-gray-400">Checking…</p>}
      {data && (
        <>
          <div className="mb-4 text-sm text-gray-500">{data.ready} of {data.total} services live.</div>
          <div className="grid gap-2 sm:grid-cols-2">
            {Object.entries(data.checks).map(([key, c]) => (
              <div key={key} className="card flex items-center justify-between">
                <div>
                  <div className="font-medium">{LABELS[key] || key}</div>
                  <div className="text-xs text-gray-400">{c.detail}</div>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${c.ok ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
                  {c.ok ? "● live" : "○ off"}
                </span>
              </div>
            ))}
          </div>
          <p className="mt-4 text-xs text-gray-400">
            Tokens auto-refresh daily, so connections stay live on their own. You only get an email if a daily run fails.
          </p>
        </>
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><Status /></AuthGate>;
}
