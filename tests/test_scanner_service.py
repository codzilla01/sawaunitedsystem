import pytest
from deploy.scanner import server


class FakeSocket:
    def __init__(self, response):
        self.response = response
        self.sent = []
        self.timeout = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def settimeout(self, value):
        self.timeout = value

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, size):
        result, self.response = self.response, b""
        return result


def test_clamd_protocol_returns_clean_verdict(monkeypatch):
    fake = FakeSocket(b"stream: OK\x00")
    monkeypatch.setattr(server.socket, "create_connection", lambda *args, **kwargs: fake)
    assert server.scan_bytes(b"harmless") == {"clean": True}
    assert fake.sent[0] == b"zINSTREAM\x00"
    assert fake.sent[-1] == b"\x00\x00\x00\x00"


def test_clamd_protocol_rejects_eicar_verdict(monkeypatch):
    fake = FakeSocket(b"stream: Eicar-Test-Signature FOUND\x00")
    monkeypatch.setattr(server.socket, "create_connection", lambda *args, **kwargs: fake)
    assert server.scan_bytes(b"eicar-test") == {"clean": False}


def test_clamd_errors_raise_instead_of_accepting(monkeypatch):
    fake = FakeSocket(b"stream: INSTREAM size limit exceeded. ERROR\x00")
    monkeypatch.setattr(server.socket, "create_connection", lambda *args, **kwargs: fake)
    with pytest.raises(RuntimeError):
        server.scan_bytes(b"payload")
