#!/usr/bin/env python3
"""Cross-platform build driver (macOS, Linux, Windows). Standard library only.

  python3 scripts/build.py setup [DISC]      download nodtool and extract your disc into extracted/
  python3 scripts/build.py configure         build the translator, configure CMake into build/native
  python3 scripts/build.py build [--skip-translate]   translate main.dol and compile the game
  python3 scripts/build.py all [DISC]        all three steps
  python3 scripts/build.py audit             compile the native runtime only (no disc needed; used by CI)

macOS needs Xcode Command Line Tools, CMake, Ninja and the .NET 8+ SDK (`brew install cmake ninja`
and `brew install --cask dotnet-sdk`). Linux needs clang, CMake, Ninja, .NET 8+ and SDL's build
dependencies (see README). On Windows the script downloads a portable LLVM-MinGW, CMake and Ninja
into tools/ and, if no .NET 8+ SDK is installed, a portable .NET SDK.
"""
import hashlib
import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / 'tools'
SYSTEM = platform.system()  # 'Darwin', 'Linux', 'Windows'
IS_WIN = SYSTEM == 'Windows'
EXE = '.exe' if IS_WIN else ''

NOD_VERSION = 'v2.0.0-alpha.10'
WIN_TOOLS = {  # same pins as the WiiCompiled/Wario Windows tooling
    'llvm-mingw': 'https://github.com/mstorsjo/llvm-mingw/releases/download/20260616/llvm-mingw-20260616-ucrt-x86_64.zip',
    'CMake': 'https://github.com/Kitware/CMake/releases/download/v4.3.3/cmake-4.3.3-windows-x86_64.zip',
    'Ninja': 'https://github.com/ninja-build/ninja/releases/download/v1.13.2/ninja-win.zip',
}
TRANSLATOR_PROJ = ROOT / 'fw/translator/src/Translator.Cli/Translator.Cli.csproj'
TRANSLATOR_DLL = ROOT / 'fw/translator/src/Translator.Cli/bin/Release/net8.0/Translator.Cli.dll'
PROJECT = 'projects/wiiplay/recomp.yml'
BUILD = ROOT / 'build/native'
AUDIT_BUILD = ROOT / 'build/audit'
DISC_EXTS = ('.iso', '.wbfs', '.rvz', '.wia', '.ciso', '.gcz', '.tgc', '.nfs')


def log(msg):
    print(f'==> {msg}', flush=True)


def die(msg):
    sys.exit(f'error: {msg}')


def run(cmd, log_file=None, **kw):
    cmd = [str(c) for c in cmd]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'w', encoding='utf-8', errors='replace') as f:
            r = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, **kw)
        if r.returncode:
            tail = log_file.read_text(encoding='utf-8', errors='replace').splitlines()[-25:]
            die(f'{Path(cmd[0]).name} failed (exit {r.returncode}); last lines of {log_file}:\n' + '\n'.join(tail))
    else:
        r = subprocess.run(cmd, cwd=ROOT, **kw)
        if r.returncode:
            die(f'command failed (exit {r.returncode}): {" ".join(cmd)}')


def download(url, dest):
    log(f'downloading {url.rsplit("/", 1)[-1]}')
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + '.part')
    req = urllib.request.Request(url, headers={'User-Agent': 'wiiplay-recomp-build'})
    with urllib.request.urlopen(req) as r, open(tmp, 'wb') as f:
        shutil.copyfileobj(r, f)
    tmp.replace(dest)


def cpu_count():
    return os.cpu_count() or 4


# ---------------------------------------------------------------- tools

def windows_tools():
    """Portable LLVM-MinGW, CMake and Ninja in tools/ (downloaded once)."""
    for name, url in WIN_TOOLS.items():
        target = TOOLS / name
        if target.exists():
            continue
        archive = TOOLS / (name + '.zip')
        download(url, archive)
        log(f'unpacking {name}')
        staging = TOOLS / (name + '.unpack')
        shutil.rmtree(staging, ignore_errors=True)
        with zipfile.ZipFile(archive) as z:
            z.extractall(staging)
        entries = list(staging.iterdir())
        # llvm-mingw and CMake unpack into one top-level folder; Ninja is a bare ninja.exe.
        (entries[0] if len(entries) == 1 and entries[0].is_dir() else staging).rename(target)
        shutil.rmtree(staging, ignore_errors=True)
        archive.unlink()
    paths = [TOOLS / 'llvm-mingw/bin', TOOLS / 'CMake/bin', TOOLS / 'Ninja']
    os.environ['PATH'] = os.pathsep.join([str(p) for p in paths] + [os.environ.get('PATH', '')])


