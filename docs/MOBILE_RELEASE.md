# Shipping Bruno AI Workforce to the App Store and Google Play

The app is built. This is what stands between the build and a listing, split into
what the code does and what only you can do.

Developer workflow lives in [`mobile/README.md`](../mobile/README.md).

---

## 1. Decide the distribution path first

This decision changes the accounts, the cost, the review risk and the work — make
it before opening either console.

| | **Public listing** | **Private / internal** |
|---|---|---|
| Who can install | anyone | people you name |
| Apple | App Store, full review | Custom App via Apple Business Manager, or TestFlight (up to 100 internal testers) |
| Google | Play production track | Play private app (managed Google Play), or a closed testing track |
| Review risk | **real — see §4** | low |
| Store listing, screenshots, ASO | required | minimal |

**This app is a single-tenant internal tool.** It manages one agency's leads,
mailboxes and call queue; there is no sign-up, and anyone who downloads it from a
public store lands on a login screen they can never get past. That is the exact
shape Apple rejects under guideline 4.2, and Google flags for "broken
functionality". The private path is the honest fit and is far less work.

The public path is still open, but it is a product decision — it means building a
version a stranger can actually use (self-serve sign-up, their own data), not a
packaging decision.

---

## 2. Accounts you need

| | Cost | Notes |
|---|---|---|
| **Google Play Console** | $25 once | Individual or organisation. Organisation accounts need a D-U-N-S number. |
| **Apple Developer Program** | $99/year | Organisation enrolment needs a D-U-N-S number and takes days to weeks. Individual enrolment is faster but lists your personal name as the seller. |
| **Apple Business Manager** | free | Only for the private/custom-app path. |

Neither can be created from here — both require your identity and payment
details. Everything downstream of them is automated.

## 3. Secrets and variables to set in GitHub

Once the accounts exist, `Settings → Secrets and variables → Actions`:

| Name | Kind | What it is |
|---|---|---|
| `MOBILE_API_URL` | variable | The live backend URL the app talks to, e.g. `https://bruno-backend-xxxx.onrender.com`. **A variable, not a secret** — it is baked into the binary and visible to anyone who unpacks it. |
| `ANDROID_KEYSTORE_BASE64` | secret | The upload keystore, base64. Create it once (below) and never lose it — Play ties your app identity to it. |
| `ANDROID_KEYSTORE_PASSWORD` | secret | |
| `ANDROID_KEY_ALIAS` | secret | |
| `ANDROID_KEY_PASSWORD` | secret | |

Create the Android upload key once, on your own machine, and back it up somewhere
you will still have in five years:

```bash
keytool -genkeypair -v -keystore upload.keystore \
  -alias bruno-upload -keyalg RSA -keysize 2048 -validity 10000
base64 -w0 upload.keystore     # paste into ANDROID_KEYSTORE_BASE64
```

Without these the workflow still builds — it just produces an unsigned bundle,
which proves the code compiles but cannot be uploaded.

## 4. The Apple review risk, stated plainly

Guideline **4.2 (Minimum Functionality)** rejects apps that are "simply a web site
bundled as an app" and offer nothing a browser does not. A Capacitor shell around
an existing web app is precisely the pattern that guideline describes, and the
first submission is where it gets tested.

What moves an app out of that category is native capability the web cannot
provide. In priority order for this app:

1. **Push notifications** when a lead replies — genuinely useful (today the
   backend forwards replies to your cell by SMS) and the strongest single answer
   to 4.2. *Planned as the next PR in this series.*
2. **Biometric unlock** (Face ID / fingerprint) instead of retyping the password.
3. **Native share and the system dialer** from a lead's record.
4. **Camera capture** for documents straight into a lead's CRM record.

None of these exist yet. The shell ships without them; submitting before at least
push notifications land is submitting into a known rejection risk.

Google Play has no equivalent rule and will accept the shell as-is.

## 5. Store listing requirements

Already in the app, which covers most of what both stores demand:

| Requirement | Where |
|---|---|
| Privacy policy URL | `/privacy` |
| Terms | `/terms` |
| Account deletion route — **mandatory** on both stores for any app with accounts | `/data-deletion` |

Still to produce, and they need real screens rather than placeholders:

- **Screenshots** — Play wants phone plus a 7" and 10" tablet set; Apple wants
  6.7" and 6.5" iPhone sets, plus iPad if the app claims iPad support.
- **Feature graphic** (Play, 1024×500).
- **Short and full description** — see the `aso` skill when it is time to write
  these; both stores rank on them.
- **Data safety form** (Play) and **App Privacy** answers (Apple). Be accurate:
  this app handles names, email addresses, phone numbers, call recordings and
  message content. Call recording in particular has to be declared.

## 6. What the build produces today

`.github/workflows/mobile-build.yml`:

- **Android** — a debug APK on every relevant push (proves it compiles), and a
  release `.aab` on manual dispatch, signed when the keystore secrets are present.
  Targets SDK 36, which satisfies Play's current target-API requirement.
- **iOS** — compiles unsigned, which verifies the Xcode project, its Swift
  package dependencies and the bundled assets. Producing an uploadable `.ipa`
  needs an Apple distribution certificate, so that step is added once the
  account exists.

Both run on every change to `mobile/` or `frontend/`. The repository is public,
so Actions minutes — the macOS runner included — are free.

## 7. Order of work

1. ~~Static-exportable routes~~ — done.
2. ~~Capacitor shell, native projects, icons, CI~~ — done.
3. **Push notifications** — the native capability, and the answer to §4.
4. Create the developer accounts (**you**; nothing else can proceed past here).
5. Set the secrets in §3.
6. Screenshots and listing copy.
7. Android first: Play accepts the shell today, so it validates the whole pipeline
   end to end at a quarter of the risk. iOS follows once push notifications ship.
