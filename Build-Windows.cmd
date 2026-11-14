@echo off
rem Windows: downloads LLVM-MinGW, CMake, Ninja (and .NET 8 if missing) into tools\, extracts the
rem disc image from disc\ and builds build\native\WiiCompiled.exe. Needs Python 3 (python.org).
cd /d "%~dp0"
where py >nul 2>nul && (py -3 scripts\build.py all %*) || (python scripts\build.py all %*)
pause
