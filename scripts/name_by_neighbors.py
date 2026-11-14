#!/usr/bin/env python3
"""Name functions by link-order alignment against a reference game's map.

SDK libraries are linked object-by-object in the same order in every game, so
between two functions named in both maps ("anchors"), the reference and the
target usually contain the same number of functions in the same order. When
the counts match, the reference names are copied across.

Wanted names may also come from the reference runtime's override macros
(e.g. ``PPC_NATIVE_OVERRIDE_VOID(80417108, DCInvalidateRange_801a1600, ...)``),
which name addresses the reference map leaves as fn_XXXXXXXX.

Usage: name_by_neighbors.py REF_MAP.txt TARGET_MAP.txt [runtime/src] [--apply]
"""
import glob
import re
import sys
from collections import Counter

MACRO = re.compile(r'^\s*[A-Z_]*(?:NATIVE_OVERRIDE(?:_VOID)?|_HLE|REGISTER_NATIVE_FUNCTION(?:_AS)?)'
                   r'\(\s*(?:0x)?([0-9A-Fa-f]{8})\s*,\s*([A-Za-z_]\w*)', re.M)
SDK = re.compile(r'^_*(?:OS|GX|VI|SC|PAD|SI|EXI|DVD|NAND|ISFS|IPC|IOS|WPAD|KPAD|WUD|AX|AI|DSP|AR|ARQ|CARD|'
                 r'MTX|PS|C_|TPL|ENC|NWC24|SO|ARC|MEM|HBM|RFL|DB|DC|IC|LC|PPC|__|WENC|VF|SYS)')


def clean(name):
    name = re.sub(r'_HLE(_\w+)?$', '', name)
    name = re.sub(r'_[0-9A-Fa-f]{8}$', '', name)
    name = re.sub(r'_WiiPlay$', '', name)  # Wii Play-specific natives keep their SDK name
    # MKW-style "LIB__Name" (GX__SetVtxDescv, OS__JamMessage, KPAD__Read) -> SDK "LIBName"
    name = re.sub(r'^(GX|OS|VI|SC|PAD|KPAD|WPAD|DVD|NAND|AI|AX|DSP|SI|EXI|IPC|MEM|TPL)__', r'\1', name)
    return name


def load(path):
    out = []
    for l in open(path):
        p = l.split(maxsplit=1)
        if len(p) == 2:
            out.append([int(p[0], 16), p[1].strip()])
    return out


def main(ref_path, tgt_path, runtime_src=None, apply=False):
    ref, tgt = load(ref_path), load(tgt_path)
    if runtime_src:  # enrich reference names from override macros
        idx = {a: i for i, (a, _) in enumerate(ref)}
        for f in glob.glob(f'{runtime_src}/**/*.cpp', recursive=True):
            for m in MACRO.finditer(open(f, errors='ignore').read()):
                a, n = int(m.group(1), 16), clean(m.group(2))
                if a in idx and ref[idx[a]][1].startswith('fn_') and SDK.match(n):
                    ref[idx[a]][1] = n
    named = lambda n: not n.startswith('fn_')
    rc = Counter(n for _, n in ref if named(n))
    tc = Counter(n for _, n in tgt if named(n))
    rpos = {n: i for i, (_, n) in enumerate(ref) if rc[n] == 1}
    tpos = {n: i for i, (_, n) in enumerate(tgt) if tc[n] == 1}
    anchors = sorted((rpos[n], tpos[n]) for n in rpos.keys() & tpos.keys())
    # longest chain whose order agrees in both maps (LIS on target index)
    from bisect import bisect_left
    tails, tails_idx, prev = [], [], [-1] * len(anchors)
    for i, (_, t) in enumerate(anchors):
        j = bisect_left(tails, t)
        if j == len(tails):
            tails.append(t); tails_idx.append(i)
        else:
            tails[j] = t; tails_idx[j] = i
        prev[i] = tails_idx[j - 1] if j else -1
    chain, i = [], tails_idx[-1] if tails_idx else -1
    while i != -1:
        chain.append(anchors[i]); i = prev[i]
    chain.reverse()
    # Between consecutive anchors whose byte spans are identical, the code layout matches:
    # copy every reference function start (and SDK name) at the same offset.
    tmap = {a: n for a, n in tgt}
    new_starts, new_names = 0, {}
    for (r0, t0), (r1, t1) in zip(chain, chain[1:]):
        ra0, ra1, ta0, ta1 = ref[r0][0], ref[r1][0], tgt[t0][0], tgt[t1][0]
        if ra1 - ra0 != ta1 - ta0 or ra1 - ra0 > 0x8000:
            continue
        for k in range(r0 + 1, r1):
            ra, rn = ref[k]
            ta = ta0 + (ra - ra0)
            if ta not in tmap:
                tmap[ta] = f'fn_{ta:08X}'
                new_starts += 1
            if named(rn) and not named(tmap[ta]) and rn not in tc and SDK.match(rn):
                new_names[ta] = rn
    dup = Counter(new_names.values())
    new_names = {a: n for a, n in new_names.items() if dup[n] == 1}
    tmap.update(new_names)
    print(f'{len(chain)} anchors, {new_starts} new function starts, {len(new_names)} new names')
    if apply:
        with open(tgt_path, 'w') as f:
            for a in sorted(tmap):
                f.write(f'{a:08x} {tmap[a]}\n')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--apply']
    main(*args[:3], apply='--apply' in sys.argv)
