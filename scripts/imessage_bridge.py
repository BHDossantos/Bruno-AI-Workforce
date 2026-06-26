#!/usr/bin/env python3
"""Bruno AI — Mac iMessage/SMS bridge.

Runs on your Mac and sends/receives texts from your REAL number through
Messages.app (free, no Twilio). It:
  1. polls the app for queued outbound texts  (GET  /bridge/outbox)
  2. sends each via Messages (AppleScript)     -> POST /bridge/sent
  3. reads new incoming texts from chat.db     -> POST /bridge/inbound

Setup: see IMESSAGE_BRIDGE_README.md. Requires Python 3 (built into macOS) and
Full Disk Access for the terminal running this (to read the Messages database).

Env:
  API_URL        e.g. https://ai-workforce-....run.app
  BRIDGE_TOKEN   must equal the server's BRIDGE_TOKEN
  POLL_SECONDS   optional, default 20
"""
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib import error, request

API_URL = os.environ.get("API_URL", "").rstrip("/")
TOKEN = os.environ.get("BRIDGE_TOKEN", "")
POLL = int(os.environ.get("POLL_SECONDS", "20"))
CHAT_DB = Path.home() / "Library" / "Messages" / "chat.db"


def _api(path: str, payload: dict | None = None):
    url = f"{API_URL}{path}"
    data = None if payload is None else __import__("json").dumps(payload).encode()
    req = request.Request(url, data=data, method="POST" if data is not None else "GET")
    req.add_header("X-Bridge-Token", TOKEN)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with request.urlopen(req, timeout=30) as r:
            body = r.read().decode()
            return __import__("json").loads(body) if body else None
    except error.HTTPError as e:
        print(f"  ! {path} -> HTTP {e.code}: {e.read().decode()[:200]}")
    except Exception as e:  # noqa: BLE001
        print(f"  ! {path} -> {e}")
    return None


def send_imessage(to: str, body: str) -> bool:
    """Send via Messages.app. Tries iMessage, falls back to SMS service."""
    safe_to = to.replace('"', '')
    safe_body = body.replace('\\', '\\\\').replace('"', '\\"')
    script = f'''
    on run
      set theBuddy to "{safe_to}"
      set theText to "{safe_body}"
      tell application "Messages"
        try
          set svc to 1st service whose service type = iMessage
          send theText to buddy theBuddy of svc
        on error
          set smsService to 1st service whose service type = SMS
          send theText to buddy theBuddy of smsService
        end try
      end tell
    end run'''
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  ! osascript: {res.stderr.strip()[:200]}")
    return res.returncode == 0


def drain_outbox():
    items = _api("/bridge/outbox") or []
    for it in items:
        print(f"  -> texting {it['to']}")
        if send_imessage(it["to"], it["body"]):
            _api("/bridge/sent", {"id": it["id"]})


def _last_rowid_path() -> Path:
    return Path.home() / ".bruno_imessage_last_rowid"


def poll_inbound():
    """Push new incoming messages (since last seen ROWID) to the server."""
    if not CHAT_DB.exists():
        return
    last = 0
    p = _last_rowid_path()
    if p.exists():
        try:
            last = int(p.read_text().strip() or "0")
        except ValueError:
            last = 0
    try:
        con = sqlite3.connect(f"file:{CHAT_DB}?mode=ro", uri=True)
        rows = con.execute(
            """SELECT m.ROWID, h.id, m.text
               FROM message m JOIN handle h ON m.handle_id = h.ROWID
               WHERE m.is_from_me = 0 AND m.ROWID > ? AND m.text IS NOT NULL
               ORDER BY m.ROWID ASC LIMIT 200""", (last,)).fetchall()
        con.close()
    except Exception as e:  # noqa: BLE001
        print(f"  ! chat.db read failed (grant Full Disk Access?): {e}")
        return
    newest = last
    for rowid, sender, text in rows:
        newest = max(newest, rowid)
        if text and sender:
            print(f"  <- inbound from {sender}")
            _api("/bridge/inbound", {"from": sender, "body": text})
    if newest != last:
        _last_rowid_path().write_text(str(newest))


def main():
    if not API_URL or not TOKEN:
        sys.exit("Set API_URL and BRIDGE_TOKEN environment variables first.")
    print(f"Bruno iMessage bridge → {API_URL} (every {POLL}s). Ctrl-C to stop.")
    while True:
        try:
            drain_outbox()
            poll_inbound()
        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as e:  # noqa: BLE001
            print(f"  ! loop error: {e}")
        time.sleep(POLL)


if __name__ == "__main__":
    main()
