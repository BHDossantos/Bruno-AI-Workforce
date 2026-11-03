# Durable outbound actions — draft, not rollout approval

PR #312 is separate from mobile PR #311. Development and testing do not restart a
scheduler, change autopilot/settings, send real outreach or deploy production.

## What is protected

A PostgreSQL transaction reserves an operation and recipient before a provider call.
The reservation survives caller rollback and process exit. Unique constraints choose
one worker; pending and unknown holds never expire or requeue themselves. Different
accounts/providers cannot bypass a recipient hold. Email addresses are trimmed and
case-normalized; phone transports share normalized phone scopes. SMS/WhatsApp share a
scope, as do automatic/manual calls.

Public Gmail, Resend, SendGrid, SMTP report-mailer, SMS, Plivo, WhatsApp Cloud, Twilio
WhatsApp and voice transport entry points use the guard. Nested adapters reuse an
existing matching reservation instead of reserving twice. Automatic calls use the same
recipient/day key through the dispatcher or direct adapter. Bridge, recording and test
calls use purpose/payload/day keys. Private transport primitives are not public retry
APIs and must not be called directly by new features.

Outbox and approval sends share message-ID keys and row locks. Bulk email/SMS sends
skip locked rows. A competing request cannot overwrite Sent with Needs Review.
Legacy direct email/SMS calls without explicit operation keys permanently deduplicate
identical payloads. An intentional later identical action requires a new stable intent;
never generate a fresh intent merely to retry a timeout. Automatic calls are limited
to one accepted attempt per normalized number/UTC day, suppressing same-day cadence
waves. Manual call purposes with identical payloads are deduplicated for that day.

Resend -> SendGrid -> Gmail preference remains after explicit rejection. HTTP 408,
409, 5xx, exceptions and missing receipts stop fallback. SMS also stops carrier
fallback after uncertainty. Gmail failure cannot trigger SMTP. A configured carrier's
failed SMS cannot be queued to the Mac bridge. Provider acceptance is not confirmed
inbox/phone delivery. Boolean-only SMTP/bridge APIs retain an explicitly local
acceptance reference, not a fabricated carrier receipt.

## Shared daily budgets

The `outbound_quotas` row atomically reserves capacity with the operation and hold.
Email uses the existing ramp-aware global email cap; SMS and WhatsApp share the SMS
cap; all guarded calls share the stricter configured call/auto-call cap. Budgets use
UTC days across accounts/providers/processes. They count logical attempted actions,
including rejected, uncertain, and bridge-handoff actions. Fallback HTTP requests
within one action and multiple carrier call legs are not separate budget units.

Replays do not consume capacity. Failed/uncertain actions and operator resolutions
never refund it. Database failure prevents a call. The lowest cap observed by a worker
for that UTC day wins, so a stale higher cap cannot reopen capacity. Raising a cap only
takes effect on a later UTC day; lowering it cannot undo already-issued actions.

Initial counters conservatively include recorded outbound messages with `sent_at`
that day. This is not proof of historical actions from old/unlogged writers. Provider
billing, per-mailbox limits, browser-originated calling and third-party campaign
execution are not globally metered by this ledger. Existing UI/compliance limits
remain additional gates, not substitutes for the atomic shared budget.

## Mac bridge protocol

`GET /bridge/outbox` now claims explicitly Queued messages once, using row locks and
committed durable reservations. It never steals carrier Drafted messages. A claim
consumes quota, observes the existing texting checks and changes the item to Needs
Review pending the helper result. The response carries an opaque per-claim token;
only its hash is stored. Lost responses/crashed helpers leave a pending hold rather
than making the text available to another helper.

`POST /bridge/sent` requires that token and records accepted or unknown. ACK replay
cannot send anything; an invalid claim cannot update the message. Accepted releases
the hold; unknown stays held. The updated helper selects iMessage or SMS BEFORE its
single send. It never falls back after a send error, reports timeouts as unknown, and
refuses to send when the server does not supply a durable claim. Upgrade server and
helper together with all old helpers stopped. Do not run mixed helper versions.

## Operator reconciliation

