#!/usr/bin/env python3
"""Draws the Tanks! controller icons for Xbox, PlayStation and keyboard + mouse (needs Pillow).

Everything here is drawn from scratch to match Wii Play's look: flat line art, dark-brown outlines,
the light-blue cards of the How to Play screen and the font's outlined button glyphs. Output goes to
assets/button_icons/<style>/:

  tex1_200x160_8643ac135bf172a4_5.png  the controls picture (Nunchuk + Wii Remote), drawn at 4x
  glyphs_24.png, glyphs_25.png         button glyphs for sheets 24/25 of pac_nRodDb_32_I4.brfnt;
                                       scripts/build.py pastes the cells listed in GLYPH_CELLS onto
                                       the sheets read from the player's own disc (no game pixels
                                       are stored here)

Run after changing the art:  python3 scripts/make_button_icons.py
"""
import json
import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "assets", "button_icons")

# Wii Play's How to Play palette (sampled from the card it replaces).
CARD = (165, 222, 239, 255)
SKIN = (255, 231, 189, 255)
SKIN_SHADE = (239, 214, 181, 255)
WHITE = (255, 255, 255, 255)
LIGHT = (239, 239, 239, 255)
GREY = (214, 222, 222, 255)
MID = (165, 173, 181, 255)
DARK = (99, 99, 107, 255)
INK = (33, 24, 16, 255)

S = 4  # illustration scale (the texture is 200x160)
W, H = 200 * S, 160 * S


def font(size, bold=True):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


# ---------------------------------------------------------------------------------------------
# Shapes: each part is a filled mask plus an outline, like the original's line art.


class Layer:
    def __init__(self):
        self.mask = Image.new("L", (W, H), 0)
        self.draw = ImageDraw.Draw(self.mask)


def outline_of(mask, width):
    grown = mask.filter(ImageFilter.MaxFilter(width * 2 + 1))
    return ImageChops.subtract(grown, mask)


def paint(img, mask, fill, line=INK, width=5):
    fill_img = Image.new("RGBA", (W, H), fill)
    img.paste(fill_img, (0, 0), mask)
    if width:
        img.paste(Image.new("RGBA", (W, H), line), (0, 0), outline_of(mask, width))


def rotated_ellipse(cx, cy, rx, ry, angle):
    pts = []
    for i in range(72):
        t = 2 * math.pi * i / 72
        x, y = rx * math.cos(t), ry * math.sin(t)
        a = math.radians(angle)
        pts.append((cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)))
    return pts


def card():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, W - 1, H - 1], radius=10 * S, fill=CARD)
    return img


def text_center(draw, xy, text, size, fill=INK):
    f = font(size)
    draw.text(xy, text, font=f, fill=fill, anchor="mm")


def ring(draw, cx, cy, r, width, fill=None, line=INK):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=line, width=width)


def stick(draw, cx, cy, r):
    ring(draw, cx, cy, r, 5, fill=GREY)
    ring(draw, cx, cy, int(r * 0.66), 5, fill=WHITE)


def dpad(draw, cx, cy, arm, half):
    pts = [
        (cx - half, cy - arm), (cx + half, cy - arm), (cx + half, cy - half), (cx + arm, cy - half),
        (cx + arm, cy + half), (cx + half, cy + half), (cx + half, cy + arm), (cx - half, cy + arm),
        (cx - half, cy + half), (cx - arm, cy + half), (cx - arm, cy - half), (cx - half, cy - half),
    ]
    draw.polygon(pts, fill=WHITE, outline=INK, width=5)


def thumb(img, tip, base, width):
    """A thumb reaching from `base` to rest on `tip`, skin with an outline."""
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    d.line([base, tip], fill=255, width=width)
    r = width // 2
    d.ellipse([tip[0] - r, tip[1] - r, tip[0] + r, tip[1] + r], fill=255)
    d.ellipse([base[0] - r, base[1] - r, base[0] + r, base[1] + r], fill=255)
    paint(img, m, SKIN)


