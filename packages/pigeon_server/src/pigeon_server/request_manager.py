# Copyright (c) 2026 Forschungszentrum Juelich GmbH, Juelich Supercomputing Centre
# Contributors:
# - Aravind Sankaran
# SPDX-License-Identifier: BSD-3-Clause

import logging
import time
import os
import tempfile
import requests
import shutil
from typing import Optional
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

logger = logging.getLogger(__name__)



class RequestManager:
    """
    Coordinates token generation/validation and upload routing via dispatch.

    Used by the server layer to create time-limited upload tokens, resolve
    upload destinations via dispatch, stream upload content, and send status
    notifications to dispatch.
    """

    def __init__(self, dispatch_key, dispatch_url, token_key, token_age=600):
        """
        Initialize a request manager instance.

        :param dispatch_key: Shared secret used to authenticate server-to-dispatch calls.
        :type dispatch_key: str
        :param dispatch_url: Base URL of the dispatch service.
        :type dispatch_url: str
        :param token_key: Secret used to sign and verify upload tokens.
        :type token_key: str
        :param token_age: Token validity period in seconds.
        :type token_age: int
        """
        self.serializer = URLSafeTimedSerializer(token_key)
        self.token_age = int(token_age)
        
        self.dispatch_headers = {"X-Pigeon-Dispatch-Key": dispatch_key}
        self.dispatch_url = dispatch_url

    def _post_json(self, path: str, payload: dict, *, timeout=(2, 5), headers={}) -> requests.Response:
        """
        Send a JSON POST request to dispatch and enforce HTTP 200 responses.

        :param path: Dispatch endpoint path (for example, ``"/get_dispatch_info"``).
        :type path: str
        :param payload: JSON body sent to dispatch.
        :type payload: dict
        :param timeout: Requests timeout tuple ``(connect, read)``.
        :type timeout: tuple
        :param headers: Optional HTTP headers.
        :type headers: dict
        :returns: Raw response object when status is 200.
        :rtype: requests.Response
        :raises RuntimeError: If request transmission fails or dispatch returns non-200.
        """
        url = f"{self.dispatch_url}{path}"
        _headers = {**self.dispatch_headers, **headers}
        try:
            resp = requests.post(url, json=payload, timeout=timeout, headers=_headers)
        except requests.RequestException as e:
            msg = f"500, Failed to contact dispatch at {url}"
            logger.error(msg)
            raise RuntimeError(msg)
        
        try:
            response_json = resp.json()
        except ValueError:
            msg = f"{resp.status_code}, Dispatch returned non-JSON response for POST {path}"
            logger.error(msg)
            raise RuntimeError(msg)
        
        if resp.status_code != 200:
            msg = f"{resp.status_code}, Dispatch returned error for POST {path}: {response_json.get('error')}"
            logger.error(msg)
            raise RuntimeError(msg)
            
        return response_json


    def _generate_token(self, request_id: int) -> str:
        """
        Create a signed token containing the given request id.

        :param request_id: Request identifier to encode in the token payload.
        :type request_id: int
        :returns: Signed token string.
        :rtype: str
        """
        return self.serializer.dumps({"request_id": request_id})

    def _verify_token(self, token: str) -> dict:
        """
        Verify and deserialize a signed token constrained by ``self.token_age``.

        :param token: Signed token string.
        :type token: str
        :returns: Deserialized token payload.
        :rtype: dict
        :raises itsdangerous.BadSignature: If token signature is invalid.
        :raises itsdangerous.SignatureExpired: If token is older than ``self.token_age``.
        """
        return self.serializer.loads(token, max_age=self.token_age)

    def generate_upload_token(self, object_key: str) -> str:
        """
        Create an upload token for a validated object key.

        Workflow:
        - ask dispatch to validate object_key and return a request_id,
        - generate a signed token embedding that request_id,
        - register token issue/expiry timestamps with dispatch.

        :param object_key: Caller-provided upload intent identifier.
        :type object_key: str
        :returns: Signed upload token.
        :rtype: str
        :raises RuntimeError: If dispatch communication or response parsing fails.
        """
        logger.info(f"[{object_key}] - Calling /generate-request-id")
        
        resp_json = self._post_json(
            "/generate-request-id",
            {"object_key": object_key}
        )

        request_id = resp_json.get("request_id")
        if request_id is None:
            msg = f"500, Dispatch did not return request_id for object_key {object_key}"
            logger.error(msg)
            raise RuntimeError(msg) 

        
        
        issued_at = int(time.time())
        expires_at = issued_at + self.token_age
        token = self._generate_token(request_id)
        
        logger.info(f"[{request_id}] - Validation successful. Received request ID and generated token. Calling /register-token")

        # self._register_token_lifetime(request_id, issued_at, expires_at)
        
        _ = self._post_json(
            "/register-token",
            {"request_id": request_id, "issued_at": issued_at, "expires_at": expires_at},
        )

        logger.info(f"[{request_id}] - Request bound with dispatch.")
        
        return token

    def process_upload_stream(self, token: str, stream, content_length: Optional[int]=None):
        """
        Validate token, stream uploaded bytes, and notify dispatch on success.

        This method never buffers the full body in memory. It either:
        - atomically writes to a filesystem path provided by dispatch, or
        - streams bytes to an API endpoint provided by dispatch.

        :param token: Signed upload token generated by :meth:`generate_upload_token`.
        :type token: str
        :param stream: Binary file-like input stream (for example Flask ``request.stream``).
        :type stream: typing.BinaryIO
        :param content_length: Optional upload size in bytes, forwarded for API routing.
        :type content_length: int | None
        :raises RuntimeError: If token verification, routing lookup, streaming, or
            final dispatch notification fails.
        """
        # 1) verify token first (cheap)
        logger.info(f"[ ] - Received upload request, verifying token.")
        try:
            payload = self._verify_token(token)
            request_id = payload.get("request_id")
            if request_id is None:
                msg = "500, Token payload missing request_id"
                logger.error(msg)
                raise RuntimeError(msg)
        except SignatureExpired:
            msg = "401, Token has expired"
            logger.info(msg)
            raise RuntimeError(msg)
        except BadSignature:
            msg = "400, Invalid token"
            logger.info(msg)
            raise RuntimeError(msg)

        logger.info(f"[{request_id}] - Token verified successfully. Calling /get_dispatch_info")
        # 2) ask dispatch where to save / send
        resp_json = self._post_json("/get_dispatch_info", {"request_id": request_id})

        process_type = resp_json.get("type")
        if process_type not in ("filesystem", "api"):
            msg = f"500, Dispatch returned unknown process type for request_id {request_id}: {process_type}"
            logger.error(msg)
            raise RuntimeError(msg)
        
        logger.info(f"[{request_id}] - Dispatching to {process_type}. Starting upload streaming.")

        # 3) stream to destination
        if process_type == "filesystem":
            file_path = os.path.abspath(resp_json.get("file_path"))
            if not file_path:
                msg = "500, Missing file_path for filesystem process type"
                logger.error(msg)
                raise RuntimeError(msg)

            try:
                directory = os.path.dirname(file_path)
                if directory:
                    os.makedirs(directory, exist_ok=True)
            except Exception as e:
                msg = f"500, Failed to prepare directory for file_path {file_path}"
                logger.error(f"{msg}: {e}")
                raise RuntimeError(msg)

            tmp_path = None
            try:
                # atomic write via temp file
                with tempfile.NamedTemporaryFile(dir=directory or ".", delete=False) as tmp_file:
                    tmp_path = tmp_file.name
                    shutil.copyfileobj(stream, tmp_file, length=1024 * 1024)  # 1MiB buffer
                    tmp_file.flush()
                    os.fsync(tmp_file.fileno())

                os.replace(tmp_path, file_path)
            except Exception as e:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        logger.warning(f"Failed to clean up temp file {tmp_path}")
                msg = f"500, Failed to write uploaded file for request {request_id}"
                logger.error(f"{msg}: {e}")
                raise RuntimeError(msg)
            
            logger.info(f"[{request_id}] - Upload to filesystem complete. Path: {file_path}")

        else:
            api_endpoint = resp_json.get("api_endpoint")
            if not api_endpoint:
                msg = "500, Missing api_endpoint for api process type"
                logger.error(msg)
                raise RuntimeError(msg)

            headers = {"Content-Type": "application/octet-stream"}
            # If we know length, send it; helps some servers/proxies
            if content_length is not None:
                headers["Content-Length"] = str(content_length)

            try:
                r = requests.post(
                    api_endpoint,
                    data=stream,          # <-- streamed, not buffered into memory
                    headers=headers,
                    timeout=(3, 60),
                )
            except requests.RequestException as e:
                msg = f"500, Failed to contact API endpoint {api_endpoint}"
                logger.error(f"{msg}: {e}")
                raise RuntimeError(msg)
            
            if r.status_code != 200:
                msg = f"{r.status_code}, API endpoint {api_endpoint} returned error: {r.text[:300]}"
                logger.error(msg)
                raise RuntimeError(msg)

            logger.info(f"[{request_id}] - Upload to API endpoit complete. Endpoint: {api_endpoint}")
        
        logger.info(f"[{request_id}] - Calling /notification")    
        # 4) success notify
        _ = self._post_json(
                "/notification",
                {"request_id": request_id, "status": 1, "message": "success"},
            )
        logger.info(f"[{request_id}] - Dispatch approved upload.")
