"""No live calls: durable fences, terminal replay and signed routing boundaries."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from app.models import Lead, DoNotContact
from app.calling_capacity_models import CallHandler, CallPermit, CallReservation, CallLeadHold
from app import calling_capacity as c
from app.routers import calling_capacity as r
from app.database import get_db

@compiles(JSONB, "sqlite")
def jsonb(element, compiler, **kw): return "JSON"

@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in (Lead, DoNotContact, CallHandler, CallPermit, CallReservation, CallLeadHold): model.__table__.create(engine)
    monkeypatch.setattr(c.settings, "auto_dial_capacity_enabled", False)
    with Session(engine) as session: yield session
    engine.dispose()

def setup(db, phone="+16175550101", handler_phone="+16175550201"):
    now = datetime.now(timezone.utc)
    lead = Lead(id=uuid4(), segment="commercial", phone=phone)
    db.add(lead)
    db.flush()  # Persist FK parent before independent permit mapper flushes.
    db.add(CallPermit(lead_id=lead.id, phone=phone, state="MA", recipient_timezone="America/New_York", authorization_ref="fixture:consent", expires_at=now+timedelta(days=1)))
    h = CallHandler(id=uuid4(), phone=handler_phone, states=["MA"], authorization_ref="fixture:license", verified_until=now+timedelta(days=1), available_until=now+timedelta(minutes=15))
    db.add(h); db.commit()
    return lead, h

def test_disabled_dispatch_no_provider(db, monkeypatch):
    lead, h = setup(db)
    from app.integrations import voice
    monkeypatch.setattr(voice, "place_auto_call", lambda *a, **kw: pytest.fail("provider called"))
    assert c.dispatch(db, lead) == (None, "capacity calling disabled")
    assert h.reservation_id is None

def test_one_slot_one_lead_across_workers(db):
    lead, h = setup(db); row = c.reserve(db, lead)
    assert row and h.reservation_id == row.id
    with Session(db.bind) as other: assert c.reserve(other, other.get(Lead, lead.id)) is None
    second = Lead(id=uuid4(), segment="commercial", phone="+16175550102")
    db.add(second); db.add(CallPermit(lead_id=second.id, phone=second.phone, state="MA", recipient_timezone="America/New_York", authorization_ref="fixture:consent", expires_at=datetime.now(timezone.utc)+timedelta(days=1))); db.commit()
    assert c.reserve(db, second) is None

def test_two_handlers_two_legs(db):
    first, _ = setup(db); second, _ = setup(db, "+16175550102", "+16175550202")
    a, b = c.reserve(db, first), c.reserve(db, second)
    assert a and b and a.handler_id != b.handler_id
    assert c.reserve(db, first) is None

@pytest.mark.parametrize("change", ["expired_permit","wrong_phone","expired_handler","unavailable","wrong_state","no_permit","dnc"])
def test_ineligible_never_reserves(db, change):
    lead,h=setup(db); p=db.get(CallPermit,lead.id); past=datetime.now(timezone.utc)-timedelta(days=1)
    if change=="expired_permit": p.expires_at=past
    if change=="wrong_phone": p.phone="+16175550999"
    if change=="expired_handler": h.verified_until=past
    if change=="unavailable": h.available_until=past
    if change=="wrong_state": h.states=["NH"]
    if change=="no_permit": db.delete(p)
    if change=="dnc": db.add(DoNotContact(kind="phone", value=c.compliance._phone_key(lead.phone)))
    db.commit(); assert c.reserve(db,lead) is None

def test_unknown_outcome_holds(db):
    lead,h=setup(db); row=c.reserve(db,lead); c.provider_result(db,row.id,None,"timeout")
    assert row.status=="uncertain" and h.reservation_id==row.id
    assert c.reserve(db,lead,datetime.now(timezone.utc)+timedelta(days=100)) is None

def test_not_attempted_releases(db):
    lead,h=setup(db); row=c.reserve(db,lead)
    c.provider_result(db,row.id,None,c.outbound_guard.no_attempt("not ready","configuration").error)
    assert row.status=="terminal" and h.reservation_id is None
    assert db.get(CallLeadHold,lead.id) is None

def test_early_duplicate_terminal_callback(db):
    lead,h=setup(db); row=c.reserve(db,lead)
    assert c.callback(db,row.id,"CAfixture","completed")
    c.provider_result(db,row.id,"CAfixture",None)
    assert c.callback(db,row.id,"CAfixture","ringing")
    assert not c.callback(db,row.id,"CAother","completed")
    assert row.status=="terminal" and h.reservation_id is None

def test_mismatched_sid_cannot_free(db):
    lead,h=setup(db); row=c.reserve(db,lead); c.provider_result(db,row.id,"CAfixture",None)
    assert not c.callback(db,row.id,"CAother","completed")
    assert h.reservation_id==row.id

def test_target_rechecks_dnc(db):
    lead,h=setup(db); row=c.reserve(db,lead)
    assert c.transfer_target(db,row.id,"CAfixture")==h.phone
    db.add(DoNotContact(kind="phone", value=c.compliance._phone_key(lead.phone))); db.commit()
    assert c.transfer_target(db,row.id,"CAfixture") is None
    assert h.reservation_id==row.id

def test_api_auth_required(db, monkeypatch):
    monkeypatch.setattr(c.settings, "environment", "production")
    app=FastAPI(); app.include_router(r.router); app.dependency_overrides[get_db]=lambda:db
    with TestClient(app) as client:
        assert client.get("/calls/capacity/status").status_code in (401,403)
        assert client.post("/calls/capacity/amd",params={"reservation_id":str(uuid4())},data={"CallSid":"CAfixture"}).status_code in (401,403,503)

def test_unknown_amd_no_bridge(db,monkeypatch):
    lead,h=setup(db); row=c.reserve(db,lead)
    monkeypatch.setattr(c.settings,"auto_dial_capacity_enabled",True)
    monkeypatch.setattr(r.control,"is_paused_safe",lambda db:False)
    app=FastAPI(); app.include_router(r.router); app.dependency_overrides[get_db]=lambda:db
    app.dependency_overrides[r.require_twilio_callback]=lambda:None
    with TestClient(app) as client:
        for value in ("unknown","","machine_end_beep"):
            res=client.post("/calls/capacity/amd",params={"reservation_id":str(row.id)},data={"CallSid":"CAfixture","AnsweredBy":value})
            assert "<Hangup/>" in res.text and "<Dial" not in res.text

def test_rejects_unknown_state_and_stale_expiry():
    from pydantic import ValidationError
    base=dict(phone="+16175550101",authorization_ref="fixture:permission",expires_at=datetime.now(timezone.utc)+timedelta(days=1))
    with pytest.raises(ValidationError): r.PermitInput(**base,state="ZZ")
    with pytest.raises(ValidationError): r.HandlerInput(**{**base,"expires_at":datetime.now(timezone.utc)-timedelta(days=1)},states=["MA"])

def test_human_amd_routes_only_reserved_handler(db,monkeypatch):
    lead,h=setup(db); row=c.reserve(db,lead)
    monkeypatch.setattr(c.settings,"auto_dial_capacity_enabled",True)
    monkeypatch.setattr(r.control,"is_paused_safe",lambda db:False)
    from app.integrations import twilio_voice
    monkeypatch.setattr(twilio_voice,"_base_url",lambda:"https://fixture.example")
    monkeypatch.setattr(twilio_voice,"bridge_caller_id",lambda target:"+16175550301")
    app=FastAPI(); app.include_router(r.router); app.dependency_overrides[get_db]=lambda:db
    app.dependency_overrides[r.require_twilio_callback]=lambda:None
    with TestClient(app) as client:
        res=client.post("/calls/capacity/amd",params={"reservation_id":str(row.id)},data={"CallSid":"CAfixture","AnsweredBy":"human"})
        assert "<Dial " in res.text and h.phone in res.text
        assert "record=" not in res.text and "quote you requested" not in res.text
        h.available_until=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
        res=client.post("/calls/capacity/amd",params={"reservation_id":str(row.id)},data={"CallSid":"CAfixture","AnsweredBy":"human"})
        assert "<Dial " not in res.text

def test_dispatch_uses_reserved_path_and_uncertainty_holds(db,monkeypatch):
    lead,h=setup(db)
    from app.integrations import voice
    from app import auto_dial
    monkeypatch.setattr(c.settings,"auto_dial_capacity_enabled",True)
    monkeypatch.setattr(c.settings,"environment","production")
    monkeypatch.setattr(auto_dial,"auto_dial_enabled",lambda:True)
    monkeypatch.setattr(c.control,"is_paused_safe",lambda db:False)
    monkeypatch.setattr(c.control,"get_mode",lambda db:"auto")
    monkeypatch.setattr(c.sms_engine,"in_call_window",lambda:True)
    monkeypatch.setattr(c,"recipient_in_window",lambda zone:True)
    monkeypatch.setattr(voice,"active",lambda:"twilio")
    from types import SimpleNamespace
    monkeypatch.setattr(c.compliance,"gate",lambda *a,**kw:SimpleNamespace(allowed=True))
    observed=[]
    def send(phone,lead_id,reservation_id=None):
        assert reservation_id and h.reservation_id==__import__('uuid').UUID(reservation_id)
        observed.append(phone)
        return None,"timeout"
    monkeypatch.setattr(voice,"place_auto_call",send)
    assert c.dispatch(db,lead)==(None,"timeout")
    assert len(observed)==1
    assert c.dispatch(db,lead)[0] is None and len(observed)==1
    assert db.get(CallReservation,h.reservation_id).status=="uncertain"

def test_capacity_mode_blocks_unreserved_legacy_dispatch(monkeypatch):
    from app.integrations import voice
    monkeypatch.setattr(c.settings,"auto_dial_capacity_enabled",True)
    monkeypatch.setattr(voice,"_mod",lambda:pytest.fail("legacy carrier invoked"))
    assert voice.place_auto_call("+16175550101",str(uuid4())).outcome=="not_attempted"
    assert voice.place_bridge_call("+16175550101",str(uuid4())).outcome=="not_attempted"


def test_recipient_timezone_window():
    assert c.recipient_in_window("America/New_York",datetime(2026,11,12,15,tzinfo=timezone.utc))
    assert not c.recipient_in_window("America/New_York",datetime(2026,11,12,3,tzinfo=timezone.utc))
    assert not c.recipient_in_window("invalid/zone")


def test_duplicate_guard_does_not_strand_new_handler(monkeypatch):
    from app.integrations import voice
    monkeypatch.setattr(c.settings,"auto_dial_capacity_enabled",True)
    monkeypatch.setattr(voice,"is_configured",lambda:True)
    monkeypatch.setattr(voice,"active",lambda:"twilio")
    monkeypatch.setattr(voice.outbound_guard,"voice_preflight",lambda:None)
    monkeypatch.setattr(voice.outbound_guard,"invoke",lambda *a,**kw: c.outbound_guard.held("already accepted","fixture",code="accepted"))
    monkeypatch.setattr(voice,"_mod",lambda:pytest.fail("must not invoke provider"))
    result=voice.place_auto_call("+16175550101",str(uuid4()),reservation_id=str(uuid4()))
    assert result.outcome=="not_attempted"

def test_postgres_concurrent_workers():
    """Real two-thread contention; hosted CI runs this, offline runs skip."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import text, select, func
    from app.database import engine, Base
    if engine.url.host not in {"localhost", "127.0.0.1"}:
        pytest.skip("Concurrency fixture requires local test PostgreSQL")
    try:
        with engine.connect() as conn: conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Local test PostgreSQL unavailable")
    schema="capacity_test_"+uuid4().hex
    with engine.begin() as conn: conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated=engine.execution_options(schema_translate_map={None:schema})
    try:
        tables=[m.__table__ for m in (Lead,DoNotContact,CallHandler,CallPermit,CallReservation,CallLeadHold)]
        Base.metadata.create_all(isolated,tables=tables)
        with Session(isolated) as db:
            lead,h=setup(db); lead_id=lead.id
        barrier=Barrier(2)
        def claim():
            with Session(isolated) as db:
                lead=db.get(Lead,lead_id)
                barrier.wait(timeout=10)
                row=c.reserve(db,lead)
                return str(row.id) if row else None
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(claim) for _ in range(2)]
            results=[f.result(timeout=15) for f in futures]
        assert sum(r is not None for r in results)==1
        with Session(isolated) as db:
            assert db.scalar(select(func.count()).select_from(CallReservation))==1
            assert db.scalar(select(func.count()).select_from(CallLeadHold))==1
    finally:
        with engine.begin() as conn: conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
