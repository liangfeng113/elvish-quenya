#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""昆雅 · 桌面查词与转写工具

三个页签：查词 / 验句 & Tengwar / 今日一词。
查词、验句、转写全部复用 tools/elvish.py 里已经验证过的逻辑，避免两套实现打架。
Tengwar 显示用图片（FreeMonoTengwar 不必装进系统字体）。
"""
import os
import sys
import io
import json
import contextlib
import subprocess
import datetime

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)

import elvish as E          # noqa: E402
import render_tengwar as RT  # noqa: E402

DB = os.path.join(ROOT, "data", "elvish.db")
TMP_TW = os.path.join(ROOT, "data", "_app_tw.png")

BG = "#f7f5f0"
PANEL = "#fffdf8"
FG = "#1c1a17"
MUTED = "#6d675d"
LINE = "#e0d9cb"
ACCENT = "#8a5a2b"
OK_G = "#2f6b4f"
BAD_R = "#a63d2f"

SERIF = "Georgia"
SANS = "Microsoft YaHei UI"
MONO = "Consolas"

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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        dpi_aware()
        self.title("昆雅 · Quenya")
        self.geometry("1100x790")
        self.minsize(920, 700)
        self.configure(bg=BG)
        self.con = E.connect()
        self.rows = []
        self.photo = None
        self._style()
        self._build()

    # ---------- 外观 ----------
    def _style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=BG, foreground=FG, font=(SANS, 10))
        st.configure("TFrame", background=BG)
        st.configure("Panel.TFrame", background=PANEL)
        st.configure("TLabel", background=BG, foreground=FG)
        st.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(SANS, 9))
        st.configure("H1.TLabel", background=BG, foreground=FG, font=(SERIF, 20))
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", padding=(18, 8), font=(SANS, 10), background="#efe9de")
        st.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", ACCENT)])
        st.configure("TButton", padding=(14, 6), font=(SANS, 10))
        st.configure("Accent.TButton", padding=(16, 7), font=(SANS, 10, "bold"))
        st.map("Accent.TButton", background=[("active", "#f0e3d2")])
        st.configure("TEntry", padding=6, fieldbackground=PANEL, bordercolor=LINE,
                     lightcolor=PANEL, darkcolor=PANEL, insertcolor=FG)
        st.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
               darkcolor=[("focus", ACCENT)], focuscolor=[("focus", "")])
        st.configure("TLabelframe", background=BG)
        st.configure("TLabelframe.Label", background=BG, foreground=MUTED, font=(SANS, 9))

    def _build(self):
        head = ttk.Frame(self, padding=(22, 16, 22, 6))
        head.pack(fill="x")
        ttk.Label(head, text="昆雅", style="H1.TLabel").pack(side="left")
        ttk.Label(head, text="  Quenya · Eldamo v0.8.13", style="Muted.TLabel").pack(side="left", pady=(8, 0))
        self.status = ttk.Label(head, text="", style="Muted.TLabel")
        self.status.pack(side="right", pady=(8, 0))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=18, pady=(0, 14))
        self.nb = nb
        self.tab_word = ttk.Frame(nb, padding=14)
        self.tab_sent = ttk.Frame(nb, padding=14)
        self.tab_daily = ttk.Frame(nb, padding=14)
        nb.add(self.tab_word, text="查词")
        nb.add(self.tab_sent, text="验句 & Tengwar")
        nb.add(self.tab_daily, text="今日一词")
        self._build_word()
        self._build_sentence()
        self._build_daily()

    # ---------- 查词 ----------
    def _build_word(self):
        top = ttk.Frame(self.tab_word)
        top.pack(fill="x", pady=(0, 10))
        self.q = tk.StringVar()
        # 用 tk.Entry 而不是 ttk：clam 主题的 focus 环画成粗黑边，压不住
        ent = tk.Entry(
            top, textvariable=self.q, font=(SERIF, 15), bg=PANEL, fg=FG, bd=0,
            highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT,
            insertbackground=FG, disabledbackground=PANEL,
        )
        ent.pack(side="left", fill="x", expand=True, ipady=7, ipadx=8)
        ent.bind("<Return>", self.do_search)
        ent.focus_set()
        ttk.Button(top, text="查", style="Accent.TButton", command=self.do_search).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="今日一词", command=self.goto_daily).pack(side="left", padx=(6, 0))

        split = ttk.Frame(self.tab_word)
        split.pack(fill="both", expand=True)

        left = ttk.Frame(split, width=380)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self.results = tk.Listbox(
            left, font=(SANS, 10), bg=PANEL, fg=FG, bd=0, highlightthickness=1,
            highlightbackground=LINE, selectbackground="#efe3d0", selectforeground=FG,
            activestyle="none",
        )
        self.results.pack(fill="both", expand=True)
        self.results.bind("<<ListboxSelect>>", self.on_select)

        right = ttk.Frame(split, padding=(14, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True)
        self.detail = tk.Text(
            right, wrap="word", font=(SANS, 10), bg=PANEL, fg=FG, bd=0,
            highlightthickness=1, highlightbackground=LINE, padx=14, pady=12,
            spacing1=1, spacing3=3,
        )
        self.detail.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(right, command=self.detail.yview)
        sb.pack(side="right", fill="y")
        self.detail.configure(yscrollcommand=sb.set)
        self.detail.tag_configure("muted", foreground=MUTED)
        self.detail.configure(state="disabled")
        self.hint("输入昆雅词或英文释义反查，例如 elen / mellon / star")

    def hint(self, text):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("end", text, "muted")
        self.detail.configure(state="disabled")

    def do_search(self, *_):
        term = self.q.get().strip()
        if not term:
            return
        k = E.form_key(term)
        con = self.con
        rows = con.execute(
            """SELECT * FROM word WHERE form_key = ?
               ORDER BY CASE lang WHEN 'q' THEN 0 WHEN 'nq' THEN 1 WHEN 'mq' THEN 2
                                  WHEN 'eq' THEN 3 WHEN 's' THEN 4 ELSE 5 END, tier""",
            (k,),
        ).fetchall()
        mode = "精确"
        if not rows:
            rows = con.execute(
                "SELECT * FROM word WHERE form_key LIKE ? ORDER BY tier LIMIT 400", (k + "%",)
            ).fetchall()
            mode = "前缀"
        if not rows:
            rows = con.execute(
                "SELECT * FROM word WHERE gloss LIKE ? COLLATE NOCASE ORDER BY tier LIMIT 400",
                ("%" + term + "%",),
            ).fetchall()
            mode = "释义"
        if not rows:
            self.results.delete(0, "end")
            self.hint("没找到「%s」。\n\n试试：去掉词尾的 -（查词干）、只输词根、或换成英文释义反查。" % term)
            self.set_status("0 条")
            return
        self.rows = rows[:120]
        self.results.delete(0, "end")
        for r in self.rows:
            mark = (" " + r["mark"]) if r["mark"] else ""
            g = (r["gloss"] or "—")
            if len(g) > 40:
                g = g[:40] + "…"
            ln = LANG_SHORT.get(r["lang"], r["lang"] or "?")
            self.results.insert("end", "%s%s · %s  [%s·L%d]" % (r["form"], mark, g, ln, r["tier"]))
        self.set_status("%s匹配 %d 条" % (mode, len(rows)))
        self.results.selection_clear(0, "end")
        self.results.selection_set(0)
        self.on_select()

    def on_select(self, *_):
        sel = self.results.curselection()
        if not sel:
            return
        row = self.rows[sel[0]]
        # 详情栏用比例字体，按窗口宽度收窄折行，否则会长出一行被控件二次折断
        px = max(self.detail.winfo_width(), 520)
        cols = max(56, min(110, int((px - 40) / 7.4)))
        text = E.fmt_word(self.con, row, True, cols)
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("end", text)
        self.detail.configure(state="disabled")

    # ---------- 验句 ----------
    def _build_sentence(self):
        ttk.Label(
            self.tab_sent,
            text="敲一段昆雅（拉丁转写），先核对每个词是否成立，再转成 Tengwar。",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 6))
        self.phrase = tk.Text(
            self.tab_sent, height=3, wrap="word", font=(SERIF, 14), bg=PANEL, fg=FG,
            bd=0, highlightthickness=1, highlightbackground=LINE, padx=12, pady=10,
        )
        self.phrase.pack(fill="x")
        self.phrase.insert("end", "Elen síla lúmenn' omentielvo")

        bar = ttk.Frame(self.tab_sent)
        bar.pack(fill="x", pady=8)
        ttk.Button(bar, text="核对词形", style="Accent.TButton", command=self.do_check).pack(side="left")
        ttk.Button(bar, text="转写 Tengwar", command=self.do_tengwar).pack(side="left", padx=6)
        ttk.Button(bar, text="两样都要", command=self.do_both).pack(side="left")
        ttk.Button(bar, text="清空", command=self.clear_sentence).pack(side="right")

        # 先把 Tengwar 横幅钉在底部（整行宽度——精灵文是长条文本，塞侧栏必被裁）
        band = tk.Frame(self.tab_sent, bg=BG)
        band.pack(fill="x", side="bottom", pady=(10, 0))
        ttk.Label(band, text="TENGWAR", style="Muted.TLabel").pack(anchor="w")
        self.tw_canvas = tk.Label(band, bg=BG, bd=0, anchor="w", height=3)
        self.tw_canvas.pack(anchor="w", fill="x", pady=(2, 0))

        body = ttk.Frame(self.tab_sent)
        body.pack(fill="both", expand=True)
        self.out = tk.Text(
            body, wrap="word", font=(MONO, 10), bg=PANEL, fg=FG, bd=0,
            highlightthickness=1, highlightbackground=LINE, padx=12, pady=10,
        )
        self.out.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(body, command=self.out.yview)
        sb.pack(side="right", fill="y")
        self.out.configure(yscrollcommand=sb.set)
        self.out.tag_configure("ok", foreground=OK_G)
        self.out.tag_configure("bad", foreground=BAD_R)
        self.out.configure(state="disabled")

    def clear_sentence(self):
        self.phrase.delete("1.0", "end")
        self.write_out("")
        self.tw_canvas.configure(image="")
        self.photo = None

    def write_out(self, text, marks=None):
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        self.out.insert("end", text)
        self.out.configure(state="disabled")

    def read_phrase(self):
        return self.phrase.get("1.0", "end").strip().replace("\n", " ")

    def do_check(self):
        txt = self.read_phrase()
        if not txt:
            return
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            E.cmd_check(self.con, txt)
        text = buf.getvalue()
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        for line in text.splitlines():
            tag = ()
            if "✗" in line or "存疑" in line and "小计" not in line:
                tag = ("bad",)
            elif "✓" in line or "↳" in line:
                tag = ("ok",)
            self.out.insert("end", line + "\n", tag)
        self.out.configure(state="disabled")

    def do_tengwar(self):
        txt = self.read_phrase()
        if not txt:
            return
        node = E.find_node()
        if not node:
            self.write_out("转写需要 node，没找到。")
            return
        r = subprocess.run(
            [node, os.path.join(TOOLS, "tengwar.mjs"), txt, "--json"],
            capture_output=True,
        )
        if r.returncode != 0:
            self.write_out("转写失败：" + r.stderr.decode("utf-8", "replace"))
            return
        data = json.loads(r.stdout.decode("utf-8", "replace"))
        # 按控件实际宽度出图，避免被容器裁掉
        avail = max(self.tw_canvas.winfo_width(), 640) - 24
        png, size = RT.render(data["tengwar"], TMP_TW, size=56, max_width=avail, caption=txt)
        img = Image.open(png)
        w, h = img.size
        s = min(avail / w, 190 / h, 1.0)
        if s < 1:
            img = img.resize((int(w * s), int(h * s)), Image.LANCZOS)
        self.photo = ImageTk.PhotoImage(img)
        self.tw_canvas.configure(image=self.photo, height=img.size[1])
        if not self.out.get("1.0", "end").strip():
            self.write_out("码位：" + " ".join(data["codepoints"]))
        self.set_status("已转写 %d 个码位" % len(data["codepoints"]))

    def do_both(self):
        self.do_check()
        self.do_tengwar()

    # ---------- 今日一词 ----------
    def _build_daily(self):
        ttk.Label(
            self.tab_daily, text="每天一个词，从词库里按日期确定性挑选（同一天刷新也一样）。",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        ttk.Button(self.tab_daily, text="换一个", style="Accent.TButton", command=self.new_daily).pack(anchor="w")
        self.daily = tk.Text(
            self.tab_daily, wrap="word", font=(SANS, 11), bg=PANEL, fg=FG, bd=0,
            highlightthickness=1, highlightbackground=LINE, padx=16, pady=14,
            spacing1=2, spacing3=4,
        )
        self.daily.pack(fill="both", expand=True, pady=(10, 0))
        self.daily.tag_configure("head", font=(SANS, 11, "bold"), foreground=ACCENT,
                                 spacing1=2, spacing3=6)
        self.daily.configure(state="disabled")
        self.daily_n = 0
        self.new_daily()

    def new_daily(self):
        self.daily_n += 1
        day = (datetime.date.today() + datetime.timedelta(days=self.daily_n - 1)).isoformat()
        day, row = E.pick_daily(self.con, day)
        if row is None:
            body = "词库里没有符合条件的词。"
        else:
            px = max(self.daily.winfo_width(), 560)
            cols = max(56, min(110, int((px - 40) / 7.4)))
            body = E.fmt_word(self.con, row, True, cols)
        self.daily.configure(state="normal")
        self.daily.delete("1.0", "end")
        self.daily.insert("end", "今日一词 · %s\n\n" % day, ("head",))
        self.daily.insert("end", body)
        self.daily.configure(state="disabled")

    def goto_daily(self):
        self.nb.select(self.tab_daily)

    def set_status(self, text):
        self.status.configure(text=text)


def selftest(app):
    """不弹窗，把三条主路径跑一遍，验证接线。"""
    app.withdraw()
    app.q.set("elen")
    app.do_search()
    assert app.rows, "查词没结果"
    detail = app.detail.get("1.0", "end")
    assert "elen" in detail and "引文" in detail, "词条详情不完整"
    print("查词 OK:", app.rows[0]["form"], "|", len(app.rows), "条")

    app.phrase.delete("1.0", "end")
    app.phrase.insert("end", "Elen sila lumenn omentielvo")
    app.do_check()
    out = app.out.get("1.0", "end")
    assert "✗" in out, "错句应该被抓出来"
    print("验句 OK: 抓到错形")

    app.phrase.delete("1.0", "end")
    app.phrase.insert("end", "Elen síla lúmenn' omentielvo")
    app.do_both()
    assert app.photo is not None, "Tengwar 图片没生成"
    print("转写 OK: 图片", app.photo.width(), "x", app.photo.height())

    app.new_daily()
    assert "今日一词" in app.daily.get("1.0", "end"), "今日一词没内容"
    print("今日一词 OK")
    app.destroy()
    print("ALL SELFTEST PASS")


def autoshot(app, out, tab="word"):
    """把窗口调到前台、截自己的图，然后退出（给验收用）。"""
    from PIL import ImageGrab
    app.deiconify()
    app.lift()
    try:
        app.attributes("-topmost", True)
    except tk.TclError:
        pass
    if tab == "sent":
        app.nb.select(app.tab_sent)
        app.phrase.delete("1.0", "end")
        app.phrase.insert("end", "Elen síla lúmenn' omentielvo")
        app.after(400, app.do_check)
        app.after(700, app.do_tengwar)
    elif tab == "daily":
        app.nb.select(app.tab_daily)

    def grab():
        app.update_idletasks()
        app.update()
        x, y = app.winfo_rootx(), app.winfo_rooty()
        w, h = app.winfo_width(), app.winfo_height()
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        img.save(out)
        print("shot ->", out, img.size)
        app.destroy()

    app.after(1600, grab)
    app.mainloop()


if __name__ == "__main__":
    app = App()
    if "--selftest" in sys.argv:
        selftest(app)
    elif "--shot" in sys.argv:
        i = sys.argv.index("--shot")
        out = sys.argv[i + 1]
        tab = sys.argv[i + 2] if len(sys.argv) > i + 2 else "word"
        app.q.set("elen")
        if tab == "word":
            app.do_search()
        autoshot(app, out, tab)
    else:
        app.mainloop()
