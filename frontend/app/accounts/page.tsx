"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, KpiCard, LoadState, useFetch } from "@/components/ui";

type Account = {
  id: string; name: string; businesses: string[];
  leads: number; clients: number; won: number;
  cold: number; warm: number; hot: number;
  pipeline_value: number; revenue_monthly: number; contacts: number;
};
type LeadCard = {
  id: string; type: "lead"; name: string | null; email: string | null; phone: string | null;
  status: string; stage: string; temperature: string; line: string | null; value: number; link: string;
};
type ClientCard = {
  id: string; type: "client"; name: string; email: string | null; phone: string | null;
  business: string; line: string | null; carrier: string | null; status: string;
  premium_monthly: number; link: string;
};
type RestaurantCard = {
  id: string; type: "restaurant"; name: string; email: string | null; phone: string | null;
  status: string; temperature: string; link: string;
};
type ContactCard = {
  id: string; type: "contact"; name: string; title: string | null; email: string | null;
  phone: string | null; kind: string;
};
type TimelineEntry = { at: string | null; kind: string; body: string | null };
type AccountDetail = Account & {
  leads: LeadCard[]; clients: ClientCard[]; restaurants: RestaurantCard[];
  contacts: ContactCard[]; timeline: TimelineEntry[];
} & { leads_count?: number };

const money = (n: number) => (n >= 1000 ? `$${(n / 1000).toFixed(1)}k` : `$${Math.round(n)}`);
const TEMP_DOT: Record<string, string> = { hot: "🔥", warm: "🌤️", cold: "❄️" };

