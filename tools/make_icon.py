#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成应用图标 assets/quenya.ico

设计取两条硬约束：
  · 桌面是浅色的，图标要能"跳出来" —— 深色底 + 亮色前景，而不是浅底 + 细线；
  · 16px 也要认得出 —— 用一整块四角星（elen「星」），不用细笔画文字。
    腾格瓦的笔画是发丝级的，缩到 16px 只会变成一团灰（旧版就是这个毛病）。

格式：全部写成 BMP 帧（不压缩）。Windows 虽支持 PNG-in-ICO，但某些视图/版本
对 PNG 帧处理不好，BMP 帧最保险。

用法: python tools/make_icon.py
"""
import math
import os
import struct

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "assets", "quenya.ico")

DARK = (36, 29, 22, 255)      # 暖黑，浅色桌面上能跳出来
DARK_EDGE = (58, 46, 34, 255)
GOLD = (232, 172, 76, 255)    # elen 的金色
GOLD_HI = (247, 208, 132, 255)

SIZES = [16, 24, 32, 48, 64, 128, 256]


def star(cx, cy, r_out, r_in, points=4, rot=-math.pi / 2):
    """四角星（星芒）多边形：points 个尖，外/内半径交替。"""
    pts = []
    for i in range(points * 2):
        ang = rot + i * math.pi / points
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def render(size):
    """画一张 size×size 的图。小尺寸单独调粗，不做纯缩放。"""
    s = size * 4 if size < 64 else size      # 小尺寸超采样再缩，边缘更干净
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = s * 0.045
    d.rounded_rectangle([pad, pad, s - pad, s - pad], radius=s * 0.22,
                        fill=DARK, outline=DARK_EDGE, width=max(1, int(s * 0.012)))

    # 小尺寸给星更大的占比，缩下去才看得见
    frac = 0.40 if size >= 48 else 0.42
    r_out = s * frac
    r_in = r_out * (0.34 if size >= 48 else 0.40)
    cx = cy = s / 2
    d.polygon(star(cx, cy, r_out, r_in), fill=GOLD)
    d.polygon(star(cx, cy - s * 0.012, r_out * 0.92, r_in * 0.80), fill=GOLD_HI)
    d.polygon(star(cx, cy + s * 0.010, r_out * 0.62, r_in * 0.55), fill=GOLD)

    if s != size:
        img = img.resize((size, size), Image.LANCZOS)
    return img


def bmp_frame(img):
    """ICO 内的 BMP 帧：BITMAPINFOHEADER（高度写两倍）+ BGRA 像素 + AND 掩码。"""
    s = img.size[0]
    header = struct.pack("<IiiHHIIiiII", 40, s, s * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    pixels = img.transpose(Image.FLIP_TOP_BOTTOM).tobytes("raw", "BGRA")
    mask_row = ((s + 31) // 32) * 4
    mask = b"\x00" * (mask_row * s)          # 全 0 = 不透明，透明度交给 alpha
    return header + pixels + mask


def write_ico(frames, path):
    count = len(frames)
    head = struct.pack("<HHH", 0, 1, count)
    entries = b""
    data = b""
    offset = 6 + 16 * count
    for size, blob in frames:
        w = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(blob), offset + len(data))
        data += blob
    with open(path, "wb") as f:
        f.write(head + entries + data)


def main():
    frames = [(size, bmp_frame(render(size))) for size in SIZES]
    write_ico(frames, OUT)
    print("icon -> %s  %.1f KB  frames=%s"
          % (OUT, os.path.getsize(OUT) / 1024, [s for s, _ in frames]))

    sheet = Image.new("RGB", (60 + 170 * 4, 220), "#2b2b2b")
    x = 30
    for size in (16, 32, 48, 256):
        im = render(size).resize((150, 150), Image.NEAREST if size < 64 else Image.LANCZOS)
        bg = Image.new("RGBA", (150, 150), (43, 43, 43, 255))
        bg.alpha_composite(im)
        sheet.paste(bg.convert("RGB"), (x, 34))
        x += 170
    sheet.save(os.path.join(ROOT, "data", "_icon_sizes.png"))
    print("preview -> data/_icon_sizes.png")


if __name__ == "__main__":
    main()
