# Copyright (c) 2026 Forschungszentrum Juelich GmbH, Juelich Supercomputing Centre
# Contributors:
# - Aravind Sankaran
# SPDX-License-Identifier: BSD-3-Clause

import io
import json
import time
from pathlib import Path
import types
import pytest

from pigeon_server.request_manager import RequestManager


class DummyResp:
    def __init__(self, status_code=200, json_data=None, text="OK"):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


@pytest.fixture
def rm():
    return RequestManager(
        dispatch_key="dispatch-secret",
        dispatch_url="http://dispatch.local",
        token_key="token-secret",
        token_age=600,
    )


def test_post_json_network_error(rm, monkeypatch):
    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        import requests
        raise requests.RequestException("boom")

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(RuntimeError, match=r"500, Failed to contact dispatch at http://dispatch\.local/x"):
        rm._post_json("/x", {"a": 1}, headers={"h": "v"})


def test_post_json_non_200(rm, monkeypatch):
    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        return DummyResp(status_code=500, json_data={"error": "nope"}, text="nope")

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(RuntimeError, match=r"500, Dispatch returned error for POST /x: nope"):
        rm._post_json("/x", {"a": 1}, headers={"h": "v"})


def test_generate_upload_token_happy_path(rm, monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        calls.append((url, json, headers))
        if url.endswith("/generate-request-id"):
            return DummyResp(200, {"request_id": 123})
        if url.endswith("/register-token"):
            return DummyResp(200, {"ok": True})
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("requests.post", fake_post)

    token = rm.generate_upload_token("objkey-1")
    assert isinstance(token, str) and token

    payload = rm._verify_token(token)
    assert payload["request_id"] == 123

    # Ensure headers were passed to dispatch for both calls
    assert any(u.endswith("/generate-request-id") and h == rm.dispatch_headers for u, _, h in calls)
    assert any(u.endswith("/register-token") and h == rm.dispatch_headers for u, _, h in calls)


def test_generate_upload_token_non_json(rm, monkeypatch):
    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        return DummyResp(200, json_data=ValueError("bad json"))

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(RuntimeError, match="non-JSON"):
        rm.generate_upload_token("objkey")


def test_generate_upload_token_missing_request_id(rm, monkeypatch):
    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        return DummyResp(200, {"no_request_id": 1})

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(RuntimeError, match="did not return request_id"):
        rm.generate_upload_token("objkey")


def test_process_upload_stream_invalid_token(rm):
    with pytest.raises(RuntimeError, match="Invalid token"):
        rm.process_upload_stream("not-a-token", io.BytesIO(b"hello"))


def test_process_upload_stream_filesystem_writes_file(rm, monkeypatch, tmp_path):
    dest = tmp_path / "uploads" / "file.bin"
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Generate a valid token for request_id=999
    token = rm._generate_token(999)

    calls = []

    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        calls.append((url, json, headers))
        if url.endswith("/get_dispatch_info"):
            return DummyResp(200, {"type": "filesystem", "file_path": str(dest)})
        if url.endswith("/notification"):
            return DummyResp(200, {"ok": True})
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("requests.post", fake_post)

    data = b"A" * (1024 * 10) + b"END"
    rm.process_upload_stream(token, io.BytesIO(data), content_length=len(data))

    assert dest.exists()
    assert dest.read_bytes() == data

    # Notification should have been attempted
    assert any(u.endswith("/notification") for u, _, _ in calls)


def test_process_upload_stream_filesystem_notification_failure_raises(rm, monkeypatch, tmp_path):
    dest = tmp_path / "file.bin"
    token = rm._generate_token(111)

    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        if url.endswith("/get_dispatch_info"):
            return DummyResp(200, {"type": "filesystem", "file_path": str(dest)})
        if url.endswith("/notification"):
            return DummyResp(500, json_data={"error": "down"}, text="down")
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(RuntimeError, match=r"500, Dispatch returned error for POST /notification: down"):
        rm.process_upload_stream(token, io.BytesIO(b"hi"))
    assert dest.read_bytes() == b"hi"


def test_process_upload_stream_unknown_type(rm, monkeypatch):
    token = rm._generate_token(222)

    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        if url.endswith("/get_dispatch_info"):
            return DummyResp(200, {"type": "wat"})
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(RuntimeError, match=r"500, Dispatch returned unknown process type for request_id 222: wat"):
        rm.process_upload_stream(token, io.BytesIO(b"x"))


def test_process_upload_stream_api_happy_path(rm, monkeypatch):
    token = rm._generate_token(333)

    seen = {"api_called": False, "dispatch_notification": False, "content_length": None, "bytes": b""}

    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        # dispatch calls (json=...)
        if json is not None:
            if url.endswith("/get_dispatch_info"):
                return DummyResp(200, {"type": "api", "api_endpoint": "http://sink.local/upload"})
            if url.endswith("/notification"):
                seen["dispatch_notification"] = True
                return DummyResp(200, {"ok": True})
            raise AssertionError(f"Unexpected dispatch URL {url}")

        # api endpoint call (data=stream)
        if url == "http://sink.local/upload":
            seen["api_called"] = True
            seen["content_length"] = headers.get("Content-Length")
            # read from stream to prove it is file-like streaming
            chunk = data.read()
            seen["bytes"] = chunk
            return DummyResp(200, text="ok")

        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("requests.post", fake_post)

    payload = b"streamed-bytes"
    rm.process_upload_stream(token, io.BytesIO(payload), content_length=len(payload))

    assert seen["api_called"] is True
    assert seen["bytes"] == payload
    assert seen["content_length"] == str(len(payload))
    assert seen["dispatch_notification"] is True


def test_process_upload_stream_api_rejected(rm, monkeypatch):
    token = rm._generate_token(444)

    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        if json is not None and url.endswith("/get_dispatch_info"):
            return DummyResp(200, {"type": "api", "api_endpoint": "http://sink.local/upload"})
        if url == "http://sink.local/upload":
            return DummyResp(403, text="no")
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(RuntimeError, match=r"403, API endpoint http://sink\.local/upload returned error: no"):
        rm.process_upload_stream(token, io.BytesIO(b"x"), content_length=1)
        
def test_process_upload_stream_expired_token():
    # token_age = 1 second
    rm = RequestManager(
        dispatch_key="dispatch-secret",
        dispatch_url="http://dispatch.local",
        token_key="token-secret",
        token_age=1,
    )

    token = rm._generate_token(42)

    # wait until token expires
    time.sleep(2)

    with pytest.raises(RuntimeError, match="Token has expired"):
        rm.process_upload_stream(token, io.BytesIO(b"data"))
