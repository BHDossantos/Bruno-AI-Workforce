# Telephony callback authentication candidate

Extends local production guard commit 2511627 on draft PR312. No provider calls,
settings, credentials, outbound adapter behavior, deployments or publications.

## Implemented boundary

Production guards cover `/sms/inbound`, `/sms/status`, `/sms/plivo-inbound`,
`/sms/plivo-status`, all `/calls/twiml/*`, `/calls/plivo/*`, and the public call
`vm-saved`, `dial-status`, `amd-transfer-result`, `status`, `recording` callbacks.
Local/test runtime modes retain unsigned fixtures. The Docker image now defaults
ENVIRONMENT to production; local Compose uses the explicit development value in
`.env.example`. Direct Python still defaults to development for existing local
workflows: unmanaged non-container hosts MUST set ENVIRONMENT=production. Render
runtime markers also activate guards. Do not publish an instance using development
mode; it intentionally bypasses provider verification. No running config changed.

Twilio uses pinned official `twilio==9.13.0` RequestValidator and requires a matching
configured AccountSid. Plivo uses pinned official `plivo==4.63.0` V3 verification,
including URL/query and POST form fields. V2 cannot downgrade verification: it
does not bind POST payloads and is deprecated in Plivo's voice documentation.
Rotation to a different account/token requires a separate reviewed operation.

The canonical URL is reconstructed from existing PUBLIC_BASE_URL (or its existing
Render fallback) plus raw request path/query, never Host/forwarded headers. It
must be an HTTPS origin, with no credentials, path prefix, query or fragment.
Reverse proxies using a path prefix need an explicitly reviewed mapping first.
POST requests must be form-urlencoded; duplicated keys and JSON are rejected.

Credential resolution matches existing Setup precedence: explicit environment
then cfg: settings rows then application settings, without mutating shared settings.
Unreadable config DB returns 503; a cleared stored token cannot reuse stale live
settings. Business handlers do not run after verification failure. Read-only
configuration lookups are necessary before authentication; no business queries
or writes are performed by the verifier.

## Required deployment decisions and compatibility gates

- **SignalWire is unresolved.** Existing compatibility routes serve both providers.
  SignalWire's documented signing key is distinct from its API token and is absent
  from this app's settings model. The patch never guesses it. Non-Twilio account
  IDs are rejected, even when SignalWire is today's preferred outbound provider.
  Confirm whether SignalWire callbacks are required, then separately approve and
  implement signing-key storage/provisioning before deploying on that channel.
- **Confirm Plivo V3 on every callback.** Messaging docs still show V2, whereas
  voice docs prescribe V3. V2-only messaging traffic will be rejected. Verify V3
  delivery in an approved staging integration; do not substitute payload-unbound V2.
- Verify the exact callback origin configured at each provider, credentials/account
  identity and env-vs-Setup precedence. A custom domain mismatch, missing credentials,
  inaccessible configuration DB or unsupported deployment prefix fails closed.
- Signed callback rejection can stop call flow/voicemail XML, block receipt or
  inbound-message updates and cause provider retries or Twilio error 11200.
  This changes inbound acceptance only; it is not safe to deploy without the
  callback verification and PR312 drained-worker rollout gates.
- This is authentication, **not replay prevention** or durable event deduplication.
  Twilio and Plivo signed requests can be replayed; repeated legitimate events
  still need idempotent processing. The four unsigned Vonage/SIP `vm-saved` and
  `event` mutation routes now return 503 in secure runtime before upload, global
  voicemail settings or Message status changes. Those providers cannot save new
  voicemail greetings or update call status until a separately authenticated
  integration exists. No provider credentials or callback configuration was changed.
  Their instruction-returning routes and other webhook families remain separate
  security review items; this is not an assertion that all public routes are secure.

## Validation

Official SDK implementations were inspected locally. Tests use an isolated
FastAPI app, fake config DB and SDK-generated signatures; no live providers or
shared DB. Coverage includes valid SMS and voice GET/POST callbacks, raw query
binding, payload/account/URL tampering, missing headers/credentials, V2 downgrade,
proxy spoofing, cleared/stale credentials, env precedence and a callback-route
inventory. Business query sentinels ensure invalid requests cannot update records.
Full DB-backed integration and actual provider callback delivery remain untested.
Initial combined result: 77 tests passed (30 callback cases, 33 production/Resend cases,
14 existing outbound fallback cases), two dependency deprecation warnings.
`pip check` reports no broken requirements; `git diff --check` passes.
After alternate-route hardening: 84 tests pass, including four route-level
voicemail/status rejection cases, an upload/storage sentinel, local-mode behavior
and example-secret rejection. Docker image default was inspected but the image
was not built or deployed in this task.

References:
- https://www.twilio.com/docs/usage/api-security-reference-guide/webhook
- https://docs.plivo.com/docs/voice/concepts/signature-validation
- https://www.plivo.com/docs/messaging/concepts/signature-validation
- https://signalwire.com/docs/server-sdks/reference/python/core/security/validate-webhook-signature
