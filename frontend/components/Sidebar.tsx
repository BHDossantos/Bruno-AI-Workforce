"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken } from "@/lib/api";

const NAV = [
  { href: "/", label: "Home Dashboard", icon: "🏠" },
  { href: "/jobs", label: "Jobs", icon: "💼" },
  { href: "/insurance", label: "Insurance Leads", icon: "🛡️" },
  { href: "/savorymind", label: "SavoryMind Leads", icon: "🍽️" },
  { href: "/music", label: "Music Campaigns", icon: "🎵" },
  { href: "/instagram", label: "Instagram Planner", icon: "📸" },
  { href: "/outbox", label: "Outbox", icon: "📧" },
  { href: "/brief", label: "Daily Brief", icon: "📋" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  if (pathname === "/login") return null;

  return (
    <aside className="flex w-60 flex-col bg-brand-dark text-white">
      <div className="px-5 py-6">
        <h1 className="text-lg font-bold leading-tight">Bruno AI</h1>
        <p className="text-xs text-brand-light">Workforce Platform</p>
      </div>
      <nav className="flex-1 space-y-1 px-3">
        {NAV.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
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
  );
}
