"""文件與程式碼的一致性。

`CLAUDE.md` 每次對話都會自動載入，裡面的數字與指路是 agent 讀到的**第一手
資訊**——錯了不會有人發現，而它有 100KB 以上、沒有人會為了查一個門檻把整份
讀一遍。2026-08-23 那輪 code review 一次抓出五處與程式不符或自相矛盾的敘述
（投影半徑公式、`nat_close` 門檻、chromatic 退回的新條件、已解決卻仍寫著
「需使用者裁示」的限制、同一段裡一句說移除一句說還在的閘門），全是人工發現
的。這一支把機器驗得到的那幾類釘死。

守的是四類**會靜默腐爛**的東西：

1. **文件引用的常數值** —— `CJK_INK_RATIO` 就這樣錯了很久：commit 4c97794 把
   程式改成 0.875，`CLAUDE.md` 還寫著 0.91（這一支的第一次執行就抓到它）。
2. **指路** —— 檔名、模組、函式名。改名或刪除之後，指路變成死巷，而讀的人
   要 grep 過才知道。
3. **CLI 旗標的三方一致** —— `cli.py` 的 argparse 是正典，`README.md` 的選項
   表與 `pdf2ppt_gui_2.py` 的控制項都是**手抄**的。CLAUDE.md 記著它已經漂移
   過一次（`--lang` 在 CLI 與 README 都有、GUI 完全沒有，2026-08-16 補上）。
4. **「量過而否決的路」索引** —— 索引只寫「見『某某標題』」，被指的那一條改
   了標題或被刪掉，索引就悄悄變成假的，而索引正是因為沒人會翻全檔才存在。

⚠️ 這支測試**不驗語意**：它不知道某條規則講得對不對，只知道文件裡那個數字
與程式裡那個數字是不是同一個。語意的真值仍然只有一個來源——渲染圖的目視比對
（見 `CLAUDE.md` 的「驗證」章）。
"""
import importlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
README_MD = (ROOT / "README.md").read_text(encoding="utf-8")
CLI_PY = (ROOT / "pdf2ppt" / "cli.py").read_text(encoding="utf-8")
GUI_PY = (ROOT / "pdf2ppt_gui_2.py").read_text(encoding="utf-8")

MODULES = ["pdf2ppt.style", "pdf2ppt.blocks", "pdf2ppt.builder",
           "pdf2ppt.ocr", "pdf2ppt.cli", "pdf2ppt.models", "pdf2ppt.render"]

# 刻意提到、但程式裡已經沒有的符號：CLAUDE.md 談的就是「它被刪掉」這件事，
# 名字正是那則教訓的價值所在。⚠️ 這份白名單本身就是絆索——往裡面加一個名字
# 很便宜，而每加一個就少守一個符號，所以加之前先問「這真的是歷史記述，還是
# 我剛改壞的指路？」
#   _dilate：2026-08-23 被不繞回的 _grow 取代，零呼叫者卻留了半天（見「改壞
#            了重試，成功的那一刻就把失敗的殘骸一起清掉」那一條）
HISTORICAL = {"_dilate"}

# CLAUDE.md 引用常數的四種寫法：`NAME`=V、`NAME`(V)、`NAME`（V）、`NAME = V`
_CONST_CITED = [
    re.compile(r"`([A-Z][A-Z0-9_]{2,})`\s*[=（(]\s*([0-9]+(?:\.[0-9]+)?)"),
    re.compile(r"`([A-Z][A-Z0-9_]{2,})\s*=\s*([0-9]+(?:\.[0-9]+)?)`"),
]
# 「見『某某』」形式的指路（否決索引用的）
_SEE_SECTION = re.compile(r"見「([^」]{4,60})」")


def _modules():
    return {name: importlib.import_module(name) for name in MODULES}


def _cited_constants() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for pat in _CONST_CITED:
        for m in pat.finditer(CLAUDE_MD):
            out.setdefault(m.group(1), set()).add(m.group(2))
    return out


def _cli_long_flags() -> set[str]:
    return set(re.findall(r'add_argument\("(--[a-z0-9-]+)"', CLI_PY))


