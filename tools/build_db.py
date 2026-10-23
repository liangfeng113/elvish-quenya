#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 Eldamo 的 eldamo-data.xml 解析成可查的 SQLite 词库。

数据来源: https://eldamo.org  (v0.8.13, CC-BY 4.0, © Paul Strack)
产物: data/elvish.db

用法: python build_db.py [xml路径] [db路径]
"""
import os
import re
import sqlite3
import sys
import html
import unicodedata
from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
XML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "eldamo-data.xml")
DB = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "data", "elvish.db")

# 可靠性标记 -> (等级, 中文说明)，等级越小越可靠
MARKS = {
    "": (0, "托老原文证实"),
    "#": (1, "可由原文词按规则推导，或仅作为复合词成分出现"),
    "*": (2, "未直接出现，但可比对同源词合理重建"),
    "\u2020": (3, "托老用于古语或诗歌体，现代口语不用"),
    "^": (4, "由早期语言版本改写而来，后世昆雅未必认"),
    "?": (5, "推测性较强"),
    "\u203d": (5, "托老自己在原文里打了个问号"),
    "!": (6, "纯新造词（其他作者发明，非托老）"),
    "-": (7, "Eldamo 特殊标记 -"),
    "|": (7, "Eldamo 特殊标记 |"),
    "\u26a0\ufe0f": (9, "Eldamo 自己不建议在新昆雅写作中使用"),
}

LANGS = {}   # id -> (name, parent, period)

SUP = "\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079"


def form_key(s):
    """匹配用的规范化形：去掉同形词的上标编号、统一撇号、折叠大小写。
    Eldamo 用 a¹ / a² / pharaz² 区分同形异义词，撇号用的是 ’ 而非 '。"""
    if not s:
        return ""
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u02bc", "'")
    s = s.translate({ord(c): None for c in SUP})
    return s.casefold().strip()


def form_fold(s):
    """去掉全部变音符号和撇号的形，用来在用户漏写长音符时找近形（sila → síla）。"""
    k = form_key(s)
    k = k.replace("'", "")
    d = unicodedata.normalize("NFD", k)
    return "".join(c for c in d if unicodedata.category(c) != "Mn")


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</p>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def split_source(src):
    """'PE17/040.2712' -> ('PE17', '040.2712')"""
    if not src:
        return (None, None)
    if "/" in src:
        a, b = src.split("/", 1)
        return (a, b)
    return (src, None)


def mark_rank(mark):
    return MARKS.get(mark or "", (7, "未记载的标记")).__getitem__(0)


