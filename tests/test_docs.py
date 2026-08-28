"""文件與程式碼的一致性。

`CLAUDE.md` 每次對話都會自動載入，裡面的數字與指路是 agent 讀到的**第一手
資訊**——錯了不會有人發現，而沒有人會為了查一個門檻把整份讀一遍。2026-08-23
那輪 code review 一次抓出五處與程式不符或自相矛盾的敘述（投影半徑公式、
`nat_close` 門檻、chromatic 退回的新條件、已解決卻仍寫著「需使用者裁示」的
限制、同一段裡一句說移除一句說還在的閘門），全是人工發現的。這一支把機器
驗得到的那幾類釘死。

⚠️ 2026-08-23 之後**規則的完整理由搬進了 `docs/spec/`**，CLAUDE.md 只留規則
與指路——所以下面幾條都同時掃這兩邊，兩邊漂了都要紅。

守的是五類**會靜默腐爛**的東西：

1. **文件引用的常數值** —— `CJK_INK_RATIO` 就這樣錯了很久：commit 4c97794 把
   程式改成 0.875，`CLAUDE.md` 還寫著 0.91（這一支的第一次執行就抓到它）。
2. **指路** —— 檔名、模組、函式名。改名或刪除之後，指路變成死巷，而讀的人
   要 grep 過才知道。
3. **CLI 旗標的三方一致** —— `cli.py` 的 argparse 是正典，`README.md` 的選項
   表與 `pdf2ppt_gui_2.py` 的控制項都是**手抄**的。CLAUDE.md 記著它已經漂移
   過一次（`--lang` 在 CLI 與 README 都有、GUI 完全沒有，2026-08-16 補上）。
4. **「量過而否決的路」索引** —— 索引只寫「見『某某標題』」，被指的那一條改
   了標題或被刪掉，索引就悄悄變成假的，而索引正是因為沒人會翻全檔才存在。
5. **規格書的章號與地圖** —— `docs/spec/00` 的文件地圖是手抄目錄的，加章漏改
   地圖、或刪檔漏改地圖，兩個方向都要紅。

⚠️ 這支測試**不驗語意**：它不知道某條規則講得對不對，只知道文件裡那個數字
與程式裡那個數字是不是同一個。語意的真值仍然只有一個來源——渲染圖的目視比對
（見 `CLAUDE.md` 的「驗證」章）。
"""
import importlib
import re
import subprocess
import tomllib
from pathlib import Path, PurePosixPath

import winkit

from pdf2ppt import brand

ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = ROOT / "docs" / "spec"

CLAUDE_MD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
README_MD = (ROOT / "README.md").read_text(encoding="utf-8")
CLI_PY = (ROOT / "pdf2ppt" / "cli.py").read_text(encoding="utf-8")
GUI_PY = (ROOT / "pdf2ppt_gui_2.py").read_text(encoding="utf-8")

SPEC_FILES = sorted(SPEC_DIR.glob("*.md"))
SPEC_TEXT = {p.name: p.read_text(encoding="utf-8") for p in SPEC_FILES}

# 會被「常數值」與「符號指路」兩條掃到的全部文件：規則搬家之後，正典的整理版
# 分散在這幾份，任何一份漂掉都一樣害人。
#
RULE_DOCS = {"CLAUDE.md": CLAUDE_MD,
             # ⚠️ 架構導讀 2026-08-24 從 docs 頂層搬進 docs/dev/，但
             # **必須留在這一份名單裡**：底下的 SYMBOL_DOCS 會整個 docs/dev/
             # 加掃，可是「死指路」那條刻意不吃 dev（dev 有示範用的假路徑）。
             # 而這一份正是模組名最多的文件——漏了它就等於搬完之後沒人守它。
             "docs/dev/architecture.md": (
                 ROOT / "docs" / "dev" / "architecture.md").read_text(
                     encoding="utf-8"),
             **{f"docs/spec/{n}": t for n, t in SPEC_TEXT.items()}}

# 常數值與符號指路**另外**加掃 `docs/dev/`（2026-08-24）：spec 正文改成技術中立、
# 實作名詞集中進「附錄-現行實作對照」之後，符號指路會同時住在那一章與 `docs/dev/`。
# 上面那份名單原本身兼二職，等於預設「符號只住在 spec」——那個預設會讓「把實作
# 細節搬進 dev」這件對的事看起來像在拆守備。
#
# ⚠️ **只加掃這兩條，不加掃「死指路」那條**：`docs/dev/` 裡有刻意寫出來的**示範
# 路徑**（平台變體的目錄、別的 repo 的範例），它們本來就不該存在。真正的檔案路徑
# 由 `tests/test_docs_index.py` 全 repo 掃，那一條要求副檔名、不會誤咬目錄示範。
SYMBOL_DOCS = {**RULE_DOCS,
               **{f"docs/dev/{p.name}": p.read_text(encoding="utf-8")
                  for p in sorted((ROOT / "docs" / "dev").glob("*.md"))}}

