"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";

/** "Hey Jarvis" — hands-free voice assistant. Toggle it on and it listens
 * continuously for the wake word "Jarvis", then acts on the order that follows
 * and speaks the result. Uses the browser Web Speech API (speech-to-text). No
 * keyboard needed. Respects semi-auto + Emergency Stop on the backend. */
type SpeechResult = { isFinal: boolean } & ArrayLike<{ transcript: string }>;
type Rec = {
  lang: string; interimResults: boolean; continuous: boolean; maxAlternatives: number;
  start: () => void; stop: () => void; abort: () => void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<SpeechResult> }) => void) | null;
type Rec = {
  lang: string; interimResults: boolean; continuous: boolean;
  start: () => void; stop: () => void;
  onresult: ((e: { results: ArrayLike<{ isFinal: boolean } & ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
  onend: (() => void) | null;
};

const WAKE = /\b(hey,?\s*)?jarvis\b/i;
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ").trim();
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
  const [lang, setLang] = useState<string>("en-US");
  const recRef = useRef<Rec | null>(null);
  const onRef = useRef(false);          // latest "on" for async callbacks
  const langRef = useRef("en-US");      // latest lang for the recognizer
  const armedRef = useRef(false);       // heard "Jarvis", waiting for the order
  const armTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const busyRef = useRef(false);
  const lastSpokenRef = useRef("");     // what Jarvis just said → filter the mic echo by CONTENT

  useEffect(() => { onRef.current = on; }, [on]);
  useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem("jarvis_lang") : null;
    if (saved) { setLang(saved); langRef.current = saved; }
  }, []);

  // Speak a reply (in the active language). We remember the text so the recognizer
  // can ignore its own voice bouncing back, WITHOUT going deaf to the user.
  function speak(text: string) {
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = langRef.current; u.rate = 1.05;
      lastSpokenRef.current = norm(text);
      // Stop treating it as an echo a moment after it should have finished.
      setTimeout(() => { lastSpokenRef.current = ""; }, 1500 + text.length * 60);
      window.speechSynthesis.speak(u);
    } catch { /* TTS unsupported — non-fatal */ }
  }

  function isEcho(text: string): boolean {
    const last = lastSpokenRef.current;
    if (!last) return false;
    const c = norm(text);
    return !!c && (last.includes(c) || c.includes(last));
  }

  function disarm() {
    armedRef.current = false;
    if (armTimer.current) { clearTimeout(armTimer.current); armTimer.current = null; }
  }

  function arm() {
    armedRef.current = true;
    if (armTimer.current) clearTimeout(armTimer.current);
    // If no order arrives soon, stop waiting so a later stray phrase isn't treated as a command.
    armTimer.current = setTimeout(() => {
      if (armedRef.current) { armedRef.current = false; setLine('Still here — say "Jarvis, …"'); }
    }, 12000);
  }

  function restart() {
    const rec = recRef.current;
    if (!rec || !onRef.current) return;
    try { rec.start(); }
    catch { setTimeout(() => { if (onRef.current) { try { rec.start(); } catch { /* already running */ } } }, 350); }
  }
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
    rec.lang = langRef.current; rec.interimResults = false; rec.continuous = true; rec.maxAlternatives = 1;
    rec.onresult = (e) => {
      // Only look at results NEW to this event — in continuous mode e.results is
      // cumulative, so iterating from 0 would reprocess old phrases.
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (!res || !res.isFinal) continue;
        const text = (res[0]?.transcript || "").trim();
        if (text.length < 2) continue;
        if (isEcho(text)) { lastSpokenRef.current = ""; continue; }  // our own TTS, not the user
        if (armedRef.current) {                          // wake word already heard → this is the order
          disarm();
          handle(text);
        } else if (WAKE.test(text)) {
          const after = text.replace(WAKE, "").replace(/^[\s,]+/, "").trim();
          if (after) handle(after);                      // "Jarvis, source leads" in one breath
          else {
            arm();
            setLine(langRef.current.startsWith("pt") ? "Sim? Estou ouvindo…" : "Yes? I'm listening…");
            speak(langRef.current.startsWith("pt") ? "Sim?" : "Yes?");
          }
        }
        // No wake word and not armed → ambient speech, ignored.
      }
    };
    rec.onerror = (ev) => {
      // Most errors ("no-speech"/"aborted"/"audio-capture"/"network") are transient;
      // onend fires next and we restart. Only a hard permission block stops us.
      if (ev?.error === "not-allowed" || ev?.error === "service-not-allowed") {
        onRef.current = false; setOn(false);
        setLine("Microphone blocked — allow mic access (and use Chrome/Edge over HTTPS).");
      }
    };
    rec.onend = () => { restart(); };  // keep listening continuously
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

  const PT = () => langRef.current.startsWith("pt");

  function toggle() {
    const rec = recRef.current;
    if (!rec) return;
    if (on) {
      setOn(false); onRef.current = false; disarm();
      setOn(false); onRef.current = false; armedRef.current = false;
      try { rec.stop(); } catch { /* */ }
      setLine(null);
    } else {
      setOn(true); onRef.current = true;
      restart();
      setLine(PT() ? "Jarvis está ouvindo… diga “Jarvis, …”" : 'Hey Jarvis is listening… say “Jarvis, …”');
      speak(PT() ? "Jarvis online." : "Jarvis online.");
    }
  }

  // Switch the recognition language (English ⇄ Portuguese) for bilingual use.
  function toggleLang() {
    const next = langRef.current.startsWith("pt") ? "en-US" : "pt-BR";
    langRef.current = next; setLang(next);
    try { localStorage.setItem("jarvis_lang", next); } catch { /* */ }
    const rec = recRef.current;
    if (rec) {
      rec.lang = next;
      if (onRef.current) { try { rec.abort(); } catch { /* */ } /* onend → restart with new lang */ }
    }
    setLine(next.startsWith("pt") ? "Idioma: Português 🇧🇷" : "Language: English 🇺🇸");
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
      <div className="flex items-center gap-2">
        <button onClick={toggleLang} title="Switch language (English / Português)"
          className="rounded-full bg-white px-3 py-3 text-sm font-semibold text-gray-700 shadow-xl ring-1 ring-gray-200 hover:bg-gray-50">
          {lang.startsWith("pt") ? "🇧🇷 PT" : "🇺🇸 EN"}
        </button>
        <button onClick={toggle} title='Toggle "Hey Jarvis"'
          className={`flex items-center gap-2 rounded-full px-4 py-3 text-sm font-semibold text-white shadow-xl transition ${
            on ? "animate-pulse bg-red-600" : "bg-brand hover:bg-brand-dark"
          }`}>
          🎙️ {on ? "Jarvis on" : "Hey Jarvis"}
        </button>
      </div>
      <button onClick={toggle} title='Toggle "Hey Jarvis"'
        className={`flex items-center gap-2 rounded-full px-4 py-3 text-sm font-semibold text-white shadow-xl transition ${
          on ? "animate-pulse bg-red-600" : "bg-brand hover:bg-brand-dark"
        }`}>
        🎙️ {on ? "Jarvis on" : "Hey Jarvis"}
      </button>
    </div>
  );
}
