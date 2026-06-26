"use client";

import { useEffect, useState } from "react";

/** Live date + time, updates every second. Shown next to Bruno's name. */
export default function LiveClock({ className = "" }: { className?: string }) {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!now) return null;
  const date = now.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  const time = now.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return <span className={className}>{date} · {time}</span>;
}