# ⚠️ `tools.make_icon` 也在名單裡：圖示的門檻（HALO、SMALL_MAX）跟管線的門檻
# 一樣是校準結果、一樣寫進了 docs/dev，少了它那些數字就沒人守。
# ⚠️ **共用包 `winkit` 也在名單裡**（2026-08-28 接上時補的）：皮膚、路徑、Windows
# 整合那幾支整批搬過去之後，`docs/dev/` 引用的門檻（`SKIN_SCALE_TOL`、`SQ_N`…）
# 有一半住在那裡。少了它們，那些數字就從「被釘住」變成「沒有人守」——而症狀是
# 文件寫著一個早就改掉的值，讀的人照著錯的值推理。
MODULES = ["pdf2ppt.style", "pdf2ppt.blocks", "pdf2ppt.builder",
           "pdf2ppt.ocr", "pdf2ppt.cli", "pdf2ppt.models", "pdf2ppt.render",
           "tools.make_icon", "tools.make_skin",
           "winkit.skin", "winkit.skingen", "winkit.paths", "winkit.palette",
           "winkit.winui",
           # GUI 也在裡面：它的 SELF_REPORTED_RC 是與「啟動.vbs」講好的暗號，
           # CLAUDE.md 引用了那個數字。import 它只會定義常數與類別（Tk 是
           # App() 才建的），不會開視窗。
           "pdf2ppt_gui_2"]

# 刻意提到、但程式裡已經沒有的符號：文件談的就是「它被刪掉」這件事，名字正是
# 那則教訓的價值所在。⚠️ 這份白名單本身就是絆索——往裡面加一個名字很便宜，而
# 每加一個就少守一個符號，所以加之前先問「這真的是歷史記述，還是我剛改壞的
# 指路？」
#   _dilate：2026-08-23 被不繞回的 _grow 取代，零呼叫者卻留了半天
#   _restore_height_after_collapse：2026-08-25 併進 _fit_window。文件記的是
#     「為什麼從『減法還原』走到『每次重量 reqheight』」，那段沿革的價值正在
#     於舊名字——沒有它，讀者無法把 docs/dev §5 第 3 點與 git 歷史對起來
HISTORICAL = {"_dilate", "_restore_height_after_collapse"}

# 文件引用常數的四種寫法：`NAME`=V、`NAME`(V)、`NAME`（V）、`NAME = V`
_CONST_CITED = [
    re.compile(r"`([A-Z][A-Z0-9_]{2,})`\s*[=（(]\s*([0-9]+(?:\.[0-9]+)?)"),
    re.compile(r"`([A-Z][A-Z0-9_]{2,})\s*=\s*([0-9]+(?:\.[0-9]+)?)`"),
]
# 「見『某某』」形式的指路（否決索引用的）
_SEE_SECTION = re.compile(r"見「([^」]{4,60})」")
# 規格書章節檔名（章號 + 中文標題），用來雙向比對目錄與地圖
_SPEC_FILE = re.compile(r"(\d{2}-[^\s`)）]+?\.md)")


def _modules():
    return {name: importlib.import_module(name) for name in MODULES}


def _cited_constants() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for text in SYMBOL_DOCS.values():
        for pat in _CONST_CITED:
            for m in pat.finditer(text):
                out.setdefault(m.group(1), set()).add(m.group(2))
    return out


def _cli_long_flags() -> set[str]:
    return set(re.findall(r'add_argument\("(--[a-z0-9-]+)"', CLI_PY))


def _spec_numbers() -> dict[int, str]:
    out = {}
    for p in SPEC_FILES:
        out[int(p.name[:2])] = p.name
    return out


def test_claude_md_cites_some_constants():
    """抓法本身要先活著。

    文件的寫法一旦改變（例如把 `` `X`=1 `` 改寫成「X 設成 1」），下面那條會
    變成「零個常數全部通過」的空綠燈——那比沒有測試更糟，因為它看起來在守
    東西。"""
    cited = _cited_constants()
    assert len(cited) >= 10, f"只抓到 {sorted(cited)}，文件的引用寫法變了？"


def test_claude_md_constant_values_match_the_code():
    """文件引用的常數值要等於程式裡的值。

    這些數字是校準結果，每一個背後都有一段實測；文件寫錯的那一刻，下一個人
    就會照著錯的值推理，而程式跑起來完全正常。"""
    mods = _modules()
    problems = []
    for name, cited in sorted(_cited_constants().items()):
        owners = [n for n, m in mods.items() if hasattr(m, name)]
        if not owners:
            problems.append(f"{name}：文件引用了，但程式裡沒有這個常數")
            continue
        actual = getattr(mods[owners[0]], name)
        if not any(abs(float(v) - float(actual)) < 1e-9 for v in cited):
            problems.append(
                f"{name}：文件寫 {sorted(cited)}，{owners[0]} 是 {actual}")
    assert not problems, "文件與程式的常數不一致：\n  " + "\n  ".join(problems)


