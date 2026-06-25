"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";

type Action = {
  key: string; title: string; command_center: string; objective: string; action_type: string;
  value: number; probability: number; effort: number; priority: number;
  link: string; why: string;
};
type RecapItem = { icon: string; label: string; count: number };
type Brief = {
  greeting: string; focus_score: number; estimated_value_today: number;
  top_actions: Action[]; summary: string[]; total_actions: number; hidden_count: number;
  recap: RecapItem[];
};
type Score = {
  monthly_income: number; pipeline_value: number; net_worth: number;
  leads: number; users: number; reach: number; fitness_score: number;
};

const CENTER_ICON: Record<string, string> = {
  wealth: "💰", business: "🏢", influence: "📣", personal: "💪", life_ops: "🗂️",
};

function money(n: number) {
  return n >= 1000 ? `$${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}k` : `$${n}`;
}

function Home() {
  const [refresh, setRefresh] = useState(0);
  const { data: b } = useFetch<Brief>(() => api.get<Brief>("/brief/today"), [refresh]);
  const { data: score } = useFetch<Score>(() => api.get<Score>("/scoreboard"), [refresh]);
  const [running, setRunning] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  async function runAll() {
    setRunning(true); setMsg("");
    try { await api.post("/agents/run-all"); setMsg("Agents running — refresh in a minute."); }
    catch (e) { setMsg(String(e)); }
    finally { setRunning(false); }
  }

  async function act(path: string, key: string) {
    setBusyKey(key); setMsg("");
    try {
      const r = await api.post<{ ok: boolean; message?: string; reason?: string }>(path, { key });
      setMsg(r.ok ? `✅ ${r.message || "Done"}` : `❌ ${r.reason || "Failed"}`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(String(e)); }
    finally { setBusyKey(null); }
  }

  return (
    <div>
      <PageHeader
        title={b?.greeting || "Good morning, Bruno"}
        subtitle="Your chief of staff has ranked today. Do the top 3 — the rest can wait."
        action={<button className="btn" onClick={runAll} disabled={running}>{running ? "Running…" : "Refresh opportunities"}</button>}
      />
      {msg && <p className="mb-4 rounded bg-brand/10 p-3 text-sm text-brand-dark">{msg}</p>}

      {/* Yesterday — what your team did while you were away */}
      {b && (
        <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
            While you were away (last 24h)
          </div>
          {b.recap.length > 0 ? (
            <div className="flex flex-wrap gap-x-6 gap-y-2">
              {b.recap.map((r) => (
                <div key={r.label} className="flex items-baseline gap-1.5">
                  <span>{r.icon}</span>
                  <span className="font-bold text-gray-900">{r.count.toLocaleString()}</span>
                  <span className="text-sm text-gray-500">{r.label}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500">
              Your team is standing by. Hit <b>Refresh opportunities</b> to put it to work.
            </p>
          )}
        </div>
      )}

      {/* Focus + value */}
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="card">
          <div className="text-xs text-gray-500">Focus score</div>
          <div className="text-3xl font-bold text-brand">{b?.focus_score ?? "—"}<span className="text-base text-gray-400">/100</span></div>
        </div>
        <div className="card">
          <div className="text-xs text-gray-500">Est. value in today&apos;s top 3</div>
          <div className="text-3xl font-bold">{b ? money(b.estimated_value_today) : "—"}</div>
        </div>
        <div className="card">
          <div className="text-xs text-gray-500">Pipeline value</div>
          <div className="text-3xl font-bold">{score ? money(score.pipeline_value) : "—"}</div>
        </div>
        <div className="card">
          <div className="text-xs text-gray-500">Reach</div>
          <div className="text-3xl font-bold">{score ? score.reach.toLocaleString() : "—"}</div>
        </div>
      </div>

      {/* Top 3 actions */}
      <h2 className="mb-3 text-lg font-semibold">🎯 Highest-value actions today</h2>
      <div className="space-y-3">
        {(b?.top_actions || []).map((a, i) => {
          const isLink = a.link?.startsWith("http");
          const execLabel = a.action_type === "apply" ? "Mark applied"
            : a.action_type === "follow_up" ? "Send follow-up" : "Done";
          return (
            <div key={a.key} className="card">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  <span className="text-xl font-bold text-gray-300">{i + 1}</span>
                  <div>
                    <div className="font-semibold">{CENTER_ICON[a.command_center] || "•"} {a.title}</div>
                    <div className="text-xs text-gray-500">{a.why}</div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-semibold text-green-600">{money(Math.round(a.value * a.probability))}</div>
                  <div className="text-[10px] text-gray-400">expected value</div>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {isLink ? (
                  <a href={a.link} target="_blank" rel="noreferrer"
                     className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">Open ↗</a>
                ) : (
                  <Link href={a.link} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm">Open</Link>
                )}
                {a.action_type !== "reply" && (
                  <button onClick={() => act("/actions/execute", a.key)} disabled={busyKey === a.key}
                          className="rounded-lg bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700">
                    {busyKey === a.key ? "Working…" : `✓ ${execLabel}`}
                  </button>
                )}
                <button onClick={() => act("/actions/dismiss", a.key)} disabled={busyKey === a.key}
                        className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-500">Dismiss</button>
              </div>
            </div>
          );
        })}
        {b && b.top_actions.length === 0 && (
          <div className="card text-sm text-gray-500">No open actions yet — hit “Refresh opportunities”.</div>
        )}
      </div>

      {b && (b.hidden_count > 0 || b.summary.length > 0) && (
        <div className="mt-4 rounded-lg bg-gray-50 p-4 text-sm text-gray-600">
          <ul className="list-inside list-disc space-y-1">
            {b.summary.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
          {b.hidden_count > 0 && (
            <p className="mt-2 text-xs text-gray-400">
              {b.hidden_count} more lower-priority actions hidden so you can focus.
            </p>
          )}
        </div>
      )}

      <p className="mt-6 text-xs text-gray-400">
        Ranked by expected value × win probability ÷ effort, weighted by your objective priorities
        (executive role &gt; insurance &gt; consulting &gt; SavoryMind &gt; music).
      </p>
    </div>
  );
}

export default function HomePage() {
  return <AuthGate><Home /></AuthGate>;
}
