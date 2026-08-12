# Copyright (c) 2026 Forschungszentrum Juelich GmbH, Juelich Supercomputing Centre
# Contributors:
# - Aravind Sankaran
# SPDX-License-Identifier: BSD-3-Clause

"""
Flask blueprint for dispatch-side endpoints used by ``pigeon-server``.

Endpoints:
    POST /generate-request-id
    POST /register-token
    POST /get_dispatch_info
    POST /notification
"""

from .backend import DispatchBackend
from flask import Blueprint, jsonify, request
import os
import hmac
import logging

logger = logging.getLogger(__name__)

HEADER_NAME = "X-Pigeon-Dispatch-Key"
ENV_KEY = "PIGEON_DISPATCH_KEY"


def _require_dispatch_key():
    """
    Enforce shared-secret authentication for server-to-dispatch requests.

    :returns: ``None`` if authorized, otherwise a Flask error response tuple.
    :rtype: tuple | None
    """
    dispatch_key = os.getenv(ENV_KEY)
    if not dispatch_key:
        logger.error("%s is not set; refusing request", ENV_KEY)
        return jsonify({"error": "Server misconfigured"}), 500

    provided = request.headers.get(HEADER_NAME)
    if not provided or not hmac.compare_digest(provided, dispatch_key):
        logger.warning("Unauthorized dispatch request to %s", request.path)
        return jsonify({"error": "Unauthorized"}), 401

    return None


