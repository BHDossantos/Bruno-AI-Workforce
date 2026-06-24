"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, Expandable, PageHeader, useFetch } from "@/components/ui";

type Playlist = { id: string; name: string; curator_name: string; genre: string; followers: number; genre_match: number; submission_link: string; pitch: string | null };
type Influencer = { id: string; name: string; niche: string; handle: string; followers: number; dm_pitch: string | null; collab_pitch: string | null };
type Campaign = { id: string; title: string; content: Record<string, unknown> | null };

function Music() {
  const [refresh, setRefresh] = useState(0);
  const { data: playlists } = useFetch<Playlist[]>(() => api.get<Playlist[]>("/music/playlists?limit=100"), [refresh]);
  const { data: influencers } = useFetch<Influencer[]>(() => api.get<Influencer[]>("/music/influencers?limit=100"), [refresh]);
  const { data: content } = useFetch<Campaign[]>(() => api.get<Campaign[]>("/music/content?limit=5"));
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  async function send(path: string, id: string) {
    setBusy(id); setMsg("");
    try {
      const r = await api.post<{ ok: boolean; status?: string; reason?: string }>(path, {});
      setMsg(r.ok ? `✅ Pitch ${r.status?.toLowerCase() || "queued"}` : `❌ ${r.reason || "failed"}`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(String(e)); }
    finally { setBusy(null); }
  }

  return (
    <div className="space-y-8">
      <PageHeader title="Music Campaigns" subtitle="Playlists, influencers, and daily content package" />
      {msg && <p className="text-sm text-gray-600">{msg}</p>}

      {content && content[0]?.content && (
        <div className="card">
          <h2 className="mb-2 font-semibold">Today&apos;s content package</h2>
          <pre className="whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs">{JSON.stringify(content[0].content, null, 2)}</pre>
        </div>
      )}

      <div>
        <h2 className="mb-3 text-lg font-semibold">Playlists</h2>
        <div className="card overflow-x-auto">
          <table className="w-full">
            <thead><tr><th className="th">Match</th><th className="th">Playlist</th><th className="th">Genre</th><th className="th">Curator</th><th className="th">Followers</th><th className="th">Pitch</th><th className="th">Action</th></tr></thead>
            <tbody>
              {(playlists || []).map((p) => (
                <tr key={p.id} className="border-t border-gray-100">
                  <td className="td"><span className="badge bg-brand/10 text-brand-dark">{p.genre_match}</span></td>
                  <td className="td font-medium"><a href={p.submission_link} target="_blank" className="hover:underline">{p.name}</a></td>
                  <td className="td">{p.genre}</td>
                  <td className="td">{p.curator_name}</td>
                  <td className="td">{p.followers?.toLocaleString()}</td>
                  <td className="td"><Expandable label="Pitch" text={p.pitch} /></td>
                  <td className="td">
                    <button onClick={() => send(`/music/playlists/${p.id}/send`, p.id)} disabled={busy === p.id}
                      className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">
                      {busy === p.id ? "Sending…" : "Pitch"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold">Influencers</h2>
        <div className="card overflow-x-auto">
          <table className="w-full">
            <thead><tr><th className="th">Name</th><th className="th">Niche</th><th className="th">Handle</th><th className="th">Followers</th><th className="th">Outreach</th><th className="th">Action</th></tr></thead>
            <tbody>
              {(influencers || []).map((i) => (
                <tr key={i.id} className="border-t border-gray-100">
                  <td className="td font-medium">{i.name}</td>
                  <td className="td">{i.niche}</td>
                  <td className="td">@{i.handle}</td>
                  <td className="td">{i.followers?.toLocaleString()}</td>
                  <td className="td space-y-1">
                    <Expandable label="DM pitch" text={i.dm_pitch} />
                    <Expandable label="Collab pitch" text={i.collab_pitch} />
                  </td>
                  <td className="td">
                    <button onClick={() => send(`/music/influencers/${i.id}/send`, i.id)} disabled={busy === i.id}
                      className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">
                      {busy === i.id ? "Sending…" : "Pitch"}
                    </button>
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
  return <AuthGate><Music /></AuthGate>;
}
