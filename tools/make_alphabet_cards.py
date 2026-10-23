#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成 app「字母表」页用的图卡 → assets/alphabet/*.png

五张卡，对应学习者理解腾格瓦时需要的五个层次：
  01 发音表     4 列（部位）× 6 行（方式），每格带拉丁值与字母名
  02 形状规律   三个维度：弓数 / 竖笔下伸 / 竖笔上延
  03 元音符号   五个 tehta + 长元音的承载方式
  04 例词拆解   六个词，每个词只讲一条规则
  05 长元音写法 长载体 vs 双写符号（同一个 lúmë）

内容全部来自引擎实际输出，改字体或引擎后重跑即可。
用法: python tools/make_alphabet_cards.py
"""
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import elvish as E  # noqa: E402

OUT = os.path.join(ROOT, "assets", "alphabet")
TF_PATH = os.path.join(ROOT, "assets", "tengwar-font", "FreeMonoTengwar.2013-07-21", "FreeMonoTengwar.ttf")
LF_PATH = os.path.join(ROOT, "assets", "freefont", "freefont-20120503", "FreeSerif.ttf")
CJK = r"C:\Windows\Fonts\msyh.ttc"
CJK_B = r"C:\Windows\Fonts\msyhbd.ttc"

PAPER = "#fbf9f4"
INK = "#1c1a17"
MUTED = "#7a7266"
ACCENT = "#8a5a2b"
LINE = "#e6e0d3"
FAINT = "#9a9285"


def f(size):
    return ImageFont.truetype(TF_PATH, size)


def cjk(size, bold=False):
    return ImageFont.truetype(CJK_B if bold else CJK, size)


def latin(size):
    return ImageFont.truetype(LF_PATH, size)


def header(d, title, subs):
    d.text((30, 20), title, font=cjk(21, True), fill=INK)
    y = 58
    for s in subs:
        d.text((30, y), s, font=cjk(13.5), fill=MUTED)
        y += 22
    return y + 8


def tengwar(word, longmode=None):
    """调引擎，拿字形与字母名。"""
    node = E.find_node()
    args = [node, os.path.join(HERE, "tengwar.mjs"), word, "--names"]
    if longmode:
        args += ["--opt", "long_vowels_format=" + longmode]
    r = subprocess.run(args, capture_output=True)
    out = r.stdout.decode("utf-8", "replace")

    def pick(prefix):
        for line in out.splitlines():
            if line.startswith(prefix):
                return line.split(":", 1)[1].strip()
        return ""
    return pick("Tengwar"), pick("字符名").split()


# ---------------------------------------------------------------- 01 发音表
LATIN_VALUES = [
    [("t", "tinco"), ("p", "parma"), ("k/c", "calma"), ("qu", "quesse")],
    [("nd", "ando"), ("mb", "umbar"), ("ng", "anga"), ("ngw", "ungwe")],
    [("th", "thule"), ("f", "formen"), ("h", "aha"), ("hw", "hwesta")],
    [("nt", "anto"), ("mp", "ampa"), ("nc", "anca"), ("nqu", "unque")],
    [("n", "numen"), ("m", "malta"), ("n/ñ", "noldo"), ("nw", "nwalme")],
    [("r", "ore"), ("v", "vala"), ("y", "anna"), ("w", "vilya")],
]
COLS = ["舌尖（牙）", "双唇", "舌根（喉）", "舌根＋圆唇"]
ROW_NOTES = ["第1行 单弓·下伸", "第2行 双弓·下伸", "第3行 单弓·下伸·上延",
             "第4行 双弓·下伸·上延", "第5行 双弓·不下伸", "第6行 单弓·不下伸"]


def card_grid():
    cw, ch, left, top = 224, 104, 236, 168
    W = left + cw * 4 + 30
    H = top + ch * 6 + 78
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    header(d, "腾格瓦的发音表", [
        "横着读 = 同一个嘴的位置；竖着读 = 同一种发音方式。",
        "24 个基本字母 = 4 列（部位）× 6 行（方式），不是一串字母。",
    ])
    for j, name in enumerate(COLS):
        d.text((left + j * cw + 12, top - 34), name, font=cjk(13), fill=MUTED)
    for i, row in enumerate(LATIN_VALUES):
        y = top + i * ch
        d.rectangle([left - 6, y, left + cw * 4, y + ch], outline=LINE)
        d.text((24, y + 18), ROW_NOTES[i], font=cjk(12.5), fill=ACCENT)
        for j, (val, name) in enumerate(row):
            x = left + j * cw
            d.text((x + 16, y + 2), chr(0xE000 + i * 4 + j), font=f(46), fill=INK)
            d.text((x + 16, y + 58), val, font=cjk(16, True), fill=ACCENT)
            d.text((x + 62, y + 62), name, font=latin(13), fill=FAINT)
    d.text((30, H - 52), "第 2 行在昆雅里不是 d/b/g —— 昆雅没有浊塞音，这几个字母改读 nd / mb / ng / ngw。",
           font=cjk(12.5), fill="#a08b6a")
    p = os.path.join(OUT, "01-grid.png")
    img.save(p)
    return p


# ---------------------------------------------------------------- 02 形状规律
def card_shapes():
    rows = [
        (0xE000, "tinco", "单弓 · 竖笔下伸 · 不上延", "t", "清塞音"),
        (0xE004, "ando", "双弓 · 竖笔下伸 · 不上延", "nd（通用读 d）", "浊塞音"),
        (0xE008, "thule", "单弓 · 竖笔下伸 · 上延", "th", "清擦音"),
        (0xE00C, "anto", "双弓 · 竖笔下伸 · 上延", "nt", "浊擦音位→昆雅读 nt"),
        (0xE010, "numen", "双弓 · 竖笔【不下伸】", "n", "鼻音"),
        (0xE014, "ore", "单弓（开口）· 竖笔【不下伸】", "r", "半元音"),
    ]
    W, rowh = 1060, 104
    H = 168 + rowh * len(rows) + 46
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    y0 = header(d, "形状的真正规律：三个维度", [
        "① 弓有几道（1 / 2）　② 竖笔向不向下伸出　③（第 1–4 行）竖笔向不向上延长",
        "第 5、6 行最容易看错——字形碰巧像拉丁字母 m 和 n，但「像什么」不算规律。",
    ])
    y = y0 + 6
    for cp, name, rule, val, kind in rows:
        d.rectangle([20, y - 8, W - 20, y + rowh - 20], outline=LINE)
        d.text((44, y - 8), chr(cp), font=f(76), fill=INK)
        d.text((150, y + 2), name, font=latin(17), fill=INK)
        d.text((150, y + 26), rule, font=cjk(13.5), fill=ACCENT)
        d.text((150, y + 50), "昆雅读 " + val + "　（" + kind + "）", font=cjk(12.5), fill=MUTED)
        y += rowh
    d.text((30, H - 38), "记住这一笔：竖笔下伸 = 塞音/擦音那四行；不下伸 = 鼻音与半元音那两行。",
           font=cjk(13.5), fill=ACCENT)
    p = os.path.join(OUT, "02-shapes.png")
    img.save(p)
    return p


# ---------------------------------------------------------------- 03 元音符号
TEHTA = [("a", 0xE040, "三点"), ("e", 0xE046, "一小撇"), ("i", 0xE044, "一点"),
         ("o", 0xE04A, "向右开的圈"), ("u", 0xE04C, "向左开的圈")]
LONG = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}


def card_vowels():
    W, H = 1010, 486
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    header(d, "元音是五个「符号」，不是五个字母", [
        "同一个符号可以戴在任何辅音头上（例子里都戴在 t 上）；长元音不是写两遍，是换一个「长载体」来戴。",
    ])
    TINCO, ARA = 0xE000, 0xE02C
    d.text((30, 118), "短", font=cjk(13.5), fill=ACCENT)
    x = 92
    for v, cp, desc in TEHTA:
        d.text((x, 104), chr(TINCO) + chr(cp), font=f(66), fill=INK)
        d.text((x + 34, 176), "t" + v, font=latin(21), fill=INK)
        d.text((x + 34, 202), desc, font=cjk(11.5), fill=FAINT)
        x += 180
    d.text((30, 252), "长", font=cjk(13.5), fill=ACCENT)
    x = 92
    for v, cp, _ in TEHTA:
        d.text((x, 238), chr(ARA) + chr(cp), font=f(66), fill=INK)
        d.text((x + 34, 310), "t" + LONG[v], font=latin(21), fill=INK)
        x += 180
    d.line([30, 352, W - 30, 352], fill=LINE)
    d.text((30, 370), "同一个 e 的小撇，戴在 l 头上读 le，戴在 m 头上读 me —— 符号不变，架子在变。",
           font=cjk(13.5), fill=INK)
    d.text((30, 398), "所以「元音符号 + 它下面那个辅音」才是一个整体；单独一个符号没有读音。",
           font=cjk(13.5), fill=INK)
    d.text((30, 430), "长音这一行用的是「长载体」写法；换一种写法也可以，见最后一张卡。",
           font=cjk(12), fill=FAINT)
    p = os.path.join(OUT, "03-vowels.png")
    img.save(p)
    return p


# ---------------------------------------------------------------- 04 例词拆解
NICE = {
    "TELCO": "空载体", "ARA": "长载体", "TW_11": "t", "TW_12": "p", "TW_14": "qu",
    "TW_22": "mb", "TW_23": "ng", "TW_31": "th", "TW_32": "f", "TW_33": "h", "TW_34": "hw",
    "TW_41": "nt", "TW_51": "n", "TW_52": "m", "TW_61": "r", "TW_62": "v", "TW_63": "y",
    "TW_71": "r", "TW_72": "rd", "TW_73": "l", "TW_74": "ld", "TW_81": "s", "TW_84": "ss",
    "TW_91": "hy", "TW_93": "au", "TW_94": "au",
    "E_TEHTA": "e·撇", "A_TEHTA": "a·三点", "I_TEHTA": "i·点", "O_TEHTA": "o·圈",
    "U_TEHTA": "u·圈", "GEMINATE_SIGN": "加倍线", "PALATAL_SIGN": "双点",
    "I_TEHTA_DOUBLE_INF": "双点", "SARINCE": "s·勾",
}
CASES = [
    ("elen", "星", "元音不是字母，是戴在辅音上的记号；词首没有辅音，就坐一根空竖棍",
     "e 坐在空载体上 → l 顶着 e → n 光秃秃（后面没元音）"),
    ("anar", "太阳", "最朴素的「辅音 + 帽子」结构", "a 空载体 → n 顶着 a → r 收尾"),
    ("mellon", "朋友", "双写辅音不写两遍，加一道加倍线", "m 顶 e → l 带加倍线、顶 o → n"),
    ("lúmë", "时间", "长元音换个更高的「长载体」，不是写两遍", "l 空着 → 长 ú → m 顶 e"),
    ("quetta", "词、话", "一个字母可以读两个音：qu 就是一个字母", "qu 顶 e → t 带加倍线（tt）、顶 a"),
    ("tyelpe", "银", "t+y 挤成一个字母，靠头上两点表示「y 化」", "t 带双点、顶 e → l → p 顶 e"),
]


def card_words():
    W, rowh = 1120, 128
    H = 150 + rowh * len(CASES) + 50
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    y = header(d, "六个词：每个词只讲一条规则", [
        "读腾格瓦不是「从左到右念字母」，而是「一个辅音 + 它头上那顶元音帽子」算一个单位。",
    ]) + 26
    for w, gloss, rule, decomp in CASES:
        tw, names = tengwar(w)
        d.rectangle([20, y - 14, W - 20, y + rowh - 26], outline=LINE)
        d.text((40, y - 2), w, font=latin(24), fill=INK)
        d.text((40, y + 34), gloss, font=cjk(15, True), fill=ACCENT)
        d.text((150, y - 8), tw, font=f(54), fill=INK)
        d.text((430, y - 2), " → ".join(NICE.get(n, n.lower()) for n in names), font=cjk(13.5), fill=INK)
        d.text((430, y + 30), rule, font=cjk(13), fill="#4a443a")
        d.text((430, y + 56), decomp, font=cjk(11.5), fill=FAINT)
        y += rowh
    d.text((30, H - 42), "共同点：辅音是主体，元音是配件。所以 4 个字母的词，写出来常常只有 3 个字形。",
           font=cjk(13.5), fill=ACCENT)
    p = os.path.join(OUT, "04-words.png")
    img.save(p)
    return p


# ---------------------------------------------------------------- 05 长元音两种写法
def card_longvowel():
    rows = [
        ("默认：长载体", "LONG_VOWELS_USE_LONG_CARRIER",
         "l 空着 → 一根长载体顶 ú → m 顶 e", "长音自己站一根更高的竖棍，这是模式默认"),
        ("切换：双写元音符号", "LONG_VOWELS_USE_DOUBLE_TEHTAR",
         "l 头上叠两个 u 符号 → m 顶 e", "这才是你直觉里的写法：元音就在 l 上，只是叠了两个"),
    ]
    W, H = 980, 470
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    y = header(d, "同一个 lúmë，两种都算对的写法", [
        "长元音「写在长载体上」和「叠两个元音符号」是两种通行写法，可切换。",
    ]) + 10
    for title, opt, desc, note in rows:
        tw, names = tengwar("lúmë", opt)
        d.rectangle([20, y, W - 20, y + 142], outline=LINE)
        d.text((40, y + 14), title, font=cjk(18, True), fill=ACCENT)
        d.text((330, y + 6), tw, font=f(66), fill=INK)
        d.text((40, y + 56), desc, font=cjk(13.5), fill=INK)
        d.text((40, y + 80), note, font=cjk(11.5), fill=FAINT)
        d.text((330, y + 92), " ".join(names), font=cjk(11), fill="#a0907a")
        y += 158
    d.text((30, H - 38), "两个选项都来自同一个模式的规则文件；命令行加 --opt long_vowels_format=… 就能切。",
           font=cjk(12.5), fill=FAINT)
    p = os.path.join(OUT, "05-longvowel.png")
    img.save(p)
    return p


# ---------------------------------------------------------------- 06 下面两个点
PALATAL_ROWS = [
    ("tya", "tya（ty）", "下面两点 = 这个 t 后面跟 y", "上面还空着，因为这里没有元音"),
    ("tyelpe", "tyelpe", "双点在下面，e 的小撇在上面", "各占一块地方，不打架"),
    ("nya", "nya（ny）", "同一套：n 带下两点", ""),
    ("lya", "lya（ly）", "同一套：l 带下两点", ""),
    ("mellon", "mellon", "对比：下面那道是【加倍线】，不是两点", "一道横线 = 辅音双写；两个点 = 带 y"),
]


def card_palatal():
    W, rowh = 1060, 120
    H = 150 + rowh * len(PALATAL_ROWS) + 40
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    y = header(d, "字母下面那两个点：y 化记号", [
        "它放在下面，是因为上面那块地方要留给元音符号（tehta）。",
        "和「加倍线」区分：两个点 = 带 y；一道横线 = 辅音双写。",
    ]) + 8
    for word, label, note1, note2 in PALATAL_ROWS:
        tw, names = tengwar(word)          # 只把词本身交给引擎
        d.rectangle([20, y - 10, W - 20, y + rowh - 28], outline=LINE)
        d.text((40, y + 6), label, font=cjk(16, True), fill=INK)
        d.text((210, y - 6), tw, font=f(64), fill=INK)
        d.text((470, y + 4), note1, font=cjk(14, True), fill=INK)
        if note2:
            d.text((470, y + 32), note2, font=cjk(13), fill=MUTED)
        d.text((470, y + 62), " ".join(names), font=cjk(10.5), fill="#b0a89a")
        y += rowh
    p = os.path.join(OUT, "06-palatal.png")
    img.save(p)
    return p


def main():
    os.makedirs(OUT, exist_ok=True)
    made = [card_grid(), card_shapes(), card_vowels(), card_words(),
            card_longvowel(), card_palatal()]
    for p in made:
        print("%-28s %6.1f KB" % (os.path.basename(p), os.path.getsize(p) / 1024))


if __name__ == "__main__":
    main()
