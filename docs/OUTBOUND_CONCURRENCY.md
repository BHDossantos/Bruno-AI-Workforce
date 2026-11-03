# Durable outbound reservations (draft; not deployment approval)

This branch is separate from mobile PR #311. No live service, scheduler, autopilot,
credentials, or production database was changed while implementing it.

## Guarantees and state

The new `outbound_attempts` and `outbound_holds` tables are created by the existing
`create_all` startup step. No existing table columns change. Provisioning must finish
before workers resume. If tables/DB are unavailable, guarded sends fail closed.

A PostgreSQL transaction reserves the operation key and recipient scope BEFORE
invoking a provider. Independent transactions mean caller rollback cannot erase the
reservation. Concurrent workers compete through unique constraints, not process-local
locks. Successful repeated message sends replay the stored provider ID without
contacting the provider. Reusing a key with a different payload is held.

- `pending`: reservation exists; worker may still be running or may have crashed.
- `accepted`: provider returned a receipt and the reservation store recorded it.
  This is acceptance, not inbox/phone delivery confirmation.
- `unknown`: timeout, exception, server error, missing receipt, or ambiguous result.
- `rejected`: an explicit provider rejection; this operation remains non-retryable,
  but the recipient is released for a separate, intentional operation.

Pending/unknown attempts keep a recipient hold, including across a restart or new
operation key/day. They NEVER expire automatically. A crash before sending may thus
hold an unsent message; availability is deliberately traded for duplicate prevention.
If recording the result fails after sending, the original pending row remains held.

## Covered paths and user-visible changes

- Outbox send and bulk email drafts share stable message-ID keys. Already-Sent
  historical messages return without resending. Held bulk items show `Needs Review`;
  single-send errors return 409 with a reconciliation reference instead of suggesting
  a retryable provider failure.
- Direct dispatch uses account + recipient + UTC-day intent, matching the existing
  same-day outreach policy; different payload on that intent is held. Campaign
  enrollment is durably reserved as a separate channel.
- Auto-call dispatch is shared by the dialer, EverQuote cadence, and manual auto-call
  endpoint: at most one accepted automatic call per normalized number/UTC day.
  This deliberately suppresses later same-day cadence waves. Replays do not report
  a new call to the caller or create another call log.
- Legacy `deliver()` calls without an explicit intent key deduplicate identical
  content permanently; intentional identical later sends must use a new stable
  message ID. Never generate a fresh UUID merely to retry an uncertain send.
- Resend -> SendGrid -> Gmail preference is preserved after explicit rejections.
  Timeouts, HTTP 408/409/5xx, exceptions and missing receipts stop fallback. Gmail OAuth
  failure no longer triggers an SMTP send that could duplicate acceptance.
- Scheduled jobs share a dedicated PostgreSQL session advisory lock. Another job
  skips rather than running concurrently, including different scheduled jobs.
  Skipped jobs wait for their next schedule; this can reduce throughput. Unlock
  failures invalidate the connection so a locked session cannot return to the pool.
- Admin/operator `GET /messages/delivery-attempts` exposes a read-only reconciliation
  queue. It returns hashes, channel/state/timestamps, not message bodies or recipients.

## Reconciliation and rollout gates

This PR intentionally exposes NO automatic retry/unlock endpoint. An authorized
operator must correlate the attempt reference with the original message and provider
records. Confirm recipient, intent and provider acceptance; never clear a hold simply
because it is old. If provider acceptance cannot be determined, keep it held. A later
administrative reconciliation workflow should record evidence and reviewer identity,
atomically resolve the attempt and release its hold; that workflow is not supplied.

Do not deploy this draft to the active insurance scheduler yet. Before rollout:

1. Verify active service/workspace, workers, provider configuration and all live sender
   entry points. Drain/stop old writers through an explicitly approved operational
   procedure: old binaries ignore these reservations and can overlap new writers.
2. Exercise tests with PostgreSQL and mock providers, including concurrent instances,
   crashes before/after acceptance, commit failure, missing schema and restart overlap.
3. Confirm owners accept held-delivery behavior, reduced scheduler concurrency and
   once-per-day automatic calls. Complete an operator reconciliation procedure.
4. Cover remaining paths before claiming global duplicate protection: direct provider
   adapter callers, manual bridge/test/recording calls, SMS, third-party campaign
   engines after enrollment, publishing and external cron jobs bypassing `_with_db`.
   Existing direct SMS carrier fallback is not changed by this PR.
5. Audit capacity controls separately: per-recipient claims do not atomically reserve
   global daily quota across manual/external workers. Scheduler lock loss is not a
   fencing token; supported provider claims remain the second line of defense.

This is NOT exactly-once delivery, a guarantee about old workers, or proof that a
provider never duplicates internally. No store readiness or release-signing claim.

## Validation

Local PostgreSQL 16 with mocked providers: unchanged baseline 362 passed; final full
backend suite 391 passed. The focused concurrency/adapter suite has 29 tests, covering
worker races, process exit/restart, caller rollback, result-store failure, replay,
missing receipts, timeouts, conflicts, server errors and explicit rate-limit rejection.
Single/bulk Outbox integration tests verify that concurrent sends preserve Sent state.
Test-owned message rows are cleaned up so they cannot contaminate the shared suite.
Next.js production build passed. No live provider calls, production scheduler
restarts, or deployments were performed.
