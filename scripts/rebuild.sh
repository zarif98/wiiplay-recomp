#!/bin/sh
# Kept for convenience; see scripts/build.py. Usage: scripts/rebuild.sh [--skip-translate]
exec python3 "$(dirname "$0")/build.py" build "$@"
