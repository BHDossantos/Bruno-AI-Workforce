# Corrected scope: AI first on existing outbound live answers

This supersedes the earlier inbound-first interpretation. The requested workflow
is the EXISTING outbound lead call, using the existing Twilio number/account:

- Machine/voicemail → Bruno's existing recorded message, unchanged.
- Existing live-answer classification → Workforce AI speaks first, then the prospect may press 1 to
  transfer to Bruno's existing independently verified personal cell.

This is Workforce's OpenAI-backed assistant, not the ChatGPT dot. No new inbound
number routing, account, number purchase or TwiML App is required. The earlier
inbound implementation remains separate and disabled. Its staging script is for
that earlier inbound proposal, not for enabling this corrected outbound feature.

## Inspected integration

`integrations/twilio_voice.place_auto_call` already places the lead call via the
existing per-channel telephony provider, selecting the caller ID using local
presence or the default voice number. It sets `MachineDetection=DetectMessageEnd`
and uses `/calls/twiml/amd`. Both that REST request and all recorded-message code
are unchanged. Current source defaults select Twilio, with SignalWire compatibility
elsewhere; live provider/account configuration has not been verified.

The existing `amd_twiml` sends human/unknown/empty answers to the producer if
`auto_dial_transfer_enabled` is true. Machines (or transfers disabled) receive the
existing `producer_voicemail_url` playback or existing spoken fallback. The new
interception uses that SAME `_amd_is_human` classifier when the new flag AND existing
transfer flag are true: human/unknown/empty now reach AI before any personal-cell
transfer. This prevents unknown/empty results bypassing AI. Machine/fax results
and all results with transfers disabled retain their exact legacy recorded-message
behavior. AMD can misclassify a machine as human/unknown; the classifier itself is
unchanged, so provider staging must check this known limitation.

## Implementation

`/calls/twiml/amd` delegates the selected human branch to the new outbound assistant.
That branch verifies the Twilio signature even in development, validates the signed
`Direction=outbound-api` and `From` number, and never falls back to a direct cell
bridge after an authentication/state error. Machine handling still calls the
unchanged original function. The new route is Twilio-only: SignalWire/other-provider
activation is not supported and must not be inferred from current credentials.

The existing assistant turn engine is reused through an immutable per-request
flow configuration. Its new outbound state table, `outbound_assistant_calls`,
is separate from inbound state and created by existing `init_db/create_all`;
no existing columns change. Signed `/calls/outbound-assistant/turn` and `/result`
callbacks handle speech/DTMF and transfer results. Direct `/start` is refused:
only the existing live-answer AMD branch can start the assistant session.

The assistant discloses its identity and speech processing, acknowledges the
prospect's request using the existing OpenAI client, and offers press 1 to try
Bruno. It has no account/quote/calendar tools and does not give professional advice.
The model cannot select a destination or initiate a call. Speech requests for Bruno
lead to DTMF confirmation. No new outbound REST call is made by this feature;
Twilio Dial bridges the active prospect call after confirmation.

Transfers reuse the existing producer-cell/callback and bridge caller-ID selection.
Both must match explicit independently verified values. Current stored numbers
are read with environment precedence, including cleared stored values. A target
matching the prospect, originating number, caller ID, or any configured Twilio
voice/insurance/from/local-presence number is rejected. Carrier-side forwarding
loops cannot be inferred from code and must be checked before verification.

Atomic durable sequence claims prevent duplicate callbacks from producing repeated
AI requests/transfer instructions. Ambiguous/lost responses fail closed rather than
replaying Dial. Emergency Stop is checked before entry and transfer. No answer,
busy or failed transfer plays an unavailable message and hangs up; it does not
promise a callback. The original machine voicemail path remains unchanged.
The new AI/transfer stage does not add recording; the old recorded-message asset
is untouched. A personal carrier voicemail can still answer the transfer leg;
human acceptance screening on Bruno's phone is not implemented.

## Disabled staging configuration

Leave existing Twilio credentials, number routing, outbound dialing guards,
recorded-message URL and billing settings alone. No live provider changes were made.

