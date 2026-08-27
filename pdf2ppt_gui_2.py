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

   本檔隨專案一起存放在根目錄、pdf2ppt 套件就在旁邊，載入的程式碼**永遠**是
   本檔所在資料夾的那一份（PROJECT_DIR）：介面上沒有位置選擇（使用者
   2026-08-25 指示）。同一層看不到 pdf2ppt/cli.py 就跳訊息框、視窗不開 ——
   那代表這份複製品缺東西，開起來也只會在按下轉檔的那一刻才失敗。

   首次轉檔會自動下載 OCR 模型，需要短暫連網。

這支 GUI 只負責「收集選項 + 呼叫專案的轉檔邏輯 + 即時顯示進度」，真正的
OCR / 排版工作全部沿用 pdf2ppt 套件。

⚠️ 介面上**只露出五個選項**（使用者 2026-08-25 指示）：頁碼、保留浮水印、
關閉簡體混入修正、色塊獨立畫成矩形、保留圖表內小字。理由是其餘那些「改了
會讓結果差很多，或根本用不到」——DPI／字型／信心分數是校準值（200 DPI ＋
Microsoft YaHei 是整條管線唯一校準過的作業點，動了排版估算就失準）、
粗體模式與 --fast 會整份換掉判別依據、--device 有 auto、--lang 預設就是中英、
--merge-lines 與 --debug 是開發用的。它們**不再由 GUI 傳**，直接吃 cli.py 的
argparse 預設值：少一份手抄就少一處會漂移的地方（要調就用命令列）。

外觀：Sun Valley 佈景（模仿 Windows 11 Fluent／WinUI）、Microsoft JhengHei UI、
亮暗跟隨 Windows，並且開了 DPI 感知 —— 三個一動就壞的點寫在 apply_ui_style 與
enable_dpi_awareness 的 docstring 裡，取捨（以及「為什麼不是真的 WinUI 3」）見
docs/dev/windows-環境與入口.md 5.1。

版面：由上而下是**四張卡片**（檔案／進度與動作／轉檔選項／詳細訊息），後兩張
預設收起來、由自己頭上那顆整條寬的收合鈕開關。主畫面只留輸入／輸出檔，那五個
選項全部收在「轉檔選項」區（_toggle_advanced）。主線的終點「開始轉檔」排在檔案區
正下方、收合按鈕**之上**（使用者 2026-08-25 指示）。⚠️ 收合鈕就是那張卡片自己的
標題列，展開的內容長在**同一張卡片裡**（使用者 2026-08-26 指示）。

⚠️ 卡片是 2026-08-26 加的（使用者「參考 MP4-2-SRT UI 的圓角、卡片、顏色」）：
底色分三階 page → card → field（唯一真值在 pdf2ppt/palette.py），圓角底板由
tools/make_skin.py 畫。兩顆收合鈕與「開啟紀錄」坐在**卡片上**、走低調皮
（靜止態就是卡片底色，滑過才浮出灰底）——做成實底的話，畫面上最重的三個元素會是
三條灰橫槓，而它們講的是最不重要的三件事。
色塊的選項曾經是主畫面上唯一的核取方塊（要拿它做 A/B），
2026-08-24 量完之後 cli.py 的預設換成 --no-cover，這裡也就跟著收進選項區、
反向成「輸出獨立色塊形狀」，預設不勾 —— 三方的預設值現在一致。

⚠️ 選項區與日誌區是**手風琴**（_set_advanced／_set_log_shown）：展開選項就收
日誌、按下轉檔就收選項並展開日誌。理由是量出來的——1143x1006 的視窗展開當時的
進階區後 reqheight 是 953 邏輯 px，而本機工作區只有 912（1080p@125% 更只有約
810），兩區同時攤開必定有一截在螢幕外。選項砍到五個之後那一區矮了很多，但手風
琴留著：日誌區是唯一 expand=True 的區塊，兩區同時攤開仍然是「進度看不到」的那
一種版面。高度一律由 _fit_window() 統一決定：量 reqheight、
鉗進所在螢幕的工作區、必要時把視窗往上移；使用者自己拉過視窗之後就只長不縮。

進度：動作卡片上是**同一列**的「開始轉檔／停止轉檔」鈕、進度條與狀態字（舊版散在
三個地方：右上角的「就緒」、中段一條沒有資訊量的 indeterminate 進度條、下方日誌）。
進度條**沒在跑就不顯示**（使用者 2026-08-25 晚指示：閒置時那條 determinate value=0
的空槽橫貫版面中段，讀起來像一條分隔線）；轉檔一開始 grid() 回來，在 cli 印出第一行
`page N (n/total)` 時從 indeterminate 換成 determinate（_scan_line）。⚠️ 狀態字**只報頁數、不報剩餘時間**（使用者 2026-08-25 指示刪掉
「約剩 2 分」那一段）：頁數是量到的，剩餘時間是猜的。轉檔結果不再用互動式對話框問「要開啟資料夾嗎」——那個框正好蓋住
日誌最後一行的降級 WARNING，改成動作卡片上的一條結果列（_show_result），降級的
頁碼直接寫在列上。

