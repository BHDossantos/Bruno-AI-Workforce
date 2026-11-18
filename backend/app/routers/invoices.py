"""Invoicing / billing API — bill the won book of business, track payments.

Thin HTTP layer over ``billing``: the domain logic (numbering, totals, overdue
sweep, auto-settle) lives in the service so the router just validates and maps.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import billing
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/invoices", tags=["invoices"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class LineIn(BaseModel):
    description: str
    quantity: float = 1
    unit_price: float = 0


class InvoiceIn(BaseModel):
    client_name: str = Field(min_length=1)
    business: str = "insurance"
    client_id: str | None = None
    client_email: str | None = None
    issue_date: str | None = None
    due_date: str | None = None
    currency: str = "USD"
    notes: str | None = None
    lines: list[LineIn] = []


class StatusIn(BaseModel):
    status: str


class PaymentIn(BaseModel):
    amount: float = Field(gt=0)
    method: str | None = None
    reference: str | None = None
    paid_at: str | None = None


@router.get("/summary")
def summary(business: str | None = None, db: Session = Depends(get_db), _=Depends(_read)):
    return billing.summary(db, business=business)


@router.get("")
def list_invoices(business: str | None = None, status: str | None = None,
                  limit: int = 200, db: Session = Depends(get_db), _=Depends(_read)):
    return billing.list_invoices(db, business=business, status=status, limit=limit)


@router.post("")
def create_invoice(body: InvoiceIn, db: Session = Depends(get_db), _=Depends(_write)):
    inv = billing.create_invoice(
        db, client_name=body.client_name, business=body.business,
        client_id=body.client_id, client_email=body.client_email,
        issue_date=body.issue_date, due_date=body.due_date, currency=body.currency,
        notes=body.notes, lines=[ln.model_dump() for ln in body.lines])
    return billing.get_invoice(db, inv.id)


@router.get("/{invoice_id}")
def get_invoice(invoice_id: str, db: Session = Depends(get_db), _=Depends(_read)):
    out = billing.get_invoice(db, invoice_id)
    if out is None:
        raise HTTPException(404, "invoice not found")
    return out


@router.post("/{invoice_id}/status")
def set_status(invoice_id: str, body: StatusIn, db: Session = Depends(get_db), _=Depends(_write)):
    inv = billing.set_status(db, invoice_id, body.status)
    if inv is None:
        raise HTTPException(404, "invoice not found")
    return billing.get_invoice(db, invoice_id)


@router.post("/{invoice_id}/payments")
def record_payment(invoice_id: str, body: PaymentIn, db: Session = Depends(get_db), _=Depends(_write)):
    inv = billing.record_payment(db, invoice_id, amount=body.amount, method=body.method,
                                 reference=body.reference, paid_at=body.paid_at)
    if inv is None:
        raise HTTPException(404, "invoice not found")
    return billing.get_invoice(db, invoice_id)


@router.delete("/{invoice_id}")
def delete_invoice(invoice_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    if not billing.delete_invoice(db, invoice_id):
        raise HTTPException(404, "invoice not found")
    return {"ok": True}
