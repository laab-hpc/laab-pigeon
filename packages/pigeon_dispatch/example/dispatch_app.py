# Copyright (c) 2026 Forschungszentrum Juelich GmbH, Juelich Supercomputing Centre
# Contributors:
# - Aravind Sankaran
# SPDX-License-Identifier: BSD-3-Clause

from flask import Flask
from pathlib import Path
import os

from pigeon_dispatch.blueprint import create_dispatch_blueprint
from pigeon_dispatch.backends.simple_file import SimpleFileDispatchBackend

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def create_app():
    # directory where uploaded files + state.json live
    base_dir = Path(os.getenv("PIGEON_DISPATCH_DIR", "./test-data"))

    backend = SimpleFileDispatchBackend(base_dir=base_dir)

    app = Flask(__name__)
    app.register_blueprint(create_dispatch_blueprint(backend))
    return app


def main():
    app = create_app()
    app.run(debug=True, port=5001)
    
if __name__ == "__main__":
    main()