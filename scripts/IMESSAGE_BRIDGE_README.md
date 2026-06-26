# iMessage / SMS bridge (free texting from your real number)

Send and receive texts from your **real AT&T number** through your Mac's
Messages.app — no Twilio, no monthly fee. The app queues outbound texts; a tiny
helper on your Mac sends them and pushes replies back.

## One-time setup

1. **Server:** set a shared secret on the backend (Cloud Run / Secret Manager):
   - `BRUNO_BRIDGE_TOKEN` = a long random string (e.g. `openssl rand -hex 24`).

2. **iPhone → Mac SMS forwarding** (so green-bubble SMS, not just iMessage, send
   from your number):
   - iPhone: **Settings → Messages → Text Message Forwarding → enable your Mac**.
   - Mac: sign into Messages with the same Apple ID.

3. **Mac permissions:** give your Terminal **Full Disk Access**
   (System Settings → Privacy & Security → Full Disk Access) so the helper can
   read incoming texts from the Messages database.

## Run it

```bash
export API_URL="https://YOUR-BACKEND-URL"      # the app's API base
export BRIDGE_TOKEN="the-same-secret-as-server"
export POLL_SECONDS=20                          # optional
python3 scripts/imessage_bridge.py
```

Leave it running (the Mac must be awake/logged in). To keep it alive, run it in a
`tmux`/`screen` session or add a `launchd` plist.

## What it does each cycle
- **Outbound:** `GET /bridge/outbox` → sends each via Messages → `POST /bridge/sent`.
- **Inbound:** reads new messages from `~/Library/Messages/chat.db` →
  `POST /bridge/inbound` (the server records them and runs the same warm-lead
  handling as email replies — they appear on the Texts page).

## Notes
- Outbound texts are created as **Queued** SMS only when Twilio is *not*
  configured and `BRIDGE_TOKEN` is set, so you choose exactly one path.
- All three endpoints require the `X-Bridge-Token` header — keep the token secret.
- iMessage (blue) works without step 2; step 2 adds SMS (green) to non-Apple phones.
