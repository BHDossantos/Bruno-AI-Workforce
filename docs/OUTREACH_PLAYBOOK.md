# Outreach Playbook — email, SMS & calling

The operator's guide to the outreach engine: how to fire it up, turn on the
optional boosters, and keep your sender reputation healthy. Everything below is
in the app — no code or redeploy needed.

## Go-live sequence (do this once, in order)

1. **Merge the PR + let it deploy** (a few minutes).
2. **Insurance Leads → "Test to my inbox"** — enter your email. You'll receive
   the exact AI email your hottest lead would get. Read it; make sure it sounds
   like you. This sends nothing to leads.
3. **Insurance Leads → "Remove duplicates"** — clears any duplicate leads from
   earlier re-imports. Keeps the most-worked copy of each. Safe to run anytime.
4. **Insurance Leads → "Send all pending"** — fires the outreach. Sends the
   highest-priority drafts now (hot → warm → cold), held under your daily cap so
   a fresh domain isn't spam-flagged. Anyone on Do-Not-Contact is skipped.
5. **Watch it work** — Email Outbox shows messages moving to "Sent"; the
   Deliverability page shows sent-today vs cap and your reputation.

That's the whole daily loop. The 9:30am & 3:30pm cron also sends automatically,
so leads never sit un-worked.

## Importing leads

**Import Options** (sidebar) → pick the list type:
- **Insurance leads** — your Thrust Insurance book.
- **BNB leads** — B&B Global consulting prospects (sent from the BnB mailbox).
- **SavoryMind leads** — restaurant prospects.
- **Contacts** — a Google/iPhone export → warm personal intros.

CSV needs an **email** column; **phone** is optional but required for calling.
Import is instant — the AI writes and sends on the paced schedule afterward,
never during the upload. **Re-importing the same list updates existing leads
instead of duplicating them.**

## Sender reputation (keep email out of spam)

- The **Deliverability** page shows your 7-day **bounce rate** (keep < 2%) and
  **complaint rate** (keep < 0.1%), plus how many bad addresses were suppressed.
- **Hard bounces and spam complaints auto-suppress** the address — it's never
  emailed, texted, or called again. You don't have to do anything.
- The **daily cap ramps** on a new domain, then settles. Don't raise it manually
  to blast a backlog — that's what gets domains flagged.

## Optional boosters (Setup → ⚡ Outreach automation)

Both are **OFF by default** — turn on when ready:

- **Auto-reply to interested leads** — when a lead replies that they're
  interested, instantly send the AI reply *with your booking link* (instead of
  only drafting it). Only fires on clearly-interested replies; everything else
  still drafts for your review.
- **SMS follow-up to non-repliers** — text leads who were emailed but never
  replied, a couple days later. **Requires A2P 10DLC registration** with your
  texting provider first, or carriers block the texts. Manual run anytime:
  Insurance Leads → "Text non-repliers".

## Do Not Contact (opt-outs)

**Setup → 🚫 Do Not Contact.** Enter an email and/or phone and click Add — that
contact is blocked on email, text, AND calls immediately. Remove an entry with
the ✕ if it was added by mistake or a bounce later recovered. STOP texts and
spam complaints also add people here automatically.

## Calling

Calling routes through whichever provider is connected (SignalWire / Plivo /
Vonage / the self-hosted softswitch), selectable in Setup via **Voice provider**.

**The #1 thing that decides whether calls ring vs. go to voicemail is carrier
reputation (STIR/SHAKEN attestation) — not the app.** To make calls ring:
1. Get **higher attestation** from your carrier (SignalWire sent a DocuSign form
   for this — sign it).
2. **Register your number** at freecallerregistry.com (covers Hiya / TNS /
   First Orion).
3. Warm the number: start low-volume, longer talk-times.

The **Call List** shows a calling-health strip (connect rate, provider, daily
cap). Transfer-to-cell stays OFF until a number reliably rings.

### Self-hosted softswitch (optional, "build our own")

If you run your own FreeSWITCH + a bring-your-own-carrier SIP trunk (see
`deploy/softswitch/README.md`): set **Voice provider = sip** in Setup, fill the
softswitch fields, and click **Test connection** to confirm the app reaches
FreeSWITCH and the trunk is registered before placing a real call. The same
attestation/registration rules above still apply — the softswitch controls the
call, not the carrier's reputation.

## Troubleshooting

- **Import spinning / slow** → you're on the old version; the instant importer
  ships with this PR. After it deploys, imports return in ~1 second.
- **"Send all pending" errors / times out** → almost always a huge duplicate
  backlog. Run "Remove duplicates" first; the paced sender then works in
  capped batches.
- **Emails sending but going to spam** → check the Deliverability reputation
  card; if bounce/complaint is high, slow down and let suppression clean the
  list.
- **Calls go to voicemail** → carrier attestation, not the app. Sign the
  attestation form + register the number (see Calling above).
