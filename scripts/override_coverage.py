#!/usr/bin/env python3
"""Report which runtime overrides (written against Wario Land addresses) can be
retargeted to Wii Play through SDK names.

Usage: override_coverage.py REF_MAP.txt TARGET_MAP.txt runtime/src [--missing]
"""
import collections
import glob
import re
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from name_by_neighbors import MACRO, clean, load  # noqa: E402


def resolve(ref_map, tgt_map, runtime_src):
    ref = {a: n for a, n in load(ref_map)}
    tgt = collections.defaultdict(list)
    for a, n in load(tgt_map):
        tgt[n].append(a)
    rows = []
    for f in sorted(glob.glob(f'{runtime_src}/**/*.cpp', recursive=True)):
        for m in MACRO.finditer(open(f, errors='ignore').read()):
            a, macro_name = int(m.group(1), 16), m.group(2)
            name = ref.get(a, '')
            if not name or name.startswith('fn_'):
                name = clean(macro_name)
            hits = tgt.get(name, [])
            rows.append((f, a, name, hits[0] if len(hits) == 1 else None))
    return rows


if __name__ == '__main__':
    rows = resolve(*sys.argv[1:4])
    ok = sum(1 for r in rows if r[3] is not None)
    print(f'{ok} / {len(rows)} overrides resolve to a Wii Play address')
    by_file = collections.Counter(r[0].split('src/', 1)[1] for r in rows if r[3] is None)
    print('unresolved by file:', by_file.most_common(12))
    if '--missing' in sys.argv:
        for f, a, n, _ in rows:
            if _ is None:
                print(f'  {a:08x} {n}  ({f.split("src/", 1)[1]})')
