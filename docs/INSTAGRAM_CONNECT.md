# Connect your Instagram (live data + publishing)

Once connected, the **Instagram Planner** shows your real followers, reach, and
recent posts, and the app can publish posts via the official Graph API.

## Requirements (one-time)
1. Your Instagram must be a **Business or Creator** account.
2. It must be **linked to a Facebook Page** (IG app → Settings → Account type → link Page).

## Step 1 — Create a Meta app
1. Go to https://developers.facebook.com/apps → **Create app** → type **Business**.
2. Add the **Instagram Graph API** product.
3. Under **App roles**, add yourself; keep the app in **Development** mode for testing.

## Step 2 — Get your IG Business Account ID + a long-lived token
Easiest path — the **Graph API Explorer** (developers.facebook.com/tools/explorer):
1. Select your app, click **Generate Access Token**, and grant these permissions:
   `instagram_basic`, `pages_show_list`, `instagram_manage_insights`,
   `pages_read_engagement` (add `instagram_content_publish` later for posting).
2. Run `GET /me/accounts` → copy your Page's `id`.
3. Run `GET /{page-id}?fields=instagram_business_account` → copy the
   `instagram_business_account.id`. **That number is your `ig_user_id`.**
4. Make the token long-lived (≈60 days):
   `GET /oauth/access_token?grant_type=fb_exchange_token&client_id={app-id}&client_secret={app-secret}&fb_exchange_token={short-token}`
   → copy the returned `access_token`.

## Step 3 — Paste into the app
In the dashboard → **Connections** → **Instagram**, enter:
- **access_token** = the long-lived token from Step 2.4
- **ig_user_id** = the `instagram_business_account.id` from Step 2.3

Open **Instagram Planner** — your live followers, reach, and recent posts appear.

## Publishing (optional, later)
To let the app publish posts (`POST /instagram/publish` with a public `image_url`
+ caption), your Meta app needs the **`instagram_content_publish`** permission,
which requires **App Review** by Meta. Reading insights works without review
while you're an app role/tester.

## Notes
- Long-lived tokens expire (~60 days). Re-run Step 2.4 and update the connection
  when it lapses (the planner will show a "couldn't load account" note).
- Tokens are stored **encrypted** (Fernet) and never returned by the API.
