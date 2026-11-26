"""TOTP MFA helpers with Fernet encryption for recoverable shared secrets."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken


MFA_REQUIRED_ROLES = frozenset({
    "super_admin", "group_manager", "business_manager", "contract_manager", "accountant"
})
MFA_ISSUER = "SAWA UNITED"
TOTP_PERIOD_SECONDS = 30
TOTP_DIGITS = 6


def is_mfa_required(role: str) -> bool:
    from .production import is_production
    return is_production() and role in MFA_REQUIRED_ROLES


def _fernet() -> Fernet:
    key = os.getenv("MFA_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError("MFA_ENCRYPTION_KEY is required to use MFA")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise RuntimeError("MFA_ENCRYPTION_KEY must be a valid Fernet key") from None


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        raise RuntimeError("Unable to decrypt the user's MFA secret; check the configured encryption key") from None


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, counter: int) -> str:
    padded = secret.upper() + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10 ** TOTP_DIGITS)).zfill(TOTP_DIGITS)


def current_counter(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // TOTP_PERIOD_SECONDS)


def verify_totp(secret: str, code: str | None, *, last_counter: int = -1,
                now: float | None = None, window: int = 1) -> int | None:
    if code is None:
        return None
    normalized = str(code).replace(" ", "").strip()
    if len(normalized) != TOTP_DIGITS or not normalized.isascii() or not normalized.isdigit():
        return None
    center = current_counter(now)
    for counter in range(center - window, center + window + 1):
        if counter <= last_counter:
            continue
        if hmac.compare_digest(totp_code(secret, counter), normalized):
            return counter
    return None


def provisioning_uri(email: str, secret: str) -> str:
    label = quote(f"{MFA_ISSUER}:{email}", safe="")
    issuer = quote(MFA_ISSUER, safe="")
    return (f"otpauth://totp/{label}?secret={secret}&issuer={issuer}"
            f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD_SECONDS}")
