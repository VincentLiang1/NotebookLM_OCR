r"""路徑的單一出處：我們自己的落地位置，加上要問 Windows 才算得準的那幾個。

`%LOCALAPPDATA%\NotebookLM_Pdf2Ppt` 底下的所有落地（目前只有皮膚快取）都從
`appdata_root()` 出發：基底路徑邏輯只此一份，要盤點「這支工具在使用者機器上寫了
什麼」看這裡即可。⚠️ 專案底下的 `logs\`（隨專案走、可以整包刪）不在此列，它由
`pdf2ppt_gui_2.py` 自己算——那是**專案相對**的路徑，不是使用者機器上的落地。

桌面與「開始功能表」（`desktop_dir` / `start_menu_programs_dir`）也收在這裡。它們
不是我們的落地位置，擺進來的理由只有一個：**那兩條路徑都不可以用 `~/Desktop` 猜**
（原因見 `desktop_dir`），而這件事原本只寫在 `tools/make_shortcut.py` 裡——哪天別的
地方也要用，那個教訓就只會有一邊記得。

⚠️ **本檔移植自姊妹專案 meeting-scribe 的同名模組**（2026-08-27，使用者指定拿它
當底層工具的藍本）：那邊 450 筆提交、實際踩過 OneDrive 重導與非 Windows 匯入兩個
坑，結構與註解照搬。⚠️ 它屬於共用層 A/B 界線裡「**下游不該改**」的那一類——三個姊
妹專案應該長得**一模一樣**，本專案刻意不同的只有 `APP_DIR_NAME` 的**值**（2026-08-27
搬進 `pdf2ppt/brand.py`，這裡只剩一行注入）與 `repo_root()` 的**層數**（那兩個才是
「這個專案需要跟別人不一樣」的 A 類）。界線與落地形式見 `docs/dev/architecture.md` §4。

⚠️ **只准 import 標準函式庫，外加 `pdf2ppt/brand.py` 這一個注入點**（理由與
`pdf2ppt/palette.py` 那一條相同）：GUI 的啟動路徑會載到這一支，而
`pdf2ppt/__init__.py` 只有一行 docstring、`brand.py` 一行 import 都沒有——這裡多拉
一個相依進來，就等於把 numpy／pymupdf／python-pptx 那一整串塞進「雙擊到視窗出現」
之間。
"""
import ctypes
import os
from pathlib import Path
from uuid import UUID

from pdf2ppt import brand

# 這支工具在 `%LOCALAPPDATA%` 底下的資料夾名。⚠️ **值住在 `pdf2ppt/brand.py`**——本
# 模組是**通用**的路徑工具（將來要整支搬進共用包），而資料夾名是**這支程式的身分**：
# 兩者混在同一個檔案裡，共用包就搬不走。三者為什麼不可以併成一份，也寫在那邊。
# ⚠️ **真的要搬那天，這一行改成由呼叫端注入**（參數或一次性初始化），不要讓共用包
# 反過來 import 下游的 `brand`——那是環，而且會把「誰依賴誰」整個顛倒過來。
APP_DIR_NAME = brand.APP_DIR_NAME

# Windows 的「已知資料夾」GUID（shlobj_core.h 的 FOLDERID_*）
_DESKTOP_GUID = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"
_PROGRAMS_GUID = "{A77F5D77-2E2B-44C3-A6A2-ABA601054A51}"   # 開始功能表\程式集


def repo_root() -> Path:
    r"""專案根目錄（`assets\`、`tools\`、`docs\`、`logs\` 與四個入口都掛在它底下）。

    `pdf2ppt/paths.py` → **往上一層**。⚠️ 姊妹專案那兩份是 `parents[2]`，本專案是
    `parents[1]`，差別在**這個 repo 沒有 `src/` 那一層**：套件 `pdf2ppt/` 直接坐在
    根目錄上，入口腳本就在它旁邊。這不是隨手擺的——`pyproject.toml` 的
    `package = false` 寫著理由（根目錄同時有 `pdf2ppt.py` 與 `pdf2ppt/`，同名，做成
    wheel 只會製造麻煩），所以這個 repo **永遠**是原地跑，這條也就永遠成立。"""
    return Path(__file__).resolve().parents[1]


