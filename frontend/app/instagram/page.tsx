"use client";

import { api } from "@/lib/api";
import { AuthGate, Expandable, PageHeader, useFetch } from "@/components/ui";

type Target = { id: string; handle: string; niche: string; category: string; followers: number; comment_idea: string | null; dm_opener: string | null; story_reply: string | null };
type Campaign = { id: string; title: string; content: { calendar?: { day: string; pillar: string; idea: string; caption: string }[] } | null };

function Instagram() {
  const { data: targets } = useFetch<Target[]>(() => api.get<Target[]>("/instagram/targets?limit=200"));
  const { data: calendars } = useFetch<Campaign[]>(() => api.get<Campaign[]>("/instagram/calendar?limit=1"));
  const calendar = calendars?.[0]?.content?.calendar;

  return (
    <div className="space-y-8">
      <PageHeader title="Instagram Planner" subtitle="Daily target accounts and weekly content calendar" />

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
