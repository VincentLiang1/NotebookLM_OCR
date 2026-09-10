"""指路不得腐爛:CLAUDE.md 對 `docs/dev/` 的,以及全 repo 寫在註解裡的。

2026-08-06 把 CLAUDE.md 從 75,689 字元瘦到 18,414(它每開一次新對話就整份
載入,而八成的內容只有動到特定領域時才用得到)。細節搬進 `docs/dev/`,
CLAUDE.md 留摘要 + 「動到 X 之前先讀 Y」的指路。

**這個作法的唯一風險是指路斷掉**:檔案被改名或刪掉時,CLAUDE.md 那一行
會變成指向不存在的檔案,而症狀是**知識安靜地消失**——以後的人(或以後的
我)不會知道那裡本來有東西,只會重蹈一次已經記載過的覆轍。所以用測試釘住。
"""
import ast
import io
import re
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = ROOT / "CLAUDE.md"
DEV_DOCS = ROOT / "docs" / "dev"

# `CLAUDE.md` 的字元上限:**這裡是唯一正典**。⚠️ 這個數字以前散在三個地方(這條
# assert、那條測試的 docstring、`CLAUDE.md` 自己那句),而 2026-08-29 還查出三個
# repo 的 `docs/dev/documentation.md` 各抄了一份**三個 repo**的值——每一份都只有
# 自己那一格是對的,另外兩格停在放寬之前。根治的做法是「會變的值只留在它自己驗
# 得出來的地方」:那份共用規範裡的數字全部拿掉,散文那句由下面那條測試釘著。
CLAUDE_MD_MAX = 38_000

# 不掃的目錄:產物、快取、輸出。把打包/輸出目錄掃進來只會讓每一條發現
# 都被報兩次
_SKIP_DIRS = {
    ".git", ".venv", "dist", "build", "logs", "output",
    "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules",
}
# repo 內的相對路徑寫法(反斜線也認:文件裡慣用 `docs\dev\collaboration.md`)。
# ⚠️ **`pdf2ppt` 要在清單裡**:這個 repo 的程式碼不住在 `src/`,漏了它就等於
# 對所有「指向某支模組」的指路完全失明
_PATH_RE = re.compile(
    r"(?<![\w./\\-])"
    r"((?:scripts|tests|src|pdf2ppt|tools|docs|packaging|skills|data)[/\\][\w./\\-]*[\w-]"
    r"\.(?:py|ps1|md|txt|npz|json|wav|bat|toml|yaml|yml|jpg|png))"
)
# 已知的例外,每一條都要有理由。⚠️ **這裡只放「不是指路」的東西**
# (別的 repo 的路徑、示範用的假檔名);真的斷掉的指路要修,不是寫進來
_ALLOW: dict[str, str] = {
    # squircle 皮膚的色票是從 meeting-scribe 那個 repo 抄過來的,指的是**它的**
    # 檔案、不是本專案的(見 pdf2ppt_gui_2.py 的 SKINS)。寫全路徑才找得到。
    "src/meeting_scribe/ui_style.py": "別的 repo(meeting-scribe)的路徑:色票來源",
}


def _pointers() -> set[str]:
    return set(re.findall(r"`(docs/[\w/.-]+\.md)`", CLAUDE.read_text(encoding="utf-8")))


def test_every_pointer_in_claude_md_resolves():
    """CLAUDE.md 提到的每一份 docs 都要真的存在。"""
    missing = [p for p in _pointers() if not (ROOT / p).is_file()]
    assert not missing, f"CLAUDE.md 指向不存在的檔案:{missing}"


def test_every_dev_doc_is_reachable_from_claude_md():
    """反向:`docs/dev/` 裡的每一份都要有人指得到它。

    沒有入口的文件等於不存在——它不會被載入、也不會有人想到要去讀。"""
    pointed = _pointers()
    orphans = [
        f"docs/dev/{p.name}" for p in DEV_DOCS.glob("*.md")
        if f"docs/dev/{p.name}" not in pointed
    ]
    assert not orphans, f"沒有從 CLAUDE.md 指到的文件:{orphans}"


