"""Logging setup: level, text/JSON format and tracking-code masking (spec §9.16, §9.27)."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import TextIO

from app.services.log_masking import mask_tracking_codes

# Uvicorn installs its own non-propagating handlers; route them through ours instead.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")
_HANDLER_NAME = "benchtrack"


class MaskTrackingCodesFilter(logging.Filter):
    """Rewrites every record so tracking codes never reach a log sink."""

    def filter(self, record: logging.LogRecord) -> bool:
        masked = mask_tracking_codes(record.getMessage())
        record.msg, record.args = masked, None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exc_info"] = mask_tracking_codes(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str, fmt: str, stream: TextIO | None = None) -> logging.Handler:
    """Install a single masked handler on the root logger. Safe to call repeatedly."""
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.set_name(_HANDLER_NAME)
    handler.addFilter(MaskTrackingCodesFilter())
    handler.setFormatter(
        JsonFormatter()
        if fmt == "json"
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )

    root = logging.getLogger()
    for existing in [h for h in root.handlers if h.get_name() == _HANDLER_NAME]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    return handler
