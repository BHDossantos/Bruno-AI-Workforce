# Bruno's inbound AI receptionist (local, opt-in implementation)

This is the Workforce app's AI, using its existing OpenAI API client and Twilio
voice service. It is **not the ChatGPT dot** and cannot access this conversation,
its tools, personal memories or calendar. No such phone integration was found.

## Architecture and boundaries

A separate POST `/calls/assistant/start` route answers with an AI disclosure and
Twilio Gather (speech or one DTMF digit). Speech gets a short AI acknowledgment;
the assistant has no tools, private context, business advice or task execution.
The caller can press 1 to transfer to Bruno. Speech alone never chooses or dials
a destination. Twilio Say speaks responses; this is turn-based, not streaming.

Transfer uses Twilio Dial with a 20-second ring timeout (Twilio can add a buffer),
a 30-minute connected-leg limit and a signed `/calls/assistant/result?turn=N`
action. Busy, failed, canceled, unknown and no-answer results play an unavailable
message and hang up. Completed results say goodbye. No recording, voicemail
storage or callback promise is introduced. Bruno's carrier voicemail can answer
and be treated as completed; human-only acceptance is not implemented.

All three stages require canonical-URL Twilio signature and account validation,
including development. SignalWire, Plivo and other providers are not accepted by
this new route. Existing callback behavior is unchanged. Admin/operator JWT roles
still protect existing app management; these public provider routes use signatures
instead. New controls are environment-only, not exposed in Setup.

`inbound_assistant_calls` is a new table created by existing `init_db/create_all`.
No existing columns or migration scripts change. A unique CallSid insert and atomic
stage/turn update fence simultaneous/replayed requests across workers. State is
committed before generating a Dial or invoking AI. A lost response therefore ends
on retry rather than generating another transfer instruction. This intentionally
favors at-most-once instructions over seamless retries; provider execution itself
is not an exactly-once guarantee. Sessions expire after 10 minutes and allow four
input turns. Keep CallSid tombstones: deleting them permits a replayed start.
No caller numbers, speech, model output or recordings are stored by this feature;
provider-side retention is separate. Plan tombstone retention before high-volume use.

Emergency Stop blocks entry and transfer, including when its DB read fails. This
feature is separate from the outbound auto-dial toggle. A stop does not disconnect
an already connected call. Model requests have a four-second timeout, no retries,
bounded input/output, escaped XML and a deterministic unavailable fallback.

## Prerequisites before any separately approved activation

