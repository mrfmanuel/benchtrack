"""Container health check: GET /api/health on the local port (no curl in the slim image).

Exits 0 when the API answers 200 (database reachable), 1 otherwise.
"""

import os
import sys
import urllib.request

url = f"http://127.0.0.1:{os.environ.get('PORT', '8000')}/api/health"
try:
    with urllib.request.urlopen(url, timeout=4) as response:  # noqa: S310 (fixed local URL)
        sys.exit(0 if response.status == 200 else 1)
except Exception as exc:  # noqa: BLE001
    print(f"healthcheck failed: {exc}", file=sys.stderr)
    sys.exit(1)
