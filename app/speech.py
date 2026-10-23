#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""昆雅发音：espeak-ng 的 ctypes 封装（离线，不启动子进程、不依赖系统 TTS）。

为什么用 espeak-ng 而不是 Windows SAPI：
 · espeak-ng 自带昆雅音素数据（voice "qya" / 列表里叫 "Quenya"）——认长元音 á/é/í/ó/ú、
   c=k、qu=kw、y=j、ë 独立成音节。交给英语 TTS 会按拼写乱读。
 · 没有母语者是这门语言的事实，任何 TTS 都是近似；但「按昆雅音系近似」和
   「按英语拼写乱读」是两件事，前者能用来练长短元音。

一个坑：espeak 的数据路径里不能有非 ASCII 字符（路径含中文会 access violation），
而本项目就住在「灵感」下面，所以首次运行会把数据复制到 ASCII 缓存目录。

用法:
  from speech import Speaker
  sp = Speaker()
  sp.say("Elen síla lúmenn' omentielvo")   # 后台线程播放
  sp.ipa("elen")                          # /ˈɛlɛn/
"""
import os
import ctypes
import shutil
import tempfile
import threading
import wave

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESPEAK = os.path.join(HERE, "assets", "espeak")
DLL = os.path.join(ESPEAK, "libespeak_ng.dll")
DATA_SRC = os.path.join(ESPEAK, "espeak-ng-data")

VOICE = "qya"        # 列表里显示为 "Quenya"
MARK = "v1"          # 数据版本标记，升级 espeak 时改这个

_AUDIO_OUTPUT_RETRIEVAL = 1
_cb_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short),
                            ctypes.c_int, ctypes.c_void_p)


def _ascii_dirs():
    """候选缓存目录，全部要求纯 ASCII（espeak 读不了非 ASCII 路径）。
    按顺序尝试：用户本地目录 → ProgramData → 临时目录。"""
    cands = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "QuenyaLearn", "espeak"),
             os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "QuenyaLearn", "espeak"),
             os.path.join(tempfile.gettempdir(), "quenya-espeak")]
    return [c for c in cands if c and all(ord(ch) < 128 for ch in c)]


def ensure_data():
    """把随包数据铺到能用的 ASCII 目录；已是最新就跳过。返回数据父目录或 None。"""
    if not os.path.isdir(DATA_SRC):
        return None
    for root in _ascii_dirs():
        data = os.path.join(root, "espeak-ng-data")
        mark = os.path.join(root, ".ok_" + MARK)
        if os.path.exists(mark) and os.path.isdir(data):
            return root
        try:
            os.makedirs(root, exist_ok=True)
            if os.path.isdir(data):
                shutil.rmtree(data, ignore_errors=True)
            shutil.copytree(DATA_SRC, data)
            with open(mark, "w", encoding="utf-8") as f:
                f.write(MARK)
            return root
        except Exception:
            # 这个位置不可写（权限/沙箱），换下一个
            continue
    return None


class Speaker:
    """初始化一次，反复合成。合成串行，播放后台线程。"""

    def __init__(self, voice=VOICE, speed=135):
        self.ok = False
        self.err = None
        self.voice = voice
        self.speed = speed
        self._buf = []
        self._lock = threading.Lock()
        self._cb = None
        self.sample_rate = 22050
        self._loaded = False

        if not os.path.exists(DLL):
            self.err = "缺少 libespeak_ng.dll"
            return
        root = ensure_data()
        if not root:
            self.err = "缺少 espeak-ng-data"
            return
        try:
            try:
                os.add_dll_directory(ESPEAK)
            except Exception:
                pass
            L = ctypes.WinDLL(DLL)
            self.lib = L
            L.espeak_Initialize.restype = ctypes.c_int
            L.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
            L.espeak_SetVoiceByName.restype = ctypes.c_int
            L.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
            L.espeak_SetParameter.restype = ctypes.c_int
            L.espeak_SetParameter.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
            L.espeak_Synth.restype = ctypes.c_int
            L.espeak_Synth.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint, ctypes.c_int,
                                       ctypes.c_uint, ctypes.c_uint,
                                       ctypes.POINTER(ctypes.c_uint), ctypes.c_void_p]
            L.espeak_Synchronize.restype = ctypes.c_int
            L.espeak_Synchronize.argtypes = []
            L.espeak_TextToPhonemes.restype = ctypes.c_char_p
            L.espeak_TextToPhonemes.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.c_int]
            L.espeak_Terminate.restype = ctypes.c_int
            L.espeak_Terminate.argtypes = []

            rate = L.espeak_Initialize(_AUDIO_OUTPUT_RETRIEVAL, 0, root.encode("utf-8"), 0)
            if rate <= 0:
                self.err = "espeak 初始化失败"
                return
            self.sample_rate = rate
            self._cb = _cb_type(self._on_wave)
            L.espeak_SetSynthCallback(self._cb)
            if L.espeak_SetVoiceByName(voice.encode("utf-8")) != 0:
                self.err = "没有昆雅语音（qya）"
                return
            L.espeak_SetParameter(1, speed, 0)   # 1 = espeakRATE
            self.ok = True
        except Exception as e:
            self.err = "%s: %s" % (type(e).__name__, e)

    def _on_wave(self, wav, n, events):
        if n > 0 and wav:
            self._buf.append(ctypes.string_at(wav, n * 2))
        return 0

    def wav(self, text, path=None):
        if not self.ok or not (text or "").strip():
            return None
        with self._lock:
            self._buf.clear()
            t = text.encode("utf-8")
            self.lib.espeak_Synth(t, len(t) + 1, 0, 1, 0, 0x01, None, None)
            self.lib.espeak_Synchronize()
            pcm = b"".join(self._buf)
            if not pcm:
                return None
            path = path or os.path.join(tempfile.gettempdir(), "quenya_say.wav")
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(self.sample_rate)
                w.writeframes(pcm)
            return path

    def duration(self, text):
        p = self.wav(text)
        if not p:
            return 0.0
        with wave.open(p, "rb") as w:
            return w.getnframes() / float(w.getframerate())

    def ipa(self, text):
        """转成 IPA，用来在界面上标音（也让学习者能对照 TTS 到底读了什么）。"""
        if not self.ok:
            return ""
        try:
            ptr = ctypes.c_void_p()
            buf = ctypes.c_char_p(text.encode("utf-8"))
            ptr.value = ctypes.cast(buf, ctypes.c_void_p).value
            p = self.lib.espeak_TextToPhonemes(ctypes.byref(ptr), 1, 0x02)  # UTF8, IPA
            return (p or b"").decode("utf-8", "replace").strip()
        except Exception:
            return ""

    def play(self, path):
        if not path:
            return

        def run():
            try:
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME)
            except Exception:
                pass

        threading.Thread(target=run, daemon=True).start()

    def say(self, text):
        """合成并后台播放。返回 wav 路径（失败为 None）。"""
        p = self.wav(text)
        if p:
            self.play(p)
        return p


def selftest():
    sp = Speaker()
    print("初始化:", "OK" if sp.ok else "失败 — %s" % sp.err)
    if not sp.ok:
        return False
    cases = ["Elen síla lúmenn' omentielvo", "mellon", "Nai tiruvantel ar varyuvantel"]
    allok = True
    for s in cases:
        d = sp.duration(s)
        ip = sp.ipa(s)
        ok = d > 0.3
        allok = allok and ok
        print("  %-38s %5.2fs  %-6s IPA: %s" % (s, d, "OK" if ok else "失败", ip[:48]))
    return allok


if __name__ == "__main__":
    print("SELFTEST PASS" if selftest() else "SELFTEST FAIL")
