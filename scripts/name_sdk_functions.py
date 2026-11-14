#!/usr/bin/env python3
"""Name SDK functions in a function map using Dolphin's signature database.

Reimplements Dolphin's HashSignatureDB::ComputeCodeChecksum and reads a DSY
file (u32 count, then {u32 checksum, u32 size, char name[128]}, little endian).
A map entry is renamed only when its (checksum, size) matches exactly one name.

Usage: name_sdk_functions.py main.dol MAP.txt totaldb.dsy [out MAP.txt]
"""
import struct
import sys
from collections import defaultdict


def checksum(words):
    s = 0
    for w in words:
        s = checksum_step(s, w)
    return s


def checksum_step(s, w):
    op = w & 0xFC000000
    aux = op >> 26
    op2 = op3 = 0
    if aux == 4:
        op2 = w & 0x3F
        if op2 in (0, 8, 16, 21, 22):
            op3 = w & 0x7C0
    elif aux in (7, 8, 10, 11, 12, 13, 14, 15):
        op2 = w & 0x03FF0000
    elif aux in (19, 31, 63):
        op2 = w & 0x7FF
    elif aux == 59:
        op2 = w & 0x3F
        if op2 < 16:
            op3 = w & 0x7C0
    elif 32 <= aux < 56:
        op2 = w & 0x03FF0000
    s = ((s << 17) & 0xFFFE0000) | ((s >> 15) & 0x1FFFF)
    s ^= op | op2 | op3
    return s


def main(dol, map_path, dsy, out=None):
    d = open(dol, 'rb').read()
    u = lambda o: struct.unpack('>I', d[o:o + 4])[0]
    words = {}
    for i in range(7):
        off, addr, size = u(i * 4), u(0x48 + i * 4), u(0x90 + i * 4)
        for k in range(0, size, 4):
            words[addr + k] = u(off + k)

    db = defaultdict(set)
    raw = open(dsy, 'rb').read()
    (count,) = struct.unpack_from('<I', raw, 0)
    for i in range(count):
        cs, size, name = struct.unpack_from('<II128s', raw, 4 + i * 136)
        db[(cs, size)].add(name.split(b'\0', 1)[0].decode('latin-1').split('\t')[0].strip())

    entries = [l.split(maxsplit=1) for l in open(map_path) if l.strip()]
    starts = [int(a, 16) for a, _ in entries]
    MIN_WORDS = int(__import__("os").environ.get("MIN_WORDS", 3))  # tiny getters/setters collide across libraries
    proposed = {}
    BLR = 0x4E800020
    MAX_SPAN = 6  # map entries a signature may span (switch-case blocks split off by the map)
    for idx, (a, name) in enumerate(entries):
        if not name.startswith('fn_'):
            continue
        start = starts[idx]
        # Span the following unnamed entries too, and test the signature at every blr: the map
        # can split a function at its jump-table cases, or merge it with a neighbour.
        last = idx
        while last + 1 < len(entries) and last - idx < MAX_SPAN and entries[last + 1][1].startswith('fn_'):
            last += 1
        end = starts[last + 1] if last + 1 < len(starts) else start + 4
        hits = set()
        s = 0
        for k, x in enumerate(range(start, end, 4)):
            w = words.get(x, 0)
            s = checksum_step(s, w)
            if w == BLR and k + 1 >= MIN_WORDS:
                hit = db.get((s, (k + 1) * 4))
                if hit and len(hit) == 1:
                    hits.add(next(iter(hit)))
        if len(hits) == 1:
            proposed[idx] = next(iter(hits))
    uses = defaultdict(int)
    for n in proposed.values():
        uses[n] += 1
    named = 0
    out_lines = []
    for idx, (a, name) in enumerate(entries):
        if idx in proposed and uses[proposed[idx]] == 1:
            name = proposed[idx]
            named += 1
        out_lines.append(f'{a} {name.strip()}\n')
    open(out or map_path, 'w').writelines(out_lines)
    print(f'{named} of {len(entries)} functions named from {count} signatures')


if __name__ == '__main__':
    main(*sys.argv[1:5])
