#!/bin/zsh
# Translate -> data init -> shards -> native build. Usage: scripts/rebuild.sh [--skip-translate]
set -euo pipefail
cd "$(dirname "$0")/.."
T=fw/translator/src/Translator.Cli/bin/Release/net8.0/Translator.Cli.dll
P=projects/wiiplay/recomp.yml
if [[ "${1:-}" != "--skip-translate" ]]; then
  mkdir -p generated/functions build/base
  dotnet $T translate-recursive 0x80006124 --project $P --outdir generated/functions \
    --output-metadata generated/base_translation_output.json \
    --production-source-bundle generated/base_translation_sources.bin \
    --no-function-files --prune-stale --threads $(sysctl -n hw.ncpu) > generated/translate.log 2>&1
  grep -E 'Recursively|DEVELOPER' generated/translate.log || true
  dotnet $T generate-data-init --project $P > generated/data-init.log 2>&1
fi
dotnet $T emit-build-shards --project $P --base-metadata $PWD/generated/base_translation_output.json \
  --base-functions-dir $PWD/generated/functions --native-source-dir $PWD/runtime/src \
  --out $PWD/generated/build_shards > generated/shards.log 2>&1 || { tail -3 generated/shards.log; exit 1; }
ninja -C build/native WiiCompiled > build/compile.log 2>&1 || { grep -E 'error:|^  "_' build/compile.log | head -20; exit 1; }
echo "built build/native/WiiCompiled"
