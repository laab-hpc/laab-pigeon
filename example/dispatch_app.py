from flask import Flask
from pathlib import Path
import os

from typing import Dict
import json
import uuid
from pigeon_dispatch.blueprint import create_dispatch_blueprint
from pigeon_dispatch.backend import DispatchBackend, ProcessInfo


import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class SimpleFileDispatchBackend(DispatchBackend):
    """
    Extremely simple testing backend.

    - request_id is a UUID string
    - object_key must start with "123"
    - on_notification checks file existence
    """

    def __init__(self, dispatch_dir: Path):
        self.dispatch_dir = Path(os.path.abspath(dispatch_dir))
        self.dispatch_dir.mkdir(parents=True, exist_ok=True)

        self.state_file = self.dispatch_dir / "state.json"
        if not self.state_file.exists():
            self._write_state({})

    # -----------------------------
    # Internal helpers
    # -----------------------------

    def _read_state(self) -> Dict[str, dict]:
        return json.loads(self.state_file.read_text())

    def _write_state(self, state: Dict[str, dict]) -> None:
        self.state_file.write_text(json.dumps(state, indent=2))

    # -----------------------------
    # Interface implementation
    # -----------------------------

    def validate_object_key(self, object_key: str) -> None:
        if not object_key.startswith("123"):
            raise ValueError("Invalid object key.")

    def generate_request_id(self, object_key: str) -> str:
        # Do NOT persist anything here
        return f"{object_key}-{uuid.uuid4()}"

    def register_token(self, request_id: str, issued_at: int, expires_at: int) -> None:
        state = self._read_state()

        state[request_id] = {
            "request_id": request_id,
            "object_key": request_id.split("-")[0],
            "issued_at": issued_at,
            "expires_at": expires_at,
            "status": "registered",
        }

        self._write_state(state)

    def get_dispatch_info(self, request_id: str) -> ProcessInfo:
        state = self._read_state()

        if request_id not in state:
            raise ValueError("Unknown request_id")

        file_path = self.dispatch_dir / f"{request_id}.bin"
        
        return ProcessInfo(type="filesystem", file_path=str(file_path))

    def on_notification(self, request_id: str, status: int, message: str) -> None:
        file_path = self.dispatch_dir / f"{request_id}.bin"
        state = self._read_state()
        
        if status == 1:
            if file_path.exists():
                state[request_id]["status"] = "received"
                self._write_state(state)
                return
            else:
                state[request_id]["status"] = "file_missing"
                self._write_state(state)
                raise RuntimeError("File is missing")
        else:
            state[request_id]["status"] = f"error: {message}"
            self._write_state(state)
            raise RuntimeError(f"Received error notification: {message}")


def main():
    dispatch_dir = Path(os.getenv("PIGEON_DISPATCH_DIR", "./test-data"))

    backend = SimpleFileDispatchBackend(dispatch_dir=dispatch_dir)

    app = Flask(__name__)
    app.register_blueprint(create_dispatch_blueprint(backend))
    
    app.run(debug=True, port=3001)


if __name__ == "__main__":
    main()
