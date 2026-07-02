"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";

type Area = { configured: boolean; address?: string };
type Status = {
  ai?: { configured: boolean; model: string };
  gmail_personal: Area; gmail_insurance: Area; gmail_bnb?: Area; gmail_savorymind?: Area;
  apollo: Area; google_places: Area;
  sms?: Area; whatsapp?: Area & { via?: string | null }; jobs_api?: Area;
  instantly?: Area; smartlead?: Area; sendgrid?: Area;
  meta_app?: { configured: boolean; app_id: string; redirect_uri: string };
  tiktok_app?: { configured: boolean; client_key: string; redirect_uri: string };
  booking?: { default: string; insurance: string; bnb: string; savorymind: string };
  contacts_outreach_exclude?: string;
  newsletter_banners?: { insurance: string; bnb: string; savorymind: string; music: string };
};
type MailboxHealth = {
  outbound_mode: string;
  accounts: { account: string; label: string; configured: boolean; can_send: boolean;
    method: string | null; address: string | null; reason: string | null;
    sent_today: number; daily_cap: number; remaining_today: number }[];
};

function Badge({ ok }: { ok: boolean }) {
  return (
    <span className={`badge ${ok ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
      {ok ? "Connected" : "Not connected"}
    </span>
  );
}

function Setup() {
  const { data, loading, error, reload } = useFetch<Status>(() => api.get<Status>("/setup"));
  const [health, setHealth] = useState<MailboxHealth | null>(null);
  const [checking, setChecking] = useState(false);
  const { data: control, reload: reloadControl } = useFetch<{ insurance_relay?: boolean }>(() => api.get<{ insurance_relay?: boolean }>("/control/status"));
  const [form, setForm] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function checkMailboxes() {
    setChecking(true);
    try { setHealth(await api.get<MailboxHealth>("/setup/mailbox-health")); }
    catch (e) { setMsg(`❌ ${e}`); }
    finally { setChecking(false); }
  }

  function set(k: string, v: string) { setForm((f) => ({ ...f, [k]: v })); }

  async function toggleRelay(on: boolean) {
    try { await api.post("/control/insurance-relay", { on }); reloadControl(); }
    catch (e) { setMsg(`❌ ${e}`); }
  }

  async function save() {
    setBusy(true); setMsg("");
    try {
      const r = await api.post<{ saved: string[] }>("/setup", form);
      setMsg(r.saved.length ? `✅ Saved: ${r.saved.join(", ")}. It's live now.` : "Nothing to save — fill a field first.");
      setForm({});
      reload();
    } catch (e) { setMsg(`❌ ${e}`); }
    finally { setBusy(false); }
  }

  if (!data) return <LoadState loading={loading} error={error} onRetry={reload} />;

  return (
    <div className="max-w-2xl">
      <PageHeader title="Connect Email & Data"
        subtitle="The agents need a mailbox to send outreach and read replies, and a data source for high-quality leads. Connect them here — it takes effect immediately, no redeploy." />
      {msg && <p className="mb-3 text-sm text-gray-700">{msg}</p>}

      {/* Mailbox send diagnostic — confirm outreach can ACTUALLY go out */}
      <div className="card mb-4">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">📤 Is my email actually sending?</h2>
          <button className="btn" onClick={checkMailboxes} disabled={checking}>
            {checking ? "Checking…" : "Test sending"}
          </button>
        </div>
        {!health && <p className="mt-2 text-xs text-gray-500">Click “Test sending” to verify each mailbox can send right now (no email is sent — it just checks the login).</p>}
        {health && (
          <div className="mt-3 space-y-2">
            <div className="text-xs text-gray-400">Outbound mode: <b>{health.outbound_mode}</b></div>
            {health.accounts.map((a) => (
              <div key={a.account} className="rounded-lg border border-gray-100 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{a.label}{a.address ? ` · ${a.address}` : ""}</span>
                  <span className={`badge ${a.can_send ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                    {a.can_send ? `✅ Sending (${a.method})` : "❌ Not sending"}
                  </span>
                </div>
                {a.can_send ? (
                  <div className="mt-1 text-xs text-gray-500">Sent today {a.sent_today}/{a.daily_cap} · {a.remaining_today} left today</div>
                ) : (
                  <div className="mt-1 text-xs text-red-600">{a.reason}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-4">
        {/* AI brain (OpenAI) — without this, every AI draft is stub text */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🧠 AI brain (OpenAI)</h2>
            <Badge ok={!!data.ai?.configured} />
          </div>
          <p className="mb-2 text-xs text-gray-500">
            Powers <b>every</b> AI draft — cold emails, quote-intake replies, content, newsletters,
            lead scoring. Without it the system still runs but writes clearly-marked placeholder text
            instead of real copy. Paste an <a className="underline" href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer">OpenAI API key</a> — it takes effect immediately.
          </p>
          {!data.ai?.configured && (
            <div className="mb-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-900">
              ⚠️ Not connected — AI drafts are currently placeholder text. Connect a key to turn on real generation.
            </div>
          )}
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" type="password" placeholder="OpenAI API key (sk-…)"
              value={form.openai_api_key || ""} onChange={(e) => set("openai_api_key", e.target.value)} />
            <input className="input" placeholder={data.ai?.model || "Model (default gpt-4o)"}
              value={form.openai_model || ""} onChange={(e) => set("openai_model", e.target.value)} />
          </div>
        </div>

        {/* Gmail personal */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📧 Gmail — personal mailbox</h2>
            <Badge ok={data.gmail_personal.configured} />
          </div>
          <p className="mb-2 text-xs text-gray-500">
            Used for BnB Global + SavoryMind + (relayed) insurance outreach and to read replies.
            You must use a Google <b>App Password</b> — your normal login password will be rejected
            (that&apos;s the <code>534 5.7.9 application-specific password required</code> error).
          </p>
          <div className="mb-3 rounded-lg bg-blue-50 p-3 text-xs text-blue-900">
            <b>How to get one (≈2 min):</b>
            <ol className="ml-4 mt-1 list-decimal space-y-0.5">
              <li>Turn on <a className="underline" href="https://myaccount.google.com/signinoptions/two-step-verification" target="_blank" rel="noreferrer">2-Step Verification</a> (required, or App passwords won&apos;t appear).</li>
              <li>Open <a className="underline" href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer">Google App passwords</a>, name it &quot;Bruno AI&quot;, click Create.</li>
              <li>Paste the 16-character code below (the spaces Google shows are fine — we strip them).</li>
            </ol>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder={data.gmail_personal.address || "you@gmail.com"}
              value={form.gmail_address || ""} onChange={(e) => set("gmail_address", e.target.value)} />
            <input className="input" type="password" placeholder="16-character App Password"
              value={form.gmail_app_password || ""} onChange={(e) => set("gmail_app_password", e.target.value)} />
          </div>
        </div>

        {/* Gmail insurance */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🛡️ Gmail — insurance mailbox (optional)</h2>
            <Badge ok={data.gmail_insurance.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            <b>Most Thrust / Google Workspace accounts block App Passwords</b> (that&apos;s the
            <code> 535 5.7.8</code> error). Easiest fix: <b>leave these two fields blank</b> and turn ON
            the toggle below — insurance then sends through your personal mailbox with replies routed to Thrust.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder={data.gmail_insurance.address || "you@thrustinsurance.com"}
              value={form.insurance_gmail_address || ""} onChange={(e) => set("insurance_gmail_address", e.target.value)} />
            <input className="input" type="password" placeholder="16-character App Password"
              value={form.insurance_gmail_app_password || ""} onChange={(e) => set("insurance_gmail_app_password", e.target.value)} />
          </div>
          <label className="mt-3 flex items-start gap-2 rounded-lg bg-gray-50 p-3 text-xs text-gray-600">
            <input type="checkbox" className="mt-0.5" checked={!!control?.insurance_relay}
              onChange={(e) => toggleRelay(e.target.checked)} />
            <span>
              <b>Send insurance through my personal mailbox</b> (Reply-To set to Thrust). Use this if you don&apos;t have a separate Thrust App Password — insurance emails still go out, and replies land in the Thrust inbox.
              {control?.insurance_relay ? <span className="ml-1 font-medium text-green-700">ON</span> : null}
            </span>
          </label>
        </div>

        {/* BnB Global mailbox */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">💻 Gmail — BnB Global mailbox</h2>
            <Badge ok={!!data.gmail_bnb?.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Dedicated mailbox for BnB Global consulting outreach (keeps it off your personal Gmail).
            Use a Google <b>App Password</b> (not your login password). Note: a single Gmail still has
            a low safe cold-volume limit — for real volume, route BnB through Smartlead/SendGrid.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder={data.gmail_bnb?.address || "braxandbrie@gmail.com"}
              value={form.bnb_gmail_address || ""} onChange={(e) => set("bnb_gmail_address", e.target.value)} />
            <input className="input" type="password" placeholder="16-character App Password"
              value={form.bnb_gmail_app_password || ""} onChange={(e) => set("bnb_gmail_app_password", e.target.value)} />
          </div>
        </div>

        {/* SavoryMind mailbox */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🍽️ Gmail — SavoryMind mailbox</h2>
            <Badge ok={!!data.gmail_savorymind?.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Dedicated mailbox for SavoryMind restaurant outreach. Use a Google <b>App Password</b>.
            For real volume, route SavoryMind through Smartlead/SendGrid instead of a single Gmail.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder={data.gmail_savorymind?.address || "taste@savorymindfood.com"}
              value={form.savorymind_gmail_address || ""} onChange={(e) => set("savorymind_gmail_address", e.target.value)} />
            <input className="input" type="password" placeholder="16-character App Password"
              value={form.savorymind_gmail_app_password || ""} onChange={(e) => set("savorymind_gmail_app_password", e.target.value)} />
          </div>
        </div>

        {/* Cold-email engine: Instantly / Smartlead */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🚀 Cold-email engine (Instantly / Smartlead)</h2>
            <Badge ok={!!(data.instantly?.configured || data.smartlead?.configured)} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            The durable way to send cold outreach at volume — many warmed inboxes + deliverability,
            instead of a personal Gmail (which Google revokes at volume). Connect EITHER: paste the
            API key + the campaign ID to send into. The app hands every lead to that campaign and
            passes our AI-written copy as <code>{`{{personalization}}`}</code> — set your campaign&apos;s
            email step to use it. When connected, this replaces Gmail sending automatically.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" type="password" placeholder="Instantly API key"
              value={form.instantly_api_key || ""} onChange={(e) => set("instantly_api_key", e.target.value)} />
            <input className="input" placeholder="Instantly campaign ID"
              value={form.instantly_campaign_id || ""} onChange={(e) => set("instantly_campaign_id", e.target.value)} />
            <input className="input" type="password" placeholder="Smartlead API key"
              value={form.smartlead_api_key || ""} onChange={(e) => set("smartlead_api_key", e.target.value)} />
            <input className="input" placeholder="Smartlead campaign ID"
              value={form.smartlead_campaign_id || ""} onChange={(e) => set("smartlead_campaign_id", e.target.value)} />
          </div>
        </div>

        {/* SendGrid — reliable delivery */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📨 SendGrid (reliable email delivery)</h2>
            <Badge ok={!!data.sendgrid?.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Sends your outreach through SendGrid instead of Gmail (which Google revokes at volume) —
            you keep all your copy, sequences and automation. Paste your <b>API key</b> and a{" "}
            <b>verified sender</b> email (verify it first in SendGrid → Sender Authentication; full
            domain auth with SPF/DKIM gives the best inbox placement). When connected, outreach
            sends via SendGrid automatically at a higher daily cap.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" type="password" placeholder="SendGrid API key"
              value={form.sendgrid_api_key || ""} onChange={(e) => set("sendgrid_api_key", e.target.value)} />
            <input className="input" placeholder="Default verified sender (from)"
              value={form.sendgrid_from_email || ""} onChange={(e) => set("sendgrid_from_email", e.target.value)} />
          </div>
          <div className="mt-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Verified sender per business</div>
          <div className="mt-1 grid gap-2 sm:grid-cols-3">
            <input className="input" placeholder="Insurance from"
              value={form.sendgrid_from_insurance || ""} onChange={(e) => set("sendgrid_from_insurance", e.target.value)} />
            <input className="input" placeholder="BnB Global from"
              value={form.sendgrid_from_bnb || ""} onChange={(e) => set("sendgrid_from_bnb", e.target.value)} />
            <input className="input" placeholder="SavoryMind from"
              value={form.sendgrid_from_savorymind || ""} onChange={(e) => set("sendgrid_from_savorymind", e.target.value)} />
          </div>
          <div className="mt-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Reply-To per business (optional — where replies land)</div>
          <div className="mt-1 grid gap-2 sm:grid-cols-3">
            <input className="input" placeholder="Insurance reply-to"
              value={form.sendgrid_replyto_insurance || ""} onChange={(e) => set("sendgrid_replyto_insurance", e.target.value)} />
            <input className="input" placeholder="BnB reply-to"
              value={form.sendgrid_replyto_bnb || ""} onChange={(e) => set("sendgrid_replyto_bnb", e.target.value)} />
            <input className="input" placeholder="SavoryMind reply-to"
              value={form.sendgrid_replyto_savorymind || ""} onChange={(e) => set("sendgrid_replyto_savorymind", e.target.value)} />
          </div>
        </div>

        {/* Meta app — powers the one-click Facebook/Instagram connect button */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📘 Facebook / Instagram app (one-click connect)</h2>
            <Badge ok={!!data.meta_app?.configured} />
          </div>
          <p className="mb-2 text-xs text-gray-500">
            Enables the <b>&ldquo;Connect with Facebook/Instagram&rdquo;</b> button on the Connections
            page — one click instead of pasting tokens, with a long-lived token that auto-refreshes
            (no more surprise disconnects). From your Meta app (developers.facebook.com): App ID,
            App Secret, and add the redirect URI below as a <b>Valid OAuth Redirect URI</b>.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder={data.meta_app?.app_id || "Facebook App ID"}
              value={form.facebook_app_id || ""} onChange={(e) => set("facebook_app_id", e.target.value)} />
            <input className="input" type="password" placeholder="Facebook App Secret"
              value={form.facebook_app_secret || ""} onChange={(e) => set("facebook_app_secret", e.target.value)} />
            <input className="input sm:col-span-2" placeholder={data.meta_app?.redirect_uri || "Redirect URI — https://<backend>/connections/meta/oauth/callback"}
              value={form.meta_redirect_uri || ""} onChange={(e) => set("meta_redirect_uri", e.target.value)} />
          </div>
        </div>

        {/* TikTok app — powers the one-click Connect with TikTok button */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🎵 TikTok app (one-click connect)</h2>
            <Badge ok={!!data.tiktok_app?.configured} />
          </div>
          <p className="mb-2 text-xs text-gray-500">
            Enables the <b>&ldquo;Connect with TikTok&rdquo;</b> button on the Connections page. From your
            TikTok app (developers.tiktok.com): Client Key, Client Secret, and add the redirect URI below
            as a registered redirect URI. Note: until TikTok audits your app, posts publish as private
            (SELF_ONLY) — that&apos;s a TikTok review step, not a setting.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder={data.tiktok_app?.client_key || "TikTok Client Key"}
              value={form.tiktok_client_key || ""} onChange={(e) => set("tiktok_client_key", e.target.value)} />
            <input className="input" type="password" placeholder="TikTok Client Secret"
              value={form.tiktok_client_secret || ""} onChange={(e) => set("tiktok_client_secret", e.target.value)} />
            <input className="input sm:col-span-2" placeholder={data.tiktok_app?.redirect_uri || "Redirect URI — https://<backend>/connections/tiktok/oauth/callback"}
              value={form.tiktok_redirect_uri || ""} onChange={(e) => set("tiktok_redirect_uri", e.target.value)} />
          </div>
        </div>

        {/* Booking links — turn an interested reply into a booked call */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📅 Booking links (Calendly / Cal.com)</h2>
            <Badge ok={!!(data.booking && (data.booking.default || data.booking.insurance || data.booking.bnb || data.booking.savorymind))} />
          </div>
          <p className="mb-2 text-xs text-gray-500">
            Paste a scheduling link and a <b>&ldquo;Book a time&rdquo;</b> button is added to every outreach
            email and AI-drafted reply — so an interested prospect books a call instead of trading emails.
            Set a link per business; the default is used for anything without its own.
          </p>
          <input className="input w-full" placeholder={data.booking?.default || "Default booking link (https://calendly.com/…)"}
            value={form.calendar_link || ""} onChange={(e) => set("calendar_link", e.target.value)} />
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            <input className="input" placeholder={data.booking?.insurance || "Insurance booking link"}
              value={form.calendar_link_insurance || ""} onChange={(e) => set("calendar_link_insurance", e.target.value)} />
            <input className="input" placeholder={data.booking?.bnb || "BnB Global booking link"}
              value={form.calendar_link_bnb || ""} onChange={(e) => set("calendar_link_bnb", e.target.value)} />
            <input className="input" placeholder={data.booking?.savorymind || "SavoryMind booking link"}
              value={form.calendar_link_savorymind || ""} onChange={(e) => set("calendar_link_savorymind", e.target.value)} />
          </div>
        </div>

        {/* Newsletter banner photos — a nice default gradient is used if left blank */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🖼️ Newsletter banner photos</h2>
          </div>
          <p className="mb-2 text-xs text-gray-500">
            Every newsletter is already designed (banner, card layout, CTA button) — this just lets you
            swap the default color banner for a real photo per business. Paste a hosted image URL
            (e.g. from your website); leave blank to keep the designed gradient banner.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder={data.newsletter_banners?.insurance || "Insurance banner image URL"}
              value={form.newsletter_banner_insurance || ""} onChange={(e) => set("newsletter_banner_insurance", e.target.value)} />
            <input className="input" placeholder={data.newsletter_banners?.bnb || "BnB Global banner image URL"}
              value={form.newsletter_banner_bnb || ""} onChange={(e) => set("newsletter_banner_bnb", e.target.value)} />
            <input className="input" placeholder={data.newsletter_banners?.savorymind || "SavoryMind banner image URL"}
              value={form.newsletter_banner_savorymind || ""} onChange={(e) => set("newsletter_banner_savorymind", e.target.value)} />
            <input className="input" placeholder={data.newsletter_banners?.music || "Music banner image URL"}
              value={form.newsletter_banner_music || ""} onChange={(e) => set("newsletter_banner_music", e.target.value)} />
          </div>
        </div>

        {/* Imported-contacts warm outreach — who to never auto-email */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🚫 Never auto-email these (imported contacts)</h2>
          </div>
          <p className="mb-2 text-xs text-gray-500">
            When you import a personal contact list, every address on it EXCEPT these gets one warm
            &ldquo;free insurance review&rdquo; intro. Add family, close friends, and anyone who
            shouldn&apos;t get an automated email — comma-separated. This REPLACES the current list
            when saved, so include everyone you want excluded, not just new additions.
          </p>
          <textarea className="input w-full" rows={2}
            placeholder={data.contacts_outreach_exclude || "family@example.com, friend@example.com, …"}
            value={form.contacts_outreach_exclude ?? ""}
            onChange={(e) => set("contacts_outreach_exclude", e.target.value)} />
          {data.contacts_outreach_exclude && (
            <p className="mt-1 text-xs text-gray-400">Currently excluded: {data.contacts_outreach_exclude}</p>
          )}
        </div>

        {/* Apollo */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">🚀 Apollo API key (high-volume B2B leads)</h2>
            <Badge ok={data.apollo.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Best source for BnB Global + commercial insurance volume: real companies with verified emails and firmographics.
            Get a key at apollo.io → Settings → API.
          </p>
          <input className="input w-full" type="password" placeholder="Apollo API key"
            value={form.apollo_api_key || ""} onChange={(e) => set("apollo_api_key", e.target.value)} />
        </div>

        {/* Google Places */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📍 Google Places API key (local businesses)</h2>
            <Badge ok={data.google_places.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Adds real local businesses with contact data (free $200/mo credit). Google Cloud Console → enable Places API → create a key.
          </p>
          <input className="input w-full" type="password" placeholder="Google Places API key"
            value={form.google_places_api_key || ""} onChange={(e) => set("google_places_api_key", e.target.value)} />
        </div>

        {/* Twilio (SMS) */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">💬 Twilio (two-way SMS / texting)</h2>
            <Badge ok={!!data.sms?.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Powers the Texts page. From twilio.com → Console: Account SID, Auth Token, and your Twilio phone number (E.164, e.g. +16175551234). The insurance number is optional — leave it blank to text from the main number.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" type="password" placeholder="Account SID"
              value={form.twilio_account_sid || ""} onChange={(e) => set("twilio_account_sid", e.target.value)} />
            <input className="input" type="password" placeholder="Auth Token"
              value={form.twilio_auth_token || ""} onChange={(e) => set("twilio_auth_token", e.target.value)} />
            <input className="input" placeholder="Main number +1 555 123 4567"
              value={form.twilio_from_number || ""} onChange={(e) => set("twilio_from_number", e.target.value)} />
            <input className="input" placeholder="Insurance number (optional)"
              value={form.twilio_insurance_number || ""} onChange={(e) => set("twilio_insurance_number", e.target.value)} />
          </div>
        </div>

        {/* WhatsApp — Meta Cloud API (preferred, no Twilio) or Twilio WhatsApp */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">📲 WhatsApp</h2>
            <Badge ok={!!data.whatsapp?.configured} />
          </div>
          {data.whatsapp?.configured && (
            <p className="mb-2 text-xs text-emerald-700">
              Active via {data.whatsapp.via === "meta_cloud" ? "Meta's Cloud API (no Twilio)" : "Twilio"}.
            </p>
          )}
          <p className="mb-3 text-xs text-gray-500">
            A legitimate, official channel for messaging clients — unlike consumer-WhatsApp
            automation, which risks account bans. If both are filled in, Meta&apos;s Cloud API is
            used (no reseller markup).
          </p>
          <div className="mb-3 rounded-lg border border-gray-100 p-3">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Meta Cloud API (recommended — no Twilio)
            </div>
            <p className="mb-2 text-xs text-gray-500">
              Reuses your Facebook Developer app: add the <b>WhatsApp</b> product, verify a phone
              number, then copy its Phone Number ID and a permanent access token from Business Settings.
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              <input className="input" placeholder="Phone Number ID"
                value={form.whatsapp_cloud_phone_number_id || ""} onChange={(e) => set("whatsapp_cloud_phone_number_id", e.target.value)} />
              <input className="input" type="password" placeholder="Access token"
                value={form.whatsapp_cloud_token || ""} onChange={(e) => set("whatsapp_cloud_token", e.target.value)} />
            </div>
          </div>
          <div className="rounded-lg border border-gray-100 p-3">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Twilio WhatsApp (fallback)
            </div>
            <p className="mb-2 text-xs text-gray-500">
              Uses the Twilio account above. From twilio.com → Messaging → Try WhatsApp: sandbox
              number to test, or an approved WhatsApp Sender for production.
            </p>
            <input className="input w-full" placeholder="WhatsApp number, e.g. +14155238886"
              value={form.twilio_whatsapp_number || ""} onChange={(e) => set("twilio_whatsapp_number", e.target.value)} />
          </div>
        </div>

        {/* Jobs API (JSearch) */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">💼 Jobs API key (LinkedIn / Indeed / Glassdoor)</h2>
            <Badge ok={!!data.jobs_api?.configured} />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            Live roles from the top job boards via JSearch. Get a free key at rapidapi.com → JSearch → subscribe → copy the X-RapidAPI-Key. Without it, only free remote boards are searched.
          </p>
          <input className="input w-full" type="password" placeholder="JSearch / RapidAPI key"
            value={form.jobs_api_key || ""} onChange={(e) => set("jobs_api_key", e.target.value)} />
        </div>

        <button className="btn" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save & connect"}</button>
        <p className="text-xs text-gray-400">
          Stored securely server-side and never shown again. After connecting Gmail, the Lead Pipeline Health panel
          on the Insurance/BnB pages will turn green and outreach will start flowing.
        </p>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Setup /></AuthGate>;
}
