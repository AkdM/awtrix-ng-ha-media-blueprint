#!/usr/bin/env python3
"""Build the 8x8 animated play / pause GIFs for AWTRIX NG.

Writes play.gif and pause.gif next to this script, enlarged LED-style
previews in preview/, and embeds the icons as base64 in the blueprint
(AWTRIX NG decodes any icon string longer than 64 characters as image data).
Standard library only.
"""

import base64
import re
from pathlib import Path

HERE = Path(__file__).parent
BLUEPRINT = HERE.parent / "media_awtrix_ng_blueprint.yaml"

PLAY = [
    "........",
    ".#......",
    ".###....",
    ".#####..",
    ".######.",
    ".#####..",
    ".###....",
    ".#......",
]

PAUSE = [
    "........",
    ".##..##.",
    ".##..##.",
    ".##..##.",
    ".##..##.",
    ".##..##.",
    ".##..##.",
    ".##..##.",
]

BLACK = (0, 0, 0)
GREEN = (0, 210, 80)
AMBER = (255, 170, 0)


def scale(rgb, k):
    return tuple(round(c * k) for c in rgb)


def mix(a, b, k):
    return tuple(round(x + (y - x) * k) for x, y in zip(a, b))


def play_frames():
    """Green triangle with a light sweeping across it, then a pause."""
    shine = {0: 0.85, 1: 0.45, 2: 0.15}  # distance behind the band -> whiteness
    frames = [(lambda x, y: GREEN, 900)]
    for band in range(1, 9):
        def px(x, y, band=band):
            k = shine.get(band - x, 0.0)
            return mix(GREEN, (255, 255, 255), k)
        frames.append((px, 60))
    return [(render(PLAY, f), ms) for f, ms in frames]


def pause_frames():
    """Amber bars slowly breathing."""
    levels = [(1.0, 700), (0.8, 90), (0.6, 90), (0.42, 90), (0.3, 160),
              (0.42, 90), (0.6, 90), (0.8, 90)]
    return [(render(PAUSE, lambda x, y, k=k: scale(AMBER, k)), ms) for k, ms in levels]


def render(mask, color):
    return [[color(x, y) if mask[y][x] == "#" else BLACK for x in range(8)] for y in range(8)]


def led_preview(img, cell=12):
    """Draw an 8x8 frame as round LEDs on a dark panel, for the README."""
    panel, unlit = (16, 16, 16), (34, 34, 34)
    c, r2 = (cell - 1) / 2, (cell * 0.4) ** 2
    lit = [[(x - c) ** 2 + (y - c) ** 2 <= r2 for x in range(cell)] for y in range(cell)]
    return [[(img[py // cell][px // cell] if img[py // cell][px // cell] != BLACK else unlit)
             if lit[py % cell][px % cell] else panel
             for px in range(8 * cell)] for py in range(8 * cell)]


def lzw(indices, min_size):
    """GIF-flavoured LZW: variable code width, LSB-first bit packing."""
    clear, eoi = 1 << min_size, (1 << min_size) + 1
    out, acc, nbits = bytearray(), 0, 0

    def emit(code, width):
        nonlocal acc, nbits
        acc |= code << nbits
        nbits += width
        while nbits >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            nbits -= 8

    table = {(i,): i for i in range(clear)}
    width, nxt = min_size + 1, eoi + 1
    emit(clear, width)
    w = (indices[0],)
    for k in indices[1:]:
        if w + (k,) in table:
            w += (k,)
            continue
        emit(table[w], width)
        if nxt < 4096:
            table[w + (k,)] = nxt
            nxt += 1
            if nxt > (1 << width) and width < 12:
                width += 1
        else:  # table full: start over
            emit(clear, width)
            table = {(i,): i for i in range(clear)}
            width, nxt = min_size + 1, eoi + 1
        w = (k,)
    emit(table[w], width)
    emit(eoi, width)
    if nbits:
        out.append(acc & 0xFF)
    return bytes(out)


def gif(frames):
    """Looping GIF89a with one global palette and full, opaque frames."""
    palette = sorted({c for img, _ in frames for row in img for c in row})
    bits = max(1, (len(palette) - 1).bit_length())
    palette += [BLACK] * ((1 << bits) - len(palette))
    index = {c: i for i, c in enumerate(palette)}
    size = len(frames[0][0][0]).to_bytes(2, "little") + len(frames[0][0]).to_bytes(2, "little")

    data = bytearray(b"GIF89a")
    data += size + bytes([0xF0 | (bits - 1), 0, 0])
    data += b"".join(bytes(c) for c in palette)
    data += b"\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00"  # loop forever
    min_size = max(2, bits)
    for img, ms in frames:
        data += b"\x21\xF9\x04\x04" + (ms // 10).to_bytes(2, "little") + b"\x00\x00"
        data += b"\x2C" + bytes(4) + size + b"\x00"
        code = lzw([index[c] for row in img for c in row], min_size)
        data.append(min_size)
        for i in range(0, len(code), 255):
            chunk = code[i:i + 255]
            data += bytes([len(chunk)]) + chunk
        data += b"\x00"
    return bytes(data + b"\x3B")


if __name__ == "__main__":
    (HERE / "preview").mkdir(exist_ok=True)
    blueprint = BLUEPRINT.read_text()
    for name, frames in [("play", play_frames()), ("pause", pause_frames())]:
        blob = gif(frames)
        (HERE / f"{name}.gif").write_bytes(blob)
        (HERE / "preview" / f"{name}.gif").write_bytes(gif([(led_preview(f), ms) for f, ms in frames]))
        b64 = base64.b64encode(blob).decode()
        blueprint, n = re.subn(rf'(builtin_{name}_icon: ")[^"]*"', lambda m: m.group(1) + b64 + '"', blueprint)
        assert n == 1, f"builtin_{name}_icon not found in {BLUEPRINT.name}"
        print(f"{name}.gif: {len(frames)} frames, {len(blob)} bytes, {len(b64)} base64 chars")
    BLUEPRINT.write_text(blueprint)
    print(f"updated {BLUEPRINT.name}")
