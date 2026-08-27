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

import ctypes
import os
import sys
from ctypes import POINTER, byref, c_int, c_void_p, c_wchar_p
from pathlib import Path
from uuid import UUID

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
# 這支腳本本來就已經 import 同一個套件裡的 `paths` 了。姊妹專案 MP4-2-SRT 那邊仍是
# regex（沿革見 `docs/dev/windows-環境與入口.md` §5.3）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pdf2ppt import brand                                    # noqa: E402
from pdf2ppt.paths import (desktop_dir, repo_root,           # noqa: E402
                           start_menu_programs_dir)

ROOT = repo_root()

LAUNCHER = "啟動.vbs"          # 不開黑視窗的那條，README 教的也是它
ICON = Path("assets") / "icon.ico"

_S_OK = 0
_CLSCTX_INPROC_SERVER = 1
_CLSID_SHELL_LINK = "{00021401-0000-0000-C000-000000000046}"
_IID_ISHELL_LINK_W = "{000214F9-0000-0000-C000-000000000046}"
_IID_IPERSIST_FILE = "{0000010B-0000-0000-C000-000000000046}"
_IID_IPROPERTY_STORE = "{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}"
# PKEY_AppUserModel_ID（propkey.h）：工作列拿來認「這是哪個應用程式」
_PKEY_AUMID_FMTID = "{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"
_PKEY_AUMID_PID = 5

# vtable 上的**順序**，不是名字——數錯一格就是呼叫到隔壁那個方法，而那多半
# 是當場 crash 不是回錯誤碼。所以照介面宣告的順序整段抄在這裡對照：
#   IUnknown:      0 QueryInterface  1 AddRef  2 Release
#   IShellLinkW:   3 GetPath  4 GetIDList  5 SetIDList  6 GetDescription
#                  7 SetDescription  8 GetWorkingDirectory  9 SetWorkingDirectory
#                  10 GetArguments  11 SetArguments  12 GetHotkey  13 SetHotkey
#                  14 GetShowCmd  15 SetShowCmd  16 GetIconLocation
#                  17 SetIconLocation  18 SetRelativePath  19 Resolve  20 SetPath
#   IPersistFile:  3 GetClassID  4 IsDirty  5 Load  6 Save  7 SaveCompleted
_QUERY_INTERFACE, _RELEASE = 0, 2
_SET_DESCRIPTION, _SET_WORKING_DIRECTORY = 7, 9
_SET_ARGUMENTS = 11
_SET_ICON_LOCATION, _SET_PATH = 17, 20
_PERSIST_SAVE = 6
#   IPropertyStore: 3 GetCount  4 GetAt  5 GetValue  6 SetValue  7 Commit
_PS_SET_VALUE, _PS_COMMIT = 6, 7


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", ctypes.c_ulong)]


class _PROPVARIANT(ctypes.Structure):
    """只夠用來裝一個 VT_LPWSTR 的 PROPVARIANT。

    ⚠️ **尾巴那個 `pad` 不可以省**：真正的 PROPVARIANT 是 24 bytes（x64）／
    16（x86），而 `PropVariantClear` 會把整個結構清成零——宣告短了就是寫出界
    8 個位元組。這裡刻意排成與真實大小相同（8 + 指標 + 指標）。
    ⚠️ 也不要找 `InitPropVariantFromString`：那是 propvarutil.h 的 **inline**
    函式，propsys.dll 沒有匯出這個符號（2026-08-25 實測 not found）。"""
    _fields_ = [("vt", ctypes.c_ushort),
                ("r1", ctypes.c_ushort),
                ("r2", ctypes.c_ushort),
                ("r3", ctypes.c_ushort),
                ("p", c_void_p),
                ("pad", c_void_p)]


_VT_LPWSTR = 31


def _propvariant_str(text: str) -> _PROPVARIANT:
    """把字串包成 VT_LPWSTR 的 PROPVARIANT；字串用 CoTaskMemAlloc 配置，
    才能由 `PropVariantClear` 收回去。"""
    ole32 = ctypes.windll.ole32
    ole32.CoTaskMemAlloc.restype = c_void_p          # ⚠️ 不設就會在 x64 被截斷
    ole32.CoTaskMemAlloc.argtypes = [ctypes.c_size_t]
    buf = (text + chr(0)).encode("utf-16-le")
    mem = ole32.CoTaskMemAlloc(len(buf))
    if not mem:
        raise MemoryError("CoTaskMemAlloc 失敗")
    ctypes.memmove(mem, buf, len(buf))
    pv = _PROPVARIANT()
    pv.vt = _VT_LPWSTR
    pv.p = mem
    return pv


def _guid(text: str) -> _GUID:
    u = UUID(text)
    return _GUID(u.time_low, u.time_mid, u.time_hi_version,
                 (ctypes.c_ubyte * 8)(*u.bytes[8:]))


