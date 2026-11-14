#!/usr/bin/env python3
"""Build a WiiCompiled function map (``ADDR name`` per line) for a Wii DOL.

Function starts are collected from:
  * the DOL entry point and every ``bl`` target in the text sections;
  * 4-byte words in the data sections that point into text (vtables,
    callback tables) when the target looks like a function boundary;
  * the instruction after a ``blr``/``bctr``/``rfi`` (or padding) that opens
    with a typical prologue (``stwu r1,-N(r1)`` or ``mflr r0``).

CodeWarrior register save/restore thunks are detected by pattern and named
``_save_gpr_N`` / ``_rest_gpr_N`` / ``_save_fpr_N`` / ``_rest_fpr_N`` so the
translator can recognise them.

Usage: make_function_map.py main.dol out/MAP.txt
"""
import struct
import sys

BLR, BCTR, RFI = 0x4E800020, 0x4E800420, 0x4C000064


def load(path):
    d = open(path, 'rb').read()
    u = lambda o: struct.unpack('>I', d[o:o + 4])[0]
    text, data = [], []
    for i in range(18):
        off, addr, size = u(i * 4), u(0x48 + i * 4), u(0x90 + i * 4)
        if size:
            (text if i < 7 else data).append((off, addr, size))
    return d, text, data, u(0xE0)