執行紀錄：每次啟動在本檔所在資料夾底下的 logs 寫一份（檔名是啟動時間＋pid，
保留 30 天），介面日誌區看得到的東西那裡都有，轉檔失敗的 traceback 也在裡面。
「啟動.vbs」那條路自己不落檔，它是在程式沒能正常結束時直接把攔到的訊息跳訊息
框顯示出來。作法與取捨見 docs/dev/gui-啟動與錯誤留底.md。
"""
from __future__ import annotations

import base64
import ctypes
import datetime
import io
import json
import os
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

# ⚠️ 這是本檔**唯一**從專案套件裡拿的東西，而且是刻意的：`pdf2ppt/palette.py`
# 一行 import 都沒有、`pdf2ppt/__init__.py` 也只有一句 docstring，所以這一行
# **不會**把 numpy／pymupdf／python-pptx 那一整串拉進啟動路徑（那些只有按下轉檔
# 的那一刻、`_run_conversion` 裡 import cli 時才付出）。顏色抽成一份的理由見那支
# 的 docstring —— 產生器（tools/make_skin.py）與這裡共用同一份色票。
from pdf2ppt.palette import PALETTES


APP_TITLE = "NotebookLM PDF → PPT 轉檔工具"

# 專案根目錄 ＝ **本檔所在的資料夾**，沒有第二個候選（使用者 2026-08-25 指示
# 拿掉介面上的位置選擇）。⚠️ 一定要用 `__file__` 而不是 cwd：從「啟動.vbs」／
# 捷徑進來時工作目錄不保證是這裡。合不合格由 is_project_dir() 在 main() 驗一次
# ——不合格就跳訊息框、不開視窗（見 fail_no_project）。
PROJECT_DIR = Path(__file__).resolve().parent

# 視窗圖示。檔案本身由 tools/make_icon.py 產生（幾何與色票的唯一真值在那支）。
APP_ICON = PROJECT_DIR / "assets" / "icon.ico"

# 工作列用來認「這是哪個應用程式」的身分。⚠️ `tools/make_shortcut.py` 會把
# 這個字串讀走寫進 .lnk，兩邊必須同值——不同的話，釘選到工作列的那顆與
# 執行中的視窗會變成兩個各自獨立的按鈕。
APP_ID = "VincentLiang.NotebookLM.Pdf2Ppt"

# 間距尺規（邏輯 px，一律再過 App.px() 換算成實體像素）。⚠️ **版面裡不要再出現
# 別的間距數字**：2026-08-25 晚上使用者說「還是有點擠」，量出來的成因不是字太小
# （基準字級本來就是 10pt），而是**間距的階層是反的**——每個區塊都用同一個
# `pady=5`（實際間距 10px）pack 出去，而卡片自己的 padding 是 12px。外面的縫比
# 裡面的窄，眼睛就分不出群，五個區塊糊成一片。
# 用法：SP_LG＝區塊之間與卡片內距、SP_MD＝卡片裡的欄距、SP_SM＝同一群裡的行距
# 與「區段標題貼著它管的內容」、SP_XL＝卡片內要分成兩件事時的那一道縫。
SP_XS, SP_SM, SP_MD, SP_LG, SP_XL = 4, 8, 12, 16, 24

# 卡片的三個尺規（2026-08-26 卡片化時加的，與姊妹專案 MP4-2-SRT 同源）。⚠️ 那邊
# 的使用者在截圖上圈了卡片邊到內部元件之間那圈白，逐像素掃出 42px、換算回邏輯
# 像素約 27——所以 `CARD_PAD` 走既有尺規的 SP_XL(24)，**第一版寫 16，他當場說
# 太窄**。⚠️ 這三個不可以寫進皮膚的底板圖裡：它們要跟著顯示縮放走（過 App.px()），
# 而圖片自帶的內距是固定像素（`make_skin.SQ_PAD` 那一組是另一件事——那是補回
# sv_ttk 原本圖片自帶的量）。
PAGE_PAD = 20      # 視窗邊 → 卡片

# 視窗尺寸。⚠️ **啟動寬度就是最小寬度**（使用者 2026-08-27 指示）：開起來剛好
# 是下限，要更寬自己拉。所以這兩個地方一定要是**同一個常數**——寫成兩個數字
# 的話，下次調 minsize 就會讓「啟動 ＝ 最小」這件事安靜地不成立。
# ⚠️ 舊值是 880（2026-08-25 晚從 760 提上去的），理由是「760 之下副標那一整句
# 會從左邊界頂到右邊界」。2026-08-27 副標換成更短的一句之後那個理由就沒了
# ——現在整個介面的 reqwidth 只有 468，760 還有很寬的餘裕。
# ⚠️ 高度是另一回事，**不寫死**：閒置時的畫面只有「檔案 + 開始轉檔」，寫死 640
# 等於讓一半的視窗是一個還沒有內容的空白日誌框（2026-08-25 量到的是 51%）。
# 建完介面由 _fit_window() 量出實際需要的高度（2026-08-27 膠囊化後量到 549），之後每次展開／
# 收合也走同一支；底下這個只是它跑起來之前的初值。
WIN_W, WIN_H0 = 760, 460
# ⚠️ minsize 的**高度**要小：它是 _fit_window 縮不下去的地板。
WIN_MIN_H = 320
CARD_PAD = SP_XL   # 卡片邊 → 裡面的元件
CARD_GAP = 20      # 卡片與卡片之間

# 選項區的收合按鈕文字。預設收起來：這五個都有合用的預設值，日常轉檔一項都不
# 必動，攤在主畫面上只是讓「選檔 → 開始轉檔」這條主線被一排控制項擋住。
# ⚠️ 兩個狀態的**標籤要一模一樣、只換三角形**：舊版收合時寫「進階選項（頁碼、
# 字型、DPI、除錯…）」、展開後整句換成「進階選項（收合）」，同一顆鈕在兩個狀態
# 講的是兩件事（一個講內容、一個講動作），而它的寬度又是寫死的 34 字，於是右半
# 邊永遠空著。現在是整條寬、只有三角形會翻。
# ⚠️ 括號裡列的是**實際露出來的那五個**，不是「還有什麼藏在裡面」：2026-08-25
# 把選項砍到五個之後，舊標籤上的字型／DPI／除錯已經沒有對應的控制項了。
ADV_LABEL = "轉檔選項（頁碼、浮水印、簡體修正、色塊、小字）"
LOG_LABEL = "詳細訊息（每頁的處理結果與錯誤）"
# 三角形**只在沒有皮膚時**用得到：有皮膚時它是一張圖（`_set_chevron`），因為字元
# 放不大——使用者 2026-08-27 說「三角形太小」，而字級是整顆鈕共用的，沒辦法只放大
# 一個字元。⚠️ 退路這一對仍然要**兩個狀態同寬**，否則換狀態時整行文字會左右跳一格：
# 實測（Microsoft JhengHei UI，`Font.measure` @10pt）▶／▼ 是 10／13、►／▼ 是 12／13、
# ‣／▾ 是 5／7，這三對都會跳；▸／▾ 是 7／7。
CHEV_SHOW, CHEV_HIDE = "▸  ", "▾  "

# 主要動作鈕的兩個狀態。⚠️ 同一顆鈕**兼任停止**，不是另外擺一顆：多一顆常駐的
# 「停止」在閒置時是永遠灰著的死按鈕，而轉檔中才長出來會讓整列的控制項左右位移。
RUN_TEXT = "▶  開始轉檔"
STOP_TEXT = "■  停止轉檔"
STOPPING_TEXT = "停止中…"
# 同一顆鈕的兩張皮。⚠️ 名字要以 `.Accent.TButton` 結尾：ttk 的樣式選項是照後綴
# 一層層往上找的，`Stop.Run.Accent.TButton` 這樣寫才繼承得到 `Run.Accent.TButton`
# 上面設的字級與內距（layout 則由 SquircleSkin 各給一份，見那裡）。
RUN_STYLE = "Run.Accent.TButton"
STOP_STYLE = "Stop.Run.Accent.TButton"

# 低調按鈕（Fluent 說的 Subtle button）：坐在**卡片上**（收合鈕就是那張卡片自己的
# 標題列），靜止態就是卡片底色本身、滑過才浮出灰底。⚠️ 這三顆 2026-08-26 之前確實
# 在卡片之外、靜止色是視窗底，那次改成「展開的內容長在同一張卡片裡」時一起搬進
# 卡片，`make_skin` 給它們的 `on` 也跟著從 `page` 換成 `card`——註解漏改到 2026-08-27
# 才發現。⚠️ **要改 `on` 之前先確認父容器**：`adv_toggle` 掛在 `adv_card`、
# `log_toggle` 與 `open_log_btn` 掛在 `log_card` 裡的 `head`。⚠️ 兩顆整條寬的收合鈕與「開啟紀錄」都走這個
# ——做成實底的話，畫面上最重的三個元素會是三條灰橫槓，而它們講的是最不重要
# 的三件事。⚠️ 名字要以 `.TButton` 結尾（ttk 的樣式選項照後綴一層層往上找）。
ADV_STYLE = "Adv.TButton"       # 整條寬的收合鈕（區段標題）
SUBTLE_STYLE = "Subtle.TButton"  # 同一張皮、小一號的內距（開啟紀錄）

# 「選檔」那條主線的起點：靜止是**白底藍框藍字**，滑鼠經過**整顆翻成藍底白字**
# （使用者 2026-08-27 指定，比照 apple.com 那一頁「查看價格」那顆）。
# ⚠️ **整個畫面只有這一顆**。「變更…」一度也套上去，使用者當場要求還原成一般的
# 灰底鈕：**主要焦點只有一個**——輸出檔名程式自己帶得出來，改它是例外不是主線；
# 「開啟簡報／開啟資料夾」則是跑完之後的分岔。同一種強調用在每一顆上，就等於
# 沒有強調。
CTA_STYLE = "Cta.TButton"

# 狀態字會出現的**所有**長相。用途是量出右欄要保留多寬——⚠️ 這一格的寬度必須
# 釘住（不然「就緒」換成「載入 OCR 引擎…」時進度條的右端會跟著左右抽動），但
# **要用量的、不要用猜的**：2026-08-25 一開始寫死 `width=20` 個字元，結果進度條
# 右邊留了一塊永遠用不到的空白（使用者截圖圈出來的就是它）。
# ⚠️ 新增狀態字時要一併加進這份名單，否則那一個會把欄位撐開、進度條當場縮一截。
STATUS_SAMPLES = ("等待選檔", "就緒", "準備中…", "載入 OCR 引擎…",
                  # 頁數：三位數是這個工具實務上的上限（NotebookLM 的簡報頁數
                  # 遠小於此），寬度取最寬的數字字形
                  "888/888 頁",
                  "完成 ✓", "完成（有降級）", "已停止", "停止中…",
                  "失敗（代碼 78）")

# --------------------------------------------------------------------------- #
#  外觀（字型、DPI、佈景）
# --------------------------------------------------------------------------- #
# 介面字型（使用者 2026-08-25 指定）。⚠️ **這跟 --font 完全是兩回事**：
# `--font` 是**輸出到 PPTX 裡**的東亞字型，必須是 Microsoft YaHei（style.py 的
# 寬度量測固定用 msyh.ttc 校準，換掉會讓排版估算失準——這也正是介面上不再露出
# 字型選單的理由）；這裡只管介面自己的字，兩者不可互相「順手統一」。
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
# 顏色要自己餵 —— 那正是色票（`pdf2ppt/palette.py`）存在的理由。
THEME_ENV = "NOTEBOOKLM_PDF2PPT_THEME"     # light / dark，不設就跟隨 Windows
# ⚠️ **色票不在這裡**（2026-08-26 起）：`pdf2ppt/palette.py` 是唯一真值，皮膚產生
# 器 `tools/make_skin.py` 讀的是同一份。它原本真的分成兩份（產生器一份「畫進圖片
# 的顏色」、這裡一份「文字的顏色」），而重疊的鍵一旦漂開，症狀是「按鈕的藍跟卡片
# 邊框的灰差一階」——肉眼看得到卻查不出來源。


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


def set_app_user_model_id() -> None:
    """讓工作列用「視窗自己的圖示」，不要沿用啟動鏈上游那支執行檔的。

    ⚠️ **必須在建立第一個視窗之前呼叫**（和 enable_dpi_awareness 一樣）：
    視窗一旦建出來，工作列就已經把它歸好隊了。

    症狀是使用者 2026-08-25 回報的「工作列上的圖示不是我設計的那顆」——標題列
    那顆是對的，**工作列那顆是 wscript 的**。兩顆走的是不同的路：標題列讀視窗
    的 `WM_SETICON`（`iconbitmap` 設的就是它），工作列則是先把視窗歸到某個
    AppUserModelID、再用**那個身分**的圖示。行程沒有自己宣告身分時，Windows
    會沿用啟動鏈上游的執行檔，而我們這條鏈是「捷徑 → wscript.exe → cmd → uv
    → pythonw」，於是拿到 wscript 的圖示。宣告了就用視窗自己的。
    """
    if not sys.platform.startswith("win"):
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass                               # 純外觀，失敗就回到舊行為


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


def window_handle(root: tk.Misc) -> int:
    """視窗真正的 top-level HWND（拿不到回 0）。

    ⚠️ **`winfo_id()` 不是它**：那是 Tk 自己那個**子**視窗，DWM 與工作列都不認
    —— 要往上取一層才是工作列上那顆按鈕對應的視窗。

    ⚠️ **`restype` 一定要設**：`ctypes.windll` 的預設回傳型別是 `c_int`（32 位
    元），而 64 位元 Windows 的 HWND 是指標寬。值小的時候看起來完全正常，一旦
    某次配到高位元有值的 handle 就會被**靜默截斷**成另一個視窗的號碼——那種
    bug 只會偶爾發生一次，查起來毫無線索。
    """
    user32 = ctypes.windll.user32
    user32.GetParent.restype = ctypes.c_void_p
    user32.GetParent.argtypes = [ctypes.c_void_p]
    return user32.GetParent(root.winfo_id()) or 0


def use_dark_titlebar(root: tk.Misc) -> None:
    """把視窗標題列也換成深色（Windows 10 20H1+ 的 DWM 屬性）。

    不做的話深色介面會頂著一條白色標題列，比整片亮色還醜。失敗就算了。"""
    if not sys.platform.startswith("win"):
        return
    try:
        root.update_idletasks()          # 先讓 HWND 真的存在
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(window_handle(root)), 20,
            ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int))
    except Exception:
        pass


# --------------------------------------------------------------------------- #
#  工作列：使用者切走之後，唯一還看得見的東西
# --------------------------------------------------------------------------- #
# ⚠️ 這一整段的存在理由是「**使用者不會盯著這個視窗看**」：一份三十頁的簡報要
# 跑好幾分鐘，人會切去做別的事，而那一刻視窗裡的進度條、狀態字、結果列**全部
# 看不見了**。Windows 對這件事有兩個原生答案，這裡兩個都用——轉檔中把工作列
# 按鈕本身畫成進度條，收工時閃那顆按鈕。
#
# ⚠️ **絕對不要改成把視窗搶到前景**（`focus_force`／`deiconify`／`-topmost`）：
# 使用者這時正在別的視窗打字，搶焦點會把他的按鍵吃掉。而且 Windows 本來就有
# 前景鎖擋著，擋下來的結果**還是閃工作列**——差別只在系統選的閃法比我們吵。
#
# 全段沿用本檔既有的原則（見 `set_app_user_model_id`）：**純外觀，任何一步失敗
# 就安靜回到舊行為**，不可以讓轉檔本身跟著倒。

# ITaskbarList3（shell32 內建，Win7 起）。⚠️ vtable 的位置是介面定義的一部分、
# 不會變動：IUnknown 佔 0-2、ITaskbarList 佔 3-7、ITaskbarList2 佔 8，
# ITaskbarList3 自己的方法從 9 開始算。
_CLSID_TASKBARLIST = "{56FDF344-FD6D-11D0-958A-006097C9A090}"
_IID_ITASKBARLIST3 = "{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}"
_VT_HRINIT = 3
_VT_SETPROGRESSVALUE = 9
_VT_SETPROGRESSSTATE = 10
# TBPFLAG（shellapi.h）。⚠️ 這是**位元旗標**不是序號，別自己重排。
TBPF_NOPROGRESS = 0x0
TBPF_INDETERMINATE = 0x1
TBPF_NORMAL = 0x2
TBPF_ERROR = 0x4
TBPF_PAUSED = 0x8

# FlashWindowEx 的旗標。只閃**工作列按鈕**（TRAY），不閃標題列（CAPTION）：
# 視窗如果只是被蓋住一半，標題列閃起來很吵而且沒有多給任何資訊。
# TIMERNOFG＝一直閃到使用者把視窗切到前景為止，不必自己算次數。
FLASHW_TRAY = 0x2
FLASHW_TIMERNOFG = 0xC

_taskbar_ptr: ctypes.c_void_p | None = None
_taskbar_dead = False        # 建過一次失敗就不再重試（每頁都重試一次會很吵）


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]


class _FLASHWINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p),
                ("dwFlags", ctypes.c_uint), ("uCount", ctypes.c_uint),
                ("dwTimeout", ctypes.c_uint)]


def _com_call(ptr: ctypes.c_void_p, index: int, *argtypes):
    """取 COM 物件 vtable 上第 `index` 個方法，回傳可直接呼叫的函式。

    呼叫慣例是 `fn(ptr, 其餘參數…)` —— COM 的 this 指標要自己帶。"""
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p)).contents.value
    slot = ctypes.cast(vtbl, ctypes.POINTER(ctypes.c_void_p))[index]
    return ctypes.WINFUNCTYPE(
        ctypes.c_long, ctypes.c_void_p, *argtypes)(slot)


def _taskbar() -> ctypes.c_void_p | None:
    """取得 ITaskbarList3（第一次呼叫時建立並 `HrInit`）。失敗一律回 None。

    ⚠️ **只能在主執行緒呼叫**：COM 物件綁在建立它的 apartment 上，而
    `CoInitialize` 給的是 STA。本檔所有呼叫點（`_start`／`_scan_line`／
    `_finish`）都在 Tk 的主執行緒上，背景工作執行緒不可以碰它。"""
    global _taskbar_ptr, _taskbar_dead
    if _taskbar_ptr is not None or _taskbar_dead:
        return _taskbar_ptr
    try:
        ole32 = ctypes.windll.ole32
        # 已經初始化過會回 S_FALSE(1)，那不是錯誤，不必也不該去 CoUninitialize
        ole32.CoInitialize(None)
        clsid, iid = _GUID(), _GUID()
        if ole32.CLSIDFromString(_CLSID_TASKBARLIST, ctypes.byref(clsid)) < 0:
            raise OSError("CLSIDFromString")
        if ole32.IIDFromString(_IID_ITASKBARLIST3, ctypes.byref(iid)) < 0:
            raise OSError("IIDFromString")
        ptr = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid), None, 1,          # CLSCTX_INPROC_SERVER
            ctypes.byref(iid), ctypes.byref(ptr))
        if hr < 0 or not ptr:
            raise OSError(f"CoCreateInstance hr=0x{hr & 0xFFFFFFFF:08X}")
        if _com_call(ptr, _VT_HRINIT)(ptr) < 0:
            raise OSError("HrInit")
        _taskbar_ptr = ptr
    except Exception:
        _taskbar_dead = True             # 純外觀：這台機器沒有就算了
    return _taskbar_ptr


def taskbar_progress(root: tk.Misc, done: int, total: int) -> None:
    """把工作列按鈕畫成進度條。`total <= 0` 代表「還不知道總量」（跑馬燈）。

    對應視窗裡那條 `ttk.Progressbar` 的兩個階段：載入引擎時沒有頁數可報，用
    indeterminate；收到第一行 `page N (n/total)` 之後才有分母。"""
    if not sys.platform.startswith("win"):
        return
    try:
        tb = _taskbar()
        hwnd = window_handle(root)
        if tb is None or not hwnd:
            return
        state = TBPF_NORMAL if total > 0 else TBPF_INDETERMINATE
        _com_call(tb, _VT_SETPROGRESSSTATE, ctypes.c_void_p, ctypes.c_int)(
            tb, hwnd, state)
        if total > 0:
            _com_call(tb, _VT_SETPROGRESSVALUE, ctypes.c_void_p,
                      ctypes.c_ulonglong, ctypes.c_ulonglong)(
                tb, hwnd, done, total)
    except Exception:
        pass


def taskbar_finish(root: tk.Misc, state: str) -> None:
    """收工時的工作列狀態：`ok` 清掉、`warn` 留黃的、`error` 留紅的。

    ⚠️ **有降級與失敗要「留在那裡」**，不是清掉：那條顏色正是給「還沒切回來的
    人」看的——工作列上一眼就知道這趟不是乾淨完成，不必先切回視窗才發現。
    下一趟 `_start()` 會把它蓋掉，關掉視窗也就沒了。

    ⚠️ **`ERROR`／`PAUSED` 要先有長度才看得到顏色**：那兩個狀態只換色、不動
    數值，前一刻若停在 0% 就等於畫了一條看不見的紅線。所以先推到滿格再換色。"""
    if not sys.platform.startswith("win"):
        return
    try:
        tb = _taskbar()
        hwnd = window_handle(root)
        if tb is None or not hwnd:
            return
        flag = {"warn": TBPF_PAUSED, "error": TBPF_ERROR}.get(
            state, TBPF_NOPROGRESS)
        if flag != TBPF_NOPROGRESS:
            _com_call(tb, _VT_SETPROGRESSVALUE, ctypes.c_void_p,
                      ctypes.c_ulonglong, ctypes.c_ulonglong)(tb, hwnd, 1, 1)
        _com_call(tb, _VT_SETPROGRESSSTATE, ctypes.c_void_p, ctypes.c_int)(
            tb, hwnd, flag)
    except Exception:
        pass


def flash_taskbar(root: tk.Misc) -> None:
    """閃工作列按鈕，直到使用者把視窗切回前景。

    ⚠️ **視窗已經在前景就什麼都不做**：人就坐在這個畫面前面，結果列已經把話
    講完了，再閃一次只是噪音（而且前景視窗閃自己在 Windows 上根本看不出來）。
    """
    if not sys.platform.startswith("win"):
        return
    try:
        hwnd = window_handle(root)
        if not hwnd:
            return
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        if user32.GetForegroundWindow() == hwnd:
            return
        info = _FLASHWINFO(ctypes.sizeof(_FLASHWINFO), hwnd,
                           FLASHW_TRAY | FLASHW_TIMERNOFG, 0, 0)
        user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass


# --------------------------------------------------------------------------- #
#  皮膚：正圓角底板與 Apple 色票
# --------------------------------------------------------------------------- #
# 換的是**控制項與容器**的背景（按鈕、輸入框、核取方塊、進度條、卡片、日誌槽）；
# ⚠️ **視窗外框不碰**（使用者 2026-08-26 拍板）：那不是省事，是量過的——視窗四角
# 的圓角是 Windows 11 的 DWM 畫的，app 改不了形狀。要改只能走 layered window ＋
# 逐像素 alpha，代價是失去原生標題列，最小化、貼齊、工作列預覽全部得自己重寫，
# 而 taskbar_progress 那一套也綁在原生視窗上。
#
# ⚠️ **卡片是 2026-08-26 才加的**（使用者「參考 MP4-2-SRT UI 的圓角、卡片、顏色」）。
# 在那之前這裡寫著「卡片維持實色」，理由是「`ttk.Frame` 只能是實色、沒有透明，
# 坐在上面的每個 `ttk.Label` 都會用自己的底色蓋掉一塊」——那個觀察是對的，但它是
# **做法的限制，不是不能做的理由**：解法就是讓卡片上的每一個控制項都繼承得到
# `Card.*` 那一層的 background（見 apply_ui_style 的那一批 `st.configure`）。
# ⚠️ 真正不能做的仍然是**漸層**：`Muted.TLabel` 那條「對比度 ≥9:1」的硬規則在
# 非平面的底色上會沿著底色滑動（實色底量一次就算數，非實色底得整片量，最淡的
# 一端會掉到 6:1）。三階底色（page → card → field）每一階都是實色，量得準。
#
# **為什麼是圖**：ttk 內建的繪圖能力只有矩形、3D 浮雕邊框、直線——沒有圓角、
# 沒有抗鋸齒、沒有任意路徑。現在這個 Sun Valley 佈景（sv_ttk）自己就是一張
# spritesheet 切成一堆小圖、再用 `ttk::style element create ... image` 掛上去的，
# 我們換掉的正是它的 `Button.button`／`AccentButton.button`／`Entry.field`／
# `Checkbutton.indicator`／進度條那幾個元件，另外三張（卡片、日誌槽、低調按鈕）
# 沒有前身，是自己開一份 layout 掛上去的。
#
# **圖從哪來**：`assets/skin/`（`tools/make_skin.py` 的產物，形狀與內距的唯一真值
# 在那支，顏色則在 `pdf2ppt/palette.py`）。⚠️ **資產不在就當場畫**（使用者 2026-08-26 指示）：那支
# 工具是可以直接 import 的，缺圖時就地畫一份在記憶體裡用，畫不出來（連 Pillow
# 都沒有）才整個放棄。所以三種情況都活得下去——有資產、只有原始碼、兩者皆無。
# ⚠️ **不要用 Pillow 的 ImageTk**：它要再多一個 C 擴充模組才 import 得起來，而
# Tk 8.6 的 `PhotoImage` 本來就吃 base64 的 PNG（含 alpha）。走 base64 也順手
# 避開了「專案放在非 ASCII 路徑時 `-file` 讀不到」的那一類麻煩。

SKIN_DIR = PROJECT_DIR / "assets" / "skin"

# 資產的縮放檔與這台機器的實際縮放要**幾乎相等**才用得上（見 `_from_assets`）。
SKIN_SCALE_TOL = 0.01

# `sprites.json` 的 schema 版本，要與 `tools/make_skin.py` 的 `SCHEMA_VERSION` 同號
# （`tests/test_gui_helpers.py` 兩邊對釘）。⚠️ **不從 make_skin import**：資產這條路
# 的重點就是不必有 Pillow，為了一個整數把相依拉進來等於把這條路廢掉。
SKIN_SCHEMA = 2


def import_make_skin():
    """import `tools/make_skin.py`（產生器與 GUI 不同層，要先把 `tools/` 放進路徑）。

    ⚠️ **只有「當場畫」那條路會用到**：讀資產不需要產生器、也不需要 Pillow。
    ⚠️ `finally` 裡的 `sys.path.pop(0)` 不可省，也不可改成 `remove()`——插在最前面
    就從最前面拿掉，才不會在重複呼叫時愈積愈長、或誤刪別人放的同名路徑。
    ⚠️ 測試也走這一支（`tests/test_gui_helpers.py`），這樣「資產＝產生器」那支
    測試驗到的才是**真正會出貨的**匯入路徑，而不是它自己另一份抄本。
    """
    sys.path.insert(0, str(PROJECT_DIR / "tools"))
    try:
        import make_skin
    finally:
        sys.path.pop(0)
    return make_skin

# 把 sv_ttk layout 裡的背景元件換成我們的。第二欄是**要從哪個樣式抄 layout**
# ——主要動作鈕的兩張皮都是從 `Accent.TButton` 複製出來的（`Run.…` 與 `Stop.…`
# 各要一份自己的 layout 才分得開，字級與內距則靠樣式名的後綴繼承）；兩種低調鈕
# 是從 `TButton` 抄的（同一張底板、兩份 layout，因為它們的內距不同）。
SKIN_SWAPS = (
    ("TButton", None, {"Button.button": "Sq.button"}),
    ("TEntry", None, {"Entry.field": "Sq.field"}),
    ("TCheckbutton", None, {"Checkbutton.indicator": "Sq.check"}),
    ("Horizontal.TProgressbar", None,
     {"Horizontal.Progressbar.trough": "Sq.trough",
      "Horizontal.Progressbar.pbar": "Sq.pbar"}),
    (RUN_STYLE, "Accent.TButton", {"AccentButton.button": "Sq.accent"}),
    (STOP_STYLE, "Accent.TButton", {"AccentButton.button": "Sq.stop"}),
    (CTA_STYLE, "TButton", {"Button.button": "Sq.cta"}),
    (ADV_STYLE, "TButton", {"Button.button": "Sq.subtle"}),
    # ⚠️ **「開啟紀錄」走小一號的低調皮**（`Sq.subtlesm`，2026-08-27 膠囊化時拆
    # 開）：膠囊的半徑恆等於**自己圖高**的一半，而圖高又必須等於元件高度，所以
    # 兩種高度就是兩張圖——收合鈕釘在 `SQ_H_ADV`＝45、這一顆是 `SQ_H_SUB`＝31。
    # ⚠️ 共用一張的話，矮的那顆會被高的圖**裁掉下緣**、高的那顆會把矮的圖**垂直
    # 重複貼**（不是「上下圓角被畫到框外」——那是同日上午還切四邊時的失效模式，
    # 垂直改成不切之後已經不可能發生，見 `tools/make_skin.py` 第 5 點）。
    (SUBTLE_STYLE, "TButton", {"Button.button": "Sq.subtlesm"}),
)

# 自己開 layout 的兩個 Frame（不從別的樣式抄，因為要的就只有一張底板）。
#
# ⚠️ 三欄綁在一起：誰換 layout、換成哪張圖、以及**沒有皮膚時它自己是什麼顏色**。
# 最後一欄只在皮膚裝不起來時用得到（那時退回實色的方角矩形）。
#
# ⚠️ **圓角外側的顏色不在這裡**，它畫進圖片本身了（`make_skin.plate` 的 `on`）。
# 一度想走另一條路：把樣式的 `background` 設成外側色——ttk 先用那個值填滿整塊、
# 再把九宮格圖畫上去，所以透明的圓角外側露出來的正是它。那條路對 Frame 有效，
# 但對有自己 `background` 語意的控制項就會把別的東西一起改掉，於是整批改成
# 不透明底板（理由完整寫在 `make_skin.plate` 的 docstring）。
#
# ⚠️ **抄 `TEntry` 是行不通的**：那會把 `Entry.textarea` 一起帶進 Frame 裡，而那個
# 元件在非輸入框的控制項上沒有定義的行為。
SKIN_FRAMES = (
    # (樣式, 底板元件, 沒有皮膚時它自己的底色)
    ("Card.TFrame", "Sq.card", "card"),
    # 日誌槽：`tk.Text` 是 classic 控制項、**做不到圓角**——所以圓角由外面這層
    # Frame 畫，Text 縮在它裡面（內距 ≥ 圓角半徑，方角才不會伸進弧裡）
    ("Sunken.TFrame", "Sq.sunken", "field"),
)


class SquircleSkin:
    """把 ttk 互動控制項的背景換成 squircle 圖片。

    ⚠️ **只在 sv_ttk 載得起來時才安裝**：這裡是把 sv_ttk 的 layout 複製一份、
    只換掉背景元件的名字，換不到 layout（原生 vista 佈景的結構不一樣）就整個
    放棄，讓畫面留在原本的長相——外觀不值得賠上「開得起來」。
    """

    def __init__(self, root: tk.Misc, scale: float, mode: str) -> None:
        self.root, self.scale, self.mode = root, scale, mode
        self.st = ttk.Style(root)
        self.source = ""           # "assets"／"drawn"：哪一條路成的，驗收時要分得出來
        self._keep: list = []      # ⚠️ Tk 不持有 PhotoImage 的參考，放掉就變空白
        # 收合鈕的三角形。跟底板同一張 sprite sheet，但**不是** ttk 元件——GUI
        # 直接拿去當按鈕的 image（見 App._set_chevron）
        self.chev: dict[str, tk.PhotoImage] = {}

    # ---- 安裝 ----
    def install(self) -> bool:
        spec = self._from_assets() or self._drawn()
        if spec is None:
            return False
        elems, fg = spec
        try:
            for name, e in elems.items():
                states = e["states"]
                args = [str(states[0][1])] + [(s, str(i)) for s, i in states[1:]]
                self.st.element_create(
                    name, "image", *args,
                    border=e["border"], padding=e["padding"],
                    sticky=e["sticky"], width=e["width"], height=e["height"])
            # ⚠️ **先把來源 layout 全部抓下來，再統一寫回去。** 邊抄邊寫的話
            # 後面那幾條會抄到**已經換過**的版本：`Adv.TButton` 從 `TButton` 抄
            # 時，`Button.button` 早就被前一圈改名成 `Sq.button` 了，於是替換表
            # 對不上任何一個元件名——兩顆收合鈕安靜地留在一般按鈕的灰底皮上，
            # 沒有例外、也沒有錯誤訊息（2026-08-26 截圖才看出來）。
            src_layouts = [(style, self.st.layout(src or style), table)
                           for style, src, table in SKIN_SWAPS]
            for style, layout, table in src_layouts:
                self.st.layout(style, self._swap(layout, table))
            # 卡片與日誌槽：自己開一個**只有底板**的 layout。⚠️ 卡片的內距不在
            # 這裡——它是版面的尺規（CARD_PAD，要跟著顯示縮放走），由 Frame 自己
            # 的 padding 給
            for style, elem, _own in SKIN_FRAMES:
                self.st.layout(style, [(elem, {"sticky": "nswe"})])
            self.st.configure("Horizontal.TProgressbar",
                              thickness=elems["Sq.trough"]["height"])
            for style in (RUN_STYLE, STOP_STYLE):
                self.st.map(style, foreground=[("disabled", fg["run_off"]),
                                               ("!disabled", fg["on_accent"])])
        except Exception:
            # 佈景結構跟預期不一樣（換了 sv_ttk 版本、Tcl 版本不合）：畫面留在
            # 原本的長相就好，不要讓外觀把整支程式帶下水
            return False
        return True

    def _swap(self, layout, table: dict):
        """複製一份 layout，把背景元件換成我們的（其餘結構原封不動）。"""
        out = []
        for elem, opts in layout:
            opts = dict(opts)
            if "children" in opts:
                opts["children"] = self._swap(opts["children"], table)
            out.append((table.get(elem, elem), opts))
        return out

    def _photo(self, **kw) -> tk.PhotoImage:
        ph = tk.PhotoImage(master=self.root, **kw)
        self._keep.append(ph)
        return ph

    # ---- 來源一：打包好的資產 ----
    def _from_assets(self):
        """讀 `assets/skin/`。⚠️ 任何一步不對就回 None 交給當場畫，不要丟例外。"""
        try:
            meta = json.loads((SKIN_DIR / "sprites.json").read_text("utf-8"))
            # ⚠️ **schema 對不上就當作沒有資產**：舊 `sprites.json` 的每個 key 都還
            # 在，不擋的話會**成功**載入、`source` 還報 `assets`，把不相容的元件定義
            # 裝上去（膠囊化把 `border` 從 int 改成四元組就是這種變更）。使用者換電腦
            # 是複製專案資料夾，只覆蓋 `.py` 而留著舊資產完全做得到。
            if meta.get("version") != SKIN_SCHEMA:
                return None
            # 資產是固定像素、顯示縮放不是，挑最接近的那一檔。
            # ⚠️ **只有「幾乎精確」才收**（2026-08-27 晚補）：膠囊化之後底板的高度就是
            # 元件的高度，而樣式內距與點數字型走的是**真實 DPI**——貼齊到隔壁那一檔
            # 等於讓元件比底板高，下半個圓被裁掉。實測 250% 貼 2.0x 檔時 Run 83 對
            # 底板 80、Adv 94 對 90、輸入框 65 對 60，300% 更差到 +18。Windows 在高
            # DPI 面板上本來就給 225／250／300%，自訂縮放更是任意值。
            # ⚠️ 對不上就回 None 交給 `_drawn()`——**那條路用的是實際縮放倍率**，
            # 任何 DPI 都畫得對（見它的 docstring）。改版前四邊九宮格有 1px 中段可以
            # 重複貼，縮放對不上完全無害，所以這個把關是膠囊化才需要的。
            best = min(meta["scales"], key=lambda s: abs(s - self.scale))
            if abs(best - self.scale) > SKIN_SCALE_TOL:
                return None
            var = meta["variants"][f"{self.mode}@{best:g}"]
            # ⚠️ **整張 sheet 刻意不走 `_photo()`、不進 `_keep`**：切完之後就沒有
            # 人用它了，留著等於讓解碼後的整張點陣常駐一輩子（@2x 那張 282×2416，
            # 解碼後 2.73MB；十組裡只會載一組，但那一份是白留的）。個別 sprite 是
            # `copy` 出來的**獨立** PhotoImage、不參照它，所以 sheet 只是個普通區域
            # 變數，函式結束就回收——**不必寫 `del`**（那會讀起來像洩漏防護，害下一個
            # 在中間插 `return` 的人以為自己在處理一個 2.73MB 的不變量）。
            sheet = tk.PhotoImage(
                master=self.root,
                data=base64.b64encode((SKIN_DIR / var["file"]).read_bytes()))
            # ⚠️ **同一塊 rect 只裁一次**：`pack()` 去重之後每個 variant 有三個
            # key 指到同一塊區域（`accent-dis`／`stop-dis`、兩張低調皮的 `rest`／
            # `dis`），逐 key 裁等於多做三次 blit，又把三張一模一樣的 PhotoImage
            # 永久留在 `_keep` 裡（@2x 約 252KB）。對 `elems`／`chev` 完全透明——
            # 那兩邊都只是查 `cut`。
            cut: dict[str, tk.PhotoImage] = {}
            same: dict[tuple, tk.PhotoImage] = {}
            for key, (x, y, w, h) in var["sprites"].items():
                if (x, y, w, h) in same:
                    cut[key] = same[(x, y, w, h)]
                    continue
                sub = self._photo(width=w, height=h)
                # ⚠️ `-compositingrule set` 不可省：預設是 overlay，會把來源
                # **疊**上去而不是覆蓋，半透明的角落會被疊成不透明
                self.root.tk.call(sub, "copy", sheet, "-from", x, y,
                                  x + w, y + h, "-compositingrule", "set")
                cut[key] = same[(x, y, w, h)] = sub
            elems = {name: dict(e, states=[(s, cut[k]) for s, k in e["states"]])
                     for name, e in var["elements"].items()}
            self.chev = {"right": cut["chev-right"], "down": cut["chev-down"]}
        except Exception:
            return None
        self.source = "assets"
        return elems, var["fg"]

    # ---- 來源二：當場畫 ----
    def _drawn(self):
        """資產不在（或壞了）就 import 產生器現畫一份。

        ⚠️ 這裡用的是**實際的**縮放倍率，不必貼齊資產那五檔——當場畫本來就沒有
        「只有幾種尺寸」的限制。
        """
        try:
            make_skin = import_make_skin()
            imgs, elems = make_skin.build_variant(self.mode, self.scale)
            cut = {}
            for key, im in imgs.items():
                buf = io.BytesIO()
                im.save(buf, "PNG")
                cut[key] = self._photo(data=base64.b64encode(buf.getvalue()))
            elems = {name: dict(e, states=[(s, cut[k]) for s, k in e["states"]])
                     for name, e in elems.items()}
            fg = {"on_accent": make_skin.SKINS[self.mode]["on_accent"],
                  "run_off": make_skin.SKINS[self.mode]["run_off_fg"]}
            self.chev = {"right": cut["chev-right"], "down": cut["chev-down"]}
        except Exception:
            return None
        self.source = "drawn"
        return elems, fg


# ⚠️ **膠囊那幾顆的內距只有這一份。** 左右一律照這裡；上下分兩欄——`pin` 是膠囊
# 底板裝得起來時用的（高度由底板釘死，內距只要讓內容矮於圖高就好），`plain` 是膠囊化
# 之前的值，皮膚裝不起來時要還原回去（見 `_set_pill_padding`）。
#
# ⚠️ **為什麼是一張表兩欄、不是兩張表**：兩張表等於把六個**水平**值抄第二遍，而
# 水平值與膠囊無關（`CTA_STYLE` 的 `px(8)` 修的是 sv_ttk 寫死像素、不跟 DPI 走的老
# 問題），改一邊漏一邊完全不會被抓到——皮膚裝不起來那條路 `_measure_pills` 直接
# skip，沒有任何測試看得到。2026-08-27 晚一度真的抄成兩份，這張表就是收掉它。
#
# ⚠️ 每一格的理由寫在 `apply_ui_style` 裡對應的那段註解，不要只看數字。
PILL_PADDING = (
    # (樣式, 左右, 上下[有底板], 上下[沒底板])
    (RUN_STYLE, 20, 4, 7),
    (ADV_STYLE, SP_SM, 7, SP_MD - 2),
    ("Small.TButton", 10, 1, 3),
    (SUBTLE_STYLE, 10, 1, 3),
    # 這兩個膠囊化之前都沒明寫內距、吃 sv_ttk 的 `8 2 8 3`
    (CTA_STYLE, 8, 1, 3),
    ("TButton", 8, 1, 3),
)


def _set_pill_padding(st: ttk.Style, px, *, pinned: bool) -> None:
    """套用 `PILL_PADDING`。`pinned` ＝ 膠囊底板裝得起來嗎。

    ⚠️ **垂直內距是底板的配套，不是獨立的設計選擇。** 砍到 4／7／1 的前提是
    「按鈕沒有因此變矮，高度改由底板釘死」——而底板只有 `SquircleSkin.install()`
    成功時才存在。sv_ttk 載不起來會在更前面就 return（那條路沒動過內距，安全），但
    **sv_ttk 載得起來、皮膚卻裝不起來**是另一條：資產與 Pillow 都沒有、`sprites.json`
    壞掉、換了 ttk 版本讓 `element_create`／`layout` 丟例外。`SquircleSkin` 的
    docstring 把「只有原始碼」與「兩者皆無」列為支援狀態，所以這是會出貨的路。

    ⚠️ 不還原的話，內距是砍過的、卻沒有底板補回高度：實測 100% 下五個樣式全部
    塌成 27px（改版前是 39／45／31／30／31），150% 下收合鈕少 28px，而且主要動作鈕、
    區段標題鈕、次要小鈕的高度階層被抹平成同一個數。那違反 `apply_ui_style` 自己的
    承諾——「裝不起來就回 None，畫面留在原本的長相」。
    """
    for style, h, v_pin, v_plain in PILL_PADDING:
        st.configure(style, padding=(px(h), px(v_pin if pinned else v_plain)))


def apply_ui_style(root: tk.Misc,
                   scale: float) -> tuple[str, dict, SquircleSkin | None]:
    """設定字型與佈景，回傳 (字型家族名, 調色盤, squircle 皮膚)。

    字型走 **Tk 的具名字型**（TkDefaultFont…）：所有 ttk 控制項預設就吃這幾個，
    改一次全部跟著換，不必逐個 widget 設 font。⚠️ 連 TkFixedFont 也換掉 ——
    日誌區原本是 Consolas（等寬），使用者 2026-08-25 要求「全部的字體」都用
    Microsoft JhengHei UI。

    ⚠️ **沒有 sv_ttk 也必須開得起來**：這支是使用者的主要入口，為了外觀讓它
    開不了完全不划算。缺套件就留在系統原生佈景（vista），只換字型。
    squircle 皮膚同一條原則——裝不起來就回 None，畫面留在原本的長相。
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
        return fam, pal, None

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
    # ⚠️ 樣式名要以 .Accent.TButton 結尾才繼承得到那組圖片元件。
    # ⚠️ 字級與內距對齊姊妹專案 MP4-2-SRT（使用者 2026-08-26「按鈕都請依照
    # MP4-2-SRT 樣式」）：11pt／(20,7)，比舊值 12pt／(22,9) 收斂一點。⚠️ 垂直那個
    # 2026-08-27 從 7 降到 4，**按鈕沒有因此變矮**——高度改由底板釘死（見下）。
    # ⚠️ **垂直內距是膠囊底板的配套，不是自由參數**（2026-08-27）：底板高度由
    # `tools/make_skin.py` 的 `SQ_H_*` 釘死，而元件高度取「內容需求」與底板高度的
    # 較大者——垂直內距一旦讓內容撐過底板高度，Tk 就改成**裁掉底板下緣**，膠囊的
    # 下半個圓當場被削平（不報錯，只有截圖看得出來）。動這幾個數字或字級之前，先讀
    # `docs/dev/windows-環境與入口.md` §5.11 並重跑那裡的驗算。
    # ⚠️ 內距的數字在 `PILL_PADDING`（上下兩欄，見那裡）。
    st.configure(RUN_STYLE, font=(fam, 11, "bold"))
    # 轉檔選項／詳細訊息的收合鈕：整條寬 + anchor="w"，讀起來像區段標題而不是
    # 一顆浮在半空中的按鈕。⚠️ 它是**卡片自己的標題列**，走低調皮（見 ADV_STYLE）。
    # ⚠️ 內距要撐得起「這是一條區段標題」：(10,6) 時它比上下的卡片都薄，看起來
    # 像夾在兩塊板子中間的縫，而不是可以按的東西
    # ⚠️ 左右內距 `SP_SM`、上下 `px(7)`（膠囊化時從 `SP_MD-2`＝10 降下來，見下）。左右這個值是 2026-08-27 加回來的
    # （使用者：「三角形太靠近邊界，要多留一點空白」）：先前為了讓**底板左緣**
    # 落在卡片內距上而給了 0，底板確實對齊了，但底板靜止時是看不見的（低調皮
    # ＝卡片色），畫面上真正讀得到的是三角形，而它離卡片邊只剩底板自帶的 4px。
    # ⚠️ 內距不會動到底板的位置，所以那條「六個直接子元件左緣都是 24」仍然成立
    # ——量的是元件邊緣，這裡加的是元件**裡面**的留白。
    # ⚠️ 垂直從 SP_MD-2（10）降到 7 是膠囊底板的配套（見上），高度仍由底板釘死。
    st.configure(ADV_STYLE, anchor="w")
    # 「開啟紀錄」：與收合鈕同一列、同樣坐在卡片上，所以走同一張低調皮，
    # 只是內距比照 Small
    # 「瀏覽…／變更…」：靜止是白底藍框，所以字也要是藍的；滑過去整顆翻藍，
    # **文字要在同一刻翻白**（見 CTA_STYLE）。
    # ⚠️ 內距 2026-08-27 起**明寫**：不寫就是吃 sv_ttk 的 `8 2 8 3`，而那個垂直值
    # 會把內容撐到只剩 0 實體像素的餘裕（@100%），下一版佈景或換台機器就把膠囊底板
    # 的下緣裁掉（見上）。⚠️ 水平取 `px(8)` ＝ **sv_ttk 那個 8，但跟著 DPI 走**
    # ——照抄成固定 8 的話 200% 下只有一半該有的寬度（那是 sv_ttk 自己的漏，它整組
    # padding 都是寫死像素）。寫成 `px(10)` 試過，這顆會寬 14px，沒有理由動它。
    st.configure(CTA_STYLE, foreground=pal["cta_fg"])
    # ⚠️ **基底 `TButton` 也要明寫**（2026-08-27 晚，被新測試抓出來的）：`Sq.button`
    # 這張膠囊底板是掛在 `TButton` 的 layout 上，而基底自己吃的是 sv_ttk 的
    # `8 2 8 3`——垂直 2+3 讓內容剛好等於底板高度，**餘裕 0**。現在畫面上每顆鈕都
    # 指定了樣式（`Small.`／`Cta.`／`Adv.`／`Subtle.`／`Run.`），所以還沒踩到；但
    # 只要有人加一顆不帶 `style=` 的 `ttk.Button`，或加一個沒覆寫內距的新樣式，
    # 那顆鈕的下半個圓就會被裁掉。把基底補齊，這一類就不可能再發生。
    # ⚠️ `map` 不會與 `TButton` 的合併、是整個取代，所以 `disabled` 也要自己列
    # ——漏掉的話轉檔中被鎖起來的那兩顆會是一般的黑字，看起來還能按。
    # ⚠️ `pressed` 要排在 `active` 前面：按住不放時兩個狀態同時成立，而 ttk 取的
    # 是第一個對上的。
    st.map(CTA_STYLE,
           foreground=[("disabled", pal["run_off_fg"]),
                       ("pressed", pal["on_accent"]),
                       ("active", pal["on_accent"])])
    st.configure("Muted.TLabel", foreground=pal["muted"])
    # 視窗第一句說明（副標）：粗體（使用者 2026-08-25 晚指示）。
    # ⚠️ 樣式名**必須以 `.Muted.TLabel` 結尾**才繼承得到說明文字的前景色——ttk
    # 是照後綴一層層往上找的（`Sub.Muted.TLabel` → `Muted.TLabel` → `TLabel`）。
    # 取名成 `Subtitle.TLabel` 就只會繼承到 `TLabel`，顏色會掉回預設的黑。
    # ⚠️ 副標坐在**視窗底**上（卡片之外），所以底色要跟著 page；`ttk.Label` 是
    # 實色底、不是透明的，不指定就吃佈景的 #fafafa，副標那一行會是一塊淺色矩形
    st.configure("Sub.Muted.TLabel", font=(fam, 10, "bold"),
                 background=pal["page"])
    # 卡片之間露出來的視窗底。⚠️ 不設就是 sv_ttk 的 #fafafa，而卡片是純白——
    # 兩者只差 5 階，卡片整個融進背景，三階層次的最上面那一階等於沒有
    st.configure("Page.TFrame", background=pal["page"])
    # ⚠️ **這是沒有皮膚時的後備**（皮膚裝不起來就退回實色的方角矩形）。有皮膚時
    # 這個值看不到——底板是不透明的，圓角外側已經畫進圖裡了（見 SKIN_FRAMES）。
    for style, _elem, own in SKIN_FRAMES:
        st.configure(style, background=pal[own])
    # 卡片**裡面**的文字。⚠️ 同上：`ttk.Label` 是實色底的，坐在白卡上不指定底色
    # 就是一塊塊淺灰矩形浮在白色裡。所以卡片上的每一種文字都要繼承得到
    # `Card.TLabel` 這一層的 background——樣式名的後綴一定要留 `.Card.TLabel`。
    st.configure("Card.TLabel", background=pal["card"])
    # 卡片裡的小標（「輸入 PDF」）：Fluent 的 BodyStrong，不是另一級字級
    st.configure("CardTitle.Card.TLabel", font=(fam, 10, "bold"))
    st.configure("CardHint.Card.TLabel", foreground=pal["muted"])
    st.configure("CardStatus.Card.TLabel", font=(fam, 10, "bold"))
    # 核取方塊跟 Label 一樣是實色底的（那個「底」是文字那半邊，方塊本身是圖片），
    # 坐在白卡上不指定就是四塊淺灰矩形。⚠️ layout 照後綴繼承，所以這一支照樣
    # 拿得到換過皮的 `Sq.check`
    st.configure("Card.TCheckbutton", background=pal["card"])
    # ⚠️ 卡片**裡面**的 Frame 要用這一支，不是 `Card.TFrame`：那一支的 layout 被
    # 換成了一張底板圖（`Sq.card`），每用一次就多畫一張帶邊框的小卡片。這一支
    # 只換背景色、layout 照 ttk 原本的
    st.configure("CardBody.TFrame", background=pal["card"])
    if mode == "dark":
        use_dark_titlebar(root)
    # ⚠️ 一定要在 sv_ttk 切完佈景**之後**：image element 是建在「當下這個
    # 佈景」裡的，`ttk::style theme use` 一換就整批不見了。
    _set_pill_padding(st, px, pinned=True)
    skin = SquircleSkin(root, scale, mode)
    if skin.install():
        return fam, pal, skin
    # ⚠️ **沒有底板就沒有東西釘住高度，垂直內距要還原**（見 `_set_pill_padding`）。
    _set_pill_padding(st, px, pinned=False)
    return fam, pal, None


