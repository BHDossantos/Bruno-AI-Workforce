"""Outbound sending provider selector.

Picks the configured dedicated cold-email engine (Instantly or Smartlead) to hand
leads off to. When neither is configured, the app falls back to direct Gmail SMTP.
Keeping this behind one tiny interface means dispatch code doesn't care which
provider is connected — and adding another later is a one-line change.
"""
from __future__ import annotations

from . import instantly, smartlead

_PROVIDERS = [("instantly", instantly), ("smartlead", smartlead)]


def active():
    """Return (name, module) of the first configured provider, or (None, None)."""
    for name, mod in _PROVIDERS:
        if mod.is_configured():
            return name, mod
    return None, None


def is_configured() -> bool:
    return active()[1] is not None


def name() -> str | None:
    return active()[0]


def add_lead(**kwargs) -> bool:
    _, mod = active()
    return mod.add_lead(**kwargs) if mod else False
