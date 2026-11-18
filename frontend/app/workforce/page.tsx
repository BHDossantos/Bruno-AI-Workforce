"use client";

import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type Dept = {
  key: string; name: string; icon: string; tagline: string;
  agents: string[]; count: number; active: boolean;
};
type WaitsForYou = {
  mode: string; autopilot: boolean; paused: boolean; calls_on: boolean;
  pending_drafts: number; open_actions: number; approve_from_phone: boolean;
};
type Activity = { time: string; actor: string; action: string; detail: string };
type Map = {
  departments: Dept[]; total_agents: number; knowledge: string[];
  today: { email: number; sms: number; call: number; replies: number };
  week: { email: number; sms: number; call: number; replies: number };
  waits_for_you: WaitsForYou; activity: Activity[];
};

const ACCENT: Record<string, string> = {
  leads: "from-emerald-500/20 to-emerald-500/5 border-emerald-400/40",
  email: "from-sky-500/20 to-sky-500/5 border-sky-400/40",
  texting: "from-violet-500/20 to-violet-500/5 border-violet-400/40",
  calls: "from-amber-500/20 to-amber-500/5 border-amber-400/40",
  conversation: "from-rose-500/20 to-rose-500/5 border-rose-400/40",
  content: "from-indigo-500/20 to-indigo-500/5 border-indigo-400/40",
};

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3 text-center">
      <div className="text-2xl font-bold text-gray-900">{value.toLocaleString()}</div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  );
}

function Workforce() {
  const { data, loading, error, reload } = useFetch<Map>(() => api.get<Map>("/workforce/map"));
  const w = data?.waits_for_you;
  const activeCount = (data?.departments || []).filter((d) => d.active).length;

  return (
    <div>
      <PageHeader
        title="Workforce"
        subtitle="Your whole AI team on one page — every agent, what it's doing, and what's waiting on you."
      />
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}
      {data && (
        <>
          {/* Hub summary + human-approval gate */}
          <div className="mb-4 grid gap-3 md:grid-cols-3">
            <div className="col-span-1 flex items-center gap-3 rounded-2xl border border-brand/30 bg-gradient-to-br from-brand/15 to-brand/5 p-4 md:col-span-2">
              <div className="flex h-14 w-14 flex-none items-center justify-center rounded-2xl bg-brand/20 text-2xl">🧠</div>
              <div>
                <div className="text-lg font-bold text-gray-900">Bruno AI Workforce</div>
                <div className="text-sm text-gray-600">
                  <b>{data.total_agents}</b> agents across <b>{data.departments.length}</b> departments
                  {" · "}<span className={activeCount ? "text-emerald-600" : "text-gray-400"}>{activeCount} on-task now</span>
                </div>
              </div>
            </div>
            <div className={`rounded-2xl border p-4 ${w?.approve_from_phone ? "border-amber-300 bg-amber-50" : "border-emerald-300 bg-emerald-50"}`}>
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">🙌 Waits for you</div>
              <div className="mt-1 text-sm text-gray-800">
                {w?.paused
                  ? "⛔ Everything is paused (Emergency Stop)."
                  : w?.approve_from_phone
                    ? "Nothing sends without your yes — approve from your phone."
                    : "Full autopilot — sending on its own."}
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                <span className="rounded-full bg-white px-2 py-0.5 text-gray-700 ring-1 ring-gray-200">{w?.pending_drafts ?? 0} drafts pending</span>
                <span className="rounded-full bg-white px-2 py-0.5 text-gray-700 ring-1 ring-gray-200">{w?.open_actions ?? 0} replies need you</span>
                <span className={`rounded-full px-2 py-0.5 ring-1 ${w?.calls_on ? "bg-white text-gray-700 ring-gray-200" : "bg-red-100 text-red-700 ring-red-200"}`}>
                  calls {w?.calls_on ? "on" : "off"}
                </span>
              </div>
            </div>
          </div>

          {/* The map — departments */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.departments.map((d) => (
              <div key={d.key} className={`rounded-2xl border bg-gradient-to-br p-4 ${ACCENT[d.key] || "from-gray-100 to-white border-gray-200"}`}>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{d.icon}</span>
                    <div>
                      <div className="font-semibold text-gray-900">{d.name}</div>
                      <div className="text-xs text-gray-500">{d.tagline}</div>
                    </div>
                  </div>
                  <span className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${d.active ? "bg-emerald-100 text-emerald-700" : "bg-gray-200 text-gray-500"}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${d.active ? "animate-pulse bg-emerald-500" : "bg-gray-400"}`} />
                    {d.active ? "running" : "paused"}
                  </span>
                </div>
                <div className="mt-2 text-[11px] font-semibold uppercase tracking-wide text-gray-400">{d.count} agents</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {d.agents.map((a) => (
                    <span key={a} className="rounded-md bg-white/70 px-1.5 py-0.5 text-[11px] text-gray-700 ring-1 ring-black/5">{a}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Knowledge every agent reads */}
          <div className="mt-4 rounded-2xl border border-gray-200 bg-white p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">📚 Knowledge — read by every agent</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {data.knowledge.map((k) => (
                <span key={k} className="rounded-lg bg-gray-50 px-2.5 py-1 text-sm text-gray-700 ring-1 ring-gray-200">{k}</span>
              ))}
            </div>
          </div>

          {/* Today's numbers */}
          <div className="mt-4">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">📊 Today</div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Emails sent" value={data.today.email} />
              <Stat label="Texts sent" value={data.today.sms} />
              <Stat label="Calls placed" value={data.today.call} />
              <Stat label="Replies in" value={data.today.replies} />
            </div>
            <div className="mt-1 text-right text-xs text-gray-400">
              This week: {data.week.email} emails · {data.week.sms} texts · {data.week.call} calls · {data.week.replies} replies
            </div>
          </div>

          {/* Live activity */}
          <div className="mt-4 rounded-2xl border border-gray-200 bg-white p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">⚡ Live activity</div>
            {data.activity.length === 0 ? (
              <p className="mt-2 text-sm text-gray-400">No agent activity logged yet. As the agents work, their runs show here.</p>
            ) : (
              <ol className="mt-2 space-y-1.5">
                {data.activity.map((a, i) => (
                  <li key={i} className="flex items-baseline gap-2 text-sm">
                    <span className="w-10 flex-none font-mono text-xs text-gray-400">{a.time}</span>
                    <span className="font-medium text-brand-dark">{a.actor}</span>
                    <span className="text-gray-700">{a.action}</span>
                    {a.detail && <span className="truncate text-xs text-gray-400">{a.detail}</span>}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><Workforce /></AuthGate>;
}
