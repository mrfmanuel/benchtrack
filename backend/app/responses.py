"""Response classes shared by routes and error handlers."""

from fastapi.responses import JSONResponse


class UTF8JSONResponse(JSONResponse):
    """JSON with an explicit charset.

    JSON is UTF-8 by definition, but clients such as Windows PowerShell 5.1 fall back to
    a legacy code page without `charset=utf-8` and garble accented names.
    """

    media_type = "application/json; charset=utf-8"
