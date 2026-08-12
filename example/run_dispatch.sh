#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source /home/aravind/laab/tools/pigeon/venv/bin/activate

export PIGEON_DISPATCH_DIR="${PIGEON_DISPATCH_DIR:-$SCRIPT_DIR/test-data}"
export PIGEON_DISPATCH_KEY="${PIGEON_DISPATCH_KEY:-supersecretkey}"

python "$SCRIPT_DIR/dispatch_app.py"
