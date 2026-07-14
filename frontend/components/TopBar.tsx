"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

// The few pages worked every day — pinned to the top bar so they're one click
// from anywhere, no menu-hunting.
const QUICK = [
  { href: "/worklist", label: "Call List", icon: "📞" },
  { href: "/crm", label: "CRM", icon: "👥" },
  { href: "/texts", label: "Texts", icon: "💬" },
  { href: "/outbox", label: "Outbox", icon: "📧" },
];

/** A persistent header on every page with a prominent global search (was buried
 * in the side menu) plus the daily-use shortcuts. Hidden on public pages so they
 * stay chrome-less for app-review crawlers. */
export default function TopBar() {
  const pathname = usePathname();
  const router = useRouter();
  const [q, setQ] = useState("");

  if (pathname === "/login" || pathname === "/terms" || pathname === "/privacy" || pathname === "/data-deletion") {
    return null;
  }

  function search(e: FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    router.push(`/search?q=${encodeURIComponent(q)}`);
  }

  return (
    <div className="sticky top-0 z-10 flex flex-wrap items-center gap-2 border-b border-gray-200 bg-white/90 px-4 py-2 backdrop-blur md:px-6">
      <form onSubmit={search} className="flex min-w-0 flex-1 items-center">
        <div className="relative w-full max-w-xl">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">🔍</span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search leads, contacts, anything…"
            aria-label="Search"
            className="w-full rounded-lg border border-gray-300 bg-gray-50 py-2 pl-9 pr-3 text-sm outline-none focus:border-brand focus:bg-white focus:ring-2 focus:ring-brand/20"
          />
        </div>
      </form>
      <nav className="flex items-center gap-1">
        {QUICK.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm ${
                active ? "bg-brand/10 font-semibold text-brand-dark" : "text-gray-600 hover:bg-gray-100"
              }`}
            >
              <span>{item.icon}</span>
              <span className="hidden md:inline">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
