"use client";

import { api } from "@/lib/api";
import { AuthGate, PageHeader, KpiCard, useFetch, LoadState } from "@/components/ui";

type PlatformRow = {
  platform: string;
  connected: boolean;
  followers: number | null;
  follower_delta: number | null;
  per_day_target: number;
  auto_publish: boolean;
  published_14d: number;
  published_total: number;
  avg_engagement: number;
  top_category: string | null;
  best_hour: number | null;
  best_hour_learned: boolean;
};
type TopContent = {
  topic: string;
  channel: string;
  business: string;
  engagement: number;
};
type Growth = {
  kpis: Record<string, number>;
  platforms: PlatformRow[];
  follower_series: Record<string, { date: string | null; followers: number }[]>;
  by_category: Record<string, number>;
  top_content: TopContent[];
};

const ICON: Record<string, string> = {
  linkedin: "💼", instagram: "📸", facebook: "👍", x: "✖️", tiktok: "🎵", youtube: "▶️",
};

function fmtHour(h: number | null): string {
  if (h === null || h === undefined) return "—";
  const am = h < 12;
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}${am ? "am" : "pm"}`;
}

function Delta({ n }: { n: number | null }) {
  if (n === null) return <span className="text-gray-400">—</span>;
  if (n === 0) return <span className="text-gray-500">±0</span>;
  const up = n > 0;
  return <span className={up ? "text-green-600" : "text-red-600"}>{up ? "▲" : "▼"} {Math.abs(n)}</span>;
}

function Sparkline({ points }: { points: { followers: number }[] }) {
  if (!points || points.length < 2) return <div className="h-8 text-xs text-gray-300">no trend yet</div>;
  const ys = points.map((p) => p.followers);
  const min = Math.min(...ys), max = Math.max(...ys), span = Math.max(1, max - min);
  const w = 120, h = 32;
  const d = points
    .map((p, i) => `${(i / (points.length - 1)) * w},${h - ((p.followers - min) / span) * h}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline points={d} fill="none" stroke="currentColor" strokeWidth={1.5} className="text-brand" />
    </svg>
  );
}

function GrowthView() {
  const { data, loading, error, reload } = useFetch<Growth>(() => api.get<Growth>("/analytics/growth"));
  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;
  const k = data.kpis;
  const cats = Object.entries(data.by_category).sort((a, b) => b[1] - a[1]);
  const maxCat = Math.max(1, ...cats.map(([, v]) => v));

  return (
    <div className="space-y-8">
      <PageHeader title="Growth Analytics" subtitle="What the media engine is producing, and how every platform is performing" />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="Total followers" value={k.total_followers} />
        <KpiCard label="Connected platforms" value={k.connected_platforms} hint={`of ${data.platforms.length}`} />
        <KpiCard label="Published (14d)" value={k.published_14d} />
        <KpiCard label="Daily cadence target" value={k.daily_target} hint="pieces/day across platforms" />
      </div>

      <div className="card overflow-x-auto">
        <h2 className="mb-3 font-semibold">Per-platform performance</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500">
              <th className="py-2">Platform</th>
              <th>Followers</th>
              <th>30d</th>
              <th>Trend</th>
              <th>Cadence</th>
              <th>Best time</th>
              <th>Published</th>
              <th>Avg engagement</th>
              <th>Top category</th>
              <th>Mode</th>
            </tr>
          </thead>
          <tbody>
            {data.platforms.map((p) => (
              <tr key={p.platform} className="border-t">
                <td className="py-2 font-medium capitalize">
                  <span className="mr-1">{ICON[p.platform] || "🌐"}</span>{p.platform}
                  {!p.connected && <span className="ml-2 rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">not connected</span>}
                </td>
                <td>{p.followers ?? "—"}</td>
                <td><Delta n={p.follower_delta} /></td>
                <td className="text-brand"><Sparkline points={data.follower_series[p.platform] || []} /></td>
                <td>{p.per_day_target}/day</td>
                <td title={p.best_hour_learned ? "learned from engagement" : "default — not enough data yet"}>
                  {fmtHour(p.best_hour)}
                  {p.best_hour_learned
                    ? <span className="ml-1 text-[10px] text-green-600">learned</span>
                    : <span className="ml-1 text-[10px] text-gray-400">default</span>}
                </td>
                <td>{p.published_14d} <span className="text-gray-400">/ {p.published_total}</span></td>
                <td>{p.avg_engagement}</td>
                <td className="text-gray-600">{p.top_category || "—"}</td>
                <td>
                  <span className={`rounded px-1.5 py-0.5 text-[10px] ${p.auto_publish ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
                    {p.auto_publish ? "auto" : "assist"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="card">
          <h2 className="mb-3 font-semibold">Engagement by category</h2>
          {cats.length === 0 ? (
            <p className="text-sm text-gray-400">No engagement data yet — metrics fill in once content is published and synced.</p>
          ) : (
            <div className="space-y-2">
              {cats.map(([c, v]) => (
                <div key={c} className="flex items-center gap-3">
                  <div className="w-28 shrink-0 text-sm capitalize text-gray-600">{c}</div>
                  <div className="h-5 flex-1 overflow-hidden rounded bg-gray-100">
                    <div className="flex h-full items-center justify-end rounded bg-brand px-2 text-xs font-medium text-white"
                         style={{ width: `${Math.max(8, (v / maxCat) * 100)}%` }}>{v}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <h2 className="mb-3 font-semibold">Top performing content</h2>
          {data.top_content.length === 0 ? (
            <p className="text-sm text-gray-400">No published content with metrics yet.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {data.top_content.map((t, i) => (
                <li key={i} className="flex items-center justify-between gap-3 border-b pb-2">
                  <span className="truncate">
                    <span className="mr-1">{ICON[t.channel] || "🌐"}</span>
                    {t.topic} <span className="text-gray-400">· {t.business}</span>
                  </span>
                  <span className="shrink-0 font-medium text-brand">{t.engagement}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><GrowthView /></AuthGate>;
}
