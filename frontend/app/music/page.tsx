"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, Expandable, PageHeader, useFetch } from "@/components/ui";

type Playlist = { id: string; name: string; curator_name: string; genre: string; followers: number; genre_match: number; submission_link: string; pitch: string | null };
type Influencer = { id: string; name: string; niche: string; handle: string; followers: number; dm_pitch: string | null; collab_pitch: string | null };
type Campaign = { id: string; title: string; content: Record<string, unknown> | null };
type Spotify = { connected: boolean; name?: string; followers?: number; popularity?: number; top_tracks?: { name: string; url: string }[] };
type Brand = {
  artist: string; category: string; identity: string; edge: string; signature: string;
  genres: string; links: string; cities: string[]; eras: string[];
  playlist_targets: string[]; content_angles: string[]; channels: string[]; not_on: string[];
};
type Release = {
  id: string; title: string; era: string | null; release_date: string | null;
  city: string | null; story: string | null; key_line: string | null;
  language: string | null; status: string;
};
type Piece = { id: string; topic: string; channel: string; title: string | null; body: string | null; hashtags: string | null; status: string };

function Music() {
  const [refresh, setRefresh] = useState(0);
  const { data: brand } = useFetch<Brand>(() => api.get<Brand>("/music/brand"));
  const { data: playlists } = useFetch<Playlist[]>(() => api.get<Playlist[]>("/music/playlists?limit=100"), [refresh]);
  const { data: influencers } = useFetch<Influencer[]>(() => api.get<Influencer[]>("/music/influencers?limit=100"), [refresh]);
  const { data: content } = useFetch<Campaign[]>(() => api.get<Campaign[]>("/music/content?limit=5"));
  const { data: spotify } = useFetch<Spotify>(() => api.get<Spotify>("/music/spotify"));
  const { data: releases } = useFetch<Release[]>(() => api.get<Release[]>("/music/releases"), [refresh]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [form, setForm] = useState({ title: "", era: "", city: "", story: "" });
  const [pieces, setPieces] = useState<Record<string, Piece[]>>({});

  async function createRelease() {
    if (!form.title.trim()) { setMsg("Add a song title first."); return; }
    setBusy("new"); setMsg("");
    try {
      await api.post("/music/releases", {
        title: form.title.trim(), era: form.era.trim() || undefined,
        city: form.city.trim() || undefined, story: form.story.trim() || undefined,
      });
      setForm({ title: "", era: "", city: "", story: "" });
      setMsg("✅ Song added — generate its kit below.");
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(String(e)); }
    finally { setBusy(null); }
  }

  async function buildKit(id: string) {
    setBusy(`kit-${id}`); setMsg("");
    try {
      const r = await api.post<{ ok: boolean; pieces?: number; key_line?: string; reason?: string }>(`/music/releases/${id}/kit`, {});
      setMsg(r.ok ? `✅ Built ${r.pieces} pieces${r.key_line ? ` · hook: "${r.key_line}"` : ""}` : `❌ ${r.reason || "failed"}`);
      setRefresh((n) => n + 1);
      if (r.ok) viewPieces(id);
    } catch (e) { setMsg(String(e)); }
    finally { setBusy(null); }
  }

  async function viewPieces(id: string) {
    if (pieces[id]) { setPieces((p) => { const c = { ...p }; delete c[id]; return c; }); return; }
    const data = await api.get<Piece[]>(`/music/releases/${id}/pieces`);
    setPieces((p) => ({ ...p, [id]: data }));
  }

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

      {brand && (
        <div className="card bg-gradient-to-br from-brand/5 to-transparent">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-lg font-semibold">🎷 {brand.artist} — <span className="text-brand-dark">{brand.category}</span></h2>
            <span className="text-xs text-gray-400">brand bible · no music on {brand.not_on.join(", ")}</span>
          </div>
          <p className="mt-1 text-sm italic text-gray-600">&ldquo;{brand.identity}&rdquo;</p>
          <div className="mt-3 grid gap-3 text-xs sm:grid-cols-2">
            <div><span className="font-semibold text-gray-700">Signature:</span> {brand.signature}</div>
            <div><span className="font-semibold text-gray-700">Sound:</span> {brand.genres}</div>
            <div className="sm:col-span-2"><span className="font-semibold text-gray-700">Story world:</span> {brand.cities.join(" · ")}</div>
            <div className="sm:col-span-2"><span className="font-semibold text-gray-700">Stream:</span> {brand.links}</div>
          </div>
          <div className="mt-3">
            <p className="mb-1 text-xs font-semibold text-gray-700">Era arc</p>
            <div className="flex flex-wrap gap-1.5">
              {brand.eras.map((e, idx) => (
                <span key={e} className="rounded-full bg-brand/10 px-2.5 py-1 text-xs text-brand-dark">{idx + 1}. {e}</span>
              ))}
            </div>
          </div>
          <div className="mt-3">
            <p className="mb-1 text-xs font-semibold text-gray-700">Playlist lanes to own</p>
            <div className="flex flex-wrap gap-1.5">
              {brand.playlist_targets.map((t) => (
                <span key={t} className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600">{t}</span>
              ))}
            </div>
          </div>
          <details className="mt-3 text-xs">
            <summary className="cursor-pointer font-semibold text-gray-700">Story angles the engine draws from ({brand.content_angles.length})</summary>
            <ul className="mt-2 list-inside list-disc space-y-0.5 text-gray-600">
              {brand.content_angles.map((a) => <li key={a}>{a}</li>)}
            </ul>
          </details>
        </div>
      )}

      {spotify?.connected ? (
        <div className="card">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">🎧 {spotify.name || "Spotify"}</h2>
            <span className="text-sm text-gray-500">{spotify.followers?.toLocaleString()} followers · popularity {spotify.popularity ?? "—"}</span>
          </div>
          {spotify.top_tracks && spotify.top_tracks.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              {spotify.top_tracks.slice(0, 6).map((t) => (
                <a key={t.url} href={t.url} target="_blank" rel="noreferrer" className="rounded bg-gray-100 px-2 py-1 hover:bg-gray-200">{t.name}</a>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="card bg-gray-50 text-sm text-gray-500">🎧 Connect Spotify in Connections to see your live follower count and top tracks.</div>
      )}

      <div className="card">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-semibold">💿 Releases — one song → a full era kit</h2>
          <span className="text-xs text-gray-400">music video · lyric video · sax / acoustic / piano · behind-the-song · TikTok hook · reels · cross-posts</span>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="Song title (e.g. Marry Me In This Lifetime)" className="rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <input value={form.era} onChange={(e) => setForm({ ...form, era: e.target.value })}
            placeholder="Era (optional)" className="rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })}
            placeholder="City / setting (Rome, Naples…)" className="rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          <input value={form.story} onChange={(e) => setForm({ ...form, story: e.target.value })}
            placeholder="The true story behind it (optional)" className="rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        <button onClick={createRelease} disabled={busy === "new"} className="btn mt-3">
          {busy === "new" ? "Adding…" : "Add song"}
        </button>

        <div className="mt-4 space-y-3">
          {(releases || []).map((r) => (
            <div key={r.id} className="rounded-lg border border-gray-200 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="font-medium">{r.title}</span>
                  {r.era && <span className="ml-2 text-xs text-gray-400">· {r.era}</span>}
                  <span className={`ml-2 badge ${r.status === "Kit Built" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>{r.status}</span>
                  {r.key_line && <p className="mt-0.5 text-xs italic text-brand-dark">&ldquo;{r.key_line}&rdquo;</p>}
                </div>
                <div className="flex gap-2">
                  <button onClick={() => buildKit(r.id)} disabled={busy === `kit-${r.id}`}
                    className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">
                    {busy === `kit-${r.id}` ? "Building…" : r.status === "Kit Built" ? "Rebuild kit" : "Generate kit"}
                  </button>
                  {r.status === "Kit Built" && (
                    <button onClick={() => viewPieces(r.id)} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">
                      {pieces[r.id] ? "Hide" : "View pieces"}
                    </button>
                  )}
                </div>
              </div>
              {pieces[r.id] && (
                <div className="mt-3 space-y-2">
                  {pieces[r.id].map((pc) => (
                    <details key={pc.id} className="rounded border border-gray-100 bg-gray-50 p-2 text-xs">
                      <summary className="cursor-pointer font-medium">
                        <span className="text-gray-400">[{pc.channel}]</span> {pc.title}
                      </summary>
                      <pre className="mt-1 whitespace-pre-wrap text-gray-600">{pc.body}</pre>
                      {pc.hashtags && <p className="mt-1 text-brand-dark">{pc.hashtags}</p>}
                    </details>
                  ))}
                </div>
              )}
            </div>
          ))}
          {releases && releases.length === 0 && (
            <p className="text-sm text-gray-400">No releases yet — add a song to spin up its full content kit.</p>
          )}
        </div>
      </div>

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
