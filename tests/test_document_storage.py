from unittest.mock import Mock
import httpx
import pytest
from fastapi import HTTPException
from app import storage


@pytest.fixture
def production_storage(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("S3_BUCKET", "private-test")
    monkeypatch.setenv("DOCUMENT_SCANNER_URL", "https://scanner.example/scan")
    monkeypatch.setenv("DOCUMENT_SCANNER_TOKEN", "test-secret")
    client = Mock()
    monkeypatch.setattr(storage, "s3_client", lambda: client)
    return client


@pytest.mark.parametrize("verdict", [False, "true", None])
def test_unsafe_scan_never_reaches_storage(production_storage, monkeypatch, verdict):
    response = Mock(status_code=200)
    response.json.return_value = {"clean": verdict}
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: response)
    with pytest.raises(HTTPException) as error:
        storage.save_document("key.bin", b"test")
    assert error.value.status_code == 422
    production_storage.put_object.assert_not_called()


def test_scanner_outage_fails_closed(production_storage, monkeypatch):
    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("scanner offline")
    monkeypatch.setattr(httpx.Client, "post", unavailable)
    with pytest.raises(HTTPException) as error:
        storage.save_document("key.bin", b"test")
    assert error.value.status_code == 503
    production_storage.put_object.assert_not_called()


def test_clean_document_stored_privately_and_encrypted(production_storage, monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"clean": True}
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: response)
    storage.save_document("key.bin", b"test")
    production_storage.put_object.assert_called_once_with(
        Bucket="private-test", Key="key.bin", Body=b"test",
        ContentType="application/octet-stream", ServerSideEncryption="AES256")


def test_document_invalid_entity_rejected(auth):
    response = auth.post("/api/v1/documents", data={"entity_type": "party", "entity_id": "missing", "business_unit_code": "REAL_ESTATE"},
                         files={"file": ("a.pdf", b"%PDF-test", "application/pdf")})
    assert response.status_code == 404


def test_document_routes_require_session(client):
    assert client.get("/api/v1/documents").status_code == 401
    assert client.get("/api/v1/documents/missing/download").status_code == 401
