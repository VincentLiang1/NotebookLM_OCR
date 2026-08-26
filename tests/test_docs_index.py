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
    MP4-2-SRT 是 18,000)。本 repo 定在 30,000,理由是它的主體與那兩個不同:

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

    ⚠️ **放寬不等於不守**:新增的規則一樣要先問「這條沒每次載入會不會做錯」
    ——會做錯才留在這裡,否則進 `docs/spec/` 對應章。判準沒有變:長篇內容放
    `docs/spec/` 與 `docs/dev/`,這裡只留摘要、指路,以及「**用到時才知道就
    來不及**」的那幾條。分層規範見 `docs/dev/documentation.md`。"""
    n = len(CLAUDE.read_text(encoding="utf-8"))
    assert n < 30_000, (
        f"CLAUDE.md 已經 {n:,} 字元。長篇內容請搬進 docs/spec/ 或 docs/dev/ 並在這裡留指路"
    )
