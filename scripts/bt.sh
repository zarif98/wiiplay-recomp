#!/bin/zsh
# Start the game, wait N seconds (default 15), print the main thread's guest call chain.
cd "$(dirname "$0")/.."
(cd build/native && perl -e 'alarm 60; exec @ARGV' ./WiiCompiled > ../run.log 2>&1 &)
perl -e "select(undef,undef,undef,${1:-15})"
pid=$(pgrep -n WiiCompiled)
lldb -p $pid --batch -o 'thread backtrace 1 -c 40' > build/bt.txt 2>&1
kill $pid 2>/dev/null
python3 -I - <<'PY'
import re
from bisect import bisect_right
L=[l.split(maxsplit=1) for l in open('projects/wiiplay/MAP.txt')]
S=[int(a,16) for a,_ in L]
for line in open('build/bt.txt'):
    m=re.search(r'frame #(\d+): \S+ (?:WiiCompiled`)?(.*?)(?: at |$)', line)
    if not m: continue
    f=m.group(2).strip()
    g=re.search(r'func_([0-9A-F]{8})', f) or re.search(r'Static<(\d+)u>', f)
    if g:
        a=int(g.group(1),16) if 'func_' in f else int(g.group(1))
        i=bisect_right(S,a)-1
        print(f'#{m.group(1):>2} 0x{a:08X} {L[i][1].strip()}' + ('' if 'func_' in f else '   (dispatch)'))
    else:
        print(f'#{m.group(1):>2} {f[:90]}')
PY
