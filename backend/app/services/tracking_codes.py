"""Tracking codes: generation, normalization and collision retry (spec §9.12, §9.13)."""

import re
import secrets
from collections.abc import Callable

PREFIX = "BT-"
ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"  # no 0, O, 1, I, L, U
CODE_LENGTH = 5
MAX_ATTEMPTS = 5

_CODE_RE = re.compile(rf"^{re.escape(PREFIX)}[{ALPHABET}]{{{CODE_LENGTH}}}$")


class TrackingCodeCollision(Exception):
    """Raised by a `try_create` callback when the code is already taken."""


class TrackingCodeGenerationError(Exception):
    """No unique tracking code could be generated within MAX_ATTEMPTS."""


def generate_tracking_code(choice: Callable[[str], str] = secrets.choice) -> str:
    return PREFIX + "".join(choice(ALPHABET) for _ in range(CODE_LENGTH))


def is_valid_tracking_code(code: str) -> bool:
    """True if `code` is in canonical form (`BT-` + 5 alphabet chars, uppercase)."""
    return _CODE_RE.fullmatch(code) is not None


def normalize_tracking_code(raw: str) -> str | None:
    """Turn user input into a canonical code, or None if it cannot be one.

    Case-insensitive, trims surrounding whitespace, `BT-` prefix optional.
    """
    candidate = raw.strip().upper()
    if not candidate.startswith(PREFIX):
        candidate = PREFIX + candidate
    return candidate if is_valid_tracking_code(candidate) else None


def create_with_unique_code[T](
    try_create: Callable[[str], T],
    *,
    generate: Callable[[], str] = generate_tracking_code,
    max_attempts: int = MAX_ATTEMPTS,
) -> T:
    """Call `try_create(code)` with fresh codes until it succeeds.

    `try_create` raises TrackingCodeCollision when the code is taken (e.g. on a
    unique-constraint violation). After `max_attempts` collisions this raises
    TrackingCodeGenerationError. Other exceptions propagate immediately.
    """
    for _ in range(max_attempts):
        try:
            return try_create(generate())
        except TrackingCodeCollision:
            continue
    raise TrackingCodeGenerationError(
        f"Could not generate a unique tracking code after {max_attempts} attempts."
    )
