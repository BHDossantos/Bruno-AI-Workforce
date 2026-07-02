"""Accounts API — the Salesforce-style "one page per company" view."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import accounts
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/accounts", tags=["accounts"])
_read = require_role("admin", "operator", "viewer")


@router.get("")
def list_accounts(q: str | None = None, business: str | None = None, limit: int = 200,
                  db: Session = Depends(get_db), _=Depends(_read)):
    return accounts.list_accounts(db, q=q, business=business, limit=limit)


@router.get("/{account_id}")
def get_account(account_id: str, db: Session = Depends(get_db), _=Depends(_read)):
    acc = accounts.get_account(db, account_id)
    if not acc:
        raise HTTPException(404, "account not found")
    return acc
