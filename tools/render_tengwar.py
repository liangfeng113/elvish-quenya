#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 Tengwar 码位渲染成 PNG。

为什么能直接画：FreeMonoTengwar 是等宽字体，元音符号（tehta）的 advance 宽度是 0，
所以「辅音 + 符号」在同一格里自然叠合，不需要 GPOS/Graphite 排版引擎。
（浏览器里 Chromium 不支持 Graphite，靠 margin 排版反而会掉字距；Pillow 直接画更可控。）

字体: FreeMonoTengwar © Free Tengwar Font Project，GPL + 字体嵌入例外。
     来源 https://freetengwar.sourceforge.net/

用法（一般由 elvish.py 调用）:
  python render_tengwar.py "<tengwar 文本>" out.png [--size 72] [--width 1200]
"""
import argparse
import os
import sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONT_DIR = os.path.join(ROOT, "assets", "tengwar-font", "FreeMonoTengwar.2013-07-21")


def find_font():
    for name in ("FreeMonoTengwar.ttf", "FreeMonoTengwar-embedding.ttf"):
        p = os.path.join(FONT_DIR, name)
        if os.path.exists(p):
            return p
    return None


def wrap_cells(text, font, max_width):
    """按词换行（只按空格切，不拆词——Tengwar 拆行要看音节，先不碰）。"""
    space = font.getlength(" ")
    lines, cur, cur_w = [], [], 0.0
    for word in text.split(" "):
        w = font.getlength(word)
        if cur and cur_w + space + w > max_width:
            lines.append(" ".join(cur))
            cur, cur_w = [word], w
        else:
            cur_w += (space if cur else 0) + w
            cur.append(word)
    if cur:
        lines.append(" ".join(cur))
    return lines


def find_latin_font():
    """配图用的拉丁字体（FreeSerif，同为 GNU FreeFont，GPL + 字体例外）。"""
    base = os.path.join(ROOT, "assets", "freefont", "freefont-20120503")
    p = os.path.join(base, "FreeSerif.ttf")
    return p if os.path.exists(p) else None


def render(text, out_path, size=72, max_width=1200, fg="#1c1a17", bg="#f7f5f0",
           caption=None, caption_size=30):
    fp = find_font()
    if not fp:
        sys.exit("找不到 FreeMonoTengwar.ttf，请把字体放到 %s" % FONT_DIR)
    font = ImageFont.truetype(fp, size)
    lines = wrap_cells(text, font, max_width)

    cap_font = None
    if caption:
        lf = find_latin_font()
        if lf:
            cap_font = ImageFont.truetype(lf, caption_size)

    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * 1.35)
    pad = int(size * 0.7)
    cap_h = int(caption_size * 2.1) if cap_font else 0
    width = int(max([font.getlength(l) for l in lines] + [10]) + pad * 2)
    height = int(line_h * len(lines) + pad * 2 + cap_h)

    img = Image.new("RGB", (max(width, 320), max(height, 120)), bg)
    dr = ImageDraw.Draw(img)
    y = pad
    if cap_font:
        dr.text((pad, y), caption, font=cap_font, fill="#6d675d")
        y += cap_h
    for line in lines:
        dr.text((pad, y), line, font=font, fill=fg)
        y += line_h
    img.save(out_path)
    return out_path, img.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("out")
    ap.add_argument("--size", type=int, default=72)
    ap.add_argument("--width", type=int, default=1200)
    ap.add_argument("--fg", default="#1c1a17")
    ap.add_argument("--bg", default="#f7f5f0")
    ap.add_argument("--caption", default=None, help="在 Tengwar 上方加一行拉丁转写")
    a = ap.parse_args()
    p, sz = render(a.text, a.out, a.size, a.width, a.fg, a.bg, a.caption)
    print("saved %s (%dx%d)" % (p, sz[0], sz[1]))


if __name__ == "__main__":
    main()
