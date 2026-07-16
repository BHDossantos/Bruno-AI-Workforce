"""CSV import endpoints — bring your own real contact lists."""
import csv
import io

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from .. import importer
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/import", tags=["import"])
_write = require_role("admin", "operator")


_HEADER_HINTS = ("first name", "last name", "name", "email", "e-mail", "company")


def _csv_rows(content: str) -> list[dict]:
    """DictReader, but tolerant of a preamble before the real header row — e.g.
    LinkedIn's Connections.csv starts with a 3-line 'Notes:' block, which would
    otherwise make DictReader treat 'Notes:' as the only column (→ 0 imported)."""
    lines = content.splitlines()
    start = 0
    for i, ln in enumerate(lines[:10]):
        low = ln.lower()
        if "," in ln and sum(h in low for h in _HEADER_HINTS) >= 1:
            start = i
            break
    return list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))


async def _rows(file: UploadFile) -> list[dict]:
    """Parse an uploaded contact file from ANY platform — CSV (Google, Outlook,
    LinkedIn, …) or an Apple/iCloud/iPhone vCard (.vcf)."""
    content = (await file.read()).decode("utf-8-sig", errors="ignore")
    is_vcard = (file.filename or "").lower().endswith(".vcf") \
        or "BEGIN:VCARD" in content[:200].upper()
    if is_vcard:
        return importer.parse_vcards(content)
    return _csv_rows(content)


@router.post("/leads")
async def import_leads(file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(_write)):
    return importer.process_leads_csv(db, await _rows(file))


@router.post("/bnb")
async def import_bnb(file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(_write)):
    """Import B&B Global (tech consulting) leads — sent from the BnB mailbox."""
    return importer.process_bnb_csv(db, await _rows(file))


@router.post("/restaurants")
async def import_restaurants(file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(_write)):
    return importer.process_restaurants_csv(db, await _rows(file))


@router.post("/contacts")
async def import_contacts(file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(_write)):
    """Import a personal contact list from any platform — Google/Outlook/LinkedIn
    CSV or an iPhone/iCloud vCard (.vcf) — into the CRM."""
    return importer.process_contacts_csv(db, await _rows(file))


@router.get("/template/leads.csv", response_class=PlainTextResponse)
def leads_template(_=Depends(require_role("admin", "operator", "viewer"))):
    return ("email,company_name,owner_name,phone,website,linkedin,industry,segment,category\n"
            "owner@acme.com,Acme Plumbing,Jane Doe,+16175551212,https://acme.com,,Contractor,commercial,Contractor\n")


@router.get("/template/bnb.csv", response_class=PlainTextResponse)
def bnb_template(_=Depends(require_role("admin", "operator", "viewer"))):
    return ("email,company_name,owner_name,phone,website,linkedin,industry,category\n"
            "cto@saasco.com,SaaSCo,Alex Kim,+16175551212,https://saasco.com,,SaaS,Technology\n")


@router.get("/template/restaurants.csv", response_class=PlainTextResponse)
def restaurants_template(_=Depends(require_role("admin", "operator", "viewer"))):
    return ("email,name,owner_manager,phone,website,instagram,cuisine,city\n"
            "info@bistro.com,Bistro 21,Marco Rossi,+16175551212,https://bistro21.com,@bistro21,Italian,Boston\n")
