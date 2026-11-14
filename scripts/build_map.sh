#!/bin/zsh
# Rebuild projects/wiiplay/MAP.txt from scratch.
set -euo pipefail
cd "$(dirname "$0")/.."
D=extracted/sys/main.dol M=projects/wiiplay/MAP.txt
REF=vendor/wario-reference/projects/wario/MAP.txt
RT=vendor/wario-reference/runtime/src  # original Wario addresses
DSY=/Applications/Dolphin.app/Contents/Resources/Sys/totaldb.dsy
python3 -I scripts/make_function_map.py $D $M
python3 -I scripts/name_sdk_functions.py $D $M $DSY
python3 -I scripts/name_sdk_inits.py $D $M --apply | tail -1
for i in 1 2; do python3 -I scripts/name_by_neighbors.py $REF $M $RT --apply; done
# second signature pass over the newly split functions
python3 -I scripts/name_sdk_functions.py $D $M $DSY
python3 -I scripts/name_by_neighbors.py $REF $M $RT --apply
# drop known data addresses
python3 -I - "$M" projects/wiiplay/MAP_exclude.txt <<'PY'
import sys
m, ex = sys.argv[1], sys.argv[2]
bad = {l.split()[0].lower() for l in open(ex) if l.strip() and not l.startswith('#')}
lines = [l for l in open(m) if l.split()[0].lower() not in bad]
open(m, 'w').writelines(lines)
PY
# apply hand-found names
python3 -I - "$M" projects/wiiplay/MAP_manual.txt <<'PY'
import sys
m, man = sys.argv[1], sys.argv[2]
names = {}
for l in open(man):
    l = l.split('#', 1)[0].split()
    if len(l) >= 2:
        names[int(l[0], 16)] = l[1]
rows = {int(a, 16): n.strip() for a, n in (l.split(maxsplit=1) for l in open(m) if l.strip())}
rows.update(names)
open(m, 'w').writelines(f'{a:08x} {n}\n' for a, n in sorted(rows.items()))
PY
python3 -I scripts/override_coverage.py $REF $M $RT | head -1
