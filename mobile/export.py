#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把桌面版的课程、原文句子、词库导出成手机网页能直接吃的 JSON。

桌面版的内容生成逻辑（app/course.py）一行没改，这里只是把它的结果
序列化下来——所以手机版和桌面版永远看到同一套 180 词 / 244 句。

用法: python mobile/export.py
"""
import json
import os
import sys
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(HERE, "web")

sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import course as C          # noqa: E402
import elvish as E          # noqa: E402


def word_dict(r):
    return {
        "u": r["uid"],
        "f": r["form"],
        "k": E.form_key(r["form"]),
        "g": r["gloss"],
        "s": r["speech"] or "",
        "t": r["tier"] if r["tier"] is not None else 9,
    }


def sent_dict(con, r):
    return {
        "u": r["uid"],
        "f": r["form"],
        "g": r["gloss"],
        "c": (C.citation_of(con, r, 1) or [""])[0],
    }


def export_dictionary(con, max_tier=9):
    """词库：按 form_key 去重，同一词形优先取昆雅语（q）和低 tier 的那条。

    tier 0 是托老原文确证的形式，越往上越是重建/推测形。查词要能查到冷僻词，
    所以这里不设上限（约 1.2 万条，压缩后仍是几百 KB）；「常用词」那种按
    tier<=1 筛，界面上另算。
    """
    rows = con.execute(
        """SELECT uid, form, gloss, speech, tier, lang, form_key
           FROM word
           WHERE lang IN ('q','nq','mq','eq') AND gloss <> '' AND gloss IS NOT NULL
             AND tier <= ? AND form NOT LIKE '[%'
           ORDER BY CASE lang WHEN 'q' THEN 0 WHEN 'nq' THEN 1 WHEN 'mq' THEN 2 ELSE 3 END,
                    tier ASC, uid""",
        (max_tier,),
    ).fetchall()
    out, seen = [], set()
    for r in rows:
        k = r["form_key"] or E.form_key(r["form"])
        if not k or k in seen:
            continue
        seen.add(k)
        out.append([r["form"], r["gloss"], r["speech"] or "",
                    r["tier"] if r["tier"] is not None else 9])
    return out


def export_hot(con, n=30):
    """「常用词」：按 Eldamo 里引文条数排，引文多 = 托老原文真用得多的词。

    只取 q/nq（昆雅、新昆雅）。mq/eq 那批早期/中期昆雅的 n_refs 是词源引用数
    （tulu- 能到 644 条），把它们混进来会让「常用词」变成一列冷僻词。
    """
    rows = con.execute(
        """SELECT form, gloss, speech, tier, form_key FROM word
           WHERE lang IN ('q','nq') AND gloss <> '' AND gloss IS NOT NULL
             AND tier <= 1 AND n_refs > 0 AND speech <> 'phrase' AND form NOT LIKE '[%'
           ORDER BY n_refs DESC, uid""").fetchall()
    out, seen = [], set()
    for r in rows:
        k = r["form_key"] or E.form_key(r["form"])
        if not k or k in seen:
            continue
        seen.add(k)
        out.append([r["form"], r["gloss"], r["speech"] or "",
                    r["tier"] if r["tier"] is not None else 9])
        if len(out) >= n:
            break
    return out


def main():
    if not os.path.isdir(WEB):
        sys.exit("找不到 %s" % WEB)
    con = C.connect()

    units, chapters = [], []
    bd = {}

    for node in C.build_path(con):
        is_sent = str(node.get("uid", "")).startswith("S.")
        if is_sent:
            lessons = []
            for les in node["lessons"]:
                sents = []
                for r in les["sents"]:
                    sents.append(sent_dict(con, r))
                    bd[str(r["uid"])] = [
                        [tok, g, t] for (tok, g, t, _note) in C.breakdown(con, r["form"])
                    ]
                lessons.append({"id": les["lid"], "t": les["title"], "sents": sents})
            chapters.append({
                "id": node["uid"], "t": node["title"],
                "l": node.get("label", ""), "lessons": lessons,
            })
        else:
            lessons = []
            for les in node["lessons"]:
                lessons.append({
                    "id": les["lid"], "t": les["title"],
                    "words": [word_dict(r) for r in les["words"]],
                })
            units.append({
                "id": node["uid"], "t": node["title"],
                "l": node.get("label", ""), "lessons": lessons,
            })

    dic = export_dictionary(con)
    hot = export_hot(con)
    data = {
        "generated": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
        "units": units,
        "chapters": chapters,
        "dict": dic,
        "hot": hot,
        "bd": bd,
    }

    os.makedirs(WEB, exist_ok=True)
    out = os.path.join(WEB, "data.json")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, out)

    n_words = sum(len(les["words"]) for u in units for les in u["lessons"])
    n_sents = sum(len(les["sents"]) for c in chapters for les in c["lessons"])
    n_lessons = sum(len(u["lessons"]) for u in units) + sum(len(c["lessons"]) for c in chapters)
    print("课程单元 %d · 阅读章 %d · 节 %d" % (len(units), len(chapters), n_lessons))
    print("词汇 %d · 原文句 %d · 词库 %d 条 · 拆解 %d 句" % (n_words, n_sents, len(dic), len(bd)))
    print("写出 %s  %.1f KB" % (out, os.path.getsize(out) / 1024.0))


if __name__ == "__main__":
    main()
