# Copyright (c) 2026 Forschungszentrum Juelich GmbH, Juelich Supercomputing Centre
# Contributors:
# - Aravind Sankaran
# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Optional



ProcessType = Literal["filesystem", "api"]


@dataclass(frozen=True)
class ProcessInfo:
    type: ProcessType
    file_path: Optional[str] = None
    api_endpoint: Optional[str] = None


class DispatchBackend(ABC):
    """
    Dispatch apps implement this interface.
    pigeon provides the HTTP layer around it.
    """

    @abstractmethod
    def validate_object_key(self, object_key: str) -> None:
        """Raise an exception if object_key is not allowed."""

    @abstractmethod
    def generate_request_id(self, object_key: str) -> int:
        """
        Return a request_id. Caller (pigeon client) will later register it.
        Does not need to persist anything if you don't want to.
        """

    @abstractmethod
    def register_token(self, request_id: int, issued_at: int, expires_at: int) -> None:
        """Persist request state so you can expire it later."""

    @abstractmethod
    def get_dispatch_info(self, request_id: int) -> ProcessInfo:
        """Return where the uploaded bytes should go (filesystem path or API endpoint)."""

    @abstractmethod
    def on_notification(self, request_id: int, status: int, message: str) -> None:
        """Receive status updates from pigeon (success/failure/etc)."""