```dotenv
OUTBOUND_ASSISTANT_ENABLED=false
OUTBOUND_ASSISTANT_FROM_NUMBER=
OUTBOUND_ASSISTANT_VERIFIED_TRANSFER_NUMBER=
OUTBOUND_ASSISTANT_VERIFIED_CALLER_ID=
```

Before separately authorized activation:

1. Verify the existing account and its voice-capable originating number using
   authorized Twilio Console/service access. Set `OUTBOUND_ASSISTANT_FROM_NUMBER`
   to that exact E.164 `From`. Do not infer it from the source default toll-free
   number. Local-presence calls with another `From` fail closed in the AI branch;
   inventory actual originating numbers before rollout. No local-presence settings
   were changed to force a particular caller ID.
2. Independently verify that the existing `producer_cell` (or fallback
   `producer_callback`) is Bruno's personal destination, then set
   `OUTBOUND_ASSISTANT_VERIFIED_TRANSFER_NUMBER` to the exact normalized number.
   Do not forward that personal destination back to an assistant number. This is
   operator attestation, not automatic provider ownership verification.
3. Verify ownership/voice capability and two-way transfer audio for the existing
   selected bridge caller-ID, then set `OUTBOUND_ASSISTANT_VERIFIED_CALLER_ID` to
   that exact E.164 number. Existing bridge selection prefers a local caller ID;
   do not change it or purchase a number as part of staging.
4. Confirm canonical HTTPS `PUBLIC_BASE_URL`, existing Twilio SID/token, working
   PostgreSQL/new table, existing OpenAI config, caller consent/processing notices
   and readiness of Bruno's phone. This change does not authorize new outreach.
5. Separately authorize deployment and enabling the new flag. Keep the existing
   transfer flag's intended setting; if it is false, legacy voicemail behavior
   remains in effect. No Twilio phone-number webhook change is needed: outbound
   calls already point to `/calls/twiml/amd`. Do not use the earlier inbound URL.
6. Separately authorize staging calls: machine/beep recorded-message equality,
   human greeting, speech latency, DTMF consent, two-way audio, busy/no-answer,
   personal voicemail, duplicate/lost callbacks, Emergency Stop, unknown AMD,
   local-presence origins, and rejection of missing verification/mismatched accounts.
   Coordinate availability with the independent capacity-routing PR #323 if used.

Rollback the new behavior by setting `OUTBOUND_ASSISTANT_ENABLED=false`: the
existing live-transfer and recorded-voicemail paths are restored. This does not
stop existing outbound dialing or hang up an already connected call.

## Verification limits

No local production credentials/database configuration or direct Twilio connector
was available. Existing account identity, prepaid balance, current number ownership,
caller-ID/audio behavior and personal forwarding remain unverified. The same
Twilio account uses its existing balance; AI API charges are separate. Nothing
here changes billing, initiates calls, deploys, merges or changes live routing.
Tests use SDK-signed fixtures, local databases and mocked/offline AI, not real calls.

## Local validation of the corrected implementation

- Final full backend suite against fresh local PostgreSQL 16: **769 passed**,
  172 warnings, 61.92s. Includes SQLite and PostgreSQL assistant variants.
- Regression tests assert byte-for-byte original machine/fax TwiML with and without
  the recorded asset; disabled flags preserve original human behavior. Human,
  unknown and empty results exercise AI before transfer under the existing classifier.
- Signed POST/GET AMD, refusal of direct start, invalid signatures/configuration,
  cleared stored cell, wrong direction/origin, duplicate start/transfer, real database
  concurrency, loop targets, Emergency Stop and missing state-table behavior tested.
- Speech-to-confirmation and no-answer behavior tested with offline/mocked AI.
  No Twilio call execution, carrier forwarding, real speech recognition or live
  model responses were tested.
- Frontend build and TypeScript passed. Python compilation and whitespace checks
  passed. Frontend generated configuration edits were restored.
- Existing `npm run lint` remains blocked: `next lint` is removed in the installed
  Next version. No unrelated lint migration was mixed into this correction.

The corrected implementation is authorized for branch push only. No PR, merge,
deployment, credential creation, billing change, live routing change or call was made.
