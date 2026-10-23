#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""昆雅 · 学（Duolingo 的循环 + Anki 的排期）

学习页：课程路径（10 个语义单元 × 3 节 × 6 词，从词库自动生成）
上课：  每词先看卡 → 立刻考 → 课尾混考；答错扣心，答对加连击
复习页：到期卡片按间隔重复队列排队
查词 / 造句：保留原来的词典与 Tengwar 能力
"""
import os
import sys
import io
import json
import random
import datetime
import contextlib
import subprocess
import threading

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
APP = os.path.join(ROOT, "app")
sys.path.insert(0, TOOLS)
sys.path.insert(0, APP)

# pythonw 下没有控制台：stdout/stderr 都是 None。下面这些模块里可能有 print 调用，
# 给个黑洞兜住，否则一次 print 就能让整个窗口起不来。
if sys.stdout is None or sys.stderr is None:
    class _Sink:
        def write(self, *a): pass
        def flush(self): pass
        def isatty(self): return False
        encoding = "utf-8"
    if sys.stdout is None:
        sys.stdout = _Sink()
    if sys.stderr is None:
        sys.stderr = _Sink()

import elvish as E          # noqa: E402
import render_tengwar as RT  # noqa: E402
import course as C          # noqa: E402

BG = "#f6f3ec"
PANEL = "#fffdf8"
FG = "#1c1a17"
MUTED = "#7a7266"
LINE = "#e2dbcd"
ACCENT = "#8a5a2b"
GREEN = "#2f8f4e"
GREEN_BG = "#e8f5ec"
RED = "#c0392b"
RED_BG = "#fdeceb"
GOLD = "#c98a1f"
LOCK = "#b8b0a2"

GLYPH_FONT = os.path.join(ROOT, "assets", "tengwar-font", "FreeMonoTengwar.2013-07-21", "FreeMonoTengwar.ttf")

SERIF = "Georgia"
SANS = "Microsoft YaHei UI"
MONO = "Consolas"

DAILY_GOAL = 30
HEARTS = 3

LANG_SHORT = {
    "q": "Q.", "nq": "NQ.", "mq": "MQ.", "eq": "EQ.", "s": "S.", "ns": "NS.",
    "n": "N.", "on": "ON.", "g": "G.", "p": "P.", "mp": "MP.", "ep": "EP.",
    "t": "T.", "ad": "Ad.", "ilk": "Ilk.", "dan": "Dan.", "en": "EN.", "np": "NP.",
}


def dpi_aware():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


class LearnApp(tk.Tk):
    def __init__(self):
        super().__init__()
        dpi_aware()
        self.title("昆雅 · 学")
        self.geometry("1100x800")
        self.minsize(960, 720)
        self.configure(bg=BG)
        self.con = C.connect()
        self.prog = C.load_progress()
        self.prog.setdefault("settings", {"tts": True, "speed": 135})
        self.prog["settings"].setdefault("refbar", True)
        self.path = C.build_path(self.con)
        self.lesson = None
        self.speaker = None
        self._glyph_cache = {}
        self._style()
        self._build()
        self.refresh_meta()
        self.overlay = None
        threading.Thread(target=self._init_speech, daemon=True).start()

    # ------------------------------------------------------------ 语音
    def _init_speech(self):
        try:
            import speech as S
            self.speaker = S.Speaker(speed=self.prog["settings"].get("speed", 135))
        except Exception as e:
            self.speaker = None
            print("语音初始化失败:", e)

    def tts_on(self):
        return bool(self.prog["settings"].get("tts", True))

    def say(self, text):
        sp = self.speaker
        if sp and sp.ok and text:
            try:
                sp.say(text)
            except Exception:
                pass

    def say_if_on(self, text):
        if self.tts_on():
            self.say(text)

    def toggle_tts(self):
        v = not self.tts_on()
        self.prog["settings"]["tts"] = v
        C.save_progress(self.prog)
        self.tts_btn.configure(text="🔊 朗读 开" if v else "🔇 朗读 关",
                               fg=GREEN if v else MUTED)

    def speaker_button(self, parent, text, form=None):
        b = tk.Button(parent, text="🔊", font=(SANS, 10), bg=PANEL, fg=ACCENT, bd=0,
                      activebackground=PANEL, cursor="hand2",
                      command=lambda: self.say(form if form is not None else text))
        return b

    # ------------------------------------------------------------ 外观
    def _style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=BG, foreground=FG, font=(SANS, 10))
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=BG, foreground=FG)
        st.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(SANS, 9))
        st.configure("H1.TLabel", background=BG, foreground=FG, font=(SERIF, 20))
        st.configure("H2.TLabel", background=BG, foreground=FG, font=(SANS, 12, "bold"))
        st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 2, 0, 0))
        st.configure("TNotebook.Tab", padding=(20, 9), font=(SANS, 10), background="#e7e0d2")
        st.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", ACCENT)])

    # ------------------------------------------------------------ 骨架
    def _build(self):
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=24, pady=(16, 4))
        tk.Label(head, text="昆雅", font=(SERIF, 21), bg=BG, fg=FG).pack(side="left")
        tk.Label(head, text="  Quenya", font=(SANS, 10), bg=BG, fg=MUTED).pack(side="left", pady=(9, 0))

        self.meta = tk.Frame(head, bg=BG)
        self.meta.pack(side="right", pady=(6, 0))
        self.ref_btn = tk.Button(self.meta, text="", font=(SANS, 9), bg=BG, fg=ACCENT,
                                 bd=0, activebackground=BG, cursor="hand2",
                                 command=self.toggle_ref)
        self.ref_btn.pack(side="left", padx=(0, 14))
        self.tts_btn = tk.Button(self.meta, text="🔊 朗读 开" if self.tts_on() else "🔇 朗读 关",
                                 font=(SANS, 9), bg=BG, fg=GREEN if self.tts_on() else MUTED,
                                 bd=0, activebackground=BG, cursor="hand2", command=self.toggle_tts)
        self.tts_btn.pack(side="left", padx=(0, 14))
        self.lb_due = tk.Label(self.meta, text="", font=(SANS, 10), bg=BG, fg=MUTED)
        self.lb_due.pack(side="left", padx=10)
        self.lb_streak = tk.Label(self.meta, text="", font=(SANS, 10, "bold"), bg=BG, fg=GOLD)
        self.lb_streak.pack(side="left", padx=10)
        self.lb_xp = tk.Label(self.meta, text="", font=(SANS, 10), bg=BG, fg=GREEN)
        self.lb_xp.pack(side="left", padx=10)

        # 外层：左边是主区（页签 + 上课层），右边是对照侧栏。
        # 上课层挂在 main 里，所以侧栏不会被盖住 —— 上课时也能对照。
        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True, padx=20, pady=(4, 16))
        self.main = tk.Frame(self.body, bg=BG)
        self.main.pack(side="left", fill="both", expand=True)

        self.nb = ttk.Notebook(self.main)
        self.nb.pack(fill="both", expand=True)
        self.tab_learn = tk.Frame(self.nb, bg=BG)
        self.tab_review = tk.Frame(self.nb, bg=BG)
        self.tab_dict = tk.Frame(self.nb, bg=BG)
        self.tab_sent = tk.Frame(self.nb, bg=BG)
        self.tab_alpha = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.tab_learn, text="学习")
        self.nb.add(self.tab_review, text="复习")
        self.nb.add(self.tab_dict, text="查词")
        self.nb.add(self.tab_sent, text="造句")
        self.nb.add(self.tab_alpha, text="字母表")
        self._build_path()
        self._build_review()
        self._build_dict()
        self._build_sentence()
        self._build_alphabet()
        self._build_refbar()
        self.render_review()
        self.apply_ref_visibility()

    def refresh_meta(self):
        p = self.prog
        due = len(C.due_cards(p, 999))
        self.lb_due.configure(text="复习到期 %d" % due if due else "今天没有到期的")
        s = p["streak"].get("count", 0)
        self.lb_streak.configure(text=("🔥 连胜 %d 天" % s) if s else "连胜 0 天")
        xp = C.xp_today(p)
        self.lb_xp.configure(text="今日 %d/%d XP" % (xp, DAILY_GOAL))

    # ------------------------------------------------------------ 学习路径
    def _build_path(self):
        wrap = tk.Frame(self.tab_learn, bg=BG)
        wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw", tags="win")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))
        self.canvas.bind("<Configure>", self._fit_path)
        self.render_path()

    def _fit_path(self, ev):
        """路径卡片跟随窗口宽度，但不超过 860px（一行太长反而难读），超宽时居中。"""
        w = max(360, min(ev.width - 16, 860))
        self.canvas.itemconfigure("win", width=w)
        self.canvas.coords("win", (ev.width - w) / 2, 6)

    def lesson_done(self, lid):
        return lid in self.prog["done"]

    def current_lesson(self):
        for u in self.path:
            for l in u["lessons"]:
                if not self.lesson_done(l["lid"]):
                    return u, l
        return None, None

    def render_path(self):
        for w in self.inner.winfo_children():
            w.destroy()
        cur_u, cur_l = self.current_lesson()
        top = tk.Frame(self.inner, bg=BG)
        top.pack(fill="x", pady=(2, 12))
        if cur_l:
            tk.Label(top, text="下一课：%s" % cur_l["title"], font=(SANS, 11, "bold"),
                     bg=BG, fg=ACCENT).pack(anchor="w")
            tk.Label(top, text="一节 6 个词，大约 3 分钟。", font=(SANS, 9),
                     bg=BG, fg=MUTED).pack(anchor="w")
        else:
            tk.Label(top, text="30 节课都上完了 —— 去「复习」里巩固吧。",
                     font=(SANS, 11, "bold"), bg=BG, fg=GREEN).pack(anchor="w")

        for u in self.path:
            card = tk.Frame(self.inner, bg=PANEL, highlightthickness=1,
                            highlightbackground=LINE)
            card.pack(fill="x", pady=5, padx=2)
            hd = tk.Frame(card, bg=PANEL)
            hd.pack(fill="x", padx=16, pady=(12, 4))
            tk.Label(hd, text=u["title"], font=(SANS, 12, "bold"), bg=PANEL, fg=FG).pack(side="left")
            tk.Label(hd, text=u["label"], font=(SANS, 9), bg=PANEL, fg=MUTED).pack(side="left", padx=8)
            row = tk.Frame(card, bg=PANEL)
            row.pack(fill="x", padx=16, pady=(4, 14))
            for l in u["lessons"]:
                done = self.lesson_done(l["lid"])
                is_cur = bool(cur_l and l["lid"] == cur_l["lid"])
                # 阅读线不锁：随时可以挑一章原文来读（像 Duolingo 的 Stories）
                open_any = (u["uid"].startswith("S.") and not done)
                startable = is_cur or open_any
                if done:
                    bgc, fgc, txt = GREEN_BG, GREEN, "✓  %s" % l["title"]
                elif is_cur:
                    bgc, fgc, txt = ACCENT, "#ffffff", "▶  %s" % l["title"]
                elif open_any:
                    bgc, fgc, txt = "#f3ead9", ACCENT, "○  %s" % l["title"]
                else:
                    bgc, fgc, txt = "#f0ece2", LOCK, "🔒 %s" % l["title"]
                b = tk.Button(row, text=txt, font=(SANS, 9, "bold"), bg=bgc, fg=fgc,
                              activebackground=bgc, disabledforeground=fgc,
                              bd=0, padx=12, pady=7, cursor="hand2" if startable else "",
                              state="normal" if startable else "disabled",
                              command=(lambda l=l, u=u: self.start_lesson(u, l)) if startable else None)
                b.pack(side="left", padx=(0, 8))

    # ------------------------------------------------------------ 上课
    def start_lesson(self, unit, lesson):
        if lesson.get("kind") == "sent":
            sents = list(lesson["sents"])
            steps = []
            for s in sents:
                steps.append({"t": "read", "sent": s})
                steps.append({"t": "sentq", "sent": s, "pool": sents})
            self.lesson = {"kind": "sent", "lid": lesson["lid"], "title": lesson["title"],
                           "steps": steps, "i": 0, "hearts": HEARTS, "correct": 0, "wrong": 0,
                           "new_words": [], "next_fn": self.finish_lesson,
                           "sentence_only": True}
            self.open_lesson()
            return
        words = list(lesson["words"])
        pool = [w for l in unit["lessons"] for w in l["words"]]
        steps = []
        for w in words:
            steps.append({"t": "teach", "word": w})
            steps.append({"t": "quiz", "row": w, "pool": pool})
        for w in random.sample(words, min(3, len(words))):
            steps.append({"t": "quiz", "row": w, "pool": pool})
        self.lesson = {"kind": "lesson", "lid": lesson["lid"], "title": lesson["title"],
                       "steps": steps, "i": 0, "hearts": HEARTS, "correct": 0, "wrong": 0,
                       "new_words": words, "next_fn": self.finish_lesson}
        self.open_lesson()

    def start_review(self):
        rows = C.due_rows(self.con, self.prog, 12)
        if not rows:
            self.refresh_meta()
            return
        steps = [{"t": "quiz", "row": r, "pool": rows} for r in rows]
        random.shuffle(steps)
        self.lesson = {"kind": "review", "lid": None, "title": "复习 %d 张卡" % len(rows),
                       "steps": steps, "i": 0, "hearts": HEARTS, "correct": 0, "wrong": 0,
                       "new_words": [], "next_fn": self.finish_review}
        self.open_lesson()

    def open_lesson(self):
        if self.overlay:
            self.overlay.destroy()
        self.overlay = tk.Frame(self.main, bg=BG)
        self.overlay.place(x=0, y=0, relwidth=1, relheight=1)

        bar = tk.Frame(self.overlay, bg=BG)
        bar.pack(fill="x", padx=20, pady=(14, 6))
        tk.Button(bar, text="✕", font=(SANS, 12), bg=BG, fg=MUTED, bd=0, padx=10,
                  activebackground=BG, cursor="hand2", command=self.abort_lesson).pack(side="left")
        self.pb = tk.Canvas(bar, height=10, bg="#e6dfd1", highlightthickness=0)
        self.pb.pack(side="left", fill="x", expand=True, padx=14)
        self.hearts_lb = tk.Label(bar, text="", font=(SANS, 11), bg=BG, fg=RED)
        self.hearts_lb.pack(side="left", padx=(4, 10))
        self.combo_lb = tk.Label(bar, text="", font=(SANS, 10, "bold"), bg=BG, fg=GOLD)
        self.combo_lb.pack(side="left")

        self.body = tk.Frame(self.overlay, bg=BG)
        self.body.pack(fill="both", expand=True, padx=40, pady=(10, 0))
        self.foot = tk.Frame(self.overlay, bg=BG)
        self.foot.pack(fill="x", side="bottom", pady=16)
        self.step()

    def abort_lesson(self):
        self.lesson = None
        if self.overlay:
            self.overlay.destroy()
            self.overlay = None

    def step(self):
        L = self.lesson
        if not L:
            return
        if L["i"] >= len(L["steps"]):
            L["next_fn"]()
            return
        for w in self.body.winfo_children():
            w.destroy()
        for w in self.foot.winfo_children():
            w.destroy()
        self.combo_lb.configure(text="")

        # 进度条
        self.pb.update_idletasks()
        w = max(self.pb.winfo_width(), 200)
        self.pb.delete("all")
        frac = L["i"] / len(L["steps"])
        self.pb.create_rectangle(0, 0, int(w * frac), 10, fill=ACCENT, width=0)
        self.pb.create_rectangle(0, 0, w, 10, fill="#e6dfd1", width=0)
        self.pb.create_rectangle(0, 0, int(w * frac), 10, fill=ACCENT, width=0)
        self.hearts_lb.configure(text="♥" * L["hearts"] + "♡" * (HEARTS - L["hearts"]))

        s = L["steps"][L["i"]]
        if s["t"] == "teach":
            self.render_teach(s["word"])
        elif s["t"] == "read":
            self.render_read(s["sent"])
        elif s["t"] == "sentq":
            self.render_sentence_quiz(s["sent"], s.get("pool") or [s["sent"]])
        else:
            self.render_quiz(s["row"], s.get("pool") or [s["row"]])

    # ---------------- 教学卡
    def render_teach(self, row):
        cf = tk.Frame(self.body, bg=BG)
        cf.pack(expand=True)
        tk.Label(cf, text="新词", font=(SANS, 9), bg=BG, fg=MUTED).pack(pady=(10, 2))
        line = tk.Frame(cf, bg=BG)
        line.pack()
        tk.Label(line, text=C.display_form(row["form"]), font=(SERIF, 44), bg=BG, fg=FG).pack(side="left")
        self.speaker_button(line, row["form"]).pack(side="left", padx=(12, 0), pady=(14, 0))
        tk.Label(cf, text=row["gloss"] or "—", font=(SANS, 13), bg=BG, fg=ACCENT,
                 wraplength=720, justify="center").pack(pady=(4, 2))
        sub = []
        if row["speech"]:
            sub.append(row["speech"])
        sub.append("等级 %d" % row["tier"])
        cites = C.citation_of(self.con, row, 2)
        if cites:
            sub.append("出处 " + " / ".join(cites))
        tk.Label(cf, text="·".join(sub), font=(SANS, 9), bg=BG, fg=MUTED).pack(pady=(0, 6))

        # Tengwar：同一个词看两种写法
        self._tw_small = None
        try:
            png = C.tengwar_png(C.display_form(row["form"]))
            if png:
                img = Image.open(png)
                s = min(300 / img.size[0], 90 / img.size[1], 1.0)
                if s != 1:
                    img = img.resize((max(1, int(img.size[0] * s)), max(1, int(img.size[1] * s))),
                                     Image.LANCZOS)
                self._tw_small = ImageTk.PhotoImage(img)
                tk.Label(cf, text="TENGWAR", font=(SANS, 8), bg=BG, fg=MUTED).pack()
                tk.Label(cf, image=self._tw_small, bg=BG, bd=0).pack()
        except Exception:
            pass
        # 听到的和看到的对不对得上：给 IPA
        sp = self.speaker
        if sp and sp.ok:
            ip = sp.ipa(row["form"])
            if ip:
                tk.Label(cf, text="IPA  " + ip, font=(MONO, 9), bg=BG, fg=MUTED).pack(pady=(4, 0))

        infl = self.con.execute(
            "SELECT DISTINCT kind, form FROM inflect WHERE word_uid=? AND kind IS NOT NULL "
            "ORDER BY kind LIMIT 4", (row["uid"],)).fetchall()
        if infl:
            box = tk.Frame(cf, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
            box.pack(pady=10, ipadx=14, ipady=8)
            tk.Label(box, text="屈折形式", font=(SANS, 9), bg=PANEL, fg=MUTED).pack(anchor="w")
            for r in infl:
                tk.Label(box, text="%-24s → %s" % (r["kind"], r["form"] or "?"),
                         font=(MONO, 10), bg=PANEL, fg=FG).pack(anchor="w")

        tk.Label(self.foot, text="看完点「继续」，马上就考。", font=(SANS, 9),
                 bg=BG, fg=MUTED).pack(anchor="center")
        self.advance_button("继续")

    def advance_button(self, text, on_click=None, color=GREEN):
        b = tk.Button(self.foot, text=text, font=(SANS, 12, "bold"), bg=color, fg="white",
                      activebackground=color, activeforeground="white", bd=0,
                      padx=40, pady=12, cursor="hand2",
                      command=on_click or self.next_step)
        b.pack(pady=6)
        return b

    def next_step(self):
        if not self.lesson:
            return
        self.lesson["i"] += 1
        self.step()

    # ---------------- 读原文句子
    def render_read(self, sent):
        box = tk.Frame(self.body, bg=BG)
        box.pack(fill="both", expand=True)
        tk.Frame(box, bg=BG).pack(expand=True)
        tk.Label(box, text="托尔金原文", font=(SANS, 9), bg=BG, fg=MUTED).pack()
        line = tk.Frame(box, bg=BG)
        line.pack(pady=(6, 4))
        tk.Label(line, text=sent["form"], font=(SERIF, 22), bg=BG, fg=FG,
                 wraplength=880, justify="center").pack(side="left")
        self.speaker_button(line, sent["form"]).pack(side="left", padx=(10, 0), pady=(6, 0))
        tk.Label(box, text=sent["gloss"] or "—", font=(SANS, 12), bg=BG, fg=ACCENT,
                 wraplength=900, justify="center").pack()
        cits = C.citation_of(self.con, sent, 2)
        if cits:
            tk.Label(box, text="出处 " + " / ".join(cits), font=(SANS, 9),
                     bg=BG, fg=MUTED).pack(pady=(4, 6))

        # Tengwar：同一句话的精灵文写法
        self._tw_sent = None
        try:
            png = C.tengwar_png(sent["form"])
            if png:
                img = Image.open(png)
                s = min(820 / img.size[0], 120 / img.size[1], 1.0)
                if s != 1:
                    img = img.resize((max(1, int(img.size[0] * s)), max(1, int(img.size[1] * s))),
                                     Image.LANCZOS)
                self._tw_sent = ImageTk.PhotoImage(img)
                tk.Label(box, image=self._tw_sent, bg=BG, bd=0).pack(pady=(0, 8))
        except Exception:
            pass

        tbl = tk.Frame(box, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        tbl.pack(fill="x", padx=70, pady=6, ipady=10)
        tk.Label(tbl, text="逐词", font=(SANS, 9), bg=PANEL, fg=MUTED).pack(anchor="w", padx=16, pady=(0, 2))
        tk.Label(tbl, text="同形的两种读法会并排给出（如 i = he 的复数 / 冠词），要靠上下文判断",
                 font=(SANS, 8), bg=PANEL, fg=LOCK).pack(anchor="w", padx=16, pady=(0, 6))
        for tok, gl, tier, note in C.breakdown(self.con, sent["form"]):
            row = tk.Frame(tbl, bg=PANEL)
            row.pack(fill="x", padx=16, pady=1)
            tk.Label(row, text=tok, font=(SERIF, 12), bg=PANEL, fg=FG, width=18,
                     anchor="w").pack(side="left")
            tk.Label(row, text=gl or "—— Eldamo 未收录（可能是缩合形或专名）",
                     font=(SANS, 9), bg=PANEL, fg=FG if gl else LOCK,
                     anchor="w", justify="left").pack(side="left")
        tk.Frame(box, bg=BG).pack(expand=True)
        tk.Label(self.foot, text="读完点「继续」，然后考这句。", font=(SANS, 9),
                 bg=BG, fg=MUTED).pack(anchor="center")
        self.advance_button("继续")

    def render_sentence_quiz(self, sent, pool):
        self._answered = False
        q = C.make_sentence_question(sent, pool)
        self.cur_q = q
        L = self.lesson

        qbox = tk.Frame(self.body, bg=BG)
        qbox.pack(fill="both", expand=True)
        tk.Frame(qbox, bg=BG).pack(expand=True)
        tk.Label(qbox, text=q["kind_cn"], font=(SANS, 9), bg=BG, fg=MUTED).pack(anchor="w", pady=(0, 8))

        if q["kind"] == "sent2gloss":
            tk.Label(qbox, text=q["prompt"], font=(SERIF, 21), bg=BG, fg=FG,
                     wraplength=900, justify="left").pack(anchor="w")
            tk.Label(qbox, text="（托老原文）", font=(SANS, 9), bg=BG, fg=MUTED).pack(anchor="w", pady=(0, 14))
            grid = tk.Frame(qbox, bg=BG)
            grid.pack(fill="x")
            self.opt_buttons = []
            for i, opt in enumerate(q["options"]):
                b = tk.Button(grid, text="%d.   %s" % (i + 1, opt), font=(SANS, 11), bg=PANEL, fg=FG,
                              activebackground="#f0e8d8", bd=1, relief="solid",
                              highlightthickness=1, highlightbackground=LINE,
                              anchor="w", justify="left", wraplength=820, padx=18, pady=10,
                              cursor="hand2", command=lambda o=opt: self.answer_choice(o))
                b.pack(fill="x", pady=4)
                self.opt_buttons.append(b)
        else:
            tk.Label(qbox, text=q["prompt"], font=(SERIF, 20), bg=BG, fg=ACCENT,
                     wraplength=900, justify="left").pack(anchor="w")
            tk.Label(qbox, text="点词块，按原文顺序拼出来", font=(SANS, 9),
                     bg=BG, fg=MUTED).pack(anchor="w", pady=(2, 10))

            self.order_box = tk.Frame(qbox, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
            self.order_box.pack(fill="x", ipady=10, ipadx=10)
            self.order_line = tk.Label(self.order_box, text="（空）", font=(SERIF, 15),
                                       bg=PANEL, fg=FG, wraplength=880, justify="left", anchor="w")
            self.order_line.pack(fill="x")
            self.chosen = []

            self.chip_box = tk.Frame(qbox, bg=BG)
            self.chip_box.pack(fill="x", pady=(12, 0))
            self.chips = list(q["chips"])
            self.chip_btns = []
            for i, tok in enumerate(self.chips):
                b = tk.Button(self.chip_box, text=tok, font=(SERIF, 13), bg=PANEL, fg=FG,
                              activebackground="#f0e8d8", bd=1, relief="solid",
                              highlightthickness=1, highlightbackground=LINE,
                              padx=12, pady=6, cursor="hand2",
                              command=lambda i=i: self.pick_chip(i))
                b.pack(side="left", padx=3, pady=3)
                self.chip_btns.append(b)

            row2 = tk.Frame(qbox, bg=BG)
            row2.pack(fill="x", pady=(12, 0))
            tk.Button(row2, text="撤销", font=(SANS, 9), bg=BG, fg=MUTED, bd=0, padx=10,
                      cursor="hand2", command=self.undo_chip).pack(side="left")
            self.advance_button("检查", self.answer_order)

        tk.Frame(qbox, bg=BG).pack(expand=True)
        self.bind("<Key>", self.on_key)

    def pick_chip(self, i):
        if getattr(self, "_answered", False):
            return
        b = self.chip_btns[i]
        if str(b.cget("state")) == "disabled":
            return
        b.configure(state="disabled", fg=LOCK)
        self.chosen.append(i)
        self.order_line.configure(text=" ".join(self.chips[j] for j in self.chosen))

    def undo_chip(self):
        if getattr(self, "_answered", False) or not self.chosen:
            return
        i = self.chosen.pop()
        self.chip_btns[i].configure(state="normal", fg=FG)
        self.order_line.configure(text=" ".join(self.chips[j] for j in self.chosen) or "（空）")

    def answer_order(self):
        q = self.cur_q
        if getattr(self, "_answered", False):
            return
        if not self.chosen:
            return
        self._answered = True
        got = " ".join(self.chips[j] for j in self.chosen)
        want = q["answer"]
        norm = lambda s: " ".join(s.split()).replace("’", "'")
        ok = norm(got) == norm(want)
        self.order_box.configure(bg=GREEN_BG if ok else RED_BG,
                                 highlightbackground=GREEN if ok else RED)
        self.grade(ok)
        self.feedback(ok, q)

    # ---------------- 题目
    def render_quiz(self, row, pool):
        self._answered = False
        q = C.make_question(row, pool)
        self.cur_q = q
        L = self.lesson

        qbox = tk.Frame(self.body, bg=BG)
        qbox.pack(fill="both", expand=True)
        tk.Frame(qbox, bg=BG).pack(expand=True)

        tk.Label(qbox, text=q["kind_cn"], font=(SANS, 9), bg=BG, fg=MUTED).pack(anchor="w", pady=(0, 8))

        if q["kind"] == "tengwar" and isinstance(q["prompt"], str):
            img = Image.open(q["prompt"])
            s = min(680 / img.size[0], 150 / img.size[1], 1.0)
            if s < 1:
                img = img.resize((int(img.size[0] * s), int(img.size[1] * s)), Image.LANCZOS)
            self._tw_img = ImageTk.PhotoImage(img)
            tk.Label(qbox, image=self._tw_img, bg=PANEL, bd=0).pack(anchor="w", pady=4)
            tk.Label(qbox, text="这是哪个词？", font=(SANS, 12), bg=BG, fg=FG).pack(anchor="w", pady=(2, 10))
        else:
            tk.Label(qbox, text=q["prompt"], font=(SERIF, 34), bg=BG, fg=FG,
                     wraplength=820, justify="left").pack(anchor="w", pady=(2, 2))
            tk.Label(qbox, text=q["prompt_sub"], font=(SANS, 9), bg=BG, fg=MUTED).pack(anchor="w", pady=(0, 16))

        if q["options"]:
            grid = tk.Frame(qbox, bg=BG)
            grid.pack(fill="x", pady=(4, 0))
            self.opt_buttons = []
            for i, opt in enumerate(q["options"]):
                b = tk.Button(grid, text="%d.   %s" % (i + 1, opt), font=(SANS, 12), bg=PANEL, fg=FG,
                              activebackground="#f0e8d8", bd=1, relief="solid",
                              highlightthickness=1, highlightbackground=LINE,
                              anchor="w", padx=18, pady=12, cursor="hand2",
                              command=lambda o=opt: self.answer_choice(o))
                b.pack(fill="x", pady=5)
                self.opt_buttons.append(b)
        else:
            tk.Label(qbox, text="提示：" + q["hint"], font=(SANS, 9), bg=BG, fg=MUTED).pack(anchor="w")
            self.entry = tk.Entry(qbox, font=(SERIF, 18), bg=PANEL, fg=FG, bd=0,
                                  highlightthickness=1, highlightbackground=LINE,
                                  highlightcolor=ACCENT, insertbackground=FG)
            self.entry.pack(fill="x", ipady=8, ipadx=8, pady=(4, 0))
            self.entry.bind("<Return>", lambda e: self.answer_spell())
            self.entry.focus_set()
            self.advance_button("检查", self.answer_spell)

        tk.Frame(qbox, bg=BG).pack(expand=True)
        self.bind("<Key>", self.on_key)

    def on_key(self, ev):
        if not self.lesson or not self.overlay:
            return
        if ev.char in "1234" and getattr(self, "opt_buttons", None):
            i = int(ev.char) - 1
            if 0 <= i < len(self.opt_buttons):
                self.answer_choice(self.cur_q["options"][i])
        elif ev.keysym == "Return" and self.foot_continue_ready():
            self.next_step()

    def foot_continue_ready(self):
        for w in self.foot.winfo_children():
            if isinstance(w, tk.Button) and w.cget("text") == "继续":
                return True
        return False

    def answer_choice(self, opt):
        q = self.cur_q
        if getattr(self, "_answered", False):
            return
        self._answered = True
        ok = (opt == q["answer"])
        for b in self.opt_buttons:
            txt = b.cget("text").split(".  ", 1)[-1]
            if txt == q["answer"]:
                b.configure(bg=GREEN_BG, fg=GREEN, highlightbackground=GREEN)
            elif txt == opt and not ok:
                b.configure(bg=RED_BG, fg=RED, highlightbackground=RED)
        self.grade(ok)
        self.feedback(ok, q)

    def answer_spell(self):
        q = self.cur_q
        if getattr(self, "_answered", False):
            return
        typed = self.entry.get().strip()
        if not typed:
            return
        self._answered = True
        ok, hint = C.check_spelling(typed, q["answer"])
        self.entry.configure(bg=GREEN_BG if ok else RED_BG)
        self.grade(ok, note=hint)
        self.feedback(ok, q, extra=hint)

    # ---------------- 判分与反馈
    def grade(self, ok, note=None):
        L = self.lesson
        if ok:
            L["correct"] += 1
            L["combo"] = L.get("combo", 0) + 1
        else:
            L["wrong"] += 1
            L["combo"] = 0
            L["hearts"] -= 1
        C.grade(self.prog, self.cur_q["row"], ok)
        C.save_progress(self.prog)
        self.hearts_lb.configure(text="♥" * max(0, L["hearts"]) + "♡" * (HEARTS - max(0, L["hearts"])))
        if L.get("combo", 0) >= 3:
            self.combo_lb.configure(text="连击 %d" % L["combo"])

    def feedback(self, ok, q, extra=None):
        L = self.lesson
        # 不管对错，先让它读一遍正确的那个
        self.say_if_on(q["row"]["form"])
        for w in self.foot.winfo_children():
            w.destroy()
        row = q["row"]
        box = tk.Frame(self.foot, bg=GREEN_BG if ok else RED_BG)
        box.pack(fill="x")
        inner = tk.Frame(box, bg=GREEN_BG if ok else RED_BG)
        inner.pack(fill="x", padx=24, pady=10)
        head = "对了 ✓" if ok else "不对 ✗"
        tk.Label(inner, text=head, font=(SANS, 12, "bold"),
                 bg=box["bg"], fg=GREEN if ok else RED).pack(anchor="w")
        detail = "%s — %s" % (C.display_form(row["form"]), row["gloss"] or "—")
        cites = C.citation_of(self.con, row, 1)
        if cites:
            detail += "   （%s）" % cites[0]
        tk.Label(inner, text=detail, font=(SANS, 10), bg=box["bg"], fg=FG,
                 wraplength=900, justify="left").pack(anchor="w")
        if extra:
            tk.Label(inner, text=extra.replace("**", ""), font=(SANS, 9),
                     bg=box["bg"], fg=MUTED, wraplength=900, justify="left").pack(anchor="w")

        if L["hearts"] <= 0:
            b = tk.Button(self.foot, text="再来一次", font=(SANS, 12, "bold"),
                          bg=RED, fg="white", bd=0, padx=40, pady=10,
                          cursor="hand2", command=self.finish_fail)
            b.pack(pady=8)
            return
        last = (L["i"] + 1) >= len(L["steps"])
        b = tk.Button(self.foot, text="完成" if last else "继续", font=(SANS, 12, "bold"),
                      bg=GREEN if ok else RED, fg="white", bd=0, padx=40, pady=10,
                      cursor="hand2", command=self.next_step)
        b.pack(pady=8)

    # ---------------- 结算
    def finish_lesson(self):
        L = self.lesson
        self.prog["done"].append(L["lid"])
        xp = 10 + 2 * L["correct"]
        C.add_xp(self.prog, xp)
        streak = C.touch_streak(self.prog)
        C.save_progress(self.prog)
        self.lesson = None
        self.result_screen("一节课完成", xp, L, streak, extra="新学 %d 个词" % len(L["new_words"]))

    def finish_review(self):
        L = self.lesson
        xp = 5 + 2 * L["correct"]
        C.add_xp(self.prog, xp)
        streak = C.touch_streak(self.prog)
        C.save_progress(self.prog)
        self.lesson = None
        self.result_screen("复习完成", xp, L, streak, extra="处理 %d 张卡" % len(L["steps"]))

    def finish_fail(self):
        L = self.lesson
        self.lesson = None
        self.result_screen("心用完了", 0, L, self.prog["streak"].get("count", 0),
                           extra="这节没过，重来一次吧", fail=True)

    def result_screen(self, title, xp, L, streak, extra="", fail=False):
        for w in self.body.winfo_children():
            w.destroy()
        for w in self.foot.winfo_children():
            w.destroy()
        total = L["correct"] + L["wrong"]
        acc = round(100 * L["correct"] / total) if total else 0
        box = tk.Frame(self.body, bg=BG)
        box.pack(expand=True)
        tk.Label(box, text=title, font=(SERIF, 30), bg=BG,
                 fg=RED if fail else GREEN).pack(pady=(10, 6))
        tk.Label(box, text=("正确率 %d%%   ·   对 %d / 错 %d" % (acc, L["correct"], L["wrong"]))
                 if total else acc, font=(SANS, 12), bg=BG, fg=FG).pack()
        if xp:
            tk.Label(box, text="+%d XP" % xp, font=(SANS, 14, "bold"), bg=BG, fg=GOLD).pack(pady=6)
        if streak:
            tk.Label(box, text="🔥 连胜 %d 天" % streak, font=(SANS, 11), bg=BG, fg=GOLD).pack(pady=2)
        if extra:
            tk.Label(box, text=extra, font=(SANS, 9), bg=BG, fg=MUTED).pack(pady=(6, 0))

        b = tk.Button(self.foot, text="回到路径", font=(SANS, 12, "bold"), bg=ACCENT, fg="white",
                      bd=0, padx=40, pady=11, cursor="hand2", command=self.close_lesson)
        b.pack(pady=8)

    def close_lesson(self):
        if self.overlay:
            self.overlay.destroy()
            self.overlay = None
        self.lesson = None
        self.refresh_meta()
        self.render_path()
        self.render_review()

    # ------------------------------------------------------------ 复习页
    def _build_review(self):
        self.review_box = tk.Frame(self.tab_review, bg=BG)
        self.review_box.pack(fill="both", expand=True, padx=6, pady=10)

    def render_review(self):
        for w in self.review_box.winfo_children():
            w.destroy()
        due = C.due_cards(self.prog, 999)
        strong, total = C.mastery(self.prog)
        head = tk.Frame(self.review_box, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="复习", font=(SANS, 14, "bold"), bg=BG, fg=FG).pack(anchor="w")
        tk.Label(head, text="答对一次，下次见它的时间就往后推（1→2→4→8…天）；答错打回 1 天。",
                 font=(SANS, 9), bg=BG, fg=MUTED).pack(anchor="w", pady=(2, 10))

        stat = tk.Frame(head, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        stat.pack(fill="x", pady=(0, 12), ipady=10)
        for label, val, col in (("到期卡片", len(due), RED if due else GREEN),
                                ("掌握了", strong, GREEN),
                                ("学过", total, FG)):
            cell = tk.Frame(stat, bg=PANEL)
            cell.pack(side="left", expand=True)
            tk.Label(cell, text=str(val), font=(SERIF, 22), bg=PANEL, fg=col).pack()
            tk.Label(cell, text=label, font=(SANS, 9), bg=PANEL, fg=MUTED).pack()

        if due:
            tk.Button(self.review_box, text="开始复习（%d 张）" % len(due), font=(SANS, 12, "bold"),
                      bg=GREEN, fg="white", bd=0, padx=36, pady=11, cursor="hand2",
                      command=self.start_review).pack(pady=6)
        else:
            tk.Label(self.review_box, text="今天没有到期的卡片。上完一节新课，明天它们会回来。",
                     font=(SANS, 10), bg=BG, fg=MUTED).pack(pady=20)

        if total:
            tk.Label(self.review_box, text="最近学过的词", font=(SANS, 10, "bold"),
                     bg=BG, fg=FG).pack(anchor="w", pady=(16, 6))
            lst = tk.Frame(self.review_box, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
            lst.pack(fill="both", expand=True)
            items = sorted(self.prog["cards"].items(), key=lambda kv: kv[1].get("due", ""))[:40]
            for k, c in items:
                r = tk.Frame(lst, bg=PANEL)
                r.pack(fill="x", padx=12, pady=3)
                g = (c.get("gloss") or "")
                g = g[:44] + "…" if len(g) > 44 else g
                tk.Label(r, text=C.display_form(c.get("form", k)), font=(SERIF, 12), bg=PANEL,
                         fg=FG, width=16, anchor="w").pack(side="left")
                tk.Label(r, text=g, font=(SANS, 9), bg=PANEL, fg=MUTED, anchor="w").pack(side="left")
                tk.Label(r, text="%d 天后到期" % max(0, c.get("iv", 0)), font=(SANS, 9),
                         bg=PANEL, fg=ACCENT if c.get("iv", 0) >= 8 else MUTED).pack(side="right")

    # ------------------------------------------------------------ 对照侧栏
    # 侧栏里不用整张大图（缩到 300px 就看不清字了），而是：
    # 字形单独渲染成小图、文字用真字体排 —— 窄栏里也清楚，窗口缩放也不会糊。
    REF_GRID = [
        [("t", 0xE000), ("p", 0xE001), ("k/c", 0xE002), ("qu", 0xE003)],
        [("nd", 0xE004), ("mb", 0xE005), ("ng", 0xE006), ("ngw", 0xE007)],
        [("th", 0xE008), ("f", 0xE009), ("h", 0xE00A), ("hw", 0xE00B)],
        [("nt", 0xE00C), ("mp", 0xE00D), ("nc", 0xE00E), ("nqu", 0xE00F)],
        [("n", 0xE010), ("m", 0xE011), ("ñ", 0xE012), ("nw", 0xE013)],
        [("r", 0xE014), ("v", 0xE015), ("y", 0xE016), ("w", 0xE017)],
    ]
    REF_MARKS = [
        [("a", 0xE000, 0xE040), ("e", 0xE000, 0xE046), ("i", 0xE000, 0xE044),
         ("o", 0xE000, 0xE04A), ("u", 0xE000, 0xE04C)],
        [("á", 0xE02C, 0xE040), ("é", 0xE02C, 0xE046), ("í", 0xE02C, 0xE044),
         ("ó", 0xE02C, 0xE04A), ("ú", 0xE02C, 0xE04C)],
        [("ty", 0xE000, 0xE043), ("ll", 0xE022, 0xE051)],
    ]

    def _glyph(self, cps, px=34):
        """把一串码位渲染成小图（带缓存）。侧栏字形用，不落盘。"""
        key = (tuple(cps), px)
        if key in self._glyph_cache:
            return self._glyph_cache[key]
        try:
            ft = ImageFont.truetype(GLYPH_FONT, px)
            img = Image.new("RGBA", (px * 3, px * 2), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((px // 4, px // 4), "".join(chr(c) for c in cps),
                                     font=ft, fill=FG)
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)
            ph = ImageTk.PhotoImage(img)
        except Exception:
            ph = None
        self._glyph_cache[key] = ph
        return ph

    def _build_refbar(self):
        self.ref = tk.Frame(self.body, bg=PANEL, highlightthickness=1, highlightbackground=LINE)

        head = tk.Frame(self.ref, bg=PANEL)
        head.pack(fill="x", padx=10, pady=(10, 2))
        tk.Label(head, text="对照表", font=(SANS, 10, "bold"), bg=PANEL, fg=FG).pack(side="left")
        tk.Button(head, text="✕", font=(SANS, 9), bg=PANEL, fg=MUTED, bd=0,
                  activebackground=PANEL, cursor="hand2",
                  command=self.toggle_ref).pack(side="right")
        tk.Label(self.ref, text="昆雅读法（横＝部位　竖＝方式）", font=(SANS, 8),
                 bg=PANEL, fg=MUTED).pack(anchor="w", padx=10)

        grid = tk.Frame(self.ref, bg=PANEL)
        grid.pack(padx=8, pady=(4, 6))
        for i, row in enumerate(self.REF_GRID):
            for j, (val, cp) in enumerate(row):
                cell = tk.Frame(grid, bg=PANEL)
                cell.grid(row=i, column=j, padx=2, pady=1)
                ph = self._glyph([cp])
                if ph:
                    tk.Label(cell, image=ph, bg=PANEL).pack()
                tk.Label(cell, text=val, font=(SANS, 8), bg=PANEL, fg=ACCENT).pack()

        tk.Label(self.ref, text="元音记号（戴在前一个辅音上）", font=(SANS, 8), bg=PANEL,
                 fg=MUTED).pack(anchor="w", padx=10, pady=(6, 0))
        row1 = tk.Frame(self.ref, bg=PANEL)
        row1.pack(padx=8, pady=(2, 0))
        for val, base, mark in self.REF_MARKS[0]:
            cell = tk.Frame(row1, bg=PANEL)
            cell.pack(side="left", padx=3)
            ph = self._glyph([base, mark], 30)
            if ph:
                tk.Label(cell, image=ph, bg=PANEL).pack()
            tk.Label(cell, text=val, font=(SANS, 8), bg=PANEL, fg=ACCENT).pack()

        row2 = tk.Frame(self.ref, bg=PANEL)
        row2.pack(padx=8, pady=(2, 0))
        tk.Label(row2, text="长音：", font=(SANS, 8), bg=PANEL, fg=MUTED).pack(side="left")
        for val, base, mark in self.REF_MARKS[1]:
            cell = tk.Frame(row2, bg=PANEL)
            cell.pack(side="left", padx=2)
            ph = self._glyph([base, mark], 28)
            if ph:
                tk.Label(cell, image=ph, bg=PANEL).pack()
            tk.Label(cell, text=val, font=(SANS, 8), bg=PANEL, fg=ACCENT).pack()

        tk.Label(self.ref, text="字母下面的记号", font=(SANS, 8), bg=PANEL,
                 fg=MUTED).pack(anchor="w", padx=10, pady=(8, 0))
        row3 = tk.Frame(self.ref, bg=PANEL)
        row3.pack(padx=8, pady=(2, 10))
        for (val, base, mark), caption in zip(self.REF_MARKS[2], ["两点＝带 y", "一横＝双写"]):
            cell = tk.Frame(row3, bg=PANEL)
            cell.pack(side="left", padx=4)
            ph = self._glyph([base, mark], 30)
            if ph:
                tk.Label(cell, image=ph, bg=PANEL).pack()
            tk.Label(cell, text=caption, font=(SANS, 8), bg=PANEL, fg=MUTED).pack()

        tk.Button(self.ref, text="看完整解释 →", font=(SANS, 8), bg=PANEL, fg=ACCENT,
                  bd=0, activebackground=PANEL, cursor="hand2",
                  command=self.goto_alphabet).pack(anchor="w", padx=10, pady=(0, 10))

    def toggle_ref(self):
        on = not self.prog["settings"].get("refbar", False)
        self.prog["settings"]["refbar"] = on
        C.save_progress(self.prog)
        self.apply_ref_visibility()

    def apply_ref_visibility(self):
        on = bool(self.prog["settings"].get("refbar", False))
        if on:
            # 必须插到 main 前面：main 带 expand，先 pack 会把整行吃光，侧栏就 0 宽
            self.ref.pack(side="right", fill="y", padx=(14, 0), before=self.main)
        else:
            self.ref.pack_forget()
        self.ref_btn.configure(text="📖 对照表 开" if on else "📖 对照表 关",
                               fg=ACCENT if on else MUTED)

    def goto_alphabet(self):
        self.nb.select(self.tab_alpha)

    # ------------------------------------------------------------ 字母表
    ALPHABET = [
        ("01-grid.png", "发音表", "4 列 × 6 行：横着是嘴的位置，竖着是发音方式"),
        ("02-shapes.png", "形状规律", "弓数 / 竖笔下伸 / 竖笔上延 —— 三个维度"),
        ("03-vowels.png", "元音符号", "五个符号戴在辅音上；长音换载体"),
        ("04-words.png", "例词拆解", "六个词，每个词只讲一条规则"),
        ("05-longvowel.png", "长元音的两种写法", "长载体 vs 双写符号，同一句 lúmë"),
        ("06-palatal.png", "字母下面那两个点", "y 化记号；附与「加倍线」的区别"),
    ]

    def _build_alphabet(self):
        bar = tk.Frame(self.tab_alpha, bg=BG)
        bar.pack(fill="x", padx=6, pady=(8, 6))
        tk.Label(bar, text="字母表", font=(SANS, 13, "bold"), bg=BG, fg=FG).pack(side="left")
        tk.Label(bar, text="  学腾格瓦的规律，都在这几张卡上", font=(SANS, 9),
                 bg=BG, fg=MUTED).pack(side="left", pady=(3, 0))

        split = tk.Frame(self.tab_alpha, bg=BG)
        split.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        left = tk.Frame(split, bg=BG, width=250)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self.alpha_list = tk.Listbox(
            left, font=(SANS, 10), bg=PANEL, fg=FG, bd=0, highlightthickness=1,
            highlightbackground=LINE, selectbackground="#efe3d0", selectforeground=FG,
            activestyle="none",
        )
        self.alpha_list.pack(fill="both", expand=True)
        self.alpha_list.bind("<<ListboxSelect>>", self.on_pick_card)
        for _, title, _sub in self.ALPHABET:
            self.alpha_list.insert("end", title)

        right = tk.Frame(split, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.alpha_cap = tk.Label(right, text="", font=(SANS, 10), bg=BG, fg=MUTED,
                                  anchor="w", justify="left", wraplength=720)
        self.alpha_cap.pack(fill="x", pady=(0, 6))
        self.alpha_img = tk.Label(right, bg=PANEL, bd=0, anchor="nw",
                                  highlightthickness=1, highlightbackground=LINE)
        self.alpha_img.pack(fill="both", expand=True)
        self.alpha_img.bind("<Configure>", lambda e: self.show_card())

        self.alpha_list.selection_set(0)
        self._alpha_idx = 0
        self.show_card()

    def on_pick_card(self, *_):
        sel = self.alpha_list.curselection()
        if not sel:
            return
        self._alpha_idx = min(sel[0], len(self.ALPHABET) - 1)
        self.show_card()

    def show_card(self):
        name, title, sub = self.ALPHABET[getattr(self, "_alpha_idx", 0)]
        self.alpha_cap.configure(text="%s —— %s" % (title, sub))
        path = os.path.join(ROOT, "assets", "alphabet", name)
        if not os.path.exists(path):
            self._alpha_img = None
            self.alpha_img.configure(
                image="", text="缺少 %s\n\n跑一下 tools\\make_alphabet_cards.py 生成。" % name,
                font=(SANS, 10), fg=MUTED, bg=PANEL, compound="center")
            return
        try:
            img = Image.open(path)
            avail_w = max(self.alpha_img.winfo_width() - 16, 400)
            avail_h = max(self.alpha_img.winfo_height() - 16, 300)
            s = min(avail_w / img.size[0], avail_h / img.size[1], 1.0)
            if s < 1:
                img = img.resize((max(1, int(img.size[0] * s)), max(1, int(img.size[1] * s))),
                                 Image.LANCZOS)
            self._alpha_img = ImageTk.PhotoImage(img)
            self.alpha_img.configure(image=self._alpha_img, text="", compound="center")
        except Exception as e:
            self.alpha_img.configure(image="", text="图片打开失败：%s" % e, fg=RED, bg=PANEL)


    def _build_dict(self):
        top = tk.Frame(self.tab_dict, bg=BG)
        top.pack(fill="x", pady=(8, 8), padx=6)
        self.q = tk.StringVar()
        ent = tk.Entry(top, textvariable=self.q, font=(SERIF, 15), bg=PANEL, fg=FG, bd=0,
                       highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT,
                       insertbackground=FG)
        ent.pack(side="left", fill="x", expand=True, ipady=7, ipadx=8)
        ent.bind("<Return>", lambda e: self.do_search())
        ent.focus_set()
        tk.Button(top, text="查", font=(SANS, 10, "bold"), bg=PANEL, fg=FG, bd=1, relief="solid",
                  padx=18, pady=6, cursor="hand2", command=self.do_search).pack(side="left", padx=(8, 0))

        split = tk.Frame(self.tab_dict, bg=BG)
        split.pack(fill="both", expand=True, padx=6)
        left = tk.Frame(split, bg=BG, width=380)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self.results = tk.Listbox(left, font=(SANS, 10), bg=PANEL, fg=FG, bd=0,
                                  highlightthickness=1, highlightbackground=LINE,
                                  selectbackground="#efe3d0", selectforeground=FG, activestyle="none")
        self.results.pack(fill="both", expand=True)
        self.results.bind("<<ListboxSelect>>", self.on_select)
        right = tk.Frame(split, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.detail = tk.Text(right, wrap="word", font=(SANS, 10), bg=PANEL, fg=FG, bd=0,
                              highlightthickness=1, highlightbackground=LINE, padx=14, pady=12,
                              spacing1=1, spacing3=3, state="disabled")
        self.detail.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(right, command=self.detail.yview)
        sb.pack(side="right", fill="y")
        self.detail.configure(yscrollcommand=sb.set)
        self.rows = []

    def do_search(self):
        term = self.q.get().strip()
        if not term:
            return
        k = E.form_key(term)
        rows = self.con.execute(
            """SELECT * FROM word WHERE form_key = ?
               ORDER BY CASE lang WHEN 'q' THEN 0 WHEN 'nq' THEN 1 ELSE 2 END, tier""", (k,)).fetchall()
        if not rows:
            rows = self.con.execute("SELECT * FROM word WHERE form_key LIKE ? ORDER BY tier LIMIT 300",
                                    (k + "%",)).fetchall()
        if not rows:
            rows = self.con.execute("SELECT * FROM word WHERE gloss LIKE ? COLLATE NOCASE ORDER BY tier LIMIT 300",
                                    ("%" + term + "%",)).fetchall()
        self.rows = rows[:120]
        self.results.delete(0, "end")
        for r in self.rows:
            mk = (" " + r["mark"]) if r["mark"] else ""
            g = (r["gloss"] or "—")[:40]
            self.results.insert("end", "%s%s · %s  [%s·L%d]" % (
                r["form"], mk, g, LANG_SHORT.get(r["lang"], r["lang"] or "?"), r["tier"]))
        if self.rows:
            self.results.selection_set(0)
            self.on_select()

    def on_select(self, *_):
        sel = self.results.curselection()
        if not sel:
            return
        px = max(self.detail.winfo_width(), 520)
        cols = max(56, min(110, int((px - 40) / 7.4)))
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("end", E.fmt_word(self.con, self.rows[sel[0]], True, cols))
        self.detail.configure(state="disabled")

    # ------------------------------------------------------------ 造句
    def _build_sentence(self):
        tk.Label(self.tab_sent, text="敲一段昆雅，先核对每个词是否成立，再转成 Tengwar。",
                 font=(SANS, 9), bg=BG, fg=MUTED).pack(anchor="w", padx=6, pady=(8, 6))
        self.phrase = tk.Text(self.tab_sent, height=3, wrap="word", font=(SERIF, 14),
                              bg=PANEL, fg=FG, bd=0, highlightthickness=1,
                              highlightbackground=LINE, padx=12, pady=10)
        self.phrase.pack(fill="x", padx=6)
        self.phrase.insert("end", "Elen síla lúmenn' omentielvo")
        bar = tk.Frame(self.tab_sent, bg=BG)
        bar.pack(fill="x", padx=6, pady=8)
        for txt, fn, col in (("核对词形", self.do_check, GREEN), ("转写 Tengwar", self.do_tengwar, ACCENT)):
            tk.Button(bar, text=txt, font=(SANS, 10, "bold"), bg=col, fg="white", bd=0,
                      padx=18, pady=9, cursor="hand2", command=fn).pack(side="left", padx=(0, 8))
        self.out = tk.Text(self.tab_sent, wrap="word", font=(MONO, 10), bg=PANEL, fg=FG, bd=0,
                           highlightthickness=1, highlightbackground=LINE, padx=12, pady=10,
                           state="disabled")
        self.out.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.out.tag_configure("ok", foreground=GREEN)
        self.out.tag_configure("bad", foreground=RED)
        self.tw_band = tk.Frame(self.tab_sent, bg=BG)
        self.tw_band.pack(fill="x", padx=6, pady=(0, 8))
        self.tw_label = tk.Label(self.tw_band, bg=BG, anchor="w")
        self.tw_label.pack(anchor="w")

    def _phrase_text(self):
        return self.phrase.get("1.0", "end").strip().replace("\n", " ")

    def do_check(self):
        txt = self._phrase_text()
        if not txt:
            return
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            E.cmd_check(self.con, txt)
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        for line in buf.getvalue().splitlines():
            tag = ()
            if "✗" in line:
                tag = ("bad",)
            elif "✓" in line or "↳" in line:
                tag = ("ok",)
            self.out.insert("end", line + "\n", tag)
        self.out.configure(state="disabled")

    def do_tengwar(self):
        txt = self._phrase_text()
        node = E.find_node()
        if not node or not txt:
            return
        r = subprocess.run([node, os.path.join(TOOLS, "tengwar.mjs"), txt, "--json"], capture_output=True)
        if r.returncode != 0:
            return
        data = json.loads(r.stdout.decode("utf-8", "replace"))
        avail = max(self.tw_label.winfo_width(), 800) - 20
        png, _ = RT.render(data["tengwar"], os.path.join(ROOT, "data", "_app_tw.png"),
                           size=54, max_width=avail, caption=txt)
        img = Image.open(png)
        s = min(avail / img.size[0], 200 / img.size[1], 1.0)
        if s < 1:
            img = img.resize((int(img.size[0] * s), int(img.size[1] * s)), Image.LANCZOS)
        self._tw = ImageTk.PhotoImage(img)
        self.tw_label.configure(image=self._tw)


def selftest(app):
    """不开课也把全链路跑一遍：路径 → 上课 → 答对/答错 → 结算 → 复习队列。"""
    app.withdraw()
    assert len(app.path) >= 8, "课程路径太短"
    total = sum(len(u["lessons"]) for u in app.path)
    print("路径 OK: %d 单元 / %d 课" % (len(app.path), total))

    u, l = app.current_lesson()
    assert l, "找不到当前课"
    app.start_lesson(u, l)
    assert app.lesson, "课没开起来"
    n = len(app.lesson["steps"])
    print("开课 OK: %s, %d 步" % (l["lid"], n))

    # 走完整节：教学卡直接过，题目按正确答案点/填
    guard = 0
    while app.lesson and guard < 200:
        guard += 1
        s = app.lesson["steps"][app.lesson["i"]] if app.lesson["i"] < len(app.lesson["steps"]) else None
        if s is None:
            break
        if s["t"] == "teach":
            app.next_step()
            continue
        # 交替答对/答错，验证两条分支
        app.step()  # 重建界面，确保有 self.cur_q
        want_wrong = (guard % 5 == 0)
        if app.cur_q["options"]:
            pick = app.cur_q["answer"]
            if want_wrong:
                alt = [o for o in app.cur_q["options"] if o != app.cur_q["answer"]]
                pick = alt[0] if alt else pick
            app.answer_choice(pick)
        else:
            typed = app.cur_q["answer"] if not want_wrong else "zzz"
            app.entry.delete(0, "end")
            app.entry.insert(0, typed)
            app.answer_spell()
        # 点「继续/完成」
        for w in app.foot.winfo_children():
            if isinstance(w, tk.Button) and w.cget("text") in ("继续", "完成"):
                w.invoke()
                break
    assert l["lid"] in app.prog["done"], "课没记入进度"
    print("上课 OK: 完成并计入进度, XP=%d, 连胜=%d"
          % (C.xp_today(app.prog), app.prog["streak"].get("count", 0)))

    # 句子课：读句卡 + 两种题型都要走一遍
    sent_u = [u for u in app.path if u["uid"].startswith("S.")]
    assert sent_u, "没有句子单元"
    sl = sent_u[0]["lessons"][0]
    app.start_lesson(sent_u[0], sl)
    assert app.lesson and app.lesson["kind"] == "sent", "句子课没开起来"
    kinds = set()
    guard = 0
    while app.lesson and guard < 200:
        guard += 1
        if app.lesson["i"] >= len(app.lesson["steps"]):
            break
        s = app.lesson["steps"][app.lesson["i"]]
        if s["t"] == "read":
            app.next_step()
            continue
        app.step()
        q = app.cur_q
        kinds.add(q["kind"])
        if q["kind"] == "order":
            for i, tok in enumerate(app.chips):
                for j in q["target"]:
                    pass
            # 按正确答案的顺序点词块
            remain = list(range(len(app.chips)))
            for want in q["target"]:
                for i in remain:
                    if app.chips[i] == want:
                        app.pick_chip(i)
                        remain.remove(i)
                        break
            app.answer_order()
        else:
            app.answer_choice(q["answer"])
        for w in app.foot.winfo_children():
            if isinstance(w, tk.Button) and w.cget("text") in ("继续", "完成"):
                w.invoke()
                break
    print("句子课 OK: 题型 %s, 完成 %s" % (sorted(kinds), sl["lid"] in app.prog["done"]))
    assert "order" in kinds or "sent2gloss" in kinds, "句子题没出现"
    app.close_lesson()

    # 语音：初始化 + 真的合成出音频
    import time
    for _ in range(60):
        if app.speaker is not None:
            break
        time.sleep(0.2)
    sp = app.speaker
    assert sp is not None, "语音初始化没跑起来"
    assert sp.ok, "语音不可用: %s" % sp.err
    d = sp.duration("mellon")
    ip = sp.ipa("mellon")
    assert d > 0.2, "合成时长异常: %.2fs" % d
    print("语音 OK: mellon %.2fs  IPA %s" % (d, ip))
    print("设置 OK: 朗读=%s 语速=%s" % (app.prog["settings"].get("tts"),
                                       app.prog["settings"].get("speed")))

    # 复习队列：刚答错的卡应该在 1 天后到期，答对的更久
    cards = app.prog["cards"]
    assert cards, "没写下任何卡片"
    ivs = sorted(c["iv"] for c in cards.values())
    print("排期 OK: %d 张卡, 间隔分布 %s" % (len(cards), ivs[:8]))
    today = C._today().isoformat()
    assert all(c["due"] >= today for c in cards.values()), "有卡到期日算错了"

    app.close_lesson()
    app.refresh_meta()
    app.destroy()
    print("ALL SELFTEST PASS")


def _log_crash(exc):
    """启动失败也要留痕：pythonw 没有控制台，崩了什么都看不到。"""
    import traceback
    import datetime as _dt
    p = os.path.join(ROOT, "data", "crash.log")
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write("\n=== %s ===\n" % _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            f.write("cwd=%s\nargv=%s\n" % (os.getcwd(), sys.argv))
            f.write(traceback.format_exc())
    except Exception:
        pass
    try:
        import tkinter.messagebox as mb
        mb.showerror("昆雅 · 启动失败", "%s: %s\n\n详情已写入 data\\crash.log" % (type(exc).__name__, exc))
    except Exception:
        pass


if __name__ == "__main__":
    try:
        app = LearnApp()
    except Exception as _e:
        _log_crash(_e)
        raise SystemExit(1)
    if "--selftest" in sys.argv:
        selftest(app)
    elif "--shot" in sys.argv:
        i = sys.argv.index("--shot")
        out = sys.argv[i + 1]
        tab = sys.argv[i + 2] if len(sys.argv) > i + 2 else "learn"

        def goto():
            if tab == "review":
                app.nb.select(app.tab_review)
            elif tab.startswith("alpha"):
                app.nb.select(app.tab_alpha)
                if tab.startswith("alpha") and len(tab) > 5:
                    n = int(tab[5:])
                    app._alpha_idx = n
                    app.show_card()
            elif tab == "dict":
                app.nb.select(app.tab_dict)
                app.q.set("elen")
                app.do_search()
            elif tab in ("lesson", "teach", "quiz", "result", "read", "order", "sentq"):
                app.nb.select(app.tab_learn)
                if tab in ("read", "order", "sentq"):
                    su = [u for u in app.path if u["uid"].startswith("S.")][0]
                    app.start_lesson(su, su["lessons"][0])
                    want = {"read": None, "order": "order", "sentq": "sent2gloss"}[tab]
                    for _ in range(60):
                        if not app.lesson or app.lesson["i"] >= len(app.lesson["steps"]):
                            break
                        s = app.lesson["steps"][app.lesson["i"]]
                        if s["t"] == "read" and want is None:
                            break
                        if s["t"] == "read":
                            app.next_step()
                            continue
                        app.step()
                        if app.cur_q["kind"] == want:
                            break
                else:
                    u, l = app.current_lesson()
                    if l:
                        app.start_lesson(u, l)
                        if tab == "quiz":
                            while app.lesson and app.lesson["i"] < len(app.lesson["steps"]) \
                                    and app.lesson["steps"][app.lesson["i"]]["t"] != "quiz":
                                app.next_step()
            app.lift()
            try:
                app.attributes("-topmost", True)
            except tk.TclError:
                pass

        def grab():
            app.update_idletasks()
            app.update()
            from PIL import ImageGrab
            x, y = app.winfo_rootx(), app.winfo_rooty()
            img = ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height()))
            img.save(out)
            print("shot ->", out, img.size)
            app.destroy()

        app.after(300, goto)
        app.after(3800, grab)
        app.mainloop()
    else:
        app.mainloop()
