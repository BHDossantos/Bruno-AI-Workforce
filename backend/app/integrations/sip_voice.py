"""Voice via our OWN self-hosted SIP softswitch (FreeSWITCH + a BYOC trunk).

The "build our own" voice provider. Instead of paying a CPaaS to place calls over
their HTTP API, we run FreeSWITCH ourselves and bring our own carrier — a plain SIP
trunk from any wholesale provider (Bandwidth, Telnyx, a wholesale DID vendor, …).
Full control of the dialplan, cheaper per minute, no per-provider lock-in.

Same interface as twilio_voice / plivo_voice / vonage_voice
(``is_configured`` / ``place_auto_call`` / ``place_bridge_call`` /
``record_voicemail_call``) so the dispatcher (integrations/voice.py) routes to it
when ``voice_provider == "sip"``.

How it works:
  • Originate: we open FreeSWITCH's Event Socket (ESL) and issue a non-blocking
    ``bgapi originate`` through the configured sofia gateway (the SIP trunk). No
    new dependency — a tiny synchronous ESL client lives in this module.
  • Call control: FreeSWITCH fetches instructions from our backend as **HTTAPI**
    (an XML dialog document), served from the /calls/sip/* routes — the same
    fetch-instructions-over-HTTP shape as Twilio's TwiML or Vonage's NCCO.

The FreeSWITCH side (Docker image, sofia gateway, HTTAPI + ESL config) lives in
deploy/softswitch/. See that README for the trunk + server setup.

HONEST LIMIT: call attestation / caller-reputation (STIR-SHAKEN A/B/C) is decided
by the SIP-trunk carrier and the destination carrier — NOT by our switch. A brand
new trunk number still has to be registered (freecallerregistry.com) and warmed,
or it hits the same voicemail wall as any other new number. The softswitch gives
us control and lower cost; it is not, by itself, a fix for a cold number.

No-ops cleanly when unconfigured. Transfer-to-cell honors
``auto_dial_transfer_enabled`` (default off → leave the recorded voicemail).
"""
from __future__ import annotations

import logging
import re
import socket
from urllib.parse import urlencode
from xml.sax.saxutils import escape as _xesc

from ..config import settings

log = logging.getLogger("bruno.sip_voice")

_CONSENT = ("This call is with a licensed insurance producer and may be "
            "recorded for quality and training purposes.")


def _num(phone: str | None) -> str:
    """E.164 digits WITHOUT the '+': '+16039308272' → '16039308272'. The sofia
    gateway config decides whether to prepend '+'; most wholesale trunks take the
    11-digit form. Left 11-digit here for a US/CA number."""
    d = re.sub(r"\D", "", phone or "")
    if len(d) == 10:
        return "1" + d
    return d


def _gateway() -> str:
    return (settings.sip_gateway or "").strip()


def _from_number() -> str:
    return _num(settings.sip_voice_number or settings.sip_from_number or "")


def _transfer_number() -> str:
    return _num(settings.producer_cell or settings.producer_callback)


def _base_url() -> str:
    return (settings.public_base_url or "").rstrip("/")


def is_configured() -> bool:
    """Our softswitch is usable when we know the ESL host, the trunk gateway name,
    a caller-ID number, your callback number, and the public URL FreeSWITCH calls
    back for HTTAPI instructions."""
    return bool(settings.sip_esl_host and _gateway() and _from_number()
                and settings.producer_callback and _base_url())


def voicemail_configured() -> bool:
    return bool(settings.producer_voicemail_url)


# ── Minimal FreeSWITCH Event Socket (ESL) client — no third-party dependency ──
def _read_block(sock: socket.socket) -> dict:
    """Read one ESL event/reply: headers up to a blank line, then any body the
    Content-Length announces. Returns parsed headers plus '_body'."""
    buf = b""
    while b"\n\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    head, _, rest = buf.partition(b"\n\n")
    hdrs: dict[str, str] = {}
    for line in head.decode("utf-8", "replace").splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            hdrs[k.strip()] = v.strip()
    body = rest
    try:
        clen = int(hdrs.get("Content-Length", "0"))
    except ValueError:
        clen = 0
    while clen and len(body) < clen:
        chunk = sock.recv(4096)
        if not chunk:
            break
        body += chunk
    hdrs["_body"] = body.decode("utf-8", "replace")
    return hdrs


def _esl(command: str) -> tuple[str | None, str | None]:
    """Connect, authenticate, run one command. Returns (job/uuid, None) or (None, error)."""
    host = (settings.sip_esl_host or "127.0.0.1").strip()
    try:
        port = int(settings.sip_esl_port or 8021)
    except (TypeError, ValueError):
        port = 8021
    password = settings.sip_esl_password or "ClueCon"
    try:
        with socket.create_connection((host, port), timeout=8) as sock:
            sock.settimeout(8)
            _read_block(sock)                       # server: auth/request
            sock.sendall(f"auth {password}\n\n".encode())
            reply = _read_block(sock)
            if "+OK" not in (reply.get("Reply-Text", "") + reply.get("_body", "")):
                return None, "FreeSWITCH ESL auth failed — check sip_esl_password."
            sock.sendall(f"{command}\n\n".encode())
            reply = _read_block(sock)
            text = (reply.get("Reply-Text", "") or reply.get("_body", "")).strip()
            job = reply.get("Job-UUID")             # bgapi → async job id
            if job:
                return job, None
            if text.startswith("+OK"):
                parts = text.split()
                return (parts[-1] if len(parts) > 1 else "sip-call"), None
            return None, f"FreeSWITCH refused the call: {text[:160] or 'no reply'}"
    except OSError as exc:  # pragma: no cover - network guard
        return None, (f"Can't reach FreeSWITCH ESL at {host}:{port} — is the softswitch "
                      f"running and reachable? ({str(exc)[:120]})")


