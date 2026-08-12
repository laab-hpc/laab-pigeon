#!/usr/bin/env bash
set -euo pipefail

source /home/aravind/laab/tools/pigeon/venv/bin/activate

pigeon-client -v push --key 123-demo --data-dir sample-data --server-url http://127.0.0.1:3000
