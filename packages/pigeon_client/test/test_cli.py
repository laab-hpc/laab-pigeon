# Copyright (c) 2026 Forschungszentrum Juelich GmbH, Juelich Supercomputing Centre
# Contributors:
# - Aravind Sankaran
# SPDX-License-Identifier: BSD-3-Clause

import io
import os
import tarfile
from pathlib import Path

import pytest

from pigeon_client.cli import (
    build_tar_gz,
    generate_upload_url,
    upload_archive,
    cmd_push,
    main,
)


class DummyResp:
    def __init__(self, status_code=200, json_data=None, text="OK"):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


def test_build_tar_gz_creates_archive(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "a.txt").write_text("hello")
    (data_dir / "sub").mkdir()
    (data_dir / "sub" / "b.bin").write_bytes(b"\x00\x01")

    tar_path = build_tar_gz(data_dir)
    try:
        assert tar_path.exists()
        assert tar_path.suffixes[-2:] == [".tar", ".gz"]

        with tarfile.open(tar_path, "r:gz") as tf:
            names = tf.getnames()

        # Should include a top-level folder named after data_dir.name
        assert f"{data_dir.name}/a.txt" in names
        assert f"{data_dir.name}/sub/b.bin" in names
    finally:
        tar_path.unlink(missing_ok=True)


def test_build_tar_gz_missing_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_tar_gz(tmp_path / "does-not-exist")


def test_build_tar_gz_not_a_dir(tmp_path):
    p = tmp_path / "file.txt"
    p.write_text("x")
    with pytest.raises(NotADirectoryError):
        build_tar_gz(p)


def test_generate_upload_url_happy(monkeypatch):
    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        assert url.endswith("/generate-upload-url")
        assert json == {"object_key": "k1"}
        return DummyResp(200, {"upload_url": "upload/abc"})

    monkeypatch.setattr("requests.post", fake_post)

    u = generate_upload_url("http://server/", "k1")
    assert u == "http://server/upload/abc"


def test_generate_upload_url_relative_with_mount(monkeypatch):
    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        return DummyResp(200, {"upload_url": "upload/abc"})

    monkeypatch.setattr("requests.post", fake_post)

    u = generate_upload_url("https://host.example/pigeon-server", "k1")
    assert u == "https://host.example/pigeon-server/upload/abc"


def test_generate_upload_url_non_200(monkeypatch):
    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        return DummyResp(400, {"error": "bad key"})

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(RuntimeError, match=r"Server rejected upload URL request"):
        generate_upload_url("http://server", "k1")


def test_generate_upload_url_non_json_200(monkeypatch):
    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        return DummyResp(200, ValueError("no json"))

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(RuntimeError, match=r"Server is reachable, but returned HTTP 200"):
        generate_upload_url("http://server", "k1")


def test_generate_upload_url_missing_upload_url(monkeypatch):
    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        return DummyResp(200, {"nope": 1})

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(RuntimeError, match=r"missing upload_url"):
        generate_upload_url("http://server", "k1")


def test_generate_upload_url_network_error(monkeypatch):
    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        raise Exception("network down")

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(RuntimeError, match=r"Failed to contact server"):
        generate_upload_url("http://server", "k1")


def test_upload_archive_happy(monkeypatch, tmp_path):
    archive = tmp_path / "x.tar.gz"
    archive.write_bytes(b"abc123")

    seen = {"headers": None, "data_type": None, "data_bytes": b""}

    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        assert url == "http://upload/here"
        seen["headers"] = headers
        seen["data_type"] = type(data).__name__
        # Simulate server reading stream
        seen["data_bytes"] = data.read()
        return DummyResp(200, {"ok": True})

    monkeypatch.setattr("requests.post", fake_post)

    upload_archive("http://upload/here", archive, timeout=(1, 1))

    assert seen["headers"]["Content-Type"] == "application/octet-stream"
    assert seen["headers"]["Content-Length"] == str(archive.stat().st_size)
    assert seen["data_bytes"] == b"abc123"


def test_upload_archive_rejected(monkeypatch, tmp_path):
    archive = tmp_path / "x.tar.gz"
    archive.write_bytes(b"abc123")

    def fake_post(url, json=None, timeout=None, headers=None, data=None):
        return DummyResp(403, json_data={"error": "nope"}, text="nope")

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(RuntimeError, match=r"Upload failed: Server rejected upload with HTTP 403: nope"):
        upload_archive("http://upload/here", archive, timeout=(1, 1))


def test_cmd_push_missing_server_url(monkeypatch, caplog, tmp_path):
    # No env and no args.server_url
    monkeypatch.delenv("PIGEON_SERVER_URL", raising=False)

    args = type("Args", (), {})()
    args.server_url = None
    args.key = "k"
    args.data_dir = str(tmp_path)

    rc = cmd_push(args)
    assert rc == 2


def test_cmd_push_happy_flow(monkeypatch, tmp_path, capsys):
    # Create some data to archive
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "file.txt").write_text("hello")

    # Patch network functions to avoid real HTTP
    monkeypatch.setenv("PIGEON_SERVER_URL", "http://server/")

    def fake_generate_upload_url(server_url, object_key):
        assert server_url == "http://server/"
        assert object_key == "k1"
        return "http://upload/abc"

    uploaded = {"called": False}

    def fake_upload_archive(upload_url, archive_path, timeout=(5, 300)):
        assert upload_url == "http://upload/abc"
        assert archive_path.exists()
        uploaded["called"] = True

    monkeypatch.setattr("pigeon_client.cli.generate_upload_url", fake_generate_upload_url)
    monkeypatch.setattr("pigeon_client.cli.upload_archive", fake_upload_archive)

    args = type("Args", (), {})()
    args.server_url = None
    args.key = "k1"
    args.data_dir = str(data_dir)

    rc = cmd_push(args)
    assert rc == 0
    assert uploaded["called"] is True

    out = capsys.readouterr().out
    assert "Upload successful" in out

    # cmd_push should cleanup its temp archive (we can't know the name, but ensure no pigeon_*.tar.gz left)
    leftovers = list(tmp_path.glob("pigeon_*.tar.gz"))
    assert leftovers == []


def test_main_parses_and_calls_push(monkeypatch, tmp_path):
    # Minimal smoke test for argparse wiring: replace cmd_push via parser dispatch
    called = {"ok": False}

    def fake_cmd_push(args):
        called["ok"] = True
        return 0

    monkeypatch.setattr("pigeon_client.cli.cmd_push", fake_cmd_push)

    rc = main(["push", "-k", "k1", "-d", str(tmp_path), "--server-url", "http://server/"])
    assert rc == 0
    assert called["ok"] is True
