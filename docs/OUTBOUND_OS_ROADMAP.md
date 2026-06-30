# Bruno AI Workforce — Outbound OS Roadmap (Instantly + Smartlead vision)

Goal: an **AI Business Operating System** where specialized AI commanders run
insurance, SavoryMind, B&B Global, music, jobs and the foundation 24/7 — the
power of Instantly/Smartlead, specialized to Bruno's businesses.

## Honest framing
Instantly and Smartlead are not one feature — they're years of work, especially
the **email-deliverability infrastructure** (mailbox pools, warmup networks, IP
reputation). Re-building that from scratch is not realistic or wise. The winning
move is: **ride their rails for sending (via API) and build the specialized
AI-agent + CRM brain on top** — which is most of what makes this *yours*.

## What already exists in this app (a lot of the spec)
| Instantly/Smartlead feature | Status here |
|---|---|
| Workspaces per business | ✅ Command Centers (insurance/savorymind/bnb/music/jobs/foundation) |
| Autopilot OFF/MANUAL/SEMI/FULL | ✅ Automation mode + Outreach Autopilot toggle |
| CRM pipeline | ✅ Universal CRM + lead temperature (cold/warm/hot/dead) |
| Lead finder + enrichment | ✅ OSM (free) → Google Places → Apollo (enrich) |
| AI message generation | ✅ per-business prompts + injected skills (cold-email, etc.) |
| Multi-step sequences | ✅ 7-touch follow-ups (value→proof→reframe→…→breakup) |
| AI reply classification + suggested reply | ✅ CLASSIFY_REPLY (intent + draft) |
| Unified inbox | ✅ Outbox + inbound sync (per-account) |
| Multi-channel | ✅ email + SMS (Twilio) + Instagram/social planners |
| Analytics | ✅ Funnel + Growth analytics, Mission Control, Client Engine goal |
| Deliverability guardrails | ✅ daily caps + warmup + real-email guard |
| Lead scoring → send best first | ✅ dispatch orders by Lead.score desc |
| Self-learning loop | ✅ content metrics sync + AI Learnings |

## Shipped now (this PR) — the keystone gap
**Dedicated cold-email sending engine integration (Instantly + Smartlead).**
- `integrations/instantly.py`, `integrations/smartlead.py`, `integrations/sender.py`
  (provider-agnostic selector).
- When an API key + campaign are connected on the Connect page, every lead is
  **handed off to the provider's campaign** (which sends + follows up + warms across
  many inboxes); our AI copy is passed as `personalization`. Falls back to Gmail
  when no provider is connected — zero change until you opt in.
- Gmail caps lowered to consumer-safe levels so a personal Gmail isn't revoked.

This is the durable fix for "send cold email at volume" — exactly the Instantly/
Smartlead core, without re-building deliverability infra.

## Phased build order for the rest (each phase = its own PR)
1. **Mailbox pool + rotation** (Smartlead's strongest feature): let the provider
   hold many inboxes per business; we already hand off per-campaign, so this is
   mostly campaign/account config + a health view. (Provider does the rotation.)
2. **AI Agent from URL** ("Create Agent"): scan a business URL → offer summary,
   ICP, pain points, angles, scripts, sequence. New `agent_builder` module +
   `/agents/create-from-url`. Reuses content/skills stack.
3. **Lead Finder UI**: filter UI over the existing Apollo/Places sourcing
   (state, industry, size, title, rating, reviews) + "Find more like this".
4. **Lookalike search**: domain in → similar companies (Apollo lookalike / Places
   category+geo).
5. **Natural-language campaign builder**: "Find Boston restaurants <4.3 stars…" →
   query + filters + sequence + schedule. LLM → structured campaign spec.
6. **Automation rules engine**: if reply positive → task+notify; opened 3× → warm;
   meeting booked → stop; unsubscribe → suppress forever. Event table + rules.
7. **Unified inbox v2**: per-business reply queues + AI summary + approve/auto-reply.
8. **Revenue analytics v2**: cost-per-lead, cost-per-meeting, ROI per agent/campaign.
9. **Website visitor tracking**: JS pixel → visitor → auto-lead (where legal).
10. **Calendar booking**: meeting links + auto-stop campaign on book.

## Stack alignment (from the vision)
- Instantly/Smartlead → sending engine (✅ integrated)
- Apollo → contact DB (✅), Clay → enrichment (future)
- OpenAI → reasoning (✅), LangGraph → multi-agent (partially; agents/commanders)
- n8n/Make → external automation (future webhook layer)

## Compliance guardrails (must persist through every phase)
Marketing/sales/content only; CAN-SPAM unsubscribe on every send; insurance
NH/MA/FL only; SMS requires prior consent (TCPA); exclude family/personal emails;
no music brand on LinkedIn; aggressive auto-apply stays opt-in + ToS-flagged.
