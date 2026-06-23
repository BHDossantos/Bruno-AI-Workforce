"""One-time Gmail OAuth helper.

Usage:
    1. In Google Cloud Console, create an OAuth 2.0 "Desktop app" client and
       download the credentials as ``client_secret.json``.
    2. Run:  python -m app.scripts.gmail_auth /path/to/client_secret.json
    3. Complete the browser consent flow.
    4. Copy the printed JSON into the ``GOOGLE_TOKEN_JSON`` env var (single line).

The token contains a refresh token, so the backend can send/read mail headless.
"""
import sys

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m app.scripts.gmail_auth <client_secret.json>")
        raise SystemExit(1)
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
    creds = flow.run_local_server(port=0)
    print("\n--- Set this as GOOGLE_TOKEN_JSON (one line) ---\n")
    print(creds.to_json())


if __name__ == "__main__":
    main()
