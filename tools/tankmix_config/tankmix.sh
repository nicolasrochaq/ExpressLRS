#!/bin/bash
# TankMix launcher for Linux: ./tankmix.sh
cd "$(dirname "$0")" || exit 1
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.8+ not found / Python 3.8+ nao encontrado: https://www.python.org/downloads/"
  xdg-open "https://www.python.org/downloads/" 2>/dev/null
  read -r -p "Press Enter / Aperte Enter " _
  exit 1
fi
exec "$PY" tankmix_config.py "$@"