Outbox's Review held deliveries panel is for authenticated admins/operators. It shows
recipient, account, channel, time, operation reference and history. Recipient/account
are now stored for usable reconciliation; payload bodies and credentials are not.
Evidence/history access uses the same role gate; claim secrets are never returned by
this operator API. Keep evidence free of credentials and unnecessary personal data.

1. Verify the original intent, recipient and provider records/support case.
2. If uncertain, record evidence and **keep held**. Missing records are not proof that
   nothing was sent; a timed-out provider may still complete.
3. For an `unknown` or `rejected` completed attempt, record provider-confirmed
   acceptance with its receipt, or affirmative provider-confirmed non-acceptance.
   The server records actor/evidence/reference and checks the expected current state
   under a row lock. Competing decisions cannot both resolve the same state.
4. Accepted message intents update their Outbox item to Sent; confirmed non-acceptance
   becomes Not Sent. The original key remains consumed. Resolution never sends,
   retries, turns the item into a draft, or refunds quota. A separate intentional new
   action is possible only after that recipient hold has been released.

The API cannot independently verify an operator's provider evidence. Pending attempts
may still have a worker capable of sending, so the panel can only append evidence for
them; it cannot release their holds, regardless of age. Orphaned pending actions need
an approved drained-worker maintenance procedure and authoritative provider evidence.
No generic force-unlock/expiry endpoint is provided. This remaining operational gate
is intentional, not a claim of completed unattended recovery.

## Rollout and drain procedure — instructions only, not executed

1. Inventory all old API workers, schedulers, external cron clients, browser calling,
   campaign engines and Mac helpers. Confirm the intended service/DB with the owner.
   This task defers Render and production operations.
2. Arrange an explicitly approved maintenance window. Stop new outbound ingress and
   every old scheduler/helper/cron writer; drain in-flight requests and provider work.
   Verify old worker processes/containers and cached bridge batches are gone. Merely
   pausing the scheduler or waiting out a lease does not prove old writers are gone.
3. Reconcile pre-cutover ambiguous actions from provider evidence. If uncertainty or
   an uncontrolled sender remains, keep the affected channel stopped. Prefer a fresh
   UTC-day cutover after the drain; otherwise inventory and conservatively account for
   every historical action, including those absent from Message records. The app
   cannot reconstruct unlogged sends.
4. Apply the full new-table schema before admitting any sender. Existing application
   tables retain their columns. This draft adds fields to its own new attempt table;
   `create_all` will not upgrade an installation of an earlier draft schema. Such an
   installation needs a reviewed additive migration. Do not deploy an intermediate
   draft and assume later `create_all` alters its tables.
5. Update the Mac helper while stopped. In an isolated staging DB with fake providers,
   test multiple workers/helpers, crash before/after handoff, result-store loss,
   exhausted quotas, unknown holds, operator evidence and duplicate ACKs.
6. Confirm the owner accepts permanent holds, intent/day dedupe, shared call limits,
   reduced scheduler concurrency and operator workload. Resume only updated writers
   through a separately approved operation; observe claims, quota and provider records.
7. On trouble, stop outbound work. Do not roll back to old sending binaries while
   claims/holds exist: they ignore this ledger. Preserve evidence; never clear holds
   because they are old or to make a dashboard green.

## Remaining limits

Scheduled jobs share one PostgreSQL session advisory lock and skip overlaps, so
throughput can decrease. Connection loss is not a fencing token. Provider reservations
protect covered calls, but old binaries, browser softphone/provider-executed call
legs, third-party campaigns after enrollment, publishing, external scripts/private
transport calls and provider-internal duplication remain outside the guarantee.
Provider credentials, consent/DNC policy, legal eligibility and store signing are not
established by these tests. No exactly-once delivery or production/store readiness
claim is made.

## Validation

Real disposable PostgreSQL 16 and mocked providers. Prior draft: 391 full backend tests
passed. Extension includes separate-process quota competition, nested boundaries,
cross-account/provider holds, stale-cap races, operator resolution races, pending
worker protection, bridge claim competition/ACK ownership and Mac fallback checks.
Final local full suite: 411 passed (49 concurrency/provider/reconciliation tests plus
362 existing tests). Next.js production build passed. Hosted CI is recorded in the
PR. No live providers were called; actual macOS Messages and native devices still
require controlled testing.
