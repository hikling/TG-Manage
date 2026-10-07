"""Derive a country flag region from a Telegram user's phone number."""
from __future__ import annotations

import re

import phonenumbers


def country_code_from_phone(phone: str | None) -> str | None:
    """Return ISO 3166-1 alpha-2 only for a valid international number."""
    digits = re.sub(r"\D", "", phone or "")
    if not 7 <= len(digits) <= 15:
        return None
    try:
        number = phonenumbers.parse(f"+{digits}", None)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(number):
        return None
    region = phonenumbers.region_code_for_number(number)
    return region if region and re.fullmatch(r"[A-Z]{2}", region) else None
