"""Minimal private ClamAV HTTP adapter for the application's scanner protocol.

Expose this service only through an HTTPS reverse proxy. Port 3310 must remain
on the private Docker network and the bearer token must match the app setting.
"""
from __future__ import annotations

import hmac
import json
import os
import socket
import struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


MAX_SCAN_BYTES = 15 * 1024 * 1024
CHUNK_BYTES = 64 * 1024


def _clamd_exchange(payload: bytes | None, command: bytes) -> bytes:
    host = os.getenv("CLAMD_HOST", "clamav")
    port = int(os.getenv("CLAMD_PORT", "3310"))
    timeout = float(os.getenv("CLAMD_TIMEOUT_SECONDS", "30"))
    chunks = [command]
    if payload is not None:
        for offset in range(0, len(payload), CHUNK_BYTES):
            chunk = payload[offset:offset + CHUNK_BYTES]
            chunks.extend((struct.pack(">I", len(chunk)), chunk))
        chunks.append(b"\x00\x00\x00\x00")

    with socket.create_connection((host, port), timeout=timeout) as client:
        client.settimeout(timeout)
        for chunk in chunks:
            client.sendall(chunk)
        response = bytearray()
        while not response.endswith(b"\x00"):
            part = client.recv(4096)
            if not part:
                raise RuntimeError("ClamAV closed the scanner connection")
            response.extend(part)
            if len(response) > 4096:
                raise RuntimeError("Unexpectedly large ClamAV response")
    return bytes(response[:-1])


def scan_bytes(payload: bytes) -> dict[str, bool]:
    result = _clamd_exchange(payload, b"zINSTREAM\x00").decode("utf-8", "replace")
    if result.endswith(": OK"):
        return {"clean": True}
    if result.endswith(" FOUND"):
        # Do not disclose malware signature names or file data to the caller.
        return {"clean": False}
    raise RuntimeError("ClamAV returned an incomplete or error verdict")


def clamd_ready() -> bool:
    try:
        return _clamd_exchange(None, b"zPING\x00") == b"PONG"
    except Exception:
        return False


class ScannerHandler(BaseHTTPRequestHandler):
    server_version = "SawaScanner"
    sys_version = ""

    def log_message(self, format, *args):
        # Avoid logging file names, request headers, tokens, or payload metadata.
        return

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            return self._send_json(200, {"status": "ok"})
        if self.path == "/ready":
            if clamd_ready():
                return self._send_json(200, {"status": "ready"})
            return self._send_json(503, {"status": "unavailable"})
        return self._send_json(404, {"detail": "Not found"})

    def do_POST(self):
        if self.path != "/scan":
            return self._send_json(404, {"detail": "Not found"})
        expected = os.getenv("SCANNER_BEARER_TOKEN", "")
        supplied = self.headers.get("Authorization", "")
        if not expected or not hmac.compare_digest(supplied, "Bearer " + expected):
            return self._send_json(401, {"detail": "Unauthorized"})
        if self.headers.get("Transfer-Encoding"):
            return self._send_json(411, {"detail": "Content-Length is required"})
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._send_json(411, {"detail": "Content-Length is required"})
        if content_length < 1:
            return self._send_json(422, {"detail": "Empty payload"})
        if content_length > MAX_SCAN_BYTES:
            return self._send_json(413, {"detail": "Payload exceeds scanner limit"})
        payload = self.rfile.read(content_length)
        if len(payload) != content_length:
            return self._send_json(400, {"detail": "Incomplete request body"})
        try:
            verdict = scan_bytes(payload)
        except Exception:
            # Fail closed. Never claim clean on a ClamAV timeout or protocol error.
            return self._send_json(503, {"detail": "Scanner unavailable"})
        return self._send_json(200, verdict)


def main() -> None:
    port = int(os.getenv("SCANNER_PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), ScannerHandler)
    server.daemon_threads = True
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
