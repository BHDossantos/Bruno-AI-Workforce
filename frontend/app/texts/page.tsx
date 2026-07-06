"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type Thread = { phone: string; name: string | null; count: number; last_at: string | null; last_body: string | null; last_direction: string | null };
type Msg = { direction: string; body: string; status: string; at: string | null };
type ThreadDetail = { phone: string; name: string | null; messages: Msg[] };

function Texts() {
  const [active, setActive] = useState<string | null>(null);
  const [account, setAccount] = useState("personal");
  const [draft, setDraft] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [newPhone, setNewPhone] = useState("");
  const [sendMsg, setSendMsg] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const { data: setup } = useFetch<{ sms?: { configured: boolean; via: string | null; daily_cap?: number; window_start?: number; window_end?: number; timezone?: string } }>(
    () => api.get("/setup"), []);
  const smsReady = setup?.sms?.configured ?? true;  // assume ok until we know
  const win = setup?.sms;
  const hours = win?.window_start != null && win?.window_end != null
    ? `${win.window_start}am–${win.window_end - 12}pm` : "8am–9pm";
  const { data: threads, loading, error, reload } = useFetch<Thread[]>(() => api.get<Thread[]>("/sms/threads"), [refresh]);
  const { data: detail } = useFetch<ThreadDetail | null>(
    () => (active ? api.get<ThreadDetail>(`/sms/thread?phone=${encodeURIComponent(active)}`) : Promise.resolve(null)),
    [active, refresh]
  );
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView(); }, [detail]);

  async function send() {
    if (!active || !draft.trim()) return;
    const body = draft;
    setDraft(""); setSendMsg(null);
    try {
      const r = await api.post<{ ok?: boolean; reason?: string }>("/sms/send", { to: active, message: body, account });
      if (r.ok === false) {
        setSendMsg(`❌ Not sent — ${r.reason || "SMS isn't connected. Add Twilio in Connect Email & Data, or set up the Mac bridge."}`);
      }
    } catch (e) { setSendMsg(`❌ ${e}`); }
    setRefresh((r) => r + 1);
  }

  async function sendNext(limit: number) {
    setBulkBusy(true);
    setSendMsg(`Sending the next ${limit} drafted texts…`);
    try {
      const r = await api.post<{ sent: number; failed: number; blocked: number; considered: number; reasons: string[] }>(
        "/sms/send-drafts", { limit });
      setSendMsg(
        `✅ Sent ${r.sent} · ${r.failed} failed · ${r.blocked} held (of ${r.considered} drafts)` +
        (r.reasons?.length ? ` — ${r.reasons.join(" | ")}` : "")
      );
      setRefresh((x) => x + 1);
    } catch (e) {
      setSendMsg(`❌ ${e}`);
    } finally {
      setBulkBusy(false);
    }
  }

  function startNew() {
    const phone = newPhone.trim();
    if (!/^\+?\d{10,15}$/.test(phone.replace(/[\s()-]/g, ""))) {
      alert("Enter a valid phone number in E.164 form, e.g. +16175551234");
      return;
    }
    setActive(phone.startsWith("+") ? phone : `+${phone}`);
    setNewPhone("");
  }

  return (
    <div>
      <PageHeader
        title="Texts"
        subtitle="Two-way SMS — start a new text or reply to warm leads here"
        action={
          <button className="btn" disabled={bulkBusy} onClick={() => sendNext(20)}>
            {bulkBusy ? "Sending…" : "Send next 20"}
          </button>
        }
      />
      <p className="mb-3 text-xs text-gray-500">“Send next 20” sends your oldest drafted texts (e.g. the EverQuote batch). Opt-outs, texting hours ({hours}{win?.timezone ? "" : " ET"}){win?.daily_cap ? `, and the daily cap of ${win.daily_cap}` : ", and the daily cap"} are enforced automatically — anything held shows the reason.</p>
      {!smsReady && (
        <div className="mb-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          ⚠️ SMS isn&apos;t connected yet — messages won&apos;t actually send. Add Twilio in <b>Connect Email &amp; Data</b> (or run the Mac bridge).
        </div>
      )}
      {sendMsg && <p className="mb-2 text-sm text-red-600">{sendMsg}</p>}
      <div className="flex h-[70vh] overflow-hidden rounded-xl border border-gray-200 bg-white">
        {/* Threads list */}
        <div className="w-72 shrink-0 overflow-y-auto border-r border-gray-200">
          <div className="flex gap-1 border-b border-gray-200 p-2">
            <input value={newPhone} onChange={(e) => setNewPhone(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && startNew()}
              placeholder="+1 617 555 1234" className="min-w-0 flex-1 rounded-lg border border-gray-300 px-2 py-1.5 text-sm" />
            <button onClick={startNew} className="shrink-0 rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white">New</button>
          </div>
          {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}
          {(threads || []).map((t) => (
            <button
              key={t.phone}
              onClick={() => setActive(t.phone)}
              className={`block w-full border-b border-gray-100 px-4 py-3 text-left hover:bg-gray-50 ${active === t.phone ? "bg-brand/10" : ""}`}
            >
              <div className="flex justify-between">
                <span className="font-medium">{t.name || t.phone}</span>
                <span className="text-xs text-gray-400">{t.count}</span>
              </div>
              <div className="truncate text-xs text-gray-500">
                {t.last_direction === "inbound" ? "↩ " : "→ "}{t.last_body}
              </div>
            </button>
          ))}
          {!loading && !error && !threads?.length && <p className="p-4 text-sm text-gray-400">No conversations yet.</p>}
        </div>

        {/* Conversation */}
        <div className="flex flex-1 flex-col">
          {active ? (
            <>
              <div className="border-b border-gray-200 px-4 py-2 text-sm font-medium">
                {detail?.name || active} <span className="text-gray-400">· {active}</span>
              </div>
              <div className="flex-1 space-y-2 overflow-y-auto bg-gray-50 p-4">
                {(detail?.messages || []).map((m, i) => (
                  <div key={i} className={`flex ${m.direction === "outbound" ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[70%] rounded-2xl px-3 py-2 text-sm ${m.direction === "outbound" ? "bg-brand text-white" : "bg-white border border-gray-200"}`}>
                      {m.body}
                      <div className={`mt-1 text-[10px] ${m.direction === "outbound" ? "text-white/70" : "text-gray-400"}`}>
                        {m.at ? new Date(m.at).toLocaleString() : ""} {m.direction === "outbound" ? `· ${m.status}` : ""}
                      </div>
                    </div>
                  </div>
                ))}
                <div ref={endRef} />
              </div>
              <div className="flex items-center gap-2 border-t border-gray-200 p-3">
                <select value={account} onChange={(e) => setAccount(e.target.value)} className="rounded-lg border border-gray-300 px-2 py-2 text-xs">
                  <option value="personal">Personal #</option>
                  <option value="insurance">Insurance #</option>
                </select>
                <input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && send()}
                  placeholder="Type a message…"
                  className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm"
                />
                <button className="btn" onClick={send}>Send</button>
              </div>
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center text-gray-400">Select a conversation</div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Texts /></AuthGate>;
}
