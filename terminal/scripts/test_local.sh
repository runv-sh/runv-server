#!/bin/sh
# Teste local sem SSH: fila e log dentro de terminal/data/.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/data/queue"
export RUNV_ENTRE_ROOT="$ROOT"
export RUNV_ENTRE_CONFIG="$ROOT/config.example.toml"
export RUNV_ENTRE_QUEUE_DIR="$ROOT/data/queue"
export RUNV_ENTRE_LOG_FILE="$ROOT/data/entre-test.log"
exec python3 "$ROOT/entre_app.py" "$@"
