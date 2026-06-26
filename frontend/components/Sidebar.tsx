"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken } from "@/lib/api";

const NAV = [
  { href: "/", label: "Home Dashboard", icon: "🏠" },
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
  { href: "/instagram", label: "Instagram Planner", icon: "📸" },
  { href: "/connections", label: "Connections", icon: "🔌" },
  { href: "/status", label: "System Status", icon: "🩺" },
  { href: "/import", label: "Import Contacts", icon: "📥" },
  { href: "/outbox", label: "Outbox", icon: "📧" },
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
        <button
          onClick={() => {
            clearToken();
            router.push("/login");
          }}
          className="m-3 rounded-lg border border-white/20 px-3 py-2 text-sm text-brand-light hover:bg-white/10"
        >
          Sign out
        </button>
      </aside>
    </>
  );
}
