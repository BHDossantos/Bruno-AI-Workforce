"""Money & net-worth tracking.

Net worth from accounts (assets − liabilities), income/expense/cashflow from
transactions. Works today with manual entry + CSV import; a bank feed (Plaid)
can later write the same models with source='plaid'.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Account, Objective, Transaction

log = logging.getLogger("bruno.finance")
_LIQUID = {"checking", "savings", "cash"}


def _f(x) -> float:
    return float(x or 0)


def net_worth(db: Session) -> float:
    assets = db.query(func.coalesce(func.sum(Account.balance), 0)).filter(Account.kind == "asset").scalar()
    liab = db.query(func.coalesce(func.sum(Account.balance), 0)).filter(Account.kind == "liability").scalar()
    return round(_f(assets) - _f(liab), 2)


def summary(db: Session) -> dict:
    accounts = db.query(Account).order_by(Account.kind, Account.name).all()
    nw = net_worth(db)
    liquid = sum(_f(a.balance) for a in accounts if a.kind == "asset" and (a.category or "") in _LIQUID)

    month_start = datetime.now().date().replace(day=1)
    month_tx = db.query(Transaction).filter(Transaction.date >= month_start).all()
    income = round(sum(_f(t.amount) for t in month_tx if _f(t.amount) > 0), 2)
    expenses = round(-sum(_f(t.amount) for t in month_tx if _f(t.amount) < 0), 2)

    by_cat: dict[str, float] = {}
    for t in month_tx:
        if _f(t.amount) < 0:
            k = t.category or "Uncategorized"
            by_cat[k] = round(by_cat.get(k, 0) - _f(t.amount), 2)
    top = sorted(({"category": k, "spent": v} for k, v in by_cat.items()),
                 key=lambda c: c["spent"], reverse=True)[:8]

    return {
        "net_worth": nw, "liquid": round(liquid, 2),
        "monthly_income": income, "monthly_expenses": expenses,
        "monthly_cashflow": round(income - expenses, 2),
        "runway_months": round(liquid / expenses, 1) if expenses > 0 else None,
        "accounts": [_account_out(a) for a in accounts],
        "top_categories": top,
    }


def _account_out(a: Account) -> dict:
    return {"id": str(a.id), "name": a.name, "kind": a.kind, "category": a.category,
            "balance": _f(a.balance), "currency": a.currency,
            "institution": a.institution, "source": a.source}


def _tx_out(t: Transaction) -> dict:
    return {"id": str(t.id), "date": t.date.isoformat() if t.date else None,
            "amount": _f(t.amount), "category": t.category, "description": t.description,
            "source": t.source}


def upsert_account(db: Session, *, id=None, **fields) -> dict:
    acct = db.query(Account).filter(Account.id == id).first() if id else None
    if acct:
        for k, v in fields.items():
            if v is not None:
                setattr(acct, k, v)
        acct.updated_at = datetime.now()
    else:
        acct = Account(**{k: v for k, v in fields.items() if v is not None})
        db.add(acct)
    db.commit()
    db.refresh(acct)
    return _account_out(acct)


def delete_account(db: Session, id) -> bool:
    acct = db.query(Account).filter(Account.id == id).first()
    if not acct:
        return False
    db.delete(acct)
    db.commit()
    return True


def add_transaction(db: Session, *, amount: float, date=None, category=None,
                    description=None, source="manual") -> dict:
    tx = Transaction(amount=amount, date=date or datetime.now().date(),
                     category=category, description=description, source=source)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return _tx_out(tx)


def list_transactions(db: Session, limit: int = 100) -> list[dict]:
    rows = (db.query(Transaction).order_by(Transaction.date.desc(),
            Transaction.created_at.desc()).limit(limit).all())
    return [_tx_out(t) for t in rows]


def import_csv(db: Session, text: str) -> dict:
    """Import transactions from a bank CSV (date, amount[, category, description])."""
    reader = csv.DictReader(io.StringIO(text))
    imported = skipped = 0
    for row in reader:
        low = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        raw = low.get("amount") or low.get("value")
        if not raw:
            skipped += 1
            continue
        try:
            amount = float(raw.replace("$", "").replace(",", ""))
        except ValueError:
            skipped += 1
            continue
        d = None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                d = datetime.strptime(low.get("date", ""), fmt).date()
                break
            except ValueError:
                continue
        db.add(Transaction(amount=amount, date=d or datetime.now().date(),
                           category=low.get("category"),
                           description=low.get("description") or low.get("memo"), source="csv"))
        imported += 1
    db.commit()
    return {"imported": imported, "skipped": skipped}


def rollup(db: Session) -> None:
    """Push net worth into the net_worth objective's current_value."""
    obj = db.query(Objective).filter(Objective.key == "net_worth").first()
    if obj is not None:
        obj.current_value = net_worth(db)
        db.commit()