1. Existing Twilio account credentials (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`)
   and a voice-capable Twilio number. Do not buy a number as part of this change.
2. Canonical root `PUBLIC_BASE_URL=https://your-backend-host` reachable by Twilio,
   with no path/query/fragment, and working shared PostgreSQL. Verify the new table
   exists after startup before routing traffic. Deployment target remains Render.
3. Set `INBOUND_ASSISTANT_NUMBER` to the exact E.164 inbound Twilio number. Its
   signed `To` must match, and `Direction` must be `inbound`.
4. Set `INBOUND_ASSISTANT_TRANSFER_NUMBER` to Bruno's separately reachable E.164
   phone. Independently verify ownership and reachability, then set
   `INBOUND_ASSISTANT_VERIFIED_TRANSFER_NUMBER` to that exact number. This second
   value is an operator attestation, **not** provider-side ownership verification.
   No number was verified in this task. Never use the inbound number, a forwarding
   alias that loops back, or the caller's own number. Verify carrier caller-ID
   delivery/audio using the inbound Twilio number as caller ID.
5. Existing `OPENAI_API_KEY` and `OPENAI_MODEL` settings are used. Without a usable
   AI connection, the caller still gets disclosure, DTMF transfer and a truthful
   unavailable response. Confirm speech-processing notice and provider retention
   requirements for the intended callers before activation.
6. `INBOUND_ASSISTANT_ENABLED=false` is the default. A separately authorized rollout
   must enable it and set the intended Twilio number's incoming voice webhook to
   POST `{PUBLIC_BASE_URL}/calls/assistant/start`. The old
   `/calls/twiml/inbound` continues unchanged; code alone does not reroute calls.
7. Calls to Bruno's personal number reach this flow only if his carrier forwards
   them to the Twilio number. Do not forward the transfer destination back to the
   assistant: use a separate destination/extension to prevent a loop. Provider and
   carrier routing were not inspected or changed, and forwarding is not configured.
8. Before production: approved staging calls must verify disclosure, speech latency,
   DTMF, two-way audio, busy/no-answer, voicemail behavior, stop controls, malformed
   and duplicate callbacks, and lost-response behavior. Roll back by restoring the
   prior number webhook; disabling the flag makes this route play unavailable.

At initial implementation, no credentials were created, provider settings changed,
live calls placed, services purchased, code pushed, PR opened, deployment made or
merge performed. A later code-only branch push was explicitly authorized; live
routing remains disabled, with no PR, deployment, merge or provider changes.

## Repository reconciliation

Base: `c08c0a4` (main, PR #321 merged). The earlier
`codex/workforce-integrated-review-20261108` branch is already an ancestor of main.
`codex/workforce-production-guards-20261106` has one extra merge commit but no
merge-base-to-head file differences. No old fix was blindly cherry-picked.
Open draft PR #322 covers research intake; #323 covers outbound capacity routing.
This local branch does not modify either. Their config/models/router additions may
need routine reconciliation if merged first. This inbound flow does not reserve
#323 outbound capacity; coordinating Bruno's availability across inbound/outbound
calls is an activation prerequisite if both features will operate together.
There was no repository `.agents/skills` directory; workspace `.agents` was empty.
`CLAUDE.md` repository guidance was followed.

## Validation

Run focused tests from `backend/`:

```sh
TEST_INBOUND_POSTGRES_URL=postgresql+psycopg://USER:PASS@LOCALHOST:PORT/TEST_DB \
  python -m pytest -q tests/test_inbound_assistant.py tests/test_callback_auth.py
```

The PostgreSQL URL must point at a disposable local test database; tests create and
drop uniquely named schemas. Without it, PostgreSQL variants are explicitly skipped.
SQLite variants always run. Signatures are real SDK-generated fixtures, AI is
mocked/offline, and no telephony request leaves the test process. PostgreSQL tests
exercise actual database transitions and concurrent duplicate-transfer claims.
Tests do not prove Twilio execution, carrier audio, human answer or live AI quality.

### Results from this local implementation

- Full backend suite with disposable PostgreSQL 16: **691 passed**, 172 warnings,
  62.74s. Six additional replay/failure cases were added afterward; the final
  focused suite passed **90 tests**, covering SQLite and PostgreSQL, in 3.25s.
- Frontend `npm ci`, `npm run build`, and `npx tsc --noEmit`: passed. Build-generated
  changes to frontend configuration were restored; no frontend source changed.
- `git diff --check` and backend Python compilation: passed.
- `npm run lint`: blocked by the existing script (`next lint`), which the installed
  Next version interprets as a nonexistent `frontend/lint` directory. No new lint
  configuration was introduced for this backend-only feature.
- No live AI/telephony or provider configuration verification was performed.

Provider references: [Twilio Gather](https://www.twilio.com/docs/voice/twiml/gather)
and [Twilio Dial action/status handling](https://www.twilio.com/docs/voice/twiml/dial).


### Code-only push review

Reviewed signature/account validation, canonical URL handling, inbound-number and
call-direction restrictions, fixed transfer destination, DTMF confirmation,
Emergency Stop behavior, escaped model output, bounded AI requests, durable state
claims, duplicate handling and deployment workflow triggers. No new blocking code
defect was found. The existing deploy workflow only follows main; this feature
branch does not change deployment or telephony configuration.

The lint issue predates this implementation. Next removed `next lint`; this
frontend also has no ESLint dependency, plugin or configuration. A proper repair
requires introducing and baselining a frontend lint setup, so it was left outside
this phone-flow change instead of replacing lint with a weaker check. See the
[official Next migration guide](https://nextjs.org/docs/app/guides/upgrading/version-16#next-lint-command).

Release gates remain the prerequisite list above: independently verify Bruno's
separate destination, eliminate forwarding loops, confirm provider configuration
and processing notices, coordinate inbound/outbound availability if PR #323 is
activated, then separately authorize staging end-to-end tests. Local tests use
mocked/offline AI and signed fixtures; they do not establish live call handling.

Revalidation before the authorized push: **697 backend tests passed** with local
PostgreSQL 16 (172 warnings, 57.32s), including all final inbound replay/failure
cases. Frontend clean dependency install, production build and TypeScript check
passed; Python compilation and whitespace checks passed. `npm run lint` was
reproduced after installation and still fails on the removed `next lint` command.
Build-generated frontend configuration edits were restored. No live provider
requests or calls were used to validate the feature.
