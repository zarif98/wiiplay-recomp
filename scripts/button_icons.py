"""Installs the per-controller button icons into UserData/button_icons (standard library only).

assets/button_icons/<style>/ holds original art (scripts/make_button_icons.py draws it):
  - tex1_*.png pictures, copied as they are;
  - glyphs_<sheet>.png + glyphs.json, button glyphs for some cells of the game's button font. The
    font's sheets come from the player's own disc (Font/font.carc), are decoded here, get those
    cells replaced, and are written out as the texture replacements the runtime looks up. That way
    no game data is kept in the repository.
"""
import json
import shutil
import struct
import zlib
from pathlib import Path

# The texture each font sheet becomes in RAM, as the runtime names it (tex1_<w>x<h>_<hash>_<format>).
SHEET_TEXTURES = {
    24: 'tex1_512x32_90aa0228642d19ed_0',
    25: 'tex1_512x32_9c2db8962cc032b3_0',
}


def yaz0(data):
    size = struct.unpack_from('>I', data, 4)[0]
    out = bytearray()
    src = 16
    while len(out) < size:
        code = data[src]
        src += 1
        for bit in range(8):
            if len(out) >= size:
                break
            if code & (0x80 >> bit):
                out.append(data[src])
                src += 1
            else:
                b1, b2 = data[src], data[src + 1]
                src += 2
                dist = ((b1 & 15) << 8 | b2) + 1
                length = b1 >> 4
                if length == 0:
                    length = data[src] + 0x12
                    src += 1
                else:
                    length += 2
                for _ in range(length):
                    out.append(out[-dist])
    return bytes(out)


def u8_files(data):
    root = struct.unpack_from('>I', data, 4)[0]
    count = struct.unpack_from('>I', data, root + 8)[0]
    names = root + count * 12
    for i in range(1, count):
        entry = root + i * 12
        name_off = struct.unpack_from('>I', data, entry)[0] & 0xFFFFFF
        off, size = struct.unpack_from('>II', data, entry + 4)
        if data[entry] == 0:
            name = data[names + name_off:data.index(b'\0', names + name_off)].decode('latin-1')
            yield name, data[off:off + size]


def rfnt_sheets(font):
    """(width, height, raw bytes) of each glyph sheet of an I4 BRFNT."""
    pos = struct.unpack_from('>H', font, 0xC)[0]
    while pos < len(font):
        magic, length = font[pos:pos + 4], struct.unpack_from('>I', font, pos + 4)[0]
        if magic == b'TGLP':
            sheet_size = struct.unpack_from('>I', font, pos + 12)[0]
            count, fmt, _, _, width, height = struct.unpack_from('>HHHHHH', font, pos + 16)
            data_off = struct.unpack_from('>I', font, pos + 28)[0]
            if fmt != 0:
                raise ValueError('expected an I4 font')
            return [(width, height, font[data_off + i * sheet_size:data_off + (i + 1) * sheet_size])
                    for i in range(count)]
        pos += length
    raise ValueError('no TGLP section')


def decode_i4(width, height, raw):
    px = bytearray(width * height)
    i = 0
    for ty in range(0, height, 8):
        for tx in range(0, width, 8):
            for y in range(8):
                for x in range(0, 8, 2):
                    v = raw[i]
                    i += 1
                    px[(ty + y) * width + tx + x] = (v >> 4) * 17
                    px[(ty + y) * width + tx + x + 1] = (v & 15) * 17
    return px


def read_png(path):
    """8-bit grey+alpha or RGBA PNG (what make_icons.py writes) -> (width, height, channels, bytes)."""
    data = Path(path).read_bytes()
    pos, idat, width = 8, b'', 0
    while pos < len(data):
        length, kind = struct.unpack_from('>I4s', data, pos)
        body = data[pos + 8:pos + 8 + length]
        if kind == b'IHDR':
            width, height, depth, color = struct.unpack_from('>IIBB', body)
            if depth != 8 or color not in (4, 6):
                raise ValueError(f'{path}: unsupported PNG layout')
            channels = 2 if color == 4 else 4
        elif kind == b'IDAT':
            idat += body
        pos += 12 + length
    raw = zlib.decompress(idat)
    stride = width * channels
    out = bytearray(stride * height)
    prev = bytearray(stride)
    for y in range(height):
        kind = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for x in range(stride):
            a = line[x - channels] if x >= channels else 0
            b = prev[x]
            c = prev[x - channels] if x >= channels else 0
            if kind == 1:
                line[x] = (line[x] + a) & 255
            elif kind == 2:
                line[x] = (line[x] + b) & 255
            elif kind == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif kind == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return width, height, channels, out


def write_png_rgba(path, width, height, rgba):
    raw = b''.join(b'\0' + bytes(rgba[y * width * 4:(y + 1) * width * 4]) for y in range(height))

    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xFFFFFFFF)

    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def install(root, user_dir, log=print):
    assets = Path(root) / 'assets' / 'button_icons'
    if not assets.is_dir():
        return
    font_carc = next(iter(sorted((Path(root) / 'extracted').glob('**/Font/font.carc'))), None)
    sheets = None
    if font_carc is not None:
        for name, data in u8_files(yaz0(font_carc.read_bytes())):
            if name == 'pac_nRodDb_32_I4.brfnt':
                sheets = rfnt_sheets(data)
    if sheets is None:
        log('button icons: Font/font.carc not found in extracted/, installing pictures only')

    for style_dir in sorted(p for p in assets.iterdir() if p.is_dir()):
        dest = Path(user_dir) / 'button_icons' / style_dir.name
        dest.mkdir(parents=True, exist_ok=True)
        for picture in style_dir.glob('tex1_*.png'):
            shutil.copyfile(picture, dest / picture.name)
        manifest = style_dir / 'glyphs.json'
        if sheets is None or not manifest.exists():
            continue
        info = json.loads(manifest.read_text())
        cell_w = info['cell_width']
        for sheet_text, cells in info['cells'].items():
            sheet = int(sheet_text)
            width, height, raw = sheets[sheet]
            base = decode_i4(width, height, raw)
            gw, gh, ch, glyphs = read_png(style_dir / f'glyphs_{sheet}.png')
            assert (gw, gh) == (width, height), 'glyph strip must match the font sheet'
            for cell in cells:  # the new glyph's coverage replaces the cell outright
                for y in range(height):
                    for x in range(cell * cell_w, min(width, (cell + 1) * cell_w)):
                        i = y * width + x
                        base[i] = glyphs[i * ch + ch - 1]
            rgba = bytearray()
            for v in base:  # I4 reads as (I, I, I, I)
                rgba += bytes((v, v, v, v))
            write_png_rgba(dest / f'{SHEET_TEXTURES[sheet]}.png', width, height, rgba)
    log(f'button icons installed into {Path(user_dir) / "button_icons"}')
