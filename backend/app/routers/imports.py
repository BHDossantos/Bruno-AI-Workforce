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


async def _rows(file: UploadFile) -> list[dict]:
    """Parse an uploaded contact file from ANY platform — CSV (Google, Outlook,
    LinkedIn, …) or an Apple/iCloud/iPhone vCard (.vcf)."""
    content = (await file.read()).decode("utf-8-sig", errors="ignore")
    is_vcard = (file.filename or "").lower().endswith(".vcf") \
        or "BEGIN:VCARD" in content[:200].upper()
    if is_vcard:
        return importer.parse_vcards(content)
    return list(csv.DictReader(io.StringIO(content)))


@router.post("/leads")
async def import_leads(file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(_write)):
    return importer.process_leads_csv(db, await _rows(file))


@router.post("/restaurants")
async def import_restaurants(file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(_write)):
    return importer.process_restaurants_csv(db, await _rows(file))


@router.post("/contacts")
async def import_contacts(file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(_write)):
    """Import a personal contact list from any platform — Google/Outlook/LinkedIn
    CSV or an iPhone/iCloud vCard (.vcf) — into the CRM."""
    return importer.process_contacts_csv(db, await _rows(file))


@router.get("/template/leads.csv", response_class=PlainTextResponse)
def leads_template():
    return ("email,company_name,owner_name,phone,website,linkedin,industry,segment,category\n"
            "owner@acme.com,Acme Plumbing,Jane Doe,+16175551212,https://acme.com,,Contractor,commercial,Contractor\n")


@router.get("/template/restaurants.csv", response_class=PlainTextResponse)
def restaurants_template():
    return ("email,name,owner_manager,phone,website,instagram,cuisine,city\n"
            "info@bistro.com,Bistro 21,Marco Rossi,+16175551212,https://bistro21.com,@bistro21,Italian,Boston\n")
