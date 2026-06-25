# Connect your social accounts (publishing + analytics)

Your Content Factory generates posts every day, but they can only **publish**
once the matching account is connected. This guide gets each platform connected
via its **official API** (token-based — never your username/password). Once a
token is in, the daily platform loops publish to it automatically and the Growth
dashboard fills with real follower + engagement data.

> Where to enter everything: **dashboard → Connections →** pick the platform →
> paste the fields below → **Connect**. Then click **Test** on the connected card
> to confirm the token actually works (it calls the live API and flips the badge
> to green, or shows exactly what's wrong).

All credentials are stored **encrypted at rest** (Fernet) and are never returned
by the API.

---

## Instagram  📸  (fields: `access_token`, `ig_user_id`)
Requires an IG **Business/Creator** account linked to a Facebook Page. Full
walkthrough in [INSTAGRAM_CONNECT.md](./INSTAGRAM_CONNECT.md). Short version:
1. Create a **Business**-type app at https://developers.facebook.com/apps and add
   **Instagram Graph API**.
2. In the **Graph API Explorer**, grant `instagram_basic`, `pages_show_list`,
   `instagram_manage_insights`, `pages_read_engagement`, and (for posting)
   `instagram_content_publish`.
3. `GET /me/accounts` → your Page `id`; `GET /{page-id}?fields=instagram_business_account`
   → that `id` is your **`ig_user_id`**.
4. Exchange for a long-lived (~60-day) token (`grant_type=fb_exchange_token`) →
   that's your **`access_token`**.
5. Posting needs `instagram_content_publish` approved via **App Review**; reading
   insights works while you're an app tester.

## Facebook Page  👍  (fields: `page_access_token`, `page_id`)
Same Meta app as Instagram.
1. In the Graph API Explorer grant `pages_show_list`, `pages_read_engagement`,
   `pages_manage_posts`.
2. `GET /me/accounts` → copy your Page's **`id`** (`page_id`) and its
   **`access_token`** (`page_access_token`). Use the **page** token, not the user
   token, and exchange it for a long-lived one.

## LinkedIn  💼  (fields: `access_token`, `author_urn`, `profile_url` optional)
1. Create an app at https://www.linkedin.com/developers/apps and request the
   **Share on LinkedIn** (`w_member_social`) product.
2. Run the OAuth flow to mint a **member access token** with `w_member_social`.
3. Your **`author_urn`** is `urn:li:person:{id}` (from `GET /v2/userinfo` → `sub`)
   or `urn:li:organization:{id}` for a company page.
> Only **your own posts** auto-publish — LinkedIn forbids automated connections &
> DMs, so those stay one-click assisted.

## X / Twitter  𝕏  (field: `access_token`)
1. In the X developer portal create a project/app on a **paid API tier** (posting
   requires it) and enable **OAuth 2.0**.
2. Mint a **user access token** with the `tweet.write` (and `users.read`) scopes →
   that's your **`access_token`**.
> **Test** verifies it via `GET /2/users/me`. Text posts work today; media is a
> later add.

## Spotify for Artists  🎧  (fields: `access_token`, `artist_id`) — analytics only
Read-only follower/top-track analytics via the Spotify Web API (Spotify has no
post/upload API). Mint an OAuth token and grab your artist ID from your artist
URL.

## TikTok  🎵  (fields: `access_token`, `open_id`) — video auto-post
TikTok publishing is wired (Content Posting API, Direct Post), but it's gated on
TikTok's app audit and needs a produced video:
1. **https://developers.tiktok.com/** → Developer Portal → **Manage apps** → create an app.
2. Add products **Login Kit** + **Content Posting API** (enable **Direct Post**).
3. Scopes: `user.info.basic`, `video.publish`, `video.upload`.
4. OAuth to mint a user **access_token**; copy your **open_id**.
5. Set the video-pipeline keys (`ELEVENLABS_API_KEY`, `VIDEO_API_KEY`) so the
   engine can produce the clip TikTok requires.
> Pre-audit, TikTok forces posts to **SELF_ONLY** (private). After your app passes
> audit, set `TIKTOK_PRIVACY_LEVEL=PUBLIC_TO_EVERYONE`. Until then TikTok content
> stays as ready-to-post drafts in the Content Factory.

## YouTube  ▶️  (fields: Google OAuth `client_id` + `client_secret` + `refresh_token`) — video auto-upload
Uploads videos via the YouTube Data API v3 (`youtube.upload`):
1. In Google Cloud Console, enable the **YouTube Data API v3** and create an
   **OAuth client** (Desktop or Web).
2. Run an OAuth consent for the **`https://www.googleapis.com/auth/youtube.upload`**
   scope and capture the **refresh token** (e.g. via the OAuth Playground).
3. Connect with `client_id`, `client_secret`, `refresh_token` (tokens
   auto-refresh). `channel_id` optional.
> Until your Google OAuth app is **verified**, uploads are forced to **private**.
> After verification, set `YOUTUBE_PRIVACY_STATUS=public`.

---

## After connecting — verify it end to end
1. **Connections → Test** on each card → expect `✅ Live: @handle · N followers`.
2. Open **Growth Analytics** — connected platforms show real followers; published
   counts tick up as the daily loops run.
3. Force one cycle now instead of waiting for 7am:
   ```bash
   curl -s -X POST -H "X-Cron-Token: $CRON_SECRET" \
     https://ai-workforce-746155486511.europe-west1.run.app/cron/platform-loops
   curl -s -X POST -H "X-Cron-Token: $CRON_SECRET" \
     https://ai-workforce-746155486511.europe-west1.run.app/cron/publish-content
   ```

## Keeping tokens alive
Meta/LinkedIn long-lived tokens expire (~60 days). The nightly
`/cron/refresh-tokens` job refreshes what it can; when a token fully lapses, the
**Test** button will show it red — re-mint and update the connection.
