#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""昆雅词库查询器（Eldamo v0.8.13 数据，CC-BY 4.0 © Paul Strack）。

用法:
  python elvish.py word elen          按拼写查（精确 → 前缀 → 包含）
  python elvish.py en star            按英文释义反查
  python elvish.py id 3268020261      按 Eldamo page-id 查
  python elvish.py stats              词库统计
  python elvish.py daily [2026-10-23] 今日一词（按日期确定性挑选，可复现）
  python elvish.py inflect eleni      按变格/变位形式反查原形
  python elvish.py check "一句话"      逐词核对一整句昆雅
  python elvish.py tengwar "一句话"    拉丁转写 → Tengwar（可选 --png 出图）
  python elvish.py repl               交互模式：敲词查词、敲句核对

常用选项:
  --lang q,nq     限定语言（q=Late Quenya, nq=Neo-Quenya, mq, eq, s, ns ...）
  --tier 0,1,2    限定可靠性等级（0 原文证实 … 5 纯新造词）
  --limit N       最多显示几条（默认 8）
"""
import os
import sqlite3
import sys
import textwrap
import datetime
import random
import unicodedata

# 只给命令行用；被 GUI 导入时必须容错——pythonw 下 sys.stdout / stderr 是 None，
# 硬调用 reconfigure 会让整个应用在导入阶段就崩（表现为"双击没反应"）。
try:
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr is not None:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB = os.path.join(ROOT, "data", "elvish.db")

TIER_LABEL = {
    0: "原文证实",
    1: "可推导/复合成分",
    2: "合理重建",
    3: "古语/诗歌体",
    4: "早期版本改写",
    5: "推测",
    6: "新造词(非托老)",
    7: "特殊标记",
    9: "不建议使用",
}
PERIOD_ORDER = ["q", "nq", "mq", "eq", "s", "ns", "n", "on", "g", "p", "mp", "ep", "t", "ad"]

SUP = "\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079"


def form_key(s):
    """匹配用规范化形：去上标编号、统一撇号、折叠大小写。"""
    if not s:
        return ""
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u02bc", "'")
    s = s.translate({ord(c): None for c in SUP})
    return s.casefold().strip()


def form_fold(s):
    """去掉全部变音符号和撇号的形，用来在用户漏写长音符时找近形（sila → síla）。"""
    k = form_key(s).replace("'", "")
    d = unicodedata.normalize("NFD", k)
    return "".join(c for c in d if unicodedata.category(c) != "Mn")


def connect():
    if not os.path.exists(DB):
        sys.exit("找不到词库 %s，先跑 tools/build_db.py" % DB)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def lang_name(con, lid):
    r = con.execute("SELECT name, period FROM language WHERE id=?", (lid,)).fetchone()
    return (r["name"], r["period"]) if r else (lid or "?", None)


def wrap(text, indent="    ", width=96, subsequent=None):
    if not text:
        return []
    return textwrap.wrap(text, width=width, initial_indent=indent,
                         subsequent_indent=(subsequent if subsequent is not None else indent),
                         break_long_words=False, break_on_hyphens=False)


def fmt_word(con, w, verbose=True, width=96):
    name, period = lang_name(con, w["lang"])
    out = []
    mark = (" " + w["mark"]) if w["mark"] else ""
    out.append("%s%s  —  %s  [%s]" % (w["form"], mark, w["gloss"] or "(无释义)", name))
    meta = ["等级 %d %s" % (w["tier"], TIER_LABEL.get(w["tier"], "?"))]
    if w["speech"]:
        meta.append(w["speech"])
    if w["cat"]:
        r = con.execute("SELECT label, group_label FROM cat WHERE id=?", (w["cat"],)).fetchone()
        if r:
            meta.append("义类 %s/%s" % (r["group_label"], r["label"]))
    if w["created"]:
        meta.append("造词者 " + w["created"])
    meta.append("%d 条引文" % w["n_refs"])
    out.append("  · " + " · ".join(meta))

    if w["notes"] and verbose:
        note = w["notes"].replace("@@@", "").strip()
        note = " ".join(note.split())   # 把段落折行拍平，交给 textwrap 统一排版
        if len(note) > 700:
            note = note[:700].rsplit(" ", 1)[0] + "…"
        for line in wrap(note, indent="  注: ", subsequent="      ", width=width):
            out.append(line)

    refs = con.execute(
        "SELECT form, src, gloss FROM ref WHERE word_uid=? ORDER BY id LIMIT 8", (w["uid"],)
    ).fetchall()
    if refs:
        out.append("  引文（托老原文出处）:")
        for r in refs:
            g = ("  “%s”" % r["gloss"]) if r["gloss"] else ""
            f = (" 写作 %s" % r["form"]) if r["form"] and r["form"] != w["form"] else ""
            out.append("    %-22s%s%s" % (r["src"] or "?", g, f))

    infl = con.execute(
        "SELECT DISTINCT kind, form FROM inflect WHERE word_uid=? AND kind IS NOT NULL ORDER BY kind LIMIT 20",
        (w["uid"],),
    ).fetchall()
    if infl:
        out.append("  屈折形式:")
        for i in infl:
            out.append("    %-28s → %s" % (i["kind"], i["form"] or "?"))

    els = con.execute("SELECT lang, form, kind FROM element WHERE word_uid=?", (w["uid"],)).fetchall()
    if els:
        out.append("  构成成分: " + " + ".join(
            "%s%s" % (e["form"], ("(%s)" % e["kind"] if e["kind"] else "") if e["form"] else "") for e in els
        ))

    subs = con.execute(
        "SELECT * FROM word WHERE parent_uid=? ORDER BY uid", (w["uid"],)
    ).fetchall()
    if subs:
        out.append("  词源链条（同一词条更早的语言形式）:")
        for s in subs:
            sn, _ = lang_name(con, s["lang"])
            out.append("    %-8s %-14s %s" % (s["lang"], s["form"], (s["gloss"] or sn)))
    return "\n".join(out)


def order_key(w):
    lang = w["lang"] if w["lang"] in PERIOD_ORDER else "zz"
    return (PERIOD_ORDER.index(lang), w["tier"], -(w["n_refs"] or 0))


def cmd_word(con, term, langs, tiers, limit, verbose):
    k = form_key(term)
    rows = con.execute(
        "SELECT * FROM word WHERE form_key = ? ORDER BY uid LIMIT 600", (k,)
    ).fetchall()
    if not rows:
        rows = con.execute(
            "SELECT * FROM word WHERE form_key LIKE ? ORDER BY uid LIMIT 600", (k + "%",)
        ).fetchall()
    if not rows:
        rows = con.execute(
            "SELECT * FROM word WHERE form_key LIKE ? ORDER BY uid LIMIT 600", ("%" + k + "%",)
        ).fetchall()
    rows = [r for r in rows if (not langs or r["lang"] in langs) and (not tiers or r["tier"] in tiers)]
    if not rows:
        print("没找到 “%s”。换个写法试试（昆雅常带词干尾 -）" % term)
        return
    rows.sort(key=order_key)
    print("命中 %d 条，显示前 %d 条：" % (len(rows), min(limit, len(rows))))
    for r in rows[:limit]:
        print()
        print(fmt_word(con, r, verbose))


def cmd_en(con, term, langs, tiers, limit):
    rows = con.execute(
        "SELECT * FROM word WHERE gloss LIKE ? COLLATE NOCASE ORDER BY uid LIMIT 600", ("%" + term + "%",)
    ).fetchall()
    rows = [r for r in rows if (not langs or r["lang"] in langs) and (not tiers or r["tier"] in tiers)]
    if not rows:
        print("英文 “%s” 没有对应词条。" % term)
        return
    rows.sort(key=order_key)
    print("“%s” → %d 条，前 %d 条：" % (term, len(rows), min(limit, len(rows))))
    for r in rows[:limit]:
        name, _ = lang_name(con, r["lang"])
        mk = (" [%s]" % r["mark"]) if r["mark"] else ""
        print("  %-16s %-13s %s%s  (等级%d %s)" % (
            r["form"], r["lang"], r["gloss"], mk, r["tier"], TIER_LABEL.get(r["tier"], "")))


def cmd_id(con, pid):
    rows = con.execute("SELECT * FROM word WHERE page_id=?", (pid,)).fetchall()
    if not rows:
        print("没有 page-id = %s 的词条" % pid)
        return
    for r in rows:
        print()
        print(fmt_word(con, r, True))


def find_node():
    """找 node：优先 PATH，退回本机便携版。"""
    import shutil
    p = shutil.which("node")
    if p:
        return p
    cand = os.path.expanduser(os.path.join("~", "dsh", "node-portable"))
    if os.path.isdir(cand):
        for d in sorted(os.listdir(cand), reverse=True):
            exe = os.path.join(cand, d, "node.exe")
            if os.path.exists(exe):
                return exe
    return None


def cmd_tengwar(text, extra=None, png=None, quiet=False):
    """拉丁转写 → Tengwar。转写引擎是 Glǽmscribe（AGPL-3.0），渲染用 Pillow。"""
    import subprocess
    node = find_node()
    if not node:
        print("转写需要 node，没找到。")
        return
    script = os.path.join(ROOT, "tools", "tengwar.mjs")
    r = subprocess.run([node, script, text] + (extra or []), capture_output=True)
    out = r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")
    if r.returncode != 0:
        print(out + err)
        return
    if quiet:
        for line in out.splitlines():
            if line.startswith("Tengwar :"):
                print(line.split(":", 1)[1].strip())
    else:
        print(out.rstrip())
    if png:
        # 再取一次纯 JSON 输出喂给渲染器
        r2 = subprocess.run([node, script, text, "--json"] + (extra or []), capture_output=True)
        if r2.returncode == 0:
            import json
            tw = json.loads(r2.stdout.decode("utf-8", "replace"))["tengwar"]
            rr = subprocess.run(
                [sys.executable, os.path.join(ROOT, "tools", "render_tengwar.py"),
                 tw, png, "--caption", text],
                capture_output=True,
            )
            msg = rr.stdout.decode("utf-8", "replace").strip() or rr.stderr.decode("utf-8", "replace").strip()
            print("图片    : " + msg)


def cmd_inflect(con, form, limit):
    rows = con.execute(
        """SELECT DISTINCT w.*, i.kind FROM inflect i JOIN word w ON w.uid = i.word_uid
           WHERE i.form_key = ? ORDER BY w.uid LIMIT ?""", (form_key(form), limit)
    ).fetchall()
    if not rows:
        print("“%s” 不是任何已记录的屈折形式（Eldamo 只收原文里出现过的形式）" % form)
        return
    for r in rows:
        name, _ = lang_name(con, r["lang"])
        print("  %s 是 %s（%s, %s）的 %s 形式" % (
            form, r["form"], name, r["gloss"], r["kind"]))


def cmd_stats(con):
    print("语言分布：")
    for r in con.execute("SELECT lang, COUNT(*) n FROM word GROUP BY lang ORDER BY n DESC LIMIT 16"):
        name, period = lang_name(con, r["lang"])
        print("  %-6s %-26s %6d" % (r["lang"], name, r["n"]))
    print("\n昆雅相关（q/mq/eq/nq）可靠性：")
    for r in con.execute(
        """SELECT tier, COUNT(*) n FROM word WHERE lang IN ('q','mq','eq','nq')
           GROUP BY tier ORDER BY tier"""
    ):
        print("  等级 %d %-16s %6d" % (r["tier"], TIER_LABEL.get(r["tier"], ""), r["n"]))
    print("\n可学核心词（q/nq/mq/eq 且等级≤2）：%d 条" % con.execute(
        "SELECT COUNT(*) FROM quenya_core").fetchone()[0])
    print("带屈折形式的词：%d 条" % con.execute(
        "SELECT COUNT(DISTINCT word_uid) FROM inflect").fetchone()[0])


CONTENT_SPEECH = ("n", "adj", "vb", "adv", "pron", "interj", "phrase", "prep", "conj",
                  "cardinal", "ordinal", "particle")


def pick_daily(con, day=None):
    """按日期确定性地挑一个实词（名词/动词/形容词…），返回 (日期, 词条行)。"""
    day = day or datetime.date.today().isoformat()
    seed = int(day.replace("-", ""))
    where = ("lang IN ('q','nq') AND tier<=1 AND n_refs>0 AND gloss<>'' "
             "AND form NOT LIKE '[%' AND speech IN ("
             + ",".join("?" * len(CONTENT_SPEECH)) + ")")
    args = list(CONTENT_SPEECH)
    total = con.execute("SELECT COUNT(*) FROM word WHERE " + where, args).fetchone()[0]
    if not total:
        return day, None
    idx = random.Random(seed).randrange(total)
    row = con.execute(
        "SELECT * FROM word WHERE " + where + " ORDER BY uid LIMIT 1 OFFSET ?", args + [idx]
    ).fetchone()
    return day, row


def cmd_daily(con, day=None):
    day, row = pick_daily(con, day)
    print("今日一词 · %s" % day)
    print()
    if row is None:
        print("词库里没有符合条件的词。")
        return
    print(fmt_word(con, row, True))
    print("今日一词 · %s" % day)
    print()
    print(fmt_word(con, row, True))


def cmd_check(con, phrase):
    """逐词核对一段昆雅文字是否站得住：命中原文形 / 屈折形 / 查无此词。"""
    import re
    tokens = re.findall(r"[A-Za-zÀ-ÿĀ-ž'’\u00C0-\u024F-]+", phrase)
    tokens = [t for t in tokens if len(t) > 0]
    if not tokens:
        print("没解析出词。")
        return
    ok = infl = bad = 0
    print("逐词核对：%s" % phrase)
    print()
    for t in tokens:
        cands = [t]
        stripped = t.rstrip("'’")
        if stripped != t:
            cands.append(stripped)
        rows = []
        for key in cands:
            rows = con.execute(
                """SELECT * FROM word WHERE form_key = ? AND lang IN ('q','nq','mq','eq','s','ns')
                   ORDER BY CASE lang WHEN 'q' THEN 0 WHEN 'nq' THEN 1 WHEN 'mq' THEN 2 WHEN 'eq' THEN 3 ELSE 4 END,
                            tier LIMIT 3""", (form_key(key),)
            ).fetchall()
            if rows:
                break
        if rows:
            ok += 1
            for j, w in enumerate(rows[:2]):
                mark = (" [%s]" % w["mark"]) if w["mark"] else ""
                lead = ("  %-18s" % t) if j == 0 else "  %-18s" % ""
                print("%s ✓ 等级%d %s%s  “%s”  (%s/%s)" % (
                    lead, w["tier"], TIER_LABEL.get(w["tier"], ""), mark,
                    w["gloss"], w["lang"], (w["speech"] or "")))
                if j == 0 and len(rows) > 1:
                    pass
            if len(rows) > 1:
                print("  %-18s   （同形 %d 条，按语言优先级只列前 2）" % ("", len(rows)))
            continue
        inf = None
        for key in cands:
            inf = con.execute(
                """SELECT w.form AS base, w.gloss, w.lang, w.tier, i.kind, i.form AS shape
                   FROM inflect i JOIN word w ON w.uid = i.word_uid
                   WHERE i.form_key = ? LIMIT 1""", (form_key(key),)
            ).fetchone()
            if inf:
                break
        if inf:
            infl += 1
            print("  %-18s ↳ %s 的 %s 形式（原形 %s：%s，等级%d）" % (
                t, inf["shape"], inf["kind"], inf["base"], inf["gloss"], inf["tier"]))
            continue
        key = form_key(cands[-1])
        # 再试去掉常见词尾
        guess = None
        for suf in ("-", "r", "n", "na", "o", "on", "ion", "llor", "ssë", "nna", "va", "nen", "llo"):
            if key.endswith(suf) and len(key) - len(suf) >= 3:
                base = key[: -len(suf)]
                r2 = con.execute(
                    "SELECT form, gloss, lang, tier FROM word WHERE form_key = ? AND lang IN ('q','nq') LIMIT 1",
                    (base,),
                ).fetchone()
                if r2:
                    guess = (suf, r2)
                    break
        bad += 1
        fk = form_fold(key)
        near = con.execute(
            """SELECT form, gloss, lang, tier FROM word
               WHERE form_fold = ? AND lang IN ('q','nq','mq','eq')
               ORDER BY CASE lang WHEN 'q' THEN 0 WHEN 'nq' THEN 1 WHEN 'mq' THEN 2 ELSE 3 END, tier
               LIMIT 2""", (fk,)
        ).fetchall()
        near_inf = con.execute(
            """SELECT DISTINCT w.form AS base, w.gloss, w.tier, i.form AS shape, i.kind
               FROM inflect i JOIN word w ON w.uid = i.word_uid
               WHERE i.form_fold = ? LIMIT 2""", (fk,)
        ).fetchall()
        if near or near_inf:
            first = True
            for n in near:
                print("  %-18s %s 词库无此形 —— 近形：%s（%s，等级%d）" % (
                    t if first else "", "✗" if first else " ", n["form"], n["gloss"], n["tier"]))
                first = False
            for n in near_inf:
                print("  %-18s %s 词库无此形 —— 近形：%s 的 %s 形式（%s）" % (
                    t if first else "", "✗" if first else " ", n["shape"], n["kind"], n["base"]))
                first = False
            print("  %-18s   ↑ 差别只在长音符/分音符/撇号。昆雅里长音能改变词义，别漏掉" % "")
        elif guess:
            print("  %-18s ? 词库没有此形；可能是 %s + 词尾 -%s" % (t, guess[1]["form"], guess[0]))
        else:
            print("  %-18s ✗ 词库无此形 —— 多半是拼错，或这词根本不成立" % t)
    print()
    print("小计：原文形 %d · 屈折形 %d · 存疑 %d" % (ok, infl, bad))


def cmd_repl(con):
    """交互模式：敲单词就查词，敲一句就逐词核对。"""
    print("昆雅词典 · 交互模式")
    print("  敲一个词   → 查词（含引文、变格、词源）")
    print("  敲一句话   → 逐词核对，标出哪个词不成立")
    print("  /t 一句话  → 转写成 Tengwar")
    print("  /w 词      → 只看简要释义")
    print("  q 回车退出")
    print()
    while True:
        try:
            line = input("昆雅> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in ("q", "quit", "exit", "/q", "/quit"):
            break
        if line.startswith("/t "):
            cmd_tengwar(line[3:].strip(), ["--names"])
            print()
            continue
        if line.startswith("/w "):
            cmd_word(con, line[3:].strip(), set(), set(), 4, False)
            print()
            continue
        if line.startswith("/"):
            print("  只有 /t <句子> 和 /w <词> 两个斜杠命令。")
            continue
        if " " in line:
            print()
            cmd_check(con, line)
            print()
        else:
            hits = con.execute(
                "SELECT COUNT(*) FROM word WHERE form_key = ?",
                (form_key(line),),
            ).fetchone()[0]
            if hits:
                cmd_word(con, line, set(), set(), 3, True)
            else:
                # 不是昆雅词条，按句子核对（会给出近形提示）
                cmd_check(con, line)
            print()


def main():
    args = [a for a in sys.argv[1:]]
    if not args:
        print(__doc__)
        return
    langs, tiers, limit, verbose = set(), set(), 8, True
    tengwar_flag = False
    png_path = None
    pos = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--lang":
            langs = set(x.strip() for x in args[i + 1].split(",") if x.strip()); i += 2
        elif a == "--tier":
            tiers = set(int(x) for x in args[i + 1].split(",") if x.strip()); i += 2
        elif a == "--limit":
            limit = int(args[i + 1]); i += 2
        elif a == "--brief":
            verbose = False; i += 1
        elif a == "--tengwar":
            tengwar_flag = True; i += 1
        elif a == "--png":
            png_path = args[i + 1]; i += 2
        else:
            pos.append(a); i += 1
    if not pos:
        print(__doc__)
        return
    cmd, rest = pos[0], pos[1:]
    con = connect()
    if cmd in ("word", "w"):
        cmd_word(con, rest[0], langs, tiers, limit, verbose)
    elif cmd in ("en", "gloss", "g"):
        cmd_en(con, rest[0], langs, tiers, limit)
    elif cmd in ("id",):
        cmd_id(con, rest[0])
    elif cmd in ("inflect", "i"):
        cmd_inflect(con, rest[0], limit)
    elif cmd in ("stats", "s"):
        cmd_stats(con)
    elif cmd in ("daily", "d"):
        cmd_daily(con, rest[0] if rest else None)
    elif cmd in ("check", "c"):
        cmd_check(con, " ".join(rest))
        if tengwar_flag:
            print()
            print("—— Tengwar 转写 ——")
            cmd_tengwar(" ".join(rest), ["--names"], png=png_path)
    elif cmd in ("tengwar", "t"):
        cmd_tengwar(" ".join(rest), ["--names"], png=png_path)
    elif cmd in ("repl", "r"):
        cmd_repl(con)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