def create_dispatch_blueprint(backend: DispatchBackend) -> Blueprint:
    """
    Create the dispatch API blueprint bound to a backend implementation.

    :param backend: Application backend implementing :class:`DispatchBackend`.
    :type backend: DispatchBackend
    :returns: Configured Flask blueprint containing dispatch endpoints.
    :rtype: flask.Blueprint
    """
    bp = Blueprint("pigeon_dispatch", __name__)

    @bp.post("/generate-request-id")
    def generate_request_id():
        """
        Validate an object key and allocate a request id.

        Request JSON:
            ``{"object_key": "<string>"}``

        :returns: JSON with ``request_id`` on success or an ``error`` message.
        :rtype: flask.Response
        """
        auth = _require_dispatch_key()
        if auth is not None:
            return auth

        logger.info("[ ] - /generate-request-id called")
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            logger.error("Invalid JSON body from pigeon-server")
            return jsonify({"error": "Internal error"}), 500

        object_key = data.get("object_key")
        if not object_key:
            logger.error("pigeon-server did not forward object_key")
            return jsonify({"error": "Internal error"}), 500

        logger.info(f"[{object_key}] - Validating object key")
        try:
            backend.validate_object_key(object_key)
        except Exception as e:
            # This is a client/input error (object_key not allowed)
            logger.info(f"[{object_key}] - Validation failed")
            return jsonify({"error": f"Invalid object key {object_key}"}), 401

        logger.info(f"[{object_key}] - Validation successful. Generating request ID.")
        try:
            request_id = backend.generate_request_id(object_key)
            logger.info(f"[{object_key}] - Generated request ID {request_id}")
            return jsonify({"request_id": request_id}), 200
        except Exception:
            logger.exception("generate-request-id: Valid object key was provided, but dispatch did not generate request_id.")
            return jsonify({"error": "Internal error"}), 500

    @bp.post("/register-token")
    def register_token():
        """
        Register token validity metadata for a request id.

        Request JSON:
            ``{"request_id": ..., "issued_at": <int>, "expires_at": <int>}``

        :returns: JSON ``{"ok": true}`` on success or ``{"error": ...}`` on failure.
        :rtype: flask.Response
        """
        auth = _require_dispatch_key()
        if auth is not None:
            return auth

        logger.info("[ ] - /register-token called")
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            logger.info("Invalid JSON body from pigeon-server")
            return jsonify({"error": "Invalid JSON body"}), 400
        
        try:
            request_id = data["request_id"]
            issued_at = int(data["issued_at"])
            expires_at = int(data["expires_at"])
        except (KeyError, TypeError, ValueError) as e:
            logger.info(f"Bad request from pigeon-server: {e}")
            return jsonify({"error": "Invalid request_id/issued_at/expires_at"}), 400

        logger.info(f"[{request_id}] - Registering request")
        try:
            backend.register_token(request_id, issued_at, expires_at)
            logger.info(f"[{request_id}] - Request lifetime bound.")
            return jsonify({"ok": True}), 200
        except Exception:
            logger.error(f"[{request_id}] - Failed to register token lifetime.")
            return jsonify({"error": "Internal error"}), 500

    @bp.post("/get_dispatch_info")
    def get_dispatch_info():
        """
        Resolve dispatch destination metadata for a request id.

        Request JSON:
            ``{"request_id": ...}``

        Response JSON:
            - filesystem mode: ``{"type": "filesystem", "file_path": "<path>"}``
            - api mode: ``{"type": "api", "api_endpoint": "<url>"}``

        :returns: Destination metadata or error JSON.
        :rtype: flask.Response
        """
        auth = _require_dispatch_key()
        if auth is not None:
            return auth

        logger.info("[ ] - /get_dispatch_info called")
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            logger.info("Invalid JSON body")
            return jsonify({"error": "Invalid JSON body"}), 400

        try:
            request_id = data["request_id"]
        except (KeyError, TypeError, ValueError):
            logger.info("Invalid/missing request_id")
            return jsonify({"error": "Invalid request_id"}), 400

        logger.info(f"[{request_id}] - Resolving dispatch info")
        try:
            info = backend.get_dispatch_info(request_id)
        except Exception:
            logger.error(f"[{request_id}] - Failed to get dispatch info from backend")
            return jsonify({"error": "Internal error"}), 500

        logger.info(f"[{request_id}] - Dispatch resolved to {info.type}")
        if info.type == "filesystem":
            if not info.file_path:
                logger.error(f"[{request_id}] - Filesystem path not provided")
                return jsonify({"error": "Internal error"}), 500
            logger.info(f"[{request_id}] - Forwarding filesystem path {info.file_path}")
            return jsonify({"type": "filesystem", "file_path": info.file_path}), 200

        if info.type == "api":
            if not info.api_endpoint:
                logger.error(f"[{request_id}] - API endpoint not provided")
                return jsonify({"error": "Internal error"}), 500
            logger.info(f"[{request_id}] - Forwarding API endpoint {info.api_endpoint}")
            return jsonify({"type": "api", "api_endpoint": info.api_endpoint}), 200

        logger.error(f"[{request_id}] - Invalid dispatch info type: {info.type}")
        return jsonify({"error": "Internal error"}), 500

    @bp.post("/notification")
    def notification():
        """
        Receive final upload status notification from the server.

        Request JSON:
            ``{"request_id": ..., "status": <int>, "message": "<string>"}``

        :returns: JSON ``{"ok": true}`` on success or ``{"error": ...}`` on failure.
        :rtype: flask.Response
        """
        auth = _require_dispatch_key()
        if auth is not None:
            return auth

        logger.info("[ ] - /notification called")
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            logger.info("Invalid JSON body")
            return jsonify({"error": "Invalid JSON body"}), 400

        try:
            request_id = data["request_id"]
            status = int(data["status"])
            message = str(data["message"])
        except (KeyError, TypeError, ValueError) as e:
            logger.info(f"Bad request from pigeon-server: {e}")
            return jsonify({"error": "Invalid request_id/status/message"}), 400

        logger.info(f"[{request_id}] - Processing upload notification")

        try:
            backend.on_notification(request_id, status, message)
            logger.info(f"[{request_id}] - Upload approved")
            return jsonify({"ok": True}), 200
        except Exception as e:
            logger.error(f"[{request_id}] - Approval failed with error {e}")
            return jsonify({"error": "Internal error"}), 500

    return bp
