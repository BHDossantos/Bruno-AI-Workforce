# Mobile readiness — 2026-11-02

Status: development preview, **not ready for App Store or Google Play submission**.

Only mobile files were recovered from `mobile/workforce-foundation`; none of that
branch's older backend/frontend state replaces current main. The mobile preview is
an offline operator guide, not a connected dashboard.

Source audit: `auto_dial.run` reads the persisted auto-dial setting; the Twilio
`/calls/twiml/inbound` route checks that setting and emergency pause before forwarding.
The `/calls/lead/{id}`, `/calls/test`, `/calls/record-voicemail`, and browser calling
paths are separate. Existing calls are not terminated by this switch. The web copy
now describes this limited scope; email and SMS are unaffected. No production API
was called and no calls were placed. Provider-specific behavior still needs a mocked
integration matrix and authorized staging acceptance tests.

Remaining product work: authenticated read APIs, secure sessions, account/role
permissions, fresh-state display and offline/error handling; explicit confirmations
for any future call or automation mutation; notification delivery and account deletion.
Do not add a live toggle based only on the offline guide.

## Reproducible local validation

Use Node 22 or newer:

```sh
cd mobile
npm ci
npm run typecheck
EXPO_OFFLINE=1 npx expo export --platform ios --platform android --output-dir dist
```

The PR workflow runs typechecking and both JavaScript bundle exports. Bundle export
is not a native Xcode/Gradle build, device test, signed release, or store approval.
The lockfile records the prototype's Expo SDK 54 dependencies. Review SDK currency,
security updates, platform target requirements and compatibility before release.

## Workspace evidence

Mobile and frontend typechecks passed; iOS/Android Hermes exports passed.
Two pure voice/TwiML tests passed. Broader targeted backend run: 2 passed,
2 skipped, 1 failed because local PostgreSQL was unavailable. No backend code
was changed; DB-backed pause/resume acceptance remains unverified.

Exports used `EXPO_OFFLINE=1` because the Expo metadata fetch failed in this
environment. Native compilation, signed builds and device QA were not performed.

## Signing and release gate

`eas.json` defines internal preview and production build profiles with remote version
management. Submission profiles were intentionally omitted. No cloud builds were
started, credentials created, stores configured, or releases submitted.

Before an owner-authorized build: verify ownership of the bundle identifiers in
`app.json`, link the correct EAS project, supply existing iOS provisioning and Android
upload-key credentials through the approved signing service, and verify version/build
numbers. Then perform signed device builds and review their permissions and manifests.
Do not store credentials in git. Signing and store validation remain unverified.

Before public release also complete branded icons/splash/screenshots, accessible UI
and device QA, review notes/demo access, support and privacy URLs, privacy disclosures,
data-safety declarations, account deletion where accounts exist, and functional
acceptance tests. This small preview alone is not sufficient product functionality
for submission.
