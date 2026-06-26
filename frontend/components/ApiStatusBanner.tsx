"use client";

import { useCallback, useEffect, useState } from "react";
import { API_URL } from "@/lib/api";

/** Site-wide banner that makes backend problems OBVIOUS instead of leaving pages
 * stuck on "Loading…". It pings the public /health endpoint; if it can't reach
 * the backend it shows the API URL it's trying (so a misconfigured
 * NEXT_PUBLIC_API_URL is instantly visible) plus a Retry. */
export default function ApiStatusBanner() {
  const [status, setStatus] = useState<"checking" | "ok" | "down">("checking");

  const check = useCallback(async () => {
    setStatus("checking");
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 12000);
      const res = await fetch(`${API_URL}/health`, { signal: ctrl.signal });
      clearTimeout(t);
      setStatus(res.ok ? "ok" : "down");
    } catch {
      setStatus("down");
    }
  }, []);

  useEffect(() => { check(); }, [check]);

  if (status !== "down") return null;
  return (
    <div className="sticky top-0 z-40 flex flex-wrap items-center gap-x-3 gap-y-1 bg-red-600 px-4 py-2 text-sm text-white">
      <span className="font-semibold">⚠️ Can&apos;t reach the backend.</span>
      <span className="opacity-90">
        Trying <code className="rounded bg-white/20 px-1">{API_URL}</code> — it may be starting up, blocked, or misconfigured.
      </span>
      <button onClick={check} className="ml-auto rounded bg-white/20 px-3 py-0.5 font-medium hover:bg-white/30">
        Retry
      </button>
    </div>
  );
}
