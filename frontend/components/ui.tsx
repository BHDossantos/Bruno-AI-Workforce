"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/api";

/** Redirects to /login if there is no token. Wraps every protected page. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!getToken()) router.replace("/login");
    else setReady(true);
  }, [router]);
  if (!ready) return <div className="p-8 text-gray-400">Loading…</div>;
  return <>{children}</>;
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return (
    <div className="mb-6 flex items-end justify-between">
      <div>
        <h1 className="text-2xl font-bold">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-gray-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function KpiCard({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="card">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p className="mt-2 text-3xl font-bold text-brand-dark">{value}</p>
      {hint && <p className="mt-1 text-xs text-gray-400">{hint}</p>}
    </div>
  );
}

const STATUS_COLORS: Record<string, string> = {
  New: "bg-gray-100 text-gray-700",
  Drafted: "bg-blue-100 text-blue-700",
  Sent: "bg-indigo-100 text-indigo-700",
  Opened: "bg-cyan-100 text-cyan-700",
  Replied: "bg-teal-100 text-teal-700",
  Interested: "bg-green-100 text-green-700",
  "Follow-up Needed": "bg-amber-100 text-amber-700",
  "Closed Won": "bg-emerald-200 text-emerald-800",
  "Closed Lost": "bg-red-100 text-red-700",
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${STATUS_COLORS[status] || "bg-gray-100 text-gray-700"}`}>{status}</span>;
}

/** Collapsible text cell for long AI-generated content. */
export function Expandable({ label, text }: { label: string; text?: string | null }) {
  const [open, setOpen] = useState(false);
  if (!text) return <span className="text-xs text-gray-300">—</span>;
  return (
    <div>
      <button onClick={() => setOpen(!open)} className="text-xs font-medium text-brand hover:underline">
        {open ? `▾ Hide ${label}` : `▸ ${label}`}
      </button>
      {open && <pre className="mt-1 max-w-md whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs text-gray-700">{text}</pre>}
    </div>
  );
}

/** Generic data fetching hook. */
export function useFetch<T>(fetcher: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    setData(null);
    fetcher()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, loading };
}
