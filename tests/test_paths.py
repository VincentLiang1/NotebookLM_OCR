r"""落地位置的單一出處（`pdf2ppt/paths.py`）：守「只有一份」與那兩個沒有訊息的失效。

2026-08-27 把散在兩處的路徑推導收攏進 `pdf2ppt/paths.py`（藍本是姊妹專案
meeting-scribe 的同名模組，那邊踩過 OneDrive 重導與非 Windows 匯入兩個坑）。收攏
本身沒有測試守不住——**散回去的過程是安靜的**：下一個人要加一個落地位置時，就地
再拼一次 `%LOCALAPPDATA%` 是最順手的寫法，而多出來的那一份不會有任何徵狀，直到
兩份對不上、使用者的快取憑空「消失」為止。

四類：

1. **每次呼叫重讀環境變數** —— 定死在 import 時的話，測試就導不進 tmp，於是
   **在開發者自己的家目錄裡長出資料夾**（而且是在別人的機器上）。
2. **取不到就退回、不丟例外** —— 掛在底下的整條路是純加速，一個 `KeyError` 會從
   「皮膚裝不起來」一路炸到視窗開不起來。
3. **只有一份** —— 環境變數的讀取、三支已知資料夾函式、資料夾名的字面值。
4. **落地位置 ≠ 顯示身分** —— 資料夾名、視窗標題、工作列身分是三個概念，字面值
   哪天撞在一起也不可以併成一份（理由見 `pdf2ppt/paths.py` 的 `APP_DIR_NAME`）。
"""
import ast
import re
import sys
from pathlib import Path

import pdf2ppt_gui_2 as G
from pdf2ppt import paths

ROOT = Path(__file__).resolve().parents[1]
_SKIP = {".venv", "__pycache__", ".git", ".pytest_cache", "logs"}


def _py_files() -> list[Path]:
    return [p for p in ROOT.rglob("*.py")
            if not any(part in _SKIP for part in p.parts)]


def _owners(pattern: re.Pattern) -> list[str]:
    """哪幾支 `.py` 裡出現這個樣式（回 repo 相對路徑，排序過）。"""
    return sorted(p.relative_to(ROOT).as_posix() for p in _py_files()
                  if pattern.search(p.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- #
#  一、每次呼叫重讀環境變數
# --------------------------------------------------------------------------- #
def test_the_landing_root_follows_the_environment_at_call_time(monkeypatch, tmp_path):
    """⚠️ **不可以在 import 時把基底路徑定死**。

    症狀不是「測試比較難寫」：`monkeypatch` 導不動的話，任何會落檔的測試都會寫進
    **跑測試那個人自己的家目錄**，然後在別人的機器上留下一堆沒人知道哪來的資料夾。
    所以這裡連換兩次，第二次要跟著動。"""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "one"))
    assert paths.appdata_root() == tmp_path / "one" / paths.APP_DIR_NAME
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "two"))
    assert paths.appdata_root() == tmp_path / "two" / paths.APP_DIR_NAME, (
        "換了環境變數卻沒跟著動：基底路徑被 import 時定死了")


def test_a_missing_environment_variable_falls_back_instead_of_raising(monkeypatch):
    r"""⚠️ **取不到就退回 `~/.cache`，不丟例外**（非 Windows、被清乾淨的服務帳號）。

    掛在這底下的整條路是**純加速**（皮膚快取），一個 `KeyError` 會從「皮膚裝不
    起來」一路炸成「視窗開不起來」，而那是使用者唯一的入口。
    ⚠️ 也順便釘住**退到哪裡**：退回 `.`（當前工作目錄）的話，從捷徑進來時那正好
    就是專案資料夾——而專案資料夾可能是唯讀的，使用者換電腦又是整包複製，機器
    專屬的快取跟著走就只是帶著別台機器的 DPI。收攏之前這裡真的寫著 `or "."`。"""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    root = paths.appdata_root()          # 不可以拋例外
    assert root == Path.home() / ".cache" / paths.APP_DIR_NAME
    assert paths.repo_root() not in root.parents, "落地位置掉進專案資料夾裡了"
    assert Path.cwd() not in root.parents, "落地位置跟著當前工作目錄跑"


