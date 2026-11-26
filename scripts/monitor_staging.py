"""Scheduled external probe for the staging URL, with optional webhook alert."""
import json
import os
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.parse import urlsplit


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def main() -> int:
    base_url = os.getenv("STAGING_BASE_URL", "")
    if not base_url:
        print("STAGING_BASE_URL is not configured in the staging environment.", file=sys.stderr)
        return 2
    result = subprocess.run(
        [sys.executable, "scripts/check_deployment.py", base_url],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        print(result.stdout.strip())
        return 0

    print(result.stderr.strip() or "Staging readiness check failed.", file=sys.stderr)
    webhook = os.getenv("ALERT_WEBHOOK_URL", "")
    if webhook:
        try:
            webhook_parts = urlsplit(webhook)
        except ValueError:
            webhook_parts = None
        if (webhook_parts is None or webhook_parts.scheme != "https" or not webhook_parts.hostname
                or webhook_parts.username or webhook_parts.password or webhook_parts.fragment):
            print("Alert webhook must be an HTTPS URL without credentials or a fragment; notification was not sent.", file=sys.stderr)
            return result.returncode or 1
        message = {"text": "SAWA UNITED staging health/readiness probe failed. Check the latest GitHub Actions run."}
        request = Request(webhook, data=json.dumps(message).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        try:
            with build_opener(_NoRedirect).open(request, timeout=10) as response:
                if not 200 <= response.status < 300:
                    print("Alert webhook returned a non-success status.", file=sys.stderr)
        except (HTTPError, URLError, TimeoutError):
            print("Alert webhook delivery failed; GitHub Actions will still report the failed probe.", file=sys.stderr)
    return result.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