def test_docs_do_not_point_at_files_that_do_not_exist():
    """文件裡 `` `something.py` `` / `` `docs/...` `` 這類指路要指得到東西。

    死指路與「刻意留的歷史記述」長得一模一樣，分得出來的只有剛改完的那個
    人——所以要在他還在的時候紅。"""
    known = {p.name for p in ROOT.rglob("*.py") if ".venv" not in p.parts}
    problems = []
    for doc, text in (("README.md", README_MD), *RULE_DOCS.items()):
        for hit in set(re.findall(r"`([A-Za-z_][\w./-]*\.py)`", text)):
            if Path(hit).name not in known:
                problems.append(f"{doc} 指向不存在的 {hit}")
        # 章節檔名含全形標點（顏色、蓋板與裁切），所以吃到反引號為止；
        # 另允許 `docs/spec/06` 這種只寫章號的簡寫（指得到就算數）
        for hit in set(re.findall(r"`((?:docs|tools)/[^`]+)`", text)):
            if (ROOT / hit).exists():
                continue
            stem = ROOT / hit
            if stem.parent.is_dir() and any(stem.parent.glob(stem.name + "*")):
                continue
            problems.append(f"{doc} 指向不存在的 {hit}")
        # ⚠️ `..\某某` 是**隔壁那個資料夾**（共用包）。程式已經不看這種字面值了
        # （改讀 `pyproject.toml` 的 `[tool.uv.sources]`），但敘述照樣會過期：
        # 共用包搬家或改名之後，這幾句還在教人去看一個不存在的地方。
        for hit in set(re.findall(r"\.\.[\\/]([A-Za-z0-9_.-]+)", text)):
            if not (ROOT.parent / hit).exists():
                problems.append(f"{doc} 指向不存在的隔壁資料夾 ../{hit}")
    assert not problems, "死指路：\n  " + "\n  ".join(problems)


def test_documented_symbols_exist_in_the_code():
    """規則逐條都寫著「見 `module.py` 的 `_some_function`」。

    重構改了名字而沒改文件時，那句指路就再也帶不到人——這正是把規則寫下來的
    整個用意所在。"""
    # ⚠️ `tools/` 也要掃（2026-08-26 補的，與 MODULES 那份名單同一個理由）：
    # 圖示與皮膚的產生器同樣被 docs/dev 逐條指路，而它們的私有函式漏在外面時，
    # 那句指路照樣帶不到人——`_sq_points` 就是這樣才被發現沒人守。
    src = "\n".join(p.read_text(encoding="utf-8")
                    for p in (*(ROOT / "pdf2ppt").glob("*.py"),
                              *(ROOT / "tools").glob("*.py"),
                              # ⚠️ **共用包也要掃**（2026-08-28）：皮膚載入器與它的
                              # 幾何整批搬進 `winkit` 之後，`docs/dev/` 那幾條指路
                              # 指的是那邊的函式。把它排除掉的話那些指路就沒人守，
                              # 而「指路帶不到人」正是把規則寫下來的整個用意所在。
                              *Path(winkit.__file__).parent.glob("*.py")))
    src += "\n" + GUI_PY
    problems = []
    cited = set()
    for text in SYMBOL_DOCS.values():
        cited |= set(re.findall(r"`(_[a-z][a-z0-9_]{3,})`", text))
    assert HISTORICAL <= cited, (
        f"白名單裡有文件已經不提的符號，該刪了：{sorted(HISTORICAL - cited)}")
    for hit in cited - HISTORICAL:
        # 三種定義形式：def/class、模組層級常數，以及**實例屬性**
        # （`self._boot_stderr = ...`）。第三種是 2026-08-24 補的：文件指得到
        # 實例屬性是正常的，少了它會逼著文件改寫成 `self._x` 只為了閃過測試，
        # 那等於用「規避」換「通過」，守備範圍反而變小
        if not re.search(rf"\b(?:def|class)\s+{re.escape(hit)}\b|"
                         rf"^\s*{re.escape(hit)}\s*[:=]|"
                         rf"\bself\.{re.escape(hit)}\s*[:=][^=]", src, re.M):
            problems.append(hit)
    assert not problems, (
        "文件提到但程式裡找不到定義的符號：" + "、".join(sorted(problems)))


def test_every_cli_flag_is_in_the_readme_option_table():
    """`cli.py` 的 argparse 是正典，README 的選項表是手抄的。

    漏抄的旗標等於不存在——使用者只讀 README。"""
    missing = [f for f in sorted(_cli_long_flags()) if f"`{f}" not in README_MD]
    assert not missing, f"README 選項表漏了：{missing}"


def test_every_cli_flag_has_a_gui_control():
    """GUI 只露出**使用者拍板的那五個**選項（2026-08-25 指示），其餘一律吃
    `cli.py` 的 argparse 預設值。

    這支測試本來是「每個旗標都要有 GUI 控制項」——當時它抓到過真的漂移
    （`--lang` 在 CLI 與 README 都有、GUI 完全沒有，2026-08-16 補上）。選項砍
    到五個之後那個述詞不再成立，但**守備範圍不可以跟著消失**，所以改成雙向釘：
    露出來的五個必須真的在 GUI 裡，而**沒露出來的每一個都要在下面這份名單上**
    ——`cli.py` 新增旗標時就會紅一次，逼人回答「這個要不要給使用者看」。

    刻意的取捨寫在這裡、不是寫在註解裡——例外要能被讀到才算數。"""
    # 介面上真的有控制項的五個
    exposed = {"--pages", "--keep-watermark", "--no-s2t", "--cover",
               "--keep-tiny-text"}
    # 刻意不給 GUI 的：
    #   --output      由 GUI 自己的存檔對話框決定
    #   --no-cover    自 2026-08-24 起是預設值，只需要 --cover 這個反向開關
    #   --dpi/--font/--min-score  校準值（200 DPI ＋ YaHei 是唯一校準過的作業點）
    #   --no-bold/--force-bold/--fast  會整份換掉粗體／辨識的判別依據
    #   --device      auto 已經是 DirectML > CUDA > CPU
    #   --lang        預設就是中英
    #   --merge-lines/--debug  開發用的
    hidden = {"--output", "--no-cover", "--dpi", "--font", "--min-score",
              "--no-bold", "--force-bold", "--fast", "--device", "--lang",
              "--merge-lines", "--debug"}
    flags = _cli_long_flags()
    assert exposed <= flags, (
        f"GUI 露出的旗標在 cli.py 裡不見了：{sorted(exposed - flags)}")
    missing = [f for f in sorted(exposed) if f'"{f}"' not in GUI_PY]
    assert not missing, f"pdf2ppt_gui_2.py 沒有對應控制項的旗標：{missing}"
    undecided = flags - exposed - hidden
    assert not undecided, (
        f"cli.py 新增了旗標卻沒人決定它在 GUI 露不露：{sorted(undecided)}"
        "（要露就加控制項並列進 exposed，不露就列進 hidden）")


