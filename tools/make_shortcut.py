#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""在桌面與「開始」功能表放上本工具的捷徑。

由「安裝.bat」在環境建好之後呼叫；資料夾搬過位置要重建，直接跑

    uv run python tools/make_shortcut.py

**存在的理由是那三段路徑只有安裝當下才知道**：使用者把專案放在哪裡是他的
自由（他換電腦的方式就是複製整個資料夾），所以捷徑要指的「啟動.vbs」、工作
目錄與圖示檔**都得從這支腳本自己的位置往上推**——任何一段寫死，就只有開發
那台機器按得動，別人桌面上會出現一顆指向不存在路徑的死圖示，比沒有更糟。

⚠️ **捷徑指的是 `wscript.exe`，不是 `啟動.vbs` 本身**（本專案與姊妹專案
`meeting-scribe` 的關鍵差異：那邊的入口是 `.bat`，直接指就好）。`.vbs` 當
捷徑目標有兩個踩得到的坑，都會讓「雙擊桌面圖示」與「雙擊 `啟動.vbs`」表現
不一致：**①** 副檔名關聯被改掉——不少公司把 `.vbs` 關聯到記事本當作防毒
措施，那時捷徑會打開原始碼而不是執行；**②** 預設主機若是 `cscript`，就會
蹦出一個黑視窗，而那正是 `啟動.vbs` 存在的唯一理由。把主機釘成
`wscript.exe`、`.vbs` 當參數，兩個都繞開了。找不到 `wscript.exe` 才退回直接
指 `.vbs`。

⚠️ **為什麼不叫 PowerShell 的 `WScript.Shell`**：`.lnk` 在 Windows 上只有
COM 一條路，而 PowerShell 正是公司電腦最常被群組原則收走的東西（執行原則、
Constrained Language Mode 都擋得掉）。ctypes 直接叫 `IShellLinkW` 不經過任何
外部行程，也不必為了一顆捷徑多拉一個相依進來。

⚠️ **中文不從 .bat 傳進來**：批次檔是 cp950，字串經 cmd 那一層會被重新編碼。
捷徑名稱與所有訊息都寫在這支 UTF-8 的 Python 裡，「安裝.bat」只負責呼叫一行
**純 ASCII** 的指令。

⚠️ **建不出來絕不能擋住安裝**：走到這一步環境已經好了，捷徑只是方便。桌面被
群組原則重導到唯讀的網路磁碟、OneDrive 沒登入、資安軟體擋住寫入，都會讓這裡
失敗——那時該做的是告訴他「雙擊資料夾裡的啟動.vbs 一樣能用」，而不是讓他以為
安裝失敗、回頭重跑一次。離開碼只拿來讓「安裝.bat」挑最後那句話該怎麼寫，
**兩種都算安裝成功**：0=桌面那顆放好了，3=沒放成。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 路徑的單一出處：專案根目錄、桌面、「開始」功能表都從這一支拿——`repo_root()` 往
# 上幾層、OneDrive 把桌面整個重導走的那個坑、問不到已知資料夾時該退到哪裡，理由全
# 寫在那邊的 docstring 裡（本檔原本自己抄了一份，2026-08-27 收攏）。
# ⚠️ **走 `sys.path` 而不是要求套件已經安裝**：這支跑在**安裝當下**，而且本專案根本
# 不做套件安裝（`pyproject.toml` 的 `package = false`）。做法與 `tools/make_skin.py`
# 同。⚠️ 插的是**根目錄**、不是 `src`——這個 repo 沒有 `src/` 那一層。
# ⚠️ 下面那個 `parents[1]` 與 `repo_root()` 看起來重複，其實回答的是兩個問題：前者
# 是「去哪裡找那個套件」（找錯了會當場 ImportError，很吵），後者是「專案根目錄在
# 哪」（算錯了是安靜地把捷徑指到別處）。**不要為了少一行而把 ROOT 寫回前者**，那會
# 讓兩邊哪天分岔時沒有任何徵狀。
#
# 捷徑的**名字、提示文字與工作列身分**同樣只有一份，在 `pdf2ppt/brand.py`。
# ⚠️ **這裡是 import，不是讀檔正規表示式**（2026-08-27 收攏時一起換掉的）：那三個值
# 原本住在 `pdf2ppt_gui_2.py`，import 它會把整個 tkinter 拉進安裝流程，所以當時只能
# 用 regex 讀字面值、抓不到就退回自己那份 fallback。⚠️ **而那個退路正是它的問題**：
# fallback 的值與正本一模一樣，所以 regex 哪天抓不到（換行、改成 f-string、常數搬
# 家、非 ASCII 的 `→` 被編碼咬到）**捷徑照樣建得出來、只是帶著一份不會再更新的舊
# 值**，沒有任何徵狀。值搬進 `brand.py` 之後那個理由整個消失：它一行 import 都沒有，
# 這支腳本本來就已經 import 同一個套件裡的 `paths` 了。姊妹專案 MP4-2-SRT 同一天跟進，
# 兩邊現在同形（沿革見 `docs/dev/windows-環境與入口.md` §5.3）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pdf2ppt import brand                                    # noqa: E402
from winkit.paths import (assets_dir, desktop_dir, repo_root,  # noqa: E402
                          start_menu_programs_dir)
