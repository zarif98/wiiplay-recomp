#!/bin/sh
# macOS one-time setup: Homebrew tools, then scripts/build.py setup (extracts your disc).
set -eu
cd "$(dirname "$0")"
brew install cmake ninja
brew list --cask dotnet-sdk >/dev/null 2>&1 || brew install --cask dotnet-sdk
exec python3 scripts/build.py setup "$@"
