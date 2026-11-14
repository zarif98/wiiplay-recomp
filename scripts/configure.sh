#!/bin/zsh
# Configure the native build (CMake + Ninja) into build/native. Run once before scripts/rebuild.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
dotnet build fw/translator/src/Translator.Cli/Translator.Cli.csproj -c Release
cmake -S runtime -B build/native -G Ninja \
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_BUILD_TYPE=Release \
  -DAURORA_DAWN_PROVIDER=package -DAURORA_SDL3_PROVIDER=vendor -DCMAKE_POLICY_DEFAULT_CMP0168=NEW \
  -DMKW_TRANSLATED_COMPILE_JOBS=6
# The runtime looks for its data next to the executable in portable mode.
touch build/native/portable.txt
mkdir -p build/native/UserData
if [[ ! -f build/native/UserData/Config.toml ]]; then
  printf '[paths]\ndvd_root = "%s"\n\n[video]\ndisplay_mode = "windowed"\nwindow_width = 1280\nwindow_height = 720\n' \
    "$PWD/extracted" > build/native/UserData/Config.toml
fi
echo "configured build/native"
