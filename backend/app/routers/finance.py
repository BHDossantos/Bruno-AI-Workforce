"""Money & net-worth API."""
import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import finance
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/finance", tags=["finance"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class AccountIn(BaseModel):
    id: str | None = None
    name: str
    kind: str = "asset"
    category: str | None = None
    balance: float = 0
    institution: str | None = None


class TxIn(BaseModel):
    amount: float
    date: str | None = None
    category: str | None = None
    description: str | None = None


@router.get("/summary")
def summary(db: Session = Depends(get_db), _=Depends(_read)):
    return finance.summary(db)


@router.post("/accounts")
def upsert_account(body: AccountIn, db: Session = Depends(get_db), _=Depends(_write)):
    out = finance.upsert_account(db, **body.model_dump())
    finance.rollup(db)
    return out


@router.delete("/accounts/{account_id}")
def delete_account(account_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    if not finance.delete_account(db, account_id):
        raise HTTPException(404, "account not found")
    finance.rollup(db)
    return {"ok": True}


@router.get("/transactions")
def transactions(limit: int = 100, db: Session = Depends(get_db), _=Depends(_read)):
    return finance.list_transactions(db, limit)


@router.post("/transactions")
def add_transaction(body: TxIn, db: Session = Depends(get_db), _=Depends(_write)):
    from datetime import datetime
    d = None
    if body.date:
        try:
            d = datetime.fromisoformat(body.date).date()
        except ValueError:
            d = None
    return finance.add_transaction(db, amount=body.amount, date=d,
                                   category=body.category, description=body.description)


class PublicToken(BaseModel):
    public_token: str


@router.get("/plaid/status")
def plaid_status(db: Session = Depends(get_db), _=Depends(_read)):
    from ..integrations import connectors, plaid_api
    return {"configured": plaid_api.is_configured(), "linked": connectors.is_connected(db, "plaid")}


@router.post("/plaid/link-token")
def plaid_link_token(_=Depends(_write)):
    from ..integrations import plaid_api
    tok = plaid_api.create_link_token()
    return {"link_token": tok} if tok else {"error": "Plaid not configured"}


@router.post("/plaid/exchange")
def plaid_exchange(body: PublicToken, db: Session = Depends(get_db), _=Depends(_write)):
    from ..integrations import plaid_api
    ok = plaid_api.exchange_public_token(db, body.public_token)
    if ok:
        plaid_api.sync(db)
    return {"ok": ok}


@router.post("/plaid/sync")
def plaid_sync(db: Session = Depends(get_db), _=Depends(_write)):
    from ..integrations import plaid_api
    return plaid_api.sync(db)


@router.post("/import")
async def import_transactions(file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(_write)):
    content = (await file.read()).decode("utf-8-sig", errors="ignore")
    # validate it parses as CSV before handing to the importer
    list(csv.reader(io.StringIO(content[:200])))
    return finance.import_csv(db, content)
