"""Mask tracking codes before they reach logs (spec §9.16)."""

import re

MASK = "BT-*****"

# Anything in a tracking path segment, valid or not (customers may omit the prefix).
_TRACK_PATH_RE = re.compile(r"(/track/)[^/?#\s\"']+")
# Prefixed codes anywhere else (search queries, messages, JSON).
_CODE_RE = re.compile(r"\bBT-[A-Z0-9]{5}\b", re.IGNORECASE)


def mask_tracking_codes(text: str) -> str:
    text = _TRACK_PATH_RE.sub(rf"\g<1>{MASK}", text)
    return _CODE_RE.sub(MASK, text)
