"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api, clearToken, getToken } from "@/lib/api";
import LiveClock from "@/components/LiveClock";

// Navigation is grouped into collapsible sections so the ~60 pages are easy to
// scan and navigate instead of one long flat list. Every page still lives here —
// nothing is hidden, just organized. The group containing the current page is
// always shown, and each section's open/closed state is remembered per-browser.
type NavItem = { href: string; label: string; icon: string };
type NavGroup = { title: string; icon: string; items: NavItem[] };

const GROUPS: NavGroup[] = [
  {
    title: "🛡️ Work Leads", icon: "🛡️",
    items: [
      { href: "/worklist", label: "Call List", icon: "📞" },
      { href: "/insurance", label: "Insurance Leads", icon: "🎯" },
      { href: "/texts", label: "Texts", icon: "💬" },
      { href: "/outbox", label: "Email Outbox", icon: "📧" },
      { href: "/approvals", label: "Approval Queue", icon: "☑️" },
      { href: "/inbox", label: "Unified Inbox", icon: "📨" },
      { href: "/followups", label: "Follow-ups", icon: "🔁" },
      { href: "/queue", label: "Outreach Queue", icon: "✋" },
      { href: "/lead-finder", label: "Lead Finder", icon: "🔎" },
    ],
  },
  {
    title: "🗃️ CRM & Pipeline", icon: "🗃️",
    items: [
      { href: "/clients-crm", label: "Client Book (CRM)", icon: "🗃️" },
      { href: "/crm", label: "Universal CRM", icon: "👥" },
      { href: "/accounts", label: "Accounts", icon: "🏢" },
      { href: "/deals", label: "Deal Pipeline", icon: "🗂️" },
      { href: "/pipeline", label: "Sales Pipeline", icon: "💰" },
      { href: "/quote-intake", label: "Quote Intake", icon: "📝" },
      { href: "/import", label: "Import Contacts", icon: "📥" },
    ],
  },
  {
    title: "⭐ Command", icon: "⭐",
    items: [
      { href: "/", label: "Mission Control", icon: "🛰️" },
      { href: "/insurance-commander", label: "Insurance Commander", icon: "🎖️" },
      { href: "/today", label: "Today's Money Actions", icon: "💸" },
      { href: "/brief", label: "Daily Brief", icon: "📋" },
      { href: "/knowledge", label: "Knowledge Base", icon: "📚" },
    ],
  },
  {
    title: "📊 Analytics", icon: "📊",
    items: [
      { href: "/analytics", label: "Funnel Analytics", icon: "📊" },
      { href: "/revenue", label: "Revenue & ROI", icon: "💵" },
      { href: "/growth", label: "Growth Analytics", icon: "📈" },
      { href: "/outreach-report", label: "Outreach Performance", icon: "📈" },
      { href: "/by-line", label: "Conversion by Line", icon: "📶" },
      { href: "/agents", label: "Agent Performance", icon: "🤖" },
      { href: "/opportunities", label: "Opportunities", icon: "✨" },
      { href: "/objectives", label: "Objectives", icon: "🎯" },
      { href: "/board", label: "Board Report", icon: "🧑‍⚖️" },
      { href: "/planning", label: "Predictive Planning", icon: "🔮" },
      { href: "/decisions", label: "Decision Journal", icon: "📓" },
      { href: "/learnings", label: "AI Learnings", icon: "🎓" },
      { href: "/money", label: "Money / Net Worth", icon: "🏦" },
      { href: "/centers", label: "Command Centers", icon: "🎖️" },
    ],
  },
  {
    title: "📬 Deliverability", icon: "📬",
    items: [
      { href: "/deliverability", label: "Email Deliverability", icon: "📬" },
      { href: "/mailboxes", label: "Mailbox Pool", icon: "📮" },
      { href: "/subject-ab", label: "Subject A/B Testing", icon: "🧪" },
    ],
  },
  {
    title: "⚙️ Setup & System", icon: "⚙️",
    items: [
      { href: "/setup", label: "Connect Email & Data", icon: "🔑" },
      { href: "/connections", label: "Connections", icon: "🔌" },
      { href: "/activation", label: "Go-Live Setup", icon: "🚀" },
      { href: "/settings", label: "Brand Profile", icon: "⚙️" },
      { href: "/status", label: "System Status", icon: "🩺" },
      { href: "/webhooks", label: "Webhooks", icon: "🔗" },
      { href: "/automations", label: "Automations", icon: "⚡" },
      { href: "/agent-builder", label: "Create AI Agent", icon: "✨" },
      { href: "/memory", label: "Memory / Knowledge", icon: "🧠" },
      { href: "/search", label: "Search", icon: "🔍" },
    ],
  },
  {
    title: "📦 Other Businesses (paused)", icon: "📦",
    items: [
      { href: "/bnbglobal", label: "BnB Global Consulting", icon: "💻" },
      { href: "/savorymind", label: "SavoryMind Leads", icon: "🍽️" },
      { href: "/music", label: "Music Campaigns", icon: "🎵" },
      { href: "/foundation", label: "Foundation", icon: "🎓" },
      { href: "/clients", label: "Client Engine", icon: "🎯" },
      { href: "/campaign-builder", label: "Campaign Builder", icon: "🧭" },
      { href: "/factory", label: "Content Factory", icon: "🏭" },
      { href: "/calendar", label: "Content Calendar", icon: "🗓️" },
      { href: "/newsletters", label: "Newsletters", icon: "📰" },
      { href: "/instagram", label: "Instagram Planner", icon: "📸" },
      { href: "/jobs", label: "Jobs", icon: "💼" },
      { href: "/apply", label: "Apply Queue", icon: "✅" },
      { href: "/autopilot", label: "Application Autopilot", icon: "🤖" },
    ],
  },
];

