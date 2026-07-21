# A2P 10DLC Registration — Ready-to-File Application

This is everything you need to register for **A2P 10DLC** so the app can legally
text leads at scale from a US 10-digit long code. Copy each field into your
carrier / provider portal (Twilio, Telnyx, Plivo, Bandwidth, or The Campaign
Registry directly). Fields in `[brackets]` are the only ones you fill in from
your own records.

> **Why this is required:** US carriers filter unregistered application-to-person
> texts. Until the Brand + Campaign below are **approved**, your SMS drafts will
> queue but carriers will silently drop them. Email and calling do **not** need
> this — you can go live on those today.

---

## Step 1 — Register the Brand (your business identity)

| Field | Value |
|---|---|
| Legal company name | **B&B Global Services LLC** |
| DBA / brand name | **Thrust Insurance** |
| Business type | Limited Liability Company (LLC) |
| Country of registration | United States |
| EIN / Tax ID | `[your 9-digit EIN from your LLC formation / IRS letter]` |
| Business address | `[your registered business street address]` |
| Website | `[your business website, e.g. https://thrustinsurance.com]` |
| Vertical / industry | Insurance |
| Business contact name | Bruno Dos Santos |
| Business contact email | brunodossantos707@gmail.com |
| Business contact phone | `[your business phone]` |
| Stock symbol / exchange | N/A (privately held) |

**Brand type to select:** *Standard / Low-Volume Standard* (not Sole Proprietor —
you have an EIN, which gets you a better trust score and higher throughput).

---

## Step 2 — Register the Campaign (what you'll send)

| Field | Value |
|---|---|
| Campaign use-case | **Mixed** (or *Customer Care* + *Marketing* if asked to pick) |
| Campaign description | Insurance agency following up with consumers who requested an auto/home insurance quote through a lead marketplace (EverQuote). We reply to their inbound quote request, share quote details, verify discounts, and schedule a call. Recipients have expressed interest in insurance and consented to be contacted about their quote. |
| Sample message 1 | `Hi Sarah, it's Bruno with Thrust Insurance. I finished reviewing your 2022 Toyota Camry quote and found a few discounts to verify. Reply or call when you have 2 minutes — thanks! Reply STOP to opt out.` |
| Sample message 2 | `Hi Sarah, this is Bruno, your licensed insurance producer. I just tried reaching you regarding the insurance quote you requested. I already have most of your information and may have found additional discounts for you. Reply or call me at (XXX) XXX-XXXX. Reply STOP to opt out.` |
| Sample message 3 | `Hi Sarah, just checking in to see if you had any questions about the quote I prepared. Happy to explain anything or make adjustments. No pressure. Reply STOP to opt out.` |
| Message flow / CTA | Consumers submit an auto/home insurance quote request on EverQuote (a licensed lead marketplace), consenting to be contacted by matched insurance agents. Thrust Insurance receives the lead and texts the consumer about the quote they requested. |
| Opt-in type | **Third-party / lead marketplace** (consumer opted in on EverQuote's form) |
| Opt-in keywords | N/A (opt-in captured at the EverQuote quote form, not via keyword) |
| Opt-out keywords | STOP, STOPALL, UNSUBSCRIBE, CANCEL, END, QUIT |
| Opt-out message | `You have been unsubscribed from Thrust Insurance texts and will receive no further messages. Reply HELP for help.` |
| Help keyword | HELP |
| Help message | `Thrust Insurance: for help call [your business phone] or email brunodossantos707@gmail.com. Msg & data rates may apply. Reply STOP to opt out.` |
| Subscriber opt-in? | Yes |
| Subscriber opt-out? | Yes |
| Subscriber help? | Yes |
| Embedded links? | No (or Yes if you add a booking link — must be a branded domain, not a public shortener) |
| Embedded phone numbers? | Yes (your callback number) |
| Age-gated content? | No |
| Direct lending / financial? | No |

**These sample messages match what the app actually sends** — the opener, the
missed-call follow-up, and the check-in, all now ending in "Reply STOP to opt
out." Keep them in sync: carriers reject campaigns whose live traffic doesn't
match the registered samples.

---

## Step 3 — Proof of opt-in (have this ready if reviewed)

Carriers may ask how the consumer consented. Your answer:

> Consumers request an insurance quote on EverQuote's website and agree to
> EverQuote's terms, which include consent to be contacted by matched licensed
> insurance agents (by phone, text, and email) about their quote. Thrust
> Insurance purchases these opted-in leads and contacts the consumer about the
> specific quote they requested. Keep the EverQuote lead record (timestamp,
> consumer info, TrustedForm/consent certificate if provided) as proof.

Ask EverQuote for the **TrustedForm** or **consent certificate URL** on each lead
— that's the strongest opt-in proof if a carrier ever audits.

---

## Step 4 — After approval

1. Buy / assign a **10DLC long code** number and link it to the approved campaign.
2. In the app: **Setup → connect your texting carrier** (enter the number + API
   credentials). The autopilot readiness check (**Setup / control → autopilot**)
   will flip the **SMS** row to **green**.
3. Turn on the cold **SMS follow-up** opt-in if you want emailed-but-silent leads
   texted automatically (it's off by default until A2P is live).

Once green, the same hourly 8am–8pm pass that sends emails will also send the
queued texts — hot leads first — capped and opt-out-safe.

---

## Compliance guardrails already enforced by the app

- **STOP is permanent:** any lead who texts STOP/UNSUBSCRIBE/etc. is suppressed
  and can never be re-texted (checked before a draft is even queued).
- **Do-Not-Contact list** is honored across every channel.
- **Texting hours** (8am–9pm local) and a **daily send cap** are enforced at send
  time.
- **Opt-out language** is now included in the first message of every SMS thread.

_Not legal advice — confirm your specific obligations (TCPA, state insurance
marketing rules) with your compliance counsel._