def script_host() -> Path | None:
    """`wscript.exe` 的位置（見模組 docstring 的第一條 ⚠️）。找不到回 None。"""
    host = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wscript.exe"
    return host if host.is_file() else None


def _call(obj: c_void_p, slot: int, argtypes: tuple, *args) -> int:
    """叫 COM 物件 vtable 上第 slot 個方法，回 HRESULT。

    ⚠️ argtypes 明寫、不用 `type(a)` 推：`byref()` 回的是 CArgObject，推出來
    的型別是錯的，而錯的型別在這一層不會報錯、只會把垃圾推上堆疊。"""
    vtable = ctypes.cast(obj, POINTER(c_void_p))[0]
    method = ctypes.cast(vtable, POINTER(c_void_p))[slot]
    return ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, *argtypes)(method)(obj, *args)


def _check(hr: int, what: str) -> None:
    if hr != _S_OK:
        raise OSError(f"{what} 失敗（HRESULT 0x{hr & 0xFFFFFFFF:08X}）")


def write_shortcut(dest: Path, target: Path, arguments: str, workdir: Path,
                   icon: Path, description: str) -> None:
    """寫出一個 .lnk；失敗一律拋例外（呼叫端決定要不要當成致命）。"""
    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)
    try:
        clsid, iid = _guid(_CLSID_SHELL_LINK), _guid(_IID_ISHELL_LINK_W)
        link = c_void_p()
        _check(ole32.CoCreateInstance(byref(clsid), None, _CLSCTX_INPROC_SERVER,
                                      byref(iid), byref(link)),
               "CoCreateInstance(ShellLink)")
        try:
            _check(_call(link, _SET_PATH, (c_wchar_p,), str(target)), "SetPath")
            _check(_call(link, _SET_ARGUMENTS, (c_wchar_p,), arguments),
                   "SetArguments")
            _check(_call(link, _SET_WORKING_DIRECTORY, (c_wchar_p,), str(workdir)),
                   "SetWorkingDirectory")
            _check(_call(link, _SET_DESCRIPTION, (c_wchar_p,), description),
                   "SetDescription")
            # 第二個參數是 .ico 裡的第幾張圖；icon.ico 是同一個圖示的八個尺寸、
            # 不是八張不同的圖，所以固定 0（Windows 自己會挑合適的尺寸）
            _check(_call(link, _SET_ICON_LOCATION, (c_wchar_p, c_int), str(icon), 0),
                   "SetIconLocation")

            # ⚠️ 要在 IPersistFile::Save **之前**寫：Commit 只改記憶體裡的
            # 那個連結物件，真正落檔的是後面那個 Save。少了這一段，使用者
            # 把捷徑釘到工作列之後，釘的那顆與執行中的視窗會是兩個按鈕
            # （釘選那顆的身分是從 wscript.exe 推出來的）。
            store_iid = _guid(_IID_IPROPERTY_STORE)
            store = c_void_p()
            if _call(link, _QUERY_INTERFACE, (c_void_p, c_void_p),
                     byref(store_iid), byref(store)) == _S_OK:
                try:
                    key = _PROPERTYKEY(_guid(_PKEY_AUMID_FMTID), _PKEY_AUMID_PID)
                    prop = _propvariant_str(brand.APP_ID)
                    try:
                        _check(_call(store, _PS_SET_VALUE, (c_void_p, c_void_p),
                                     byref(key), byref(prop)),
                               "SetValue(AppUserModelID)")
                        _check(_call(store, _PS_COMMIT, ()), "Commit")
                    finally:
                        ole32.PropVariantClear(byref(prop))
                finally:
                    _call(store, _RELEASE, ())

            persist_iid = _guid(_IID_IPERSIST_FILE)
            persist = c_void_p()
            _check(_call(link, _QUERY_INTERFACE, (c_void_p, c_void_p),
                         byref(persist_iid), byref(persist)),
                   "QueryInterface(IPersistFile)")
            try:
                # 第二個參數 fRemember=TRUE：把這個路徑記成物件目前的檔案
                _check(_call(persist, _PERSIST_SAVE, (c_wchar_p, c_int),
                             str(dest), 1), "Save")
            finally:
                _call(persist, _RELEASE, ())
        finally:
            _call(link, _RELEASE, ())
    finally:
        ole32.CoUninitialize()


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
    write_shortcut(dest, target, args, ROOT, ROOT / ICON, brand.APP_DESC)
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
    if not (ROOT / ICON).is_file():
        # 圖示缺了還是建得出捷徑（Windows 會用預設圖示），但那顆圖示在桌面上
        # 認不出來，寧可講一句
        print(f"[提醒] 找不到 {ICON}，捷徑會用系統預設圖示。"
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
