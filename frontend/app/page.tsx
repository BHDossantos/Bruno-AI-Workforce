"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch } from "@/components/ui";
import LiveClock from "@/components/LiveClock";

type Action = {
  key: string; title: string; command_center: string; objective: string; action_type: string;
  value: number; probability: number; effort: number; priority: number;
  link: string; why: string;
};
type RecapItem = { icon: string; label: string; count: number };
type ChecklistItem = { key: string; label: string; required: boolean; status: string; detail: string; action: string };
type Activation = { ready_pct: number; live: boolean; done: number; required_total: number; next_step: ChecklistItem | null; checklist: ChecklistItem[] };
type Brief = {
  greeting: string; focus_score: number; estimated_value_today: number;
  top_actions: Action[]; summary: string[]; total_actions: number; hidden_count: number;
  recap: RecapItem[];
};
type Score = {
  monthly_income: number; pipeline_value: number; net_worth: number;
  leads: number; users: number; reach: number; fitness_score: number;
};
type Brand = { key: string; name: string; icon: string; metric: string; value: number; warm: number; hot: number; link: string };
type Goal = { area: string; target: number; today: number; status: string };
type ClientGoal = {
  target: number; won_today: number; won_total: number; on_track: boolean; deficit: number;
  conversion_rate: number; conversion_measured: boolean; prospects_contacted: number;
  needed_touches_per_day: number; sent_today: number;
};
type Mission = {
  paused: boolean; approvals_pending: number; auto_sending?: number; goals: Goal[];
  today: {
    posts: number; insurance_leads: number; bnb_leads: number; savorymind_leads: number;
    outreach_sent: number; replies: number; applications: number; jobs_found: number;
  };
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
  const { data: golive } = useFetch<Activation>(() => api.get<Activation>("/activation"), [refresh]);
  const { data: mission } = useFetch<Mission>(() => api.get<Mission>("/mission/control"), [refresh]);
  const { data: brands } = useFetch<Brand[]>(() => api.get<Brand[]>("/mission/brands"), [refresh]);
  const { data: cgoal } = useFetch<ClientGoal>(() => api.get<ClientGoal>("/clients/goal"), [refresh]);
  const [running, setRunning] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  async function runAll() {
    setRunning(true); setMsg("");
    try { await api.post("/agents/run-all"); setMsg("Agents running — refresh in a minute."); }
    catch (e) { setMsg(String(e)); }
    finally { setRunning(false); }
  }

  async function workPipeline() {
    setRunning(true); setMsg("Working the pipeline — sourcing & drafting across every line…");
    try {
      const r = await api.post<{ summary?: string }>("/mission/work-pipeline", {});
      setMsg(`✅ ${r.summary || "Pipeline worked — check the Approval Queue."}`);
      setRefresh((n) => n + 1);
    } catch (e) { setMsg(`❌ ${e}`); }
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
        action={
          <div className="flex items-center gap-3">
            <LiveClock className="hidden text-sm text-gray-500 sm:inline" />
            <button className="rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium disabled:opacity-50"
              onClick={workPipeline} disabled={running}>▶ Work the pipeline</button>
            <button className="btn" onClick={runAll} disabled={running}>{running ? "Running…" : "Refresh opportunities"}</button>
          </div>
        }
      />
      {msg && <p className="mb-4 rounded bg-brand/10 p-3 text-sm text-brand-dark">{msg}</p>}

      {/* Daily client goal — the standing order: bring in N new clients/day. */}
      {cgoal && (
        <div className={`mb-6 rounded-xl border p-4 ${cgoal.on_track ? "border-emerald-300 bg-emerald-50" : "border-brand/30 bg-brand/5"}`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">Today&apos;s client goal</div>
              <div className="mt-0.5 text-2xl font-bold">
                {cgoal.won_today}<span className="text-base font-normal text-gray-400"> / {cgoal.target} new clients</span>
                {cgoal.on_track
                  ? <span className="ml-2 badge bg-green-100 text-green-700">on track 🎉</span>
                  : <span className="ml-2 badge bg-amber-100 text-amber-700">{cgoal.deficit} to go</span>}
              </div>
              <div className="mt-1 text-xs text-gray-500">
                Engine sized for ~{cgoal.needed_touches_per_day.toLocaleString()} outreach touches/day at a{" "}
                {(cgoal.conversion_rate * 100).toFixed(1)}% {cgoal.conversion_measured ? "measured" : "assumed"} conversion ·{" "}
                {cgoal.sent_today.toLocaleString()} sent today
              </div>
            </div>
            <Link href="/clients" className="text-sm font-medium text-brand">Tune the engine →</Link>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded bg-white">
            <div className={`h-full rounded ${cgoal.on_track ? "bg-emerald-500" : "bg-brand"}`}
                 style={{ width: `${Math.min(100, cgoal.target ? (cgoal.won_today / cgoal.target) * 100 : 0)}%` }} />
          </div>
        </div>
      )}

      {/* Mission Control — today's status, approvals, paused state */}
      {mission?.paused && (
        <div className="mb-4 rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-700">
          ⛔ <b>Agents are paused</b> (Emergency Stop). Nothing is posting or sending. Resume from the sidebar when ready.
        </div>
      )}
      {mission && mission.approvals_pending > 0 && (
        <Link href="/approvals" className="mb-4 flex items-center justify-between rounded-xl border border-amber-300 bg-amber-50 p-4 hover:bg-amber-100">
          <span className="text-sm text-amber-800">
            ☑️ <b>{mission.approvals_pending}</b> item{mission.approvals_pending === 1 ? "" : "s"} need your approval.
          </span>
          <span className="text-sm font-medium text-amber-800">Review now →</span>
        </Link>
      )}
      {mission && (mission.auto_sending ?? 0) > 0 && (
        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          📤 <b>{mission.auto_sending}</b> outreach email{mission.auto_sending === 1 ? "" : "s"} are sending automatically (Outreach Autopilot, paced to protect deliverability) — no action needed.
        </div>
      )}
      {mission && (
        <div className="mb-6">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Today&apos;s AI workforce</div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
            {[
              ["Posts", mission.today.posts], ["Insurance", mission.today.insurance_leads],
              ["BnB", mission.today.bnb_leads], ["SavoryMind", mission.today.savorymind_leads],
              ["Outreach", mission.today.outreach_sent], ["Replies", mission.today.replies],
              ["Apps", mission.today.applications], ["Jobs", mission.today.jobs_found],
            ].map(([label, n]) => (
              <div key={label as string} className="rounded-lg border border-gray-200 bg-white p-2 text-center">
                <div className="text-xl font-bold">{n as number}</div>
                <div className="text-[11px] text-gray-500">{label as string}</div>
              </div>
            ))}
          </div>
          {/* Goal score */}
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {mission.goals.map((g) => (
              <div key={g.area} className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 text-sm">
                <span className="text-gray-700">{g.area}</span>
                <span className="flex items-center gap-2">
                  <b>{g.today}</b><span className="text-gray-400">/ {g.target}</span>
                  <span className={`badge ${g.status === "on track" ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
                    {g.status}
                  </span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Per-brand scoreboard */}
      {brands && brands.length > 0 && (
        <div className="mb-6">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Your brands</div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {brands.map((br) => (
              <Link key={br.key} href={br.link}
                className="rounded-lg border border-gray-200 bg-white p-3 hover:ring-2 hover:ring-brand/30">
                <div className="text-lg">{br.icon}</div>
                <div className="truncate text-xs font-medium text-gray-700">{br.name}</div>
                <div className="mt-1 text-xl font-bold">{br.value.toLocaleString()}</div>
                <div className="text-[11px] text-gray-400">{br.metric}</div>
                {(br.warm > 0 || br.hot > 0) && (
                  <div className="mt-1 text-[11px]">
                    {br.hot > 0 && <span className="text-red-600">🔥 {br.hot} </span>}
                    {br.warm > 0 && <span className="text-amber-600">🌤️ {br.warm}</span>}
                  </div>
                )}
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Go-live activation — only while not fully live */}
      {golive && !golive.live && (
        <div className="mb-6 rounded-xl border border-brand/30 bg-brand/5 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="font-semibold">🚀 Go-live setup — {golive.ready_pct}% ready</div>
              <div className="text-sm text-gray-600">
                {golive.done}/{golive.required_total} essentials done.
                {golive.next_step && <> Next: <b>{golive.next_step.label}</b> — {golive.next_step.detail}</>}
              </div>
            </div>
            <div className="flex items-center gap-3">
              {golive.next_step && <Link href={golive.next_step.action} className="btn">Do it</Link>}
              <Link href="/activation" className="text-sm text-brand">See full checklist →</Link>
            </div>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded bg-white">
            <div className="h-full rounded bg-brand" style={{ width: `${golive.ready_pct}%` }} />
          </div>
        </div>
      )}

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
