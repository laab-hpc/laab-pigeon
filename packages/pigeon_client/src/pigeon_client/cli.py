# Copyright (c) 2026 Forschungszentrum Juelich GmbH, Juelich Supercomputing Centre
# Contributors:
# - Aravind Sankaran
# SPDX-License-Identifier: BSD-3-Clause

import argparse
import logging
import os
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests

logger = logging.getLogger("pigeon-client")


def build_tar_gz(data_dir: Path) -> Path:
    """
    Create a ``.tar.gz`` archive from a directory in a temporary file.

    The archive stores content under a stable top-level directory equal to
    ``data_dir.name``.

    :param data_dir: Directory to archive.
    :type data_dir: pathlib.Path
    :returns: Path to the generated temporary archive file.
    :rtype: pathlib.Path
    :raises FileNotFoundError: If ``data_dir`` does not exist.
    :raises NotADirectoryError: If ``data_dir`` is not a directory.
    :raises Exception: Propagates archive creation errors after cleanup attempt.
    """
    if not data_dir.exists():
        raise FileNotFoundError(f"Data dir does not exist: {data_dir}")
    if not data_dir.is_dir():
        raise NotADirectoryError(f"Data path is not a directory: {data_dir}")

    # Create archive on disk (not in memory)
    tmp = tempfile.NamedTemporaryFile(prefix="pigeon_", suffix=".tar.gz", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    try:
        with tarfile.open(tmp_path, mode="w:gz") as tf:
            # store directory under a stable top-level name
            tf.add(str(data_dir), arcname=data_dir.name, recursive=True)
        return tmp_path
    except Exception:
        # cleanup if tar creation fails
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to cleanup temp archive %s", tmp_path, exc_info=True)
        raise


def generate_upload_url(server_base_url: str, object_key: str, timeout=(3, 10)) -> str:
    """
    Request a temporary upload URL from ``pigeon-server``.

    :param server_base_url: Base URL of the server endpoint.
    :type server_base_url: str
    :param object_key: Upload intent identifier validated by dispatch.
    :type object_key: str
    :param timeout: Requests timeout tuple ``(connect, read)``.
    :type timeout: tuple
    :returns: Absolute upload URL resolved from server response.
    :rtype: str
    :raises RuntimeError: If server communication or response parsing fails.
    """
    # Be tolerant if user passes base without trailing slash
    endpoint = urljoin(server_base_url.rstrip("/") + "/", "generate-upload-url")

    try:
        r = requests.post(endpoint, json={"object_key": object_key}, timeout=timeout)
    except Exception as e:
        raise RuntimeError(f"Failed to contact server at {endpoint}")

    
    try:
        j = r.json()
    except ValueError as e:
        raise RuntimeError(f"Server is reachable, but returned HTTP {r.status_code} for {endpoint}") from e
    
    if r.status_code != 200:
        msg = r.json().get("error")
        raise RuntimeError(f"Server rejected upload URL request: {msg}")

    upload_url = j.get("upload_url")
    if not upload_url:
        raise RuntimeError("Server response missing upload_url")

    # Backward-compatible: accept absolute URL or relative upload path.
    if upload_url.startswith("http://") or upload_url.startswith("https://"):
        return upload_url

    base = server_base_url.rstrip("/") + "/"
    return urljoin(base, upload_url)

def upload_archive(upload_url: str, archive_path: Path, timeout=(5, 300)) -> None:
    """
    Upload an archive file to a pre-signed upload URL.

    :param upload_url: Target upload URL returned by the server.
    :type upload_url: str
    :param archive_path: Path to archive file to upload.
    :type archive_path: pathlib.Path
    :param timeout: Requests timeout tuple ``(connect, read)``.
    :type timeout: tuple
    :returns: ``None`` when upload succeeds.
    :rtype: None
    :raises RuntimeError: If network upload fails or remote endpoint rejects data.
    """
    size = archive_path.stat().st_size
    headers = {
        "Content-Type": "application/octet-stream",
        "Content-Length": str(size),
    }

    with archive_path.open("rb") as f:
        try:
            r = requests.post(upload_url, data=f, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            raise RuntimeError(f"Upload failed (network) to {upload_url}: {e}") from e

    try:
        j = r.json()
    except ValueError:
        raise RuntimeError(f"Upload failed: Server returned HTTP {r.status_code} for {upload_url} with non-JSON response")
    
    if r.status_code != 200:
        msg = j.get("error")
        raise RuntimeError(f"Upload failed: Server rejected upload with HTTP {r.status_code}: {msg}")
        

def cmd_push(args: argparse.Namespace) -> int:
    """
    Execute the ``push`` subcommand workflow.

    Steps:
    - resolve server URL from CLI arg or ``PIGEON_SERVER_URL``,
    - build a temporary archive from ``--data-dir``,
    - request upload URL using ``--key``,
    - upload archive and clean temporary file.

    :param args: Parsed command-line arguments for ``push``.
    :type args: argparse.Namespace
    :returns: Process exit status code (``0`` success, non-zero failure).
    :rtype: int
    """
    server_url = args.server_url or os.getenv("PIGEON_SERVER_URL")
    if not server_url:
        logger.error("Missing server URL. Use --server-url or set PIGEON_SERVER_URL.")
        return 2

    object_key = args.key
    data_dir = Path(args.data_dir).expanduser().resolve()

    archive_path: Optional[Path] = None
    try:
        logger.info("Requesting upload URL for object_key=%s from server %s", object_key, server_url)
        upload_url = generate_upload_url(server_url, object_key)

        logger.info("Creating archive from %s", data_dir)
        archive_path = build_tar_gz(data_dir)
        logger.info("Created archive: %s (%.2f MiB)", archive_path, archive_path.stat().st_size / (1024 * 1024))

        logger.info("Uploading to %s", upload_url)
        upload_archive(upload_url, archive_path)

        print("Upload successful")
        return 0

    except Exception as e:
        logger.error("%s", e)
        return 1

    finally:
        if archive_path is not None:
            try:
                logger.info("Cleaning up temp archive %s", archive_path)
                archive_path.unlink(missing_ok=True)
            except Exception:
                logger.warning("Failed to remove temp archive %s", archive_path, exc_info=True)


def build_parser() -> argparse.ArgumentParser:
    """
    Build the top-level CLI argument parser.

    :returns: Configured ``argparse`` parser with subcommands.
    :rtype: argparse.ArgumentParser
    """
    p = argparse.ArgumentParser(prog="pigeon", description="pigeon client")
    p.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity (-v, -vv)")
    sub = p.add_subparsers(dest="command", required=True)

    push = sub.add_parser("push", help="Pack directory and upload")
    push.add_argument("-k", "--key", required=True, help="Object key for upload")
    push.add_argument("-d", "--data-dir", required=True, help="Directory to pack and upload")
    push.add_argument("--server-url", help="Base URL of pigeon-server (or set PIGEON_SERVER_URL)")
    push.set_defaults(func=cmd_push)

    return p


def main(argv=None) -> int:
    """
    CLI entry point for ``pigeon-client``.

    :param argv: Optional argv list (excluding executable name).
    :type argv: list[str] | None
    :returns: Process exit status code from the selected subcommand.
    :rtype: int
    """
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)

    level = logging.WARNING
    if args.verbose == 1:
        level = logging.INFO
    elif args.verbose >= 2:
        level = logging.DEBUG

    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
