#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NotebookLM PDF → PPT  桌面轉檔工具（圖形介面）
================================================

把本專案的命令列工具 pdf2ppt.py 包成一個有介面、可點選操作的桌面應用程式。

使用方式
--------
1. 先安裝相依套件（在專案資料夾內執行）：
       uv sync
   （需要 GPU 加速可另外 pip install onnxruntime-directml / onnxruntime-gpu）

2. 在專案根目錄執行：
       python pdf2ppt_gui_2.py

   本檔已隨專案一起存放在根目錄，通常不需要另外指定專案位置；若要用它去驅動
   另一份 checkout，按介面上的「選擇專案資料夾…」即可（會即時換載入的程式碼）。

   首次轉檔會自動下載 OCR 模型，需要短暫連網。

這支 GUI 只負責「收集選項 + 呼叫專案的轉檔邏輯 + 即時顯示進度」，真正的
OCR / 排版工作全部沿用 pdf2ppt 套件。注意選項清單目前是手抄 cli.py 的
argparse 定義：在 cli.py 增刪旗標或改預設值時，這裡與 README 的選項表要一起改。

版面：主畫面只留輸入／輸出檔，其餘選項全部收在預設收合的「進階選項」區
（_toggle_advanced）。色塊的選項曾經是主畫面上唯一的核取方塊（要拿它做 A/B），
2026-08-24 量完之後 cli.py 的預設換成 --no-cover，這裡也就跟著收進進階區、
反向成「輸出獨立色塊形狀」，預設不勾 —— 三方的預設值現在一致。

