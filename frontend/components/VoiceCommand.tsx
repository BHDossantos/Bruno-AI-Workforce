"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";

/** "Hey Jarvis" — hands-free voice assistant. Toggle it on and it listens
 * continuously for the wake word "Jarvis", then acts on the order that follows
 * and speaks the result. Uses the browser Web Speech API (speech-to-text). No
 * keyboard needed. Respects semi-auto + Emergency Stop on the backend. */
type Rec = {
  lang: string; interimResults: boolean; continuous: boolean;
  start: () => void; stop: () => void;
  onresult: ((e: { results: ArrayLike<{ isFinal: boolean } & ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
  onend: (() => void) | null;
};

const WAKE = /\b(hey )?jarvis\b/i;

function speak(text: string) {
  try {
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.05;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  } catch { /* unsupported */ }
}

export default function VoiceCommand() {
  const router = useRouter();
  const [supported, setSupported] = useState(false);
  const [on, setOn] = useState(false);
  const [line, setLine] = useState<string | null>(null);
  const recRef = useRef<Rec | null>(null);
  const onRef = useRef(false);          // latest "on" for async callbacks
  const armedRef = useRef(false);       // heard "Jarvis", waiting for the order
  const busyRef = useRef(false);

  useEffect(() => { onRef.current = on; }, [on]);

  useEffect(() => {
    const W = window as unknown as { SpeechRecognition?: new () => Rec; webkitSpeechRecognition?: new () => Rec };
    const Ctor = W.SpeechRecognition || W.webkitSpeechRecognition;
    if (!Ctor || !getToken()) return;
    setSupported(true);
    const rec = new Ctor();
    rec.lang = "en-US"; rec.interimResults = false; rec.continuous = true;
    rec.onresult = (e) => {
      for (let i = 0; i < e.results.length; i++) {
        const res = e.results[i];
        if (!res.isFinal) continue;
        const text = (res[0]?.transcript || "").trim();
        if (!text) continue;
        if (armedRef.current) {            // wake word already heard → this is the order
          armedRef.current = false;
          handle(text);
        } else if (WAKE.test(text)) {
          const after = text.replace(WAKE, "").replace(/^[\s,]+/, "").trim();
          if (after) handle(after);
          else { armedRef.current = true; setLine("Yes?"); speak("Yes?"); }
        }
      }
    };
    rec.onerror = () => { /* keep going; onend will restart */ };
    rec.onend = () => { if (onRef.current) { try { rec.start(); } catch { /* already */ } } };
    recRef.current = rec;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handle(text: string) {
    if (busyRef.current) return;
    busyRef.current = true;
    setLine(`“${text}”…`);
    try {
      const r = await api.post<{ reply?: string; navigate?: string }>("/voice/command", { text });
      const reply = r.reply || "Done.";
      setLine(`“${text}” → ${reply}`);
      speak(reply);
      if (r.navigate) router.push(r.navigate);
    } catch (e) {
      setLine(`Sorry, that failed: ${e}`); speak("Sorry, that failed.");
    } finally { busyRef.current = false; }
  }

  function toggle() {
    const rec = recRef.current;
    if (!rec) return;
    if (on) {
      setOn(false); onRef.current = false; armedRef.current = false;
      try { rec.stop(); } catch { /* */ }
      setLine(null);
    } else {
      setOn(true); onRef.current = true;
      try { rec.start(); } catch { /* already */ }
      setLine("Hey Jarvis is listening… say “Jarvis, …”");
      speak("Jarvis online.");
    }
  }

  if (!supported) return null;
  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end gap-2">
      {line && (
        <div className="max-w-xs rounded-lg bg-white px-3 py-2 text-xs text-gray-700 shadow-lg ring-1 ring-gray-200">
          {line}
        </div>
      )}
      <button onClick={toggle} title='Toggle "Hey Jarvis"'
        className={`flex items-center gap-2 rounded-full px-4 py-3 text-sm font-semibold text-white shadow-xl transition ${
          on ? "animate-pulse bg-red-600" : "bg-brand hover:bg-brand-dark"
        }`}>
        🎙️ {on ? "Jarvis on" : "Hey Jarvis"}
      </button>
    </div>
  );
}