def _originate(to: str, answer_path: str, extra_vars: str = "") -> tuple[str | None, str | None]:
    gw = _gateway()
    base = _base_url()
    if not (gw and base and to):
        return None, "SIP softswitch not fully configured (gateway / base URL / number)."
    url = f"{base}{answer_path}"
    channel_vars = ("ignore_early_media=true,hangup_after_bridge=true,"
                    f"origination_caller_id_number={_from_number()}")
    if extra_vars:
        channel_vars += "," + extra_vars
    dial = f"{{{channel_vars}}}sofia/gateway/{gw}/{to}"
    cmd = f"bgapi originate {dial} &httapi({{url={url}}})"
    return _esl(cmd)


def place_auto_call(lead_phone: str, lead_id: str | None) -> tuple[str | None, str | None]:
    if not is_configured():
        return None, "Self-hosted SIP calling not connected — set the softswitch fields on Setup."
    to = _num(lead_phone)
    if not to:
        return None, "lead has no valid phone number"
    q = urlencode({"lead_id": lead_id}) if lead_id else ""
    return _originate(to, f"/calls/sip/amd{('?' + q) if q else ''}")


def place_bridge_call(lead_phone: str, lead_id: str | None) -> tuple[str | None, str | None]:
    if not is_configured():
        return None, "Self-hosted SIP calling not connected — set the softswitch fields on Setup."
    if not _num(lead_phone):
        return None, "lead has no valid phone number"
    q = urlencode({k: v for k, v in {"lead_phone": _num(lead_phone), "lead_id": lead_id}.items() if v})
    return _originate(_num(settings.producer_callback), f"/calls/sip/bridge?{q}")


def record_voicemail_call() -> tuple[str | None, str | None]:
    if not is_configured():
        return None, "Set up the self-hosted SIP softswitch + your callback number on Setup first."
    return _originate(_num(settings.producer_callback), "/calls/sip/record-vm")


# ── HTTAPI documents the /calls/sip/* webhooks return ─────────────────────────
def _httapi(work: str) -> str:
    return f'<document type="xml/freeswitch-httapi"><work>{work}</work></document>'


def _speak(text: str) -> str:
    # FreeSWITCH TTS via mod_flite (loaded in the deploy/softswitch image).
    return f'<execute application="speak" data="flite|slt|{_xesc(text)}"/>'


def _bridge_to(number: str) -> str:
    dest = f"{{origination_caller_id_number={_from_number()}}}sofia/gateway/{_gateway()}/{number}"
    return f'<execute application="bridge" data="{_xesc(dest)}"/>'


def _vm_fallback_text() -> str:
    return (f"Hi, this is {settings.producer_name} with Thrust Insurance. I'm following up on the "
            "insurance quote you requested. Please give me a call back whenever you have a moment. "
            "Thank you and talk soon.")


def _voicemail_work() -> str:
    vm = settings.producer_voicemail_url
    body = f'<playback file="{_xesc(vm)}"/>' if vm else _speak(_vm_fallback_text())
    return body + "<hangup/>"


def amd_work(lead_id: str | None) -> str:
    """Auto-dial answer. Transfer-on connects to the producer's cell; the default
    (transfer off) leaves the recorded voicemail drop — matching every other provider.
    Real per-call machine detection can be layered on later via mod_avmd."""
    if settings.auto_dial_transfer_enabled and _transfer_number():
        return (_speak("Please hold — connecting you with a licensed insurance producer. "
                       "This call may be recorded for quality.")
                + _bridge_to(_transfer_number()) + "<hangup/>")
    return _voicemail_work()


def bridge_work(lead_phone: str, lead_id: str | None) -> str:
    """After YOU answer a bridge call — consent notice, then dial the lead."""
    to = _num(lead_phone)
    if not to:
        return _speak("No lead number to dial. Goodbye.") + "<hangup/>"
    return _speak(_CONSENT) + _bridge_to(to) + "<hangup/>"


def record_vm_work() -> str:
    """Call the producer and record their voicemail drop. FreeSWITCH POSTs the audio
    to /calls/sip/vm-saved on completion."""
    base = _base_url()
    return (
        _speak("Record the voicemail you want left for leads after the tone. "
               "Press the pound key when you are done.")
        + f'<record name="vm-greeting.wav" limit="60" '
          f'action="{base}/calls/sip/vm-saved" beep-file="tone_stream://%(500,0,640)">'
          '<bind strip="#">~\\d+#</bind></record>'
        + "<hangup/>"
    )
