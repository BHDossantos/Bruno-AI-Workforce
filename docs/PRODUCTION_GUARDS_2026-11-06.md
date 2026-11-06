# Production credentials and Resend inbound guards

Based on draft PR312 `ef161c7fe43c0304779ea9eaf56be0b5c55573c0`.
Default main remains `a392c0f281835832027f661b6d3dc6ace409f6aa`.
This is a local code candidate, not a deployment or configuration change.

## Behavior

- Only explicit development/dev/local/test/testing environments allow development
  credentials. Production, staging, unknown and blank modes reject signing keys
  shorter than 32 characters and bootstrap admin passwords shorter than 12, plus
  known defaults. Length is a minimum, not evidence of randomness or strength.
- Render runtime markers also enable guards because the existing blueprint omits
  ENVIRONMENT. Validation errors omit input values from their rendered text.
- Resend inbound returns 503 before payload processing if its verification secret
  is absent in a secure runtime. Other backend features can still start. Local
  unsigned fixtures remain available. Invalid configured signatures return 401.
- Existing HMAC verification now validates base64, rejects empty signing material,
  accepts only v1 signatures, and enforces a five-minute past/future timestamp
  tolerance. Raw-body verification and rotation signature lists remain supported.
  This limits stale replays; it is NOT durable event-ID deduplication. Repeated
  legitimate signed events within the tolerance still require idempotent handlers.

Reference: https://docs.svix.com/receiving/verifying-payloads/how-manual

## Validation and operational gates

Offline regression tests cover production/default/Render configuration rejection,
safe error rendering, unsigned/invalid/tampered/stale/future events, malformed keys,
rotation, both header naming conventions and Svix's published signature vector.
An isolated FastAPI router with a DB-access sentinel proves rejected events do
not query the database. Existing outbound fallback unit tests are included; no
outbound implementation was changed. No provider calls or production reads occur.
Result: 47 tests passed (33 new guard cases and 14 existing fallback cases), with
one existing Starlette/AnyIO deprecation warning. `git diff --check` passes.

Before a separately approved deployment, inspect existing configuration privately.
Missing/short credentials now stop startup. Do not blindly rotate SECRET_KEY:
tokens use it and absent ENCRYPTION_KEY causes stored credential encryption to
derive from it. Plan session invalidation and credential decryption/migration if
rotation is required. Changing ADMIN_PASSWORD does not update existing user rows;
it controls initial admin seeding, not an account-password reset.

Configure the real Resend webhook signing secret through an approved operation
and verify signed fixtures in staging before enabling inbound traffic. Keep the
host clock synchronized. 503/401 can cause provider retries; recover through the
provider's reviewed replay process after configuration is corrected. No signing
secret, production setting, account or credentials were changed here.

The original Resend-only patch did not cover Twilio/Plivo. The subsequent local
candidate adds those guards; see `CALLBACK_AUTH_2026-11-06.md` for exact coverage
and the remaining SignalWire/Plivo V3 deployment prerequisites. No outbound
sender change was made.
PR312's drain/schema/Mac helper rollout gates still apply. Full database/native/
provider integration and deployment verification have not been performed here.
