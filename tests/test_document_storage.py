from unittest.mock import Mock
import httpx
import pytest
from fastapi import HTTPException
from app import storage


EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


@pytest.fixture
def production_storage(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("S3_BUCKET", "private-test")
    monkeypatch.setenv("DOCUMENT_SCANNER_URL", "https://scanner.example/scan")
    monkeypatch.setenv("DOCUMENT_SCANNER_TOKEN", "test-secret")
    client = Mock()
    monkeypatch.setattr(storage, "s3_client", lambda: client)
    return client


@pytest.mark.parametrize(("verdict", "expected_status"), [(False, 422), ("true", 503), (None, 503), (0, 503)])
def test_unsafe_scan_never_reaches_storage(production_storage, monkeypatch, verdict, expected_status):
    response = Mock(status_code=200)
    response.json.return_value = {"clean": verdict}
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: response)
    with pytest.raises(HTTPException) as error:
        storage.save_document("key.bin", b"test")
    assert error.value.status_code == expected_status
    production_storage.put_object.assert_not_called()


def test_eicar_verdict_fails_closed_without_s3_write(production_storage, monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"clean": False}
    seen = {}

    def scan(_client, url, *, content, headers):
        seen.update(url=url, content=content, headers=headers)
        return response

    monkeypatch.setattr(httpx.Client, "post", scan)
    with pytest.raises(HTTPException) as error:
        storage.save_document("eicar-test.bin", EICAR)
    assert error.value.status_code == 422
    assert seen["content"] == EICAR
    production_storage.put_object.assert_not_called()


def test_scanner_outage_fails_closed(production_storage, monkeypatch):
    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("scanner offline")
    monkeypatch.setattr(httpx.Client, "post", unavailable)
    with pytest.raises(HTTPException) as error:
        storage.save_document("key.bin", b"test")
    assert error.value.status_code == 503
    production_storage.put_object.assert_not_called()


def test_scanner_http_unavailable_response_is_503(production_storage, monkeypatch):
    response = Mock(status_code=503)
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: response)
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
    response = auth.post('/api/v1/documents', data={"entity_type": "party", "entity_id": "missing", "business_unit_code": "REAL_ESTATE"},
                         files={"file": ("a.pdf", b"%PDF-test", "application/pdf")})
    assert response.status_code == 404


def test_document_routes_require_session(client):
    assert client.get('/api/v1/documents').status_code == 401
    assert client.get('/api/v1/documents/missing/download').status_code == 401
