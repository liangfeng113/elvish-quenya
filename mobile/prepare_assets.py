#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把手机版要用的静态资源从项目里搬进 mobile/web（一次性，跑完就够）。

· Tengwar 转写库（Glǽmscribe, AGPL-3.0）
· FreeMonoTengwar 字体（GPL，见 assets/tengwar-font/.../GPL.txt）
· 应用图标（从 assets/quenya.ico 转 180×180 PNG）
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(HERE, "web")

COPY = [
    ("node_modules/glaemscribe/js/glaemscribe.min.js", "vendor/glaemscribe.min.js"),
    ("node_modules/glaemscribe/js/charsets/tengwar_telcontar.cst.js", "vendor/tengwar_telcontar.cst.js"),
    ("node_modules/glaemscribe/js/modes/quenya-tengwar-classical.glaem.js", "vendor/quenya-tengwar-classical.glaem.js"),
    ("assets/tengwar-font/FreeMonoTengwar.2013-07-21/FreeMonoTengwar.ttf", "fonts/FreeMonoTengwar.ttf"),
]


def main():
    for src, dst in COPY:
        s = os.path.join(ROOT, src)
        d = os.path.join(WEB, dst)
        if not os.path.exists(s):
            sys.exit("缺少 %s" % s)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copyfile(s, d)
        print("复制 %-58s %6.1f KB" % (dst, os.path.getsize(d) / 1024.0))

    ico = os.path.join(ROOT, "assets", "quenya.ico")
    out = os.path.join(WEB, "icon-180.png")
    try:
        from PIL import Image
    except ImportError:
        print("没装 Pillow，跳过图标")
        return
    im = Image.open(ico)
    size = max(getattr(im, "ico", None).sizes() if hasattr(im, "ico") and im.ico else [(0, 0)])
    if size[0] > 0:
        im.size = size
    im = im.convert("RGBA").resize((180, 180), Image.LANCZOS)
    im.save(out, "PNG")
    print("生成 %-58s %6.1f KB" % ("icon-180.png", os.path.getsize(out) / 1024.0))


if __name__ == "__main__":
    main()
