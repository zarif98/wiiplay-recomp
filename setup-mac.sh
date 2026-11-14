#!/bin/zsh
# One-time setup: build tools + extract your own Wii Play disc.
# Usage: ./setup-mac.sh   (defaults to disc/Wii Play [RHAE01].nkit.iso)
set -euo pipefail
cd "$(dirname "$0")"

DISC="${1:-disc/Wii Play [RHAE01].nkit.iso}"

brew install cmake ninja
brew install --cask dotnet-sdk@8

mkdir -p tools
if [[ ! -x tools/nodtool ]]; then
  curl -fsSL "https://github.com/encounter/nod/releases/download/v2.0.0-alpha.10/nodtool-macos-arm64" -o tools/nodtool
  chmod +x tools/nodtool
fi

rm -rf extracted && mkdir -p extracted
tools/nodtool extract "$DISC" extracted

echo
echo "main.dol:"
find extracted -path '*sys/main.dol' -exec shasum -a 256 {} \;
echo "REL modules:"
find extracted -name '*.rel' | head -20
