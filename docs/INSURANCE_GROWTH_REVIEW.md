# Insurance growth pipeline review

## Scope and current status

Reviewed against main `aa3cbdc6ee1ccb3bec3af44bd73b3454d0c600a4` on 2026-11-11.
Previous outreach-safety and DOT work is already merged (#312, #316). This change
reuses that code rather than adding another sender, research CRM, or dialer.
Source-code presence does not establish production configuration or successful
operation. No production inspection, calling, sending, customer-data import,
credential changes, deployment, or agency authorization is part of this change.

## Existing coverage and remaining work

| Need | Existing source code | Gap / operational hold |
| --- | --- | --- |
| Commercial sourcing | `integrations/providers.py`, `agents/commercial_finder.py`: OSM, Places, Apollo; EverQuote consumer intake | Confirm live source permissions, credentials, freshness and actual success. Public contact data is not outreach consent. |
| Decision-maker contact | `integrations/apollo.py` searches owner/executive titles | Email syntax and title search are not ownership verification. New review records evidence, date, role and multiple phone observations without replacing dispatch contacts. |
| Massachusetts business/renewal data | DOT workspace accepts manually recorded Massachusetts registry observations | No Mass.gov automated adapter. Identify the exact official dataset, permitted uses, access/export rules and record identity. Business formation/registration dates are not policy renewal dates. Do not assume policy identifiers or expiration dates are publicly available. |
| Auto-dial and live-answer transfer | `auto_dial.py`, `integrations/twilio_voice.py`, signed callback routes; Twilio detection can bridge to a configured single producer number | Already implemented, not verified live here. No human-capacity reservation, skills pool or coordinated multi-line dialer. Do not add another dialer or increase concurrency until those requirements pass. |
| Cross-sell | Conversation needs capture and heuristic opportunity scores | New book-review questions use active insurance client records and explicit lead relationships. Missing records do not mean missing coverage. Scores elsewhere remain heuristics, not purchase probabilities. |
| Referrals | `referrals.py`, referral partner agents, weekly scheduler | New questions favor customer-led introductions. Referred-person consent, lineage and conversion attribution still need a separate implementation. Do not assume permission to contact third parties. |
| Funnel measurement | Conversation scoreboard and analytics exist | New distinct-lead counts and matched overlaps avoid dividing repeated conversation rows by unrelated activity. They remain operator-reported and are not verified policy issuance or causal conversion. |

## Added workspace

`/insurance/growth`, linked from Insurance, uses authenticated
`GET /insurance-growth/overview` and
`POST /insurance-growth/leads/{lead_id}/review`.

- A new `insurance_prospect_reviews` table stores a current research snapshot,
  reviewer and monotonic revision. No existing table columns are altered.
  Deployments must verify normal `create_all()` has created the new table before
  enabling the UI. Standard application role access applies; this is not a
  tenant/agency permission boundary or authorization to import another agency's book.
- Only insurance segments are accepted. At most five E.164 contact observations
  can be recorded, with provenance, check time and status. “Verified” explicitly
  means an operator's assertion of name/role/number, not independent verification.
  Research never edits the live lead phone, changes DNC, or queues a message.
- Stale contact evidence (over 30 days) and source evidence (over 90 days) remain
  review flags. Every row retains an authorization/licensed-handler review flag.
  DNC is checked on the lead and alternate observed numbers. Validation rejects
  future observations, missing evidence and duplicate numbers.
- Renewal dates require customer confirmation or authorized policy evidence.
  Registration dates alone cannot satisfy the renewal contract. Do not store raw
  policy documents/numbers, credentials or sensitive customer details in notes.
- Prospect results are a bounded sample: up to 200 recent leads, commercial first,
  then sorted within the sample by suppression and recorded renewal. This is not
  a claim that the globally earliest renewal is in the sample. Pagination and
  agency-scoped intake are future work before use with a large book.
- Active/renewed client records are grouped only by an explicit shared lead ID.
  The output uses all known active lines for those identities, never a guessed
  household/company match from shared phone/email. Suppressed clients have no
  contact questions. Missing insurance lines generate questions, not claims.
- Revision-checked writes prevent stale editors overwriting newer evidence.
  An uncertain save must reload before retry. This is a current snapshot, not an
  immutable history of every evidence revision; immutable audit history is future
  work before relying on the feature as a compliance archive.

## Measurement definitions

The default 30-day UTC window uses `ConversationOutcome.created_at`, limited to
commercial, personal and referral-partner insurance leads. It does not invent
provider attempts absent from structured logging.

- Call attempts: number of recorded call outcome rows, including repeat calls.
- Answered leads: distinct leads with a recorded answered call in the window.
- Quoted leads: distinct leads with `quote_sent=true` in the window. Starting a
  quote is not counted as a delivered quote.
- Sold leads: distinct leads with a recorded `sold` status in the window. Not
  carrier-confirmed issuance and not premium, fee or commission income.
- Answer/quote overlap: leads with both events divided by answered leads.
- Quote/sale overlap: leads with both events divided by quoted leads. Unrelated
  sales are not included in the numerator. A zero denominator is null/N/A.
- These overlap rates do not establish event order, attribution, or a full
  acquisition cohort. Events outside the window do not enter the denominator.
- Source grouping is the **current research source**, not historical acquisition
  channel. Editing evidence can change this grouping. Unreviewed leads remain
  `unattributed` rather than being guessed from their category.

## Gated implementation backlog and acceptance criteria

1. **Massachusetts source adapter**: exact official source and allowed automation
   verified; documented field meanings and freshness; stable company IDs; merge
   conflicts retained; no registration-to-renewal inference; missing/rate-limited
   lookups remain unknown; no contact enqueue from ingestion. Start with an
   agency-approved export or documented public endpoint, not private scraping.
2. **Decision-maker verification service**: permitted provider plus evidence of
   role/number association, freshness and invalid-number feedback. Any promotion
   to the dispatch contact must be separately reviewed and repeat suppression.
3. **Capacity-aware live transfer**: reuse existing Twilio/SignalWire boundary;
   verified destination, available handler and atomic capacity reservation before
   dial; bounded concurrency; cancellation of unused legs; explicit busy/no-answer
   behavior; callback commitments supported by actual capacity. Test competing
   workers, hangups, unknown outcomes and provider retry behavior without live calls.
4. **Calling activation review**: agency permission, jurisdiction-specific scope,
   recipient location/time window, lawful consent/DNC status, recording rules and
   approved source-specific wording must be verified. Unknown state is not proof
   of producer licensing. Existing default settings and generic voicemail wording
   need review before expansion. A cold business prospect must not be told they
   requested a quote unless that request is evidenced.
5. **Handler roles**: staff without a verified producer license are not represented
   as producers and do not receive quote/advice/bind responsibilities. A permitted
   administrative role, if any, needs agency/legal review. Route licensed activities
   to a verified, authorized producer. No individual is newly assigned by this PR.
6. **Referrals and conversion attribution**: distinct opportunity IDs, authorized
   client association, requested introduction/consent, per-stage timestamps and
   source lineage; agency-confirmed issuance, premium, fees and commission recorded
   separately. Never seed anecdotal reported revenue as platform results.

Merge/release remains separate. Nothing here activates a scheduler or changes
existing campaigns, transfer destinations, production secrets or calling defaults.
