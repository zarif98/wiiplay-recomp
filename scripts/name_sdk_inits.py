#!/usr/bin/env python3
"""Name SDK <LIB>Init functions via their version-string registration.

Each RVL_SDK library's init stores or registers "<< RVL_SDK - LIB ... >>".
The string's address lives in a pointer variable (__LIBVersion) or is built
directly with lis/addi. Any function referencing either one is reported; a
function that is the *only* referrer and still unnamed is named <LIB>Init.

Usage: name_sdk_inits.py main.dol MAP.txt [--apply]
"""
import re
import struct
import sys
from bisect import bisect_right

SDA = {13: 0x80442AC0, 2: 0x80444B00}


def main(dol, map_path, apply=False):
    d = open(dol, 'rb').read()
    u = lambda o: struct.unpack('>I', d[o:o + 4])[0]
    secs = [(u(i * 4), u(0x48 + i * 4), u(0x90 + i * 4), i < 7) for i in range(18) if u(0x90 + i * 4)]
    f2a = lambda o: next((a + o - off for off, a, sz, _ in secs if off <= o < off + sz), None)
    words = {}
    for off, addr, size, is_text in secs:
        for k in range(0, size, 4):
            words[addr + k] = (u(off + k), is_text)

    entries = [l.split(maxsplit=1) for l in open(map_path) if l.strip()]
    starts = [int(a, 16) for a, _ in entries]
    owner = lambda a: entries[bisect_right(starts, a) - 1] if a >= starts[0] else None

    libs = {}
    for m in re.finditer(rb'<< RVL_SDK - (\w+)', d):
        a = f2a(m.start())
        if a is not None:
            libs[m.group(1).decode()] = a

    renames = {}
    for lib, sa in sorted(libs.items()):
        targets = {sa} | {a for a, (w, t) in words.items() if not t and w == sa}  # string + pointer vars
        refs = set()
        hi = {}
        for a, (w, t) in sorted(words.items()):
            if not t:
                continue
            op, rd, ra, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
            simm = imm - 0x10000 if imm & 0x8000 else imm
            if op == 15 and ra == 0:
                hi[rd] = imm << 16
            elif op in (14, 32, 36) and ra in hi:  # addi / lwz / stw off(lis-reg)
                if ((hi[ra] + simm) & 0xFFFFFFFF) in targets:
                    refs.add(a)
            elif op in (14, 32, 36) and ra in SDA:
                if ((SDA[ra] + simm) & 0xFFFFFFFF) in targets:
                    refs.add(a)
        fns = sorted({tuple(owner(r)) for r in refs if owner(r)})
        print(f'{lib:6} string@{sa:08x}: ' + ', '.join(f'{a} {n.strip()}' for a, n in fns))
        if len(fns) == 1 and fns[0][1].startswith('fn_'):
            renames[fns[0][0]] = f'{lib}Init'

    if apply:
        with open(map_path, 'w') as f:
            for a, n in entries:
                f.write(f'{a} {renames.get(a, n.strip())}\n')
        print(f'named {len(renames)}: ' + ', '.join(sorted(renames.values())))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], '--apply' in sys.argv)