@pytest.mark.parametrize("doc", sorted(DEV_DOCS.glob("*.md")), ids=lambda p: p.name)
def test_dev_doc_says_when_to_read_it(doc):
    """每一份都要在檔頭講清楚「什麼時候該讀」——沒有這句話的話,它只是
    一份不知道何時該打開的長文。"""
    head = doc.read_text(encoding="utf-8")[:800]
    assert "之前請先讀" in head or "之前先讀" in head


def _prose(path: Path) -> list[tuple[int, str]]:
    """檔案裡「寫給人看的字」:`.py` 取註解與 docstring,`.md` 取全文。

    ⚠️ **`.py` 刻意不掃一般字串常值**:測試裡到處是現編的假路徑(`a.md`、
    `other.md`、docs 底下那些——hook 與個資掃描的測試拿它們當資料),掃進來
    就得養一份越長越沒人看的白名單,而白名單本身遲早腐爛到把真的斷鏈也
    蓋掉。指路本來就寫在註解與 docstring 裡,守這兩處就夠:這條測試要抓的
    `make_fixture.ps1`(從未存在過,卻在 `-m slow` 的整合測試裡指路了一個多
    月)兩處寫法就有一處是註解。"""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".md":
        return [(1, text)]
    out: list[tuple[int, str]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                out.append((tok.start[0], tok.string))
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    out.append((getattr(node, "lineno", 1), doc))
    except (SyntaxError, tokenize.TokenError):  # pragma: no cover - 壞檔另有測試守
        pass
    return out


def _scan_targets() -> list[Path]:
    return sorted(
        p for pat in ("*.py", "*.md") for p in ROOT.rglob(pat)
        if not any(part in _SKIP_DIRS for part in p.parts)
    )


def test_no_comment_points_at_a_file_that_does_not_exist():
    """全 repo 的註解與文件都不得指向不存在的檔案。

    上面那條只看 CLAUDE.md,而斷掉的指路不挑地方長:2026-08-19 查出整合
    測試從第一個 commit 起就寫著「先執行 `make_fixture.ps1` 產生測試音檔」,
    **那支腳本從未存在過**——於是唯一一條端到端的真實音檔測試永遠是 skip,
    而 `uv run pytest` 的輸出只會多一個不起眼的 `s`,沒有人會發現那條防線
    其實是空的。

    ⚠️ **要提到一個不存在的檔案時,別寫成完整路徑**(這條 docstring 自己也
    照做):這個檢查分不出「指路」與「講述某個檔不存在」,寫全了就是拿自己
    的敘述再餵它一條假斷鏈。

    這種斷鏈比「檔案被改名」更難察覺:改名至少還有一份舊檔在歷史裡,而
    指向從未存在的東西,連 `git log --diff-filter=D` 都查不出來。"""
    bad: dict[str, list[str]] = {}
    for path in _scan_targets():
        for lineno, chunk in _prose(path):
            for m in _PATH_RE.finditer(chunk):
                rel = m.group(1).replace("\\", "/")
                if rel in _ALLOW or "__pycache__" in rel or (ROOT / rel).exists():
                    continue
                # 註解取到的是單行,docstring 則整段共用起點行號
                line = lineno + chunk[: m.start()].count("\n")
                bad.setdefault(rel, []).append(
                    f"{path.relative_to(ROOT).as_posix()}:{line}")
    assert not bad, "指路到不存在的檔案(修掉它,或連同理由寫進 _ALLOW):\n" + "\n".join(
        f"  {rel}  ← {'、'.join(where)}" for rel, where in sorted(bad.items())
    )


def test_claude_md_stays_small():
    """CLAUDE.md 是**每次開新對話都整份載入**的東西,不是百科全書。

    ⚠️ **這個上限不是技術限制**(跟 context window、API 都無關),是**注意力
    預算**:太長的 CLAUDE.md 會開始被略讀,而它每一條都是踩過坑才寫下來的
    ——守不住注意力,寫再多也等於沒寫。

    ⚠️ **上限是各 repo 各自校準的,不是普世常數**(姊妹專案 meeting-scribe 與
    MP4-2-SRT 是 18,000)。本 repo 定在 38,000,理由是它的主體與那兩個不同:

    2026-08-23 已經做過一次抽離(使用者指示),81 條規則的完整理由、門檻與反例
    全搬進 `docs/spec/`,這裡只留**規則本身、關鍵門檻與程式指路**。剩下的六段
    「不變量索引」合計 17,067 字元、佔全檔 61%,平均 **208 字元/條**——那已經
    是「規則+門檻+⚠️陷阱」的最小形。要壓進 18,000 只剩 91 字元/條,等於砍掉
    門檻數字與陷阱警告,而**那兩樣正是它每次載入的理由**:這些是不變量,改任何
    一處都不得違反,不像領域文件可以「動到才讀」。

    ⚠️ **2026-08-26 從 28,000 放寬到 30,000**(使用者指示)。判準沒有鬆,是**被
    實際成長逼到的**:那天要加一條工作列的規則時,檔案已經 27,988、**只剩 12 個
    字元**,那一條於是被壓到只剩「不可搶前景」加一個 §指路,原本要寫的函式名與
    COM 陷阱全部塞不進去。⚠️ **上限開始咬掉的是規則本身的內容、而不是贅字時,
    那就是該重新校準的訊號**——繼續硬守只會讓新規則寫成看不懂的暗號,那比長一點
    更傷注意力。⚠️ 成長的是**不變量索引**(15,168 → 17,067),不是別的:六段以外
    的部分 10,921 字元,比 2026-08-23 的 10,943 還少。

    ⚠️ **2026-08-27 再從 30,000 放寬到 32,000**(使用者指示)。訊號與上一次是同一
    個形狀,而且這次連續發生兩輪:當天把按鈕改成膠囊,兩輪改動**各被上限逼著砍一次
    規則本身的內容**——第一輪砍掉 hover 底色的對比度數字(3.65:1)與曲線指數那句
    歷史教訓,第二輪砍掉「主要焦點只有一個」這個決策理由、皮膚資產的「深淺 × 五種
    縮放共十組」、以及「三個藍**各有各的用途**」的前半句。每一刀都是為了騰出位置
    塞新規則,不是因為判斷那些不該留。⚠️ 放寬之後那五處**已經還原**;真正該砍的
    (同一段裡重複第二次的檔案路徑、被新做法推翻的半句話)留在砍掉的狀態——**放寬
    不是把砍過的東西全部倒回來**。

    ⚠️ **2026-08-27 晚上做了一次抽離:30,077 → 28,199 字元,上限不動。** 使用者指示
    「壓縮,看有哪些能抽離」。動的**不是**不變量索引(16,849 → 16,731,只改了一條把量測
    敘事還給 `docs/spec/06-流程-顏色、蓋板與裁切.md` 的),而是 2026-08-26 之後長出來的
    那 2,300 字元 GUI 內容——它原本擠在「常用指令」章裡的一個 3,079 字元段落,現在是
    獨立的「GUI」章。⚠️ **判準是「這條在還沒開始改 GUI 的時候就可能被違反嗎」**:會的
    (只露五個選項、沒有「專案位置」選擇、介面字型不可與輸出統一、整個畫面只有一顆線框
    鈕、收合鈕就是卡片標題列)留在 `CLAUDE.md`;**只有動到那幾支檔案才咬得到**的機制
    (皮膚產生器那八條的症狀、膠囊的圖高對照表、色票三階的細節、捷徑與工作列的其餘陷阱)
    只留**名字＋一句指路**,症狀與判別碼回 `docs/dev/windows-環境與入口.md` §5–§5.11。
    ⚠️ **搬之前逐條驗過那些話真的已經在 dev/spec 裡**(消失的識別字 38 個、中文片語 79
    條全數對得上)——沒驗就搬等於把知識刪掉,而且是安靜地刪。順帶併掉三處講了兩遍的
    (README 手抄 argparse、「轉換品質沒有自動測試」、輸出字型 YaHei)。

    ⚠️ **同一晚的 code review 抓到這一輪砍過頭,已全部補回。** 上一筆 commit(9b6c9ca)
    正是「上限放寬到 32,000,還原被上限逼掉的五處規則內容」,而 79 分鐘後的壓縮把其中
    五處又砍掉:`SQ_N`=2.0 與「5.0 在卡片那麼大一塊上看起來幾乎直角」、`cta_fg`／`cta_hi`
    的 4.5:1 與 3.65:1、皮膚資產「深淺 × 五種縮放共十組」、「進度條一直是這樣」、以及膠囊
    驗收的更正(「皮膚開／關逐格相同」不再成立)。⚠️ **判準:壓縮不得覆蓋上一輪才拍板的
    還原**——那五處不是贅字,是前一輪逐條判斷過該留的,而「這條該不該留」的答案不會因為
    換一個人壓縮就改變。連帶查出最後那條更正刪掉之後,`docs/dev/windows-環境與入口.md`
    §5.10 的驗收 2 變成孤兒(它還寫著「高度仍然要一格不差」,而膠囊化之後皮膚開／關的
    高度在定義上就不可能相同,實測視窗 549 vs 529)——已一併改掉。

    ⚠️ **2026-08-28 再從 32,000 放寬到 35,000**(使用者指示)。訊號的形狀與前兩次一樣,
    但這次是**先撞牆才發現的**:那一輪要加兩條啟動提速的護欄(`.vbs` 先走 `.venv` 的
    pythonw、載 tkdnd 延到視窗出來之後),寫完發現只剩 **82 個字元**,於是先壓掉五處
    **已經在 `docs/` 有正本**的細節(winkit 那條的三句理由、守門誤報的後果、一個日期、
    兩處「講得更具體」)才塞得進去,塞完**餘裕只剩 2 個字元**。
    ⚠️ **與前兩次的差別要講清楚**:這次被上限逼掉的是**贅述、不是規則本身**,所以那個
    訊號比前兩次弱。真正的訊號是**餘裕 2 個字元**這件事——它的意思是「下一條規則不管
    內容是什麼都寫不進去」,而那正是前兩次放寬要避免的狀態,只是這次提早一步看到。
    ⚠️ 放寬之後**只還原兩個量測數字**(省 35～40ms、tkdnd 44～85ms):值不值得為那條快速
    路徑冒「環境沒同步」的險,要看省多少才判斷得出來。其餘五處留在壓縮狀態——**放寬不是
    把砍過的東西全部倒回來**。

    ⚠️ **2026-09-10 從 35,000 放寬到 38,000**(使用者指示「把上限往上帶一階」)。
    ⚠️ **這一次的訊號形狀與前三次都不同,要分開記**:前三次都是「加規則時撞牆、被
    上限逼著砍規則本身」,這一次是**先做完一輪抽離、才發現抽離救不了**。使用者說
    「壓縮」,那一輪把上次瘦身(31,682)之後長出來的 3,272 字元裡的**敘事**壓掉
    **869(26%)**,每一處都先驗過 `docs/` 真的有正本才搬——**做完仍然只剩 915 的餘裕**。
    ⚠️ **意思是「抽離的產能」已經追不上「規則的增速」。** 08-25 到 08-28 那三次,每次
    都還找得到「擠在別章的一整段 GUI 內容」那種肥肉;這一次逐條套「這條在還沒打開那支
    檔案時就可能被違反嗎」掃過全檔,能搬的都搬完了,剩下的每一句都在守一個具體的失效。
    ⚠️ **量化的那一半**:不變量索引 **80 條、17,558 字元(51.5%)**,其中帶 deck 頁碼的
    實例只有 **272 字元**,而且四處全在承載門檻的理由(trans p11 的 0.3381、
    `RING_INSIDE_MIN` 的 0.069／0.151)——砍掉它們省不到 1%,卻正好拆掉「不可以放寬這個
    門檻」的證據。其餘 16,527 比 2026-08-26 的 10,921 多了 5,600,長的是 **GUI 章**
    (0 → 約 4,000,08-27 到 08-29 那批 UI 決策)與協作、環境兩章——**那是真的長出了規則,
    不是贅字堆積**。
    ⚠️ 規矩不變:**放寬不是把砍過的東西倒回來**——這一輪壓掉的 869 全部留在壓縮狀態
    (它們在 `docs/` 有正本,而且是逐條驗過的)。

    ⚠️ **放寬不等於不守**:新增的規則一樣要先問「這條沒每次載入會不會做錯」
    ——會做錯才留在這裡,否則進 `docs/spec/` 對應章。判準沒有變:長篇內容放
    `docs/spec/` 與 `docs/dev/`,這裡只留摘要、指路,以及「**用到時才知道就
    來不及**」的那幾條。分層規範見 `docs/dev/documentation.md`。"""
    n = len(CLAUDE.read_text(encoding="utf-8"))
    assert n < CLAUDE_MD_MAX, (
        f"CLAUDE.md 已經 {n:,} 字元。長篇內容請搬進 docs/spec/ 或 docs/dev/ 並在這裡留指路"
    )


def test_claude_md_states_its_own_cap():
    """`CLAUDE.md` 裡自稱的上限,要等於真正在守的那個。

    2026-08-29 補。這條守的是同一類錯誤裡**唯一在 repo 內驗得到的那半**:改了
    `CLAUDE_MD_MAX` 卻忘了改 `CLAUDE.md` 那句散文。⚠️ **跨 repo 的一致守不住**
    ——每個 repo 的測試都看不到別的 repo,所以那半的解法不是加稽核,是把跨 repo
    的數字整個消滅掉(見 `docs/dev/documentation.md` 那條通則)。

    ⚠️ **要求 `CLAUDE.md` 一定要寫出數字,不是「有寫才驗」**:寫成「有字元上限,
    測試守著」那種沒有數字的句子,這條測試會靜靜地變成 no-op——而那正是它要防的
    失效方式(規則還在、守衛沒了,沒有任何徵狀)。"""
    said = re.findall(r"([\d,]{5,7})\s*字元?上限", CLAUDE.read_text(encoding="utf-8"))
    assert said, (
        "CLAUDE.md 要寫出自己的上限數字(例:「(18,000 字元上限)」)——"
        "這條測試靠它比對,沒有數字就等於沒有守衛"
    )
    wrong = sorted({s for s in said if int(s.replace(",", "")) != CLAUDE_MD_MAX})
    assert not wrong, (
        f"CLAUDE.md 裡寫的上限是 {wrong},而真正在守的是 {CLAUDE_MD_MAX:,}"
    )


def test_claude_md_states_how_many_rules_it_carries():
    """「以下 NN 條規則」那個數字,要等於「不變量索引」裡真正的條數。

    2026-09-10 補,與上面那條同一個形狀(自稱的數字 vs 真正的數字),而它是**先
    漂了才補的**:那句話寫著 83 條,實際數出來是 80。⚠️ **漂的方向永遠是往多**
    ——搬走或併掉規則的人不會想到回頭改這個總數,而加規則的人反而會。

    ⚠️ **這個數字不是裝飾**:它是「這份檔在守幾件事」的唯一速讀指標,也是判斷
    「該不該再放寬上限」時分母那一半(見 `test_claude_md_stays_small` 的
    docstring:平均 208 字元/條就是這樣算出來的)。分子量得到、分母用猜的話,
    那整套校準就是空的。"""
    text = CLAUDE.read_text(encoding="utf-8")
    said = re.findall(r"以下\s*(\d+)\s*條規則", text)
    assert said, (
        "CLAUDE.md 的不變量索引要寫出自己有幾條(例:「以下 80 條規則」)——"
        "這條測試靠它比對,沒有數字就等於沒有守衛"
    )
    body = text.split("### 不變量索引", 1)[1].split("\n### ", 1)[0]
    actual = sum(1 for ln in body.splitlines() if ln.startswith("- "))
    wrong = sorted({s for s in said if int(s) != actual})
    assert not wrong, (
        f"CLAUDE.md 自稱 {wrong} 條規則,不變量索引裡實際數到 {actual} 條"
    )
