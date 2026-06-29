"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api, clearToken, getToken } from "@/lib/api";
import LiveClock from "@/components/LiveClock";

const NAV = [
  { href: "/", label: "Mission Control", icon: "🛰️" },
  { href: "/clients", label: "Client Engine", icon: "🎯" },
  { href: "/approvals", label: "Approval Queue", icon: "☑️" },
  { href: "/followups", label: "Follow-ups", icon: "🔁" },
  { href: "/activation", label: "Go-Live Setup", icon: "🚀" },
  { href: "/setup", label: "Connect Email & Data", icon: "🔑" },
  { href: "/search", label: "Search", icon: "🔍" },
  { href: "/autopilot", label: "Application Autopilot", icon: "🤖" },
  { href: "/crm", label: "Universal CRM", icon: "👥" },
  { href: "/factory", label: "Content Factory", icon: "🏭" },
  { href: "/calendar", label: "Content Calendar", icon: "🗓️" },
  { href: "/centers", label: "Command Centers", icon: "🎖️" },
  { href: "/money", label: "Money / Net Worth", icon: "💵" },
  { href: "/objectives", label: "Objectives", icon: "🎯" },
  { href: "/opportunities", label: "Opportunities", icon: "✨" },
  { href: "/board", label: "Board Report", icon: "🧑‍⚖️" },
  { href: "/planning", label: "Predictive Planning", icon: "🔮" },
  { href: "/decisions", label: "Decision Journal", icon: "📓" },
  { href: "/agents", label: "Agent Performance", icon: "🤖" },
  { href: "/analytics", label: "Funnel Analytics", icon: "📊" },
  { href: "/growth", label: "Growth Analytics", icon: "📈" },
  { href: "/pipeline", label: "Sales Pipeline", icon: "💰" },
  { href: "/learnings", label: "AI Learnings", icon: "🎓" },
  { href: "/jobs", label: "Jobs", icon: "💼" },
  { href: "/apply", label: "Apply Queue", icon: "✅" },
  { href: "/insurance", label: "Insurance Leads", icon: "🛡️" },
  { href: "/bnbglobal", label: "BnB Global Consulting", icon: "💻" },
  { href: "/savorymind", label: "SavoryMind Leads", icon: "🍽️" },
  { href: "/music", label: "Music Campaigns", icon: "🎵" },
  { href: "/foundation", label: "Foundation — Grants", icon: "🎓" },
  { href: "/instagram", label: "Instagram Planner", icon: "📸" },
  { href: "/connections", label: "Connections", icon: "🔌" },
  { href: "/status", label: "System Status", icon: "🩺" },
  { href: "/import", label: "Import Contacts", icon: "📥" },
  { href: "/outbox", label: "Outbox", icon: "📧" },
  { href: "/newsletters", label: "Newsletters", icon: "📰" },
  { href: "/texts", label: "Texts", icon: "💬" },
  { href: "/queue", label: "Outreach Queue", icon: "✋" },
  { href: "/brief", label: "Daily Brief", icon: "📋" },
  { href: "/memory", label: "Memory / Knowledge", icon: "🧠" },
  { href: "/settings", label: "Brand Profile", icon: "⚙️" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");

  // Public pages (login + legal) render without the app chrome so they're
  // cleanly crawlable by TikTok/Meta app review without a login.
  if (pathname === "/login" || pathname === "/terms" || pathname === "/privacy") return null;

  function search() {
    if (!q.trim()) return;
    router.push(`/search?q=${encodeURIComponent(q)}`);
    setOpen(false);
  }

  return (
    <>
      {/* Mobile top bar */}
      <div className="flex items-center justify-between bg-brand-dark px-4 py-3 text-white md:hidden">
        <span className="font-bold">Bruno AI</span>
        <button aria-label="Menu" onClick={() => setOpen(!open)} className="rounded p-1 hover:bg-white/10">
          {open ? "✕" : "☰"}
        </button>
      </div>

      {open && <div className="fixed inset-0 z-20 bg-black/40 md:hidden" onClick={() => setOpen(false)} />}

      <aside className={`fixed inset-y-0 left-0 z-30 flex w-60 flex-col bg-brand-dark text-white transition-transform md:static md:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="px-5 py-6">
          <h1 className="text-lg font-bold leading-tight">Bruno AI</h1>
          <p className="text-xs text-brand-light">Workforce Platform</p>
          <LiveClock className="mt-1 block text-xs text-brand-light" />
        </div>

        <div className="px-3 pb-3">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search()}
            placeholder="Search everything…"
            className="w-full rounded-lg bg-white/10 px-3 py-2 text-sm text-white placeholder-brand-light outline-none focus:bg-white/15"
          />
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3">
          {NAV.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                  active ? "bg-white/15 font-semibold" : "text-brand-light hover:bg-white/10"
                }`}
              >
                <span>{item.icon}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>
        <EmergencyStop />
        <button
          onClick={() => {
            clearToken();
            router.push("/login");
          }}
          className="mx-3 mb-3 rounded-lg border border-white/20 px-3 py-2 text-sm text-brand-light hover:bg-white/10"
        >
          Sign out
        </button>
      </aside>
    </>
  );
}

/** Always-visible global kill-switch. Pauses/resumes all autonomous posting,
 * sending and agent runs. */
function EmergencyStop() {
  const [paused, setPaused] = useState<boolean | null>(null);
  const [mode, setMode] = useState<string>("semi");
  const [outreach, setOutreach] = useState<boolean>(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) return;
    api.get<{ paused: boolean; mode?: string; outreach_autopilot?: boolean }>("/control/status")
      .then((r) => {
        setPaused(r.paused);
        if (r.mode) setMode(r.mode);
        if (typeof r.outreach_autopilot === "boolean") setOutreach(r.outreach_autopilot);
      })
      .catch(() => {});
  }, []);

  async function toggle() {
    setBusy(true);
    try {
      const r = await api.post<{ paused: boolean }>(paused ? "/control/resume" : "/control/pause", {});
      setPaused(r.paused);
    } catch {
      /* ignore — status stays as-is */
    } finally {
      setBusy(false);
    }
  }

  async function changeMode(m: string) {
    setBusy(true);
    try {
      const r = await api.post<{ mode: string }>("/control/mode", { mode: m });
      setMode(r.mode);
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  }

  async function toggleOutreach() {
    setBusy(true);
    try {
      const r = await api.post<{ outreach_autopilot: boolean }>("/control/outreach-autopilot", { on: !outreach });
      setOutreach(r.outreach_autopilot);
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  }

  if (paused === null) return null;
  return (
    <div className="mx-3 mt-3 space-y-2">
      {/* Automation mode: semi (you approve to send) vs full autopilot */}
      <div className="rounded-lg bg-white/10 p-2">
        <div className="mb-1 text-[11px] uppercase tracking-wide text-brand-light">Automation</div>
        <div className="flex gap-1">
          {[["semi", "Semi (approve)"], ["auto", "Autopilot"], ["manual", "Manual"]].map(([m, label]) => (
            <button key={m} onClick={() => changeMode(m)} disabled={busy}
              className={`flex-1 rounded px-1.5 py-1 text-[11px] ${
                mode === m ? "bg-white text-brand-dark font-semibold" : "text-brand-light hover:bg-white/10"
              }`}>
              {label}
            </button>
          ))}
        </div>
      </div>
      {/* Outreach Autopilot: cold sales leads + their follow-ups auto-send even in
          Semi mode, so the lead machine runs on its own. Content still drafts. */}
      <div className="rounded-lg bg-white/10 p-2">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-brand-light">Outreach Autopilot</div>
            <div className="text-[10px] text-brand-light/70">Leads + follow-ups auto-send</div>
          </div>
          <button onClick={toggleOutreach} disabled={busy} title="Auto-send cold outreach and follow-ups"
            className={`rounded px-2 py-1 text-[11px] font-semibold ${
              outreach ? "bg-emerald-400 text-emerald-950 hover:bg-emerald-300"
                       : "bg-white/15 text-brand-light hover:bg-white/20"
            }`}>
            {outreach ? "ON" : "OFF"}
          </button>
        </div>
      </div>
      <button
        onClick={toggle}
        disabled={busy}
        className={`w-full rounded-lg px-3 py-2 text-sm font-semibold disabled:opacity-50 ${
          paused ? "bg-amber-400 text-amber-950 hover:bg-amber-300"
                 : "bg-red-600 text-white hover:bg-red-500"
        }`}
      >
        {busy ? "…" : paused ? "▶ Agents PAUSED — Resume" : "⛔ Emergency Stop"}
      </button>
    </div>
  );
}
