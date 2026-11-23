import Link from "next/link";

type ChannelCounts = { email: number; sms: number; call: number };
type OutreachAction = { name: string; channel: string; status: string; snippet: string; received_at: string; link: string };
export type OutreachSummary = {
  sent: { today: ChannelCounts; week: ChannelCounts };
  replies: { today: number; week: number };
  actions: OutreachAction[];
  actions_count: number;
  window?: { today_start: string; seven_day_start: string; snapshot_at: string; timezone: "UTC" };
};

const CHANNELS = [
  ["email", "Email records"],
  ["sms", "Text records"],
  ["call", "Call records"],
] as const;

function metric(value: number | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString() : "Not available";
}

export default function MissionOutreach({ data, loading, error, onRetry }: {
  data: OutreachSummary | null; loading: boolean; error: string | null; onRetry: () => void;
}) {
  const window = data?.window;
  const day = window?.today_start.slice(0, 10);
  const start = window?.seven_day_start.slice(0, 10);

  return (
    <section id="outreach-activity" aria-labelledby="outreach-heading" className="mb-6 scroll-mt-4 rounded-xl border border-gray-200 bg-white p-4 sm:p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="outreach-heading" className="text-lg font-semibold text-gray-900">Outreach activity</h2>
          <p className="text-sm text-gray-600">
            {day && start ? `Today: ${day} UTC. Last 7 calendar days: ${start} to ${day} UTC.`
              : "Reporting uses UTC. The 7-day window includes today."}
          </p>
          {window && <p className="text-xs text-gray-600">Snapshot: <time dateTime={window.snapshot_at}>{window.snapshot_at.slice(11, 16)} UTC</time></p>}
        </div>
        <Link href="/analytics" className="text-sm font-medium text-brand-dark underline">Open analytics</Link>
      </div>

      {!data || error ? (
        <div className="rounded-lg border border-gray-200 p-3 text-sm text-gray-700">
          {loading && !error ? <p role="status">Loading outreach records…</p> : (
            <div className="flex flex-wrap items-center gap-3">
              <p role="status">Outreach data unavailable. Counts are unknown, not zero.</p>
              <button type="button" className="rounded-lg border border-gray-300 px-3 py-2 font-medium" onClick={onRetry}>Retry outreach data</button>
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
            <section aria-labelledby="outbound-heading" className="rounded-lg border border-gray-200 p-3">
              <h3 id="outbound-heading" className="font-semibold">Outbound records</h3>
              <p className="mb-3 text-xs text-gray-600">App records with a send timestamp. These totals do not show all attempts, provider acceptance, delivery or answered calls.</p>
              <dl className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                {CHANNELS.map(([key, label]) => (
                  <div key={key} className="rounded-md bg-gray-50 p-2.5">
                    <dt className="text-sm font-medium text-gray-700">{label}</dt>
                    <dd className="text-xl font-bold">{metric(data.sent?.today?.[key])}<span className="ml-1 text-xs font-normal text-gray-600">today</span></dd>
                    <dd className="text-xs text-gray-600">{metric(data.sent?.week?.[key])} in last 7 days</dd>
                  </div>
                ))}
              </dl>
            </section>
            <section aria-labelledby="inbound-heading" className="rounded-lg border border-gray-200 p-3">
              <h3 id="inbound-heading" className="font-semibold">Inbound records</h3>
              <p className="mb-3 text-xs text-gray-600">Logged incoming activity across channels, not a verified human-reply count.</p>
              <dl className="rounded-md bg-gray-50 p-2.5">
                <dt className="sr-only">Incoming activity</dt>
                <dd className="text-xl font-bold">{metric(data.replies?.today)}<span className="ml-1 text-xs font-normal text-gray-600">today</span></dd>
                <dd className="text-xs text-gray-600">{metric(data.replies?.week)} in last 7 days</dd>
              </dl>
            </section>
          </div>
          <p className="mt-2 text-xs text-gray-600">A zero means no matching records were logged in this app for the period. It does not establish provider activity.</p>

          <section id="follow-up" aria-labelledby="follow-up-heading" className="mt-4 scroll-mt-4 border-t border-gray-200 pt-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 id="follow-up-heading" className="font-semibold">Flagged for follow-up <span className="text-sm font-normal text-gray-600">({data.actions.length} shown)</span></h3>
              <Link href="/inbox" className="text-sm font-medium text-brand-dark underline">Open inbox</Link>
            </div>
            <p className="mb-2 text-xs text-gray-600">Up to 20 recent flagged records. Check the thread before acting.</p>
            {data.actions.length === 0 ? <p className="rounded-md bg-gray-50 p-2.5 text-sm text-gray-700">No recent flagged records were returned.</p> : (
              <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200">
                {data.actions.map((a, i) => (
                  <li key={`${a.link}:${a.received_at}:${i}`}>
                    <Link href={a.link} className="block break-words px-3 py-2 text-sm hover:bg-gray-50">
                      <span className="font-semibold text-gray-900">{a.name}</span>
                      <span className="ml-2 text-xs font-medium text-gray-600">{({ email: "Email", sms: "Text", call: "Call" } as Record<string, string>)[a.channel] || "Channel not recorded"} · {a.status}</span>
                      <span className="mt-0.5 block text-gray-600">{a.snippet}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </section>
  );
}