# 轉檔結束代碼裡的這一個代表「檔案有了，但至少一頁降級」（cli.py 的
# PARTIAL_RC）。⚠️ 手抄過來的常數，tests/test_docs.py 釘著兩邊一致 ——
# 不 import 是因為 cli.py 會把整組相依（numpy／pymupdf／python-pptx…）拉進來，
# 而那些只有按下轉檔的那一刻才需要——啟動路徑不該為一個整數付那個代價。
PARTIAL_RC = 3

# 「使用者按了停止」。同樣是手抄 cli.py 的（`CANCELLED_RC`，測試釘著兩邊一致）。
# ⚠️ 不可以跟 0／1 共用：0 會讓結果列報成「完成」而磁碟上根本沒有檔案，1 會把
# 使用者自己的決定報成失敗、還附一個沒有意義的代碼。
CANCELLED_RC = 4

# 本行程的結束碼，意思是「失敗**已經自己跳過訊息框了**，啟動端不必再跳一次」。
# 「啟動.vbs」讀同一個數字（它的 `RC_SELF_REPORTED`），tests/test_docs.py 釘著
# 兩邊一致。⚠️ **不可改成 1 或 2**：那兩個是直譯器自己會回的（1＝未攔到的例外、
# **2＝連 .py 都打不開**——只複製了 .vbs 而 pdf2ppt_gui_2.py 不在時就是 2），
# 撞上去等於讓那些真正需要顯示的失敗被靜靜吞掉。78 是 sysexits 的 EX_CONFIG
# （「安裝／設定不對」），uv 與 Python 都不會回這個值。
SELF_REPORTED_RC = 78

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


