# Duplicate insurance follow-ups, 2026-11-06

Production evidence (read-only Render logs and SQL): at 16:20 UTC, 34 Sent
email rows for 17 distinct recipients and 34 provider IDs. Each pair was drafted
in transactions at 16:00:00.003653 and 16:00:00.24226. Logs show both scheduled
FollowUpAgent and the followups worker at 16:00. Both call process_due_followups,
which selected unfinished rows without mutual exclusion. At 16:20 the hourly
flush sent the resulting duplicate drafts via Resend (SES transport). This was
Bruno AI Workforce bruno-backend, not a separately identified campaign service.
The insurance Drafted/Approved email queue was empty at 17:18 UTC.

This patch removes only the redundant scheduled agent, retaining the enrolling
followups worker and explicit agent entrypoint. The engine acquires a
nonblocking PostgreSQL advisory lock on a separate connection, so overlapping
manual/cron/agent invocations return without processing and dispatcher commits
cannot release the lock prematurely. Release failures invalidate the connection.
No schema, credentials, other schedules, or business switches change.

Two confirmed non-prospect destinations from this incident are rejected by the
existing dispatch and draft-flush address validator using exact-address matches.
No domain-wide suppression, deletion of leads, or rewriting of sent history.

Validation: seven isolated regressions cover scheduler scope, exact recipient
filtering, simultaneous invocations, busy locks, commit isolation, error release,
and invalidation. An additional PostgreSQL integration test runs in hosted CI.
This prevents the observed concurrent-controller failure; it does not claim
exactly-once sending across crashes after a provider accepts a request. Durable
outbound reservations and ambiguous-result reconciliation remain in PRs 312/313.

Release must verify current main/head, CI, live service revision, and no active
outbound processing before restart. Do not force a queued message resend to test.
Verify startup registers one follow-up controller and observe subsequent logs.
Reverting this patch restores the known defect; containment should be assessed
before rollback. No production change has been made merely by publishing this PR.