def test_the_partial_exit_code_is_the_same_number_in_both_places():
    """降級的離開碼存兩份：`cli.py` 是正典，`pdf2ppt_gui_2.py` 是手抄的。

    （2026-08-25 之前是三份，第三份在拖放用的 `轉檔.bat` 裡；那個檔連同
    `啟動（顯示訊息）.bat` 一起刪掉了——使用者要交付面單純。）

    不 import 的理由寫在 GUI 自己的註解裡（不想為了一個整數把整組相依拉進啟動
    路徑）。手抄就會漂移，而**這一種漂移是沉默的**：號碼對不上時，有頁面降級的
    那一趟會被報成單純的「完成」，或者反過來被報成「失敗」——兩種都會讓使用者
    做錯決定，而且畫面上不會有任何一句話提示他號碼對不上。"""
    m = re.search(r"^PARTIAL_RC = (\d+)$", CLI_PY, re.M)
    assert m, "cli.py 的 PARTIAL_RC 不見了（改名了就要一起改這支測試）"
    rc = m.group(1)
    g = re.search(r"^PARTIAL_RC = (\d+)$", GUI_PY, re.M)
    assert g and g.group(1) == rc, (
        f"pdf2ppt_gui_2.py 的 PARTIAL_RC 是 {g and g.group(1)}，"
        f"cli.py 是 {rc}")


def test_the_cancelled_exit_code_is_the_same_number_in_both_places():
    """「使用者按了停止」的離開碼同樣存兩份（`cli.py` 是正典、GUI 手抄）。

    漂移的後果和 `PARTIAL_RC` 同一種、而且同樣沉默：號碼對不上時，使用者按下
    停止會看到一個「失敗（代碼 4）」的紅字結果列，而那一趟其實完全照他說的做。
    順便釘住它不可以撞上 0（沒有檔案卻報成功）、1（他自己的決定被報成失敗），
    以及 PARTIAL_RC。"""
    m = re.search(r"^CANCELLED_RC = (\d+)$", CLI_PY, re.M)
    assert m, "cli.py 的 CANCELLED_RC 不見了（改名了就要一起改這支測試）"
    rc = int(m.group(1))
    part = re.search(r"^PARTIAL_RC = (\d+)$", CLI_PY, re.M)
    assert rc not in (0, 1, int(part.group(1)) if part else -1), (
        f"CANCELLED_RC 不可以是 {rc}：那是別的結果已經佔用的號碼")
    g = re.search(r"^CANCELLED_RC = (\d+)$", GUI_PY, re.M)
    assert g and int(g.group(1)) == rc, (
        f"pdf2ppt_gui_2.py 的 CANCELLED_RC 是 {g and g.group(1)}，cli.py 是 {rc}")


def test_the_gui_reads_the_words_cli_actually_prints():
    """GUI 的進度條與結果列是**解析 `cli.py` 的 stdout** 來的。

    ⚠️ 這是手抄的輸出格式，不是 API：cli 改掉那幾行的長相，GUI 不會報錯，只會
    安靜地退回「不定長度進度條 + 一句英文原文」——正是那種沒有人會發現的壞法。
    所以把兩邊的字面值釘在一起。"""
    # 每頁一行的 head：`page 7 (3/15): …`
    assert 'head = f"page {idx + 1} ({n}/{len(page_indices)})"' in CLI_PY, (
        "cli.py 每頁那一行的格式變了，pdf2ppt_gui_2.py 的 _PAGE_RE 要跟著改")
    for literal, where in (('"WARNING: "', "_WARN_PREFIX"),
                           ('"Loading OCR engine', "_LOADING_PREFIX")):
        assert literal.strip('"') in CLI_PY, (
            f"cli.py 不再印 {literal}，GUI 的 {where} 就沒有東西可以認")
    # 降級的三種下場（_fallback_slide 的回傳值 + render 失敗那條）
    for how in ("dropped", "image only", "partial slide"):
        assert f'"{how}"' in CLI_PY, (
            f"cli.py 不再回 {how!r}，GUI 的 _DEGRADE_ZH 要跟著改")
        assert f'"{how}"' in GUI_PY, (
            f"pdf2ppt_gui_2.py 的 _DEGRADE_ZH 少了 {how!r}，"
            "那一種降級會以英文原文顯示在結果列上")


