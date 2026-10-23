#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""课程与记忆排期层（不含界面）。

设计参照两件事：
  · Duolingo 的循环——一节短课（6 词）、必须主动产出、即时反馈、错题当堂回来、连胜/XP 驱动每天回来；
  · Anki 的核心——间隔重复，答对拉长间隔，答错打回 1 天。

课程内容不是手写的，而是从 Eldamo 词库里**按语义大类 + 引文条数**自动生成：
引文多 = 托老原文用得多的词，先学。所以越靠前的课越实用。
"""
import os
import re
import json
import hashlib
import random
import datetime
import subprocess
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)

import elvish as E            # noqa: E402
import render_tengwar as RT   # noqa: E402

DB = os.path.join(ROOT, "data", "elvish.db")
PROG = os.path.join(ROOT, "data", "progress.json")
TW_CACHE = os.path.join(ROOT, "data", "tw_cache")

CONTENT_SPEECH = ("n", "adj", "vb", "adv", "pron", "interj", "phrase",
                  "prep", "conj", "cardinal", "ordinal", "particle")

# 初学者的课程顺序：先具体、能马上用（人/食物/自然/动物），再数量时间空间，语法虚词放后面。
# 别按"引文多少"排——那样第一课全是 lá- / i / á 这种虚词，没人学得下去。
PATH = [
    ("MK", "人"),
    ("FD", "食物与饮料"),
    ("PW", "自然与世界"),
    ("AN", "动物"),
    ("QN", "数量与数"),
    ("BP", "身体"),
    ("TM", "时间"),
    ("SR", "空间与方位"),
    ("PA", "动作与材料"),
    ("GR", "基本语词"),
]

WORDS_PER_LESSON = 6
LESSONS_PER_UNIT = 3

# 间隔阶梯（天）。SM-2 的简化版：答对上一级，答错回到 1 天
LADDER = [1, 2, 4, 8, 16, 32, 64]


# ---------------------------------------------------------------- 数据

def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def _learnable_sql(cat_group):
    return ("""SELECT w.*, c.group_id, c.group_label, c.label AS cat_label
               FROM word w JOIN cat c ON c.id = w.cat
               WHERE c.group_id = ? AND w.lang IN ('q','nq') AND w.tier <= 1
                 AND w.n_refs > 0 AND w.gloss <> '' AND w.form NOT LIKE '[%'
                 AND w.speech IN ("""
            + ",".join("?" * len(CONTENT_SPEECH))
            + ") ORDER BY w.n_refs DESC, w.tier ASC, w.uid")


def unit_words(con, group_id):
    return con.execute(_learnable_sql(group_id), (group_id, *CONTENT_SPEECH)).fetchall()


def build_path(con):
    """返回课程路径：[{uid,title,group,lessons:[{lid,title,words|sents,kind}]}]"""
    out = []
    for gi, (gid, title) in enumerate(PATH):
        ws = unit_words(con, gid)
        lessons = []
        for li in range(LESSONS_PER_UNIT):
            chunk = ws[li * WORDS_PER_LESSON:(li + 1) * WORDS_PER_LESSON]
            if len(chunk) < 4:
                continue
            lessons.append({"lid": "%s.%d" % (gid, li + 1),
                            "title": "%s %d" % (title, li + 1),
                            "kind": "word", "words": chunk})
        if lessons:
            r = con.execute("SELECT group_label FROM cat WHERE group_id=? LIMIT 1", (gid,)).fetchone()
            out.append({"uid": gid, "title": title,
                        "label": r["group_label"] if r else title,
                        "lessons": lessons})

    # 阅读线：按原文出处分章，全部原文句子都进来
    for ch in sentence_chapters(con):
        out.append(ch)
    return out


# ---------------------------------------------------------------- 进度 / SRS

def _today():
    return datetime.date.today()


def load_progress():
    if os.path.exists(PROG):
        try:
            with open(PROG, encoding="utf-8-sig") as f:
                p = json.load(f)
        except Exception:
            p = {}
    else:
        p = {}
    p.setdefault("cards", {})
    p.setdefault("xp", {})
    p.setdefault("done", [])
    p.setdefault("streak", {"count": 0, "last": None})
    return p


def save_progress(p):
    tmp = PROG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PROG)


def card_key(row):
    return "%s|%s" % (row["lang"], E.form_key(row["form"]))


def due_cards(p, limit=12):
    today = _today().isoformat()
    due = []
    for k, c in p["cards"].items():
        if c.get("due", "9999") <= today:
            due.append((c.get("due", ""), k))
    due.sort()
    return [k for _, k in due[:limit]]


def grade(p, row, correct, kind="review"):
    """答对拉长间隔，答错打回 1 天。返回新的间隔天数。"""
    k = card_key(row)
    c = p["cards"].get(k) or {"iv": 0, "reps": 0, "lapses": 0, "ef": 2.5}
    if correct:
        step = LADDER.index(c["iv"]) + 1 if c["iv"] in LADDER else 1
        c["iv"] = LADDER[min(step, len(LADDER) - 1)]
        c["reps"] = c.get("reps", 0) + 1
        c["ef"] = min(3.0, c.get("ef", 2.5) + 0.05)
    else:
        c["iv"] = 1
        c["lapses"] = c.get("lapses", 0) + 1
        c["ef"] = max(1.3, c.get("ef", 2.5) - 0.15)
        c["reps"] = 0
    c["due"] = (_today() + datetime.timedelta(days=c["iv"])).isoformat()
    c["uid"] = row["uid"]
    c["form"] = row["form"]
    c["gloss"] = row["gloss"]
    c["lang"] = row["lang"]
    c["last"] = _today().isoformat()
    p["cards"][k] = c
    return c["iv"]


def rows_by_uids(con, uids):
    if not uids:
        return []
    q = "SELECT * FROM word WHERE uid IN (%s)" % ",".join("?" * len(uids))
    rows = {r["uid"]: r for r in con.execute(q, list(uids))}
    return [rows[u] for u in uids if u in rows]


def due_rows(con, p, limit=12):
    keys = due_cards(p, limit)
    uids = []
    for k in keys:
        u = p["cards"].get(k, {}).get("uid")
        if u:
            uids.append(u)
    return rows_by_uids(con, uids)


def add_xp(p, n):
    d = _today().isoformat()
    p["xp"][d] = p["xp"].get(d, 0) + n


def xp_today(p):
    return p["xp"].get(_today().isoformat(), 0)


def touch_streak(p):
    s = p["streak"]
    d = _today()
    last = s.get("last")
    if last == d.isoformat():
        return s["count"]
    y = (d - datetime.timedelta(days=1)).isoformat()
    s["count"] = (s.get("count", 0) + 1) if last == y else 1
    s["last"] = d.isoformat()
    return s["count"]


def mastery(p):
    """已进入复习阶段的卡片数 / 总卡片数。"""
    total = len(p["cards"])
    strong = sum(1 for c in p["cards"].values() if c.get("iv", 0) >= 8)
    return strong, total


# ---------------------------------------------------------------- 题目

def _short(gloss, n=46):
    g = (gloss or "").split(";")[0].split(",")[0].strip()
    return g if len(g) <= n else g[:n] + "…"


def display_form(form):
    """界面展示用的词形：去掉 Eldamo 区分同形词的 ¹²³ 上标、以及 amil(lë) 这种可选成分标记。"""
    f = E.form_key(form or "")
    f = re.sub(r"\s*\([^)]*\)", "", f)
    return f.strip()


def _distractors(row, pool, k=3):
    """同义类里取干扰项：越像越难，也越能逼你分辨。"""
    seen = {E.form_key(row["form"])}
    cands = []
    for w in pool:
        fk = E.form_key(w["form"])
        if fk in seen or not w["gloss"]:
            continue
        seen.add(fk)
        cands.append(w)
    random.shuffle(cands)
    return cands[:k]


def tengwar_png(form, charset="tengwar_telcontar"):
    """词形 → Tengwar 图片（带缓存）。"""
    os.makedirs(TW_CACHE, exist_ok=True)
    node = E.find_node()
    if not node:
        return None
    h = hashlib.sha1((form + "|" + charset).encode("utf-8")).hexdigest()[:16]
    png = os.path.join(TW_CACHE, h + ".png")
    if os.path.exists(png):
        return png
    r = subprocess.run([node, os.path.join(TOOLS, "tengwar.mjs"), form, "--json",
                        "--charset", charset], capture_output=True)
    if r.returncode != 0:
        return None
    try:
        tw = json.loads(r.stdout.decode("utf-8", "replace"))["tengwar"]
    except Exception:
        return None
    RT.render(tw, png, size=64, max_width=760, caption=None)
    return png


def make_question(row, pool, kinds=None):
    """生成一道题。返回 dict：kind/prompt/options/answer/note"""
    kinds = kinds or ["k2e", "e2k", "spell", "tengwar"]
    kind = random.choice(kinds)
    wrong = _distractors(row, pool, 3)
    form = display_form(row["form"])
    gloss = _short(row["gloss"])

    if kind in ("k2e",) and len(wrong) >= 3:
        opts = [gloss] + [_short(w["gloss"]) for w in wrong]
        random.shuffle(opts)
        return {"kind": "k2e", "kind_cn": "这个词什么意思",
                "prompt": form, "prompt_sub": "昆雅",
                "options": opts, "answer": gloss,
                "row": row, "note": None}

    if kind == "e2k" and len(wrong) >= 3:
        opts = [form] + [display_form(w["form"]) for w in wrong]
        random.shuffle(opts)
        return {"kind": "e2k", "kind_cn": "选昆雅词",
                "prompt": gloss, "prompt_sub": "意思",
                "options": opts, "answer": form,
                "row": row, "note": None}

    if kind == "tengwar" and len(wrong) >= 3:
        png = tengwar_png(form)
        if png:
            opts = [form] + [display_form(w["form"]) for w in wrong]
            random.shuffle(opts)
            return {"kind": "tengwar", "kind_cn": "读出精灵文字母",
                    "prompt": png, "prompt_sub": "Tengwar",
                    "options": opts, "answer": form,
                    "row": row, "note": None}

    # 兜底：拼写
    return {"kind": "spell", "kind_cn": "写出昆雅词",
            "prompt": gloss, "prompt_sub": "意思",
            "options": None, "answer": form,
            "hint": form[:1] + "…", "row": row, "note": None}


def check_spelling(typed, answer):
    """宽松判分：忽略重音/撇号差异，但会告诉你差在哪。"""
    t, a = E.form_fold(typed.strip()), E.form_fold(answer.strip())
    if t == a:
        if typed.strip() != answer.strip():
            return True, "答对了，不过注意重音符号：**%s**" % answer
        return True, None
    return False, None


def citation_of(con, row, limit=2):
    rows = con.execute("SELECT src, gloss FROM ref WHERE word_uid=? ORDER BY id LIMIT ?",
                       (row["uid"], limit)).fetchall()
    return [r["src"] for r in rows]


# ---------------------------------------------------------------- 真句子
# 不是造出来的例句：这些是 Eldamo 里 speech='phrase' 的词条，
# 也就是托老原文里真实出现过的整句（有名有出处），我们只是拿来当阅读材料。

SENT_MIN_WORDS = 4
SENT_MAX_WORDS = 11


def _word_count(s):
    return len([t for t in s.split() if t])


def sentences(con, limit=200):
    """可用的原文句子：4–11 个词、有引文、有译文。"""
    q = """SELECT w.*, c.group_label FROM word w LEFT JOIN cat c ON c.id = w.cat
           WHERE w.speech = 'phrase' AND w.lang IN ('q','nq','mq','eq')
             AND w.gloss <> '' AND w.n_refs > 0 AND w.tier <= 1
             AND w.form LIKE '% %'
           ORDER BY w.n_refs DESC, LENGTH(w.form)"""
    out = []
    for r in con.execute(q):
        n = _word_count(r["form"])
        if not (SENT_MIN_WORDS <= n <= SENT_MAX_WORDS):
            continue
        g = r["gloss"] or ""
        # 跳过残缺的译文（Eldamo 用 [..] 标缺、* 标重建、@@@ 标待定）
        if "@@@" in g or g.strip().startswith("*"):
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


def tokens(form):
    """按空格切词，标点跟着词走（昆雅里撇号可能是词的一部分）。"""
    return [t for t in (form or "").split(" ") if t]


SPEECH_CN = {"n": "名", "adj": "形", "vb": "动", "adv": "副", "pron": "代", "prep": "介",
             "conj": "连", "interj": "叹", "particle": "助", "cardinal": "数", "ordinal": "序",
             "phrase": "短语", "suf": "后缀", "pref": "前缀", "root": "词根"}


def gloss_token(con, tok):
    """给一个词形找释义。

    顺序：先查屈折形，再查原形。理由是屈折表里只收"原文里真的出现过"的形式——
    句子本来就出自原文，所以命中屈折表的可能性很大；而原形查询会遇到同形异义
    （nauva 既是「巨人」也是 na- 的将来时，句子里的显然是后者）。
    返回 (释义, 等级, 说明)。
    """
    key = E.form_key(tok.strip(".,:;!?\"'“”()[]·"))
    if not key:
        return None, 9, None

    def by_key(k):
        return con.execute(
            """SELECT gloss, tier, form, speech FROM word
               WHERE form_key = ? AND lang IN ('q','nq','mq','eq') AND gloss <> ''
               ORDER BY CASE lang WHEN 'q' THEN 0 WHEN 'nq' THEN 1 WHEN 'mq' THEN 2 ELSE 3 END, tier
               LIMIT 3""", (k,)).fetchall()

    def by_fold(k):
        return con.execute(
            """SELECT gloss, tier, form FROM word
               WHERE form_fold = ? AND lang IN ('q','nq','mq','eq') AND gloss <> ''
               ORDER BY CASE lang WHEN 'q' THEN 0 WHEN 'nq' THEN 1 WHEN 'mq' THEN 2 ELSE 3 END, tier
               LIMIT 1""", (E.form_fold(k),)).fetchone()

    def inflect(k, fold=False):
        col = "form_fold" if fold else "form_key"
        val = E.form_fold(k) if fold else k
        return con.execute(
            """SELECT w.gloss, w.tier, w.form, i.kind FROM inflect i JOIN word w ON w.uid = i.word_uid
               WHERE i.%s = ? AND w.gloss <> '' LIMIT 1""" % col, (val,)).fetchone()

    # 1) 屈折形优先（屈折表只收原文里真出现过的形式）
    #    但同形异义时两条都给出来——没有上下文的话，「i」既是 he 的复数，也是冠词。
    cands = []
    r = inflect(key)
    if r:
        cands.append("%s（%s）" % (_short(r["gloss"], 30), (r["kind"] or "").split()[0]))
        src_row = r
    for x in by_key(key):
        g = _short(x["gloss"], 30)
        tag = SPEECH_CN.get(x["speech"] or "", "")
        s = "%s（%s）" % (g, tag) if tag else g
        if not any(g in c for c in cands):
            cands.append(s)
        if len(cands) >= 2:
            break
    if cands:
        tier = src_row["tier"] if r else 0
        return " · ".join(cands[:2]), tier, None
    # 3) 去重音、去重音屈折
    r = by_fold(key)
    if r:
        return "%s（重音不同）" % _short(r["gloss"], 32), r["tier"], None
    r = inflect(key, fold=True)
    if r:
        return "%s（%s）" % (_short(r["gloss"], 30), (r["kind"] or "").split()[0]), r["tier"], r["form"]
    # 4) 去尾再试（昆雅的格词尾、变位词尾）
    for suf in ("-", "r", "n", "o", "on", "ion", "na", "ssë", "nna", "llo", "va", "nen"):
        if key.endswith(suf) and len(key) - len(suf) >= 3:
            base = key[:-len(suf)]
            r2 = by_key(base)
            if r2:
                return "~%s（推测 +%s）" % (_short(r2[0]["gloss"], 26), suf), 9, base
    return None, 9, None


def breakdown(con, form):
    """整句逐词拆解：[(词, 释义, 等级, 说明)]"""
    out = []
    for t in tokens(form):
        g, tier, note = gloss_token(con, t)
        out.append((t, g, tier, note))
    return out


def sentence_lessons(con, per_lesson=4, lessons=3):
    """把原文句子切成几节课（老接口，保留给单章场景）。"""
    rows = sentences(con, per_lesson * lessons)
    out = []
    for i in range(lessons):
        chunk = rows[i * per_lesson:(i + 1) * per_lesson]
        if len(chunk) < 2:
            break
        out.append({"lid": "SENT.%d" % (i + 1), "title": "真句子 %d" % (i + 1), "sents": chunk})
    return out


def sentence_chapters(con, per_lesson=4, limit=320):
    """按原文出处把句子分章——同一篇文章的句子连着读，比随机混排有用。
    返回 [{uid,title,label,lessons:[{lid,title,kind:'sent',sents}]}]"""
    rows = sentences(con, limit)
    groups = {}
    for r in rows:
        cits = citation_of(con, r, 1)
        pfx = cits[0].split("/")[0] if cits else "?"
        groups.setdefault(pfx, []).append(r)

    out = []
    for pfx, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(rs) < 2:
            continue
        row_src = con.execute("SELECT name FROM source WHERE prefix=?", (pfx,)).fetchone()
        full = row_src["name"] if row_src and row_src["name"] else pfx
        lessons = []
        for i in range(0, len(rs), per_lesson):
            chunk = rs[i:i + per_lesson]
            if len(chunk) < 2 and lessons:
                lessons[-1]["sents"].extend(chunk)   # 尾巴并进上一课，别留一节的孤儿
                continue
            lessons.append({
                "lid": "S.%s.%d" % (pfx.replace(".", "_"), i // per_lesson + 1),
                "title": "%s %d" % (pfx, i // per_lesson + 1),
                "kind": "sent", "sents": chunk,
            })
        if not lessons:
            continue
        out.append({"uid": "S." + pfx, "title": full if len(full) <= 22 else full[:21] + "…",
                    "label": "%s · %d 句" % (pfx, len(rs)), "lessons": lessons})
    return out


def make_sentence_question(row, pool):
    """句子题：句子→意思，或者把打散的词块拼回去。"""
    kinds = ["sent2gloss", "order"]
    kind = random.choice(kinds)
    gloss = _short(row["gloss"], 70)
    if kind == "sent2gloss" and len(pool) >= 4:
        others = [w for w in pool if w["uid"] != row["uid"] and w["gloss"]]
        random.shuffle(others)
        opts = [gloss] + [_short(w["gloss"], 70) for w in others[:3]]
        if len(opts) == 4:
            random.shuffle(opts)
            return {"kind": "sent2gloss", "kind_cn": "这句话是什么意思",
                    "prompt": row["form"], "prompt_sub": "托老原文", "options": opts,
                    "answer": gloss, "row": row, "note": None}
    # 词块排序
    toks = tokens(row["form"])
    shuffled = toks[:]
    for _ in range(8):
        random.shuffle(shuffled)
        if shuffled != toks:
            break
    return {"kind": "order", "kind_cn": "把词块拼成原句",
            "prompt": gloss, "prompt_sub": "意思", "options": None,
            "answer": " ".join(toks), "chips": shuffled, "target": toks,
            "row": row, "note": None}
