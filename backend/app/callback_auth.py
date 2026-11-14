"""Provider authentication for public telephony callbacks; never sends actions."""
import os
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from plivo.utils import validate_v3_signature
from twilio.request_validator import RequestValidator

from .config import settings
from .database import get_db
from .models import Setting
from .runtime_config import FIELDS


def reject_unverified_mutation_callback():
    """No signature protocol is configured for these alternate mutation paths."""
    if settings.secure_runtime:
        raise HTTPException(503, "This callback requires an authenticated provider integration")


def _credential(db, field):
    # Match Setup's env-over-DB precedence without mutating shared settings or
    # silently accepting stale credentials when the config store cannot be read.
    if os.environ.get(field.upper()):
        return os.environ[field.upper()].strip()
    if field in FIELDS:
        try:
            row = db.get(Setting, "cfg:" + field)
        except Exception:
            raise HTTPException(503, "Callback verification configuration unavailable") from None
        if row is not None:
            return (row.value or "").strip()
    return (getattr(settings, field, "") or "").strip()


def _callback_url(request):
    base = (settings.public_base_url or "").strip().rstrip("/")
    parts = urlsplit(base)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path):
        raise HTTPException(503, "Canonical HTTPS callback URL is not configured")
    # Never trust Host or forwarded headers to choose the signature origin.
    path = request.scope.get("raw_path", request.url.path.encode()).decode("ascii")
    query = request.scope.get("query_string", b"").decode("ascii")
    return base + path + ("?" + query if query else "")


async def _params(request):
    if request.method == "GET":
        return {}
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Callback requires URL-encoded form data")
    form = await request.form()
    if len(form.multi_items()) != len(form):
        raise HTTPException(400, "Duplicate callback parameters are not supported")
    return dict(form)


async def require_twilio_callback(request: Request, db=Depends(get_db)):
    if not settings.secure_runtime:
        return  # preserve local fixtures; production always verifies
    return await require_verified_twilio_callback(request, db)


async def require_verified_twilio_callback(request: Request, db=Depends(get_db)):
    """Always verify, including development; used by opt-in inbound assistant."""
    params = await _params(request)
    account = _credential(db, "twilio_account_sid")
    token = _credential(db, "twilio_auth_token")
    if not account or not token:
        raise HTTPException(503, "Twilio callback verification is not configured")
    supplied_account = params.get("AccountSid") if request.method == "POST" else request.query_params.get("AccountSid")
    # Shared compatibility routes also receive SignalWire callbacks. Its API token
    # is NOT its signing key. Never infer provider from today's sending preference.
    if supplied_account != account:
        raise HTTPException(403, "Callback account is not verified")
    signature = request.headers.get("x-twilio-signature", "")
    try:
        valid = bool(signature) and RequestValidator(token).validate(_callback_url(request), params, signature)
    except (ValueError, TypeError, UnicodeError):
        valid = False
    if not valid:
        raise HTTPException(403, "Invalid callback signature")


async def require_plivo_callback(request: Request, db=Depends(get_db)):
    if not settings.secure_runtime:
        return
    params = await _params(request)
    token = _credential(db, "plivo_auth_token")
    if not token:
        raise HTTPException(503, "Plivo callback verification is not configured")
    signature = request.headers.get("x-plivo-signature-v3", "")
    nonce = request.headers.get("x-plivo-signature-v3-nonce", "")
    if not signature or not nonce:
        raise HTTPException(403, "Plivo V3 callback signature required")
    url = _callback_url(request)
    try:
        valid = validate_v3_signature(request.method, url, nonce, token, signature, params)
    except Exception:
        valid = False
    if not valid:
        raise HTTPException(403, "Invalid callback signature")