執行紀錄：每次啟動在本檔所在資料夾底下的 logs 寫一份（檔名是啟動時間，保留
30 天），介面日誌區看得到的東西那裡都有，轉檔失敗的 traceback 也在裡面。
「啟動.vbs」那條路自己不落檔，它是在程式沒能正常結束時直接把攔到的訊息跳訊息
框顯示出來。作法與取捨見 docs/dev/gui-啟動與錯誤留底.md。
"""
from __future__ import annotations

import datetime
import io
import os
import json
import queue
import re
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "NotebookLM PDF → PPT 轉檔工具"

# 進階區的收合按鈕文字。預設收起來：這些選項全部有校準過的預設值
# （200 DPI + Microsoft YaHei 是整條管線唯一校準過的作業點），日常轉檔一項
# 都不必動，攤在主畫面上只是讓「選檔 → 開始轉檔」這條主線被十幾個控制項擋住。
ADV_SHOW_TEXT = "▸ 進階選項（頁碼、字型、DPI、除錯…）"
ADV_HIDE_TEXT = "▾ 進階選項（收合）"

# 記住專案位置的設定檔（存在使用者家目錄，跟著使用者走）
CONFIG_PATH = Path.home() / ".notebooklm_pdf2ppt_gui.json"

# 日誌視窗保留的最大行數：GUI 是長時間開著的行程，不設上限的話一整個工作階段
# 的輸出會一直累積，每次 insert 都要重繪愈來愈大的緩衝區
LOG_MAX_LINES = 4000

# --------------------------------------------------------------------------- #
#  執行紀錄（logs\<時間>.log）
# --------------------------------------------------------------------------- #
# 使用者 2026-08-24 指示「程式產生的 log 寫進 logs 目錄，參考 meeting-scribe」。
# 從那邊照抄過來的四件事（都是已經驗證過的）：
#   * **一次執行一個檔**：一次啟動正好等於一個檔，不必另外定義邊界，跨午夜也
#     不會被切成兩半。
#   * **檔頭記程式版本**：三週後拿一份 log 出來看，沒有這行就只能從訊息長相
#     反推是哪一版跑的。
#   * **逐行 flush**：使用者是直接關視窗收工的，留在緩衝區的會整段蒸發，而那
#     正好是出事的那一段。
#   * **寫檔失敗一律靜靜關掉**，不重試也不拋：紀錄檔不該有辦法讓 GUI 掛掉。
# 差別在於這裡不經過 logging（整個專案都沒用 logging，輸出是 print 到
# stdout/stderr），所以由 _append 這個唯一的顯示漏斗順手寫一份。
LOG_DIR_NAME = "logs"
LOG_KEEP_DAYS = 30
# 目錄覆寫（測試／沙箱用）：不設就寫進本檔所在資料夾底下的 logs 目錄
LOG_DIR_ENV = "NOTEBOOKLM_PDF2PPT_LOG_DIR"
# 沒有換行的內容累積到這個長度就先落地：下載模型的進度條可能很久才換行，
# 不設上限的話出事那一刻的內容還躺在緩衝區裡
LOG_MAX_PENDING = 4096

# 終端機控制碼。rapidocr 的 colorlog formatter 是以 stream=None 建構的，它的
# _colorize() 在 stream is None 時無條件著色（根本不會問 isatty），所以下載模型
# 那幾行會帶著 \x1b[32m…\x1b[0m 進來，而 tk.Text 不懂 ANSI，會原樣顯示成亂碼
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
# Tk 8.6 無法處理 BMP 以外的字元（路徑或 traceback 裡的 emoji 會讓 insert 丟
# TclError），先換成替代字元，避免一個字毀掉整個日誌輸出
_NON_BMP_RE = re.compile(r"[^\u0000-\uffff]")


def load_config() -> dict:
    """讀設定檔；壞掉或格式不對一律當成空設定（不要讓 GUI 開不起來）。"""
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return cfg if isinstance(cfg, dict) else {}


def save_config(cfg: dict) -> bool:
    """寫設定檔。回傳是否成功 —— 呼叫端必須據此決定要不要跟使用者說「已記住」，
    否則在唯讀／漫遊設定檔的環境下會每次都宣告成功、每次啟動又忘記。"""
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        return True
    except Exception:
        return False


def log_dir() -> Path:
    """執行紀錄要落在哪個資料夾。

    釘在**本檔所在的資料夾**、不是使用者挑的專案資料夾：「啟動.vbs」就在旁邊，
    出事時要找的人是雙擊它的那一個，而挑選器可以在同一次執行中途換掉專案位置
    ——紀錄檔跟著跑的話，同一趟的內容會散在兩個地方。"""
    override = os.environ.get(LOG_DIR_ENV)
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / LOG_DIR_NAME


def purge_old_logs(keep_days: int = LOG_KEEP_DAYS) -> None:
    """清掉太舊的紀錄檔。⚠️ **要在開新檔之前做**，否則剛建好的這一份會被自己
    的規則掃到（在系統時鐘往回調過的機器上真的會發生）。"""
    cutoff = time.time() - keep_days * 86400
    try:
        old = [q for q in log_dir().glob("*.log") if q.stat().st_mtime < cutoff]
    except OSError:
        return
    for q in old:
        try:
            q.unlink()
        except OSError:
            pass


def _git_sha() -> str:
    """短 commit sha；取不到回空字串。

    直接讀 `.git`、**不叫 `git` 指令**：啟動路徑不該多開一個行程，而使用者拿到
    的可能是複製過去的資料夾（這個專案的交付方式就是複製整個資料夾），機器上
    不見得有 git。"""
    git = Path(__file__).resolve().parent / ".git"
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not head.startswith("ref: "):
        return head[:7]          # detached HEAD：HEAD 本身就是 sha
    ref = head[5:].strip()
    try:
        return (git / ref).read_text(encoding="utf-8").strip()[:7]
    except OSError:
        pass
    try:                          # 鬆散檔不在，查打包過的 ref
        packed = (git / "packed-refs").read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in packed.splitlines():
        sha, _, name = line.partition(" ")
        if name.strip() == ref:
            return sha[:7]
    return ""


def code_version() -> str:
    """跑出這份紀錄的是哪一版的碼。**取不到就明說，不要假裝有。**

    版號讀 `pyproject.toml`（它就在旁邊，一定是這一份的值），再補上 sha ——
    版號一整段開發期間都不會動，能分辨「今天這一版」的只有 sha。"""
    ver = ""
    try:
        text = (Path(__file__).resolve().parent / "pyproject.toml").read_text(
            encoding="utf-8")
        m = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.M)
        ver = m.group(1) if m else ""
    except OSError:
        pass
    sha = _git_sha()
    if ver and sha:
        return f"{ver} ({sha})"
    return ver or sha or "(取不到)"


def log_header(path: Path) -> str:
    """紀錄檔的檔頭：哪一版的碼、在什麼環境上跑的。

    分析一份 log 之前一定要先知道這幾件事，而事後再問使用者就是多一趟往返。"""
    now = datetime.datetime.now()
    return "\n".join([
        "=" * 72,
        f"{APP_TITLE}  執行紀錄  開始 {now:%Y-%m-%d %H:%M:%S}",
        f"  程式版本：{code_version()}",
        f"  紀錄檔：{path}",
        f"  Python：{sys.version.split()[0]}  平台：{sys.platform}",
        "=" * 72,
        "",
    ])


def open_run_log() -> tuple[Path | None, "io.TextIOBase | None"]:
    """開這一趟的紀錄檔，回傳 (路徑, 檔案物件)。

    ⚠️ **失敗一律回 (None, None)、不拋例外**：磁碟唯讀、防毒攔截、資料夾被同步
    工具鎖住都會走到這裡，而「留不了底」絕不能升級成「打不開程式」——那正是
    「啟動（顯示訊息）.bat」這條退路存在的情境。"""
    purge_old_logs()
    path = log_dir() / f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # newline="" ：全檔統一用 LF，不要讓同一份檔案裡混著 CRLF 與 LF
        # （Python 的 traceback 帶的本來就是 LF）
        f = path.open("a", encoding="utf-8", newline="")
        f.write(log_header(path))
        f.flush()
    except OSError:
        return None, None
    return path, f


def is_project_dir(path: Path) -> bool:
    """一個合格的專案根目錄：底下有 pdf2ppt 套件（pdf2ppt/cli.py）。"""
    try:
        return (path / "pdf2ppt" / "cli.py").is_file()
    except Exception:
        return False


def find_project_dir() -> Path | None:
    """依序嘗試：1) GUI 自身所在目錄 2) 設定檔記住的路徑 3) 目前工作目錄。

    自身目錄優先於記憶路徑：本檔就存放在專案根目錄，而「把它複製到另一份
    checkout 執行」是最自然的用法。記憶路徑若優先，一個曾經用過資料夾挑選器的
    使用者會在新 checkout 裡靜靜地跑舊 checkout 的程式碼。
    """
    here = Path(__file__).resolve().parent
    if is_project_dir(here):
        return here

    remembered = load_config().get("project_dir")
    if isinstance(remembered, str) and remembered:
        try:
            if is_project_dir(Path(remembered)):
                return Path(remembered)
        except Exception:
            pass

    cwd = Path.cwd()
    return cwd if is_project_dir(cwd) else None


# --font 只設定輸出的 <a:ea> 東亞字型；style.py 的 _measure_em() 一律以
# C:\Windows\Fonts\msyh.ttc（YaHei）量寬度，換字型不會跟著換度量衡。
# 因此非 YaHei 的選擇會讓所有寬度夾制以錯誤的字型計算 —— 介面上有註明。
# PingFang TC 是 macOS 專屬、在 Windows 只會靜默回落，故不列入。
FONT_CHOICES = [
    "Microsoft YaHei",
    "Microsoft JhengHei",
    "Noto Sans CJK TC",
    "標楷體",
]


# --------------------------------------------------------------------------- #
#  把背景執行緒裡的 print() 導到 GUI 的工具
# --------------------------------------------------------------------------- #
class QueueWriter(io.TextIOBase):
    """一個假的 stdout：寫入的文字丟進 queue，由主執行緒撈出來顯示。

    繼承 io.TextIOBase 取得 closed / newlines / writelines() / close() /
    isatty() / readable() / seekable()，以及會丟 io.UnsupportedOperation 的
    fileno()（同時是 OSError 也是 ValueError，正是呼叫端會攔的型別）；這裡只
    留真正專案特有的部分：cli.py 會讀 sys.stdout.encoding 並可能呼叫
    reconfigure()。
    """

    encoding = "utf-8"
    errors = "replace"

    def __init__(self, q: "queue.Queue") -> None:
        super().__init__()
        self.q = q

    def write(self, text: str) -> int:
        if text:
            self.q.put(_ANSI_RE.sub("", text))
        return len(text)

    def writable(self) -> bool:
        return True

    def close(self) -> None:
        pass    # 這個串流活得比任何一次轉檔久，關掉它會讓後續輸出無處可去

    def reconfigure(self, *args, **kwargs) -> None:
        """cli.py 會呼叫 sys.stdout.reconfigure(encoding="utf-8")；
        我們本來就是 utf-8，當作無操作即可。"""
        enc = kwargs.get("encoding")
        if enc:
            self.encoding = enc


# --------------------------------------------------------------------------- #
#  主應用
# --------------------------------------------------------------------------- #
class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("760x620")
        self.minsize(680, 520)

        self.log_queue: "queue.Queue" = queue.Queue()
        # 整個行程共用同一個 writer。pdf2ppt 的相依套件會在 import 當下就把
        # 當時的 sys.stdout/sys.stderr 綁進模組全域（pymupdf 的 _g_out_message /
        # _g_out_log、rapidocr 的 logging.StreamHandler、tqdm 帶進來的
        # colorama.orig_stdout），而那次 import 正好發生在重導向生效期間 ——
        # finally 還原 sys.stdout 收不回這些參考。每輪都新建 writer 的話，
        # 第二輪之後這些套件的訊息就會流進一個沒人管的舊物件；共用一個實例
        # 讓那些逃逸的參考在定義上就是對的。
        self.writer = QueueWriter(self.log_queue)
        # 啟動當下的 stderr，要留著：從「啟動.vbs」進來時它是 cmd 重導向到
        # 系統暫存檔的 handle（那個檔就是 .vbs 在程式非正常結束時拿來跳訊息框
        # 的內容），從「啟動（顯示訊息）.bat」進來時它就是主控台。
        # ⚠️ 必須存這個參考而不是每次讀 sys.stderr——轉檔期間 sys.stderr 是
        # QueueWriter（只到日誌區、關掉視窗就沒了），而錯誤最需要留底的正是
        # 那段時間。
        self._boot_stderr = sys.stderr
        # 這一趟的執行紀錄。開在 _build_ui 之前：建介面途中炸掉的話，這是唯一
        # 收得到的地方。⚠️ 開不起來就是 (None, None)，一切照常跑（見
        # open_run_log 的說明）。
        self._log_lock = threading.Lock()
        self._log_pending = ""
        self._log_path, self._log_file = open_run_log()
        self.worker: threading.Thread | None = None
        self.running = False
        self.project_dir: Path | None = find_project_dir()
        # 目前 sys.modules 裡的 pdf2ppt 是從哪個目錄載入的
        self.loaded_from: Path | None = None
        # 我們上次自動帶出來的輸出路徑；使用者改過就不再自動跟著換
        self._auto_out = ""

        self._build_vars()
        self._build_ui()
        self._refresh_project_label()
        # 位置要講出來：出事時使用者才知道要附哪一個檔，而不是被問「log 在哪」
        self._append(f"執行紀錄：{self._log_path}\n" if self._log_path
                     else "（無法建立執行紀錄檔；錯誤訊息只會留在這個日誌區，"
                          "關掉視窗就沒了。要留底請改用「啟動（顯示訊息）.bat」。）\n")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(80, self._drain_log)

    # ---- 變數 ----
    def _build_vars(self) -> None:
        self.in_path = tk.StringVar()
        self.out_path = tk.StringVar()
        self.pages = tk.StringVar()
        self.lang = tk.StringVar()
        self.font = tk.StringVar(value=FONT_CHOICES[0])
        self.device = tk.StringVar(value="auto")
        # 預設值與 pdf2ppt/cli.py 的 argparse 定義一致，改一邊要改兩邊
        self.dpi = tk.IntVar(value=200)
        self.min_score = tk.DoubleVar(value=0.5)
        self.bold_mode = tk.StringVar(value="auto")       # auto / never / always

        self.fast = tk.BooleanVar(value=False)
        self.no_s2t = tk.BooleanVar(value=False)
        # 這一個存的是**反向**旗標：cli.py 的預設是 --no-cover，所以 GUI 拿
        # 「要不要輸出獨立色塊」當開關（不勾 = 走預設）。2026-08-23 到
        # 08-24 之間它曾經是主畫面上唯一的核取方塊、且預設與 cli.py 相反，
        # 量完 A/B 後兩邊的預設對齊了。其餘布林選項與 argparse 一致。
        self.cover = tk.BooleanVar(value=False)
        self.keep_watermark = tk.BooleanVar(value=False)
        self.keep_tiny_text = tk.BooleanVar(value=False)
        self.merge_lines = tk.BooleanVar(value=False)
        self.debug = tk.BooleanVar(value=False)

        # 進階區是否展開（不寫進設定檔：每次開起來都回到最單純的畫面）
        self.show_advanced = tk.BooleanVar(value=False)

    # ---- 介面 ----
    def _build_ui(self) -> None:
        pad = self._pad = {"padx": 8, "pady": 4}
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        title = ttk.Label(root, text=APP_TITLE, font=("", 15, "bold"))
        title.pack(anchor="w")
        sub = ttk.Label(
            root,
            text="把 NotebookLM 產出的繁中 PDF 簡報 OCR 後轉成可編輯的 PowerPoint（本地離線執行）。",
            foreground="#666",
        )
        sub.pack(anchor="w", pady=(0, 8))

        # ---- 專案位置區 ----
        proj = ttk.LabelFrame(root, text="專案位置（pdf2ppt 程式所在資料夾）", padding=10)
        proj.pack(fill="x", **pad)
        self.project_label = ttk.Label(proj, text="", foreground="#666",
                                       wraplength=560, justify="left")
        self.project_label.grid(row=0, column=0, sticky="w")
        ttk.Button(proj, text="選擇專案資料夾…",
                   command=self._pick_project).grid(row=0, column=1, padx=6)
        proj.columnconfigure(0, weight=1)

        # ---- 檔案區 ----
        files = ttk.LabelFrame(root, text="檔案", padding=10)
        files.pack(fill="x", **pad)

        ttk.Label(files, text="輸入 PDF：").grid(row=0, column=0, sticky="w")
        ttk.Entry(files, textvariable=self.in_path).grid(
            row=0, column=1, sticky="ew", padx=6)
        ttk.Button(files, text="瀏覽…", command=self._pick_input).grid(
            row=0, column=2)

        ttk.Label(files, text="輸出 PPTX：").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(files, textvariable=self.out_path).grid(
            row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        ttk.Button(files, text="另存…", command=self._pick_output).grid(
            row=1, column=2, pady=(6, 0))
        files.columnconfigure(1, weight=1)

        # 主畫面到這裡就結束：選項一個都不露出來（日常轉檔一項都不必動）。
        # 色塊那一項曾經留在這裡做 A/B，量完之後收進了進階區。

        # ---- 進階區的收合按鈕 ----
        # 底下兩區建好但不 pack，按下去才用 before=actions 插回原位
        toggle_row = ttk.Frame(root)
        toggle_row.pack(fill="x", padx=8, pady=(2, 0))
        self.adv_toggle = ttk.Button(toggle_row, text=ADV_SHOW_TEXT,
                                     width=34,
                                     command=self._toggle_advanced)
        self.adv_toggle.pack(side="left")

        # ---- 常用選項 ----
        opt = self.opt_frame = ttk.LabelFrame(root, text="常用選項", padding=10)

        ttk.Label(opt, text="頁碼（例 1-5,8，留空=全部）：").grid(
            row=0, column=0, sticky="w")
        ttk.Entry(opt, textvariable=self.pages, width=18).grid(
            row=0, column=1, sticky="w", padx=6)

        ttk.Label(opt, text="中文字型：").grid(row=0, column=2, sticky="e")
        ttk.Combobox(opt, textvariable=self.font, values=FONT_CHOICES,
                     width=20).grid(row=0, column=3, sticky="w", padx=6)

        ttk.Label(opt, text="推論裝置：").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(opt, textvariable=self.device,
                     values=["auto", "cpu", "dml", "cuda"], width=8,
                     state="readonly").grid(row=1, column=1, sticky="w",
                                            padx=6, pady=(8, 0))

        ttk.Label(opt, text="粗體模式：").grid(row=1, column=2, sticky="e", pady=(8, 0))
        ttk.Combobox(opt, textvariable=self.bold_mode,
                     values=["auto", "never", "always"], width=10,
                     state="readonly").grid(row=1, column=3, sticky="w",
                                            padx=6, pady=(8, 0))

        ttk.Label(opt, text="渲染 DPI：").grid(row=2, column=0, sticky="w", pady=(8, 0))
        # 遞增值必須讓 200 落在序列上：整條管線的門檻（TPL_SIGMA、
        # MIN_INK_ROW_PX、8px 字墨切群、COVER_PAD_PX…）都是 200dpi 的絕對像素，
        # 原本的 from_=72/increment=20 序列是 72,92,…,192,212，永遠踩不到 200，
        # 使用者只要按一下箭頭就再也回不到唯一校準過的作業點
        ttk.Spinbox(opt, from_=100, to=600, increment=25, textvariable=self.dpi,
                    width=8).grid(row=2, column=1, sticky="w", padx=6, pady=(8, 0))

        ttk.Label(opt, text="最低信心分數：").grid(row=2, column=2, sticky="e", pady=(8, 0))
        ttk.Spinbox(opt, from_=0.0, to=1.0, increment=0.05, format="%.2f",
                    textvariable=self.min_score, width=8).grid(
            row=2, column=3, sticky="w", padx=6, pady=(8, 0))

        ttk.Label(opt, text="辨識語言（留空=中英）：").grid(
            row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(opt, textvariable=self.lang, width=18).grid(
            row=3, column=1, sticky="w", padx=6, pady=(8, 0))

        ttk.Label(
            opt,
            text="註：字級／粗體／色塊的判別門檻都以 200 DPI + Microsoft YaHei 字寬校準，"
                 "改這兩項會讓排版估算失準。",
            foreground="#888", wraplength=680, justify="left").grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))

        # ---- 進階開關 ----
        adv = self.adv_frame = ttk.LabelFrame(root, text="進階開關", padding=10)
        checks = [
            ("使用快速模型（mobile，較快但繁中較不準）", self.fast),
            ("保留浮水印（NotebookLM／Gemini Notebook）", self.keep_watermark),
            ("保留圖表內小字（預設保留原圖不轉文字）", self.keep_tiny_text),
            ("相鄰同樣式行合併成一個文字方塊", self.merge_lines),
            ("關閉簡體混入修正", self.no_s2t),
            ("色塊獨立畫成矩形（預設是讓文字方塊自帶底色）", self.cover),
            ("輸出除錯資料（OCR 疊圖 PNG + JSON）", self.debug),
        ]
        # 一列一項：雙欄版的第 0 欄由最長的標籤決定寬度，兩欄合計會超出視窗的
        # 最小寬度，在 125%／150% 顯示縮放下右欄的選項會被擠出可見範圍
        for i, (label, var) in enumerate(checks):
            ttk.Checkbutton(adv, text=label, variable=var).grid(
                row=i, column=0, sticky="w", padx=6, pady=2)

        # ---- 動作列 ----
        actions = self.actions_frame = ttk.Frame(root)
        actions.pack(fill="x", **pad)
        self.run_btn = ttk.Button(actions, text="開始轉檔", command=self._start)
        self.run_btn.pack(side="left")
        ttk.Button(actions, text="清除日誌",
                   command=lambda: self.log.delete("1.0", "end")).pack(
            side="left", padx=6)
        self.status = ttk.Label(actions, text="就緒", foreground="#0a0")
        self.status.pack(side="right")

        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(fill="x", **pad)

        # ---- 日誌 ----
        logframe = ttk.LabelFrame(root, text="進度", padding=6)
        logframe.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(logframe, height=12, wrap="word",
                           font=("Consolas", 10))
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(logframe, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.config(yscrollcommand=sb.set)
        self._append("提示：首次轉檔會自動下載 OCR 模型（約數十 MB），"
                     "期間畫面只會顯示進度條，請耐心等候。\n")

    # ---- 進階區收合 ----
    def _toggle_advanced(self) -> None:
        show = not self.show_advanced.get()
        self.show_advanced.set(show)
        if show:
            self.opt_frame.pack(fill="x", before=self.actions_frame,
                                **self._pad)
            self.adv_frame.pack(fill="x", before=self.actions_frame,
                                **self._pad)
            self.adv_toggle.config(text=ADV_HIDE_TEXT)
            # 視窗高度是啟動時就寫死的，展開後的內容塞不進去時 pack 只能去壓
            # 唯一 expand=True 的日誌區（它沒有捲軸可退，只會被壓成幾像素），
            # 所以不夠高就把視窗撐開。只長不縮：收合後多出來的空間全歸日誌
            # 區，而視窗管理員可能把我們要的高度夾掉一截（工作區高度），
            # 「還原成展開前的高度」那種寫法會因為夾掉的那幾像素而失效
            self.update_idletasks()
            need = self.winfo_reqheight()
            if need > self.winfo_height():
                self.geometry(f"{self.winfo_width()}x{need}")
        else:
            self.opt_frame.pack_forget()
            self.adv_frame.pack_forget()
            self.adv_toggle.config(text=ADV_SHOW_TEXT)

    # ---- 專案位置 ----
    def _refresh_project_label(self) -> None:
        if self.project_dir and is_project_dir(self.project_dir):
            self.project_label.config(
                text=f"✓ 已找到：{self.project_dir}", foreground="#0a0")
        else:
            self.project_label.config(
                text="✗ 尚未找到 pdf2ppt 套件，請按右側按鈕選擇專案資料夾"
                     "（裡面要有 pdf2ppt.py 和 pdf2ppt 資料夾）。",
                foreground="#c00")

    def _pick_project(self) -> None:
        if self.running:
            messagebox.showinfo("轉檔進行中", "請等目前這次轉檔結束再切換專案資料夾。")
            return
        d = filedialog.askdirectory(title="選擇 NotebookLM_OCR 專案資料夾")
        if not d:
            return
        path = Path(d)
        if not is_project_dir(path):
            messagebox.showerror(
                "資料夾不正確",
                f"這個資料夾裡找不到 pdf2ppt\\cli.py：\n{path}\n\n"
                "請選擇 NotebookLM_OCR 專案的根目錄"
                "（能看到 pdf2ppt.py 和 pdf2ppt 資料夾的那一層）。")
            return
        self.project_dir = path
        cfg = load_config()
        cfg["project_dir"] = str(path)
        ok = save_config(cfg)
        self._refresh_project_label()
        if ok:
            self._append(f"已記住專案位置：{path}\n")
        else:
            self._append(f"已切換到：{path}（但寫不進設定檔 {CONFIG_PATH}，"
                         "下次啟動需要重新選擇）\n")

    # ---- 檔案挑選 ----
    def _pick_input(self) -> None:
        p = filedialog.askopenfilename(
            title="選擇輸入 PDF",
            filetypes=[("PDF 檔", "*.pdf"), ("所有檔案", "*.*")])
        if not p:
            return
        self.in_path.set(p)
        # 換了輸入檔就跟著換輸出檔。只在「輸出欄是空的」時才自動帶會讓輸出
        # 永遠釘在第一份 PDF 上，第二次轉檔就把第一份的成果直接蓋掉（而且沒走
        # 另存對話框，覆寫確認永遠不會出現）；只要欄位還是我們上次填的值就更新
        cur = self.out_path.get().strip()
        if not cur or cur == self._auto_out:
            self._auto_out = str(Path(p).with_suffix(".pptx"))
            self.out_path.set(self._auto_out)

    def _pick_output(self) -> None:
        init = self._effective_out() or Path("output.pptx")
        p = filedialog.asksaveasfilename(
            title="輸出 PPTX 另存為",
            defaultextension=".pptx",
            initialfile=init.name,
            initialdir=str(init.parent),
            filetypes=[("PowerPoint 簡報", "*.pptx")])
        if p:
            self.out_path.set(p)

    def _effective_out(self) -> Path | None:
        """實際會產出的 .pptx 路徑（輸出欄留空時 cli 會用輸入檔同名）。"""
        out = self.out_path.get().strip()
        if out:
            return Path(out).expanduser().resolve()
        src = self.in_path.get().strip()
        if src:
            return Path(src).expanduser().resolve().with_suffix(".pptx")
        return None

    # ---- 組 argv ----
    def _build_argv(self) -> list[str]:
        src_raw = self.in_path.get().strip()
        if not src_raw:
            raise ValueError("請先選擇輸入 PDF 檔。")
        src = Path(src_raw).expanduser()
        if not src.is_file():
            raise ValueError(f"找不到輸入檔：{src_raw}")

        # 一律傳絕對路徑：worker 會 os.chdir 到專案目錄，相對路徑會在「這裡驗證
        # 通過、那裡找不到」之間打架，輸出檔也會落到專案資料夾而不是使用者預期
        # 的位置
        # in_path is non-empty here, so _effective_out() always resolves
        argv = [str(src.resolve()), "-o", str(self._effective_out())]
        if self.pages.get().strip():
            argv += ["--pages", self.pages.get().strip()]
        if self.lang.get().strip():
            argv += ["--lang", self.lang.get().strip()]
        argv += ["--dpi", str(self.dpi.get())]
        argv += ["--min-score", f"{self.min_score.get():.2f}"]
        argv += ["--device", self.device.get()]
        argv += ["--font", self.font.get()]

        if self.bold_mode.get() == "never":
            argv.append("--no-bold")
        elif self.bold_mode.get() == "always":
            argv.append("--force-bold")

        if self.fast.get():
            argv.append("--fast")
        if self.no_s2t.get():
            argv.append("--no-s2t")
        if self.cover.get():
            argv.append("--cover")
        if self.keep_watermark.get():
            argv.append("--keep-watermark")
        if self.keep_tiny_text.get():
            argv.append("--keep-tiny-text")
        if self.merge_lines.get():
            argv.append("--merge-lines")
        if self.debug.get():
            argv.append("--debug")
        return argv

    # ---- 啟動轉檔 ----
    def _start(self) -> None:
        if self.running:
            return
        if not (self.project_dir and is_project_dir(self.project_dir)):
            messagebox.showwarning(
                "找不到專案",
                "尚未指定 pdf2ppt 專案位置。\n\n"
                "請按上方「選擇專案資料夾…」，指向 NotebookLM_OCR 專案根目錄。")
            return
        try:
            argv = self._build_argv()
        # IntVar/DoubleVar.get() 在 Spinbox 被清空或打成非數字時丟的是
        # tkinter.TclError（它直接繼承 Exception，不是 ValueError），只攔
        # ValueError 會讓例外穿到 Tk 的 report_callback_exception：沒有對話框、
        # 沒有日誌、狀態也不變，按鈕看起來就像壞掉
        except (ValueError, tk.TclError) as e:
            messagebox.showwarning("選項有誤", str(e) or "請檢查 DPI／信心分數欄位。")
            return

        self.running = True
        self.run_btn.config(state="disabled")
        self.status.config(text="轉檔中…", foreground="#c60")
        # 不定長度進度條不帶任何資訊，12ms（83Hz）只是白白讓主執行緒重繪；
        # 用 ttk 的預設節奏即可
        self.progress.start()
        self._append("\n" + "=" * 60 + "\n")
        self._append("執行： pdf2ppt " + " ".join(
            f'"{a}"' if " " in a else a for a in argv) + "\n")

        self.worker = threading.Thread(
            target=self._run_conversion, args=(argv,), daemon=True)
        self.worker.start()

    # ---- 背景執行緒：實際呼叫專案的 main() ----
    def _run_conversion(self, argv: list[str]) -> None:
        old_out, old_err = sys.stdout, sys.stderr
        old_cwd = os.getcwd()
        sys.stdout = sys.stderr = self.writer
        rc = 1
        try:
            proj = Path(self.project_dir)
            # 換過專案資料夾就得把舊的模組丟掉：sys.modules 會快取第一次載入的
            # pdf2ppt，光是 sys.path.insert 換不掉它，結果是「切到新 checkout、
            # 卻仍在跑舊 checkout 的程式碼」而且毫無提示
            if self.loaded_from is not None and self.loaded_from != proj:
                for name in [m for m in list(sys.modules)
                             if m == "pdf2ppt" or m.startswith("pdf2ppt.")]:
                    sys.modules.pop(name, None)
                try:
                    sys.path.remove(str(self.loaded_from))
                except ValueError:
                    pass
                self.log_queue.put(f"專案位置已變更，改載入：{proj}\n")
            if str(proj) not in sys.path:
                sys.path.insert(0, str(proj))
            # 切到專案目錄，確保模型快取等相對路徑落在專案底下
            os.chdir(proj)
            try:
                from pdf2ppt.cli import main
            except ModuleNotFoundError as e:
                # 只有「找不到 pdf2ppt 本身」才是選錯資料夾；相依套件沒裝時把
                # 使用者指去重選資料夾是錯誤的診斷
                if (e.name or "").split(".")[0] == "pdf2ppt":
                    raise ModuleNotFoundError(
                        f"在指定的專案目錄找不到 pdf2ppt 套件：{proj}\n"
                        "請確認該資料夾裡有 pdf2ppt 子資料夾。\n"
                        f"原始錯誤：{e}") from e
                raise ModuleNotFoundError(
                    f"缺少相依套件 {e.name}。\n"
                    f"請在 {proj} 執行：uv sync\n"
                    f"原始錯誤：{e}") from e
            self.loaded_from = proj
            rc = main(argv)
        except SystemExit as e:        # argparse 在參數錯誤時會 raise 這個
            rc = int(e.code) if isinstance(e.code, int) else 1
        except Exception:
            tb = traceback.format_exc()
            self.log_queue.put("\n[發生錯誤]\n")
            self.log_queue.put(tb)
            # 也留一份底：此刻 sys.stderr 是 QueueWriter，只到日誌區，關掉
            # 視窗就沒了；轉檔失敗正是事後最需要拿得出訊息的時候
            self._write_log("[轉檔失敗] argv=" + repr(argv) + "\n" + tb)
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            try:
                os.chdir(old_cwd)
            except Exception:
                self.log_queue.put(
                    f"\n[警告] 無法切回原工作目錄 {old_cwd}，"
                    "檔案對話框的預設位置可能不正確。\n")
            self.log_queue.put(("__DONE__", rc))

    # ---- 主執行緒：把 queue 內容寫進日誌 ----
    def _drain_log(self) -> None:
        try:
            chunks: list[str] = []
            done: int | None = None
            try:
                while True:
                    item = self.log_queue.get_nowait()
                    if isinstance(item, tuple) and item and item[0] == "__DONE__":
                        done = item[1]
                        break
                    chunks.append(str(item))
            except queue.Empty:
                pass
            if chunks:
                # 一次 tick 只 insert / 捲動一次，而不是每個 chunk 一次
                self._append("".join(chunks))
            if done is not None:
                # _finish 會開 modal 對話框（會跑巢狀事件迴圈），不能在 drain
                # 迴圈中間呼叫
                self.after_idle(self._finish, done)
        finally:
            # 無論如何都要重新排程：原本 self.after 寫在 except queue.Empty
            # 之後，任何非 Empty 的例外（Text 丟 TclError、modal 丟 TclError）
            # 都會讓輪詢永久停擺，__DONE__ 再也不會被取出，UI 就卡在「轉檔中…」。
            # 閒置時放慢到 500ms：GUI 是長時間開著的行程，沒在轉檔時用 80ms
            # 叫醒主執行緒只是白白讓行程進不了深度閒置。永遠不停止輪詢，才不會
            # 有「該重啟時沒重啟」的死角。
            self.after(80 if self.running else 500, self._drain_log)

    def _finish(self, rc: int) -> None:
        self.progress.stop()
        try:
            if rc == 0:
                self.status.config(text="完成 ✓", foreground="#0a0")
                out = self._effective_out()
                shown = str(out) if out else "(輸入檔同名 .pptx)"
                self._append(f"\n✓ 轉檔完成：{shown}\n")
                if out is not None and messagebox.askyesno(
                        "完成", f"轉檔完成！\n\n{shown}\n\n要開啟所在資料夾嗎？"):
                    self._open_folder(out)
            else:
                self.status.config(text=f"失敗（代碼 {rc}）", foreground="#c00")
                self._append(f"\n✗ 轉檔失敗（return code = {rc}）\n")
        finally:
            # 對話框關掉之後才解鎖，否則使用者可以在完成對話框還開著時按下
            # 「開始轉檔」，第二輪的日誌會整段看不到
            self.running = False
            self.run_btn.config(state="normal")

    def _open_folder(self, path: Path) -> None:
        # 一定要收到真正的路徑：以前這裡吃的是顯示用字串，輸出欄留空時會拿
        # 「(輸入檔同名 .pptx)」去 resolve，開出使用者的工作目錄
        try:
            folder = str(path.parent)
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            else:
                # 不要用 os.system 組字串：資料夾名稱裡的 " / $ / ` 會被 shell
                # 解讀，輕則開不起來，重則執行內嵌指令
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.run([opener, folder], check=False)
        except Exception as e:
            self._append(f"[開啟資料夾失敗] {e}\n")

    def _append(self, text: str) -> None:
        # 先落地再上畫面：下面那段在 Text 丟 TclError 時會直接 return，而顯示
        # 不出來的內容正是最該留底的那種
        self._log_write(text)
        try:
            self.log.insert("end", _NON_BMP_RE.sub("\ufffd", text))
        except tk.TclError:
            return
        try:
            lines = int(self.log.index("end-1c").split(".")[0])
            if lines > LOG_MAX_LINES:
                self.log.delete("1.0", f"{lines - LOG_MAX_LINES}.0")
        except tk.TclError:
            pass
        self.log.see("end")

    # ---- 錯誤留底 ----
    def _write_log(self, text: str) -> None:
        """把錯誤寫進這一趟的執行紀錄，**同時**寫回啟動當下的 stderr。

        兩個落點各補一個缺口，缺一個就有一種情況看不到東西：

        * 執行紀錄（`logs` 底下那一份）是事後找得回來的那一份，也是使用者要附
          給我們看的那一份。
        * 啟動當下的 stderr：從「啟動（顯示訊息）.bat」進來時它就是主控台
          （使用者當場就看得到），從「啟動.vbs」進來時它是 cmd 重導向的暫存檔
          ——程式若沒能正常結束，`.vbs` 會把那裡面的內容直接跳訊息框。**紀錄檔
          開不起來時（磁碟唯讀、防毒攔截）它就是唯一的落點。**

        全程吞例外——留底失敗絕不能反過來變成新的錯誤，蓋掉真正要記的那一個。"""
        if not text.endswith("\n"):
            text += "\n"
        self._log_write(text)
        out = self._boot_stderr
        if out is None:          # pythonw 在沒有任何 handle 時 stderr 就是 None
            return
        try:
            out.write(text)
            out.flush()
        except Exception:
            pass

    def _log_write(self, text: str) -> None:
        """把一段輸出寫進執行紀錄檔（逐行、逐次 flush）。

        ⚠️ **要上鎖**：畫面上的內容是主執行緒經由 `_append` 寫進來的，而轉檔
        失敗的 traceback 是背景執行緒直接呼叫 `_write_log` 寫的，兩邊會撞在
        一起——交錯的結果是兩段內容都糊掉，而那正是要留的東西。

        ⚠️ **寫壞了就永久關掉這條管子**、不重試：紀錄檔不該有辦法讓 GUI 停下
        來，而對一個寫不進去的檔每次輸出都重試一次，只會讓介面跟著卡住。"""
        if not text or self._log_file is None:
            return
        with self._log_lock:
            f = self._log_file
            if f is None:
                return
            try:
                self._log_pending += text
                while "\n" in self._log_pending:
                    line, self._log_pending = self._log_pending.split("\n", 1)
                    f.write(line.rsplit("\r", 1)[-1] + "\n")
                if "\r" in self._log_pending:
                    # 下載模型的進度條是原地重寫（\r），整串收下來會在紀錄檔裡
                    # 堆出上萬行，而這個檔要保持「貼得進對話」
                    self._log_pending = self._log_pending.rsplit("\r", 1)[-1]
                if len(self._log_pending) > LOG_MAX_PENDING:
                    f.write(self._log_pending + "\n")
                    self._log_pending = ""
                # 逐次 flush：使用者是直接關視窗收工的，留在緩衝區的會整段蒸發，
                # 而那正好是出事的那一段
                f.flush()
            except Exception:
                self._log_file = None
                try:
                    f.close()
                except Exception:
                    pass

    def _log_close(self) -> None:
        """收尾：把還沒換行的殘段寫掉、蓋上結束時間。

        逐次 flush 已經保證「被強制關掉也不會少東西」，這裡只讓正常關閉的那一
        份看起來是完整的（最後一行沒有換行時，殘段本來會留在緩衝區裡）。"""
        with self._log_lock:
            f, self._log_file = self._log_file, None
            if f is None:
                return
            try:
                if self._log_pending.strip():
                    f.write(self._log_pending + "\n")
                self._log_pending = ""
                f.write(f"---- 結束 {datetime.datetime.now():%Y-%m-%d %H:%M:%S}"
                        f" ----\n")
                f.close()
            except Exception:
                pass

    def report_callback_exception(self, exc, val, tb) -> None:
        """Tk 對 callback 裡漏出來的例外預設只印 stderr、不彈任何東西。

        有黑視窗時那還算看得到，改用「啟動.vbs」之後就是徹底靜默——按鈕沒反應
        而畫面毫無說明。改成三件事都做：寫 log、進日誌區、彈對話框。"""
        text = "".join(traceback.format_exception(exc, val, tb))
        self._write_log("[未預期的錯誤]\n" + text)
        try:
            self._append("\n[未預期的錯誤]\n" + text)
        except Exception:
            pass
        try:
            # 講得出檔案位置才有用：叫使用者「去看 log」而不說在哪等於沒說
            where = (f"完整內容已寫進：\n{self._log_path}" if self._log_path
                     else "（執行紀錄檔建立不起來，完整內容只在下方的日誌區）")
            messagebox.showerror("發生未預期的錯誤", f"{val}\n\n{where}")
        except Exception:
            pass

    # ---- 關閉 ----
    def _on_close(self) -> None:
        # worker 是 daemon thread：直接關窗會在任意位置把它砍掉，若正好在
        # prs.save() 寫 zip 的途中，使用者選定的輸出路徑上會留下一個開不起來
        # 的半截 .pptx（而且可能已經蓋掉上一份好檔案）
        if self.running and not messagebox.askokcancel(
                "轉檔進行中",
                "轉檔還在進行。現在關閉會中斷寫檔，"
                "可能在輸出路徑留下一個損壞、無法開啟的 .pptx。\n\n確定要關閉嗎？"):
            return
        self._log_close()
        self.destroy()


def main() -> int:
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
