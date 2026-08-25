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

外觀：Sun Valley 佈景（模仿 Windows 11 Fluent／WinUI）、Microsoft JhengHei UI、
亮暗跟隨 Windows，並且開了 DPI 感知 —— 三個一動就壞的點寫在 apply_ui_style 與
enable_dpi_awareness 的 docstring 裡，取捨（以及「為什麼不是真的 WinUI 3」）見
docs/dev/windows-環境與入口.md 5.1。

版面：主畫面只留輸入／輸出檔，其餘選項全部收在預設收合的「進階選項」區
（_toggle_advanced）。主線的終點「開始轉檔」排在檔案區正下方、收合按鈕**之上**
（使用者 2026-08-25 指示），展開的兩區插在收合按鈕與進度條之間；展開時借走的
視窗高度在收合時原樣還回去（_restore_height_after_collapse）。
色塊的選項曾經是主畫面上唯一的核取方塊（要拿它做 A/B），
2026-08-24 量完之後 cli.py 的預設換成 --no-cover，這裡也就跟著收進進階區、
反向成「輸出獨立色塊形狀」，預設不勾 —— 三方的預設值現在一致。

執行紀錄：每次啟動在本檔所在資料夾底下的 logs 寫一份（檔名是啟動時間＋pid，
保留 30 天），介面日誌區看得到的東西那裡都有，轉檔失敗的 traceback 也在裡面。
「啟動.vbs」那條路自己不落檔，它是在程式沒能正常結束時直接把攔到的訊息跳訊息
框顯示出來。作法與取捨見 docs/dev/gui-啟動與錯誤留底.md。
"""
from __future__ import annotations

import ctypes
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
from tkinter import filedialog, font as tkfont, messagebox, ttk


APP_TITLE = "NotebookLM PDF → PPT 轉檔工具"

# 視窗圖示。⚠️ 路徑要以**本檔所在位置**為基準而不是 cwd：從「啟動.vbs」進來
# 時工作目錄不一定是專案根目錄，而介面上的「選擇專案資料夾…」還會把載入的
# 程式碼換到另一份 checkout ——圖示要跟著這支 GUI 走，不跟著那個選擇走。
# 檔案本身由 tools/make_icon.py 產生（幾何與色票的唯一真值在那支）。
APP_ICON = Path(__file__).resolve().parent / "assets" / "icon.ico"

# 進階區的收合按鈕文字。預設收起來：這些選項全部有校準過的預設值
# （200 DPI + Microsoft YaHei 是整條管線唯一校準過的作業點），日常轉檔一項
# 都不必動，攤在主畫面上只是讓「選檔 → 開始轉檔」這條主線被十幾個控制項擋住。
ADV_SHOW_TEXT = "▸ 進階選項（頁碼、字型、DPI、除錯…）"
ADV_HIDE_TEXT = "▾ 進階選項（收合）"

# --------------------------------------------------------------------------- #
#  外觀（字型、DPI、佈景）
# --------------------------------------------------------------------------- #
# 介面字型（使用者 2026-08-25 指定）。⚠️ **這跟 --font 完全是兩回事**：
# FONT_CHOICES／--font 是**輸出到 PPTX 裡**的東亞字型，預設必須是 Microsoft
# YaHei（style.py 的寬度量測固定用 msyh.ttc 校準，換掉會讓排版估算失準）；
# 這裡只管介面自己的字，兩者不可互相「順手統一」。
UI_FONT = "Microsoft JhengHei UI"
UI_FONT_FALLBACK = "Microsoft JhengHei"   # 舊版 Windows 沒有 UI 版
# 佈景：**Sun Valley**（`sv-ttk`，MIT）—— 一套模仿 Windows 11 Fluent／WinUI 的
# ttk 佈景（圓角、細框線、Fluent 的輸入框與勾選方塊、內建亮／暗兩套）。
#
# ⚠️ **這不是 WinUI 3 本身，也不可能是**（使用者 2026-08-25 問過）：WinUI 3
# （microsoft/microsoft-ui-xaml + WinAppSDK）是 C++/C#/XAML 的原生框架，Tk 的
# 視窗裡放不進 XAML 控制項。要「真的」用 WinUI 3 就得把整個前端改寫成 C#、
# 讓它去呼叫本專案的 CLI（兩套工具鏈、另一套打包，而且這支 GUI 的日誌留底、
# 背景執行緒、換 checkout 重載模組全部要重寫）。取捨見
# docs/dev/windows-環境與入口.md §5。
#
# ⚠️ 佈景只挑得動 **ttk** 控制項；`tk.Text`（日誌區）與視窗底色是 classic 的，
# 顏色要自己餵 —— 就是底下這兩份 PALETTE 存在的理由。
THEME_ENV = "NOTEBOOKLM_PDF2PPT_THEME"     # light / dark，不設就跟隨 Windows
PALETTES = {
    "light": {
        "page": "#fafafa",       # 與 Sun Valley 的 light 視窗底同色
        "muted": "#5d6470",      # 說明文字
        "ok": "#0f7b3f",
        "warn": "#9a5b00",
        "err": "#c02626",
        "log_bg": "#ffffff",
        "log_fg": "#1f2328",
        "log_sel": "#cfe3fb",
    },
    "dark": {
        "page": "#1c1c1c",
        "muted": "#a6adb8",
        "ok": "#5fd18a",
        "warn": "#f0b429",
        "err": "#ff7b72",
        "log_bg": "#202020",
        "log_fg": "#e6e6e6",
        "log_sel": "#2d4f76",
    },
}


def enable_dpi_awareness() -> None:
    """讓 Windows 用真實像素畫這個視窗。⚠️ **必須在建立 Tk 之前呼叫**。

    不設的話，Windows 會把整個視窗當成 96dpi 畫完、再**點陣放大**到顯示縮放
    （本機 150%，就是 1.5×），字的邊緣全是鋸齒 —— 使用者 2026-08-25 回報的
    「UI 字體有鋸齒狀」就是這個，**跟字型無關**（本機的 TkDefaultFont 本來
    就已經是 Microsoft JhengHei UI）。

    設了之後 Tk 量到的是真實 DPI（實測 95.9 → 143.9），**用點數指定的字型會
    自己換算成正確的像素高**，但**寫死的像素數字不會**（geometry、padx、
    wraplength…）——那些一律要過 App.px()，否則 150% 下整個版面會縮成 2/3。
    """
    if not sys.platform.startswith("win"):
        return
    try:                                   # Win8.1+：PROCESS_SYSTEM_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:                               # Win7/8 的舊 API
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass                           # 沒有就算了：只是回到會鋸齒的舊行為


def ui_font_family(root: tk.Misc) -> str:
    """介面要用的字型家族名（挑不到就讓 Tk 用系統預設，不要硬塞不存在的名字）。"""
    fams = set(tkfont.families(root))
    for fam in (UI_FONT, UI_FONT_FALLBACK):
        if fam in fams:
            return fam
    return tkfont.nametofont("TkDefaultFont").actual("family")


def preferred_theme_mode() -> str:
    """"light" 或 "dark"：環境變數優先，否則跟隨 Windows 的「應用程式模式」。

    讀 registry 而不是加一個 darkdetect 依賴 —— 就這一個值，而且它正是
    darkdetect 在 Windows 上讀的那一個。讀不到就當亮色（絕大多數的情況）。"""
    override = (os.environ.get(THEME_ENV) or "").strip().lower()
    if override in PALETTES:
        return override
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        ) as key:
            return "light" if winreg.QueryValueEx(
                key, "AppsUseLightTheme")[0] else "dark"
    except Exception:
        return "light"


def use_dark_titlebar(root: tk.Misc) -> None:
    """把視窗標題列也換成深色（Windows 10 20H1+ 的 DWM 屬性）。

    不做的話深色介面會頂著一條白色標題列，比整片亮色還醜。失敗就算了。"""
    if not sys.platform.startswith("win"):
        return
    try:
        root.update_idletasks()          # 先讓 HWND 真的存在
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int))
    except Exception:
        pass


def apply_ui_style(root: tk.Misc, scale: float) -> tuple[str, dict]:
    """設定字型與佈景，回傳 (字型家族名, 調色盤)。

    字型走 **Tk 的具名字型**（TkDefaultFont…）：所有 ttk 控制項預設就吃這幾個，
    改一次全部跟著換，不必逐個 widget 設 font。⚠️ 連 TkFixedFont 也換掉 ——
    日誌區原本是 Consolas（等寬），使用者 2026-08-25 要求「全部的字體」都用
    Microsoft JhengHei UI。

    ⚠️ **沒有 sv_ttk 也必須開得起來**：這支是使用者的主要入口，為了外觀讓它
    開不了完全不划算。缺套件就留在系統原生佈景（vista），只換字型。
    """
    def px(n: float) -> int:
        return max(1, int(round(n * scale)))

    fam = ui_font_family(root)
    for name, size in (("TkDefaultFont", 10), ("TkTextFont", 10),
                       ("TkMenuFont", 10), ("TkHeadingFont", 10),
                       ("TkIconFont", 10), ("TkTooltipFont", 9),
                       ("TkCaptionFont", 10), ("TkSmallCaptionFont", 9),
                       ("TkFixedFont", 10)):
        try:
            tkfont.nametofont(name, root).configure(family=fam, size=size)
        except tk.TclError:
            pass

    mode = preferred_theme_mode()
    pal = dict(PALETTES[mode])
    st = ttk.Style(root)
    try:
        import sv_ttk
        sv_ttk.set_theme(mode, root)
    except Exception:
        # 佈景載不起來（沒跑過 uv sync、Tcl 版本不合）：字型已經換好了，
        # 版面照舊，只是回到 Windows 原生長相
        pal["page"] = st.lookup("TFrame", "background") or pal["page"]
        return fam, pal

    # ⚠️ **切完佈景要自己補一發 <<ThemeChanged>>**：sv-ttk 的顏色不是寫在佈景
    # 定義裡，而是掛在那個事件上的 configure_colors 設的，而 Tk 8.6.15 在
    # `ttk::style theme use` 時**不會**把事件送到根視窗（實測：set_theme 之後
    # `ttk::style configure .` 仍是空字串，補一發才有值）。少了這一行，ttk 控制項
    # 會沿用母佈景 clam 的淺灰 —— 深色模式下就是一堆白底黑字的標籤散在深色視窗上。
    # ⚠️ **要先 update_idletasks()**：視窗還沒實體化之前，`<<ThemeChanged>>` 送到
    # 根視窗也不會觸發 class binding（實測 tail 與 now 都一樣沒作用，補了這一行
    # 兩者才都成立）—— 而 apply_ui_style 正好跑在整支程式最早的地方。
    root.update_idletasks()
    root.event_generate("<<ThemeChanged>>", when="now")

    # 佈景自帶的字型是 Segoe UI Variable、而且用**像素**指定（-14px）：既不是
    # 使用者要的字型，在 DPI-aware 的 150% 下也會小一號（點數才會跟著 DPI 換算）
    for name, size, bold in (("SunValleyCaptionFont", 9, False),
                             ("SunValleyBodyFont", 10, False),
                             ("SunValleyBodyStrongFont", 10, True),
                             ("SunValleyBodyLargeFont", 12, False),
                             ("SunValleySubtitleFont", 14, True),
                             ("SunValleyTitleFont", 20, True)):
        try:
            tkfont.nametofont(name, root).configure(
                family=fam, size=size, weight="bold" if bold else "normal")
        except tk.TclError:
            pass
    st.configure(".", font=(fam, 10))

    # Sun Valley 沒有涵蓋到、或本專案要加大的幾處
    # 主要動作鈕：吃佈景的 Accent（Fluent 的藍底圓角鈕），只加大字與內距。
    # ⚠️ 樣式名要以 .Accent.TButton 結尾才繼承得到那組圖片元件
    st.configure("Run.Accent.TButton", font=(fam, 12, "bold"),
                 padding=(px(22), px(9)))
    # 進階選項的收合鈕：低調一點，別跟主要動作搶注意力
    st.configure("Adv.TButton", padding=(px(10), px(6)), anchor="w")
    st.configure("Title.TLabel", font=(fam, 15, "bold"))
    st.configure("Muted.TLabel", foreground=pal["muted"])
    st.configure("Status.TLabel", font=(fam, 10, "bold"))
    if mode == "dark":
        use_dark_titlebar(root)
    return fam, pal

# 轉檔結束代碼裡的這一個代表「檔案有了，但至少一頁降級」（cli.py 的
# PARTIAL_RC）。⚠️ 手抄過來的常數，tests/test_docs.py 釘著兩邊一致 ——
# 不 import 是因為 GUI 可以在執行中途改指到另一份 checkout，而那一份未必有它。
PARTIAL_RC = 3

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
#     不會被切成兩半。⚠️ 檔名要帶 pid 才真的成立 —— 見 open_run_log。
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
    # 檔名帶 pid：雙擊兩次「啟動.vbs」會有兩個行程在同一秒走到這裡，而兩邊都是
    # open("a") —— 同一個檔被兩份輸出交錯寫進去，正好是最難讀懂的那種紀錄，而
    # 出事時要讀的就是它
    path = (log_dir()
            / f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}-{os.getpid()}.log")
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
        self._apply_window_icon()
        # DPI 縮放倍率：enable_dpi_awareness() 之後這裡量到的是真實 DPI，
        # 而底下所有寫死的像素（視窗大小、padding、wraplength）都是以 96dpi
        # 為單位寫的，一律要過 px()
        self.ui_scale = self.winfo_fpixels("1i") / 96.0
        self.ui_font, self.pal = apply_ui_style(self, self.ui_scale)
        self.geometry(f"{self.px(760)}x{self.px(640)}")
        self.minsize(self.px(680), self.px(540))
        self.configure(background=self.pal["page"])

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
        # 展開進階區時「借走」的視窗高度：撐開前量到的高度與撐開後量到的高度，
        # 收合時要照原樣還回去（見 _restore_height_after_collapse）
        self._adv_prev_height: int | None = None
        self._adv_grown_height: int | None = None

        self._build_vars()
        self._build_ui()
        self._refresh_project_label()
        # 位置要講出來：出事時使用者才知道要附哪一個檔，而不是被問「log 在哪」
        self._append(f"執行紀錄：{self._log_path}\n" if self._log_path
                     else "（無法建立執行紀錄檔；錯誤訊息只會留在這個日誌區，"
                          "關掉視窗就沒了。要留底請改用「啟動（顯示訊息）.bat」。）\n")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(80, self._drain_log)

    # ---- 外觀 ----
    def _apply_window_icon(self) -> None:
        """標題列、工作列與所有對話框的圖示。

        ⚠️ **失敗一律吞掉**：圖示是純外觀，assets 不在（有人只複製了 .py）或
        Tk 讀不動都不該讓整個程式起不來——那會變成「雙擊沒反應」，而
        「啟動.vbs」把主控台藏掉了，使用者連錯誤都看不到。
        ⚠️ `default=` 那個參數才會套到之後才建出來的 Toplevel（filedialog、
        messagebox）；不加的話只有主視窗換得掉。"""
        try:
            if APP_ICON.is_file():
                self.iconbitmap(default=str(APP_ICON))
        except Exception:
            pass

    # ---- 尺寸 ----
    def px(self, n: float) -> int:
        """把「以 96dpi 為單位寫的像素」換成這台機器上的實體像素。

        ⚠️ 介面裡每一個寫死的像素數字都要走這裡（padding、wraplength、視窗
        大小…）。點數指定的字型不必——Tk 在 DPI-aware 之下會自己換算。"""
        return max(1, int(round(n * self.ui_scale)))

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
        p = self.px                       # 寫死的像素一律過這裡（見 px()）
        pad = self._pad = {"padx": p(10), "pady": p(5)}
        root = ttk.Frame(self, padding=p(14))
        root.pack(fill="both", expand=True)

        title = ttk.Label(root, text=APP_TITLE, style="Title.TLabel")
        title.pack(anchor="w")
        sub = ttk.Label(
            root,
            text="把 NotebookLM 產出的繁中 PDF 簡報 OCR 後轉成可編輯的 PowerPoint（本地離線執行）。",
            style="Muted.TLabel",
        )
        sub.pack(anchor="w", pady=(0, p(10)))

        # ---- 專案位置區 ----
        proj = ttk.LabelFrame(root, text="專案位置（pdf2ppt 程式所在資料夾）",
                              padding=p(12))
        proj.pack(fill="x", **pad)
        self.project_label = ttk.Label(proj, text="", style="Muted.TLabel",
                                       wraplength=p(560), justify="left")
        self.project_label.grid(row=0, column=0, sticky="w")
        ttk.Button(proj, text="選擇專案資料夾…",
                   command=self._pick_project).grid(row=0, column=1, padx=p(6))
        proj.columnconfigure(0, weight=1)

        # ---- 檔案區 ----
        files = ttk.LabelFrame(root, text="檔案", padding=p(12))
        files.pack(fill="x", **pad)

        ttk.Label(files, text="輸入 PDF：").grid(
            row=0, column=0, sticky="w")
        ttk.Entry(files, textvariable=self.in_path).grid(
            row=0, column=1, sticky="ew", padx=p(8))
        ttk.Button(files, text="瀏覽…", command=self._pick_input).grid(
            row=0, column=2)

        ttk.Label(files, text="輸出 PPTX：").grid(
            row=1, column=0, sticky="w", pady=(p(8), 0))
        ttk.Entry(files, textvariable=self.out_path).grid(
            row=1, column=1, sticky="ew", padx=p(8), pady=(p(8), 0))
        ttk.Button(files, text="另存…", command=self._pick_output).grid(
            row=1, column=2, pady=(p(8), 0))
        files.columnconfigure(1, weight=1)

        # 主畫面到這裡就結束：選項一個都不露出來（日常轉檔一項都不必動）。
        # 色塊那一項曾經留在這裡做 A/B，量完之後收進了進階區。

        # ---- 動作列 ----
        # 位置緊接在檔案區底下、排在進階選項的收合按鈕**之前**（使用者
        # 2026-08-25 指示）：主線是「選檔 → 按下去」，把它排在收合按鈕後面等於
        # 讓主線的終點被一個日常不必碰的東西隔開，展開進階區時還會被推到很下面。
        actions = self.actions_frame = ttk.Frame(root)
        actions.pack(fill="x", **pad)
        # 主要動作鈕吃佈景的 Accent 樣式（Fluent 的藍底圓角鈕），連 hover／
        # pressed／disabled 都由佈景畫；加大字級與內距的 Run.Accent.TButton
        # 定義在 apply_ui_style
        self.run_btn = ttk.Button(actions, text="▶  開始轉檔",
                                  style="Run.Accent.TButton",
                                  command=self._start)
        self.run_btn.pack(side="left")
        self.status = ttk.Label(actions, text="就緒", style="Status.TLabel",
                                foreground=self.pal["ok"])
        self.status.pack(side="right", pady=p(4))

        # ---- 進階區的收合按鈕 ----
        # 底下兩區建好但不 pack，按下去才用 before=progress 插回原位（也就是
        # 這顆按鈕的正下方）
        toggle_row = ttk.Frame(root)
        toggle_row.pack(fill="x", padx=8, pady=(2, 0))
        self.adv_toggle = ttk.Button(toggle_row, text=ADV_SHOW_TEXT,
                                     width=34, style="Adv.TButton",
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
            style="Muted.TLabel", wraplength=p(680), justify="left").grid(
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

        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(fill="x", **pad)

        # ---- 日誌 ----
        logframe = ttk.LabelFrame(root, text="進度", padding=6)
        logframe.pack(fill="both", expand=True, **pad)
        # tk.Text 是 classic 控制項，佈景挑不動它 —— 顏色要自己餵
        self.log = tk.Text(logframe, height=12, wrap="word",
                           font=(self.ui_font, 10),
                           relief="flat", borderwidth=0,
                           highlightthickness=0,
                           padx=p(8), pady=p(6),
                           background=self.pal["log_bg"],
                           foreground=self.pal["log_fg"],
                           insertbackground=self.pal["log_fg"],
                           selectbackground=self.pal["log_sel"],
                           selectforeground=self.pal["log_fg"])
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
            self.opt_frame.pack(fill="x", before=self.progress, **self._pad)
            self.adv_frame.pack(fill="x", before=self.progress, **self._pad)
            self.adv_toggle.config(text=ADV_HIDE_TEXT)
            # 視窗高度是啟動時就寫死的，展開後的內容塞不進去時 pack 只能去壓
            # 唯一 expand=True 的日誌區（它沒有捲軸可退，只會被壓成幾像素），
            # 所以不夠高就把視窗撐開。
            self.update_idletasks()
            need = self.winfo_reqheight()
            cur = self.winfo_height()
            if need > cur:
                # 撐開前後的高度都要記下來，收合時照原樣還回去
                self._adv_prev_height = cur
                self.geometry(f"{self.winfo_width()}x{need}")
                self.update_idletasks()
                self._adv_grown_height = self.winfo_height()
        else:
            self.opt_frame.pack_forget()
            self.adv_frame.pack_forget()
            self.adv_toggle.config(text=ADV_SHOW_TEXT)
            self._restore_height_after_collapse()

    def _restore_height_after_collapse(self) -> None:
        """收合進階區之後，把展開時借走的視窗高度還回去。

        不還的話，多出來的空間會**全部**歸給唯一 `expand=True` 的日誌區（pack
        的行為），收合後的畫面比展開前還高一大截，使用者得自己去拉視窗才回得
        到原樣（2026-08-25 使用者回報）。

        ⚠️ **還原的目標是展開前實際量到的高度**，不是「現在的高度減掉展開時
        加的量」——視窗管理員可能把我們要的高度夾掉一截（工作區高度、螢幕邊
        界），減法會把夾掉的那幾像素永久留在視窗上，展開／收合幾次就愈長愈高。

        使用者在展開期間自己拉過視窗就整個不動：那是他要的尺寸，不是我們借的。
        """
        prev, grown = self._adv_prev_height, self._adv_grown_height
        self._adv_prev_height = self._adv_grown_height = None
        if prev is None:
            return                       # 展開時根本沒撐開過，沒有東西要還
        self.update_idletasks()
        cur = self.winfo_height()
        if grown is not None and abs(cur - grown) > 8:
            return                       # 展開期間被手動調過，尊重使用者的尺寸
        # 收合後的內容仍需要的高度是下限：視窗管理員會拒絕比 reqheight 更小的
        # 要求，硬要只會得到一個跟畫面對不上的 geometry 字串
        target = max(prev, self.winfo_reqheight())
        if target < cur:
            self.geometry(f"{self.winfo_width()}x{target}")

    # ---- 專案位置 ----
    def _refresh_project_label(self) -> None:
        if self.project_dir and is_project_dir(self.project_dir):
            self.project_label.config(
                text=f"✓ 已找到：{self.project_dir}",
                foreground=self.pal["ok"])
        else:
            self.project_label.config(
                text="✗ 尚未找到 pdf2ppt 套件，請按右側按鈕選擇專案資料夾"
                     "（裡面要有 pdf2ppt.py 和 pdf2ppt 資料夾）。",
                foreground=self.pal["err"])

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
    def _set_run_enabled(self, enabled: bool) -> None:
        """開始轉檔鈕的鎖／解鎖。

        ⚠️ 底色要跟著換：它是 tk.Button，`state="disabled"` 只會換文字顏色，
        鮮豔的底色照舊留在畫面上，轉檔期間看起來仍像可以按（ttk.Button 的
        disabled 是整顆變灰，換過來就沒有這回事了）。"""
        self.run_btn.state(["!disabled"] if enabled else ["disabled"])

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
        self._set_run_enabled(False)
        self.status.config(text="轉檔中…", foreground=self.pal["warn"])
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
            if rc in (0, PARTIAL_RC):
                # 有頁面降級時不能報成單純的「完成」：檔案是好的，但那幾頁
                # 沒有可編輯文字，而頁碼只寫在日誌區最後一行的 WARNING ——
                # 對話框正好蓋在它上面，按完「否」就再也不會有人往下看
                part = rc == PARTIAL_RC
                self.status.config(
                    text="完成（有頁面降級）" if part else "完成 ✓",
                    foreground=self.pal["warn"] if part else self.pal["ok"])
                out = self._effective_out()
                shown = str(out) if out else "(輸入檔同名 .pptx)"
                tag = "⚠ 轉檔完成，但有頁面降級" if part else "✓ 轉檔完成"
                self._append(f"\n{tag}：{shown}\n")
                note = ("\n\n⚠ 有幾頁沒能轉成文字，只保留了原圖"
                        "（頁碼見下方日誌最後一行的 WARNING）。" if part else "")
                if out is not None and messagebox.askyesno(
                        "完成", f"轉檔完成！\n\n{shown}{note}"
                                f"\n\n要開啟所在資料夾嗎？"):
                    self._open_folder(out)
            else:
                self.status.config(text=f"失敗（代碼 {rc}）",
                                   foreground=self.pal["err"])
                self._append(f"\n✗ 轉檔失敗（return code = {rc}）\n")
        finally:
            # 對話框關掉之後才解鎖，否則使用者可以在完成對話框還開著時按下
            # 「開始轉檔」，第二輪的日誌會整段看不到
            self.running = False
            self._set_run_enabled(True)

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
    # ⚠️ 一定要在建 App（= 建 Tk）之前：Tk 只在啟動時問一次 DPI
    enable_dpi_awareness()
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