def which(name, hint):
    p = shutil.which(name)
    if not p:
        die(f'{name} not found. {hint}')
    return p


def dotnet():
    """A .NET SDK >= 8 (the translator targets net8.0 and rolls forward to newer runtimes)."""
    os.environ.setdefault('DOTNET_CLI_TELEMETRY_OPTOUT', '1')
    os.environ['DOTNET_ROLL_FORWARD'] = 'Major'
    candidates = [shutil.which('dotnet'), str(TOOLS / 'dotnet' / f'dotnet{EXE}')]
    for c in candidates:
        if c and Path(c).exists():
            out = subprocess.run([c, '--list-sdks'], capture_output=True, text=True).stdout
            if any(line.split('.')[0].isdigit() and int(line.split('.')[0]) >= 8 for line in out.splitlines()):
                return c
    if IS_WIN:
        installer = TOOLS / 'dotnet-install.ps1'
        download('https://dot.net/v1/dotnet-install.ps1', installer)
        log('installing a portable .NET 8 SDK into tools/dotnet')
        run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', installer,
             '-Channel', '8.0', '-InstallDir', TOOLS / 'dotnet', '-NoPath'])
        return str(TOOLS / 'dotnet' / 'dotnet.exe')
    hint = {'Darwin': 'Install it with: brew install --cask dotnet-sdk',
            'Linux': 'Install the .NET 8 SDK (e.g. sudo apt install dotnet-sdk-8.0).'}.get(SYSTEM, '')
    die(f'a .NET 8 (or newer) SDK is required. {hint}')


def native_tools():
    if IS_WIN:
        windows_tools()
        return
    hint = {'Darwin': 'Install with: xcode-select --install; brew install cmake ninja',
            'Linux': 'See the Linux section of README.md for the package list.'}.get(SYSTEM, '')
    for tool in ('cmake', 'ninja', 'clang', 'clang++'):
        which(tool, hint)


# ---------------------------------------------------------------- steps

def nodtool():
    arch = platform.machine().lower()
    arch = {'amd64': 'x86_64', 'x64': 'x86_64', 'arm64': 'arm64' if SYSTEM == 'Darwin' else 'aarch64',
            'aarch64': 'aarch64' if SYSTEM == 'Linux' else 'arm64'}.get(arch, arch)
    osname = {'Darwin': 'macos', 'Linux': 'linux', 'Windows': 'windows'}[SYSTEM]
    path = TOOLS / f'nodtool{EXE}'
    if not path.exists():
        download(f'https://github.com/encounter/nod/releases/download/{NOD_VERSION}/nodtool-{osname}-{arch}{EXE}', path)
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def find_disc(arg):
    if arg:
        p = Path(arg).expanduser()
        if not p.exists():
            die(f'disc image not found: {p}')
        return p
    found = sorted(p for p in (ROOT / 'disc').glob('*') if p.suffix.lower() in DISC_EXTS)
    if not found:
        die('put your Wii Play (USA, RHAE01) disc image in disc/ or pass its path')
    return found[0]


def setup(disc_arg=None):
    disc = find_disc(disc_arg)
    tool = nodtool()
    out = ROOT / 'extracted'
    shutil.rmtree(out, ignore_errors=True)
    log(f'extracting {disc.name}')
    run([tool, 'extract', disc, out])
    dols = list(out.glob('**/sys/main.dol'))
    if not dols:
        die('extraction finished but no sys/main.dol was found')
    log(f'main.dol sha256 {hashlib.sha256(dols[0].read_bytes()).hexdigest()}')


def build_translator():
    dn = dotnet()
    if not TRANSLATOR_DLL.exists():
        log('building the translator')
        run([dn, 'build', TRANSLATOR_PROJ, '-c', 'Release'], log_file=ROOT / 'build/logs/translator.log')
    return dn


def cmake_args(build_dir, products=True):
    args = ['cmake', '-S', ROOT / 'runtime', '-B', build_dir, '-G', 'Ninja',
            '-DCMAKE_BUILD_TYPE=Release',
            '-DAURORA_DAWN_PROVIDER=package', '-DAURORA_SDL3_PROVIDER=vendor',
            '-DCMAKE_POLICY_DEFAULT_CMP0168=NEW',
            f'-DMKW_TRANSLATED_COMPILE_JOBS={max(1, min(6, cpu_count() // 2))}']
    if IS_WIN:
        bin_ = TOOLS / 'llvm-mingw/bin'
        args += [f'-DCMAKE_C_COMPILER={(bin_ / "x86_64-w64-mingw32-clang.exe").as_posix()}',
                 f'-DCMAKE_CXX_COMPILER={(bin_ / "x86_64-w64-mingw32-clang++.exe").as_posix()}',
                 f'-DCMAKE_RC_COMPILER={(bin_ / "x86_64-w64-mingw32-windres.exe").as_posix()}',
                 f'-DCMAKE_MAKE_PROGRAM={(TOOLS / "Ninja/ninja.exe").as_posix()}',
                 '-DCMAKE_SYSTEM_PROCESSOR=x86_64', '-DAWK:FILEPATH=']
    else:
        args += ['-DCMAKE_C_COMPILER=clang', '-DCMAKE_CXX_COMPILER=clang++']
    if not products:
        args.append('-DMKW_BUILD_PRODUCTS=OFF')
    return args