def main(dol_path, out_path):
    d, text, data, entry = load(dol_path)
    words = {}
    for off, addr, size in text:
        for k in range(0, size, 4):
            words[addr + k] = struct.unpack('>I', d[off + k:off + k + 4])[0]
    in_text = lambda a: a in words

    def is_prologue(a):
        w = words.get(a, 0)
        return (w & 0xFFFF0000) == 0x94210000 or w == 0x7C0802A6  # stwu r1,-N(r1) / mflr r0

    def follows_end(a):
        p = words.get(a - 4)
        return p is None or p in (BLR, BCTR, RFI, 0)

    starts = {entry}
    # bl targets
    for a, w in words.items():
        if w >> 26 == 18 and (w & 3) == 1:
            li = w & 0x03FFFFFC
            if li & 0x02000000:
                li -= 0x04000000
            t = (a + li) & 0xFFFFFFFF
            if in_text(t):
                starts.add(t)
    # C++ this-adjusting thunks: "addi r3,r3,imm ; b target", packed back to back
    def is_thunk(a):
        w0, w1 = words.get(a, 0), words.get(a + 4, 0)
        return (w0 >> 16) == 0x3863 and (w1 >> 26) == 18 and (w1 & 3) == 0
    def follows_branch(a):
        p = words.get(a - 4, 0)
        return (p >> 26) == 18 and (p & 1) == 0
    for a in words:
        if is_thunk(a) and (follows_end(a) or follows_branch(a)):
            starts.add(a)
    # pointers from data (vtables etc.), filtered to plausible boundaries
    for off, addr, size in data:
        for k in range(0, size - 3, 4):
            t = struct.unpack('>I', d[off + k:off + k + 4])[0]
            if t & 3 == 0 and in_text(t) and (follows_end(t) or is_prologue(t)):
                starts.add(t)
    # code addresses built with lis/addi (callbacks passed by pointer) at a function boundary
    hi = {}
    for a in sorted(words):
        w = words[a]
        op, rd, ra, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if op == 15 and ra == 0:
            hi[rd] = imm << 16
        elif op == 14 and ra in hi:
            t = (hi[ra] + (imm - 0x10000 if imm & 0x8000 else imm)) & 0xFFFFFFFF
            if in_text(t) and t & 3 == 0 and (follows_end(t) or is_prologue(t)):
                starts.add(t)
        elif w in (BLR, BCTR, RFI):
            hi.clear()
    # pure function-pointer tables (_ctors/_dtors): every entry is a function start
    for off, addr, size in data:
        vals = [struct.unpack('>I', d[off + k:off + k + 4])[0] for k in range(0, size - 3, 4)]
        ptrs = [t for t in vals if t]
        if ptrs and all(in_text(t) and t & 3 == 0 for t in ptrs):
            starts.update(ptrs)
    # prologue after a function end
    for a in words:
        if follows_end(a) and is_prologue(a):
            starts.add(a)

    # C++ vtables: runs of text pointers in data where most entries are already known starts.
    # (Switch jump tables point inside one function and contain no known starts, so they are skipped.)
    for _ in range(3):
        for off, addr, size in data:
            run = []
            for k in range(0, size - 3, 4):
                t = struct.unpack('>I', d[off + k:off + k + 4])[0]
                if in_text(t) and t & 3 == 0:
                    run.append(t)
                    continue
                if len(run) >= 3 and sum(t in starts for t in run) * 2 >= len(run):
                    starts.update(run)
                run = []

    # C++ pointers-to-member-function {this_delta, vtbl_offset = -1, func} (called via __ptmf_scall):
    # a non-virtual member pointer's third word is always a real function start.
    for off, addr, size in data:
        for k in range(0, size - 11, 4):
            d0, d1, d2 = struct.unpack('>III', d[off + k:off + k + 12])
            if d1 == 0xFFFFFFFF and d0 < 0x10000 and in_text(d2) and d2 & 3 == 0:
                starts.add(d2)
    # Small tail-call wrappers referenced from data (allocator/callback tables): the target follows
    # a function end or tail branch and, within 4 instructions, tail-branches to a known start.
    def tail_calls_known(a):
        for i in range(4):
            w = words.get(a + 4 * i, 0)
            if (w >> 26) == 18 and (w & 3) == 0:
                li = w & 0x03FFFFFC
                if li & 0x02000000:
                    li -= 0x04000000
                return ((a + 4 * i + li) & 0xFFFFFFFF) in starts
            if w in (BLR, BCTR) or (w >> 26) in (16, 18):
                return False
        return False
    for off, addr, size in data:
        for k in range(0, size - 3, 4):
            t = struct.unpack('>I', d[off + k:off + k + 4])[0]
            if in_text(t) and t & 3 == 0 and t not in starts and \
                    (follows_end(t) or follows_branch(t)) and tail_calls_known(t):
                starts.add(t)

    names = {}
    # CodeWarrior save/restore thunks: runs of stw/lwz rN,-X(r11) and stfd/lfd fN,-X(r11)
    for a in sorted(words):
        for prefix, op, lo in (('_save_gpr_', 36, 14), ('_rest_gpr_', 32, 14),
                               ('_save_fpr_', 54, 14), ('_rest_fpr_', 50, 14)):
            regs = []
            b = a
            while True:
                w = words.get(b, 0)
                if w >> 26 != op or (w >> 16) & 31 != 11:
                    break
                regs.append((w >> 21) & 31)
                b += 4
            if len(regs) == 32 - lo and regs == list(range(lo, 32)) and words.get(b) == BLR \
                    and (words.get(a - 4, 0) >> 26) != op:
                for i, r in enumerate(regs):
                    names[a + 4 * i] = f'{prefix}{r}'
                    starts.add(a + 4 * i)

    # drop padding and embedded strings (e.g. the TRK banner in the first text section)
    def is_text_blob(a):
        bs = b''.join(struct.pack('>I', words.get(a + 4 * i, 0)) for i in range(2))
        return all(32 <= c < 127 for c in bs)
    starts = {s for s in starts if words.get(s, 0) != 0 and not is_text_blob(s)}
    with open(out_path, 'w') as f:
        for s in sorted(starts):
            f.write(f'{s:08x} {names.get(s, f"fn_{s:08X}")}\n')
    print(f'{len(starts)} functions, {len(names)} named thunks -> {out_path}')


if __name__ == '__main__':
    main(*sys.argv[1:3])
