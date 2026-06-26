"""The relationship graph — edges between entities so the workforce reasons across
connections, not isolated rows (recruiter → company → hiring manager → interview;
"referred by"; "introduced by"). Edges are keyed by an entity's memory *subject*
(usually its name), so the graph and the memory layer share one identity space.

Lightweight on Postgres: a single edges table, traversed one hop. Surfaced in the
CRM and folded into memory recall, so every memory-aware prompt also sees who an
entity is connected to.
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .models import Relationship

# How a stored relation reads back from each side of the edge.
_INVERSE = {
    "works_at": "employs",
    "hiring_manager_for": "has hiring manager",
    "referred_by": "referred",
    "introduced_by": "introduced",
    "reports_to": "manages",
}


def _norm(s: str | None) -> str:
    return (s or "").strip()


def link(db: Session, from_subject: str, to_subject: str, relation: str, *,
         from_type: str | None = None, to_type: str | None = None,
         note: str | None = None, source: str = "manual") -> Relationship | None:
    """Create an edge (idempotent on the same from/to/relation triple)."""
    a, b, rel = _norm(from_subject), _norm(to_subject), _norm(relation)
    if not a or not b or not rel or a.lower() == b.lower():
        return None
    existing = (db.query(Relationship).filter(
        Relationship.from_subject == a, Relationship.to_subject == b,
        Relationship.relation == rel).first())
    if existing:
        return existing
    row = Relationship(from_subject=a, from_type=from_type, to_subject=b,
                       to_type=to_type, relation=rel, note=note, source=source)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def unlink(db: Session, edge_id: str) -> bool:
    row = db.query(Relationship).filter(Relationship.id == edge_id).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def neighbors(db: Session, subject: str, k: int = 40) -> list[dict]:
    """One-hop connections for an entity (either direction), newest first."""
    s = _norm(subject)
    if not s:
        return []
    rows = (db.query(Relationship).filter(
        or_(Relationship.from_subject.ilike(s), Relationship.to_subject.ilike(s)))
        .order_by(Relationship.created_at.desc()).limit(k).all())
    out = []
    for r in rows:
        outgoing = r.from_subject.lower() == s.lower()
        other = r.to_subject if outgoing else r.from_subject
        rel = r.relation if outgoing else _INVERSE.get(r.relation, f"{r.relation} (of)")
        out.append({
            "id": str(r.id), "subject": other,
            "type": (r.to_type if outgoing else r.from_type),
            "relation": rel, "direction": "out" if outgoing else "in",
            "note": r.note,
        })
    return out


def context_block(db: Session, subject: str, k: int = 12) -> str:
    """Compact connections text to fold into a memory/outreach prompt."""
    rows = neighbors(db, subject, k=k)
    if not rows:
        return ""
    lines = "\n".join(f"- {r['relation']} {r['subject']}" for r in rows)
    return f"Known connections of {subject}:\n{lines}"
