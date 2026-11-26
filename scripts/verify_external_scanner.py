"""Run only against an approved staging scanner; never uploads to S3.

The EICAR file is a harmless antivirus test signature, not live malware.
Set DOCUMENT_SCANNER_URL and DOCUMENT_SCANNER_TOKEN in the shell environment.
"""
import json
import os
import sys
from urllib.parse import urlsplit

import httpx


EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def post(client: httpx.Client, url: str, token: str, payload: bytes) -> tuple[int, dict]:
    response = client.post(url, content=payload, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
    })
    try:
        data = response.json()
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return response.status_code, data


def main() -> int:
    url = os.getenv("DOCUMENT_SCANNER_URL", "")
    token = os.getenv("DOCUMENT_SCANNER_TOKEN", "")
    parsed = urlsplit(url)
    if (not url or parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or not token):
        print("Set an HTTPS scanner URL without credentials/query/fragment and a token through a secure staging environment.", file=sys.stderr)
        return 2

    try:
        with httpx.Client(timeout=35, follow_redirects=False) as client:
            clean_status, clean_result = post(client, url, token, b"SAWA staging scanner benign test file")
            if clean_status != 200 or clean_result.get("clean") is not True:
                print("Scanner failed the benign-file test; no document was stored.", file=sys.stderr)
                return 1
            eicar_status, eicar_result = post(client, url, token, EICAR)
            if eicar_status != 200 or eicar_result.get("clean") is not False:
                print("Scanner did not return an explicit infected verdict for EICAR.", file=sys.stderr)
                return 1
    except httpx.HTTPError as exc:
        print(f"Scanner request failed ({type(exc).__name__}); test failed closed.", file=sys.stderr)
        return 1

    print("Scanner staging verification passed: benign accepted; EICAR rejected; no S3 writes performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
