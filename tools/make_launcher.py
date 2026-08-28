#!/usr/bin/env python3
r"""產生「啟動.vbs」（無黑框的那條啟動路徑）。

    uv run python tools/make_launcher.py

**骨架不在這裡**：`.vbs` 沒有 import，所以機制（`cmd /c` 的引號、暫存檔攔輸出、
MsgBox 的長度上限、守門、快速路徑與兩道退路）住在共用包 `winkit.launcher` 的樣板
裡，這一支只給**這個專案的欄位**——程式叫什麼、跑哪個檔、少了什麼要擋。

⚠️ **產物跟著程式碼一起進版**（同 `tools/make_skin.py`／`tools/make_icon.py`）：改了
欄位或骨架就重跑這一支，把「啟動.vbs」一起提交。**不要手改產物**——手改不會有任何
抱怨，而下一次有人重跑就把那幾行無聲蓋掉（`tests/test_docs.py` 逐位元組釘著）。

⚠️ **這一支是 2026-08-28 從一份手寫的 `.vbs` 換過來的**（使用者：「想讓兩個 repo 作法
一致」）。換過來換掉的不只是重複——手寫版為了「共用包搬家只改一個地方」，在 `.vbs`
裡自己寫了一支迷你 TOML 剖析器（`LocalSources`），**執行期**去讀 `pyproject.toml`；
現在那件事在**產生期**用 `tomllib` 做完，`.vbs` 拿到的是算好的字面值。理由見
`docs/dev/gui-啟動與錯誤留底.md`。
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]

# ⚠️ 走 sys.path 而不是要求本專案已安裝：`pyproject.toml` 寫著 `package = false`
# （進入點是根目錄那兩個腳本），所以 `pdf2ppt` 與 GUI 都不是「裝起來」的。
sys.path.insert(0, str(ROOT))
from pdf2ppt.brand import APP_TITLE                          # noqa: E402
from pdf2ppt_gui_2 import SELF_REPORTED_RC                   # noqa: E402
from winkit import launcher                                  # noqa: E402

OUT = ROOT / "啟動.vbs"

# 要跑的那一支。⚠️ **只寫一份**：啟動器有兩條路（環境還新就直接跑 `.venv` 的
# pythonw、否則走 `uv run`），而兩條路跑的必須是同一個進入點；守門也用同一份
# （少了它 uv 只會吐 `can't open file ...` 那種英文訊息，結束碼 2）。
RUN_TARGET = "pdf2ppt_gui_2.py"


def _path_dep_guards() -> tuple[str, ...]:
    r"""`[tool.uv.sources]` 裡走相對路徑的相依，一條一條轉成守門項。

    ⚠️ **相對路徑相依是看不見的**：只把這一個資料夾傳給別人時 `uv sync` 會失敗，
    而錯誤訊息是 uv 自己的路徑錯誤，說不出「你少複製了隔壁那個資料夾」——那正是它
    需要一道守門的理由（使用者換電腦是複製整個 `C:\SOURCE5\`，那時兩個都在；會缺
    的是「只複製了這一個」的情況）。

    ⚠️ **當場從相依宣告算出來，不手抄第二份**（2026-08-28，使用者：「以後 winkit
    搬動目錄位置，只改一個地方就改好」）：抄一份的話，共用包哪天換位置就有兩個地方
    要改，而漏掉守門這邊的下場是它在**正常的安裝**上誤報——畫面上那句話還信誓旦旦
    地說「請把整個專案資料夾完整複製過來」，而使用者照做也不會好。算出來就漂不開。

    ⚠️ 只認 `path = ...` 那種：`git`／`workspace` 的相依缺席時不是「少複製了一個
    資料夾」，uv 自己講得清楚。⚠️ 指名 `pyproject.toml` 是因為守門真正要問的是
    「那個資料夾在不在」，而每個 uv 專案都有這個檔。⚠️ 走 `PureWindowsPath` 轉分隔
    符：`.vbs` 那份清單是 `fso.BuildPath` 吃的，而 TOML 裡寫的是正斜線。
    """
    sources = (tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
               .get("tool", {}).get("uv", {}).get("sources", {}))
    return tuple(str(PureWindowsPath(spec["path"]) / "pyproject.toml")
                 for spec in sources.values()
                 if isinstance(spec, dict) and "path" in spec)


# 少了這幾個就擋下來，並且明講少了什麼。
# ⚠️ **列的每一個都必須真的在專案裡**——守門在**正常的安裝**上誤報是最惡劣的一種
# 壞法（`tests/test_docs.py` 釘著）。
# ⚠️ **不可以伸手進 `pdf2ppt` 套件裡**：套件在不在由 GUI 的 `is_project_dir()`／
# `fail_no_project()` 判，它講得更具體（會把資料夾路徑一起印出來）。兩份清單遲早
# 只會改一邊。
GUARDS = (
    "pyproject.toml",
    RUN_TARGET,
    # 共用資料夾那條（`..\某某\pyproject.toml`）從相依宣告長出來，見上面那支。
    *_path_dep_guards(),
)


def build() -> bytes:
    """產生器現在會寫出來的那一份（不落地）。

    ⚠️ 與 `main()` 分開是為了讓測試比對得到「出貨的產物 == 現在的產生器」——手改
    產物不會有任何抱怨，而下一次重跑就把那幾行無聲蓋掉。"""
    return launcher.render(
        # ⚠️ **名字從 `brand.py` 讀**（唯一真值）：手寫版這裡是一份短版手抄，靠
        # 測試釘「它必須是正本的前綴」。產生器讀得到 Python，那個折衷就不必了。
        app_title=APP_TITLE,
        app_noun="圖形介面",       # 訊息裡的自稱（「圖形介面沒有正常結束」）
        launcher_name="啟動.vbs",
        # ⚠️ **不給 `debug_launcher`**：本專案沒有那支（2026-08-25 使用者指示「交付
        # 給使用者的檔案要盡量少」，「啟動（顯示訊息）.bat」當時被刪掉）。給了就會在
        # 產物的檔頭寫下一條指向不存在的檔案的指路。
        install_bat="安裝.bat",
        # ⚠️ 產物開頭那句「改了就重跑這一支」要指得到真的那一支：共用包的預設值是
        # 姊妹專案的 `scripts/`，本專案的產生器住在 `tools/`（那是本 repo 的慣例）。
        generator="tools/make_launcher.py",
        run_cmd=f"uv run pythonw {RUN_TARGET}",
        # 【快速路徑】給了這個，啟動器就會在環境還新的時候直接跑 `.venv` 裡的
        # pythonw，跳過 `uv run` 每次啟動的專案解析與 lock 比對（實測 35～40ms）。
        run_target=RUN_TARGET,
        # 事前那道退路要比對的輸入。⚠️ **共用包那一條與守門清單同一個來源**
        # （`_path_dep_guards()`）：兩處都要在共用包換位置時跟著走，而抄成兩份的話
        # 漂開的那一份不會有訊息——守門那份誤報、這一份則是永遠當環境沒過期。
        fresh_inputs=("pyproject.toml", "uv.lock", *_path_dep_guards()),
        guards=GUARDS,
        # ⚠️ **守門訊息要多這一句**：清單裡那條 `..\某某` 不在專案資料夾底下，只有
        # 前一句「請把整個專案資料夾完整複製過來」的話，使用者照做也不會好。
        # ⚠️ **整句從共用包讀、不手抄**（2026-08-28 改定，原本兩個下游各寫一份逐字
        # 相同的字面值）：它解釋的是「清單裡為什麼會有 `..` 開頭的路徑」，那是這套
        # 部署方式的性質、不是這支 app 的性質，所以兩支**不可能**需要不一樣。
        guard_note=launcher.PATH_DEP_GUARD_NOTE,
        # ⚠️ **與 GUI 講好的暗號**：它自己跳過訊息框時回這個值，啟動器就安靜收工
        # （使用者 2026-08-25：同一件事不要看到兩個框）。從 GUI 讀、不手抄。
        self_reported_rc=SELF_REPORTED_RC,
        # 「一個字都沒攔到」時要說的話。⚠️ **整句由這裡給**：本專案沒有 DEBUG 啟動
        # 器，所以退路是請使用者自己開一個終端機跑一次。
        no_output_hint=("仍然這樣的話，在這個資料夾按住 Shift 點右鍵選在終端機中開啟，"
                        f"執行 uv run python {RUN_TARGET}，訊息會直接顯示在視窗裡。"),
    )


def main() -> int:
    body = build()
    OUT.write_bytes(body)
    print(f"{OUT.relative_to(ROOT)}  {len(body):,} bytes  "
          f"({body.count(b'\r\n')} 行，cp950)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
