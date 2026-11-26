"""Fail-closed production configuration and browser request protections."""
import os
from urllib.parse import urlsplit, parse_qs
from starlette.responses import JSONResponse


def is_production():
    return os.getenv("APP_ENV", "development").lower() == "production"


def validate_production():
    if not is_production():
        return
    secret = os.getenv("SECRET_KEY", "")
    if len(secret) < 48 or secret.startswith(("CHANGE_", "development-")):
        raise RuntimeError("Production requires a unique SECRET_KEY of at least 48 characters")
    if not os.getenv("DATABASE_URL", "").startswith("postgresql+psycopg://"):
        raise RuntimeError("Production requires PostgreSQL via psycopg")
    if os.getenv("COOKIE_SECURE", "").lower() != "true":
        raise RuntimeError("Production requires COOKIE_SECURE=true and HTTPS")
    origin = urlsplit(os.getenv("PUBLIC_ORIGIN", ""))
    if origin.scheme != "https" or not origin.hostname or origin.path or origin.query or origin.fragment or origin.username:
        raise RuntimeError("PUBLIC_ORIGIN must be an HTTPS origin without a path or credentials")

    from cryptography.fernet import Fernet
    mfa_key = os.getenv("MFA_ENCRYPTION_KEY", "")
    try:
        Fernet(mfa_key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise RuntimeError("Production requires a valid independent MFA_ENCRYPTION_KEY") from None

    required_storage = ("S3_BUCKET", "S3_REGION", "DOCUMENT_SCANNER_URL", "DOCUMENT_SCANNER_TOKEN")
    if any(not os.getenv(name) for name in required_storage):
        raise RuntimeError("Production requires private S3 storage and a trusted document scanner")
    endpoint = os.getenv("S3_ENDPOINT_URL")
    if endpoint:
        endpoint_parts = urlsplit(endpoint)
        if (endpoint_parts.scheme != "https" or not endpoint_parts.hostname
                or endpoint_parts.username or endpoint_parts.password
                or endpoint_parts.query or endpoint_parts.fragment):
            raise RuntimeError("S3 endpoint must be an HTTPS URL without credentials, query, or fragment")
    scanner = urlsplit(os.environ["DOCUMENT_SCANNER_URL"])
    if (scanner.scheme != "https" or not scanner.hostname or scanner.username or scanner.password
            or scanner.query or scanner.fragment):
        raise RuntimeError("Document scanner must be HTTPS without URL credentials, query, or fragment")

    if os.getenv("VERCEL"):
        query = parse_qs(urlsplit(os.environ["DATABASE_URL"]).query)
        if query.get("sslmode", [""])[0] not in {"require", "verify-ca", "verify-full"}:
            raise RuntimeError("Vercel database connections require TLS (sslmode=require or stronger)")
        required_aws_keys = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
        if any(not os.getenv(name) for name in required_aws_keys):
            raise RuntimeError("Vercel requires scoped AWS credentials for the private documents bucket")


async def protect_requests(request, call_next):
    production = is_production()
    if production and request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        # A custom header cannot be sent by a cross-origin HTML form. No CORS
        # middleware is enabled; cross-origin JS preflights are not authorized.
        origin = request.headers.get("origin")
        if (request.headers.get("x-sawa-request") != "1"
                or (origin and origin != os.getenv("PUBLIC_ORIGIN"))
                or request.headers.get("sec-fetch-site") == "cross-site"):
            return JSONResponse({"detail": "Cross-site request rejected"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY" if production else "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
        + ("frame-ancestors 'none'" if production else "frame-ancestors 'self'")
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response
