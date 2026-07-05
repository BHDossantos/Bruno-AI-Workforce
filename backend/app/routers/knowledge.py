"""Insurance Knowledge Base routes — store docs and ask questions of them."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class DocIn(BaseModel):
    title: str
    content: str
    tags: list[str] = []


class AskIn(BaseModel):
    question: str


@router.get("")
def list_docs(db: Session = Depends(get_db), _=Depends(_read)):
    """All knowledge-base docs, newest first."""
    from .. import knowledge
    return knowledge.list_docs(db)


@router.post("")
def add_doc(body: DocIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Add a doc — a carrier guideline, discount rule, coverage FAQ, claims note."""
    from .. import knowledge
    if not body.title.strip() or not body.content.strip():
        raise HTTPException(400, "Title and content are required")
    return knowledge.out(knowledge.add(db, body.title, body.content, body.tags))


@router.delete("/{doc_id}")
def delete_doc(doc_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Remove a doc from the knowledge base."""
    from .. import knowledge
    if not knowledge.delete(db, doc_id):
        raise HTTPException(404, "Doc not found")
    return {"ok": True}


@router.post("/ask")
def ask(body: AskIn, db: Session = Depends(get_db), _=Depends(_read)):
    """Ask a plain-English question; the AI answers from the docs and cites them."""
    from .. import knowledge
    return knowledge.answer(db, body.question)


@router.post("/seed")
def seed(db: Session = Depends(get_db), _=Depends(_write)):
    """Load the starter insurance docs (MA/NH/FL discounts, coverage basics,
    EverQuote handling) — only if the knowledge base is currently empty."""
    from .. import knowledge_seed
    return knowledge_seed.seed_if_empty(db)