# cli.py 每處理完一頁就印一行 `page 7 (3/15): 24 lines, …`。⚠️ 這是**手抄的輸出
# 格式**，不是 API：cli.py 改掉 head 的長相，這裡只會靜靜地退回不定長度進度條
# （不會報錯，也不會少東西——那一行照樣進日誌區），所以格式對不上時的症狀是
# 「進度條不動」而不是「壞掉」。同一趟輸出裡另外兩行也認得：
#   `WARNING: page 3 dropped, …`  → 降級的頁碼，要寫在結果列上（見 _show_result）
#   `Loading OCR engine...`       → 首次執行會卡在這裡好幾分鐘下載模型
_PAGE_RE = re.compile(r"^page \d+ \((\d+)/(\d+)\)")
# 降級的三種下場，同樣是手抄 cli.py 的（`_fallback_slide` 的三個回傳值 +
# render 失敗那條的 "dropped"）。⚠️ 認不得就把原句照登，不要把訊息吃掉——
# 使用者看得懂英文總比看到一句「有頁面降級」卻不知道是哪幾頁好。
_DEGRADE_RE = re.compile(r"page (\d+) (dropped|image only|partial slide)")
_DEGRADE_ZH = {"dropped": "整頁沒能產生",
               "image only": "只保留原圖、沒有可編輯文字",
               "partial slide": "只轉出了一部分"}
_WARN_PREFIX = "WARNING: "
_LOADING_PREFIX = "Loading OCR engine"


