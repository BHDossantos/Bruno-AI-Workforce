"""AI Memory / Knowledge Graph.

A single place the AI workforce remembers everything about Bruno's world —
people, companies, leads, preferences, goals, events. Mem0-style capability,
implemented natively on Postgres: embeddings are stored as float arrays and
ranked by cosine similarity in Python (fine for a single user's volume), with a
keyword fallback when offline. No vector server, no extension, CI-safe.
"""
from __future__ import annotations

import math

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .ai import client
from .models import Memory


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def add(db: Session, content: str, *, kind: str = "fact", subject: str | None = None,
        meta: dict | None = None, source: str = "user", dedupe: bool = True) -> Memory | None:
    """Store a memory (with an embedding when AI is available)."""
    content = (content or "").strip()
    if not content:
        return None
    if dedupe:
        existing = (db.query(Memory)
                    .filter(Memory.content == content, Memory.subject == subject).first())
        if existing:
            return existing
    row = Memory(kind=kind, subject=subject, content=content, meta=meta, source=source,
                 embedding=client.embed(content))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def search(db: Session, query: str, *, k: int = 8, kind: str | None = None,
           subject: str | None = None) -> list[dict]:
    """Return the most relevant memories. Semantic when embeddings exist; else keyword."""
    q = db.query(Memory)
    if kind:
        q = q.filter(Memory.kind == kind)
    if subject:
        q = q.filter(Memory.subject == subject)

    qvec = client.embed(query) if query else None
    if qvec:
        rows = q.filter(Memory.embedding.isnot(None)).limit(2000).all()
        ranked = sorted(rows, key=lambda m: _cosine(qvec, m.embedding or []), reverse=True)
        # include any embedding-less rows by keyword as a tail
        if query:
            kw = q.filter(Memory.embedding.is_(None),
                          Memory.content.ilike(f"%{query}%")).limit(k).all()
            ranked = ranked[:k] + [r for r in kw if r not in ranked]
        return [_out(m) for m in ranked[:k]]

    # Keyword fallback (offline / no embeddings yet).
    if query:
        q = q.filter(or_(Memory.content.ilike(f"%{query}%"),
                         Memory.subject.ilike(f"%{query}%")))
    return [_out(m) for m in q.order_by(Memory.created_at.desc()).limit(k).all()]


def recall(db: Session, subject: str, k: int = 10) -> list[dict]:
    """Everything we know about a subject (person/company), newest first."""
    rows = (db.query(Memory).filter(Memory.subject.ilike(subject))
            .order_by(Memory.created_at.desc()).limit(k).all())
    return [_out(m) for m in rows]


def context_block(db: Session, query: str, k: int = 6) -> str:
    """Compact recalled-memory text to inject into an agent prompt."""
    hits = search(db, query, k=k)
    if not hits:
        return ""
    lines = "\n".join(f"- {h['content']}" for h in hits)
    return f"What you remember that may be relevant:\n{lines}"


def recall_entity(db: Session, *, name: str | None = None, email: str | None = None,
                  k: int = 25) -> list[dict]:
    """Everything we know about one person/company, recalled by name AND email and
    merged — so a note saved under a name and a reply captured under an email both
    surface on the same record. Newest first."""
    seen: dict[str, dict] = {}
    for subj in (email, name):
        if subj:
            for h in recall(db, subj, k=k):
                seen[h["id"]] = h
    return sorted(seen.values(), key=lambda h: h.get("created_at") or "", reverse=True)[:k]


def entity_context(db: Session, *, name: str | None = None, email: str | None = None,
                   k: int = 6) -> str:
    """Everything the workforce remembers about one person/company — recalled by
    name and/or email — as a compact block to inject before writing to them. This
    is what makes outreach memory-aware: it never repeats itself or forgets a
    preference, objection, or the right time to reach out."""
    rows = recall_entity(db, name=name, email=email, k=k)
    who = name or email
    blocks = []
    if rows:
        lines = "\n".join(f"- {h['content']}" for h in rows)
        blocks.append(f"What you remember about {who}:\n{lines}")
    # Fold in the relationship graph so outreach also sees who they're connected to.
    if name:
        from . import graph
        conn = graph.context_block(db, name)
        if conn:
            blocks.append(conn)
    return "\n\n".join(blocks)


def _out(m: Memory) -> dict:
    return {"id": str(m.id), "kind": m.kind, "subject": m.subject, "content": m.content,
            "source": m.source, "meta": m.meta,
            "created_at": m.created_at.isoformat() if m.created_at else None}