from winkit.shortcut import script_host, write_shortcut       # noqa: E402

ROOT = repo_root()

LAUNCHER = "啟動.vbs"          # 不開黑視窗的那條，README 教的也是它
# ⚠️ 圖示走 `assets_dir()`（＝套件底下的 `assets/`），不是自己從 ROOT 拼：資產跟著
# **套件**走，而「它在哪」只有共用包那一份說了算。
ICON = assets_dir() / "icon.ico"

# ⚠️ **IShellLink／PropertyStore 那整套 COM 2026-08-28 搬進共用包 `winkit.shortcut`**
# （見上面的 import）：vtable 的順序、`hr >= 0` 才算成功、`CoUninitialize` 只能配對
# 呼叫、把 AppUserModelID 寫進 .lnk——那些是「怎麼寫一顆 .lnk」，兩支程式都該一樣。
# ⚠️ 這裡留下來的是「**要放在哪、叫什麼名字、對使用者說什麼**」，那是這支程式的身分。
# ⚠️ **`APP_ID` 不再由這裡傳**：共用包直接從 `winkit.host()` 拿（＝`brand.APP_ID`），
# 所以「程式宣告的身分」與「寫進捷徑的身分」在定義上就是同一個值，不必再靠人記得。


def install_to(folder: Path) -> Path:
    """在 folder 底下建立（或覆寫）捷徑，回傳落地的 .lnk 路徑。

    同名一律覆寫：使用者換電腦的方式是複製整個專案資料夾，而「搬過位置就重跑
    安裝.bat」那句話要成立，這裡就得真的把舊捷徑那條指到別處的路徑改回來。"""
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{brand.APP_TITLE}.lnk"
    vbs = ROOT / LAUNCHER
    if host := script_host():
        # 參數要自己加引號：專案路徑含中文、也可能含空格
        target, args = host, f'"{vbs}"'
    else:
        target, args = vbs, ""
    write_shortcut(dest, target, args, ROOT, ICON, brand.APP_DESC)
    return dest


def main() -> int:
    # 只改 errors、不改 encoding：輸出被導向檔案時 encoding 會退回 cp950，
    # 而專案資料夾的名字可能有 cp950 表達不了的字——那時 errors 若是預設的
    # strict，會在印路徑那一行整支炸掉。接到真主控台時 PEP 528 已經保證中文
    # 顯示正確（底層走 WriteConsoleW，與黑視窗的 chcp 950 無關）。
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    if not (ROOT / LAUNCHER).is_file():
        print(f"[提醒] 找不到 {LAUNCHER}，略過建立捷徑。")
        return 3
    if not ICON.is_file():
        # 圖示缺了還是建得出捷徑（Windows 會用預設圖示），但那顆圖示在桌面上
        # 認不出來，寧可講一句
        print(f"[提醒] 找不到 {ICON.relative_to(ROOT)}，捷徑會用系統預設圖示。"
              "　可以跑 uv run python tools/make_icon.py 重新產生。")

    # 只講原因，不講「那你改用啟動.vbs」——那句由「安裝.bat」的 :nolnk 統一印。
    try:
        install_to(desktop_dir())
    except Exception as exc:
        print(f"[提醒] 桌面圖示建立失敗：{exc}")
        return 3

    print(f"已經在桌面放上「{brand.APP_TITLE}」，以後雙擊它就能啟動。")

    # 開始功能表是備援，不是主角：桌面被公司政策鎖住時它通常還寫得進去，
    # 而且使用者可以按 Windows 鍵直接搜尋名字。失敗就安靜跳過——為了一個
    # 備援去嚇使用者，只會讓他以為安裝有問題。
    if (programs := start_menu_programs_dir()) is not None:
        try:
            install_to(programs)
            print("「開始」功能表裡也放了一份，按 Windows 鍵打名字就找得到。")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