def test_the_skin_cache_hangs_off_the_landing_root(monkeypatch, tmp_path):
    """GUI 只補「皮膚放在它底下的哪一格」，位置本身走 `pdf2ppt/paths.py`。

    ⚠️ 覆寫用的環境變數要留著：皮膚快取的測試靠它把落地導進 tmp。"""
    monkeypatch.delenv(G.SKIN_CACHE_ENV, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert G.skin_cache_root() == tmp_path / paths.APP_DIR_NAME / "skin"
    monkeypatch.setenv(G.SKIN_CACHE_ENV, str(tmp_path / "elsewhere"))
    assert G.skin_cache_root() == tmp_path / "elsewhere"


# --------------------------------------------------------------------------- #
#  二、層數與相依
# --------------------------------------------------------------------------- #
def test_the_repo_root_is_the_folder_the_entry_points_live_in():
    r"""`repo_root()` 往上**一**層（姊妹專案是兩層，差在這個 repo 沒有 `src/`）。

    ⚠️ 層數數錯是安靜的：捷徑會被建到一個看起來很像、但少一層的路徑上，而
    `install_to()` 連錯誤都不會有——它自己會 `mkdir` 出來。所以這裡驗的不是層數
    本身，是**那一層底下真的擺著入口**。"""
    root = paths.repo_root()
    for name in ("pdf2ppt_gui_2.py", "pdf2ppt.py", "pyproject.toml", "啟動.vbs"):
        assert (root / name).exists(), f"repo_root() 底下沒有 {name}：層數數錯了"
    assert (root / "pdf2ppt" / "paths.py").is_file()


def test_the_paths_module_only_imports_the_standard_library():
    """⚠️ 它坐在 **GUI 的啟動路徑**上（理由與 `pdf2ppt/palette.py` 那一條相同）。

    這一支多拉一個相依進來，等於把 numpy／pymupdf／python-pptx 那一整串塞進
    「雙擊到視窗出現」之間；而 `tools/` 那兩支產生器是在 `uv sync` 之前就要跑得
    起來的，多一個相依它們就先掛。"""
    tree = ast.parse((ROOT / "pdf2ppt" / "paths.py").read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mods.add("(相對匯入)" if node.level else (node.module or "").split(".")[0])
    extra = mods - set(sys.stdlib_module_names)
    assert not extra, f"paths.py 匯入了標準函式庫以外的東西：{sorted(extra)}"


# --------------------------------------------------------------------------- #
#  三、只有一份
# --------------------------------------------------------------------------- #
# ⚠️ 樣式故意拆成兩半再拼：整串寫在同一行的話，這支測試會掃到**自己**。
_ENV_API = "environ"
_ENV_KEY = "LOCAL" + "APPDATA"


def test_the_environment_variable_is_read_in_exactly_one_place():
    """基底路徑只准在一支裡算出來。

    ⚠️ **判別的是「同一行同時出現環境變數 API 與那個變數名」**，不是那個變數名
    本身——`pdf2ppt/style.py` 有一條 `%…%` 開頭的字型路徑字面值（給 Windows 自己
    展開的），那不是讀環境變數，不該被掃進來。"""
    pat = re.compile(rf"{_ENV_API}[^\n]*{_ENV_KEY}|{_ENV_KEY}[^\n]*{_ENV_API}")
    assert _owners(pat) == ["pdf2ppt/paths.py"], (
        f"基底路徑不只一份：{_owners(pat)}")


def test_the_known_folder_lookups_are_defined_in_exactly_one_place():
    r"""桌面與「開始功能表」的問法只准一份。

    ⚠️ 這三支曾經在 `tools/make_shortcut.py` 裡另有一份、與藍本幾乎逐字相同——
    幾乎相同正是最壞的情況：漂開的那一天沒有任何徵狀，只有某一邊的捷徑會建到
    OneDrive 沒接管的那個舊桌面上，使用者看不到、也不會知道要去哪裡找。"""
    for name in ("known_folder", "desktop_dir", "start_menu_programs_dir"):
        owners = _owners(re.compile(rf"^def {name}\(", re.M))
        assert owners == ["pdf2ppt/paths.py"], f"{name}() 有 {len(owners)} 份：{owners}"


# --------------------------------------------------------------------------- #
#  四、落地位置 ≠ 顯示身分
# --------------------------------------------------------------------------- #
def test_the_landing_folder_name_is_not_the_title_or_the_taskbar_identity():
    """三個字串、三種概念，**字面值哪天撞在一起也不可以併成一份**。

    落地位置改了要使用者重畫一次快取；視窗標題是純顯示，改成別的中文完全不影響
    磁碟；工作列身分改了會讓釘選的那顆與執行中的視窗分家。併成一份的話，哪天把
    標題改掉就會順手把快取搬家——資產還在磁碟上、程式卻說沒有，**兩個位置都存在**，
    連「檔案不見了」都不會發生。
    ⚠️ 姊妹專案 MP4-2-SRT 三者同值，那是巧合不是設計（在那邊寫「這個字串只能有
    一份」的測試會當場紅，就是因為這件事）。"""
    assert paths.APP_DIR_NAME != G.APP_TITLE, "落地資料夾名被併進視窗標題了"
    assert paths.APP_DIR_NAME != G.APP_ID, "落地資料夾名被併進工作列身分了"
    owners = _owners(re.compile(re.escape(f'"{paths.APP_DIR_NAME}"')))
    assert owners == ["pdf2ppt/paths.py"], f"資料夾名的字面值不只一份：{owners}"