def test_the_self_reported_exit_code_matches_the_launcher():
    """「失敗我自己已經跳過訊息框了」這個暗號存兩份：`pdf2ppt_gui_2.py` 的
    `SELF_REPORTED_RC` 與「啟動.vbs」的 `RC_SELF_REPORTED`。

    ⚠️ **這種漂移是沉默的，而且會往壞的方向倒**：號碼對不上時，好的那一半只是
    多跳一個框（看得見）；壞的那一半是 `.vbs` 把**別人回的**結束碼當成暗號，那
    一趟真正的失敗就一句話都不會顯示。所以順便釘住「不可以是 0/1/2」——**2 正是
    「連 .py 都打不開」時直譯器自己回的值**（只複製了 `.vbs`、GUI 檔不在的情況），
    而那正是最需要跳框的一次。"""
    g = re.search(r"^SELF_REPORTED_RC = (\d+)$", GUI_PY, re.M)
    assert g, "pdf2ppt_gui_2.py 的 SELF_REPORTED_RC 不見了（改名要一起改這支測試）"
    rc = int(g.group(1))
    assert rc not in (0, 1, 2), (
        f"SELF_REPORTED_RC 不可以是 {rc}：Python 直譯器自己就會回這個值")
    vbs = (ROOT / "啟動.vbs").read_text(encoding="cp950")
    v = re.search(r"^Const RC_SELF_REPORTED = (\d+)$", vbs, re.M)
    assert v and int(v.group(1)) == rc, (
        f"啟動.vbs 的 RC_SELF_REPORTED 是 {v and v.group(1)}，"
        f"pdf2ppt_gui_2.py 是 {rc}")


def test_the_launcher_guard_lists_files_that_really_exist():
    r"""「啟動.vbs」在跑 uv 之前先檢查關鍵檔案在不在（2026-08-27，作法移植自姊妹
    專案 MP4-2-SRT）：漏掉檔案時 uv 與 Python 吐的是英文訊息，說不出「你少複製了
    東西」，而那正是「整包複製搬家」這個部署方式唯一的失敗模式。

    ⚠️ **這一支守的是誤報**：守門列的路徑必須真的存在於一份完整的專案裡，否則
    每一次**正常**的啟動都會跳「少了必要的檔案」、程式再也開不起來——而它是使用者
    唯一的入口。把某支檔案改個名就足以造成，且改的人不會想到要去看 `.vbs`。

    ⚠️ 另一個方向也釘住兩件事：守門檢查的必須就是 `.vbs` **真的會去跑的那個檔**
    （走 `target` 那個變數，不是另外手打一次檔名），而且**不可以伸手進 `pdf2ppt`
    套件裡**——套件在不在由 GUI 的 `is_project_dir()`／`fail_no_project()` 判，它
    講得更具體（會把資料夾路徑一起印出來）。兩份清單遲早只會改一邊。"""
    vbs = (ROOT / "啟動.vbs").read_text(encoding="cp950")
    target = re.search(r'^target\s*=\s*here & "\\([^"]+)"', vbs, re.M)
    assert target, "啟動.vbs 的 target 那一行變了（改名要一起改這支測試）"

    checked = set(re.findall(r'fso\.BuildPath\(here, "([^"]+)"\)', vbs))
    assert "fso.FileExists(target)" in vbs, (
        "守門沒有檢查 .vbs 真正會去跑的那個檔（或改成手打檔名了）")
    checked.add(target.group(1))
    # 抓法本身要先活著：正規表示式漂掉時 checked 會變成空集合，而空集合讓下面
    # 兩條全部通過——那比沒有測試更糟，因為它看起來在守東西
    assert len(checked) >= 2, f"只抓到 {sorted(checked)}，守門的寫法變了？"

    missing = sorted(n for n in checked if not (ROOT / n).exists())
    assert not missing, (
        f"啟動.vbs 的守門列了專案裡沒有的檔案 {missing}——正常安裝也會被擋下來")
    inside = sorted(n for n in checked if n.replace("\\", "/").startswith("pdf2ppt/"))
    assert not inside, (
        f"守門伸進 pdf2ppt 套件裡了 {inside}：那是 fail_no_project() 的工作")


def _uv_local_sources():
    """`pyproject.toml` 的 `[tool.uv.sources]` 裡以**相對路徑**相依進來的資料夾。

    這是「共用資料夾在哪裡」的**唯一真值**：uv 只吃字面值，所以那一行非寫死在
    那裡不可——反過來說，別處就一份都不准再抄（下面三支釘著）。"""
    with (ROOT / "pyproject.toml").open("rb") as fh:
        sources = tomllib.load(fh)["tool"]["uv"]["sources"]
    return {v["path"] for v in sources.values()
            if isinstance(v, dict) and "path" in v}


def test_every_local_uv_source_really_sits_where_pyproject_says():
    r"""`[tool.uv.sources]` 列的每個相對路徑都要真的指得到一個專案。

    ⚠️ **這一支守的是誤報**，理由與上面那支守門完全一樣：「啟動.vbs」的守門
    改成**讀這一份**（2026-08-28）之後，這裡寫錯就等於清單寫錯——**每一次正常
    的啟動**都會跳「少了必要的檔案」，而它是使用者唯一的入口。`uv sync` 也會
    跟著失敗，但它吐的是英文的路徑錯誤，說不出少了什麼。"""
    rels = _uv_local_sources()
    assert rels, "[tool.uv.sources] 一個相對路徑相依都不剩了？守門會整個空掉"
    bad = sorted(r for r in rels if not (ROOT / r / "pyproject.toml").is_file())
    assert not bad, f"pyproject.toml 指到的共用資料夾不在那裡：{bad}"