def hand(img, grip_center, angle):
    """Palm and fingers wrapped around a grip, seen from the front."""
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    cx, cy = grip_center
    d.polygon(rotated_ellipse(cx, cy, 70, 105, angle), fill=255)
    paint(img, m, SKIN)
    draw = ImageDraw.Draw(img)
    # finger creases
    a = math.radians(angle)
    for k in (-1, 0, 1):
        ox, oy = 30 * k * math.cos(a), 30 * k * math.sin(a)
        draw.arc([cx + ox - 50, cy + oy + 20, cx + ox + 50, cy + oy + 90], 200, 340, fill=INK, width=4)


def gamepad_body(img, playstation):
    """The controller from the front: wide top, two grips."""
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([170, 190, 630, 400], radius=110, fill=255)
    d.polygon(rotated_ellipse(245, 410, 85, 150, 28), fill=255)
    d.polygon(rotated_ellipse(555, 410, 85, 150, -28), fill=255)
    paint(img, m, WHITE)
    # bumpers above the body
    draw = ImageDraw.Draw(img)
    for x0 in (200, 470):
        draw.rounded_rectangle([x0, 160, x0 + 130, 200], radius=20, fill=GREY, outline=INK, width=5)
    paint(img, m, WHITE)  # body over the bumpers' lower edges
    return draw


def xbox_picture():
    img = card()
    draw = gamepad_body(img, False)
    stick(draw, 280, 270, 46)                    # left stick, high
    dpad(draw, 345, 365, 40, 14)
    stick(draw, 470, 365, 42)                    # right stick, low
    for (dx, dy, letter) in ((0, 52, "A"), (52, 0, "B"), (-52, 0, "X"), (0, -52, "Y")):
        cx, cy = 535 + dx, 268 + dy
        ring(draw, cx, cy, 25, 5, fill=WHITE)
        text_center(draw, (cx, cy + 1), letter, 32)
    ring(draw, 400, 228, 24, 5, fill=GREY)      # guide button, plain
    for cx in (360, 440):
        ring(draw, cx, 285, 11, 4, fill=WHITE)  # view / menu
    hand(img, (230, 470), 28)
    hand(img, (570, 470), -28)
    thumb(img, (280, 272), (232, 352), 42)
    thumb(img, (470, 367), (528, 430), 42)
    return img


def playstation_picture():
    img = card()
    draw = gamepad_body(img, True)
    dpad(draw, 270, 275, 42, 15)
    stick(draw, 330, 370, 42)                    # both sticks low, side by side
    stick(draw, 470, 370, 42)
    symbols = (((0, 52), "cross"), ((52, 0), "circle"), ((-52, 0), "square"), ((0, -52), "triangle"))
    for (dx, dy), sym in symbols:
        cx, cy = 530 + dx, 272 + dy
        ring(draw, cx, cy, 25, 5, fill=WHITE)
        if sym == "cross":
            draw.line([cx - 11, cy - 11, cx + 11, cy + 11], fill=INK, width=5)
            draw.line([cx - 11, cy + 11, cx + 11, cy - 11], fill=INK, width=5)
        elif sym == "circle":
            ring(draw, cx, cy, 12, 5)
        elif sym == "square":
            draw.rectangle([cx - 11, cy - 11, cx + 11, cy + 11], outline=INK, width=5)
        else:
            draw.polygon([(cx, cy - 14), (cx + 13, cy + 10), (cx - 13, cy + 10)], outline=INK, width=5)
    draw.rounded_rectangle([335, 205, 465, 290], radius=16, fill=LIGHT, outline=INK, width=5)  # touchpad
    for cx in (318, 482):
        draw.rounded_rectangle([cx - 8, 215, cx + 8, 245], radius=7, fill=WHITE, outline=INK, width=4)
    hand(img, (230, 470), 28)
    hand(img, (570, 470), -28)
    thumb(img, (330, 372), (262, 418), 42)
    thumb(img, (470, 372), (538, 418), 42)
    return img