def log_dir() -> Path:
    """執行紀錄要落在哪個資料夾。

    釘在**本檔所在的資料夾**（PROJECT_DIR）、不是 cwd：「啟動.vbs」就在旁邊，
    出事時要找的人是雙擊它的那一個，而 cwd 從捷徑進來時不保證是這裡。"""
    override = os.environ.get(LOG_DIR_ENV)
    if override:
        return Path(override)
    return PROJECT_DIR / LOG_DIR_NAME


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
    git = PROJECT_DIR / ".git"
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
        text = (PROJECT_DIR / "pyproject.toml").read_text(
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
    工具鎖住都會走到這裡，而「留不了底」絕不能升級成「打不開程式」。留不了底時
    唯一的落點是 _boot_stderr（從終端機跑就看得到），所以它更不能擋住啟動。"""
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


def _fmt_degraded(warning: str) -> str:
    """把 cli 的 `page 3 dropped, page 7 image only` 講成人話。

    同一種下場的頁碼併在一起講：一份 30 頁的簡報降級 12 頁時，逐頁列出來會長
    到結果列放不下，而使用者要判斷的是「哪幾頁要自己補」。"""
    hits = _DEGRADE_RE.findall(warning)
    if not hits:
        return warning
    groups: dict[str, list[str]] = {}
    for page, how in hits:
        groups.setdefault(how, []).append(page)
    return "；".join(f"第 {'、'.join(pages)} 頁{_DEGRADE_ZH[how]}"
                     for how, pages in groups.items())


def _shorten_path(path: Path, budget: int = 52) -> str:
    """長路徑縮成一行放得下的樣子，中間省略。

    ⚠️ **檔名不可以被省略掉**：使用者要在這一行確認的就是「會存成哪個檔」，
    砍尾巴等於把唯一有用的部分砍掉。所以是從中間挖，前面留碟符、後面整段留。"""
    text = str(path)
    if len(text) <= budget:
        return text
    name = path.name
    head = max(0, budget - len(name) - 4)
    return f"{text[:head]}…\\{name}" if head else f"…\\{name}"


def enable_file_drop(widgets, on_paths) -> bool:
    """讓這些控制項接得住從檔案總管拖進來的檔案，回傳有沒有接上。

    ⚠️ **接不上也必須照常開得起來**（和 sv_ttk 同一條原則）：`tkinterdnd2` 沒裝、
    它附的 tkdnd 二進位檔在這台機器上載不起來（架構不合、資安軟體擋 .dll）都會
    走到 except，介面只是回到「只能按瀏覽…」而已。

    ⚠️ **不要為了拖放把基底類別換成 `TkinterDnD.Tk`**：它的 `__init__` 在載不到
    tkdnd 時直接 raise，那等於用一個純加分的功能換掉整支程式開得起來的保證。
    改成自己呼叫 `_require()`（同一支函式，它就是 `TkinterDnD.Tk` 內部用的那個）
    再註冊**子控制項** —— ⚠️ `tkinter.Tk` 不是 `BaseWidget` 的子類，而
    tkinterdnd2 是把方法掛在 `BaseWidget` 上的，所以根視窗本身沒有
    `drop_target_register`，要拿它底下的 Frame 來註冊。

    ⚠️ 多註冊幾個控制項：tkdnd 是找游標底下那個視窗、再往上找有註冊的祖先，
    最外層的 Frame 理論上罩得住全部，但輸入欄與檔案框是使用者真正會瞄準的地方，
    多註冊一次的成本是零。"""
    try:
        from tkinterdnd2 import TkinterDnD, DND_FILES
    except Exception:
        return False
    ok = False
    for i, w in enumerate(widgets):
        try:
            if i == 0:
                TkinterDnD._require(w)     # 一個直譯器只需要載一次
            w.drop_target_register(DND_FILES)
            w.dnd_bind("<<Drop>>", on_paths)
            ok = True
        except Exception:
            continue
    return ok


def is_project_dir(path: Path) -> bool:
    """一個合格的專案根目錄：底下有 pdf2ppt 套件（pdf2ppt/cli.py）。"""
    try:
        return (path / "pdf2ppt" / "cli.py").is_file()
    except Exception:
        return False


def fail_no_project() -> bool:
    """PROJECT_DIR 裡沒有 pdf2ppt 套件：講清楚，然後讓行程收掉。

    回傳**訊息框有沒有真的跳出來** —— 呼叫端據此決定結束碼：跳出來了就回
    `SELF_REPORTED_RC`（「啟動.vbs」看到這個值會安靜地把行程收掉，使用者只看到
    我們這一個框）；沒跳成功就回一般的失敗碼，讓啟動端把 stderr 那一份跳出來。
    ⚠️ **不可以無條件回報「已說明過」**：Tk 起不來的機器上那等於什麼都沒說。

    ⚠️ **不要退而求其次開一個「殘廢的視窗」**（2026-08-25 使用者指示拿掉位置
    選擇時一併定的）：以前找不到套件會照常開窗、把紅字寫在專案位置那一格，等
    使用者按下轉檔才擋下來；沒有挑選器之後那條路已經無解，開窗只是把「這份
    複製品缺東西」延後到最不好懂的時機才講。

    訊息仍然寫一份到 **stderr**：那是訊息框跳不出來時唯一的落點，「啟動（顯示
    訊息）.bat」與直接下指令的人本來也是看那裡。"""
    msg = (f"這個資料夾裡找不到 pdf2ppt\\cli.py：\n{PROJECT_DIR}\n\n"
           "pdf2ppt_gui_2.py 必須跟 pdf2ppt 資料夾放在一起（也就是專案根目錄）。\n"
           "請把整個專案資料夾完整複製過來，再執行一次「安裝.bat」。")
    try:
        sys.stderr.write("[啟動失敗] " + msg.replace("\n\n", "\n") + "\n")
        sys.stderr.flush()
    except Exception:
        pass
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            if APP_ICON.is_file():
                root.iconbitmap(default=str(APP_ICON))
        except Exception:
            pass
        messagebox.showerror("找不到 pdf2ppt 套件", msg)
        root.destroy()
        return True
    except Exception:
        # 連 Tk 都起不來（沒有桌面工作階段之類）；stderr 那一份已經寫出去了，
        # 回 False 讓啟動端接手顯示
        return False



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
        self.ui_font, self.pal, self.skin = apply_ui_style(self, self.ui_scale)
        # 尺寸與那三個常數的理由都在模組頂端（WIN_W／WIN_H0／WIN_MIN_H）。
        # ⚠️ 寬度與 minsize 同值＝「開起來就是最小寬度」，兩邊要一起看。
        self.geometry(f"{self.px(WIN_W)}x{self.px(WIN_H0)}")
        self.minsize(self.px(WIN_W), self.px(WIN_MIN_H))
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
        # 的內容），從終端機跑（uv run python pdf2ppt_gui_2.py）時它就是主控台。
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
        # 「使用者按了停止」。⚠️ 是 Event 不是 bool：設旗標的是主執行緒、讀的是
        # 背景執行緒裡的 cli.main()，而 Event 是這件事唯一不必自己想記憶體可見性
        # 的作法。每趟開始前 clear()，不要每趟新建一個——新建的那個 cli 拿不到。
        self._cancel = threading.Event()
        # 我們上次自動帶出來的輸出路徑；使用者改過就不再自動跟著換
        self._auto_out = ""
        # _fit_window() 上次自己設定的高度。用來分辨「這個高度是我設的」與
        # 「使用者自己拉的」——後者只長不縮（見 _fit_window）
        self._auto_h: int | None = None
        # 進度追蹤（由 _scan_line 從 cli 的輸出解析出來）
        self._scan_buf = ""
        self._pages_done = 0
        self._pages_total = 0
        self._determinate = False
        # 這一趟的降級頁碼（cli 最後一行的 WARNING）。⚠️ 要留到結果列上：舊版
        # 靠使用者自己去看日誌最後一行，而完成對話框正好蓋在那一行上面
        self._last_warning = ""
        # 結果列上那兩顆鈕要開的檔（沒有產出時是 None，兩顆鈕會收起來）
        self._result_path: Path | None = None

        self._build_vars()
        self._build_ui()
        # 位置要講出來：出事時使用者才知道要附哪一個檔，而不是被問「log 在哪」。
        # ⚠️ 只印檔名：完整路徑在這個寬度下會折成兩行，而且旁邊就有「開啟紀錄」
        # 那顆鈕。完整路徑寫進紀錄檔自己的檔頭（log_header），那份才是要附出去的
        self._append(f"執行紀錄：{self._log_path.name}\n" if self._log_path
                     else "（無法建立執行紀錄檔；錯誤訊息只會留在這個日誌區，"
                          "關掉視窗就沒了。要留底請從終端機執行 uv run python pdf2ppt_gui_2.py。）\n")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(80, self._drain_log)
        self._refresh_input_state()
        self._fit_window()

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
    def _status_width(self) -> int:
        """狀態字那一格要保留多少像素：拿 `STATUS_SAMPLES` 實際去量。

        ⚠️ **要用量的**。以字元數寫死（`width=20`）在中英混排的狀態字上一定不
        準——Tk 的 `width` 單位是該字型 `0` 的寬度，而「載入 OCR 引擎…」裡的
        表意字約兩倍寬、`…` 又不到一倍，於是只能往寬的猜；猜出來的餘裕就是進度
        條右邊那塊永遠用不到的空白。

        字型從樣式查（`CardStatus.Card.TLabel` 的 `font`），⚠️ 不要在這裡重寫一次
        `(family, 10, "bold")`——那份定義在 `apply_ui_style`，抄過來就會漂。
        查不到就退回 `TkDefaultFont`：量得不準頂多是餘裕不理想，不該讓介面開不
        起來。"""
        try:
            spec = ttk.Style(self).lookup("CardStatus.Card.TLabel", "font")
            fnt = tkfont.Font(self, font=spec or "TkDefaultFont")
            return max(fnt.measure(t) for t in STATUS_SAMPLES)
        except tk.TclError:
            return self.px(150)

    def px(self, n: float) -> int:
        """把「以 96dpi 為單位寫的像素」換成這台機器上的實體像素。

        ⚠️ 介面裡每一個寫死的像素數字都要走這裡（padding、wraplength、視窗
        大小…）。點數指定的字型不必——Tk 在 DPI-aware 之下會自己換算。"""
        return max(1, int(round(n * self.ui_scale)))

    # ---- 變數 ----
    # ⚠️ 這裡**只有介面上真的露得出來的那五個**（使用者 2026-08-25 指示）。
    # 其餘旗標（--dpi／--font／--min-score／--device／--lang／--fast／
    # --no-bold／--force-bold／--merge-lines／--debug）不再由 GUI 傳，直接吃
    # cli.py 的 argparse 預設值——舊版是在這裡手抄一份預設值再原封不動傳回去，
    # 那份抄本除了會漂移之外沒有任何作用。
    def _build_vars(self) -> None:
        self.in_path = tk.StringVar()
        self.out_path = tk.StringVar()
        self.pages = tk.StringVar()

        self.no_s2t = tk.BooleanVar(value=False)
        # 這一個存的是**反向**旗標：cli.py 的預設是 --no-cover，所以 GUI 拿
        # 「要不要輸出獨立色塊」當開關（不勾 = 走預設）。2026-08-23 到
        # 08-24 之間它曾經是主畫面上唯一的核取方塊、且預設與 cli.py 相反，
        # 量完 A/B 後兩邊的預設對齊了。其餘布林選項與 argparse 一致。
        self.cover = tk.BooleanVar(value=False)
        self.keep_watermark = tk.BooleanVar(value=False)
        self.keep_tiny_text = tk.BooleanVar(value=False)

        # 選項區／日誌區是否展開（不寫進設定檔：每次開起來都回到最單純的畫面）
        self.show_advanced = tk.BooleanVar(value=False)
        self.show_log = tk.BooleanVar(value=False)
        # 畫面上顯示的輸出路徑（縮短過的）。輸出欄本身已經不是輸入框了，
        # 真值仍然是 out_path，這一個只負責好看
        self.out_show = tk.StringVar()

    # ---- 介面 ----
    def _build_ui(self) -> None:
        p = self.px                       # 寫死的像素一律過這裡（見 px()）
        # ⚠️ **沒有容器邊界時，區塊之間的縫要比區塊裡面的大**，否則眼睛分不出
        # 群。2026-08-25 晚上使用者說「還是有點擠」，量出來的成因就是這條被違反
        # 了：所有區塊都用同一個 `pady=5`（實際間距 10px）pack 出去，而卡片自己
        # 的 padding 是 12px——外面的縫比裡面的窄，五個區塊糊成一片。
        # ⚠️ 卡片化之後**分群改由卡片自己的底色與邊框負責**，所以 CARD_GAP(20)
        # 小於 CARD_PAD(24) 不會重演那次災情（MP4-2-SRT 用同一組數字）；但這只
        # 赦免有容器邊界的那幾道縫，卡片**裡面**照舊走 SP_*（欄距 SP_MD、同一群
        # 裡的行距 SP_SM、卡片內要分成兩件事時那一道縫 SP_XL）。
        pad = self._pad = {"padx": 0, "pady": (0, p(CARD_GAP))}
        # ⚠️ 視窗底要自己指定（`Page.TFrame`）：不指定的話 ttk.Frame 吃的是
        # sv_ttk 的 TFrame 底色（實測 #fafafa），而卡片是純白——兩者只差 5 階，
        # 卡片整個融進背景，三階層次的最上面那一階等於沒有
        root = self.root_frame = ttk.Frame(self, padding=p(PAGE_PAD),
                                           style="Page.TFrame")
        root.pack(fill="both", expand=True)

        # 舊版這裡還有一行 15pt 粗體大標題，寫的是與**標題列一字不差**的同一句
        # 話（連同副標吃掉 60 邏輯 px）。拿掉之後省下來的高度正好是進階區展開時
        # 超出螢幕的那個量級（2026-08-25 量到超出 41px）。
        # ⚠️ 要給 wraplength：不給的話這一整句會從左邊界一路頂到右邊界，最小寬度
        # 下更會把視窗撐開——一行字左右都貼邊，本身就是「擠」的來源之一。
        sub = ttk.Label(
            root,
            text="把 NotebookLM 產出繁中 PDF 簡報，本機轉換成可編輯的 PowerPoint。",
            style="Sub.Muted.TLabel", wraplength=p(780), justify="left",
        )
        sub.pack(anchor="w", pady=(0, p(CARD_GAP)))

        # ---- 卡片一：檔案 ----
        # ⚠️ 三種容器樣式**不要同時出現**：這裡本來是 `LabelFrame`（蝕刻邊框＋
        # 「檔案」標題）、選項區是卡片、收合鈕是扁平長條，同一畫面上三種視覺重量
        # 輪流出現。統一成卡片之後標題也不必了——卡片裡第一行就寫著「輸入 PDF」，
        # 再掛一個「檔案」只是多一行字。
        files = self.files_frame = ttk.Frame(root, style="Card.TFrame",
                                             padding=p(CARD_PAD))
        files.pack(fill="x", **pad)

        # ⚠️ 標籤在**上**、輸入框整條寬。舊版是「輸入 PDF：」與輸入框左右對擠在
        # 同一列，於是第 0 欄的寬度由那五個字決定、輸入框被推掉一截，而它正是這
        # 個畫面上唯一必填的東西。
        ttk.Label(files, text="輸入 PDF", style="CardTitle.Card.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        # 轉檔中要鎖起來的控制項都收進這一份清單（見 _set_inputs_enabled）。
        # ⚠️ 用**明列**、不要走訪 children：那樣會連「輸入 PDF」小標與提示文字
        # 一起變灰，而那兩行正是轉檔中最該讀得清楚的東西
        self._inputs: list[ttk.Widget] = []
        self.in_entry = ttk.Entry(files, textvariable=self.in_path)
        self.in_entry.grid(row=1, column=0, sticky="ew", pady=(p(SP_MD), 0))
        # ⚠️ 這一欄的兩顆鈕（瀏覽…／變更…）都要 `sticky="ew"`：同一欄裡一顆
        # `w`、一顆 `w` 時欄寬由較寬的決定，另一顆的右緣就會短一截、看起來沒對齊
        browse = ttk.Button(files, text="瀏覽…", style=CTA_STYLE,
                            command=self._pick_input)
        browse.grid(row=1, column=1, sticky="ew", padx=(p(SP_SM), 0),
                    pady=(p(SP_MD), 0))
        self._inputs += [self.in_entry, browse]

        # 提示與錯誤共用這一行，而且**一直都在**（只換文字不換有無），填錯路徑
        # 時版面才不會上下跳。⚠️ 路徑不對要在這裡當場說：舊版是照樣讓人按下
        # 「開始轉檔」，按了才跳一個對話框——用擋的比用告知的好
        self.hint = ttk.Label(files, style="CardHint.Card.TLabel", anchor="w",
                              wraplength=p(700), justify="left")
        self.hint.grid(row=2, column=0, columnspan=2, sticky="w",
                       pady=(p(SP_SM), 0))

        # 輸出：99% 的情況就是輸入檔同名的 .pptx，程式自己帶得出來。做成第二個
        # 一模一樣的空輸入欄，只會讓第一眼變成「兩個空格子，我該填哪個」——
        # 降成一行說明加一顆小鈕，主畫面就只剩一件事要做。
        # ⚠️ 真值仍然是 out_path（_effective_out／_build_argv 讀的是它），
        # out_show 只是縮短過的顯示字串。
        # ⚠️ 「輸出：」與路徑是**同一個標籤**：分成兩格的話，第 0 欄的寬度由
        # 輸入那一列決定，路徑就會被推到離冒號很遠的地方。
        # ⚠️ 與上面隔 SP_XL（不是 SP_MD）：輸入與輸出是卡片裡的**兩件事**，靠這
        # 一道比較寬的縫分群，就不必再畫一條分隔線進來加重量。
        ttk.Label(files, textvariable=self.out_show,
                  style="CardHint.Card.TLabel", anchor="w",
                  wraplength=p(700)).grid(
            row=3, column=0, sticky="ew", pady=(p(SP_XL), 0))
        change = ttk.Button(files, text="變更…", style="Small.TButton",
                            command=self._pick_output)
        change.grid(row=3, column=1, sticky="ew", padx=(p(SP_SM), 0),
                    pady=(p(SP_XL), 0))
        self._inputs.append(change)
        files.columnconfigure(0, weight=1)

        # 主畫面到這裡就結束：選項一個都不露出來（日常轉檔一項都不必動）。
        # 色塊那一項曾經留在這裡做 A/B，量完之後收進了選項區。

        # ---- 卡片二：進度與動作 ----
        # 位置緊接在檔案卡底下、排在轉檔選項的收合按鈕**之前**（使用者
        # 2026-08-25 指示）：主線是「選檔 → 按下去」，把它排在收合按鈕後面等於
        # 讓主線的終點被一個日常不必碰的東西隔開，展開選項區時還會被推到很下面。
        #
        # ⚠️ 進度回饋三件事（動作、進度條、狀態字）**同一列**：舊版是右上角一個
        # 「就緒」、版面中段一條 indeterminate 進度條、最下面一大塊日誌，三個東西
        # 講同一件事卻散在 900px 內，而中間那條進度條連「跑到第幾頁」都不說。
        #
        # ⚠️ 這一區 2026-08-26 從「浮在版面上的裸列」改成**卡片**：卡片化之後
        # 「浮著」的意思變了——畫面上其他每一塊都是白卡，只有它坐在灰底上，讀起來
        # 不是「被強調」而是「沒做完」。主要動作靠那顆藍鈕自己就夠亮了。
        # ⚠️ 動作與結果坐在同一張卡片上也是有意的：按下去與跑完之後要看的東西
        # 在同一個地方，結果列不必再自己找一條縫擠進版面。
        actions = self.actions_frame = ttk.Frame(root, style="Card.TFrame",
                                                 padding=p(CARD_PAD))
        actions.pack(fill="x", **pad)
        # 主要動作鈕：畫面上唯一吃滿彩色的東西（Apple 藍，停止時換成深紅）。
        # 字級與內距在 apply_ui_style，圓角底板由 SquircleSkin 畫；沒裝成皮膚
        # 就是佈景自己的 Accent 藍底圓角鈕。
        self.run_btn = ttk.Button(actions, text=RUN_TEXT, style=RUN_STYLE,
                                  command=self._on_run_clicked)
        self.run_btn.grid(row=0, column=0, sticky="w")
        # ⚠️ 開場一定是 indeterminate：載入引擎（首次還要下載約 90MB 模型）那段
        # 根本沒有頁數可報，畫一條會動的假進度是騙人的。收到第一行
        # `page N (n/total)` 才換成 determinate（見 _scan_line）。
        # ⚠️ **沒在跑就不顯示**（2026-08-25 晚，使用者指示）：閒置時本來是一條
        # determinate value=0 的空槽，但那條空槽橫貫版面中段，讀起來像一條分隔
        # 線——一個「什麼都沒在發生」的元件卻在畫面上劃了一刀。⚠️ **用
        # `grid_remove()`／`grid()`，不要 destroy、也不要改欄寬**：它與按鈕、狀態
        # 字是**同一列的三個欄**，列高由最高的那個（按鈕）決定，藏掉這條 7px
        # 的東西**版面完全不動**（欄 1 的 weight 讓空間原地留白）。這正是它可以
        # 「沒在跑就不顯示」的前提：換成 pack_forget 或整列重排，按鈕與狀態字
        # 就會在按下去的瞬間跳位。
        self.progress = ttk.Progressbar(actions, mode="determinate", value=0)
        self.progress.grid(row=0, column=1, sticky="ew", padx=p(SP_LG))
        self.progress.grid_remove()
        # ⚠️ 樣式要是 `.Card.TLabel` 那一支：顏色是 _set_status 動態換的，但
        # **底色**得跟著卡片，否則它是一塊灰矩形浮在白卡上
        self.status = ttk.Label(actions, text="就緒",
                                style="CardStatus.Card.TLabel",
                                anchor="e", foreground=self.pal["ok"])
        self.status.grid(row=0, column=2, sticky="e")
        actions.columnconfigure(1, weight=1)
        # 右欄只保留狀態字**真正量得到**的最大寬度，剩下的全歸進度條。
        # ⚠️ 這一格仍然要釘住（`minsize`）：不釘的話欄寬會跟著字串長短變，
        # 進度條的右端就會在「就緒」與「載入 OCR 引擎…」之間左右抽動。
        actions.columnconfigure(2, minsize=self._status_width() + p(SP_XS))

        # ---- 結果列（動作卡片的第二列，跑完才出現）----
        # ⚠️ 取代舊版的「完成」對話框（`askyesno("要開啟所在資料夾嗎？")`）。
        # 那個框有一個當時就寫在註解裡的毛病：它正好蓋在日誌最後一行的降級
        # WARNING 上面，而按完「否」就再也不會有人往下看——於是「有幾頁沒轉成
        # 文字」這件最該知道的事被一個問句擋掉了。現在頁碼直接寫在這一列上。
        # ⚠️ 用 `grid_remove()` 藏、不要 `pack_forget()`：它是卡片裡的一列，
        # grid 會把整列從高度計算裡拿掉（舊版那個「空掉的槽把高度永久留下」的坑
        # ——只發生在 pack 的容器上，沿革見 docs/dev §5.4）。
        res = self.result_row = ttk.Frame(actions, style="CardBody.TFrame")
        res.grid(row=1, column=0, columnspan=3, sticky="ew",
                 pady=(p(SP_XL), 0))
        self.result_lbl = ttk.Label(res, anchor="w", wraplength=p(560),
                                    justify="left",
                                    style="CardStatus.Card.TLabel")
        self.result_lbl.grid(row=0, column=0, sticky="ew")
        self.open_deck_btn = ttk.Button(res, text="開啟簡報",
                                        style="Small.TButton",
                                        command=self._open_deck)
        self.open_deck_btn.grid(row=0, column=1, padx=(p(SP_SM), 0))
        self.open_dir_btn = ttk.Button(res, text="開啟資料夾",
                                       style="Small.TButton",
                                       command=self._open_result_folder)
        self.open_dir_btn.grid(row=0, column=2, padx=(p(SP_SM), 0))
        res.columnconfigure(0, weight=1)
        res.grid_remove()

        # ---- 卡片三：轉檔選項（就這五個）----
        # ⚠️ **收合鈕就是這張卡片的標題列，展開的內容在同一張卡片裡**（使用者
        # 2026-08-26 指示，附了 meeting-scribe 那張網頁截圖）。舊版是「卡片外一顆
        # 整條寬的鈕 ＋ 底下另外長出一張卡片」，兩者之間還有一道 SP_SM 的縫——讀
        # 起來是兩塊東西，而它們講的是同一件事。
        # ⚠️ **內距左右是 CARD_PAD、上下是 SP_MD，兩邊刻意不同**（2026-08-26 晚，
        # 使用者圈了三張卡片的左邊那圈白說寬度不一致、要以 MP4-2-SRT 為準）：
        #   左右 24 —— 卡片裡**每一個直接子元件的左緣都落在同一條線上**（輸入框、
        #     開始轉檔鈕、收合鈕的底板、展開的選項區、日誌槽），量出來全是 24。⚠️ 對齊
        #     是**元件邊緣**不是文字：卡片一裡「輸入 PDF」那行字（24）與輸入框裡的
        #     字（約 31）本來就不同，因為後者還隔著底板自己的內距。
        #   上下 12 —— 標題列自己也有內距，兩份疊起來才是文字距卡片頂的距離，給 12
        #     之後與另外兩張卡片的 24 幾乎同一條線。⚠️ 這裡原本寫「12+10＝22」，
        #     那個 10 是收合鈕當時的垂直內距；2026-08-27 膠囊化之後標題列的高度改由
        #     底板（`SQ_H_ADV`＝45）釘死、文字在其中置中，這個加法已經不描述任何
        #     東西了——**要動的話重量，不要照那條算式反推**。給 12 的理由沒變：
        #     而且**卡片高度不變**（一度想上下也給 24，兩張可收合卡片各長高 24px，
        #     選項展開時 reqheight 會來到 841——1080p@125% 的工作區只有約 810）。
        # ⚠️ **只有五個選項**（使用者 2026-08-25 指示）：頁碼、保留浮水印、關閉
        # 簡體混入修正、色塊獨立畫成矩形、保留圖表內小字。刪掉的是「改了會讓結
        # 果差很多，或根本用不到」的那些——中文字型／渲染 DPI／最低信心分數是校
        # 準值（200 DPI ＋ Microsoft YaHei 是整條管線唯一校準過的作業點）、粗體
        # 模式與快速模型會整份換掉判別依據、推論裝置有 auto、辨識語言預設就是
        # 中英、行合併與除錯資料是開發用的。它們**連變數都不留**，直接吃 cli.py
        # 的預設值（要調就用命令列，README 的選項表是完整的）。
        adv_card = ttk.Frame(root, style="Card.TFrame",
                             padding=(p(CARD_PAD), p(SP_MD)))
        adv_card.pack(fill="x", **pad)
        adv_card.columnconfigure(0, weight=1)
        self.adv_toggle = ttk.Button(adv_card, style=ADV_STYLE,
                                     command=self._toggle_advanced)
        self._set_chevron(self.adv_toggle, False, ADV_LABEL)
        # 整條寬：舊版是寫死 34 字寬的一顆鈕，右半邊永遠空著，看起來像一個
        # 停用的輸入框而不是可以按的區段標題
        self.adv_toggle.grid(row=0, column=0, sticky="ew")
        # 展開的內容。⚠️ 用 `grid_remove()` 收、不要 `pack_forget()`：grid 會把
        # 整列從卡片的高度計算裡拿掉，卡片自己就縮回只剩標題列。舊版那個「空掉的
        # 容器把高度永久留在版面上」的坑（沿革見 docs/dev §5.4）**只發生在 pack
        # 的容器**，換成 grid 之後在定義上就不會發生。
        # ⚠️ **內容直接坐在卡片上，不要再框一圈**（使用者 2026-08-27 圈了那條灰
        # 線說「請消失」）。一度做成一張「與卡片同色、只有一圈 `card_line`」的底板
        # （`Sq.inner`），想法是把展開的內容框起來——但卡片自己已經是一個框了，
        # 框裡再一個框只是多一條線。⚠️ 連帶：那張底板整個刪掉，不要留著沒人用
        # ——沒有邊框的它與 `CardBody.TFrame` 完全同義。
        # ⚠️ 下緣要自己補一份 `SP_MD`：卡片的上下內距是 12（標題列自己有 10，見
        # 上面那段），但展開之後**底部沒有標題列來補那一截**，不補的話最後一個
        # 核取方塊離卡片底只有 12、比左右的 24 窄一半。
        opt = self.opt_frame = ttk.Frame(adv_card, style="CardBody.TFrame")
        opt.grid(row=1, column=0, sticky="ew", pady=p(SP_MD))
        opt.grid_remove()

        # 頁碼自己一行排在最上面：五個裡面只有它是「每次可能不一樣」的值，
        # 其餘四個是開關
        ttk.Label(opt, text="頁碼（例 1-5,8，留空＝全部）",
                  style="Card.TLabel").grid(row=0, column=0, sticky="w")
        pages_entry = ttk.Entry(opt, textvariable=self.pages, width=18)
        pages_entry.grid(row=0, column=1, sticky="w", padx=(p(SP_MD), 0))
        self._inputs.append(pages_entry)

        checks = [
            ("保留浮水印（NotebookLM／Gemini Notebook）", self.keep_watermark),
            ("關閉簡體混入修正", self.no_s2t),
            ("色塊獨立畫成矩形（預設是讓文字方塊自帶底色）", self.cover),
            ("保留圖表內小字（預設保留原圖不轉文字）", self.keep_tiny_text),
        ]
        # 一列一項：雙欄版的第 0 欄由最長的標籤決定寬度，兩欄合計會超出視窗的
        # 最小寬度，在 125%／150% 顯示縮放下右欄的選項會被擠出可見範圍
        # ⚠️ 行距是 SP_SM 不是 2px：四個核取方塊擠成 4px 一行時，它們看起來
        # 像一段文字而不是四個可以按的東西
        # ⚠️ 樣式要是 `.Card.TCheckbutton` 那一支：ttk 的 Checkbutton 跟 Label
        # 一樣是實色底的，坐在卡片上不指定就是四塊淺灰矩形
        for i, (label, var) in enumerate(checks):
            cb = ttk.Checkbutton(opt, text=label, variable=var,
                                 style="Card.TCheckbutton")
            cb.grid(row=1 + i, column=0, columnspan=2, sticky="w",
                    pady=(p(SP_LG) if i == 0 else p(SP_SM), 0))
            self._inputs.append(cb)

        # ---- 卡片四：詳細訊息（預設收起來）----
        # ⚠️ 舊版這一區是**開著**的，而且是唯一 expand=True 的東西：閒置時整個
        # 視窗有 51% 是一個只有兩行字的白盒子（2026-08-25 量的）。收起來之後，
        # 「開始轉檔」會自己把它打開（見 _start）——要看的時候它就在。
        # ⚠️ 這張卡片**常駐**，`expand` 是動態切的（見 _set_log_shown）：收起來時
        # 若還 expand=True，剩下的高度會全灌進一張只有標題列的空卡片。
        log_card = self.log_card = ttk.Frame(
            root, style="Card.TFrame", padding=(p(CARD_PAD), p(SP_MD)))
        log_card.pack(fill="x")
        log_card.columnconfigure(0, weight=1)
        log_card.rowconfigure(1, weight=1)
        head = ttk.Frame(log_card, style="CardBody.TFrame")
        head.grid(row=0, column=0, sticky="ew")
        self.log_toggle = ttk.Button(head, style=ADV_STYLE,
                                     command=self._toggle_log)
        self._set_chevron(self.log_toggle, False, LOG_LABEL)
        self.log_toggle.pack(side="left", fill="x", expand=True)
        # 紀錄檔的完整路徑不再印在日誌區裡（在這個寬度下會折成兩行），改成一顆
        # 按鈕。⚠️ 開不起來紀錄檔時它要是灰的，不是按了沒反應。
        # ⚠️ 它跟收合鈕同一列、同樣坐在卡片上，所以走同一張低調皮
        self.open_log_btn = ttk.Button(head, text="開啟紀錄",
                                       style=SUBTLE_STYLE,
                                       command=self._open_log)
        self.open_log_btn.pack(side="right", padx=(p(SP_SM), 0))
        if self._log_path is None:
            self.open_log_btn.state(["disabled"])

        # 日誌槽。圓角**由這一層畫**：`tk.Text` 是 classic 控制項，沒有 ttk 樣式、
        # 做不到圓角（換皮之後畫面上唯一還是方角的東西就是它）。Text 縮在裡面，
        # 四周留 SP_SM —— 只要內距大於圓角半徑的 0.29 倍，方角就不會伸進弧裡。
        # ⚠️ 這是版面上**唯一**凹下去的那一層（三階的最底下一階）：日誌是「內容
        # 區」，值得與卡片分開；轉檔選項那一區則是直接坐在卡片上（見上面那段）。
        well = self.logframe = ttk.Frame(log_card, style="Sunken.TFrame",
                                         padding=p(SP_SM))
        well.grid(row=1, column=0, sticky="nsew", pady=(p(SP_MD), 0))
        well.grid_remove()
        # tk.Text 是 classic 控制項，佈景挑不動它 —— 顏色要自己餵
        # ⚠️ `padx` 是 SP_XS：12（卡片）+ 8（槽）+ 4 ＝ 24，與上面幾張卡片的
        # CARD_PAD 對齊
        # ⚠️ `width` 要明寫，而且要**小**：`tk.Text` 的預設是 80 個字元，在這個
        # 字型下約 660px——它會直接變成整個視窗的最小寬度（2026-08-27 量到內容
        # 需求 764 > minsize 760，追下去就是這個預設值）。日誌區是 expand=True
        # 撐滿的，實際寬度由視窗決定，這個數字只是「不能再窄」的地板。
        # ⚠️ 同理 `height=10` 也是初值，實際高度由 grid 的 weight 撐（見 _fit_window）。
        self.log = tk.Text(well, height=10, width=32, wrap="word",
                           font=(self.ui_font, 10),
                           relief="flat", borderwidth=0,
                           # 邊框與圓角都由外層那張底板畫，這裡不要再描一圈——
                           # 兩圈疊起來是「框中框」，而且內圈是方的
                           highlightthickness=0,
                           padx=p(SP_XS), pady=p(SP_XS),
                           background=self.pal["log_bg"],
                           foreground=self.pal["log_fg"],
                           insertbackground=self.pal["log_fg"],
                           selectbackground=self.pal["log_sel"],
                           selectforeground=self.pal["log_fg"])
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(well, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.config(yscrollcommand=sb.set)
        self._append("提示：首次轉檔會自動下載 OCR 模型（約數十 MB），"
                     "期間進度條不會報頁數，請耐心等候。\n")

        # 拖放：接得上就把提示換成拖放版（_refresh_input_state 讀這個旗標）
        self.dnd_ok = enable_file_drop(
            (root, files, self.in_entry), self._on_files_dropped)
        # 貼上路徑。⚠️ 綁在視窗上，所以輸入欄自己的貼上也會叫到這裡——焦點
        # 在任何輸入類控制項上時要原封不動放行，否則使用者在頁碼欄貼一段文字
        # 會變成「整條路徑被換掉」
        self.bind_all("<Control-v>", self._on_paste_path)
        self.bind_all("<Control-V>", self._on_paste_path)
        # 選好檔就能按 Enter 開跑（焦點在輸入欄時最自然的下一個動作）
        self.bind("<Return>", lambda e: self._on_run_clicked())
        # 輸入路徑一改（打字、拖放、貼上、瀏覽…）就重新驗證並帶出輸出檔名
        self.in_path.trace_add("write", lambda *a: self._refresh_input_state())
        self.out_path.trace_add("write", lambda *a: self._refresh_out_show())

    # ---- 手風琴：選項區與日誌區 ----
    # ⚠️ 兩區**不同時攤開**（2026-08-25 量出來的）：當時展開進階區之後
    # `winfo_reqheight()` 是 953 邏輯 px，而本機（2560×1440@150%）的工作區只有
    # 912，1080p@125% 的筆電更只有約 810——也就是說「展開」這個動作本身就會把
    # 日誌區與進度條推到工作列底下。分成兩個模式之後兩邊都塞得進去：
    #   設定模式：展開選項 → 收日誌（在調參數，不是在看跑）
    #   執行模式：按下轉檔 → 收選項、展開日誌（在看跑，不是在調參數）
    def _set_chevron(self, btn: ttk.Button, shown: bool, label: str) -> None:
        """收合鈕左邊那個三角形。

        有皮膚就用**圖片**（`compound="left"`）：字元放不大——`▸`／`▾` 在 10pt 下的
        字墨只有 7×8px，而字級是整顆鈕共用的，沒辦法只放大一個字元（使用者
        2026-08-27 說「三角形太小」）。⚠️ 沒有皮膚時退回文字前綴，那一對必須同寬
        （見 CHEV_SHOW）。

        ⚠️ 圖片與文字之間的縫**畫在圖片裡**（`make_skin.SQ_CHEV_GAP`）：ttk 的
        `compound` 沒有間距選項，靠這個補。
        """
        chev = self.skin.chev if self.skin else None
        if chev:
            btn.config(image=chev["down" if shown else "right"],
                       compound="left", text=label)
        else:
            btn.config(text=(CHEV_HIDE if shown else CHEV_SHOW) + label)

    def _toggle_advanced(self) -> None:
        self._set_advanced(not self.show_advanced.get())

    def _toggle_log(self) -> None:
        self._set_log_shown(not self.show_log.get())

    def _set_advanced(self, show: bool, fit: bool = True) -> None:
        if show == self.show_advanced.get() and not fit:
            return
        self.show_advanced.set(show)
        # ⚠️ `grid()`／`grid_remove()`，不是 `pack`：內容是卡片裡的一列，grid 會把
        # 整列從卡片的高度計算裡拿掉，卡片自己就縮回只剩標題列
        if show:
            self.opt_frame.grid()
            self._set_log_shown(False, fit=False)
        else:
            self.opt_frame.grid_remove()
        self._set_chevron(self.adv_toggle, show, ADV_LABEL)
        if fit:
            self._fit_window()

    def _set_log_shown(self, show: bool, fit: bool = True) -> None:
        self.show_log.set(show)
        # ⚠️ 卡片**常駐**，動的是槽與卡片自己的 `expand`：日誌是版面上唯一撐得開
        # 的東西（`_fit_window` 鉗高度時唯一縮得動的那一個），但收起來時若還
        # expand=True，剩下的高度會全灌進一張只有標題列的空卡片。
        # ⚠️ 日誌卡片**不吃 `_pad` 的下緣間距**：它是最後一個區塊，root 的
        # padding 已經給了下邊界，再加一次會在視窗底部留一條雙倍的白
        if show:
            self.logframe.grid()
            self.log_card.pack_configure(fill="both", expand=True)
            self._set_advanced(False, fit=False)
        else:
            self.logframe.grid_remove()
            self.log_card.pack_configure(fill="x", expand=False)
        self._set_chevron(self.log_toggle, show, LOG_LABEL)
        if fit:
            self._fit_window()

    def _work_area(self) -> tuple[int, int] | None:
        """這個視窗所在螢幕的工作區上下緣（實體像素），取不到回 None。

        ⚠️ 要問**視窗所在的那一個**螢幕，不是主螢幕：接了外接螢幕的機器上，主
        螢幕的工作區高度跟視窗實際待的地方可以差好幾百像素，而這個值是拿來決定
        「視窗最高能多高」的。"""
        if not sys.platform.startswith("win"):
            return None
        try:
            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                            ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                            ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            mon = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)  # NEAREST
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if not ctypes.windll.user32.GetMonitorInfoW(mon,
                                                        ctypes.byref(info)):
                return None
            return info.rcWork.top, info.rcWork.bottom
        except Exception:
            return None

    def _fit_window(self) -> None:
        """把視窗高度調成剛好裝得下現在的內容，並鉗進所在螢幕的工作區。

        展開、收合、開始轉檔全部走這一支——舊版是三個地方各自算高度，其中
        「收合時把借走的高度還回去」還得記兩個數字（撐開前、撐開後）才躲得掉
        「視窗管理員把要求的高度夾掉一截」的坑。改成每次都重新量 `reqheight`
        就沒有那個坑了：算式裡沒有減法，也就沒有累積誤差。

        ⚠️ **鉗進工作區**是這支存在的主要理由：`reqheight` 可以超過螢幕（實測
        展開進階區時 953 > 912），而 Tk 會照著設，多出來的部分直接落到工作列
        底下——最下面那一塊（結果列、日誌區）就這樣消失了。鉗完還要檢查視窗
        底端有沒有掉出工作區，是的話把整個視窗往上移。

        ⚠️ **使用者自己拉過視窗就只長不縮**：我們上次設的高度記在 `_auto_h`，
        對不上就代表中間有人動過手，那是他要的尺寸，不是我們借的。"""
        self.update_idletasks()
        cur = self.winfo_height()
        need = self.winfo_reqheight()
        user_sized = self._auto_h is not None and abs(cur - self._auto_h) > 8
        target = need
        work = self._work_area()
        if work is not None:
            top, bottom = work
            # 標題列與外框：視窗外緣到內容區頂端的距離
            chrome = max(0, self.winfo_rooty() - self.winfo_y())
            target = min(target, (bottom - top) - chrome - self.px(16))
        if user_sized and target <= cur:
            return                       # 使用者要的尺寸，不要縮回去
        if target != cur:
            self.geometry(f"{self.winfo_width()}x{target}")
            self.update_idletasks()
        self._auto_h = self.winfo_height()
        # 長高之後底端可能掉到工作區外（視窗本來就靠近螢幕下緣）
        if work is not None:
            top, bottom = work
            chrome = max(0, self.winfo_rooty() - self.winfo_y())
            outer = self._auto_h + chrome + self.px(8)
            if self.winfo_y() + outer > bottom:
                self.geometry(f"+{self.winfo_x()}+{max(top, bottom - outer)}")

    # ---- 檔案挑選 ----
    def _pick_input(self) -> None:
        p = filedialog.askopenfilename(
            title="選擇輸入 PDF",
            filetypes=[("PDF 檔", "*.pdf"), ("所有檔案", "*.*")])
        if p:
            # 輸出檔名、驗證、提示文字全部由 in_path 的 trace 接手
            # （_refresh_input_state）——打字、拖放、貼上走的是同一條路
            self.in_path.set(p)

    def _on_files_dropped(self, event) -> None:
        """檔案總管拖進來的檔案。⚠️ 一次可以拖一疊，我們只吃第一個。

        `event.data` 是 **Tcl 的 list 字面值**（`{C:/有 空白/a.pdf} C:/b.pdf`），
        不是用空白切就好的字串——含空白的路徑會被大括號包起來。用直譯器自己的
        `splitlist` 拆，那是唯一不會拆錯的作法。"""
        if self.running:
            # 灰掉的欄位擋不住拖放（它不經過控制項）。⚠️ 不可以靜靜地什麼都不做：
            # 那看起來就是拖放壞了，而使用者會一直重拖
            self._set_hint("轉檔中不能換檔案 —— 要換請先按「■ 停止轉檔」。",
                           err=True)
            return
        try:
            paths = [q for q in self.tk.splitlist(event.data) if q]
        except Exception:
            paths = []
        pdfs = [q for q in paths if q.lower().endswith(".pdf")]
        if not pdfs:
            if paths:
                # 拖了東西進來卻沒有 PDF：不要無聲無息，那看起來就像拖放壞了
                self._set_hint(f"拖進來的不是 PDF：{Path(paths[0]).name}", err=True)
            return
        self.in_path.set(pdfs[0])

    def _on_paste_path(self, event):
        """Ctrl+V 貼上一條路徑。

        ⚠️ **焦點在輸入類控制項上時一律放行**（回 None 讓 Tk 走預設的貼上）：
        這個綁定掛在整個視窗上，不擋掉的話，使用者在「頁碼」欄貼一段文字會變成
        「輸入 PDF 被換掉」——而且他貼的那一段還是照樣進了頁碼欄，兩件事同時
        發生，看起來就像程式在亂跳。"""
        if self.running:
            return None                  # 轉檔中不換輸入檔（見 _set_inputs_enabled）
        w = self.focus_get()
        if isinstance(w, (ttk.Entry, tk.Entry, ttk.Spinbox, tk.Spinbox,
                          tk.Text, ttk.Combobox)):
            return None
        try:
            text = self.clipboard_get().strip().strip('"')
        except Exception:
            return None
        if text.lower().endswith(".pdf") and Path(text).is_file():
            self.in_path.set(text)
            return "break"
        return None

    # ---- 輸入狀態：提示、輸出檔名、按鈕能不能按 ----
    def _set_hint(self, text: str, err: bool = False) -> None:
        self.hint.config(text=text,
                         foreground=self.pal["err"] if err else self.pal["muted"])

    def _refresh_input_state(self) -> None:
        """輸入路徑變了：驗證、帶出輸出檔名、決定「開始轉檔」能不能按。

        ⚠️ **用擋的、不要用告知的**：舊版無論欄位是空的還是路徑不存在都讓人
        按得下去，按了才跳一個對話框說「請先選擇輸入 PDF 檔」。錯誤在按下去
        之前就已經看得出來，就不該等到按下去才講。"""
        raw = self.in_path.get().strip().strip('"')
        drop = "，或把 PDF 直接拖進這個視窗" if getattr(self, "dnd_ok", False) else ""
        ok = False
        if not raw:
            self._set_hint(f"請先選擇要轉檔的 PDF{drop}。")
        else:
            try:
                ok = Path(raw).expanduser().is_file()
            except OSError:
                ok = False
            if not ok:
                self._set_hint(f"找不到這個檔案：{raw}", err=True)
            elif not raw.lower().endswith(".pdf"):
                # 擋不到但要說：副檔名不對通常是選錯檔，而 OCR 一跑就是好幾分鐘
                self._set_hint("這個檔看起來不是 PDF，轉檔可能會失敗。")
                ok = True
            else:
                # 選好了就不必再講拖放：那句提示是給「還沒有檔案」的人看的
                self._set_hint("已選好檔案，按「開始轉檔」即可（也可以直接按 Enter）。")
        self._sync_auto_out(raw if ok else "")
        self._refresh_run_button()
        # 狀態字要跟按鈕講同一件事：沒有檔案時按鈕是灰的，右邊卻寫著綠色的
        # 「就緒」，兩者互相打臉。⚠️ 轉檔中／剛跑完的狀態不可以被蓋掉
        if not self.running:
            self._set_status("就緒" if ok else "等待選檔",
                             self.pal["ok"] if ok else self.pal["muted"])

    def _sync_auto_out(self, src: str) -> None:
        """輸入檔換了就跟著換輸出檔。

        只在「輸出欄是空的」時才自動帶，會讓輸出永遠釘在第一份 PDF 上，第二次
        轉檔就把第一份的成果直接蓋掉（而且沒走另存對話框，覆寫確認永遠不會
        出現）；所以只要欄位還是**我們上次填的值**就更新。"""
        cur = self.out_path.get().strip()
        if cur and cur != self._auto_out:
            return                       # 使用者自己改過，不要動它
        self._auto_out = str(Path(src).with_suffix(".pptx")) if src else ""
        self.out_path.set(self._auto_out)

    def _refresh_out_show(self) -> None:
        out = self._effective_out()
        if out is None:
            self.out_show.set("輸出：（選好 PDF 之後自動命名）")
            return
        src = self.in_path.get().strip().strip('"')
        same_dir = False
        try:
            same_dir = bool(src) and Path(src).expanduser().resolve().parent == out.parent
        except OSError:
            pass
        self.out_show.set(f"輸出：{out.name}（與來源同資料夾）" if same_dir
                          else f"輸出：{_shorten_path(out)}")

    def _set_inputs_enabled(self, on: bool) -> None:
        """轉檔中把「按了也沒用」的輸入全部鎖起來（使用者 2026-08-25 晚指示）。

        argv 在 `_start()` 的第一行就已經組好交給背景執行緒了，所以轉檔中改頁碼、
        改核取方塊、甚至換一份輸入 PDF，**對這一趟完全沒有作用**——但畫面上那些
        控制項照樣有反應、照樣打得進字，看起來像是改得到。鎖起來是把「這件事現在
        做不到」講在使用者動手之前，跟「路徑不存在就把開始轉檔鎖起來」是同一條原則
        （用擋的、不要用告知的）。

        ⚠️ **檔案區也要一起鎖**，不是只鎖轉檔選項：換輸入 PDF 對這一趟同樣沒有
        作用，只鎖一半反而讓人以為另一半改得到。
        ⚠️ **停止鈕、兩顆收合鈕、開啟紀錄不在清單裡**：那些是轉檔中真的要按的。
        ⚠️ 拖放與 Ctrl+V 是**繞過控制項**的另外兩條路，`_on_files_dropped()` 與
        `_on_paste_path()` 各自也要擋——不然欄位是灰的、路徑卻換掉了。"""
        for w in self._inputs:
            w.state(["!disabled"] if on else ["disabled"])

    def _refresh_run_button(self) -> None:
        if self.running:
            return                       # 轉檔中那顆鈕是「停止」，永遠可以按
        try:
            ok = Path(self.in_path.get().strip().strip('"')).expanduser().is_file()
        except OSError:
            ok = False
        self.run_btn.state(["!disabled"] if ok else ["disabled"])

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
        # ⚠️ **只傳介面上真的動得到的旗標**。舊版連 `--dpi 200 --min-score 0.50
        # --device auto --font "Microsoft YaHei"` 都照傳一遍，那是把 cli.py 的預
        # 設值抄一份再原封不動送回去：值沒變，但 cli.py 改預設時 GUI 會安靜地把
        # 舊值釘住。現在沒傳的一律由 argparse 決定。
        if self.pages.get().strip():
            argv += ["--pages", self.pages.get().strip()]
        if self.no_s2t.get():
            argv.append("--no-s2t")
        if self.cover.get():
            argv.append("--cover")
        if self.keep_watermark.get():
            argv.append("--keep-watermark")
        if self.keep_tiny_text.get():
            argv.append("--keep-tiny-text")
        return argv

    # ---- 啟動轉檔 ----
    def _on_run_clicked(self) -> None:
        """同一顆鈕的兩個身分：閒置時是「開始轉檔」，轉檔中是「停止轉檔」。"""
        if self.running:
            self._request_cancel()
            return
        # ⚠️ 鍵盤那條路也要吃這道閘門：Enter 綁在整個視窗上，不擋的話「按鈕是
        # 灰的但 Enter 照樣跑得動」，而跑進去之後擋人的又變回那個對話框
        if "disabled" in self.run_btn.state():
            return
        self._start()

    def _request_cancel(self) -> None:
        """使用者按了停止。

        ⚠️ **不跳確認對話框**：這顆鈕上面白紙黑字寫著「停止轉檔」，再問一次
        「你確定嗎」只是把剛剛移除的那種摩擦換個地方裝回來。

        ⚠️ **停不了「當下這一頁」**，要講清楚：cli 的旗標是每頁檢查一次的
        （見 `pdf2ppt/cli.py` 的 main()），而一頁的 OCR 是一次進不去的呼叫。
        所以按下去之後畫面要顯示「停止中…」而不是假裝已經停了——不然使用者會
        以為按鈕壞掉，再去關視窗，那才是真的會留下半截 .pptx 的路。"""
        if not self.running or self._cancel.is_set():
            return
        self._cancel.set()
        self.run_btn.config(text=STOPPING_TEXT)
        self.run_btn.state(["disabled"])
        self._set_status("停止中…", self.pal["warn"])
        self._append("\n[停止] 已要求停止；目前這一頁跑完就會收工，不會產生檔案。\n")

    def _set_status(self, text: str, color: str) -> None:
        self.status.config(text=text, foreground=color)

    def _start(self) -> None:
        # 專案位置不必在這裡再驗一次：main() 在開窗之前就擋掉了不合格的資料夾
        # （fail_no_project），視窗存在本身就代表 PROJECT_DIR 是好的。
        if self.running:
            return
        try:
            argv = self._build_argv()
        # ⚠️ `tk.TclError` 也要攔，即使現在的欄位都是 StringVar／BooleanVar：
        # 那是 IntVar/DoubleVar 在欄位被清空時丟的型別，它直接繼承 Exception、
        # 不是 ValueError，漏攔的話例外會穿到 Tk 的 report_callback_exception
        # ——沒有對話框、沒有日誌、狀態也不變，按鈕看起來就像壞掉。
        # （2026-08-25 選項砍到五個之後 DPI／信心分數的 Spinbox 沒了，這一半
        # 目前是防禦性的；再加回任何數值欄位它就會重新用得上。）
        except (ValueError, tk.TclError) as e:
            messagebox.showwarning("選項有誤", str(e) or "請檢查選項欄位。")
            return

        self.running = True
        self._cancel.clear()             # ⚠️ 沿用同一個 Event，不要新建
        self.run_btn.config(text=STOP_TEXT, style=STOP_STYLE)
        self.run_btn.state(["!disabled"])
        self._set_status("準備中…", self.pal["warn"])
        # 上一趟的結果留在畫面上會被當成這一趟的
        self.result_row.grid_remove()
        self._scan_buf = ""
        self._pages_done = self._pages_total = 0
        self._last_warning = ""
        self._determinate = False
        self._set_inputs_enabled(False)    # 轉檔中改了也沒用（argv 已經送出去了）
        self.progress.grid()               # 沒在跑就不顯示（見 _build_ui）
        self.progress.config(mode="indeterminate", value=0)
        # 不定長度進度條不帶任何資訊，12ms（83Hz）只是白白讓主執行緒重繪；
        # 用 ttk 的預設節奏即可
        self.progress.start()
        # 工作列跟著視窗裡那條走（見 taskbar_progress）。⚠️ 這裡要**主動設一次**
        # 而不是等第一頁：載入引擎那段可能要幾十秒，切走的人在那之前需要看到
        # 「它已經開始了」。上一趟若留著黃／紅，這一下也一併蓋掉。
        taskbar_progress(self, 0, 0)
        # 執行模式：收起選項區、把日誌打開（見 _set_advanced 上面那段說明）
        self._set_advanced(False, fit=False)
        self._set_log_shown(True)
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
            proj = PROJECT_DIR
            if str(proj) not in sys.path:
                sys.path.insert(0, str(proj))
            # 切到專案目錄，確保模型快取等相對路徑落在專案底下
            os.chdir(proj)
            try:
                from pdf2ppt.cli import main
            except ModuleNotFoundError as e:
                # 開窗前驗過 pdf2ppt\cli.py 在不在，所以缺的通常是相依套件——
                # 兩種情形的處方不同，別把「沒 uv sync」講成資料夾有問題
                if (e.name or "").split(".")[0] == "pdf2ppt":
                    raise ModuleNotFoundError(
                        f"pdf2ppt 套件在啟動之後消失了：{proj}\n"
                        "請確認資料夾沒有被移動或刪除，然後重開程式。\n"
                        f"原始錯誤：{e}") from e
                raise ModuleNotFoundError(
                    f"缺少相依套件 {e.name}。\n"
                    f"請在 {proj} 執行：uv sync（或雙擊「安裝.bat」）\n"
                    f"原始錯誤：{e}") from e
            rc = main(argv, cancel=self._cancel)
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
                text = "".join(chunks)
                self._scan_stream(text)
                self._append(text)
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

    # ---- 把 cli 的輸出讀成進度 ----
    def _scan_stream(self, text: str) -> None:
        """從這一批輸出裡撈出進度、降級頁碼與「正在載入引擎」。

        ⚠️ 要有跨批次的行緩衝：queue 裡的一塊不保證切在換行上，`page 7 (3/15)`
        很可能被切成兩半（模型下載那段更是每幾十毫秒就來一塊）。"""
        self._scan_buf += text
        while "\n" in self._scan_buf:
            line, self._scan_buf = self._scan_buf.split("\n", 1)
            # 下載進度條是用 \r 原地重寫的，只有最後一段才是完整的一行
            self._scan_line(line.rsplit("\r", 1)[-1].strip())
        if len(self._scan_buf) > 4096:   # 一直沒換行（進度條），不要無限長大
            self._scan_buf = self._scan_buf[-1024:]

    def _scan_line(self, line: str) -> None:
        if line.startswith(_WARN_PREFIX):
            self._last_warning = line[len(_WARN_PREFIX):].strip()
            return
        if line.startswith(_LOADING_PREFIX):
            self._set_status("載入 OCR 引擎…", self.pal["warn"])
            return
        m = _PAGE_RE.match(line)
        if not m:
            return
        done, total = int(m.group(1)), int(m.group(2))
        if not self._determinate:
            # 到這裡才知道總頁數；引擎載入那段沒有頁數可報，所以在此之前一律
            # 是不定長度進度條
            self.progress.stop()
            self.progress.config(mode="determinate", maximum=total, value=done)
            self._determinate = True
        self.progress.config(maximum=total, value=done)
        self._pages_done, self._pages_total = done, total
        taskbar_progress(self, done, total)   # 切走的人看的是這一條
        # ⚠️ **只報頁數，不報剩餘時間**（使用者 2026-08-25 指示刪掉）。頁數是
        # 量到的事實，剩餘時間是外推出來的猜測——而這裡的每頁耗時差異很大
        # （一行進旋轉救援就要跑七次 OCR），猜出來的數字會自己跳來跳去。
        self._set_status(f"{done}/{total} 頁", self.pal["warn"])

    def _finish(self, rc: int) -> None:
        self.progress.stop()
        # 工作列的收場與「要不要閃」。⚠️ 預設值是最壞的那個，而且是刻意的：
        # 底下任何一步炸掉都代表這趟不是乾淨完成，工作列就該留一條紅的。
        outcome, notify = "error", True
        try:
            out = self._effective_out()
            if rc in (0, PARTIAL_RC):
                # 有頁面降級時不能報成單純的「完成」：檔案是好的，但那幾頁
                # 沒有可編輯文字。⚠️ 頁碼要**寫在結果列上**：舊版是把它留在日誌
                # 最後一行的 WARNING，而完成對話框正好蓋在那一行上面
                part = rc == PARTIAL_RC
                outcome = "warn" if part else "ok"
                if self._determinate:
                    self.progress.config(value=self.progress["maximum"])
                self._set_status("完成（有降級）" if part else "完成 ✓",
                                 self.pal["warn"] if part else self.pal["ok"])
                shown = str(out) if out else "(輸入檔同名 .pptx)"
                tag = "⚠ 轉檔完成，但有頁面降級" if part else "✓ 轉檔完成"
                self._append(f"\n{tag}：{shown}\n")
                note = (f"；{_fmt_degraded(self._last_warning)}"
                        if part and self._last_warning else "")
                self._show_result(
                    ("⚠  完成，但有頁面沒轉成文字" if part else "✓  轉檔完成")
                    + f"：{out.name if out else ''}{note}",
                    self.pal["warn"] if part else self.pal["ok"], out)
            elif rc == CANCELLED_RC:
                # ⚠️ 停止**不閃、也不留顏色**：這是使用者自己剛按下去的，人就在
                # 螢幕前面，通知他一件他自己做的事只是噪音。
                outcome, notify = "ok", False
                self._set_status("已停止", self.pal["muted"])
                self._append("\n■ 已停止（沒有產生檔案）\n")
                self._show_result("■  已停止 —— 沒有產生檔案",
                                  self.pal["muted"], None)
            else:
                self._set_status(f"失敗（代碼 {rc}）", self.pal["err"])
                self._append(f"\n✗ 轉檔失敗（return code = {rc}）\n")
                self._show_result(f"✗  轉檔失敗（代碼 {rc}）—— 詳細訊息在下方",
                                  self.pal["err"], None)
                self._set_log_shown(True)
        finally:
            # 工作列：先定色，再決定要不要叫人。⚠️ 兩件事都要在 `_finish` 裡做完
            # ——這是整趟轉檔唯一保證會走到的收尾點（停止與失敗也走這裡）。
            taskbar_finish(self, outcome)
            if notify:
                flash_taskbar(self)      # 已經在前景的話它自己會不做事
            # ⚠️ **順序有意義**：`_refresh_input_state()` 要趁 `running` 還是 True
            # 時呼叫。它結尾會把狀態字寫成「就緒」，而那一步是用 `not self.running`
            # 擋住的——先把旗標放掉再呼叫，剛剛寫上去的「完成 ✓」／「已停止」／
            # 「失敗」就會被蓋成「就緒」。這裡要它做的只有一件事：把拖放／Ctrl+V
            # 被擋掉時寫進去的那句紅字換回正常提示。
            self._refresh_input_state()
            self.running = False
            self._set_inputs_enabled(True)
            # ⚠️ 歸零成 determinate/0 **再**藏起來：舊版是「`_determinate` 為假
            # 就留在 indeterminate」，那正是它自己註解裡警告過的狀態（Sun Valley
            # 下停住的 indeterminate 會在最左邊留一小截藍色）。現在閒置根本不顯
            # 示，但下一趟 `_start()` 之前的狀態還是要乾淨。
            self.progress.config(mode="determinate", value=0)
            self.progress.grid_remove()
            self.run_btn.config(text=RUN_TEXT, style=RUN_STYLE)
            self._refresh_run_button()
            self._fit_window()

    def _show_result(self, text: str, color: str, out: Path | None) -> None:
        """轉檔結果長在日誌區上方的一條列上，不再彈對話框。

        ⚠️ 這一列取代的是 `askyesno("完成", "…要開啟所在資料夾嗎？")`。互動式
        對話框在這裡有三個問題：它蓋住剛印出來的降級 WARNING、它逼使用者現在
        就回答一個「等一下再說」也完全合理的問題，而且答「否」之後那個檔案的
        路徑就再也沒有一個看得到的入口。"""
        self.result_lbl.config(text=text, foreground=color)
        has_file = out is not None and out.is_file()
        for btn in (self.open_deck_btn, self.open_dir_btn):
            btn.grid() if has_file else btn.grid_remove()
        self._result_path = out if has_file else None
        self.result_row.grid()

    def _open_deck(self) -> None:
        path = getattr(self, "_result_path", None)
        if path is None:
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.run([opener, str(path)], check=False)
        except Exception as e:
            self._append(f"[開啟簡報失敗] {e}\n")

    def _open_result_folder(self) -> None:
        path = getattr(self, "_result_path", None)
        if path is not None:
            self._open_folder(path)

    def _open_log(self) -> None:
        """開這一趟的執行紀錄。⚠️ 邊寫邊開是正常用法（逐次 flush），不必等結束。"""
        if self._log_path is None:
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(self._log_path))  # type: ignore[attr-defined]
            else:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.run([opener, str(self._log_path)], check=False)
        except Exception as e:
            self._append(f"[開啟紀錄失敗] {e}\n")

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
        * 啟動當下的 stderr：從終端機跑時它就是主控台（使用者當場就看得到），
          從「啟動.vbs」進來時它是 cmd 重導向的暫存檔
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
    # ⚠️ 同樣要在建 Tk 之前：視窗一建出來就已經被工作列歸隊了
    set_app_user_model_id()
    # 沒有 pdf2ppt 套件就別開窗：介面上每一個控制項都只是在為那一次呼叫收集
    # 參數，缺了它整支程式沒有任何一件事做得成（使用者 2026-08-25 指示）。
    # 結束碼分兩種：訊息框跳出來了就回 SELF_REPORTED_RC（啟動端安靜收工，
    # 使用者只看到一個框），跳不出來才回 1 讓啟動端把 stderr 那份顯示出來。
    if not is_project_dir(PROJECT_DIR):
        return SELF_REPORTED_RC if fail_no_project() else 1
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