def test_claude_md_cites_some_constants():
    """抓法本身要先活著。

    CLAUDE.md 的寫法一旦改變（例如把 `` `X`=1 `` 改寫成「X 設成 1」），下面
    那條會變成「零個常數全部通過」的空綠燈——那比沒有測試更糟，因為它看起來
    在守東西。"""
    cited = _cited_constants()
    assert len(cited) >= 10, f"只抓到 {sorted(cited)}，CLAUDE.md 的引用寫法變了？"


def test_claude_md_constant_values_match_the_code():
    """CLAUDE.md 引用的常數值要等於程式裡的值。

    這些數字是校準結果，每一個背後都有一段實測；文件寫錯的那一刻，下一個人
    就會照著錯的值推理，而程式跑起來完全正常。"""
    mods = _modules()
    problems = []
    for name, cited in sorted(_cited_constants().items()):
        owners = [n for n, m in mods.items() if hasattr(m, name)]
        if not owners:
            problems.append(f"{name}：CLAUDE.md 引用了，但程式裡沒有這個常數")
            continue
        actual = getattr(mods[owners[0]], name)
        if not any(abs(float(v) - float(actual)) < 1e-9 for v in cited):
            problems.append(
                f"{name}：CLAUDE.md 寫 {sorted(cited)}，{owners[0]} 是 {actual}")
    assert not problems, "文件與程式的常數不一致：\n  " + "\n  ".join(problems)


def test_docs_do_not_point_at_files_that_do_not_exist():
    """文件裡 `` `something.py` `` / `` `docs/...` `` 這類指路要指得到東西。

    死指路與「刻意留的歷史記述」長得一模一樣，分得出來的只有剛改完的那個
    人——所以要在他還在的時候紅。"""
    known = {p.name for p in ROOT.rglob("*.py") if ".venv" not in p.parts}
    problems = []
    for doc, text in (("CLAUDE.md", CLAUDE_MD), ("README.md", README_MD)):
        for hit in set(re.findall(r"`([A-Za-z_][\w./-]*\.py)`", text)):
            if Path(hit).name not in known:
                problems.append(f"{doc} 指向不存在的 {hit}")
        for hit in set(re.findall(r"`((?:docs|tools)/[\w./-]+)`", text)):
            if not (ROOT / hit).exists():
                problems.append(f"{doc} 指向不存在的 {hit}")
    assert not problems, "死指路：\n  " + "\n  ".join(problems)


def test_documented_symbols_exist_in_the_code():
    """CLAUDE.md 逐條規則都寫著「見 `module.py` 的 `_some_function`」。

    重構改了名字而沒改文件時，那句指路就再也帶不到人——這正是本 repo 把規則
    寫進 CLAUDE.md 的整個用意所在。"""
    src = "\n".join(p.read_text(encoding="utf-8")
                    for p in (ROOT / "pdf2ppt").glob("*.py"))
    src += "\n" + GUI_PY
    problems = []
    cited = set(re.findall(r"`(_[a-z][a-z0-9_]{3,})`", CLAUDE_MD))
    assert HISTORICAL <= cited, (
        f"白名單裡有 CLAUDE.md 已經不提的符號，該刪了：{sorted(HISTORICAL - cited)}")
    for hit in cited - HISTORICAL:
        if not re.search(rf"\b(?:def|class)\s+{re.escape(hit)}\b|"
                         rf"^{re.escape(hit)}\s*[:=]", src, re.M):
            problems.append(hit)
    assert not problems, (
        "CLAUDE.md 提到但程式裡找不到定義的符號：" + "、".join(sorted(problems)))


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
    會翻完 100KB 才存在的。"""
    head = "## 量過而否決的路"
    assert head in CLAUDE_MD, "「量過而否決的路」章不見了"
    index = CLAUDE_MD.split(head, 1)[1]
    body = CLAUDE_MD.split(head, 1)[0]
    targets = set(_SEE_SECTION.findall(index))
    assert targets, "索引裡一條「見『…』」都沒有，抓法或寫法變了？"
    missing = [t for t in sorted(targets) if t not in body]
    assert not missing, f"索引指向 CLAUDE.md 裡找不到的標題：{missing}"


def test_claude_md_still_points_at_the_long_form_docs():
    """規則是「結論一句 + 可 grep 的指路」，所以指路本身不能掉。"""
    for pointer in ("docs/dev/collaboration.md",):
        assert pointer in CLAUDE_MD, f"CLAUDE.md 少了指向 {pointer} 的那句"
