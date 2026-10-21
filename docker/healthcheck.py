"""Container health check: GET /api/health on the local port (no curl in the slim image).

Exits 0 when the API answers 200 (database reachable), 1 otherwise. Uses http.client with a
fixed host, so only the port comes from the environment.
"""

import http.client
import os
import sys

try:
    connection = http.client.HTTPConnection("127.0.0.1", int(os.environ.get("PORT", "8000")), timeout=4)
    connection.request("GET", "/api/health")
    status = connection.getresponse().status
except (OSError, ValueError, http.client.HTTPException) as exc:
    print(f"healthcheck failed: {exc}", file=sys.stderr)
    sys.exit(1)
sys.exit(0 if status == 200 else 1)
