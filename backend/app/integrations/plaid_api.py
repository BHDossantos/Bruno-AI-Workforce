"""Plaid bank connection (REST) — auto-populate net worth + income.

Flow: the frontend opens Plaid Link with a link_token, the user logs into their
bank, Link returns a public_token, we exchange it for an access_token (stored
encrypted on a 'plaid' connection), then sync balances → Accounts and
transactions → Transactions. Guarded so missing keys/credentials no-op.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from . import connectors

log = logging.getLogger("bruno.plaid")
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


def is_configured() -> bool:
    return bool(settings.plaid_client_id and settings.plaid_secret)


def _base() -> str:
    return f"https://{settings.plaid_env}.plaid.com"


def _post(path: str, payload: dict) -> dict | None:
    if not is_configured():
        return None
    body = {"client_id": settings.plaid_client_id, "secret": settings.plaid_secret, **payload}
    try:
        r = httpx.post(f"{_base()}{path}", json=body, timeout=_TIMEOUT)
        if r.status_code != 200:
            log.warning("Plaid %s -> %s: %s", path, r.status_code, r.text[:200])
            return None
        return r.json()
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Plaid %s failed: %s", path, exc)
        return None


def create_link_token() -> str | None:
    data = _post("/link/token/create", {
        "user": {"client_user_id": "bruno"}, "client_name": "Bruno AI Workforce",
        "products": ["transactions"], "country_codes": ["US"], "language": "en"})
    return (data or {}).get("link_token")


def exchange_public_token(db, public_token: str) -> bool:
    data = _post("/item/public_token/exchange", {"public_token": public_token})
    access = (data or {}).get("access_token")
    if not access:
        return False
    # Store as a connection (provider 'plaid'); multiple banks append.
    existing = connectors.get_credentials(db, "plaid") or {}
    tokens = existing.get("access_tokens", [])
    if access not in tokens:
        tokens.append(access)
    return connectors.update_credentials(db, "plaid", {"access_tokens": tokens}) or \
        _seed_connection(db, tokens)


def _seed_connection(db, tokens: list[str]) -> bool:
    """Create the plaid connection row if it didn't exist yet."""
    from ..models import Connection
    from ..security import encrypt_secret
    import json
    if connectors.get_connection(db, "plaid"):
        return True
    db.add(Connection(provider="plaid", display_name="Bank (Plaid)",
                      credentials_enc=encrypt_secret(json.dumps({"access_tokens": tokens})),
                      status="connected", goal="net_worth"))
    db.commit()
    return True


def sync(db) -> dict:
    """Pull balances → Accounts and transactions → Transactions for all linked banks."""
    creds = connectors.get_credentials(db, "plaid")
    if not creds:
        return {"ok": False, "reason": "no bank linked"}
    from .. import finance
    cursors = dict(creds.get("cursors") or {})
    accounts = txns = 0
    for token in creds.get("access_tokens", []):
        bal = _post("/accounts/balance/get", {"access_token": token})
        for a in (bal or {}).get("accounts", []):
            b = a.get("balances") or {}
            kind = "liability" if a.get("type") in ("credit", "loan") else "asset"
            finance.upsert_account(
                db, id=None, name=str(a.get("name")), kind=kind,
                category=a.get("subtype") or a.get("type"),
                balance=abs(b.get("current") or 0), institution="Plaid", source="plaid")
            accounts += 1
        # Incremental transactions via the stored cursor (no duplicates on re-sync).
        cursor = cursors.get(token)
        tx = _post("/transactions/sync", {"access_token": token, **({"cursor": cursor} if cursor else {})})
        for t in (tx or {}).get("added", []):
            finance.add_transaction(  # Plaid: positive = money out → flip to our sign
                db, amount=-(t.get("amount") or 0), date=None,
                category=(t.get("personal_finance_category") or {}).get("primary"),
                description=t.get("name"), source="plaid")
            txns += 1
        if tx and tx.get("next_cursor"):
            cursors[token] = tx["next_cursor"]
    connectors.update_credentials(db, "plaid", {**creds, "cursors": cursors})
    finance.rollup(db)
    return {"ok": True, "accounts": accounts, "transactions": txns}
