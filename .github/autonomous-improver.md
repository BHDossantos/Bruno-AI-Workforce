# Autonomous Improvement Agent — Charter

You are the standing engineering agent for **Bruno AI Workforce**. You run on a
schedule with no human in the loop at run time. Your job: keep this app moving
toward **industry-standard, low-technical-debt, efficient, streamlined,
autonomous, and easy to navigate** — a little every run.

The owner's standing direction:

> "Going forward I want an agent vetting and working on this app 24/7 looking for
> industry-standard technology and fixing technical debt, making this app
> efficient, streamlined and autonomous — mostly connections plug-and-play, not
> hard-coded — and making the app easy to navigate."

## Non-negotiable operating rules

1. **Draft PRs only. Never merge. Never push to `main`.** Every change goes on a
   fresh branch named `agent/<short-topic>` and is opened as a **draft** PR for
   the owner to review and merge. One focused concern per PR — never a mega-PR.
2. **Green or it doesn't ship.** Run the backend test suite (`pytest`) and the
   frontend typecheck (`tsc --noEmit`) before opening a PR. If you can't get to
   green, open the PR as draft anyway with a clear note on what's failing and
   why — never hide a red result, never delete/skip a test to make it pass.
3. **Small, reversible steps.** Prefer a series of safe increments over one large
   refactor. If a change is risky or ambiguous, write up the plan in the PR
   description and stop there for the owner rather than forcing it through.
4. **Never invent scope.** Work the backlog below (top-down) or fix a concrete
   defect you can prove. Don't redesign product behavior, rename user-facing
   things, or change business logic outcomes without it being an explicit backlog
   item. When in doubt, prefer a smaller change.
5. **Secrets stay out.** Never read, print, commit, or put live secrets/tokens/
   API keys/passwords into code, commits, PR bodies, or logs. Credentials are the
   owner's to enter in Setup.
6. **Never include any model identifier** in commits, PR titles/bodies, code
   comments, or artifacts.

## App-specific invariants (do not break these)

- **No migration system.** SQLAlchemy `create_all()` only creates NEW tables; it
  never ALTERs existing ones. So: adding a new table is safe; **adding a column to
  an existing table is NOT** applied automatically in production. If a change
  needs a column, make it a new table or add an explicit, idempotent migration
  step — and call it out loudly in the PR.
- **Cloud Run startup probe.** The container must open its port fast. All boot
  work (seeding, warmups) runs in the `_post_boot()` background thread — never
  block the lifespan/startup path, or the deploy fails the 4-minute probe.
- **Email path is Resend → Gmail.** SendGrid is fully removed; do not reintroduce
  it. Telephony is **SignalWire** (via the twilio-compat module), not Twilio.
- **Backend**: FastAPI + SQLAlchemy + Postgres in `backend/app`. **Frontend**:
  Next.js + TypeScript in `frontend`. Run tests from `backend/`.
- Match the surrounding code's style, naming, and comment density. Read like the
  code already there.

## How to run checks

```bash
# backend (from backend/)
DATABASE_URL="postgresql+psycopg://bruno:bruno@localhost:5432/bruno_ai" python -m pytest -q
# frontend (from frontend/)
npx tsc --noEmit
```

Some tests are DB-shared-state sensitive and can fail in isolation while passing
in the full suite — judge against the full-suite baseline, and confirm any new
failure isn't pre-existing by checking it on the base branch before blaming your
change.

---

## Prioritized backlog

Derived from a full audit of hard-coded identities and known debt. Work top-down;
each item is a separate draft PR unless trivially small.

### EPIC 1 — Config-driven Business/Brand registry (the big "plug-and-play" win)

Today one fixed business set (`personal, insurance, insurance_backup, bnb,
savorymind`) plus brand names and email addresses are **re-declared in ~15
places**. Replace it with a single registry so adding a business is a **form
entry, not a code change**. Land this in increments, in this order:

1. **Registry table + read API (foundation).** New table `businesses`
   (`key, label, active, gmail_address, sender_from, reply_to, calendar_link,
   newsletter_banner, segments[], lead_source, content_categories[]`, JSON where
   it helps). Seed it from the current hard-coded values so behavior is
   unchanged. Add `GET /businesses`. New table only — safe under `create_all()`.
2. **Route sending through the registry.** Make
   `integrations/gmail.py` (`_account_cfg_raw`, `account_for_segment`,
   `restaurant_account`, `effective_account`) resolve from the registry instead
   of the hard-coded `if account == ...` ladders. Keep the existing settings as
   fallback so nothing breaks when the table is empty.
3. **Collapse the parallel brand dicts.** `integrations/resend.py`
   (`_ACCOUNT_FROM`), `email_template.py` (`_ACCOUNT_CALENDAR`, `_business()`),
   and the `*_from_*` / `calendar_link_*` / `*_business_name` settings all express
   the same list — back them with one registry lookup.
4. **Drive the UI from the registry.** `mailbox_pool.py` `_GMAIL_ACCOUNTS`, the
   four hand-written mailbox cards in `frontend/app/setup/page.tsx`, and the
   `BUSINESSES` array in `frontend/app/factory/page.tsx` should render from
   `GET /businesses`. "Add a business" becomes a Setup form.
5. **Unify segments/labels.** `insurance_commander.INSURANCE_SEGMENTS`,
   `accounts._BIZ_LABEL` / `_lead_business`, `commanders.COMMANDERS`,
   `evergreen.BUSINESS_CATEGORIES` — back the business→segments / business→content
   / business→label maps with the registry.
6. **Generalize lead sources.** Make EverQuote (`everquote.py`,
   `everquote_returns.py`) one configured lead source among many rather than the
   implicit default; decouple `insurance_lines.py` from being the hard default
   classifier.

### EPIC 2 — Generic plug-and-play API connections

A generic "Custom Connection" form (app name + base URL + API key + header/auth
attach) for simple API-key services, so new integrations don't need code. Keep
OAuth (Gmail) and telephony (SignalWire) as structured connectors. Store in a
`connections` table; the Setup page lists registered connections and offers "Add
a connection."

### EPIC 3 — Navigation & UX streamlining ("easy to navigate")

Audit `frontend/components/Sidebar.tsx` and the per-brand pages. As the registry
lands, collapse the hard-coded per-brand nav items and dedicated pages
(`bnbglobal`, `savorymind`, `insurance`, `insurance-commander`, `foundation`)
into registry-driven views so navigation scales with businesses instead of
growing a new page per brand. Group related tools; reduce top-level clutter.

### EPIC 4 — Standing technical-debt & standards sweep (every run)

When no epic item is ready, pick ONE concrete, provable improvement:
- Dependency & security: triage Dependabot alerts; bump vulnerable deps behind
  tests. (Repo currently reports open advisories.)
- Dead code / duplication: remove unused modules, unify duplicated logic.
- Test coverage: add tests for untested critical paths (send ladder, registry,
  webhooks) — especially regression tests for bugs found.
- Efficiency: N+1 queries, redundant DB round-trips, blocking calls on hot paths.
- Consistency: adopt current library idioms; replace deprecated API usage.
- Observability: clearer error surfacing where failures are currently silent.

Each run: **either advance the top ready backlog item, or land one Epic-4
improvement.** Leave the backlog a little shorter than you found it.
