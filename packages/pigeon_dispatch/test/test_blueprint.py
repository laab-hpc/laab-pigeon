# Copyright (c) 2026 Forschungszentrum Juelich GmbH, Juelich Supercomputing Centre
# Contributors:
# - Aravind Sankaran
# SPDX-License-Identifier: BSD-3-Clause

# tests/test_dispatch_blueprint.py
import json
from pathlib import Path

import pytest
from flask import Flask

# Adjust these imports to your actual module paths
from pigeon_dispatch.blueprint import create_dispatch_blueprint, HEADER_NAME, ENV_KEY
from pigeon_dispatch.backends.simple_file import SimpleFileDispatchBackend


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_KEY, "dispatch-secret")
    backend = SimpleFileDispatchBackend(base_dir=tmp_path)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(create_dispatch_blueprint(backend))
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def auth_headers():
    return {HEADER_NAME: "dispatch-secret"}


def test_unauthorized_without_header(client):
    r = client.post("/generate-request-id", json={"object_key": "123abc"})
    assert r.status_code == 401
    assert r.get_json()["error"] == "Unauthorized"


def test_unauthorized_wrong_header(client):
    r = client.post(
        "/generate-request-id",
        headers={HEADER_NAME: "wrong"},
        json={"object_key": "123abc"},
    )
    assert r.status_code == 401


def test_server_misconfigured_missing_env(tmp_path, monkeypatch):
    # no ENV_KEY set
    monkeypatch.delenv(ENV_KEY, raising=False)

    backend = SimpleFileDispatchBackend(base_dir=tmp_path)
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(create_dispatch_blueprint(backend))
    client = app.test_client()

    r = client.post("/generate-request-id", headers={HEADER_NAME: "dispatch-secret"}, json={"object_key": "123abc"})
    assert r.status_code == 500
    assert r.get_json()["error"] == "Server misconfigured"


def test_generate_request_id_invalid_json_body(client):
    r = client.post(
        "/generate-request-id",
        headers=auth_headers(),
        data="not-json",
        content_type="text/plain",
    )
    assert r.status_code == 500
    assert r.get_json()["error"] == "Internal error"


def test_generate_request_id_missing_object_key(client):
    r = client.post("/generate-request-id", headers=auth_headers(), json={})
    assert r.status_code == 500
    assert r.get_json()["error"] == "Internal error"


def test_generate_request_id_object_key_validation(client):
    # SimpleFileDispatchBackend requires object_key starts with "123"
    r = client.post("/generate-request-id", headers=auth_headers(), json={"object_key": "badkey"})
    assert r.status_code == 401
    assert r.get_json()["error"] == "Invalid object key badkey"


def test_happy_flow_filesystem_backend_writes_state_and_info(client, tmp_path):
    # 1) generate request id
    r = client.post("/generate-request-id", headers=auth_headers(), json={"object_key": "123_ok"})
    assert r.status_code == 200
    request_id = r.get_json()["request_id"]
    assert isinstance(request_id, str) and request_id

    # 2) register token
    r = client.post(
        "/register-token",
        headers=auth_headers(),
        json={"request_id": request_id, "issued_at": 10, "expires_at": 20},
    )
    assert r.status_code == 200
    assert r.get_json() == {"ok": True}

    # state.json should contain request_id now
    state = json.loads((tmp_path / "state.json").read_text())
    assert request_id in state
    assert state[request_id]["status"] == "registered"

    # 3) get dispatch info
    r = client.post("/get_dispatch_info", headers=auth_headers(), json={"request_id": request_id})
    assert r.status_code == 200
    j = r.get_json()
    assert j["type"] == "filesystem"
    assert j["file_path"].endswith(f"{request_id}.bin")

    # 4) notification: success but file does not exist yet -> backend marks file_missing
    r = client.post(
        "/notification",
        headers=auth_headers(),
        json={"request_id": request_id, "status": 1, "message": "success"},
    )
    assert r.status_code == 500

    state = json.loads((tmp_path / "state.json").read_text())
    assert state[request_id]["status"] == "file_missing"

    # create file then notify again -> success
    Path(tmp_path / f"{request_id}.bin").write_bytes(b"data")
    r = client.post(
        "/notification",
        headers=auth_headers(),
        json={"request_id": request_id, "status": 1, "message": "success"},
    )
    assert r.status_code == 200
    state = json.loads((tmp_path / "state.json").read_text())
    assert state[request_id]["status"] == "received"


def test_register_token_invalid_body(client):
    r = client.post("/register-token", headers=auth_headers(), data="x", content_type="text/plain")
    assert r.status_code == 400
    assert r.get_json()["error"] == "Invalid JSON body"

    r = client.post("/register-token", headers=auth_headers(), json={"request_id": "x"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "Invalid request_id/issued_at/expires_at"


def test_get_dispatch_info_unknown_request_id(client):
    # backend only knows request_ids after register-token
    r = client.post("/get_dispatch_info", headers=auth_headers(), json={"request_id": "does-not-exist"})
    assert r.status_code == 500
    assert r.get_json()["error"] == "Internal error"


def test_notification_invalid_body(client):
    r = client.post("/notification", headers=auth_headers(), data="x", content_type="text/plain")
    assert r.status_code == 400
    assert r.get_json()["error"] == "Invalid JSON body"

    r = client.post("/notification", headers=auth_headers(), json={"request_id": "x"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "Invalid request_id/status/message"