function Accounts() {
  const [q, setQ] = useState("");
  const [business, setBusiness] = useState("");
  const [tick, setTick] = useState(0);
  const qs = new URLSearchParams({ ...(q ? { q } : {}), ...(business ? { business } : {}) }).toString();
  const { data, loading, error, reload } = useFetch<Account[]>(
    () => api.get<Account[]>(`/accounts${qs ? `?${qs}` : ""}`), [qs, tick]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AccountDetail | null>(null);

  const totals = (data || []).reduce(
    (a, r) => ({ pipeline: a.pipeline + r.pipeline_value, revenue: a.revenue + r.revenue_monthly, won: a.won + r.won }),
    { pipeline: 0, revenue: 0, won: 0 });

  async function open(id: string) {
    setOpenId(id); setDetail(null);
    try { setDetail(await api.get<AccountDetail>(`/accounts/${encodeURIComponent(id)}`)); }
    catch { setOpenId(null); }
  }

  return (
    <div>
      <PageHeader title="Accounts"
        subtitle="One page per company — every lead, won client, contact and email rolled up together, Salesforce-style." />

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="Accounts" value={(data || []).length.toLocaleString()} />
        <KpiCard label="Won clients" value={totals.won.toLocaleString()} />
        <KpiCard label="Pipeline value" value={money(totals.pipeline)} />
        <KpiCard label="Monthly revenue" value={money(totals.revenue)} />
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <input className="input flex-1" placeholder="Search company…" value={q}
          onChange={(e) => { setQ(e.target.value); setTick((t) => t + 1); }} />
        <select className="input" value={business} onChange={(e) => { setBusiness(e.target.value); setTick((t) => t + 1); }}>
          <option value="">All businesses</option>
          <option value="Insurance">Insurance</option>
          <option value="BnB Global">BnB Global</option>
          <option value="SavoryMind">SavoryMind</option>
          <option value="Music">Music</option>
        </select>
      </div>

      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}
      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="p-3">Company</th><th className="p-3">Business</th>
              <th className="p-3">Leads</th><th className="p-3">Temp</th>
              <th className="p-3">Won clients</th><th className="p-3">Pipeline</th>
              <th className="p-3">Revenue/mo</th>
            </tr>
          </thead>
          <tbody>
            {(data || []).map((a) => (
              <tr key={a.id} className="cursor-pointer border-t hover:bg-gray-50" onClick={() => open(a.id)}>
                <td className="p-3 font-medium">{a.name}</td>
                <td className="p-3">
                  <div className="flex flex-wrap gap-1">
                    {a.businesses.map((b) => <span key={b} className="badge bg-gray-100 text-gray-600">{b}</span>)}
                  </div>
                </td>
                <td className="p-3">{a.leads}</td>
                <td className="p-3 text-xs">
                  {a.hot > 0 && <span className="mr-1">{TEMP_DOT.hot}{a.hot}</span>}
                  {a.warm > 0 && <span className="mr-1">{TEMP_DOT.warm}{a.warm}</span>}
                  {a.hot === 0 && a.warm === 0 && <span className="text-gray-300">—</span>}
                </td>
                <td className="p-3">{a.won}</td>
                <td className="p-3">{a.pipeline_value > 0 ? money(a.pipeline_value) : "—"}</td>
                <td className="p-3">{a.revenue_monthly > 0 ? money(a.revenue_monthly) : "—"}</td>
              </tr>
            ))}
            {!loading && (data || []).length === 0 && (
              <tr><td colSpan={7} className="p-6 text-center text-gray-400">No accounts yet — leads, clients and contacts will roll up here automatically.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {openId && (
        <DetailModal detail={detail} onClose={() => { setOpenId(null); setDetail(null); }} />
      )}
    </div>
  );
}

function DetailModal({ detail, onClose }: { detail: AccountDetail | null; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/40 p-4" onClick={onClose}>
      <div className="mt-8 w-full max-w-2xl rounded-xl bg-white p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">{detail?.name || "Loading…"}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">✕</button>
        </div>
        {!detail ? <p className="text-sm text-gray-400">Loading…</p> : (
          <>
            <div className="mb-4 flex flex-wrap gap-2 text-xs">
              {detail.businesses.map((b) => <span key={b} className="badge bg-gray-100 text-gray-600">{b}</span>)}
              {detail.pipeline_value > 0 && <span className="badge bg-emerald-100 text-emerald-700">Pipeline {money(detail.pipeline_value)}</span>}
              {detail.revenue_monthly > 0 && <span className="badge bg-sky-100 text-sky-700">{money(detail.revenue_monthly)}/mo</span>}
            </div>

            {detail.leads.length > 0 && (
              <Section title="Leads / opportunities">
                {detail.leads.map((l) => (
                  <Row key={l.id} name={l.name || "—"} sub={`${l.line || ""} · ${l.stage}`.trim()}
                    right={`${TEMP_DOT[l.temperature] || ""} $${l.value}`} link={l.link} />
                ))}
              </Section>
            )}
            {detail.clients.length > 0 && (
              <Section title="Won clients">
                {detail.clients.map((c) => (
                  <Row key={c.id} name={c.name} sub={`${c.carrier || ""} ${c.line || ""}`.trim()}
                    right={c.premium_monthly ? `$${c.premium_monthly}/mo` : c.status} link={c.link} />
                ))}
              </Section>
            )}
            {detail.restaurants.length > 0 && (
              <Section title="Restaurant prospects">
                {detail.restaurants.map((r) => (
                  <Row key={r.id} name={r.name} sub={r.status} right={TEMP_DOT[r.temperature] || ""} link={r.link} />
                ))}
              </Section>
            )}
            {detail.contacts.length > 0 && (
              <Section title="Contacts">
                {detail.contacts.map((c) => (
                  <Row key={c.id} name={c.name} sub={c.title || c.kind} right={c.email || c.phone || ""} />
                ))}
              </Section>
            )}

            <Section title="Activity timeline">
              {detail.timeline.length === 0 && <p className="text-sm text-gray-400">Nothing logged yet.</p>}
              <div className="max-h-56 space-y-2 overflow-y-auto">
                {detail.timeline.map((t, i) => (
                  <div key={i} className="rounded-lg bg-gray-50 p-2 text-sm">
                    <div className="flex justify-between text-xs text-gray-400">
                      <span className="uppercase">{t.kind}</span>
                      <span>{t.at ? new Date(t.at).toLocaleString() : ""}</span>
                    </div>
                    <div>{t.body}</div>
                  </div>
                ))}
              </div>
            </Section>
          </>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">{title}</div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Row({ name, sub, right, link }: { name: string; sub?: string; right?: string; link?: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-gray-100 px-3 py-2 text-sm">
      <div>
        <div className="font-medium">{name}</div>
        {sub && <div className="text-xs text-gray-400">{sub}</div>}
      </div>
      <div className="flex items-center gap-2 text-xs text-gray-500">
        {right}
        {link && <a href={link} className="text-brand" onClick={(e) => e.stopPropagation()}>Open ↗</a>}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Accounts /></AuthGate>;
}
