#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成应用图标 assets/quenya.ico。

图案：暖色圆角卡片 + 昆雅词 elen（星）的 Tengwar 写法。
用自家渲染器画精灵文，所以图标和 app 里的字形是同一套。
"""
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import render_tengwar as RT  # noqa: E402

OUT = os.path.join(ROOT, "assets", "quenya.ico")
PAPER = "#f7f3e9"
INK = "#2a241d"
ACCENT = "#8a5a2b"

SIZE = 512


def rounded_mask(size, radius, inset=0):
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([inset, inset, size - inset - 1, size - inset - 1],
                        radius=radius, fill=255)
    return m


def main():
    # 1) 先把 Tengwar 渲染到临时 png（用同一套引擎，保证字形一致）
    tmp = os.path.join(ROOT, "data", "_icon_tw.png")
    png, _ = RT.render("elen", tmp, size=int(SIZE * 0.44), max_width=SIZE,
                       fg=INK, bg=PAPER)
    glyph = Image.open(png).convert("RGB")

    # 2) 裁掉留白，只留字形
    diff = Image.new("L", glyph.size, 0)
    px = glyph.load()
    w, h = glyph.size
    bb = None
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if (r + g + b) < 330:          # 明显比纸色深 → 是墨
                if bb is None:
                    bb = [x, y, x, y]
                else:
                    bb[0] = min(bb[0], x); bb[1] = min(bb[1], y)
                    bb[2] = max(bb[2], x); bb[3] = max(bb[3], y)
    if bb:
        pad = 8
        glyph = glyph.crop((max(0, bb[0] - pad), max(0, bb[1] - pad),
                            min(w, bb[2] + pad), min(h, bb[3] + pad)))

    # 3) 卡片底
    card = Image.new("RGB", (SIZE, SIZE), PAPER)
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([26, 26, SIZE - 26, SIZE - 26], radius=96,
                        outline=ACCENT, width=10)

    # 4) 字形按比例居中放上去
    gw, gh = glyph.size
    scale = min((SIZE * 0.64) / gw, (SIZE * 0.64) / gh)
    glyph = glyph.resize((max(1, int(gw * scale)), max(1, int(gh * scale))), Image.LANCZOS)
    card.paste(glyph, ((SIZE - glyph.size[0]) // 2, (SIZE - glyph.size[1]) // 2))

    # 5) 圆角 + 透明
    card_rgba = card.convert("RGBA")
    card_rgba.putalpha(rounded_mask(SIZE, 96))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    card_rgba.save(OUT, format="ICO",
                   sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    os.remove(tmp)
    print("icon ->", OUT, os.path.getsize(OUT), "bytes")
    return OUT


if __name__ == "__main__":
    main()
