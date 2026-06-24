"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { AuthGate, Expandable, PageHeader, useFetch } from "@/components/ui";

type Target = { id: string; handle: string; niche: string; category: string; followers: number; comment_idea: string | null; dm_opener: string | null; story_reply: string | null };
type Campaign = { id: string; title: string; content: { calendar?: { day: string; pillar: string; idea: string; caption: string }[] } | null };
type Media = { caption: string | null; permalink: string; likes: number | null; comments: number | null; media_url: string | null };
type Account = {
  connected: boolean; error?: string;
  account?: { username: string; followers: number; follows: number; media_count: number; biography: string; profile_picture_url: string };
  insights?: { reach?: number; profile_views?: number; accounts_engaged?: number } | null;
  recent_media?: Media[];
};

function Instagram() {
  const { data: acct } = useFetch<Account>(() => api.get<Account>("/instagram/account"));
  const { data: targets } = useFetch<Target[]>(() => api.get<Target[]>("/instagram/targets?limit=200"));
  const { data: calendars } = useFetch<Campaign[]>(() => api.get<Campaign[]>("/instagram/calendar?limit=1"));
  const calendar = calendars?.[0]?.content?.calendar;

  return (
    <div className="space-y-8">
      <PageHeader title="Instagram Planner" subtitle="Live account + daily targets and weekly content calendar" />

      {acct && !acct.connected && (
        <div className="card bg-amber-50">
          <p className="text-sm text-amber-800">
            📸 Instagram isn&apos;t connected yet. <Link href="/connections" className="font-semibold underline">Connect your account</Link> to see live followers, reach, and recent posts here.
          </p>
        </div>
      )}
      {acct?.connected && acct.account && (
        <div className="card">
          <div className="flex items-center gap-4">
            {acct.account.profile_picture_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={acct.account.profile_picture_url} alt="" className="h-14 w-14 rounded-full" />
            )}
            <div>
              <div className="font-semibold">@{acct.account.username}</div>
              <div className="text-xs text-gray-500">{acct.account.biography}</div>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-5">
            {[["Followers", acct.account.followers], ["Following", acct.account.follows],
              ["Posts", acct.account.media_count], ["Reach (24h)", acct.insights?.reach],
              ["Profile views", acct.insights?.profile_views]].map(([label, val]) => (
              <div key={label as string}>
                <div className="text-lg font-bold">{val != null ? Number(val).toLocaleString() : "—"}</div>
                <div className="text-[10px] uppercase text-gray-400">{label}</div>
              </div>
            ))}
          </div>
          {acct.recent_media && acct.recent_media.length > 0 && (
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {acct.recent_media.map((m, i) => (
                <a key={i} href={m.permalink} target="_blank" rel="noreferrer" className="rounded border p-2 text-xs hover:bg-gray-50">
                  <div className="line-clamp-2 text-gray-600">{m.caption || "(no caption)"}</div>
                  <div className="mt-1 text-gray-400">❤ {m.likes ?? 0} · 💬 {m.comments ?? 0}</div>
                </a>
              ))}
            </div>
          )}
        </div>
      )}

      {calendar && (
        <div>
          <h2 className="mb-3 text-lg font-semibold">Weekly content calendar</h2>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {calendar.map((d, idx) => (
              <div key={idx} className="card">
                <div className="flex items-center justify-between">
                  <span className="font-semibold">{d.day}</span>
                  <span className="badge bg-brand/10 text-brand-dark">{d.pillar}</span>
                </div>
                <p className="mt-2 text-sm">{d.idea}</p>
                <p className="mt-1 text-xs text-gray-400">{d.caption}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <h2 className="mb-3 text-lg font-semibold">Target accounts</h2>
        <div className="card overflow-x-auto">
          <table className="w-full">
            <thead><tr><th className="th">Handle</th><th className="th">Niche</th><th className="th">Category</th><th className="th">Followers</th><th className="th">Engagement</th></tr></thead>
            <tbody>
              {(targets || []).map((t) => (
                <tr key={t.id} className="border-t border-gray-100">
                  <td className="td font-medium">@{t.handle}</td>
                  <td className="td">{t.niche}</td>
                  <td className="td"><span className="badge bg-gray-100 text-gray-700">{t.category}</span></td>
                  <td className="td">{t.followers?.toLocaleString()}</td>
                  <td className="td space-y-1">
                    <Expandable label="Comment" text={t.comment_idea} />
                    <Expandable label="DM opener" text={t.dm_opener} />
                    <Expandable label="Story reply" text={t.story_reply} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Instagram /></AuthGate>;
}
