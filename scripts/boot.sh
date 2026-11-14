#!/bin/zsh
# Boot the native build for N seconds (default 25) and print the interesting part of the log.
cd "$(dirname "$0")/../build/native"
perl -e "alarm ${1:-25}; exec @ARGV" ./WiiCompiled > ../run.log 2>&1
echo "exit $?"
grep -vE '^\[aurora\]|^  ' ../run.log | grep -vE 'Loaded _|runtime-config|Stack words|backchain|  #|GPR|SRR|PC=|SP\(' | tail -${2:-30}
