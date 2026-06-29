"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, API_URL } from "@/lib/api";

/** "Hey Jennifer" — hands-free voice assistant. Toggle it on and it listens
 * continuously for the wake word "Jennifer", then acts on the order that follows
 * and speaks the result in a warm, sultry female voice. Uses the browser Web
 * Speech API (speech-to-text + text-to-speech). No keyboard needed. Respects
 * semi-auto + Emergency Stop on the backend. */
type SpeechResult = { isFinal: boolean } & ArrayLike<{ transcript: string }>;
type Rec = {
  lang: string; interimResults: boolean; continuous: boolean; maxAlternatives: number;
  start: () => void; stop: () => void; abort: () => void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<SpeechResult> }) => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
  onend: (() => void) | null;
};

// Wake on "Jennifer" (primary) — keep "Jarvis" as a fallback alias so old habits
// still work. Speech-to-text often mishears the name, so accept close variants.
const WAKE = /\b(hey,?\s*)?(jennifer|jenifer|jennefer|jen|jenny|jarvis)\b/i;
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ").trim();

// Pick the most natural-sounding female voice the browser offers, matching the
// active language. We prefer known-good female voices, then anything tagged
// "female", then any voice for the language. The voice list loads async, so we
// re-resolve lazily on each utterance.
const FEMALE_HINTS = [
  "samantha", "victoria", "karen", "moira", "tessa", "fiona", "serena", "allison",
  "ava", "susan", "zira", "jenny", "aria", "sonia", "luciana", "google uk english female",
  "google português do brasil", "female", "mulher", "feminin",
];
function pickVoice(lang: string): SpeechSynthesisVoice | null {
  try {
    const voices = window.speechSynthesis.getVoices() || [];
    if (!voices.length) return null;
    const base = lang.slice(0, 2).toLowerCase();
    const forLang = voices.filter((v) => v.lang?.toLowerCase().startsWith(base));
    const pool = forLang.length ? forLang : voices;
    for (const hint of FEMALE_HINTS) {
      const hit = pool.find((v) => v.name.toLowerCase().includes(hint));
      if (hit) return hit;
    }
    return pool[0] || null;
  } catch {
    return null;
  }
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
    // Warm up the TTS voice list — Chrome loads it asynchronously, so trigger it
    // now and again on the voiceschanged event so a female voice is ready.
    try {
      window.speechSynthesis?.getVoices();
      if (window.speechSynthesis) window.speechSynthesis.onvoiceschanged = () => { window.speechSynthesis.getVoices(); };
    } catch { /* TTS unsupported — non-fatal */ }
  }, []);

  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Speak a reply. Prefer Jennifer's real neural voice (server-side TTS); fall
  // back to the browser's built-in voice if that's unavailable (offline / no key).
  // We remember the text so the recognizer can ignore its own voice bouncing back.
  function speak(text: string) {
    lastSpokenRef.current = norm(text);
    setTimeout(() => { lastSpokenRef.current = ""; }, 2500 + text.length * 70);
    void speakNeural(text);
  }

  async function speakNeural(text: string) {
    try {
      const token = getToken();
      const res = await fetch(`${API_URL}/voice/say`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ text }),
      });
      if (res.status === 200) {
        const blob = await res.blob();
        if (blob.size > 0) {
          try { window.speechSynthesis.cancel(); } catch { /* */ }
          const url = URL.createObjectURL(blob);
          if (audioRef.current) { try { audioRef.current.pause(); } catch { /* */ } }
          const a = new Audio(url);
          audioRef.current = a;
          a.onended = () => URL.revokeObjectURL(url);
          await a.play();
          return;  // neural voice played — done
        }
      }
    } catch { /* fall through to browser TTS */ }
    speakBrowser(text);
  }

  function speakBrowser(text: string) {
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = langRef.current;
      // Seductive delivery on the built-in voice: pick a real female voice and
      // drop the pitch/rate for a lower, breathier register.
      const v = pickVoice(langRef.current);
      if (v) u.voice = v;
      u.rate = 0.88;
      u.pitch = 0.8;
      u.volume = 1;
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
      if (armedRef.current) { armedRef.current = false; setLine('Still here — say "Jennifer, …"'); }
    }, 12000);
  }

  function restart() {
    const rec = recRef.current;
    if (!rec || !onRef.current) return;
    try { rec.start(); }
    catch { setTimeout(() => { if (onRef.current) { try { rec.start(); } catch { /* already running */ } } }, 350); }
  }

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
            setLine(langRef.current.startsWith("pt") ? "Sim, amor? Estou ouvindo…" : "Yes, darling? I'm listening…");
            speak(langRef.current.startsWith("pt") ? "Sim, amor?" : "Yes, darling?");
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
      try { rec.stop(); } catch { /* */ }
      setLine(null);
    } else {
      setOn(true); onRef.current = true;
      restart();
      setLine(PT() ? "Jennifer está ouvindo… diga “Jennifer, …”" : 'Jennifer is listening… say “Jennifer, …”');
      speak(PT() ? "Jennifer online, amor." : "Jennifer here. I'm all yours.");
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
        <button onClick={toggle} title='Toggle "Hey Jennifer"'
          className={`flex items-center gap-2 rounded-full px-4 py-3 text-sm font-semibold text-white shadow-xl transition ${
            on ? "animate-pulse bg-red-600" : "bg-brand hover:bg-brand-dark"
          }`}>
          🎙️ {on ? "Jennifer on" : "Hey Jennifer"}
        </button>
      </div>
    </div>
  );
}
