"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type QuoteType = {
  key: string; label: string; line: string; requirements: string[];
  email_subject: string; email_body_en: string; email_body_pt: string;
};

function QuoteIntake() {
  const { data, loading, error, reload } = useFetch<QuoteType[]>(() => api.get<QuoteType[]>("/book/quote-templates"));
  const [lang, setLang] = useState<"en" | "pt">("en");
  const [copied, setCopied] = useState("");

  async function copy(key: string, text: string) {
    try { await navigator.clipboard.writeText(text); setCopied(key); setTimeout(() => setCopied(""), 1500); }
    catch { /* clipboard unavailable */ }
  }

  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;

  return (
    <div>
      <PageHeader title="Quote Intake"
        subtitle="When a prospect asks for insurance, reply with the right one — it collects exactly what's needed to quote that line. English and Portuguese."
        action={
          <div className="flex gap-1 rounded-lg border border-gray-300 p-0.5">
            {(["en", "pt"] as const).map((l) => (
              <button key={l} onClick={() => setLang(l)}
                className={`rounded px-3 py-1 text-sm ${lang === l ? "bg-brand text-white" : "text-gray-600"}`}>
                {l.toUpperCase()}
              </button>
            ))}
          </div>
        } />

      <div className="space-y-6">
        {data.map((q) => {
          const body = lang === "en" ? q.email_body_en : q.email_body_pt;
          const full = `${q.email_subject}\n\n${body}`;
          return (
            <div key={q.key} className="card">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-lg font-semibold">{q.label}</h2>
                <span className="badge bg-brand/10 text-brand-dark">{q.line}</span>
              </div>

              <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400">What to collect</div>
              <ul className="mb-4 list-inside list-disc space-y-1 text-sm text-gray-700">
                {q.requirements.map((r, i) => <li key={i}>{r}</li>)}
              </ul>

              <div className="mb-1 flex items-center justify-between">
                <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">Draft quotation email</div>
                <button className="btn-ghost text-sm" onClick={() => copy(q.key, full)}>
                  {copied === q.key ? "✓ Copied" : "Copy email"}
                </button>
              </div>
              <div className="rounded-lg bg-gray-50 p-3 text-sm">
                <div className="font-medium">Subject: {q.email_subject}</div>
                <pre className="mt-2 whitespace-pre-wrap font-sans text-gray-700">{body}</pre>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><QuoteIntake /></AuthGate>;
}
