"""Readiness smoke test for an already deployed HTTPS staging environment."""
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/check_deployment.py https://staging.example.com", file=sys.stderr)
        return 2
    base = sys.argv[1].rstrip("/")
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        print("Staging URL must be an HTTPS origin without credentials or a path.", file=sys.stderr)
        return 2

    for path in ("/health", "/ready"):
        try:
            request = Request(base + path, headers={"Accept": "application/json", "User-Agent": "sawa-staging-smoke/1"})
            with urlopen(request, timeout=12) as response:
                payload = json.loads(response.read(64 * 1024).decode("utf-8"))
                if not isinstance(payload, dict) or response.status != 200 or payload.get("status") not in {"ok", "ready"}:
                    raise RuntimeError(f"unexpected status payload at {path}")
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as exc:
            print(f"Staging check failed at {path}: {type(exc).__name__}", file=sys.stderr)
            return 1
    print("Staging health and database-readiness checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
