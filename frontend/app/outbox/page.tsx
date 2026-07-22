"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, Expandable, PageHeader, StatusBadge, useFetch, LoadState } from "@/components/ui";

type Message = {
  id: string;
  entity_type: string | null;
  to_email: string | null;
  from_account: string;
  subject: string | null;
  body: string | null;
  status: string;
  approved: boolean;
  sent_at: string | null;
};

function Outbox() {
  const [tick, setTick] = useState(0);
  const [account, setAccount] = useState("");
  const { data, loading, error, reload } = useFetch<Message[]>(
    () => api.get<Message[]>(`/messages?limit=300${account ? `&account=${account}` : ""}`),
    [tick, account]
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState("");

  async function act(id: string, path: string) {
    setBusy(id);
    setNote("");
    try {
      await api.post(`/messages/${id}/${path}`);
      setTick((t) => t + 1);
    } catch (e) {
      setNote(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function sendNext(limit: number) {
    setBusy("bulk");
    setNote(`Sending the next ${limit}${account ? ` from ${account}` : ""}…`);
    try {
      const r = await api.post<{ sent: number; failed: number; considered: number; errors: string[] }>(
        "/messages/send-drafts", { account: account || null, limit });
      setNote(
        `✅ Sent ${r.sent} · ${r.failed} failed (of ${r.considered} drafts)` +
        (r.errors?.length ? ` — reason: ${r.errors.join(" | ")}` : "")
      );
      setTick((t) => t + 1);
    } catch (e) {
      setNote(`❌ ${e}`);
    } finally {
      setBusy(null);
    }
  }

  async function syncInbound() {
    setNote("Syncing inbound replies…");
    try {
      const r = await api.post<{ scanned: number; matched: number }>("/inbound/sync");
      setNote(`Inbound sync: scanned ${r.scanned}, matched ${r.matched}.`);
      setTick((t) => t + 1);
    } catch (e) {
      setNote(String(e));
    }
  }

  return (
    <div>
      <PageHeader
        title="Outbox"
        subtitle="Outbound emails delivered via Resend (or your Gmail mailbox), and reply status"
        action={
          <div className="flex gap-2">
            <select value={account} onChange={(e) => setAccount(e.target.value)} className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
              <option value="">All accounts</option>
              <option value="personal">Personal</option>
              <option value="insurance">Insurance</option>
            </select>
            <button className="btn" disabled={busy === "bulk"} onClick={() => sendNext(70)}>
              {busy === "bulk" ? "Sending…" : "Send next 70"}
            </button>
            <button className="btn-ghost" onClick={syncInbound}>Sync replies</button>
          </div>
        }
      />
      <p className="mb-3 text-xs text-gray-500">“Send next 70” sends your highest-priority drafts now — new hot &amp; uncontacted first, then hot follow-ups, warm, cold. Total emails/day are held under a daily cap that ramps up on a new domain (so you clear a backlog without getting spam-flagged), then settles to a steady pace. Pick an account above to send only that mailbox&apos;s drafts. If a send fails, the exact reason shows below.</p>
      {note && <p className="mb-4 rounded bg-brand/10 p-3 text-sm text-brand-dark">{note}</p>}
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}
      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">To</th>
              <th className="th">From</th>
              <th className="th">Subject</th>
              <th className="th">Status</th>
              <th className="th">Body</th>
              <th className="th">Actions</th>
            </tr>
          </thead>
          <tbody>
            {(data || []).map((m) => (
              <tr key={m.id} className="border-t border-gray-100">
                <td className="td text-xs">{m.to_email || "—"}</td>
                <td className="td">
                  <span className={`badge ${m.from_account === "insurance" ? "bg-amber-100 text-amber-700" : "bg-indigo-100 text-indigo-700"}`}>
                    {m.from_account}
                  </span>
                </td>
                <td className="td max-w-xs">{m.subject}</td>
                <td className="td"><StatusBadge status={m.status} />{m.approved && <span className="ml-1 badge bg-green-100 text-green-700">approved</span>}</td>
                <td className="td"><Expandable label="Body" text={m.body} /></td>
                <td className="td whitespace-nowrap">
                  {m.status !== "Sent" && (
                    <button className="btn" disabled={busy === m.id} onClick={() => act(m.id, "send")}>Send</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Outbox /></AuthGate>;
}