def test_the_entry_files_do_not_write_down_where_the_shared_folder_lives():
    r"""共用資料夾搬家或改名時**只改 `pyproject.toml` 那一行**（使用者
    2026-08-28 要求「只改一個地方就改好」）。所以兩個入口檔裡不可以有第二份
    字面值：「啟動.vbs」用讀的（`LocalSources`），「安裝.bat」那句提示改成不
    提名字（批次檔沒有可靠的 TOML 讀法——用 `findstr` 抓會抓到
    `[tool.pytest.ini_options]` 的 `pythonpath = ["."]`，2026-08-28 實測）。

    ⚠️ **手抄一份的失效是沉默的**：搬完家 `.vbs` 的守門還在檢查舊路徑，於是
    每一次**正常**啟動都跳「少了必要的檔案」；`.bat` 那句則是搬完家還在教使用者
    去找一個已經不存在的資料夾。兩邊都不會有人來報，而改的人不會想到要看它們。"""
    for name in ("啟動.vbs", "安裝.bat"):
        text = (ROOT / name).read_text(encoding="cp950")
        for rel in sorted(_uv_local_sources()):
            for shape in (rel, rel.replace("/", "\\"), PurePosixPath(rel).name):
                assert shape not in text, (
                    f"{name} 又寫死了一份「{shape}」——共用資料夾在哪裡是"
                    " pyproject.toml 的 [tool.uv.sources] 的事，這裡要嘛用讀的、"
                    "要嘛不提")


def test_the_readme_calls_the_shared_folder_by_its_current_name():
    """`README.md` 的「資料夾複製不完整時」那一段**指名道姓**講隔壁那個資料夾。

    程式已經不看名字了（改讀 `[tool.uv.sources]`），但**給人看的那一句還是要對**
    ——搬完家或改完名之後，那句話會繼續教使用者去找一個不存在的資料夾，而使用者
    正是在「東西不見了」的時候才讀它。名字寫在 `pyproject.toml`，這裡只要求
    README 講的是**現在那一個**。"""
    missing = sorted(PurePosixPath(rel).name for rel in _uv_local_sources()
                     if PurePosixPath(rel).name not in README_MD)
    assert not missing, (
        f"README 沒提到現在的共用資料夾 {missing}——它那一段還在講舊名字？")


def test_the_launcher_parses_the_same_sources_a_real_toml_parser_sees(tmp_path):
    r"""「啟動.vbs」的 `LocalSources` 是一支手寫的迷你剖析器（VBScript 沒有 TOML
    解析器，而守門必須在 Python 起來之前就知道答案）。這一支拿**真正的** TOML
    解析器跟它對答案，而且跑的是**出貨的那一份**——把那支函式原封不動抽出來餵給
    `cscript`，不是在這裡照它的規則再寫一次（再寫一次就等於兩份會各自漂的程式）。

    ⚠️ **它的失效方向是漏報，而漏報是沉默的**：把 `[tool.uv.sources]` 改寫成它
    看不懂的形狀（多行表、`path` 跟鍵不同行），守門就靜靜地少檢查一項，使用者
    退回去看 uv 的英文錯誤——不會有任何徵狀。2026-08-28 實測過一個真的坑：不分
    區段地找 `path =` 會抓到 `[tool.pytest.ini_options]` 的 `pythonpath = ["."]`。"""
    vbs = (ROOT / "啟動.vbs").read_text(encoding="cp950")
    assert "kits = LocalSources(fso, projFile)" in vbs, (
        "守門沒有去讀 pyproject.toml（或改了寫法）")
    assert "EnvFresh(fso, here, kits)" in vbs, (
        "EnvFresh 沒有吃守門算好的那一份：兩處各讀一次就是兩份會漂的路徑")
    fn = re.search(r"^Function LocalSources\(.*?^End Function$", vbs, re.M | re.S)
    assert fn, "啟動.vbs 的 LocalSources 不見了（改名要一起改這支測試）"

    # ⚠️ 探針寫進 pytest 的 tmp_path、不落在專案裡（驗證產物要清乾淨那條）
    probe = tmp_path / "probe.vbs"
    driver = "\r\n".join([
        "Option Explicit",
        'Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")',
        "WScript.Echo LocalSources(fso, WScript.Arguments(0))",
        "", fn.group(0), ""])
    probe.write_bytes(driver.encode("cp950"))
    done = subprocess.run(
        ["cscript", "//nologo", str(probe), str(ROOT / "pyproject.toml")],
        capture_output=True, text=True, encoding="cp950", errors="replace")
    assert done.returncode == 0, f"cscript 跑不起來：{done.stderr}"
    seen = {s.replace("\\", "/") for s in done.stdout.strip().split("\t") if s}
    assert seen == _uv_local_sources(), (
        f"啟動.vbs 抓到 {sorted(seen)}，pyproject.toml 實際上是 "
        f"{sorted(_uv_local_sources())}——守門會漏檢查沒抓到的那幾個")


