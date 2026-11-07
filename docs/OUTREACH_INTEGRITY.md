# Outreach suppression and accounting

This branch is stacked on the production-guard branch underlying PR313, which
already includes PR312. It preserves the durable reservation, quota, ambiguous
result and callback-authentication machinery. The DOT workspace in PR314 remains
separate; combine its model/schema additions when reconciling branches.

## Behavior

- Provider reservations check persisted suppression before spending quota and
  again immediately before handoff. The final check holds a PostgreSQL recipient
  advisory transaction lock across the provider call. ORM opt-out, STOP, contact
  suppression and bounce writes acquire the same lock. An opt-out committed before
  handoff prevents the call. An action already handed to a provider cannot be
  recalled by this mechanism. Reads/database errors fail closed.
- Checks cover normalized DNC entries, legacy inbound STOP messages, suppressed
  contact statuses, bounced/complained mail and suppressed outbound mail. Phone
  normalization retains the existing application's last-ten-digit convention.
  Instantly/Smartlead public enrollment adapters now use the existing boundary.
- Generic follow-ups expose eligibility separately from due-date candidates and
  skip replied, terminal, suppressed, bounced and missing/invalid recipients before
  generation. The final boundary rechecks after drafting. UI and action wording no
  longer promise that every due candidate will send.
- Gmail scans all configured mailbox aliases, paginates a fixed time window,
  fetches provider IDs/internal timestamps and parses permanent machine-readable
  delivery-status reports. It includes archived replies, deduplicates by canonical
  mailbox plus provider ID, overlaps the last completed watermark, and never
  advances coverage on partial/failed scans. A scan interrupted during processing
  remains running/incomplete. Page limit is explicit (100 pages), not a healthy zero.
- Ingestion records actual inbound rows and timestamps. Unknown senders and bounce
  reports are separated from matched responses. Legacy outbound Replied flags have
  no reply timestamp and remain explicitly unallocated, rather than fabricated into
  a reporting window. DSNs are conservative suppression evidence requiring review,
  not cryptographic proof of a provider delivery outcome.
- Ingestion does not auto-send, warm-text or subscribe a person to a newsletter.
  STOP requests persist suppression without forwarding. Callback signature checks
  stay in place. Inbound Resend events require an event ID, are idempotent, reject
  changed payloads under one ID, and return retryable failures on processing errors.
  A partially committed processing receipt requires reconciliation instead of
  repeating side effects. Later delivery events cannot erase a bounce/complaint.
- Reporting uses sent_at for recorded sends (including old drafts sent recently),
  UTC day buckets, and separate recorded delivery evidence. Reply coverage and
  legacy uncertainty are explicit. /inbound/health is role-protected and reports
  per-mailbox status, completed coverage and unresolved webhook receipts.

## Review and rollout gates

Do not deploy or run outreach from this branch. Review the two new tables
mailbox_sync_health and inbound_webhook_receipts, merge dependencies, and drain
old writers before rollout: old code/raw SQL writers do not honor these ORM locks.
Review the deliberate removal of automatic outbound side effects from ingestion.

Provider fixtures and disposable PostgreSQL tests are not live-provider validation.
External campaign execution after enrollment and a Mac helper after claim handoff
are outside the app's final controlled provider boundary; existing remote work
requires independent suppression synchronization/reconciliation. Do not claim this
patch can recall work already handed off. Keep those integrations held from launch
until their end-to-end suppression protocol has been reviewed. Existing credential,
callback and worker-drain blockers from PRs312/313 remain in force. No new secrets,
network access rules, callback settings, quota values or live send controls change.

Validation on the final change: 548 backend tests passed against disposable
PostgreSQL16, including real competing-transaction suppression tests; frontend
production build and git diff --check passed. Tests use provider doubles and do
not send customer outreach. Existing callback-authentication and quota tests remain
in the full suite. Live-provider behavior and production rollout are untested.

## Follow-up queue review correction

Review 5812683285 identified a reproducible starvation bug: the first 400 due
rows could remain ineligible indefinitely and hide every later eligible row.
Selection now uses deterministic keyset pages (priority, score, date, UUID), with
`limit` counting eligible candidates rather than skipped rows. Suppressed,
bounced and invalid rows remain pending for review. The reported due count is
candidates actually examined, not the entire backlog. Scanning a mostly blocked
queue can therefore examine more than 400 rows; pages remain bounded in memory.
Regression tests cover 401 mixed blocked rows ahead of eligible work, repeated
runs with a one-candidate budget, and a completed first page disappearing during
flush without skipping the next page. No production queue was processed.
