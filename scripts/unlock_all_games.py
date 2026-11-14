#!/usr/bin/env python3
"""Unlock all nine Wii Play games in the runtime's save (RPParty.dat).

Save layout (from the writer at 0x8018A3B0): "RPPT0000", a 32-byte global block, 100 per-Mii records,
then a checksum word at 0x50A0 = (sum of u16 words) << 16 | (sum of ~u16 words) & 0xFFFF over 0..0x50A0.
The global block's two game bitmasks (object +0x18 / +0x1C, file 0x20 / 0x24; tested by 0x8018B890 /
0x8018B840) hold one bit per game; 0x1FF = all nine, Tanks! included.

Usage: unlock_all_games.py [path/to/RPParty.dat]   (backs the file up to RPParty.dat.bak first)
"""
import shutil
import struct
import sys

DEFAULT = 'build/native/UserData/NAND/title/00010000/52484145/data/RPParty.dat'


def checksum(b):
    s = n = 0
    for (h,) in struct.iter_unpack('>H', b):
        s = (s + h) & 0xFFFFFFFF
        n = (n + (~h & 0xFFFF)) & 0xFFFF
    return ((s << 16) | n) & 0xFFFFFFFF


def main(path=DEFAULT):
    d = bytearray(open(path, 'rb').read())
    if d[:8] != b'RPPT0000':
        sys.exit(f'{path}: not a Wii Play save')
    shutil.copy2(path, path + '.bak')
    struct.pack_into('>I', d, 0x20, 0x1FF)
    struct.pack_into('>I', d, 0x24, 0x1FF)
    struct.pack_into('>I', d, 0x50A0, checksum(bytes(d[:0x50A0])))
    open(path, 'wb').write(d)
    print(f'unlocked all games in {path} (backup: {path}.bak)')


if __name__ == '__main__':
    main(*sys.argv[1:2])