def appdata_root() -> Path:
    r"""`%LOCALAPPDATA%\NotebookLM_Pdf2Ppt`；沒有 LOCALAPPDATA 的環境退回 `~/.cache`。

    ⚠️ **每次呼叫重讀環境變數，不可以在 import 時定死**：測試靠
    `monkeypatch.setenv("LOCALAPPDATA", ...)` 把落地導進 tmp，定死就導不動了——而那
    不只是「測試比較難寫」，是**測試會在開發者自己的家目錄裡長出東西**，然後在別人的
    機器上留下一堆沒人知道哪來的資料夾。
    ⚠️ **取不到就退回，不丟例外**：掛在這底下的整條路（皮膚快取）是**純加速**，一個
    `KeyError` 會從「皮膚裝不起來」一路炸到視窗開不起來。⚠️ 退的是 `~/.cache`，**不
    是 `TEMP` 或 `.`**（移植前這裡寫的是 `LOCALAPPDATA or TEMP or "."`）：`.` 是**當前
    工作目錄**，而從捷徑進來時那正好就是專案資料夾，等於直接違反下面那條。
    ⚠️ **不可以寫回專案資料夾**：那裡可能是唯讀（Program Files、公司政策掛的網路
    磁碟），而且使用者換電腦是複製整個資料夾——把機器專屬的東西（某台機器的 DPI 畫出
    來的皮膚）一起複製過去，不是慢就是錯。
    ⚠️ **走 `LOCALAPPDATA` 不是 `APPDATA`**：這底下全是**衍生自這台機器**的產物。漫遊
    設定檔會跟著使用者跑到另一台機器上，而那台的 DPI 不一樣（指紋擋得住不相容，但那就
    變成每台機器互相把對方的快取洗掉）。"""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    return Path(base) / APP_DIR_NAME


def known_folder(guid: str) -> Path | None:
    r"""問 Windows 要「已知資料夾」的實際位置，問不到回 None。

    ⚠️ **不用 `ctypes.wintypes` 湊 GUID 結構**：那個模組在非 Windows 上 import 就會
    炸，而這裡是全專案都會載到的 leaf 模組。改用 ctypes 的基本型別自己排，欄位寬度
    是一樣的。"""

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    try:
        u = UUID(guid)
        g = _GUID(u.time_low, u.time_mid, u.time_hi_version,
                  (ctypes.c_ubyte * 8)(*u.bytes[8:]))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(g), 0, None, ctypes.byref(out)) != 0:
            return None
        try:
            return Path(out.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)
    except Exception:
        return None


def desktop_dir() -> Path:
    r"""桌面的實際位置。

    ⚠️ **不寫死 `~/Desktop`**：OneDrive 的「資料夾備份」會把桌面整個重導到
    `%USERPROFILE%\OneDrive\Desktop`，而寫死的那條路徑往往還在、只是沒人看——捷徑
    建立成功，使用者卻永遠看不到。所以先問 Windows，問不到才退回猜。"""
    return known_folder(_DESKTOP_GUID) or next(
        (p for p in (Path.home() / "OneDrive" / "Desktop", Path.home() / "Desktop")
         if p.is_dir()), Path.home())


def start_menu_programs_dir() -> Path | None:
    r"""這個使用者的「開始功能表\程式集」；問不到才退回 `%APPDATA%` 那條。

    回 None 代表連退路都不成立（非 Windows、或 APPDATA 不在）——呼叫端要當成「這台
    機器沒有開始功能表」處理，不是當成錯誤：它只是桌面捷徑的備援，少了不影響工具
    能不能用。"""
    if found := known_folder(_PROGRAMS_GUID):
        return found
    if base := os.environ.get("APPDATA"):
        return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return None
