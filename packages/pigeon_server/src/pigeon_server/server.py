# Copyright (c) 2026 Forschungszentrum Juelich GmbH, Juelich Supercomputing Centre
# Contributors:
# - Aravind Sankaran
# SPDX-License-Identifier: BSD-3-Clause

import os
from flask import Flask, Blueprint

_PID = os.getpid()

import logging
logging.basicConfig(level=logging.INFO, format=f'%(asctime)s - [{_PID}] - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app_mount = os.getenv("PIGEON_SERVER_MOUNT", "/")


app = Flask(__name__)


from .blueprint import bp
app.register_blueprint(bp, url_prefix=f'{app_mount}/')
logger.info(f"pigeon-server API mounted at {app_mount}/")

def main():
    app_port =  int(os.getenv("PIGEON_SERVER_PORT", "5000"))
    app.run(debug=True, port=app_port)

if __name__ == "__main__":
    main()