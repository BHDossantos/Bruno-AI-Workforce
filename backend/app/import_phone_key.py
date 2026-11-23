"""Exact phone keys for insurance CSV identity checks, not for outreach."""

import re


def import_phone_key(raw: str | None) -> str | None:
    """Accept common US formatting or an explicit international number.

    Never use a trailing substring, strip extensions, or assume a country
    for non-US local numbers. This is only a comparison key.
    """
    value = (raw or "").strip()
    if not re.fullmatch(r"\+?[0-9(). -]+", value):
        return None
    digits = re.sub(r"[^0-9]", "", value)
    if value.startswith("+"):
        if digits.startswith("1"):
            return digits if len(digits) == 11 else None
        return digits if 8 <= len(digits) <= 15 and not digits.startswith("0") else None
    if len(digits) == 10:
        return "1" + digits
    return digits if len(digits) == 11 and digits.startswith("1") else None