def test_the_launcher_keeps_a_way_back_to_uv():
    r"""「啟動.vbs」2026-08-28 起先跑 `.venv\Scripts\pythonw.exe`，`uv` 只在走不通時
    才出場（省掉 `uv run` 解析專案、比對 lock 的 35～40ms）。

    ⚠️ **那兩道退路就是這個做法的全部安全性**：`uv run` 順手做掉的「環境沒同步就
    自動補起來」，換成直接叫 `pythonw` 之後沒有人做了。事前那道（`EnvFresh`：`.venv`
    要比 `pyproject.toml`／`uv.lock`／共用包的 `pyproject.toml` 都新）擋的是「相依改了
    沒 sync」；事後那道（`FALLBACK_SECS`：很快就非正常結束＝GUI 根本沒開起來，用 uv
    再跑一次）擋的是「`.venv` 被整包複製到一台沒有同一版 Python 的機器」——後者事前
    那道看不出來，檔案都在、時間也對。

    ⚠️ **拿掉任何一道都不會有徵狀**：快速路徑在開發機上永遠成功，壞掉的是別人的機器，
    而症狀是「雙擊之後跳一個英文的 ModuleNotFoundError」或「什麼都沒發生」。"""
    vbs = (ROOT / "啟動.vbs").read_text(encoding="cp950")
    assert r"\.venv\Scripts\pythonw.exe" in vbs, "快速路徑不見了（或改了寫法）"
    assert vbs.count('"uv run pythonw"') >= 2, (
        "uv 的退路少了一處：事前判定走不通、事後重跑各要用到一次")
    assert "Function EnvFresh" in vbs, "事前那道（EnvFresh）不見了"
    assert "FALLBACK_SECS" in vbs and "Elapsed(t0)" in vbs, (
        "事後那道（跑不到 FALLBACK_SECS 就失敗 -> 用 uv 再跑一次）不見了")


def test_the_launcher_message_box_uses_the_app_name():
    """「啟動.vbs」的訊息框標題是 `pdf2ppt/brand.py` 那個名字的**短版手抄**。

    ⚠️ 這一份沒辦法收攏：VBScript 讀不到 Python，而那支又必須在**環境還沒建起來**
    的時候就能講話（它的存在理由就是「藏掉主控台之後錯誤往哪裡去」）。所以改用
    「必須是正本的前綴」來釘——短版是刻意的（訊息框標題不需要「轉檔工具」那三個
    字），但它得是**同一個名字**。

    ⚠️ 漂移是沉默的：改了程式的名字而沒改 `.vbs`，使用者唯一會看到的失敗訊息會
    掛著一個他從沒聽過的舊名字，而那是他判斷「這個框是誰跳的」的唯一線索。"""
    vbs = (ROOT / "啟動.vbs").read_text(encoding="cp950")
    m = re.search(r'^Const APP_TITLE = "([^"]+)"', vbs, re.M)
    assert m, "啟動.vbs 的 APP_TITLE 那一行變了（改名要一起改這支測試）"
    assert brand.APP_TITLE.startswith(m.group(1)), (
        f"啟動.vbs 的訊息框標題是「{m.group(1)}」，"
        f"brand.py 的 APP_TITLE 是「{brand.APP_TITLE}」")


def test_the_readme_calls_the_shortcut_by_its_real_name():
    """README 告訴使用者桌面上會出現哪一顆圖示，那個名字是**手抄**的。

    抄錯或改名沒跟上時，使用者會在桌面上找一顆不存在的圖示——而他手上沒有第二
    條線索。`tools/make_shortcut.py` 用的就是 `brand.APP_TITLE`，兩邊釘在一起。"""
    assert brand.APP_TITLE in README_MD, (
        f"README 沒有提到捷徑的真名「{brand.APP_TITLE}」")


def test_rejected_paths_index_points_at_real_sections():
    """「量過而否決的路」那一章只寫「見『某某標題』」。

    被指的那一條改了措辭或被刪掉，索引就悄悄變成假的——而索引正是因為沒人
    會翻完全部規則才存在的。規則搬進 `docs/spec/` 之後，被指的標題可能在
    CLAUDE.md，也可能在規格書裡，兩邊都算數。"""
    head = "## 量過而否決的路"
    assert head in CLAUDE_MD, "「量過而否決的路」章不見了"
    index = CLAUDE_MD.split(head, 1)[1]
    body = CLAUDE_MD.split(head, 1)[0] + "\n".join(SPEC_TEXT.values())
    targets = set(_SEE_SECTION.findall(index))
    assert targets, "索引裡一條「見『…』」都沒有，抓法或寫法變了？"
    missing = [t for t in sorted(targets) if t not in body]
    assert not missing, f"索引指向文件裡找不到的標題：{missing}"


def test_claude_md_still_points_at_the_long_form_docs():
    """規則是「結論一句 + 可 grep 的指路」，所以指路本身不能掉。

    2026-08-23 把 78 條規則搬進 `docs/spec/` 之後，這幾條指路是**唯一**能把
    人從自動載入的 CLAUDE.md 帶到完整理由的東西——掉了就等於那些反例不存在。"""
    for pointer in ("docs/dev/collaboration.md", "docs/spec/",
                    "docs/dev/architecture.md"):
        assert pointer in CLAUDE_MD, f"CLAUDE.md 少了指向 {pointer} 的那句"


