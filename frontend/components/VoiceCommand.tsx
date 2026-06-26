"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";

/** Hands-free voice commands. Tap the mic (or it auto-starts on tap), speak an
 * order ("source commercial leads", "find grants", "what's my status", "pause
 * everything", "open approvals"), and the workforce acts + speaks back. Uses the
 * browser's Web Speech API for speech-to-text; no keyboard needed. */
type Rec = {
  lang: string; interimResults: boolean; continuous: boolean;
  start: () => void; stop: () => void;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
  onend: (() => void) | null;
};

function speak(text: string) {
  try {
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.05;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  } catch { /* speech synthesis unsupported */ }
}

export default function VoiceCommand() {
  const router = useRouter();
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [line, setLine] = useState<string | null>(null);
  const recRef = useRef<Rec | null>(null);

  useEffect(() => {
    const W = window as unknown as { SpeechRecognition?: new () => Rec; webkitSpeechRecognition?: new () => Rec };
    const Ctor = W.SpeechRecognition || W.webkitSpeechRecognition;
    if (!Ctor || !getToken()) return;
    setSupported(true);
    const rec = new Ctor();
    rec.lang = "en-US"; rec.interimResults = false; rec.continuous = false;
    rec.onresult = (e) => {
      const text = e.results?.[0]?.[0]?.transcript || "";
      if (text) handle(text);
    };
    rec.onerror = () => setListening(false);
    rec.onend = () => setListening(false);
    recRef.current = rec;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handle(text: string) {
    setBusy(true); setLine(`“${text}”`);
    try {
      const r = await api.post<{ reply?: string; navigate?: string }>("/voice/command", { text });
      const reply = r.reply || "Done.";
      setLine(`“${text}” → ${reply}`);
      speak(reply);
      if (r.navigate) router.push(r.navigate);
    } catch (e) {
      const msg = `Sorry, that failed: ${e}`;
      setLine(msg); speak("Sorry, that failed.");
    } finally { setBusy(false); }
  }

  function toggle() {
    const rec = recRef.current;
    if (!rec) return;
    if (listening) { rec.stop(); setListening(false); return; }
    try { rec.start(); setListening(true); setLine("Listening…"); } catch { /* already started */ }
  }

  if (!supported) return null;
  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end gap-2">
      {line && (
        <div className="max-w-xs rounded-lg bg-white px-3 py-2 text-xs text-gray-700 shadow-lg ring-1 ring-gray-200">
          {busy ? "…" : ""}{line}
        </div>
      )}
      <button onClick={toggle} title="Voice command"
        className={`flex h-14 w-14 items-center justify-center rounded-full text-2xl text-white shadow-xl transition ${
          listening ? "animate-pulse bg-red-600" : "bg-brand hover:bg-brand-dark"
        }`}>
        🎙️
      </button>
    </div>
  );
}
