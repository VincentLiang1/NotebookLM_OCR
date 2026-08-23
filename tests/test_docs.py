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
from pathlib import Path

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
RULE_DOCS = {"CLAUDE.md": CLAUDE_MD,
             "docs/系統規格.md": (ROOT / "docs" / "系統規格.md").read_text(
                 encoding="utf-8"),
             **{f"docs/spec/{n}": t for n, t in SPEC_TEXT.items()}}

MODULES = ["pdf2ppt.style", "pdf2ppt.blocks", "pdf2ppt.builder",
           "pdf2ppt.ocr", "pdf2ppt.cli", "pdf2ppt.models", "pdf2ppt.render"]

# 刻意提到、但程式裡已經沒有的符號：文件談的就是「它被刪掉」這件事，名字正是
# 那則教訓的價值所在。⚠️ 這份白名單本身就是絆索——往裡面加一個名字很便宜，而
# 每加一個就少守一個符號，所以加之前先問「這真的是歷史記述，還是我剛改壞的
# 指路？」
#   _dilate：2026-08-23 被不繞回的 _grow 取代，零呼叫者卻留了半天
HISTORICAL = {"_dilate"}

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
    for text in RULE_DOCS.values():
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
    assert not problems, "死指路：\n  " + "\n  ".join(problems)


def test_documented_symbols_exist_in_the_code():
    """規則逐條都寫著「見 `module.py` 的 `_some_function`」。

    重構改了名字而沒改文件時，那句指路就再也帶不到人——這正是把規則寫下來的
    整個用意所在。"""
    src = "\n".join(p.read_text(encoding="utf-8")
                    for p in (ROOT / "pdf2ppt").glob("*.py"))
    src += "\n" + GUI_PY
    problems = []
    cited = set()
    for text in RULE_DOCS.values():
        cited |= set(re.findall(r"`(_[a-z][a-z0-9_]{3,})`", text))
    assert HISTORICAL <= cited, (
        f"白名單裡有文件已經不提的符號，該刪了：{sorted(HISTORICAL - cited)}")
    for hit in cited - HISTORICAL:
        if not re.search(rf"\b(?:def|class)\s+{re.escape(hit)}\b|"
                         rf"^\s*{re.escape(hit)}\s*[:=]", src, re.M):
            problems.append(hit)
    assert not problems, (
        "文件提到但程式裡找不到定義的符號：" + "、".join(sorted(problems)))


def test_every_cli_flag_is_in_the_readme_option_table():
    """`cli.py` 的 argparse 是正典，README 的選項表是手抄的。

    漏抄的旗標等於不存在——使用者只讀 README。"""
    missing = [f for f in sorted(_cli_long_flags()) if f"`{f}" not in README_MD]
    assert not missing, f"README 選項表漏了：{missing}"


def test_every_cli_flag_has_a_gui_control():
    """GUI 的選項清單同樣是手抄 argparse 的，而且**已經漂移過一次**
    （`--lang` 在 CLI 與 README 都有、GUI 完全沒有，2026-08-16 補上）。

    兩個刻意的例外寫在這裡，不是寫在註解裡——例外要能被讀到才算數。"""
    # --cover 是預設值，GUI 只需要 --no-cover 這一個開關；輸出路徑由 GUI
    # 自己的存檔對話框決定，不經 --output
    deliberate = {"--cover", "--output"}
    missing = [f for f in sorted(_cli_long_flags() - deliberate)
               if f'"{f}"' not in GUI_PY]
    assert not missing, f"pdf2ppt_gui_2.py 沒有對應控制項的旗標：{missing}"


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
    for pointer in ("docs/dev/collaboration.md", "docs/spec/", "docs/系統規格.md"):
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