def test_spec_chapters_are_numbered_without_gaps():
    """章號要從 00 連號到最後一章。

    缺號通常是「檔案改名時打錯」或「刪了一章沒重編」，而讀者是照號碼互相
    引用的（§4、§11.2）——斷號的那一刻所有交叉引用都變成猜謎。"""
    nums = _spec_numbers()
    assert nums, "docs/spec/ 底下一個章節都沒有"
    expect = set(range(0, max(nums) + 1))
    assert set(nums) == expect, (
        f"章號不連續：有 {sorted(nums)}，缺 {sorted(expect - set(nums))}")


def test_spec_h1_matches_the_file_number():
    """每一章的 H1 要與檔名的章號一致。

    改檔名沒改標題（或反過來）之後，讀者在檔案裡看到的號碼與他點進來的路徑
    對不上，交叉引用就開始互相打架。"""
    problems = []
    for n, name in sorted(_spec_numbers().items()):
        h1 = SPEC_TEXT[name].split("\n", 1)[0]
        assert h1.startswith("# "), f"{name} 的第一行不是 H1：{h1!r}"
        if n == 0:      # 總覽是書名頁，不編號
            continue
        if not h1.startswith(f"# {n}. "):
            problems.append(f"{name} 的 H1 是 {h1!r}，章號應為 {n}")
    assert not problems, "章號與 H1 不一致：\n  " + "\n  ".join(problems)


def test_spec_map_lists_every_chapter_and_only_real_ones():
    """`00-總覽與閱讀指南.md` 的文件地圖是手抄目錄的，兩個方向都要釘。

    漏列 → 新章沒人找得到；多列 → 指向已刪的檔案。這兩種錯都不會有人在
    寫程式時發現。"""
    nums = _spec_numbers()
    overview = SPEC_TEXT[nums[0]]
    listed = set(_SPEC_FILE.findall(overview))
    actual = {name for n, name in nums.items() if n != 0}
    assert not (actual - listed), f"地圖漏列：{sorted(actual - listed)}"
    assert not (listed - actual), f"地圖多列了不存在的章節：{sorted(listed - actual)}"


def test_claude_md_points_at_every_spec_chapter():
    """CLAUDE.md 的不變量索引每一節都要指得到對應章節。

    這是「規則在這裡、理由在那裡」這個安排的支點：CLAUDE.md 是唯一自動載入
    的檔，它沒指到的章節等於不存在。09/10/11 由「驗證」與「協作方式」章帶到，
    也一併算。"""
    missing = [name for n, name in sorted(_spec_numbers().items())
               if n != 0 and name not in CLAUDE_MD]
    assert not missing, f"CLAUDE.md 沒有指向這些章節：{missing}"


def test_flow_chapters_say_when_to_read_them():
    """流程六章每一章開頭都要寫「動到 X 之前請先讀完這一章」。

    這是從 `meeting-scribe` 的 `docs/dev/*.md` 學來的：把「什麼時候該讀」
    **寫死在文件裡**，而不是指望讀的人自己判斷。一章規格沒人讀到，
    跟沒寫是一樣的。"""
    trigger = "之前請先讀完這一章"
    missing = [name for n, name in sorted(_spec_numbers().items())
               if 3 <= n <= 8 and trigger not in SPEC_TEXT[name]]
    assert not missing, f"這幾章沒寫「什麼時候該讀」：{missing}"


def test_the_map_counts_match_the_chapters():
    """§0.3 地圖的「條數」欄要等於該章實際的頂層規則數。

    2026-08-24 把六章改寫成技術中立時，順手把幾條合併（例如「不可要求並排」
    併進同列多數決那一條）、又把幾條從子條目提上來——**規則一條沒少，但地圖
    的 25/5/23 全部變成假的**，而且是稽核時才發現的。這正是本檔開頭說的
    「會靜默腐爛」：沒有人為了確認一個數字把整章數一遍。

    ⚠️ 數的是**頂層** `- **…**` 條目，巢狀子條目不另計（地圖自己也這樣寫）。
    合併或拆分規則時，地圖那一格要跟著改——這條測試就是逼你改的東西。"""
    nums = _spec_numbers()
    overview = SPEC_TEXT[nums[0]]
    problems = []
    for m in re.finditer(r"\|\s*`(\d{2})-[^`]+\.md`\s*\|\s*(\d+)\s*\|", overview):
        chapter, claimed = m.group(1), int(m.group(2))
        name = nums[int(chapter)]
        actual = len(re.findall(r"^- \*\*", SPEC_TEXT[name], re.M))
        if claimed != actual:
            problems.append(f"{name}：地圖寫 {claimed} 條，實際 {actual} 條")
    assert problems == [], ("地圖的條數與章節對不上："
                            + "".join("\n  " + p for p in problems))


def test_the_map_says_when_to_read_every_chapter():
    """§0.3 的文件地圖每一列都要有「什麼時候讀」。

    地圖是讀者第一眼看到的東西；只列檔名與內容的話，他要把十二章
    都點開才知道哪一章跟手上的事有關。"""
    nums = _spec_numbers()
    overview = SPEC_TEXT[nums[0]]
    problems = []
    for ln in overview.split('\n'):
        if not ln.startswith("| `") or ".md`" not in ln:
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[-1]:
            problems.append(ln[:60])
    assert not problems, ("地圖這幾列沒寫「什麼時候讀」："
                          + "".join('\n  ' + q for q in problems))