def main():
    if not os.path.exists(XML):
        sys.exit(
            "找不到 %s\n\n"
            "原始 XML 不再随仓库分发（28.9 MB，可由 CC-BY 原始数据重新获取）。\n"
            "先跑一次下载：\n"
            "    node tools/fetch-eldamo.mjs data/eldamo-data.xml\n"
            "再重跑本脚本。" % XML)
    print("parsing %s ..." % XML)
    root = etree.parse(XML, etree.XMLParser(huge_tree=True, remove_comments=True)).getroot()
    print("version %s" % root.get("version"))

    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    con.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        CREATE TABLE language(
            id TEXT PRIMARY KEY, name TEXT, parent TEXT, period TEXT);
        CREATE TABLE source(
            prefix TEXT PRIMARY KEY, name TEXT, type TEXT, cite TEXT, notes TEXT);
        CREATE TABLE cat(
            id TEXT PRIMARY KEY, label TEXT, num TEXT, group_id TEXT, group_label TEXT);
        CREATE TABLE word(
            uid INTEGER PRIMARY KEY,
            page_id TEXT,
            parent_uid INTEGER,
            depth INTEGER,
            lang TEXT,
            form TEXT,
            form_key TEXT,
            form_fold TEXT,
            speech TEXT,
            gloss TEXT,
            mark TEXT,
            tier INTEGER,
            cat TEXT,
            created TEXT,
            notes TEXT,
            n_refs INTEGER DEFAULT 0,
            neo_version TEXT
        );
        CREATE TABLE ref(
            id INTEGER PRIMARY KEY,
            word_uid INTEGER,
            form TEXT,
            src TEXT,
            src_prefix TEXT,
            src_page TEXT,
            gloss TEXT,
            rl TEXT,
            rule TEXT,
            from_form TEXT
        );
        CREATE TABLE inflect(
            ref_id INTEGER, word_uid INTEGER, form TEXT, form_key TEXT, form_fold TEXT,
            kind TEXT, variant TEXT);
        CREATE TABLE element(
            word_uid INTEGER, lang TEXT, form TEXT, kind TEXT);
        CREATE TABLE cognate(
            word_uid INTEGER, form TEXT, src TEXT);
        CREATE TABLE deriv(
            word_uid INTEGER, form TEXT, src TEXT, rule TEXT, from_form TEXT);
        CREATE INDEX ix_word_form ON word(form COLLATE NOCASE);
        CREATE INDEX ix_word_key ON word(form_key);
        CREATE INDEX ix_word_fold ON word(form_fold);
        CREATE INDEX ix_word_gloss ON word(gloss COLLATE NOCASE);
        CREATE INDEX ix_inflect_key ON inflect(form_key);
        CREATE INDEX ix_inflect_fold ON inflect(form_fold);
        CREATE INDEX ix_word_lang ON word(lang);
        CREATE INDEX ix_word_tier ON word(tier);
        CREATE INDEX ix_ref_word ON ref(word_uid);
        CREATE INDEX ix_inflect_word ON inflect(word_uid);
        CREATE INDEX ix_element_word ON element(word_uid);
        """
    )

    # ---- languages ----
    period_of_cat = {"neo": "Neo (近代重构)", "late": "Late 1950-1973",
                     "middle": "Middle 1930-1950", "early": "Early 1910-1930"}
    lang_rows = []

    def walk_lang(el, parent, period):
        for c in el:
            if etree.QName(c).localname != "language":
                continue
            lid = c.get("id")
            LANGS[lid] = (c.get("name"), parent, period)
            lang_rows.append((lid, c.get("name"), parent, period))
            walk_lang(c, lid, period)

    for cat in root:
        if etree.QName(cat).localname == "language-cat":
            p = period_of_cat.get(cat.get("id"), cat.get("name"))
            walk_lang(cat, None, p)
    con.executemany("INSERT INTO language VALUES (?,?,?,?)", lang_rows)
    print("languages: %d" % len(lang_rows))

    # ---- sources ----
    src_rows = []
    for s in root:
        if etree.QName(s).localname == "source":
            src_rows.append((s.get("prefix"), s.get("name"), s.get("type"),
                             strip_html("".join(s.itertext("cite"))),
                             strip_html((s.findtext("notes") or ""))[:1500]))
    con.executemany("INSERT OR REPLACE INTO source VALUES (?,?,?,?,?)", src_rows)
    print("sources: %d" % len(src_rows))

    # ---- categories ----
    cat_rows = []
    for c in root:
        if etree.QName(c).localname == "cats":
            for g in c:
                for cc in g:
                    cat_rows.append((cc.get("id"), cc.get("label"), cc.get("num"),
                                     g.get("id"), g.get("label")))
    con.executemany("INSERT OR REPLACE INTO cat VALUES (?,?,?,?,?)", cat_rows)
    print("cats: %d" % len(cat_rows))

    # ---- words (recursive) ----
    words = refs = inflects = elements = cognates = derivs = 0
    uid = [0]
    rid = [0]
    buf_w, buf_r, buf_i, buf_e, buf_c, buf_d = [], [], [], [], [], []
    nref_pairs = []

    def flush():
        if buf_w:
            con.executemany("INSERT INTO word VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", buf_w)
            buf_w.clear()
        for tbl, b, cols in (("ref", buf_r, 10), ("inflect", buf_i, 7),
                             ("element", buf_e, 4), ("cognate", buf_c, 3),
                             ("deriv", buf_d, 5)):
            if b:
                con.executemany("INSERT INTO %s VALUES (%s)" % (tbl, ",".join("?" * cols)), b)
                b.clear()
        con.commit()

    def handle_word(el, parent_uid, depth):
        nonlocal words, refs, inflects, elements, cognates, derivs
        uid[0] += 1
        u = uid[0]
        words += 1
        mark = el.get("mark") or ""
        tier = mark_rank(mark)
        buf_w.append((
            u, el.get("page-id"), parent_uid, depth, el.get("l"),
            el.get("v"), form_key(el.get("v")), form_fold(el.get("v")),
            el.get("speech"), el.get("gloss"), mark, tier, el.get("cat"),
            el.get("created"),
            strip_html((el.findtext("notes") or ""))[:2000],
            0, el.get("neo-version"),
        ))
        n_ref = 0
        for c in el:
            tag = etree.QName(c).localname
            if tag == "ref":
                n_ref += 1
                refs += 1
                rid[0] += 1
                rid_now = rid[0]
                src = c.get("source")
                pfx, page = split_source(src)
                buf_r.append((rid_now, u, c.get("v"), src, pfx, page, c.get("gloss"),
                              c.get("rl"), c.get("rule"), c.get("from")))
                for g in c:
                    gt = etree.QName(g).localname
                    if gt == "inflect":
                        inflects += 1
                        buf_i.append((rid_now, u, c.get("v"), form_key(c.get("v")),
                                      form_fold(c.get("v")), g.get("form"), g.get("variant")))
                    elif gt == "cognate":
                        cognates += 1
                        buf_c.append((u, g.get("v"), g.get("source")))
                    elif gt == "deriv":
                        derivs += 1
                        buf_d.append((u, g.get("v"), g.get("source"), g.get("rule"), g.get("from")))
                # ref 第一层没有 inflect 时，也可能 word 下直接有 inflect-table
            elif tag == "element":
                elements += 1
                buf_e.append((u, c.get("l"), c.get("v"), c.get("form")))
            elif tag == "cognate":
                cognates += 1
                buf_c.append((u, c.get("v"), c.get("source")))
            elif tag == "deriv":
                derivs += 1
                buf_d.append((u, c.get("v"), c.get("source"), c.get("rule"), c.get("from")))
            elif tag == "word":
                handle_word(c, u, depth + 1)
        nref_pairs.append((n_ref, u))
        if len(buf_w) > 4000:
            flush()

    for el in root:
        if etree.QName(el).localname == "word":
            handle_word(el, None, 0)
    flush()
    con.executemany("UPDATE word SET n_refs=? WHERE uid=?", nref_pairs)
    con.commit()

    # ref.id 已按文档顺序显式赋值，inflect.ref_id 直接就是它
    con.commit()

    print("words: %d  refs: %d  inflects: %d  elements: %d  cognates: %d  derivs: %d"
          % (words, refs, inflects, elements, cognates, derivs))

    # ---- 面向学习者的视图 ----
    con.executescript(
        """
        CREATE VIEW quenya_core AS
          SELECT * FROM word
          WHERE lang IN ('q','nq','mq','eq') AND tier <= 2 AND gloss IS NOT NULL AND gloss <> ''
          ORDER BY tier, form;
        CREATE VIEW quenya_q AS SELECT * FROM word WHERE lang='q';
        """
    )
    n_core = con.execute("SELECT COUNT(*) FROM quenya_core").fetchone()[0]
    for plan in (
        "SELECT lang, COUNT(*) FROM word GROUP BY lang ORDER BY 2 DESC LIMIT 12",
        "SELECT tier, COUNT(*) FROM word WHERE lang IN ('q','nq') GROUP BY tier ORDER BY 1",
    ):
        print("  " + " | ".join("%s=%s" % r for r in con.execute(plan)))
    print("quenya_core(lang q/nq/mq/eq, tier<=2): %d" % n_core)
    con.close()
    print("OK -> %s (%.1f MB)" % (DB, os.path.getsize(DB) / 1048576))


if __name__ == "__main__":
    main()
