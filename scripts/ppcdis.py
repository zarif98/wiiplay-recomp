#!/usr/bin/env python3
"""Tiny PowerPC disassembler for reading SDK functions in a DOL.

Decodes the instructions that matter when porting runtime HLE code: loads and
stores (with r13/r2 small-data addresses resolved), lis/addi/ori constants,
branches with map names, compares, moves and returns. Everything else is shown
as raw hex.

Usage: ppcdis.py main.dol MAP.txt <address|name> [count]
"""
import struct
import sys
from bisect import bisect_right

SDA = {13: 0x80442AC0, 2: 0x80444B00}
LOADS = {32: 'lwz', 33: 'lwzu', 34: 'lbz', 35: 'lbzu', 40: 'lhz', 42: 'lha', 48: 'lfs', 50: 'lfd'}
STORES = {36: 'stw', 37: 'stwu', 38: 'stb', 44: 'sth', 52: 'stfs', 54: 'stfd'}


def main(dol, map_path, what, count='64'):
    d = open(dol, 'rb').read()
    u = lambda o: struct.unpack('>I', d[o:o + 4])[0]
    secs = [(u(i * 4), u(0x48 + i * 4), u(0x90 + i * 4)) for i in range(18) if u(0x90 + i * 4)]

    def rd(a):
        for off, ad, sz in secs:
            if ad <= a < ad + sz:
                return u(off + a - ad)

    entries = [l.split(maxsplit=1) for l in open(map_path) if l.strip()]
    starts = [int(a, 16) for a, _ in entries]
    byname = {n.strip(): int(a, 16) for a, n in entries}

    def sym(a):
        i = bisect_right(starts, a) - 1
        if i < 0:
            return f'0x{a:08X}'
        off = a - starts[i]
        n = entries[i][1].strip()
        return n if off == 0 else f'{n}+0x{off:X}'

    start = byname[what] if what in byname else int(what, 16)
    end = starts[bisect_right(starts, start)] if bisect_right(starts, start) < len(starts) else start + 4 * int(count)
    n = min(int(count), (end - start) // 4)
    for k in range(n):
        a = start + 4 * k
        w = rd(a)
        op, rt, ra, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        s = imm - 0x10000 if imm & 0x8000 else imm
        txt = f'.word 0x{w:08X}'
        if op in LOADS or op in STORES:
            mn = LOADS.get(op) or STORES.get(op)
            reg = ('f' if mn.endswith(('fs', 'fd')) else 'r') + str(rt)
            txt = f'{mn} {reg}, {s}(r{ra})'
            if ra in SDA:
                txt += f'    ; [0x{(SDA[ra] + s) & 0xFFFFFFFF:08X}] r{ra}{s:+#x}'
        elif op == 15:
            txt = f'lis r{rt}, 0x{imm:04X}' if ra == 0 else f'addis r{rt}, r{ra}, 0x{imm:04X}'
        elif op == 14:
            txt = f'li r{rt}, {s}' if ra == 0 else f'addi r{rt}, r{ra}, {s}'
            if ra in SDA:
                txt += f'    ; =0x{(SDA[ra] + s) & 0xFFFFFFFF:08X}'
        elif op == 24:
            txt = f'ori r{ra}, r{rt}, 0x{imm:04X}'
        elif op == 18:
            li = w & 0x03FFFFFC
            if li & 0x02000000:
                li -= 0x04000000
            t = (a + li) & 0xFFFFFFFF
            txt = ('bl ' if w & 1 else 'b ') + f'{sym(t)}  (0x{t:08X})'
        elif op == 16:
            bd = w & 0xFFFC
            if bd & 0x8000:
                bd -= 0x10000
            txt = f'bc {rt},{ra}, 0x{(a + bd) & 0xFFFFFFFF:08X}'
        elif op == 11:
            txt = f'cmpwi cr{rt >> 2}, r{ra}, {s}'
        elif op == 10:
            txt = f'cmplwi cr{rt >> 2}, r{ra}, {imm}'
        elif w == 0x4E800020:
            txt = 'blr'
        elif op == 31 and (w >> 1) & 0x3FF == 444 and rt == (w >> 11) & 31:
            txt = f'mr r{ra}, r{rt}'
        print(f'{a:08X}  {w:08X}  {txt}')


if __name__ == '__main__':
    main(*sys.argv[1:5])
