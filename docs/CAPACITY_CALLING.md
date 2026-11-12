# Capacity-aware insurance calling

This increment is OFF by default (`AUTO_DIAL_CAPACITY_ENABLED=false`). It makes
no live calls, changes no production configuration, and introduces new tables
only. Do not enable until the release checks below are complete. It is not a
predictive dialer: each outgoing leg reserves one verified, available handler.
Multiple handlers permit multiple concurrent legs, never more legs than handlers.
With one available handler only one leg can be outstanding.

## Flow

1. Admin records a handler's verified destination, licensed states, agency/license
   evidence reference and expiry (max 90 days). This is an operator assertion,
   not a license lookup. No person, including Liz, is assumed licensed.
2. Admin provides a 15-minute-or-shorter availability heartbeat. Missing/stale
   availability means no capacity. The API does not start calls.
3. Admin records per-lead authorization evidence, exact current phone, verified
   state AND IANA timezone, and expiry. Unknown state/timezone means no call.
4. Existing scheduler gates, DNC/opt-outs, daily quota and outbound deduplication
   remain. Recipient local time must additionally be 09:00–20:00. Local law and
   agency review may impose tighter restrictions; this is not a legal clearance.
5. A database transaction atomically reserves an available handler and lead before
   submitting through the existing outbound guard/Twilio path. Successful call
   logs are committed before processing another lead. No new sender is created.
6. Signed callbacks route only confirmed human answers to that reserved handler.
   Unknown/machine answers hang up without a voicemail or false quote claim.
   No new recording is introduced. Busy/no-answer has no unsupported callback
   promise. Parent terminal callback frees the handler. Late callbacks cannot
   reopen a terminal reservation or free a newer call's handler.
7. Unknown provider outcomes hold indefinitely for reconciliation, never expire
   into an automatic retry. A call blocked before provider submission releases
   only the unused new capacity reservation, not the old outbound attempt.

## API

- POST `/calls/capacity/handlers`: admin-only; phone, states, authorization_ref,
  expires_at. Updating a busy handler is rejected. Starts unavailable.
- POST `/calls/capacity/handlers/{id}/availability`: admin-only; seconds 0–900.
- POST `/calls/capacity/leads/{id}/permission`: admin-only; phone, state,
  recipient_timezone, authorization_ref, expires_at. No outreach queued.
- GET `/calls/capacity/status`: authenticated unresolved reservation view (200 max).
- `/amd`, `/transfer-result`, `/status`: authenticated Twilio callbacks only.

## Release holds / limits

- Owner merges a reviewed draft PR. Deploy through the current Render path, NOT
  the obsolete Google Cloud workflow. Verify create_all created the new tables.
- Twilio only in this mode: other providers are held until their signed capacity
  callbacks are implemented and tested. Old default behavior is unchanged when
  capacity mode is off. When on, unreserved legacy auto-call and dispatcher
  manual bridge routes are blocked so they cannot silently compete for capacity.
- Audit any direct provider/test/browser-softphone paths and external dialers
  before activation; they must not use the reserved handler concurrently.
- Verify actual Trust data/source authorization, applicable calling permissions,
  DNC and opt-out import, recipient jurisdiction, agency authorization and licensed
  handler evidence. No live data or credentials were added by this change.
- Test real PostgreSQL contention, signed provider callbacks, hangup/cancellation,
  destination reachability, production schema and end-to-end behavior in an
  approved sandbox before any real campaign. No live-call QA has been performed.
- Availability heartbeat is an administrative API, not a producer UI. Unknown
  provider outcomes require provider-side reconciliation before administrative
  release tooling is added; no unsafe override/timeout release exists here.
- No speculative extra legs: therefore no unused sibling-leg cancellation is
  required. This deliberately does not implement multi-dial-to-one-producer
  behavior that could abandon simultaneous live answers.
