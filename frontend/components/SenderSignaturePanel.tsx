"use client";
import { useEffect, useState } from "react";
import { api, API_URL, getToken } from "@/lib/api";

export type SignatureProfile = { configured: boolean; mailbox?: string; plain_text?: string; source_ref?: string; digest?: string };
export default function SenderSignaturePanel({ onChange }: { onChange: (profile: SignatureProfile) => void }) {
  const [profile, setProfile] = useState<SignatureProfile>({configured: false});
  const [image, setImage] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const [mailbox, setMailbox] = useState(""); const [text, setText] = useState(""); const [source, setSource] = useState("");
  const [file, setFile] = useState<File | null>(null);
  useEffect(() => { api.get<SignatureProfile>("/sender-signature").then(p => {
    setProfile(p); onChange(p); setMailbox(p.mailbox || ""); setText(p.plain_text || ""); setSource(p.source_ref || "");
  }).catch(e => setError(String(e))); }, [onChange]);
  useEffect(() => {
    if (!profile.configured) return;
    let active = true; let url = "";
    fetch(`${API_URL}/sender-signature/image`, {headers: {Authorization: `Bearer ${getToken()}`}})
      .then(r => { if (!r.ok) throw new Error("Signature preview unavailable"); return r.blob(); })
      .then(blob => { if (active) { url = URL.createObjectURL(blob); setImage(url); } }).catch(e => { if (active) setError(String(e)); });
    return () => { active = false; if (url) URL.revokeObjectURL(url); };
  }, [profile.digest, profile.configured]);
  return <section className="card space-y-3">
    <h2 className="font-semibold">Your sender signature</h2>
    <p>This signature belongs to your signed-in profile. It is added only when you select it for a draft, and is never applied to other users.</p>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {image && <img src={image} alt={profile.plain_text || "Your approved signature"} width={600} style={{maxWidth: "100%", height: "auto"}} />}
    <form className="space-y-2" onSubmit={async e => { e.preventDefault(); setBusy(true); setError("");
      try {
        if (!file) throw new Error("Select the approved PNG");
        const body = new FormData(); body.append("file", file); body.append("mailbox", mailbox); body.append("plain_text", text); body.append("source_ref", source);
        const result = await fetch(`${API_URL}/sender-signature`, {method: "PUT", body, headers: {Authorization: `Bearer ${getToken()}`}});
        if (!result.ok) throw new Error(await result.text()); const p = await result.json(); setProfile(p); onChange(p);
      } catch (e) { setError(String(e)); } finally { setBusy(false); }
    }}>
      <label className="block">Approved signature PNG (up to 2 MB) <input required type="file" accept="image/png" onChange={e => setFile(e.target.files?.[0] || null)} /></label>
      <label className="block">Your sender mailbox <input required type="email" className="border rounded p-2 w-full" value={mailbox} onChange={e => setMailbox(e.target.value)} /></label>
      <label className="block">Matching signature text (for accessibility and plain-text email) <textarea required maxLength={2000} className="border rounded p-2 w-full" value={text} onChange={e => setText(e.target.value)} /></label>
      <label className="block">Approved source reference <input required className="border rounded p-2 w-full" value={source} onChange={e => setSource(e.target.value)} /></label>
      <button disabled={busy} className="btn-primary">Save to my sender profile</button>
    </form>
    <p className="text-sm">Images are embedded in email drafts; no public image-hosting URL or tracking pixel is added. Saving this profile does not install a Gmail signature or enable sending.</p>
  </section>;
}
