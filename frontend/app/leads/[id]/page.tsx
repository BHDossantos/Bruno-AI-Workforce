"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type Counts = { email: number; sms: number; call: number };
type LeadInfo = {
  id: string; name: string; email: string | null; phone: string | null;
  source: string | null; status: string; stage: string; temperature: string;
  score: number | null; band: string | null; times_contacted: number;
  received_at: string | null;
};
type Event = { at: string | null; kind: string; label: string; detail: string | null; status?: string };
type Outreach = {
  email: { subject: string; body: string; tailored: string | null };
  sms: { body: string; tailored: string | null };
  voicemail: string;
  call_notes: string[];
};
type Profile = {
  lead: LeadInfo;
  counts: Counts;
  timeline: Event[];
  everquote: Record<string, unknown> | null;
  outreach: Outreach | null;
};
type EmailTpl = { id: string; name: string; subject: string; body: string };
type SmsTpl = { id: string; name: string; body: string };
type CallTpl = { id: string; name: string; framework: string[]; script: string };
type Templates = { email: EmailTpl[]; sms: SmsTpl[]; call: CallTpl[] };

function fmt(at: string | null) {
  if (!at) return "";
  const d = new Date(at);
  return isNaN(d.getTime()) ? at : d.toLocaleString();
}

function Profile() {
  const { id } = useParams<{ id: string }>();
  const [tick, setTick] = useState(0);
  const { data, loading, error, reload } = useFetch<Profile>(
    () => api.get<Profile>(`/leads/${id}/profile`), [id, tick]);
  const { data: tpl } = useFetch<Templates>(() => api.get<Templates>(`/leads/${id}/templates`), [id]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [emailBody, setEmailBody] = useState<string | null>(null);
  const [emailSubject, setEmailSubject] = useState<string | null>(null);
  const [smsBody, setSmsBody] = useState<string | null>(null);
  const [callOutcome, setCallOutcome] = useState("Reached");
  const [callNotes, setCallNotes] = useState("");
  const [noteText, setNoteText] = useState("");
  const [callScript, setCallScript] = useState<CallTpl | null>(null);

  const lead = data?.lead;
  const oe = data?.outreach?.email;
  const os = data?.outreach?.sms;
  // Pre-fill the compose boxes: the lead's AI-drafted message if it's an
  // EverQuote lead, otherwise the first template (personalized) so the box is
  // never empty. The user can still switch templates or edit freely.
  const emailFallback = oe ? oe.tailored || oe.body : (tpl?.email?.[0]?.body ?? "");
  const smsFallback = os ? os.tailored || os.body : (tpl?.sms?.[0]?.body ?? "");
  const emailText = emailBody ?? emailFallback;
  const smsText = smsBody ?? smsFallback;

  async function act(kind: string, fn: () => Promise<unknown>) {
    setBusy(kind);
    setNote("");
    try {
      await fn();
      setNote(`✅ ${kind} done.`);
      setTick((t) => t + 1);
    } catch (e) {
      setNote(`❌ ${e}`);
    } finally {
      setBusy("");
    }
  }

  const emailSubj = emailSubject ?? (oe ? oe.subject : (tpl?.email?.[0]?.subject ?? ""));
  const sendEmail = () =>
    act("Email", async () => {
      const r = await api.post<{ sent: boolean; status: string }>(`/leads/${id}/send-email`, { message: emailText, subject: emailSubj });
      setNote(r.sent ? "✅ Email sent." : `✅ Email ${r.status}.`);
    });
  const sendText = () =>
    act("Text", () => api.post(`/leads/${id}/send-text`, { message: smsText }));
  const logCall = () =>
    act("Call log", async () => {
      await api.post(`/leads/${id}/log-call`, { outcome: callOutcome, notes: callNotes || null });
      setCallNotes("");
    });
  const callNow = () =>
    act("Call", async () => {
      const r = await api.post<{ message: string }>(`/calls/lead/${id}`, {});
      setNote(`📞 ${r.message}`);
    });
  const saveNote = () =>
    act("Note", async () => {
      await api.post(`/leads/${id}/note`, { note: noteText });
      setNoteText("");
    });

  return (
    <div>
      <PageHeader title={lead?.name || "Lead"} subtitle="CRM profile — email, text, log calls, and see every touch in one place" />
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}
      {note && <p className="mb-3 rounded bg-brand/10 p-3 text-sm text-brand-dark">{note}</p>}
      {lead && (
        <div className="grid gap-4 lg:grid-cols-3">
          {/* Left: identity + counters + actions */}
          <div className="space-y-4">
            <div className="card">
              <div className="mb-2 flex items-center justify-between">
                <h2 className="font-semibold">{lead.name}</h2>
                <span className="badge bg-indigo-100 text-indigo-700">{lead.stage}</span>
              </div>
              <dl className="space-y-1 text-sm">
                <Row k="Email" v={lead.email} />
                <Row k="Phone" v={lead.phone} />
                <Row k="Source" v={lead.source} />
                <Row k="Status" v={lead.status} />
                <Row k="Temperature" v={lead.temperature} />
                <Row k="AI score" v={lead.score != null ? `${lead.score}/100 · ${lead.band || ""}` : "—"} />
                <Row k="Received" v={fmt(lead.received_at)} />
              </dl>
            </div>

            <div className="card">
              <h3 className="mb-2 text-sm font-semibold text-gray-500">Touches</h3>
              <div className="grid grid-cols-3 gap-2 text-center">
                <Counter icon="📧" label="Emails" n={data.counts.email} />
                <Counter icon="💬" label="Texts" n={data.counts.sms} />
                <Counter icon="📞" label="Calls" n={data.counts.call} />
              </div>
            </div>

            {/* Call */}
            <div className="card">
              <h3 className="mb-2 text-sm font-semibold text-gray-500">Call</h3>
              <button className="btn mb-2 w-full" disabled={busy === "Call" || !lead.phone} onClick={callNow}>
                {busy === "Call" ? "Calling…" : "📞 Call lead (rings your phone)"}
              </button>
              <p className="mb-3 text-xs text-gray-400">Twilio rings your phone, then connects the lead. Recorded with a consent notice; AI notes post to the timeline after.</p>
              <h3 className="mb-2 text-sm font-semibold text-gray-500">Log a call manually</h3>
              <select value={callOutcome} onChange={(e) => setCallOutcome(e.target.value)}
                className="mb-2 w-full rounded-lg border border-gray-300 px-2 py-2 text-sm">
                {["Reached", "Left voicemail", "No answer", "Busy", "Wrong number", "Callback scheduled"].map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
              <input value={callNotes} onChange={(e) => setCallNotes(e.target.value)}
                placeholder="Notes (optional)" className="mb-2 w-full rounded-lg border border-gray-300 px-2 py-2 text-sm" />
              <button className="btn w-full" disabled={busy === "Call log"} onClick={logCall}>
                {busy === "Call log" ? "Logging…" : "📞 Log call"}
              </button>
              <h3 className="mb-2 mt-4 text-sm font-semibold text-gray-500">Add a note</h3>
              <textarea value={noteText} onChange={(e) => setNoteText(e.target.value)} rows={2}
                placeholder="Jot a note about this lead…" className="mb-2 w-full rounded-lg border border-gray-300 px-2 py-2 text-sm" />
              <button className="btn w-full" disabled={busy === "Note" || !noteText.trim()} onClick={saveNote}>
                {busy === "Note" ? "Saving…" : "📝 Save note"}
              </button>
              <select className="mt-3 w-full rounded-lg border border-gray-300 px-2 py-2 text-sm"
                defaultValue="" onChange={(e) => setCallScript(tpl?.call.find((x) => x.id === e.target.value) || null)}>
                <option value="">Call script…</option>
                {(tpl?.call || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
              {callScript && (
                <div className="mt-2">
                  <div className="mb-1 flex flex-wrap gap-1">
                    {callScript.framework.map((f) => (
                      <span key={f} className="badge bg-brand/10 text-brand-dark text-[10px]">{f}</span>
                    ))}
                  </div>
                  <p className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs text-gray-600">{callScript.script}</p>
                </div>
              )}
              {!callScript && data.outreach && (
                <p className="mt-2 whitespace-pre-wrap text-xs text-gray-500">Voicemail script:{"\n"}{data.outreach.voicemail}</p>
              )}
            </div>
          </div>

          {/* Middle: compose email + text */}
          <div className="space-y-4">
            <div className="card">
              <h3 className="mb-2 text-sm font-semibold text-gray-500">Email</h3>
              <select className="mb-2 w-full rounded-lg border border-gray-300 px-2 py-2 text-sm"
                defaultValue="" onChange={(e) => {
                  const t = tpl?.email.find((x) => x.id === e.target.value);
                  if (t) { setEmailBody(t.body); setEmailSubject(t.subject); }
                }}>
                <option value="">Pick a template…</option>
                {(tpl?.email || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
              <input value={emailSubj} onChange={(e) => setEmailSubject(e.target.value)}
                placeholder="Subject" className="mb-2 w-full rounded-lg border border-gray-300 px-2 py-2 text-sm" />
              <textarea value={emailText} onChange={(e) => setEmailBody(e.target.value)} rows={8}
                className="mb-2 w-full rounded-lg border border-gray-300 p-2 text-sm" placeholder="No email content — type here or import an EverQuote lead." />
              <button className="btn w-full" disabled={busy === "Email" || !lead.email || !emailText} onClick={sendEmail}>
                {busy === "Email" ? "Sending…" : "📧 Send email"}
              </button>
            </div>
            <div className="card">
              <h3 className="mb-2 text-sm font-semibold text-gray-500">Text</h3>
              <select className="mb-2 w-full rounded-lg border border-gray-300 px-2 py-2 text-sm"
                defaultValue="" onChange={(e) => {
                  const t = tpl?.sms.find((x) => x.id === e.target.value);
                  if (t) setSmsBody(t.body);
                }}>
                <option value="">Pick a template…</option>
                {(tpl?.sms || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
              <textarea value={smsText} onChange={(e) => setSmsBody(e.target.value)} rows={4}
                className="mb-2 w-full rounded-lg border border-gray-300 p-2 text-sm" placeholder="Type a text…" />
              <button className="btn w-full" disabled={busy === "Text" || !lead.phone || !smsText} onClick={sendText}>
                {busy === "Text" ? "Sending…" : "💬 Send text"}
              </button>
              <p className="mt-1 text-xs text-gray-400">Opt-out, texting hours, and daily cap are enforced automatically.</p>
            </div>
          </div>

          {/* Right: timeline */}
          <div className="card">
            <h3 className="mb-3 text-sm font-semibold text-gray-500">Activity timeline</h3>
            <ol className="space-y-3">
              {(data.timeline || []).slice().reverse().map((e, i) => (
                <li key={i} className="border-l-2 border-gray-200 pl-3">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-sm font-medium">{e.label}</span>
                    <span className="shrink-0 text-xs text-gray-400">{fmt(e.at)}</span>
                  </div>
                  {e.detail && <p className="truncate text-xs text-gray-500">{e.detail}</p>}
                </li>
              ))}
              {!data.timeline?.length && <p className="text-sm text-gray-400">No activity yet.</p>}
            </ol>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string | null }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-gray-400">{k}</dt>
      <dd className="text-right font-medium text-gray-700">{v || "—"}</dd>
    </div>
  );
}

function Counter({ icon, label, n }: { icon: string; label: string; n: number }) {
  return (
    <div className="rounded-lg bg-gray-50 py-2">
      <div className="text-lg">{icon}</div>
      <div className="text-xl font-semibold">{n}</div>
      <div className="text-[10px] uppercase tracking-wide text-gray-400">{label}</div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Profile /></AuthGate>;
}
