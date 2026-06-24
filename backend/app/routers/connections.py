"""Connect-any-account platform.

Browse the provider catalog, connect any app / social / ad / commerce account
(credentials encrypted at rest), and get the automated marketing & sales funnel
the platform will run for each one.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import funnel
from ..database import get_db
from ..integrations import registry
from ..models import Connection
from ..schemas import ConnectionCreate, ConnectionOut, ConnectionUpdate
from ..security import decrypt_secret, encrypt_secret, require_role

router = APIRouter(prefix="/connections", tags=["connections"])


# ── Catalog ──────────────────────────────────────────────────────────────────
@router.get("/providers")
def providers(_=Depends(require_role("admin", "operator", "viewer"))):
    """The catalog of connectable accounts (no secrets)."""
    return registry.list_providers()


# ── Connections CRUD ─────────────────────────────────────────────────────────
@router.get("", response_model=list[ConnectionOut])
def list_connections(db: Session = Depends(get_db),
                     _=Depends(require_role("admin", "operator", "viewer"))):
    return db.query(Connection).order_by(Connection.created_at.desc()).all()


@router.post("", response_model=ConnectionOut)
def create_connection(body: ConnectionCreate, db: Session = Depends(get_db),
                      _=Depends(require_role("admin", "operator"))):
    prov = registry.get_provider(body.provider)
    if not prov:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{body.provider}'")

    missing = [f for f in registry.required_fields(body.provider)
               if not body.credentials.get(f)]
    if missing:
        raise HTTPException(status_code=400,
                            detail=f"Missing required field(s): {', '.join(missing)}")

    creds_enc = encrypt_secret(json.dumps(body.credentials)) if body.credentials else None
    conn = Connection(
        provider=body.provider,
        display_name=body.display_name or prov["name"],
        account_ref=body.account_ref or body.credentials.get("email_address")
        or body.credentials.get("page_id") or body.credentials.get("ig_user_id"),
        credentials_enc=creds_enc,
        goal=body.goal or (prov.get("goals", ["leads"])[0]),
        settings=body.settings,
        status="connected",
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


@router.patch("/{conn_id}", response_model=ConnectionOut)
def update_connection(conn_id: str, body: ConnectionUpdate, db: Session = Depends(get_db),
                      _=Depends(require_role("admin", "operator"))):
    conn = db.query(Connection).filter(Connection.id == conn_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    if body.display_name is not None:
        conn.display_name = body.display_name
    if body.goal is not None:
        conn.goal = body.goal
    if body.funnel_enabled is not None:
        conn.funnel_enabled = body.funnel_enabled
    if body.settings is not None:
        conn.settings = body.settings
    if body.credentials:
        existing = {}
        if conn.credentials_enc:
            try:
                existing = json.loads(decrypt_secret(conn.credentials_enc))
            except Exception:
                existing = {}
        existing.update(body.credentials)
        conn.credentials_enc = encrypt_secret(json.dumps(existing))
    db.commit()
    db.refresh(conn)
    return conn


@router.delete("/{conn_id}")
def delete_connection(conn_id: str, db: Session = Depends(get_db),
                      _=Depends(require_role("admin", "operator"))):
    conn = db.query(Connection).filter(Connection.id == conn_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    db.delete(conn)
    db.commit()
    return {"deleted": conn_id}


# ── Funnel plans ─────────────────────────────────────────────────────────────
@router.get("/funnel/preview/{provider_key}")
def preview_funnel(provider_key: str, goal: str | None = None,
                   _=Depends(require_role("admin", "operator", "viewer"))):
    """Show the funnel a provider WOULD run, before connecting it."""
    plan = funnel.build_plan(provider_key, goal)
    if plan.get("unsupported"):
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider_key}'")
    return plan


@router.get("/{conn_id}/funnel")
def connection_funnel(conn_id: str, db: Session = Depends(get_db),
                      _=Depends(require_role("admin", "operator", "viewer"))):
    conn = db.query(Connection).filter(Connection.id == conn_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return funnel.build_plan(conn.provider, conn.goal)


@router.get("/overview")
def funnel_overview(db: Session = Depends(get_db),
                    _=Depends(require_role("admin", "operator", "viewer"))):
    """Aggregate funnel coverage across all connected accounts + gaps to fill."""
    conns = db.query(Connection).filter(Connection.funnel_enabled.is_(True)).all()
    return funnel.overview(conns)