def key(draw, box, label=None, size=38, fill=WHITE):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle([x0, y0 + 10, x1, y1 + 10], radius=14, fill=MID, outline=INK, width=5)  # side
    draw.rounded_rectangle(box, radius=14, fill=fill, outline=INK, width=5)
    if label:
        text_center(draw, ((x0 + x1) // 2, (y0 + y1) // 2 + 1), label, size)


def keyboard_picture():
    img = card()
    draw = ImageDraw.Draw(img)
    # a corner of the keyboard: a few rows, WASD and Space marked
    draw.rounded_rectangle([40, 150, 520, 560], radius=30, fill=GREY, outline=INK, width=5)
    u, gap, ox, oy = 78, 12, 70, 180
    rows = [(0, ["Esc", "", "", ""]), (u * 0.5, ["", "W", "", ""]), (u * 0.75, ["A", "S", "D", ""])]
    for r, (shift, labels) in enumerate(rows):
        for c, label in enumerate(labels):
            x0 = ox + shift + c * (u + gap)
            y0 = oy + r * (u + gap)
            accent = label in ("W", "A", "S", "D")
            key(draw, (x0, y0, x0 + u, y0 + u), label or None, 30 if len(label) > 1 else 40,
                fill=WHITE if accent else LIGHT)
    sy = oy + 3 * (u + gap)
    key(draw, (ox + u, sy, ox + u + 3 * (u + gap) + u // 2, sy + u), "Space", 30)
    # the mouse, buttons forward
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).rounded_rectangle([580, 170, 740, 450], radius=80, fill=255)
    paint(img, m, WHITE)
    draw.line([660, 175, 660, 290], fill=INK, width=5)
    draw.line([585, 290, 735, 290], fill=INK, width=5)
    draw.rounded_rectangle([648, 210, 672, 255], radius=10, fill=GREY, outline=INK, width=4)  # wheel
    # hand on the mouse: palm from below, two fingers on the buttons
    hm = Image.new("L", (W, H), 0)
    hd = ImageDraw.Draw(hm)
    hd.ellipse([570, 345, 770, 610], fill=255)
    hd.rounded_rectangle([606, 236, 654, 390], radius=24, fill=255)
    hd.rounded_rectangle([666, 236, 714, 390], radius=24, fill=255)
    paint(img, hm, SKIN)
    draw.line([660, 300, 660, 372], fill=INK, width=4)  # between the two fingers
    return img


# ---------------------------------------------------------------------------------------------
# Glyphs: 26x32 cells of the I4 button font (sheets 24 and 25), drawn at 8x and reduced, in the
# font's style: white outline, button letters in a circle, a raised base under the round buttons.

GS = 8
CELL_W, CELL_H = 26, 32
CX, CY, R = 12.5, 14.5, 11.0  # where the font's round buttons sit in a cell


def glyph_canvas():
    img = Image.new("L", (CELL_W * GS, CELL_H * GS), 0)
    return img, ImageDraw.Draw(img)


def g(v):
    return v * GS


def g_ring(d, cx, cy, r, w=1.6):
    d.ellipse([g(cx - r), g(cy - r), g(cx + r), g(cy + r)], outline=255, width=int(w * GS))


def g_base(d, cx=CX, cy=CY, r=R):
    """The raised edge the font draws under its round buttons."""
    d.arc([g(cx - r), g(cy - r + 3), g(cx + r), g(cy + r + 3)], 20, 160, fill=255, width=int(1.6 * GS))


def g_text(d, cx, cy, text, size):
    d.text((g(cx), g(cy)), text, font=font(int(size * GS)), fill=255, anchor="mm")


def g_button(letter, base=True, size=13):
    img, d = glyph_canvas()
    g_ring(d, CX, CY, R)
    if base:
        g_base(d)
    g_text(d, CX, CY + 0.5, letter, size)
    return img


def g_symbol_button(symbol, base=True):
    img, d = glyph_canvas()
    g_ring(d, CX, CY, R)
    if base:
        g_base(d)
    w = int(1.7 * GS)
    cx, cy = g(CX), g(CY)
    s = g(5)
    if symbol == "cross":
        d.line([cx - s, cy - s, cx + s, cy + s], fill=255, width=w)
        d.line([cx - s, cy + s, cx + s, cy - s], fill=255, width=w)
    elif symbol == "circle":
        d.ellipse([cx - s, cy - s, cx + s, cy + s], outline=255, width=w)
    elif symbol == "menu":
        for k in (-1, 0, 1):
            d.line([cx - s, cy + k * g(3.3), cx + s, cy + k * g(3.3)], fill=255, width=w)
    elif symbol == "view":
        d.rectangle([cx - s, cy - s * 0.4, cx + s * 0.3, cy + s * 0.8], outline=255, width=w)
        d.rectangle([cx - s * 0.3, cy - s * 0.9, cx + s, cy + s * 0.3], outline=255, width=w)
    return img


def g_stick(letter):
    """An analog stick: a ring with a cap, its letter (L / R) on the cap."""
    img, d = glyph_canvas()
    g_ring(d, CX, CY, R, 1.3)
    d.ellipse([g(CX - R + 3), g(CY - R + 2), g(CX + R - 3), g(CY + R - 4)], outline=255, width=int(1.6 * GS))
    g_text(d, CX, CY - 0.5, letter, 11)
    return img


def g_trigger(label):
    """A shoulder trigger seen from the front: a rounded tab, flat at the bottom."""
    img, d = glyph_canvas()
    d.rounded_rectangle([g(1.2), g(3), g(21.8), g(27)], radius=g(8), outline=255, width=int(1.6 * GS))
    d.line([g(2.5), g(22.5), g(20.5), g(22.5)], fill=255, width=int(1.4 * GS))
    g_text(d, 11.5, 13, label, 9.5 if len(label) > 1 else 12)
    return img


def g_key(label, size=None):
    img, d = glyph_canvas()
    d.rounded_rectangle([g(1.2), g(3), g(22.8), g(27)], radius=g(4), outline=255, width=int(1.6 * GS))
    d.line([g(3.5), g(22.5), g(20.5), g(22.5)], fill=255, width=int(1.4 * GS))
    g_text(d, 12, 12.8, label, size or (13 if len(label) == 1 else 8))
    return img


def g_space():
    img, d = glyph_canvas()
    d.rounded_rectangle([g(1), g(7), g(23), g(25)], radius=g(4), outline=255, width=int(1.6 * GS))
    w = int(1.7 * GS)
    d.line([g(6), g(13), g(6), g(18), g(18), g(18), g(18), g(13)], fill=255, width=w, joint="curve")
    return img


def g_mouse(button):
    """A mouse from above; `button` (left / right) filled, or none for "point"."""
    img, d = glyph_canvas()
    box = [g(5), g(2.5), g(20), g(27)]
    d.rounded_rectangle(box, radius=g(7.5), outline=255, width=int(1.5 * GS))
    d.line([g(5), g(12), g(20), g(12)], fill=255, width=int(1.3 * GS))
    d.line([g(12.5), g(3), g(12.5), g(12)], fill=255, width=int(1.3 * GS))
    if button == "left":
        d.pieslice([g(5), g(2.5), g(20), g(17.5)], 180, 270, fill=255)
        d.rectangle([g(5.7), g(9.9), g(12.5), g(12)], fill=255)
    elif button == "right":
        d.pieslice([g(5), g(2.5), g(20), g(17.5)], 270, 360, fill=255)
        d.rectangle([g(12.5), g(9.9), g(19.3), g(12)], fill=255)
    return img


def g_keys_cluster(top, bottom):
    """The four movement keys, one up and three below: W over ASD as bold letters, or four arrowheads
    for the arrow keys. No key outlines: at the font's size they swallowed the letters. Fits 23 px,
    the narrowest cell it goes in (the font only draws a glyph's own width)."""
    img, d = glyph_canvas()
    spots = [(11.5, 8.5)] + [(x, 21.0) for x in (4.4, 11.5, 18.6)]
    for (x, y), label in zip(spots, [top] + list(bottom)):
        if label in ("up", "left", "down", "right"):
            cx, cy, a = g(x), g(y), g(3.6)
            tri = {"up": [(cx, cy - a), (cx + a, cy + a * 0.75), (cx - a, cy + a * 0.75)],
                   "down": [(cx, cy + a), (cx + a, cy - a * 0.75), (cx - a, cy - a * 0.75)],
                   "left": [(cx - a, cy), (cx + a * 0.75, cy - a), (cx + a * 0.75, cy + a)],
                   "right": [(cx + a, cy), (cx - a * 0.75, cy - a), (cx - a * 0.75, cy + a)]}[label]
            d.polygon(tri, fill=255)
        else:
            g_text(d, x, y, label, 11)
    return img


def reduce(img):
    small = img.resize((CELL_W, CELL_H), Image.LANCZOS)
    return small.point(lambda v: min(255, (v + 8) // 17 * 17))  # I4's 16 levels


# Which cells of each sheet are redrawn, and with what, per style. Sheet 24 (cell: Wii glyph):
#   3 A (raised)  4 2 (raised)  5 B (trigger)  8 Control Stick  10 +Control Pad  11 1 (raised)
#   15 +Control Pad  16 A  17 B
# Sheet 25: 0 + (raised)  1 - (raised)  2 1 (raised)  3 2 (raised)  4 Control Stick
# In Tanks!: stick / pad = move, pointer = aim, B = fire, A = mine, + = pause.
def glyph_set(style):
    if style == "xbox":
        a, one, two = g_button("A"), g_button("B"), g_button("A")
        a_flat = g_button("A", base=False)
        fire = g_trigger("RT")
        aim, move = g_stick("R"), g_stick("L")
        plus, minus = g_symbol_button("menu"), g_symbol_button("view")
        pad = None
    elif style == "playstation":
        a, one, two = g_symbol_button("cross"), g_symbol_button("circle"), g_symbol_button("cross")
        a_flat = g_symbol_button("cross", base=False)
        fire = g_trigger("R2")
        aim, move = g_stick("R"), g_stick("L")
        plus, minus = g_symbol_button("menu"), g_symbol_button("view")
        pad = None
    else:  # keyboard + mouse
        a = a_flat = g_space()
        one, two = g_key("Z"), g_key("X")
        fire = g_mouse("left")
        aim = g_mouse(None)
        move = g_keys_cluster("W", "ASD")
        plus, minus = g_key("Esc", 7.5), g_key("Tab", 7.5)
        pad = g_keys_cluster("up", ("left", "down", "right"))
    # 8 is the Nunchuk's Control Stick ("Move the tank with [stick] or [+]"), not the pointer.
    sheet24 = {3: a, 4: two, 5: fire, 8: move, 11: one, 16: a_flat, 17: fire}
    if pad is not None:
        sheet24[10] = sheet24[15] = pad
    sheet25 = {0: plus, 1: minus, 2: one, 3: two, 4: move}
    return {24: sheet24, 25: sheet25}


def write_glyphs(style, folder):
    cells = {}
    for sheet, glyphs in glyph_set(style).items():
        strip = Image.new("LA", (512, 32), (0, 0))
        for index, big in glyphs.items():
            cell = reduce(big)
            strip.paste(Image.merge("LA", (cell, cell)), (index * CELL_W, 0))
        strip.save(os.path.join(folder, f"glyphs_{sheet}.png"))
        cells[str(sheet)] = sorted(glyphs)
    with open(os.path.join(folder, "glyphs.json"), "w") as f:
        json.dump({"font": "Font/font.carc:pac_nRodDb_32_I4.brfnt", "cell_width": CELL_W, "cells": cells}, f,
                  indent=2)
        f.write("\n")


def pause_button(style):
    """The round grey + button of the "Pause" badge (32x32 IA8), drawn at 4x: same shading, its symbol
    swapped for the controller's Menu / Options button or the keyboard's Esc."""
    n = 128
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    shade = Image.new("L", (n, n), 0)
    sd = ImageDraw.Draw(shade)
    for r in range(56, 0, -1):  # light from the top left, like the original
        v = int(200 + 55 * (1 - r / 56) ** 0.6)
        sd.ellipse([64 - r - 6 * (1 - r / 56), 64 - r - 8 * (1 - r / 56), 64 + r - 6 * (1 - r / 56),
                    64 + r - 8 * (1 - r / 56)], fill=v)
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).ellipse([6, 6, 121, 121], fill=255)
    body = Image.merge("RGBA", (shade, shade, shade, mask))
    img.alpha_composite(body)
    d = ImageDraw.Draw(img)
    d.ellipse([6, 6, 121, 121], outline=(16, 16, 16, 255), width=9)
    sym = (80, 80, 80, 255)
    if style == "keyboard":
        d.text((64, 66), "Esc", font=font(40), fill=sym, anchor="mm")
    else:
        for y in (44, 64, 84):
            d.rounded_rectangle([36, y - 6, 92, y + 6], radius=5, fill=sym)
    return img


# ---------------------------------------------------------------------------------------------
# Glossy icons cut from Xelu's classic free prompts sheet (CC0, by Nicolae "Xelu" Berbece; see
# assets/third_party/CREDITS.md): they replace the drawn Pause badge and controls pictures above.
# Without the sheet the drawn ones stay.

SHEET = os.path.join(ROOT, "assets", "third_party", "xelu_prompts_classic.png")
SHEET_BOXES = {  # left, top, right, bottom (exclusive) of each icon on the sheet
    "esc": (506, 290, 579, 354), "key": (586, 450, 659, 514), "mouse_left": (437, 205, 488, 278),
    "round": (266, 446, 338, 518), "stick": (101, 443, 178, 516), "dpad": (23, 443, 101, 520),
}
KEY_INK = (55, 55, 40, 255)  # the sheet's key labels


def sheet_icon(sheet, name):
    return sheet.crop(SHEET_BOXES[name])


def labelled_key(sheet, label, width=None):
    """The sheet's blank glossy key with a label in its italic style; `width` stretches it (Space)
    by repeating its middle column, which keeps the rounded ends."""
    key = sheet_icon(sheet, "key")
    if width and width > key.width:
        mid = key.width // 2
        wide = Image.new("RGBA", (width, key.height))
        wide.paste(key.crop((0, 0, mid, key.height)), (0, 0))
        column = key.crop((mid, 0, mid + 1, key.height))
        for x in range(mid, width - (key.width - mid)):
            wide.paste(column, (x, 0))
        wide.paste(key.crop((mid, 0, key.width, key.height)), (width - (key.width - mid), 0))
        key = wide
    d = ImageDraw.Draw(key)
    italic = "/System/Library/Fonts/Supplemental/Arial Italic.ttf"
    f = ImageFont.truetype(italic, 24) if os.path.exists(italic) else font(24)
    d.text((key.width / 2 - 2, key.height / 2 - 3), label, font=f, fill=KEY_INK, anchor="mm")
    return key


def fit(img, size):
    """Scaled to fit `size` (keeping its shape), centred on transparency."""
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    scale = min(size[0] / img.width, size[1] / img.height)
    small = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    out.alpha_composite(small, ((size[0] - small.width) // 2, (size[1] - small.height) // 2))
    return out


def glossy_pause(sheet, style):
    """Kept to the original + button's footprint: a circle about 100 of the 128 pixels across."""
    out = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    if style == "keyboard":
        # A square key looks bigger than a circle as wide: about two-thirds of the icon fills the
        # badge's rounded end the way the round + button did.
        out.alpha_composite(fit(sheet_icon(sheet, "esc"), (84, 84)), (22, 22))
        return out
    button = fit(sheet_icon(sheet, "round"), (104, 104))
    d = ImageDraw.Draw(button)
    for y in (37, 52, 67):  # Menu / Options: three bars, in the sheet's grey button-label tone
        d.rounded_rectangle([32, y - 4, 72, y + 4], radius=4, fill=(150, 150, 150, 255))
    out.alpha_composite(button, (12, 12))
    return out


def glossy_keyboard_picture(sheet):
    img = card()
    k = 2.0  # sheet keys are 73x64; drawn at twice that on the 800x640 card
    def place(icon, x, y, scale=k):
        big = icon.resize((round(icon.width * scale), round(icon.height * scale)), Image.LANCZOS)
        img.alpha_composite(big, (round(x), round(y)))
    kw, kh, gap = 73 * k, 64 * k, 8
    group_w, group_h = 3 * kw + 2 * gap, 3 * kh + 2 * gap + 10
    mouse_scale = 3.0
    mouse_w, mouse_h = 51 * mouse_scale, 73 * mouse_scale
    x0 = (W - (group_w + 70 + mouse_w)) / 2
    y0 = (H - group_h) / 2
    place(labelled_key(sheet, "W"), x0 + kw + gap, y0)
    for i, label in enumerate("ASD"):
        place(labelled_key(sheet, label), x0 + i * (kw + gap), y0 + kh + gap)
    place(labelled_key(sheet, "Space", width=73 * 3), x0, y0 + 2 * (kh + gap) + 10)
    mouse = sheet_icon(sheet, "mouse_left")
    place(mouse, x0 + group_w + 70, (H - mouse_h) / 2, mouse_scale)
    return img


def glossy_pad_picture(sheet, style):
    """The four Tanks! actions on the blue card, from the sheet's glossy parts: L stick (move) and
    R stick (aim) on top, the fire trigger and the mine button below."""
    img = card()
    grey = (140, 140, 140, 255)

    def labelled(name, label, size):
        icon = sheet_icon(sheet, name).copy()
        d = ImageDraw.Draw(icon)
        f = font(size)
        cx, cy = icon.width / 2, icon.height / 2 - (4 if name == "stick" else 1)
        if label == "cross":
            r = icon.width * 0.17
            d.line([cx - r, cy - r, cx + r, cy + r], fill=grey, width=5)
            d.line([cx - r, cy + r, cx + r, cy - r], fill=grey, width=5)
        else:
            d.text((cx, cy), label, font=f, fill=grey, anchor="mm")
        return icon

    fire, mine = ("RT", "A") if style == "xbox" else ("R2", "cross")
    cells = [
        (labelled("stick", "L", 22), 200, 190), (labelled("stick", "R", 22), 600, 190),
        (labelled("round", fire, 22), 200, 460), (labelled("round", mine, 30), 600, 460),
    ]
    for icon, cx, cy in cells:
        scale = 2.6
        big = icon.resize((round(icon.width * scale), round(icon.height * scale)), Image.LANCZOS)
        img.alpha_composite(big, (round(cx - big.width / 2), round(cy - big.height / 2)))
    return img


def write_glossy():
    if not os.path.exists(SHEET):
        return
    sheet = Image.open(SHEET).convert("RGBA")
    for style in ("xbox", "playstation", "keyboard"):
        folder = os.path.join(OUT, style)
        os.makedirs(folder, exist_ok=True)
        glossy_pause(sheet, style).save(os.path.join(folder, "tex1_32x32_936c293ec061c777_3.png"))
        picture = glossy_keyboard_picture(sheet) if style == "keyboard" else glossy_pad_picture(sheet, style)
        picture.save(os.path.join(folder, "tex1_200x160_8643ac135bf172a4_5.png"))
        print("wrote", folder, "(glossy, from Xelu's sheet)")


def main():
    pictures = {"xbox": xbox_picture, "playstation": playstation_picture, "keyboard": keyboard_picture}
    for style, make in pictures.items():
        folder = os.path.join(OUT, style)
        os.makedirs(folder, exist_ok=True)
        make().save(os.path.join(folder, "tex1_200x160_8643ac135bf172a4_5.png"))
        pause_button(style).save(os.path.join(folder, "tex1_32x32_936c293ec061c777_3.png"))
        write_glyphs(style, folder)
        print("wrote", folder)
    write_glossy()


if __name__ == "__main__":
    main()