def write_config():
    user = BUILD / 'UserData'
    user.mkdir(parents=True, exist_ok=True)
    (BUILD / 'portable.txt').touch()  # the runtime keeps its data next to the executable
    cfg = user / 'Config.toml'
    if not cfg.exists():
        cfg.write_text(f'[paths]\ndvd_root = "{(ROOT / "extracted").as_posix()}"\n\n'
                       '[video]\ndisplay_mode = "windowed"\nwindow_width = 1280\nwindow_height = 720\n')


def configure():
    native_tools()
    build_translator()
    log('configuring CMake (the first run downloads Dawn, SDL and other dependencies)')
    if not (ROOT / 'generated/build_shards/shards.cmake').exists():
        log('no translation yet: translating first (CMake needs its shard list)')
        translate()
        emit_shards()
    run(cmake_args(BUILD), log_file=ROOT / 'build/logs/configure.log')
    write_config()
    log(f'configured {BUILD.relative_to(ROOT)}')


def translate():
    dn = build_translator()
    gen = ROOT / 'generated'
    (gen / 'functions').mkdir(parents=True, exist_ok=True)
    if not list((ROOT / 'extracted').glob('**/sys/main.dol')):
        die('extracted/ has no main.dol: run the setup step first')
    log(f'translating main.dol ({cpu_count()} threads)')
    run([dn, TRANSLATOR_DLL, 'translate-recursive', '0x80006124', '--project', PROJECT,
         '--outdir', 'generated/functions', '--output-metadata', 'generated/base_translation_output.json',
         '--production-source-bundle', 'generated/base_translation_sources.bin',
         '--no-function-files', '--prune-stale', '--threads', cpu_count()], log_file=gen / 'translate.log')
    run([dn, TRANSLATOR_DLL, 'generate-data-init', '--project', PROJECT], log_file=gen / 'data-init.log')


def emit_shards():
    dn = build_translator()
    run([dn, TRANSLATOR_DLL, 'emit-build-shards', '--project', PROJECT,
         '--base-metadata', ROOT / 'generated/base_translation_output.json',
         '--base-functions-dir', ROOT / 'generated/functions', '--native-source-dir', ROOT / 'runtime/src',
         '--out', ROOT / 'generated/build_shards'], log_file=ROOT / 'generated/shards.log')


def build(skip_translate=False):
    native_tools()
    if not skip_translate:
        translate()
    emit_shards()
    if not (BUILD / 'CMakeCache.txt').exists():
        run(cmake_args(BUILD), log_file=ROOT / 'build/logs/configure.log')
        write_config()
    log('compiling (the first build takes a while)')
    run(['cmake', '--build', BUILD, '--target', 'WiiCompiled'], log_file=ROOT / 'build/compile.log')
    log(f'built {(BUILD / ("WiiCompiled" + EXE)).relative_to(ROOT)}')


def audit():
    """Compile every native runtime source without translated game code (no disc needed)."""
    native_tools()
    build_translator()
    run(cmake_args(AUDIT_BUILD, products=False))
    run(['cmake', '--build', AUDIT_BUILD, '--target', 'mkw_native_compile', 'mkw_runtime_config_tests',
         'mkw_input_expr_tests'])
    log('native runtime compiles')


def main(argv):
    if not argv or argv[0] in ('-h', '--help', 'help'):
        print(__doc__)
        return
    cmd, rest = argv[0], argv[1:]
    if cmd == 'setup':
        setup(rest[0] if rest else None)
    elif cmd == 'configure':
        configure()
    elif cmd == 'build':
        build(skip_translate='--skip-translate' in rest)
    elif cmd == 'all':
        setup(rest[0] if rest else None)
        configure()
        build(skip_translate=True)
    elif cmd == 'audit':
        audit()
    else:
        die(f'unknown command {cmd!r} (try --help)')


if __name__ == '__main__':
    main(sys.argv[1:])
