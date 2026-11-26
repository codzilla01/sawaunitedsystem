"""Private document storage. Production requires S3 and a trusted scanner.

Scanner protocol: POST raw bytes with Bearer authentication; only an exact
JSON verdict {"clean": true} with HTTP 200 is accepted. Never send documents
 to a public scanning service without an approved data processing agreement.
"""
import os
from pathlib import Path
import httpx
from fastapi import HTTPException
from .production import is_production


def s3_client():
    import boto3
    from botocore.config import Config
    return boto3.client("s3", region_name=os.environ["S3_REGION"],
                        endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
                        config=Config(connect_timeout=5, read_timeout=15, retries={"max_attempts": 2}))


def scan_document(content: bytes):
    try:
        with httpx.Client(timeout=25, follow_redirects=False) as client:
            response = client.post(os.environ["DOCUMENT_SCANNER_URL"], content=content,
                                   headers={"Authorization": "Bearer " + os.environ["DOCUMENT_SCANNER_TOKEN"],
                                            "Content-Type": "application/octet-stream"})
        if response.status_code != 200 or response.json().get("clean") is not True:
            raise HTTPException(422, "تعذر اعتماد سلامة المستند")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "خدمة فحص المستندات غير متاحة") from None


def save_document(key: str, content: bytes):
    if is_production():
        scan_document(content)
        try:
            s3_client().put_object(Bucket=os.environ["S3_BUCKET"], Key=key, Body=content,
                                   ContentType="application/octet-stream", ServerSideEncryption="AES256")
        except Exception:
            raise HTTPException(503, "تخزين المستندات غير متاح") from None
    else:
        root = Path(os.getenv("UPLOAD_ROOT", "./private_uploads"))
        root.mkdir(parents=True, exist_ok=True)
        (root / key).write_bytes(content)


def delete_document(key: str):
    if is_production():
        s3_client().delete_object(Bucket=os.environ["S3_BUCKET"], Key=key)
    else:
        (Path(os.getenv("UPLOAD_ROOT", "./private_uploads")) / key).unlink(missing_ok=True)


def load_document(key: str) -> bytes:
    if is_production():
        try:
            result = s3_client().get_object(Bucket=os.environ["S3_BUCKET"], Key=key)
            try:
                return result["Body"].read()
            finally:
                result["Body"].close()
        except Exception:
            raise HTTPException(503, "تعذر تحميل المستند") from None
    path = Path(os.getenv("UPLOAD_ROOT", "./private_uploads")) / key
    if not path.is_file():
        raise HTTPException(404, "ملف المستند غير متاح")
    return path.read_bytes()
