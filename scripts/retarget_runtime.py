#!/usr/bin/env python3
"""Retarget the runtime's native overrides from Wario Land addresses to Wii Play.

For every override macro (PPC_NATIVE_OVERRIDE*, *_HLE, REGISTER_NATIVE_FUNCTION*)
the SDK name is resolved from, in order: the reference map, a trailing
``// Name`` comment on the macro's last line, the macro's function name.
The name is then looked up in the Wii Play map.

  * resolved   -> the address argument becomes the Wii Play address
  * unresolved -> it becomes a parking address (0x817Fxxxx, outside game code)
                  so it can never replace an unrelated Wii Play function

``func_<old>`` identifiers elsewhere in the runtime are renamed to match.
Every decision is written to projects/wiiplay/runtime_retarget.tsv.
Re-running is safe: the original Wario addresses are recovered from that table.

Usage: retarget_runtime.py REF_MAP.txt TARGET_MAP.txt runtime/src TABLE.tsv
"""
import collections
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from name_by_neighbors import MACRO, clean, load  # noqa: E402

PARK_BASE = 0x817F0000
COMMENT = re.compile(r'//\s*([A-Za-z_]\w*)')
# func_<addr> symbols and hard-coded guest calls such as InvokeIndirectCpu(0x8040759Cu, ctx)
CALL = re.compile(r'(?:\bfunc_|\bInvokeIndirectCpu\(\s*0x|\bInvokeDirectCpu<\s*0x|->lr\s*=\s*0x)([0-9A-Fa-f]{8})(?![0-9A-Fa-f])')
GENERIC = re.compile(r'(Stub|Nop|Noop|Generic|Maintenance)', re.I)


def main(ref_map, tgt_map, runtime_src, table):
    ref = {a: n for a, n in load(ref_map)}
    tgt = collections.defaultdict(list)
    for a, n in load(tgt_map):
        tgt[n].append(a)

    # undo a previous run so the script is idempotent
    previous = {}
    if os.path.exists(table):
        for l in list(open(table))[1:]:
            f, orig, name, new = l.rstrip('\n').split('\t')
            previous[int(new, 16)] = int(orig, 16)

    files = sorted(glob.glob(f'{runtime_src}/**/*.cpp', recursive=True) +
                   glob.glob(f'{runtime_src}/**/*.h', recursive=True))
    renames = {}  # old addr -> new addr (global across files: func_<addr> is a global symbol)
    rows = []
    park = PARK_BASE
    for f in files:
        src = open(f, errors='ignore').read()
        for m in MACRO.finditer(src):
            cur = int(m.group(1), 16)
            orig = previous.get(cur, cur)
            stmt_end = src.find(';', m.end())
            line_end = src.find('\n', stmt_end if stmt_end != -1 else m.end())
            tail = src[stmt_end:line_end] if stmt_end != -1 else ''
            name = ref.get(orig, '')
            if not name or name.startswith('fn_'):
                cm = COMMENT.search(tail)
                macro_name = clean(m.group(2))
                name = cm.group(1) if cm and GENERIC.search(macro_name) else macro_name
            hits = tgt.get(name, [])
            if len(hits) == 1:
                new = hits[0]
            elif cur in renames:
                new = renames[cur]
            else:
                new, park = park, park + 4
            renames[cur] = new
            rows.append((os.path.relpath(f, runtime_src), orig, name, cur))

    # one address per symbol: two different overrides must not land on the same Wii Play function
    seen = collections.Counter(n for n in renames.values() if n < PARK_BASE)
    clash = {a for a, c in seen.items() if c > 1}
    for old, new in list(renames.items()):
        if new in clash:
            renames[old], park = park, park + 4
    rows = [(f, o, n, renames[c]) for f, o, n, c in rows]

    # direct calls from native code into translated functions (func_<addr> outside macros)
    direct = 0
    for f in files:
        for m in re.finditer(CALL, open(f, errors='ignore').read()):
            cur = int(m.group(1), 16)
            if cur in renames:
                continue
            orig = previous.get(cur, cur)
            name = ref.get(orig, '')
            hits = tgt.get(name, []) if name and not name.startswith('fn_') else []
            if len(hits) == 1:
                renames[cur] = hits[0]
                rows.append(('direct-call', orig, name, hits[0]))
                direct += 1
    print(f'{direct} direct calls retargeted')

    for f in files:
        src = open(f, errors='ignore').read()
        out = MACRO.sub(lambda m: m.group(0).replace(m.group(1), fmt(renames[int(m.group(1), 16)], m.group(1)), 1), src)
        out = CALL.sub(lambda m: m.group(0).replace(m.group(1), fmt(renames[int(m.group(1), 16)], m.group(1)), 1)
                       if int(m.group(1), 16) in renames else m.group(0), out)
        if out != src:
            open(f, 'w').write(out)

    # The Wario port disabled overrides it had no address for with "#if 0 /* WARIO-TODO ... */".
    # Re-enable the ones that now resolve to a Wii Play function; still-parked ones stay off.
    todo = re.compile(r'#if 0 /\* WARIO-TODO[^\n]*\n(.*?)\n#endif\n', re.S)
    enabled = 0
    for f in files:
        src = open(f, errors='ignore').read()

        def unwrap(m):
            nonlocal enabled
            ms = list(MACRO.finditer('\n' + m.group(1)))
            if len(ms) == 1 and int(ms[0].group(1), 16) < PARK_BASE:
                enabled += 1
                return '/* WII PLAY: re-enabled (resolved by retarget_runtime.py) */\n' + m.group(1) + '\n'
            return m.group(0)
        out = todo.sub(unwrap, src)
        if out != src:
            open(f, 'w').write(out)
    print(f'{enabled} WARIO-TODO overrides re-enabled')

    with open(table, 'w') as t:
        t.write('file\twario_addr\tname\twiiplay_addr\n')
        for f, o, n, new in rows:
            t.write(f'{f}\t{o:08X}\t{n}\t{new:08X}\n')
    ok = sum(1 for r in rows if r[3] < PARK_BASE)
    print(f'{ok} / {len(rows)} overrides retargeted, {len(rows) - ok} parked at 0x817Fxxxx; '
          f'{len(clash)} address clashes parked')


def fmt(addr, _like):
    return f'{addr:08X}'  # translated functions are emitted as func_XXXXXXXX (upper case)


if __name__ == '__main__':
    main(*sys.argv[1:5])
