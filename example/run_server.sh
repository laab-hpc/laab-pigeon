#!/usr/bin/env bash
set -euo pipefail

source /home/aravind/laab/tools/pigeon/venv/bin/activate

export PIGEON_TOKEN_KEY="${PIGEON_TOKEN_KEY:-test-key}"
export PIGEON_DISPATCH_KEY="${PIGEON_DISPATCH_KEY:-supersecretkey}"
export PIGEON_DISPATCH_URL="${PIGEON_DISPATCH_URL:-http://127.0.0.1:3001}"
export PIGEON_SERVER_PORT="${PIGEON_SERVER_PORT:-3000}"

pigeon-server
