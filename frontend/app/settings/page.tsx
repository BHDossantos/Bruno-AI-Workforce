"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

type Profile = {
  business_name?: string; niche?: string; location?: string; audience?: string;
  value_prop?: string; website?: string; tone?: string; instagram_handle?: string;
  content_pillars?: string; music_artist?: string; music_genres?: string;
  music_links?: string;
};

const FIELDS: { key: keyof Profile; label: string; hint?: string; area?: boolean }[] = [
  { key: "business_name", label: "Business / brand name" },
  { key: "niche", label: "What you do / niche" },
  { key: "location", label: "Location(s)" },
  { key: "audience", label: "Target audience" },
  { key: "value_prop", label: "Offer / value proposition", area: true },
  { key: "tone", label: "Brand voice / tone", hint: "e.g. warm, confident, concise" },
  { key: "website", label: "Website" },
  { key: "instagram_handle", label: "Instagram handle", hint: "without the @" },
  { key: "content_pillars", label: "Content pillars (comma-separated)", area: true,
    hint: "themes the Instagram calendar rotates through" },
  { key: "music_artist", label: "Music artist name", hint: "stage name (e.g. Bruno D)" },
  { key: "music_genres", label: "Music genre / category",
    hint: "own a lane — e.g. Luxury Latin Soul: romantic R&B with alto sax" },
  { key: "music_links", label: "Streaming / follow links", area: true,
    hint: "Spotify, Apple Music, YouTube Music, Pandora — every music post drives fans here" },
];

function Settings() {
  const [p, setP] = useState<Profile>({});
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.get<Profile>("/profile").then(setP).catch(() => {}); }, []);

  async function save() {
    setBusy(true); setSaved(false);
    try { await api.put("/profile", p); setSaved(true); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <PageHeader title="Brand Profile"
        subtitle="This tailors everything the agents create — Instagram calendar, music content, and outreach tone — to your account." />
      <div className="card max-w-2xl space-y-4">
        {FIELDS.map((f) => (
          <div key={f.key}>
            <label className="text-sm font-medium text-gray-700">{f.label}</label>
            {f.area ? (
              <textarea rows={2} value={p[f.key] || ""}
                onChange={(e) => setP({ ...p, [f.key]: e.target.value })}
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            ) : (
              <input value={p[f.key] || ""}
                onChange={(e) => setP({ ...p, [f.key]: e.target.value })}
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            )}
            {f.hint && <p className="mt-1 text-xs text-gray-400">{f.hint}</p>}
          </div>
        ))}
        <div className="flex items-center gap-3">
          <button className="btn" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
          {saved && <span className="text-sm text-green-600">✅ Saved — next agent run uses this.</span>}
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Settings /></AuthGate>;
}
