"""Insurance Knowledge Base — the AI answers from your docs, not from guesses.

Store carrier guidelines, discount rules, coverage FAQs, claims notes and
training snippets, then ask plain-English questions. Retrieval is keyword-ranked
(fully offline); when the OpenAI key is connected the top docs are summarized
into a direct answer — but the matching passages are always returned as the
citable source, so an answer is never unsupported.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .models import KnowledgeDoc

log = logging.getLogger("bruno.knowledge")

_STOP = {"the", "a", "an", "is", "are", "of", "to", "for", "and", "or", "in", "on",
         "what", "how", "do", "does", "i", "my", "with", "can", "will", "be", "it",
         "this", "that", "you", "your", "we", "if", "when", "which", "who", "about"}


def _terms(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(w) > 2 and w not in _STOP]


def add(db: Session, title: str, content: str, tags: list[str] | None = None,
        source: str = "manual") -> KnowledgeDoc:
    doc = KnowledgeDoc(title=title.strip(), content=content.strip(),
                       tags=[t.strip() for t in (tags or []) if t.strip()], source=source)
    db.add(doc); db.commit(); db.refresh(doc)
    return doc


def out(doc: KnowledgeDoc) -> dict:
    return {"id": str(doc.id), "title": doc.title, "content": doc.content,
            "tags": doc.tags or [], "source": doc.source,
            "created_at": doc.created_at.isoformat() if doc.created_at else None}


def list_docs(db: Session, limit: int = 200) -> list[dict]:
    rows = db.query(KnowledgeDoc).order_by(KnowledgeDoc.created_at.desc()).limit(limit).all()
    return [out(d) for d in rows]


def delete(db: Session, doc_id: str) -> bool:
    doc = db.query(KnowledgeDoc).filter(KnowledgeDoc.id == doc_id).first()
    if not doc:
        return False
    db.delete(doc); db.commit()
    return True


def _score(doc: KnowledgeDoc, terms: list[str]) -> int:
    hay = f"{doc.title} {doc.title} {' '.join(doc.tags or [])} {doc.content}".lower()
    return sum(hay.count(t) for t in terms)


def _snippet(content: str, terms: list[str], width: int = 260) -> str:
    low = content.lower()
    pos = min((low.find(t) for t in terms if low.find(t) >= 0), default=-1)
    if pos < 0:
        return content[:width].strip()
    start = max(0, pos - width // 3)
    return ("…" if start > 0 else "") + content[start:start + width].strip() + \
           ("…" if start + width < len(content) else "")


def search(db: Session, query: str, limit: int = 5) -> list[dict]:
    terms = _terms(query)
    if not terms:
        return []
    scored = []
    for doc in db.query(KnowledgeDoc).all():
        s = _score(doc, terms)
        if s > 0:
            scored.append((s, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{**out(doc), "score": s, "snippet": _snippet(doc.content, terms)}
            for s, doc in scored[:limit]]


def answer(db: Session, question: str) -> dict:
    """Answer a question from the knowledge base, citing the source docs."""
    hits = search(db, question, limit=4)
    if not hits:
        return {"ok": True, "answer": "Nothing in the knowledge base covers that yet — add a "
                "doc (carrier guideline, discount rule, FAQ) and ask again.",
                "sources": [], "ai_used": False, "generated_at": _now()}

    ai_answer = None
    try:
        from .ai import client
        if client.is_live():
            context = "\n\n".join(f"[{h['title']}]\n{h['content'][:1200]}" for h in hits)
            ai_answer = client.complete(
                f"Answer the insurance question using ONLY the reference docs below. Be specific "
                f"and concise; if the docs don't cover it, say so. Do not invent carrier rules.\n\n"
                f"Question: {question}\n\nReference docs:\n{context}",
                system="You are an expert insurance assistant. Answer only from the provided docs.")
            if ai_answer and ai_answer.startswith("["):
                ai_answer = None
    except Exception:
        log.debug("knowledge answer AI step skipped", exc_info=True)

    fallback = f"Top match — {hits[0]['title']}: {hits[0]['snippet']}"
    return {"ok": True, "answer": ai_answer or fallback,
            "sources": [{"id": h["id"], "title": h["title"], "snippet": h["snippet"],
                         "tags": h["tags"]} for h in hits],
            "ai_used": bool(ai_answer), "generated_at": _now()}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
