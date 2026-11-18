"""Invoicing / billing — the agency's own client billing layer.

A self-contained domain (narrow public interface, its own tests) that bills the
WON book of business: an invoice has line items, a running paid total from its
Payment rows, and a lifecycle (Draft → Sent → Paid, or Overdue/Void). Totals are
recomputed and stored on every write so a read never sums on the fly, and
``overdue_sweep`` is a hands-free pass the scheduler runs to flip past-due Sent
invoices to Overdue — no human click.

Numbers are INV-<year>-<4-digit sequence>, sequential within the calendar year.
No new columns on existing tables — three brand-new tables only (create_all safe).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Invoice, InvoiceLine, Payment

OPEN_STATUSES = ("Draft", "Sent", "Overdue")


def _money(v) -> Decimal:
    """Coerce anything (str, float, int, Decimal, None) to a 2-dp Decimal."""
    if v is None or v == "":
        return Decimal("0.00")
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _parse_date(v) -> date | None:
    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)).date()
    except ValueError:
        return None


def next_number(db: Session, when: date | None = None) -> str:
    """Next INV-<year>-NNNN, sequential within the year. Counts existing rows for
    the year's prefix so it keeps counting after a restart (no in-memory counter)."""
    year = (when or date.today()).year
    prefix = f"INV-{year}-"
    n = db.query(func.count()).select_from(Invoice).filter(
        Invoice.number.like(f"{prefix}%")).scalar() or 0
    return f"{prefix}{n + 1:04d}"


def _recompute(inv: Invoice) -> None:
    """Refresh stored subtotal/total/amount_paid + derived status from the rows."""
    subtotal = sum((_money(ln.amount) for ln in inv.lines), Decimal("0.00"))
    inv.subtotal = subtotal
    inv.total = subtotal
    paid = sum((_money(p.amount) for p in _payments(inv)), Decimal("0.00"))
    inv.amount_paid = paid
    # Auto-settle: a Sent/Overdue invoice fully covered becomes Paid; a Paid one
    # that loses coverage (payment removed) falls back to Sent. Draft/Void are left
    # alone — they are explicit human states.
    if inv.status in ("Sent", "Overdue") and paid >= subtotal and subtotal > 0:
        inv.status = "Paid"
        inv.paid_at = inv.paid_at or datetime.now(timezone.utc)
    elif inv.status == "Paid" and paid < subtotal:
        inv.status = "Sent"
        inv.paid_at = None


def _payments(inv: Invoice) -> list[Payment]:
    """Payment rows for an invoice (loaded via its session)."""
    sess = Session.object_session(inv)
    if sess is None:
        return []
    return sess.query(Payment).filter(Payment.invoice_id == inv.id).all()


def create_invoice(db: Session, *, client_name: str, business: str = "insurance",
                   client_id=None, client_email: str | None = None,
                   issue_date=None, due_date=None, currency: str = "USD",
                   notes: str | None = None, lines: list[dict] | None = None) -> Invoice:
    inv = Invoice(
        number=next_number(db),
        business=business or "insurance",
        client_id=client_id,
        client_name=client_name,
        client_email=client_email,
        currency=currency or "USD",
        issue_date=_parse_date(issue_date) or date.today(),
        due_date=_parse_date(due_date),
        status="Draft",
        notes=notes,
    )
    for ln in (lines or []):
        qty = _money(ln.get("quantity", 1) or 1)
        unit = _money(ln.get("unit_price", 0))
        inv.lines.append(InvoiceLine(
            description=(ln.get("description") or "").strip() or "Item",
            quantity=qty, unit_price=unit, amount=(qty * unit).quantize(Decimal("0.01"))))
    _recompute(inv)
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def set_status(db: Session, invoice_id, status: str) -> Invoice | None:
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        return None
    status = status.capitalize()
    if status not in ("Draft", "Sent", "Paid", "Overdue", "Void"):
        return inv
    inv.status = status
    if status == "Sent" and inv.sent_at is None:
        inv.sent_at = datetime.now(timezone.utc)
    if status == "Paid":
        inv.paid_at = inv.paid_at or datetime.now(timezone.utc)
    if status in ("Draft", "Sent", "Overdue", "Void"):
        inv.paid_at = None if status != "Overdue" else inv.paid_at
    db.commit()
    db.refresh(inv)
    return inv


