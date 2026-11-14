#!/bin/sh
# Kept for convenience; see scripts/build.py (works on macOS, Linux and Windows).
exec python3 "$(dirname "$0")/build.py" configure "$@"
