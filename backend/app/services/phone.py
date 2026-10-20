"""Phone normalization and validation (spec §9.1)."""

import re

_SEPARATORS_RE = re.compile(r"[\s\-()]")
_PHONE_RE = re.compile(r"^\+?[0-9]{8,15}$")


class InvalidPhoneError(ValueError):
    pass


def normalize_phone(raw: str) -> str:
    """Remove spaces, dashes and parentheses, then require `^\\+?\\d{8,15}$` (ASCII digits)."""
    phone = _SEPARATORS_RE.sub("", raw)
    if not _PHONE_RE.fullmatch(phone):
        raise InvalidPhoneError("Phone must contain 8 to 15 digits, optionally starting with +.")
    return phone