function groupForPath(pathname: string): string | null {
  for (const g of GROUPS) {
    if (g.items.some((i) => i.href === pathname)) return g.title;
  }
  return null;
}

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  // Per-browser memory of which sections are expanded. Starts with just the
  // Work Leads group open; the section containing the current page is always
  // shown regardless (see `sectionOpen`).
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({ "🛡️ Work Leads": true });

  useEffect(() => {
    try {
      const raw = localStorage.getItem("nav_groups");
      if (raw) setOpenGroups(JSON.parse(raw));
    } catch { /* ignore malformed storage */ }
  }, []);

  function toggleGroup(title: string) {
    setOpenGroups((prev) => {
      const next = { ...prev, [title]: !(prev[title] ?? false) };
      try { localStorage.setItem("nav_groups", JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
  }

  const activeGroup = groupForPath(pathname);
  const sectionOpen = (title: string) => (openGroups[title] ?? false) || title === activeGroup;

  // Public pages (login + legal) render without the app chrome so they're
  // cleanly crawlable by TikTok/Meta app review without a login.
  if (pathname === "/login" || pathname === "/terms" || pathname === "/privacy" || pathname === "/data-deletion") return null;

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

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 pb-2">
          {GROUPS.map((group) => {
            const expanded = sectionOpen(group.title);
            return (
              <div key={group.title} className="mb-1">
                <button
                  onClick={() => toggleGroup(group.title)}
                  className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-brand-light/80 hover:bg-white/5"
                >
                  <span className="flex items-center gap-2">
                    <span>{group.icon}</span>
                    {group.title}
                  </span>
                  <span className="text-brand-light/60">{expanded ? "▾" : "▸"}</span>
                </button>
                {expanded && (
                  <div className="mt-0.5 space-y-0.5">
                    {group.items.map((item) => {
                      const active = pathname === item.href;
                      return (
                        <Link
                          key={item.href}
                          href={item.href}
                          onClick={() => setOpen(false)}
                          className={`flex items-center gap-3 rounded-lg py-2 pl-6 pr-3 text-sm transition ${
                            active ? "bg-white/15 font-semibold" : "text-brand-light hover:bg-white/10"
                          }`}
                        >
                          <span>{item.icon}</span>
                          {item.label}
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
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
        <BuildStamp />
      </aside>
    </>
  );
}

/** Which build is actually live — so a merged change can be confirmed to have
 * reached the site at a glance. Shows the frontend build (baked at image build)
 * and the backend build (from /version). "dev" means an un-stamped local build. */
function BuildStamp() {
  const front = process.env.NEXT_PUBLIC_BUILD_SHA || "dev";
  const [back, setBack] = useState<string>("…");
  useEffect(() => {
    if (!getToken()) { setBack("—"); return; }
    api.get<{ sha?: string }>("/version")
      .then((r) => setBack(r.sha || "?"))
      .catch(() => setBack("unreachable"));
  }, []);
  return (
    <div className="mx-3 mb-3 text-[10px] leading-tight text-brand-light/60" title="Live build versions — front (this page) and back (API)">
      build · front {front} · api {back}
    </div>
  );
}

/** Always-visible master switch for the automation engine. The scheduler runs
 * always-on in the cloud; this ON/OFF flips all autonomous sourcing, sending,
 * calling and agent runs in-app (pause/resume) with no redeploy. */
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
      {/* Master ON/OFF for the whole 24/7 schedule. The scheduler stays always-on
          in the cloud; this flips everything on/off in-app with no redeploy. */}
      <div className="rounded-lg bg-white/10 p-2">
        <div className="mb-1 flex items-center justify-between">
          <div className="text-[11px] uppercase tracking-wide text-brand-light">Automation engine</div>
          <span className={`text-[11px] font-semibold ${paused ? "text-red-300" : "text-emerald-300"}`}>
            {paused ? "OFF" : "ON"}
          </span>
        </div>
        <div className="mb-2 text-[10px] text-brand-light/70">
          {paused
            ? "Off — nothing sources, sends, or calls on schedule."
            : "On — running the 24/7 schedule: sourcing, outreach, calls, follow-ups."}
        </div>
        <button
          onClick={toggle}
          disabled={busy}
          title="Master switch for all scheduled automation"
          className={`w-full rounded-lg px-3 py-2 text-sm font-semibold disabled:opacity-50 ${
            paused ? "bg-emerald-500 text-white hover:bg-emerald-400"
                   : "bg-red-600 text-white hover:bg-red-500"
          }`}
        >
          {busy ? "…" : paused ? "▶ Turn automation ON" : "⛔ Turn automation OFF"}
        </button>
      </div>
    </div>
  );
}
