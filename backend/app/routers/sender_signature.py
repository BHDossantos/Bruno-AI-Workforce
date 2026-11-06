"""Current user's sender signature. No user-ID parameter or global assignment."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import EmailStr
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import SenderSignature
from ..security import require_role
from ..sender_signatures import Signature, validate_png, MAX_PNG_BYTES

router = APIRouter(prefix="/sender-signature", tags=["sender signature"])
_operator = require_role("admin", "operator")


def owned_signature(db, user):
    row = db.get(SenderSignature, user.id)
    if row is None:
        raise HTTPException(404, "No signature uploaded for your sender profile")
    return row


@router.get("")
def current(db: Session = Depends(get_db), user=Depends(_operator)):
    row = db.get(SenderSignature, user.id)
    return ({"configured": True, "mailbox": row.mailbox, "plain_text": row.plain_text,
             "source_ref": row.source_ref, "digest": row.digest} if row else {"configured": False})


@router.get("/image")
def image(db: Session = Depends(get_db), user=Depends(_operator)):
    row = owned_signature(db, user)
    return Response(row.png, media_type="image/png",
                    headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.put("")
async def upload(file: UploadFile = File(...), mailbox: EmailStr = Form(...),
                 plain_text: str = Form(..., min_length=1, max_length=2000),
                 source_ref: str = Form(..., min_length=1, max_length=1000),
                 db: Session = Depends(get_db), user=Depends(_operator)):
    data = await file.read(MAX_PNG_BYTES + 1)
    try:
        validate_png(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not plain_text.strip() or not source_ref.strip():
        raise HTTPException(422, "Signature text and approved source reference are required")
    row = db.get(SenderSignature, user.id)
    if row is None:
        row = SenderSignature(user_id=user.id)
        db.add(row)
    row.mailbox, row.png, row.plain_text, row.source_ref = str(mailbox).lower(), data, plain_text, source_ref
    row.digest = Signature(data, plain_text).digest
    db.commit()
    return current(db, user)
