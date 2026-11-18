# Integrated Workforce review candidate

Combines outreach integrity PR315 at f5cf53ef5079fd700631977fb2356044be85cebe
(including PR312/313) with DOT workspace PR314 at
18f9446536cf62e13e942bfc0edde6306769a163.

Resolved append conflicts in backend/app/models.py and backend/db/schema.sql by
preserving both sets of additive tables: outbound reservation/policy/quota/health/
receipt tables and DOT cases/owned sender signatures. No column or existing data
was removed. Main router additions merged without conflict. DOT sending remains
disabled, including the existing gateway/reservation readiness gates; combining
code does not activate Gmail, vendor access, campaigns, calls or messages.

Validation on this combined tree: 619 backend tests passed against disposable
PostgreSQL16 with mocked providers; frontend production build generated 74 pages;
diff checks passed. No production database or sender was exercised.

The integration is reviewable, not approved as operationally safe to deploy.
Render auto-deploys main. The legacy Cloud Run workflow also runs after main CI
if its credentials are configured; confirm it cannot start an unaccounted sender.
Stop and drain old API/scheduler/cron/helper writers, reconcile historical queues
and provider ambiguity, verify recoverable data and full additive schema, validate
production credentials and callback compatibility, and retain outbound pause during
deployment and verification. External campaign work and already claimed helper
batches need separate reconciliation. Never roll back to an old active sender
that ignores the new reservation ledger.

Do not merge PR314 and the stacked PRs separately just because their individual
CI is green. This branch records the tested integration for coordinated review;
it changes no production settings, credentials, quotas or sender activation.
