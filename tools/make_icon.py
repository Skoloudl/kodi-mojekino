#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vygeneruje ikonu doplňku (512x512 PNG) bez dalších knihoven.

    python3 tools/make_icon.py
"""
import os
import struct
import zlib

SIZE = 512
SAMPLES = 3   # vyhlazení hran (počet vzorků na pixel v každém směru)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, 'plugin.video.mojekino', 'resources', 'icon.png')


def _in_round_rect(x, y, left, top, right, bottom, radius):
    if x < left or x > right or y < top or y > bottom:
        return False
    cx = min(max(x, left + radius), right - radius)
    cy = min(max(y, top + radius), bottom - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def _in_triangle(x, y, a, b, c):
    def side(p, q):
        return (x - q[0]) * (p[1] - q[1]) - (p[0] - q[0]) * (y - q[1])
    d1, d2, d3 = side(a, b), side(b, c), side(c, a)
    negative = d1 < 0 or d2 < 0 or d3 < 0
    positive = d1 > 0 or d2 > 0 or d3 > 0
    return not (negative and positive)


def _color(x, y):
    """Barva bodu (souřadnice 0..1)."""
    if not _in_round_rect(x, y, 0.03, 0.03, 0.97, 0.97, 0.19):
        return None
    # tmavě modré pozadí s přechodem
    r, g, b = 16 + 26 * y, 26 + 34 * y, 58 + 62 * (1 - y)
    # plátno
    if _in_round_rect(x, y, 0.17, 0.20, 0.83, 0.68, 0.05):
        r, g, b = 236, 240, 248
        if _in_triangle(x, y, (0.43, 0.32), (0.43, 0.56), (0.63, 0.44)):
            r, g, b = 232, 76, 61
    # tři řádky seznamu pod plátnem
    for i, width in enumerate((0.50, 0.38, 0.44)):
        top = 0.74 + i * 0.06
        if _in_round_rect(x, y, 0.17, top, 0.17 + 0.035, top + 0.033, 0.016):
            r, g, b = 232, 76, 61
        if _in_round_rect(x, y, 0.235, top, 0.235 + width, top + 0.033, 0.016):
            r, g, b = 150, 166, 200
    return r, g, b


def render():
    rows = []
    step = 1.0 / (SIZE * SAMPLES)
    for py in range(SIZE):
        row = bytearray([0])
        for px in range(SIZE):
            total = [0.0, 0.0, 0.0]
            hits = 0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    color = _color((px * SAMPLES + sx + 0.5) * step, (py * SAMPLES + sy + 0.5) * step)
                    if color:
                        hits += 1
                        for i in range(3):
                            total[i] += color[i]
            if hits:
                row += bytes(int(total[i] / hits) for i in range(3))
                row.append(int(255 * hits / (SAMPLES * SAMPLES)))
            else:
                row += b'\x00\x00\x00\x00'
        rows.append(bytes(row))
    return b''.join(rows)


def _chunk(kind, data):
    body = kind + data
    return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)


def main():
    png = b'\x89PNG\r\n\x1a\n'
    png += _chunk(b'IHDR', struct.pack('>IIBBBBB', SIZE, SIZE, 8, 6, 0, 0, 0))
    png += _chunk(b'IDAT', zlib.compress(render(), 9))
    png += _chunk(b'IEND', b'')
    with open(TARGET, 'wb') as handle:
        handle.write(png)
    print('Ikona uložena: %s (%d kB)' % (TARGET, len(png) // 1024))


if __name__ == '__main__':
    main()