def record_payment(db: Session, invoice_id, *, amount, method: str | None = None,
                   reference: str | None = None, paid_at=None) -> Invoice | None:
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        return None
    db.add(Payment(invoice_id=inv.id, amount=_money(amount), method=method,
                   reference=reference, paid_at=_parse_date(paid_at) or date.today()))
    db.flush()
    _recompute(inv)
    db.commit()
    db.refresh(inv)
    return inv


def overdue_sweep(db: Session) -> dict:
    """Flip Sent invoices past their due date to Overdue — hands-free, scheduler-run."""
    today = date.today()
    rows = db.query(Invoice).filter(
        Invoice.status == "Sent", Invoice.due_date.isnot(None),
        Invoice.due_date < today).all()
    for inv in rows:
        inv.status = "Overdue"
    if rows:
        db.commit()
    return {"flipped": len(rows)}


def _to_dict(inv: Invoice, *, with_lines: bool = False) -> dict:
    total = _money(inv.total)
    paid = _money(inv.amount_paid)
    out = {
        "id": str(inv.id), "number": inv.number, "business": inv.business,
        "client_id": str(inv.client_id) if inv.client_id else None,
        "client_name": inv.client_name, "client_email": inv.client_email,
        "status": inv.status, "currency": inv.currency,
        "issue_date": inv.issue_date.isoformat() if inv.issue_date else None,
        "due_date": inv.due_date.isoformat() if inv.due_date else None,
        "subtotal": float(_money(inv.subtotal)), "total": float(total),
        "amount_paid": float(paid), "balance": float(total - paid),
        "notes": inv.notes,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
    }
    if with_lines:
        out["lines"] = [{
            "id": str(ln.id), "description": ln.description,
            "quantity": float(_money(ln.quantity)), "unit_price": float(_money(ln.unit_price)),
            "amount": float(_money(ln.amount)),
        } for ln in inv.lines]
        out["payments"] = [{
            "id": str(p.id), "amount": float(_money(p.amount)), "method": p.method,
            "reference": p.reference,
            "paid_at": p.paid_at.isoformat() if p.paid_at else None,
        } for p in _payments(inv)]
    return out


def list_invoices(db: Session, *, business: str | None = None,
                  status: str | None = None, limit: int = 200) -> list[dict]:
    q = db.query(Invoice)
    if business:
        q = q.filter(Invoice.business == business)
    if status:
        q = q.filter(Invoice.status == status.capitalize())
    rows = q.order_by(Invoice.created_at.desc()).limit(limit).all()
    return [_to_dict(r) for r in rows]


def get_invoice(db: Session, invoice_id) -> dict | None:
    inv = db.get(Invoice, invoice_id)
    return _to_dict(inv, with_lines=True) if inv else None


def delete_invoice(db: Session, invoice_id) -> bool:
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        return False
    db.delete(inv)
    db.commit()
    return True


def summary(db: Session, *, business: str | None = None) -> dict:
    """Billing at a glance — outstanding, overdue, paid this month, counts."""
    q = db.query(Invoice)
    if business:
        q = q.filter(Invoice.business == business)
    rows = q.all()
    month_start = date.today().replace(day=1)
    outstanding = overdue = paid_month = Decimal("0.00")
    counts: dict[str, int] = {}
    for inv in rows:
        counts[inv.status] = counts.get(inv.status, 0) + 1
        bal = _money(inv.total) - _money(inv.amount_paid)
        if inv.status in OPEN_STATUSES:
            outstanding += bal
        if inv.status == "Overdue":
            overdue += bal
        if inv.status == "Paid" and inv.paid_at and inv.paid_at.date() >= month_start:
            paid_month += _money(inv.amount_paid)
    return {
        "outstanding": float(outstanding), "overdue": float(overdue),
        "paid_this_month": float(paid_month), "total_invoices": len(rows),
        "counts": counts,
    }
