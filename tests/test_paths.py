r"""落地位置的單一出處(共用包 `winkit.paths`):守「只有一份」與那兩個沒有訊息的失效。

2026-08-27 把散在兩處的路徑推導收攏進套件裡的一支路徑模組(藍本是 meeting-scribe
的同名模組,那邊踩過 OneDrive 重導與非 Windows 匯入兩個坑);2026-08-28 那一支**整支
搬進共用包 `winkit`**,本 repo 從此一份都不留。收攏本身沒有測試守不住——**散回去的
過程是安靜的**:下一個人要加一個落地位置時,就地再拼一次 `%LOCALAPPDATA%` 是最順手
的寫法,而多出來的那一份不會有任何徵狀,直到兩份對不上、使用者的快取憑空「消失」為止。

搬家之後守的東西換了一半:上游那幾條(重讀環境變數、退回不丟例外)由 winkit 自己的
測試守,這裡守的是**接線**與**這個 repo 沒有長回第二份**。

五類:

1. **接線接對了** —— `bind()` 給的 `repo_root` 是 `parents[1]`(flat layout),而
   姊妹專案是 `parents[2]`。⚠️ **差一層沒有任何錯誤訊息**:紀錄檔與捷徑會落在一個
   看起來很像、但少一層的路徑上。
2. **每次呼叫重讀環境變數** —— 定死在 import 時的話,測試就導不進 tmp,於是
   **在開發者自己的家目錄裡長出資料夾**(而且是在別人的機器上)。
3. **取不到就退回、不丟例外** —— 掛在底下的整條路是純加速,一個 `KeyError` 會從
   「皮膚裝不起來」一路炸到視窗開不起來。
4. **只有一份** —— 環境變數的讀取、三支已知資料夾函式、五個身分值的字面值,以及
   **共用包不准回頭 import 下游**(成環的話,壞掉的不是今天,是搬家那天)。
5. **身分只住在 `pdf2ppt/brand.py`** —— 2026-08-27 收攏:名字、用途那句話、工作列
   身分、落地資料夾名散在 GUI 與路徑模組裡,複製這個專案去做下一支 Windows AP 的人
   得自己去翻。收進 `brand.py` 之後那句承諾(「底下只有這一支必須改」)本身需要有人
   守,否則第二份會安靜地長回來。⚠️ 落地位置、視窗標題、工作列身分**是三個概念,
   字面值哪天撞在一起也不可以併成一份**(理由見 `brand.py` 的 `APP_DIR_NAME`)。
"""
import ast
import re
import types
from pathlib import Path

import pytest

import winkit
import pdf2ppt_gui_2 as G      # noqa: F401（載得起來本身就是一種驗收）
from winkit import skin as wskin
from pdf2ppt import brand
from winkit import paths

ROOT = Path(__file__).resolve().parents[1]
WINKIT = Path(winkit.__file__).resolve().parent
_SKIP = {".venv", "__pycache__", ".git", ".pytest_cache", "logs"}


def _py_files() -> list[Path]:
    return [p for p in ROOT.rglob("*.py")
            if not any(part in _SKIP for part in p.parts)]


