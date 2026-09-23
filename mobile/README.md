# Bruno AI Workforce — mobile

The iOS and Android apps are the **same frontend** as the web app, exported as a
static bundle and shipped inside a [Capacitor](https://capacitorjs.com) native
shell. There is no second codebase and no React Native rewrite: a change to a
page in `frontend/` reaches the web app and both stores.

```
frontend/  ──(MOBILE_BUILD=1 next build)──>  frontend/out  ──copy──>  mobile/www
                                                                        │
                                                       cap sync ────────┤
                                                                        ├──> mobile/android
                                                                        └──> mobile/ios
```

## Build it

```bash
cd mobile
npm ci
NEXT_PUBLIC_API_URL=https://<your-backend>.onrender.com npm run sync
```

`npm run sync` builds the static export, stages it at `mobile/www`, and copies it
into both native projects. Then:

```bash
npm run open:android   # Android Studio
npm run open:ios       # Xcode (macOS only)
```

CI does the same thing on every change to `mobile/` or `frontend/` — see
`.github/workflows/mobile-build.yml`.

## Things worth knowing

- **The API URL is compiled in.** Next bakes `NEXT_PUBLIC_*` at build time, so a
  store build talks to whichever backend was set when the binary was made. There
  is no runtime switch. Change it and you ship a new build.
- **The bundle is local, the data is not.** Pages load from the device; every
  request still goes to the backend over HTTPS. The app is useless offline by
  design — it is a live CRM view, not a cache.
- **Auth is the same bearer token** the web app uses, held in the WebView's
  `localStorage`, which persists across launches. CORS already reflects any
  origin (`backend/app/main.py`), so `capacitor://localhost` needs no change.
- **`android/` and `ios/` are committed.** Capacitor treats them as source, not
  build output: `cap sync` updates plugins and web assets but leaves hand edits
  (signing config, version wiring, entitlements) alone.
- **`www/` is not committed** — it is regenerated from `frontend/` every build.

## Regenerating the icons

`resources/*.png` are drawn from geometry by `scripts/make-icons.mjs` (no fonts,
so they render identically anywhere). To rebuild every platform size:

```bash
npm run assets
```

Neither `sharp` nor `@capacitor/assets` is a dependency — between them they pull
a large native image toolchain that would otherwise sit in the lockfile, and in
its own advisories, for a task run a few times a year. `npm run assets` fetches
both on the spot (`--no-save`, `npx --yes`) and leaves nothing behind.

## Releasing

See [`docs/MOBILE_RELEASE.md`](../docs/MOBILE_RELEASE.md).
