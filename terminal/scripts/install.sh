#!/bin/sh
# Instalação rápida: delega em setup_entre.py (root).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec python3 "$ROOT/setup_entre.py" "$@"
