"use client";

import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type Arm = { category: string; avg_engagement: number; samples: number };
type ChannelLearning = { channel: string; samples: number; next_pick: string | null; arms: Arm[] };
type PostingTime = { hour: number; learned: boolean; samples: number };
type OutreachArm = { style: string; sent: number; replied: number; rate: number };
type LeadCategory = { category: string; sent: number; replied: number; rate: number };
type Learnings = {
  method: string;
  content: ChannelLearning[];
  posting_times: Record<string, PostingTime>;
  outreach?: OutreachArm[];
  lead_categories?: LeadCategory[];
};

const ICON: Record<string, string> = {
  instagram: "📸", facebook: "👍", linkedin: "💼", tiktok: "🎵", x: "✖️",
};

function fmtHour(h: number): string {
  const am = h < 12;
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}${am ? "am" : "pm"}`;
}

function LearningsView() {
  const { data, loading, error, reload } = useFetch<Learnings>(() => api.get<Learnings>("/analytics/learnings"));
  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;

  return (
    <div className="space-y-8">
      <PageHeader title="What the AI has learned" subtitle="The workforce gets smarter over time — it tracks what works and adapts" />

      <div className="card bg-brand/5">
        <p className="text-sm text-gray-700">🧠 <b>How it learns:</b> {data.method}</p>
        <p className="mt-1 text-xs text-gray-500">
          New options are tried first, winners get used more, and it keeps re-testing — so it
          re-learns whenever your audience or channels change. The more it runs, the sharper it gets.
        </p>
      </div>

      <div>
        <h2 className="mb-3 font-semibold">Content — best categories per channel</h2>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {data.content.map((c) => (
            <div key={c.channel} className="card">
              <div className="mb-1 flex items-center justify-between">
                <span className="font-medium capitalize">{ICON[c.channel] || "🌐"} {c.channel}</span>
                <span className="text-xs text-gray-400">{c.samples} samples</span>
              </div>
              {c.next_pick && (
                <p className="mb-2 text-xs text-gray-500">Next pick: <b className="text-brand-dark">{c.next_pick}</b></p>
              )}
              {c.arms.length === 0 ? (
                <p className="text-xs text-gray-400">No engagement data yet — it&apos;ll learn as posts publish.</p>
              ) : (
                <div className="space-y-1.5">
                  {(() => {
                    const max = Math.max(1, ...c.arms.map((a) => a.avg_engagement));
                    return c.arms.map((a) => (
                      <div key={a.category} className="flex items-center gap-2">
                        <div className="w-24 shrink-0 truncate text-xs text-gray-600" title={a.category}>{a.category}</div>
                        <div className="h-4 flex-1 overflow-hidden rounded bg-gray-100">
                          <div className="h-full rounded bg-brand" style={{ width: `${Math.max(6, (a.avg_engagement / max) * 100)}%` }} />
                        </div>
                        <div className="w-16 shrink-0 text-right text-[11px] text-gray-500">{a.avg_engagement} · {a.samples}×</div>
                      </div>
                    ));
                  })()}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {data.outreach && data.outreach.length > 0 && (
        <div className="card">
          <h2 className="mb-3 font-semibold">Outreach — subject styles by reply rate</h2>
          <div className="space-y-1.5">
            {(() => {
              const max = Math.max(1, ...data.outreach.map((a) => a.rate));
              return data.outreach.map((a) => (
                <div key={a.style} className="flex items-center gap-2">
                  <div className="w-28 shrink-0 truncate text-xs text-gray-600" title={a.style}>{a.style}</div>
                  <div className="h-4 flex-1 overflow-hidden rounded bg-gray-100">
                    <div className="h-full rounded bg-green-500" style={{ width: `${Math.max(6, (a.rate / max) * 100)}%` }} />
                  </div>
                  <div className="w-24 shrink-0 text-right text-[11px] text-gray-500">{Math.round(a.rate * 100)}% · {a.sent}×</div>
                </div>
              ));
            })()}
          </div>
          <p className="mt-2 text-xs text-gray-400">The outreach agents auto-favor the highest-replying styles.</p>
        </div>
      )}

      {data.lead_categories && data.lead_categories.length > 0 && (
        <div className="card">
          <h2 className="mb-3 font-semibold">Leads — prospect categories by reply rate</h2>
          <div className="space-y-1.5">
            {(() => {
              const max = Math.max(1, ...data.lead_categories!.map((a) => a.rate));
              return data.lead_categories!.map((a) => (
                <div key={a.category} className="flex items-center gap-2">
                  <div className="w-28 shrink-0 truncate text-xs text-gray-600" title={a.category}>{a.category}</div>
                  <div className="h-4 flex-1 overflow-hidden rounded bg-gray-100">
                    <div className="h-full rounded bg-brand" style={{ width: `${Math.max(6, (a.rate / max) * 100)}%` }} />
                  </div>
                  <div className="w-24 shrink-0 text-right text-[11px] text-gray-500">{Math.round(a.rate * 100)}% · {a.sent}×</div>
                </div>
              ));
            })()}
          </div>
          <p className="mt-2 text-xs text-gray-400">The lead agents source + reach out to the converting categories first.</p>
        </div>
      )}

      <div className="card">
        <h2 className="mb-3 font-semibold">Best posting time per channel</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-6">
          {Object.entries(data.posting_times).map(([ch, t]) => (
            <div key={ch} className="rounded-lg border border-gray-200 p-2 text-center">
              <div className="text-lg">{ICON[ch] || "🌐"}</div>
              <div className="text-sm font-semibold">{fmtHour(t.hour)}</div>
              <div className="text-[10px] text-gray-400">{t.learned ? `learned · ${t.samples}×` : "default"}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><LearningsView /></AuthGate>;
}