def _owners(pattern: re.Pattern) -> list[str]:
    """哪幾支 `.py` 裡出現這個樣式（回 repo 相對路徑，排序過）。"""
    return sorted(p.relative_to(ROOT).as_posix() for p in _py_files()
                  if pattern.search(p.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- #
#  二、每次呼叫重讀環境變數
# --------------------------------------------------------------------------- #
def test_the_landing_root_follows_the_environment_at_call_time(monkeypatch, tmp_path):
    """⚠️ **不可以在 import 時把基底路徑定死**。

    症狀不是「測試比較難寫」：`monkeypatch` 導不動的話，任何會落檔的測試都會寫進
    **跑測試那個人自己的家目錄**，然後在別人的機器上留下一堆沒人知道哪來的資料夾。
    所以這裡連換兩次，第二次要跟著動。"""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "one"))
    assert paths.appdata_root() == tmp_path / "one" / brand.APP_DIR_NAME
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "two"))
    assert paths.appdata_root() == tmp_path / "two" / brand.APP_DIR_NAME, (
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
    assert root == Path.home() / ".cache" / brand.APP_DIR_NAME
    assert paths.repo_root() not in root.parents, "落地位置掉進專案資料夾裡了"
    assert Path.cwd() not in root.parents, "落地位置跟著當前工作目錄跑"


def test_the_skin_cache_hangs_off_the_landing_root(monkeypatch, tmp_path):
    """皮膚快取掛在落地根底下的 `skin` 那一格，位置本身走 `winkit.paths`。

    ⚠️ 覆寫用的環境變數要留著：皮膚快取的測試靠它把落地導進 tmp。⚠️ 它的名字是
    **組出來的**（`<brand.ENV_PREFIX>_SKIN_CACHE`），所以這裡順便釘住前綴——兩支 app
    同前綴的話，那個變數就會把對方的落地也一起導開。"""
    env = wskin.skin_cache_env()
    assert env.startswith(brand.ENV_PREFIX + "_"), (
        f"皮膚快取的覆寫變數 {env} 沒有走這支 app 的前綴：兩支 app 會互相導開對方")
    monkeypatch.delenv(env, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert wskin.skin_cache_root() == tmp_path / brand.APP_DIR_NAME / "skin"
    monkeypatch.setenv(env, str(tmp_path / "elsewhere"))
    assert wskin.skin_cache_root() == tmp_path / "elsewhere"


# --------------------------------------------------------------------------- #
#  三、層數、接線與相依
# --------------------------------------------------------------------------- #
def test_the_repo_root_is_the_folder_the_entry_points_live_in():
    r"""`bind()` 給的 `repo_root` 往上**一**層(姊妹專案是兩層,差在沒有 `src/`)。

    ⚠️ **這個值不可以讓共用包自己推**,它推不出來:src layout 要往上兩層、flat
    layout 只有一層,推的那個版本會在其中一邊安靜地算錯。⚠️ 層數數錯是**沒有訊息**
    的:捷徑與紀錄檔會落到一個看起來很像、但少一層的路徑上,而 `install_to()` 連錯誤
    都不會有——它自己會 `mkdir` 出來。所以這裡驗的不是層數本身,是**那一層底下真的
    擺著入口**。"""
    root = paths.repo_root()
    for name in ("pdf2ppt_gui_2.py", "pdf2ppt.py", "pyproject.toml", "啟動.vbs"):
        assert (root / name).exists(), f"repo_root() 底下沒有 {name}:層數數錯了"


def test_the_assets_travel_with_the_package_not_the_repo_root():
    r"""資產跟著**套件**走(`winkit.paths.assets_dir()` ＝ `package_dir()/assets`)。

    ⚠️ 2026-08-28 接共用包時 `assets/` 從 repo 根搬進 `pdf2ppt/`。⚠️ **指錯的下場
    是安靜降級**:皮膚載不到就回到系統原生長相(那正是設計),沒有人會收到訊息——所以
    這裡要真的去看那兩份資產在不在,不能只比路徑字串。"""
    assert paths.package_dir() == ROOT / "pdf2ppt"
    assert paths.assets_dir() == ROOT / "pdf2ppt" / "assets"
    assert (paths.assets_dir() / "icon.ico").is_file(), "捷徑與視窗的圖示不在"
    assert (paths.assets_dir() / "skin" / "sprites.json").is_file(), "皮膚資產不在"


def test_the_shared_package_never_imports_the_downstream():
    """⚠️ **共用包不准 import 任何下游。**

    下游要給的東西全部經過 `winkit.bind()` 這一個口(身分值、環境變數前綴、以及
    下游自己在磁碟上的位置)。反過來一旦成環,拆的就不只一行,而且**不是當場壞掉——
    是搬家那天才發現搬不動**。

    ⚠️ 掃的是**本專案的套件名**:winkit 有兩個下游,而它們互相不知道對方存在。"""
    bad = []
    for src in sorted(WINKIT.rglob("*.py")):
        tree = ast.parse(src.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            if any(n.split(".")[0] == "pdf2ppt" for n in names):
                bad.append(f"{src.name}:{node.lineno}")
    assert not bad, f"共用包回頭 import 了下游:{bad}——那是環,搬家那天才會發現"


def test_the_startup_path_pays_for_nothing_but_the_shared_package():
    r"""⚠️ **`pdf2ppt/__init__.py` 是 GUI 啟動路徑上的收費站。**

    它是共用包的注入點,所以**任何**子模組被 import 都會先經過它——包含 GUI 只為了
    拿三個字串而 import 的 `brand`、以及跑在安裝當下的 `tools/make_shortcut.py`。
    這裡多拉一個領域模組進來(`cli`、`ocr`、`style`…),等於把 numpy／pymupdf／
    python-pptx 那一整串塞進「雙擊到視窗出現」之間,而症狀只是「開得有點慢」。

    ⚠️ 白名單裡的三個都驗過:`winkit` 的 `__init__` 只有 pathlib 與 typing、
    `pdf2ppt.brand` 一行 import 都沒有(下一支測試釘著)。"""
    tree = ast.parse((ROOT / "pdf2ppt" / "__init__.py").read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert not node.level, "不要用相對 import:搬家時它是第一個斷的"
            mods.add((node.module or "").split(".")[0])
            if (node.module or "") == "pdf2ppt":
                assert {a.name for a in node.names} == {"brand"}, (
                    "注入點多讀了一個領域模組:啟動路徑會跟著把它的相依全載進來")
    assert mods <= {"pathlib", "winkit", "pdf2ppt"}, (
        f"啟動路徑長出新相依:{sorted(mods)}")


def test_binding_twice_with_a_different_identity_is_an_error():
    """⚠️ 同值冪等、**異值當場炸**:一個行程只服務一支 app。

    綁第二個身分一定是出事了(測試互相污染最常見),而那種錯的症狀會出現在**別的
    測試**上——落地位置、工作列身分、環境變數前綴全部跟著換,卻沒有任何人報錯。"""
    winkit.bind(brand, package_dir=paths.package_dir(),
                repo_root=paths.repo_root(),
                skin_generator=winkit.host().skin_generator)  # 同值:什麼都不該發生
    other = types.SimpleNamespace(
        APP_ID="X", APP_TITLE="X", APP_DESC="X", APP_DIR_NAME="X", ENV_PREFIX="X")
    with pytest.raises(RuntimeError):
        winkit.bind(other, package_dir=ROOT, repo_root=ROOT)
    assert winkit.host().app_id == brand.APP_ID, "炸完之後身分被換掉了"


# --------------------------------------------------------------------------- #
#  四、只有一份
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
    assert _owners(pat) == [], (
        f"基底路徑在本 repo 又長回來了：{_owners(pat)}——它住在共用包 winkit.paths")


def test_the_known_folder_lookups_are_defined_in_exactly_one_place():
    r"""桌面與「開始功能表」的問法只准一份。

    ⚠️ 這三支曾經在 `tools/make_shortcut.py` 裡另有一份、與藍本幾乎逐字相同——
    幾乎相同正是最壞的情況：漂開的那一天沒有任何徵狀，只有某一邊的捷徑會建到
    OneDrive 沒接管的那個舊桌面上，使用者看不到、也不會知道要去哪裡找。"""
    for name in ("known_folder", "desktop_dir", "start_menu_programs_dir"):
        owners = _owners(re.compile(rf"^def {name}\(", re.M))
        assert owners == [], (
            f"{name}() 在本 repo 又長回來了：{owners}——它住在共用包 winkit.paths")
        assert re.search(rf"^def {name}\(", (WINKIT / "paths.py").read_text("utf-8"),
                         re.M), f"共用包裡沒有 {name}()：這條測試守的是空氣"


# --------------------------------------------------------------------------- #
#  五、身分只有一份，而且只在 `pdf2ppt/brand.py`
# --------------------------------------------------------------------------- #
def test_the_brand_module_imports_nothing():
    """⚠️ **`brand` 自己一行 import 都不可以有**：它被 `paths`、GUI 與 `tools/` 三
    個方向讀，其中兩個（GUI 的啟動路徑、`paths` 這個要搬進共用包的通用層）各自
    都不能承受多一條相依——一個是「雙擊到視窗出現」之間多付一次，另一個是搬家
    那天成環。"""
    tree = ast.parse((ROOT / "pdf2ppt" / "brand.py").read_text(encoding="utf-8"))
    bad = [ast.unparse(n) for n in ast.walk(tree)
           if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert not bad, f"brand.py 開始 import 東西了：{bad}——它是 leaf，三個方向都讀它"


def test_the_identity_lives_in_one_file_the_next_project_edits():
    """**複製這個專案去做下一支 Windows AP 時，`pdf2ppt/` 底下只有 `brand.py` 必須
    改**（2026-08-27 收攏，作法與姊妹專案 MP4-2-SRT 同源）。

    ⚠️ 這一支守的是那句承諾本身。五個身分值一旦有人在別的模組裡「順手」寫死第二
    份，承諾就變成**假的**，而下一個專案會帶著上一個專案的身分出貨：工作列上兩支
    程式併成一顆按鈕、捷徑叫著舊名字、快取落在別人的資料夾底下。⚠️ 而這幾種都
    **不會有錯誤訊息**——兩個位置都存在，兩顆按鈕也都按得動。

    ⚠️ 抓的是**字面值**（`"…"`）不是變數名：轉呼叫（`APP_TITLE = brand.APP_TITLE`）
    不算第二份，寫死一句一模一樣的中文才算。"""
    names = ("APP_ID", "APP_TITLE", "APP_SUB", "APP_DESC", "APP_DIR_NAME",
             "ENV_PREFIX")
    for name in names:
        value = getattr(brand, name)
        owners = _owners(re.compile(re.escape(f'"{value}"')))
        assert owners == ["pdf2ppt/brand.py"], (
            f"{name} 的字面值不只一份：{owners}——brand.py 不再是唯一要改的地方")
    # 抓法本身要先活著：值變成拼接或多行字串時，上面那圈會變成「零個檔案全部
    # 通過」的空綠燈，而它看起來還在守東西
    assert len({getattr(brand, n) for n in names}) == len(names), (
        "有兩個身分值變成同一個字串了（見下一支測試）")


def test_the_landing_folder_name_is_not_the_title_or_the_taskbar_identity():
    """三個字串、三種概念，**字面值哪天撞在一起也不可以併成一份**。

    落地位置改了要使用者重畫一次快取；視窗標題是純顯示，改成別的中文完全不影響
    磁碟；工作列身分改了會讓釘選的那顆與執行中的視窗分家。併成一份的話，哪天把
    標題改掉就會順手把快取搬家——資產還在磁碟上、程式卻說沒有，**兩個位置都存在**，
    連「檔案不見了」都不會發生。
    ⚠️ 姊妹專案 MP4-2-SRT 三者同值，那是巧合不是設計（在那邊寫「這個字串只能有
    一份」的測試會當場紅，就是因為這件事）。"""
    assert brand.APP_DIR_NAME != brand.APP_TITLE, "落地資料夾名被併進視窗標題了"
    assert brand.APP_DIR_NAME != brand.APP_ID, "落地資料夾名被併進工作列身分了"


def test_the_consumers_all_read_the_brand_module():
    """三個方向都要真的讀到那一份，不是各自抄一次。

    ⚠️ `tools/make_shortcut.py` 這一半特別要釘：它 2026-08-27 之前是用**讀檔正規
    表示式**去 GUI 裡撈 `APP_TITLE`／`APP_ID` 的（那時 import GUI 會拉進 tkinter），
    抓不到就退回自己那份 `FALLBACK_*`——而 fallback 的值與正本一模一樣，所以 regex
    失效那天**捷徑照樣建得出來**，只是從此帶著一份不會再更新的舊值。姊妹專案
    MP4-2-SRT 做同一次收攏時真的踩到了（三條測試同時紅才發現）。改成 import 之後
    抓不到會當場 `ImportError`，不會安靜地換備援值。"""
    # GUI 直接讀的只剩畫面上看得到的那兩句。⚠️ **`APP_ID` 2026-08-28 起不再經過
    # 這裡**：宣告工作列身分的是共用包（`winui.set_app_user_model_id`），它從
    # `host()` 拿——GUI 自己不需要那個值，留著一個沒人用的 import 只會讓下一個人
    # 以為它還在做事。
    assert G.APP_TITLE == brand.APP_TITLE
    assert G.APP_SUB == brand.APP_SUB
    # 共用包那半:五個值全部經過 `bind()` 這一個口(見 `pdf2ppt/__init__.py`)
    host = winkit.host()
    assert (host.app_id, host.app_title, host.app_desc,
            host.app_dir_name, host.env_prefix) == (
        brand.APP_ID, brand.APP_TITLE, brand.APP_DESC,
        brand.APP_DIR_NAME, brand.ENV_PREFIX)
    # ⚠️ 釘的是**那三個落點各自的算式**，不是「檔案裡有出現 brand.APP_TITLE」：
    # 名字用了兩次（.lnk 的檔名、最後印給使用者看的那句），只比對名字的話，把檔名
    # 換成寫死的字串照樣是綠的——而使用者桌面上那顆的名字正是檔名決定的
    shortcut = (ROOT / "tools" / "make_shortcut.py").read_text(encoding="utf-8")
    for expr, what in (('f"{brand.APP_TITLE}.lnk"', "捷徑的檔名"),
                       ("brand.APP_DESC", "滑鼠停在圖示上那句")):
        assert expr in shortcut, f"tools/make_shortcut.py 的「{what}」沒有走 {expr}"
    # ⚠️ **寫進 .lnk 的工作列身分 2026-08-28 改由共用包直接從 `host()` 拿**：那顆
    # 捷徑正是工作列取圖示的地方，而它與程式自己宣告的 `APP_ID` **必須同值**——不同
    # 值的話，釘選到工作列的那顆與執行中的視窗會變成兩個各自獨立的按鈕，**而且不會
    # 有任何錯誤訊息**。改成由 `host()` 拿之後，那個「必須同值」在定義上就成立了，
    # 所以這裡改釘「共用包真的去讀了 `host().app_id`」。
    com = (WINKIT / "shortcut.py").read_text(encoding="utf-8")
    assert "_propvariant_str(host().app_id)" in com, (
        "共用包的 write_shortcut 沒有把 host().app_id 寫進 .lnk：工作列會沿用啟動鏈"
        "上游那支 wscript 的圖示，而畫面上不會有任何徵狀")
    assert "FALLBACK" not in shortcut, (
        "捷徑那支又長出備援值了：那條退路失效時完全沒有徵狀")
