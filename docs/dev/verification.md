# 驗證與收尾的實際操作（指令、路徑、glob）

> ⚠️ **要跑回歸、要做視覺驗證，或一輪工作收尾之前請先讀這一份。**
>
> 「為什麼是這樣驗」在 `docs/spec/10-驗收準則與測試策略.md`（為什麼樣式的真值只有目視、為什麼回歸要求零差異、為什麼參考檔不可拿來校準）；這一份放**照著打就能跑**的指令與路徑。

## 1. 自動測試

```powershell
uv run pytest
```

兩支：`tests/test_docs.py`（文件與程式碼的一致性）與 `tests/test_docs_index.py`（指路不得斷掉、`CLAUDE.md` 字元上限）。另有 `tests/test_gui_helpers.py`（GUI 的純函式、皮膚資產、版面欄位）與 `tests/test_paths.py`。

⚠️ **要看 `skipped` 的數字，在這台機器上應該是 0。** skip 的形式是**綠的**——那一輪其實沒在守，而摘要行不會有任何警告。2026-08-29 真的發生過：量狀態字寬度那支排在三支膠囊測試後面，而那批每個縮放檔建一次 Tk root 又 destroy 一次，之後再 `tk.Tk()` 會丟 `Can't find a usable init.tcl`／`invalid command name "tcl_findLibrary"`，**8 次裡跳掉 6 次**（把那支搬到膠囊那批之前只解決了一半——⚠️ **同一天稍晚又抓到兩次**，這次靠訊息定位到真正的根因：**每一處 `tk.Tk()` 都會間歇性建不起來**（`Can't find a usable init.tcl`／`tk.tcl`／`invalid command name "tcl_findLibrary"`），而膠囊那批量 requested size 的輔助函式那一處沒有重試。兩處統一走帶重試的 `_fresh_tk()` 之後，連跑 **20 輪 0 skip**。）

⚠️ **skip 訊息不可以把原因寫死成猜測。** 同一輪還修掉一個：膠囊測試的 skip 原本寫「這台機器裝不上 squircle 皮膚（**多半是沒有 sv_ttk**）」，而它在**有** sv_ttk 的機器上照樣間歇跳過——那句猜測讓人以為是環境問題、不去追。訊息要帶得出「哪一條路沒走通、環境到底有沒有那個套件」。⚠️ 那幾支的 skip **是刻意的降級**（沒有 Tk、沒有 sv_ttk 的機器上要 skip 而不是紅），所以不能改成硬性 fail——判準是「**這台開發機上不該有任何 skip**」，看到就去追，不要當成正常。⚠️ 追的時候要看 skip 訊息帶的原始錯誤（`-rs`）：沒有原因的 skip 連追都追不了。姊妹專案 meeting-scribe 那邊是另一種守法（`tests/` 底下一個 Tk root 都不建，全套維持 0 skipped）——那條路這邊走不了，皮膚與膠囊的高度只有真的建一個 root 才量得到。

`tests/test_docs.py` 內部分兩份文件集合：

- `RULE_DOCS` = `CLAUDE.md` ＋ `docs/dev/architecture.md` ＋ `docs/spec/*.md` —— 死指路檢查用。⚠️ **架構導讀是明確列進去的**：它是模組名最多的文件，而下面那條刻意不吃整個 `docs/dev/`。
- `SYMBOL_DOCS` = 上面再加 `docs/dev/*.md` —— 常數值與符號指路檢查用。

⚠️ **`docs/dev/` 只進後者**：dev 文件裡有刻意寫出來的**示範路徑**（平台變體的目錄 `docs/spec/<平台>/`、姊妹 repo 的例子），死指路檢查會誤咬。真正的檔案路徑由 `tests/test_docs_index.py` 全 repo 掃，那一條要求副檔名、不會咬到目錄示範。

⚠️ **刻意提到、但程式裡已經沒有的符號**放進 `HISTORICAL` 白名單（目前只有 `_dilate`）。白名單自己也被斷言守著：往裡面加一個名字就少守一個符號，加之前先問「這真的是歷史記述，還是我剛改壞的指路？」

## 2. 回歸：四份 deck 全跑、逐行對照

```powershell
uv run python pdf2ppt.py "<pdf>" -o "<out>.pptx" --debug
```

`--debug` 會另外吐 `*.debug.json`（每行的 `text`／`font_pt`／`bold`／`bg_rgb`／`text_rgb`／`est_pt`）與疊框 PNG。改動前先跑一輪存成基準，改完再跑一輪對照，**預期零差異**。

⚠️ **`SOURCE.pdf` 與 `SOURCE.pptx` 已於 2026-08 由使用者刪除，救不回來**（`.gitignore` 從第一個 commit 起就擋 `*.pdf`／`*.pptx`，它們**從未進過版控**；回收桶與全機掃描也都沒有）。連帶後果：規則裡引用**早期 p-編號**的案例（p5 Git Hook 家族、p8 單一／主專案、p13 第三階段、p14 啟動【技術解法】…）**再也無法回歸測試**，只剩文字記錄——2026-08-23 那輪 code review 就因此無法驗證 `nat_close` 門檻的餘裕。⚠️ **p-編號有兩種來源**：p11–p15 那批新的（藍籌片投影、橘色橫幅、五張並排卡片、步驟徽章「2」）指的是 `guard`，不是 SOURCE.pdf。

語料（磁碟上的實際路徑）：

| 代稱 | 檔案 |
| --- | --- |
| `guard` | `C:\SOURCE5\AI協作開發的軟體品質護欄\AI_Quality_Guardrails.pdf` |
| `guardV2` | `C:\SOURCE5\AI協作開發的軟體品質護欄\AI_時代軟體品質精密護欄V2.pdf`（2026-08-24 起的改版，使用者現在轉的就是這一份）|
| `trans` | `C:\SOURCE5\Raw_Sources\大模型架構\Transformer_演進地圖_NotebookLM簡報.pdf` |
| `gptbp` | `C:\SOURCE5\Raw_Sources\大模型架構\GPT图解 大模型是怎样构建的\blueprint\The_GPT_Blueprint.pdf` |
| `rlbp` | `C:\SOURCE5\FUTURES\AI\Reinforcement_Learning_Blueprint.pdf` |

五份一起跑約 5 分鐘。⚠️ `guard` 同資料夾的 `.pptx` 是使用者自己的存檔，**不是基準**。

### 兩個省時間的做法（2026-08-25 用出來的）

**A/B 不要靠 git stash 來回切。** 匯入 `pdf2ppt.cli`，把要比較的那個函式換掉、在同一支腳本裡跑兩趟，就能一次得到「同一份 PDF、同一顆模型、只差這一條規則」的對照：

```python
from pdf2ppt import blocks, cli
NEW = blocks._is_illegible
def OLD(line, style): ...          # 舊版判別式，照抄再改回去
blocks._is_illegible = OLD         # 或 NEW
sys.argv = ['pdf2ppt.py', pdf, '-o', out, '--debug']
cli.main()                         # 兩趟各吐一份 debug.json，逐行比
```

**要調門檻時，先把量測傾印出來、再離線試。** OCR 一趟五份 deck 要三分鐘，而門檻通常要試好幾個值。先跑一次把每一行的**原始量測**（分數、字級、角度、欄投影的重心散佈…）存成 JSON，之後所有門檻都在那份 JSON 上算——2026-08-25 那輪就是這樣在幾秒內量出「散佈 >0.25 的純字母行有 8 個，其中 6 個是真內容」，否決掉一條看起來很合理的規則。

文字召回率比對（只在使用者提供參考檔時才做）：

```powershell
uv run python tools/compare_pptx.py generated.pptx reference.pptx
```

## 2b. 連跑兩趟（2026-08-29 加）

⚠️ **GUI 的驗收不要只跑一趟。** 「跑一趟會改到、下一趟要用到」的東西，單趟在定義上就測不到——而使用者的用法本來就是**開著程式連轉好幾份**。

2026-08-29 真的漏掉一顆：進度條的 `maximum` 在 indeterminate 下是**動畫的週期**（滑塊幾步走完全程），而上一趟的總頁數留在裡面，第二趟的滑塊於是用四步走完全程（使用者回報：「轉第二次時狀態列就會左右左跳動…那個藍點」）。⚠️ **第一趟看起來完全正常**，因為 ttk 的預設值剛好就是對的那個 100——測試全綠、截圖正常、真的轉過一頁，每一項都只跑了一趟。

要一起看的還有：`_determinate`／`_pages_done`／`_pages_total`／`_scan_buf`、結果列有沒有收起來、工作列的顏色有沒有沿用上一趟、日誌區的分隔線。成因與實測見 `docs/dev/windows-環境與入口.md` §5.18。

## 2c. 臨時腳本改壞原始碼再還原：`finally` 救不了你（2026-08-29）

回歸與故障注入常用同一個模式：**把原始碼改壞 → 跑 → `finally` 還原**。⚠️ **工具的 timeout 是把行程「殺掉」，不是丟例外——`finally` 一步都不會走。** 2026-08-29 真的發生過：一支「換成 HEAD 版的 `blocks.py` → 跑五份語料 → 換回來」的腳本超過 10 分鐘上限被中止，還原那一步沒跑到，**當時手上的修正就這樣沒了**（`git diff` 是空的才發現，而檔案看起來完全正常）。

兩條防護，看形狀選：

- **拿舊版跑語料 → 用 `git worktree`**（本輪採用）：`git worktree add <scratchpad>/head-copy HEAD`，再用主 repo 的 `.venv\Scripts\python.exe` 去跑那個副本裡的 `pdf2ppt.py`（`sys.path[0]` 是它自己的目錄，所以載到的是副本的 `pdf2ppt/`，而相依套件仍走主 venv）。**主工作樹一個字都不動**，連「被殺掉」都不會壞事。用完 `git worktree remove`。
- **要驗的正是「這一份工作樹」→ 讓中斷可回復**：原檔**先落地**（不要只留在記憶體裡的變數），腳本開頭先檢查有沒有上一次留下的殘骸並救回來。姊妹專案 meeting-scribe 的突變工具走的是這條（它要驗的是「這一份樹裡的測試抓不抓得到」，跑副本就不是同一件事了）。

⚠️ **兩條之外的統一判準**（姊妹專案 meeting-scribe 2026-08-29 補的，免得遇到第三種情況要重推）：問一句「**中斷之後，工作樹還是不是它原本的樣子**」。worktree 那條是「**本來就沒動過**」，落地救援那條是「**動過但回得去**」；第三種（動過又回不去）不可接受——那時要**換設計**，不是再加一層保險。

⚠️ 長跑的東西一律丟背景（不受前景 timeout 限制），不要卡在有時限的呼叫上。

## 3. 視覺驗證

用 PowerPoint COM 匯出 PNG，與 `pymupdf` 的頁面渲染圖上下並排：

```powershell
$pp = New-Object -ComObject PowerPoint.Application
$pres = $pp.Presentations.Open($pptx, $true, $false, $false)
$pres.Slides.Item($i).Export($png, "PNG", 1376, 768)
```

比對圖放 `verify/`。⚠️ **要看色差時匯出 3823×2134**（＝200dpi 的原尺寸），1376 寬會把幾個單位的色差糊掉。

## 4. 收尾清掃

⚠️ **這條失守過兩次**（2026-06-12、2026-06-14），兩次成因一模一樣：手打一條片段的 `rm`，漏掉 `--debug` 的疊圖 PNG。而 `.gitignore` 已經涵蓋這些檔，所以 **`git status` 看起來乾淨、把殘留藏起來了**。

**乾淨的 git status 不等於乾淨的工作目錄。** 每一輪的最後一個動作跑一次完整掃描：

```bash
rm -rf verify/ *.debug.json *.debug.p*.png dbg*.pptx dbg.* _dbg_*.py nul.* *.tmp.png
ls -1   # 強制：目視確認只剩原始碼、設定檔、.bat 與要交付的 .pptx
```

`ls -1` 那步不可省——它才是抓得到「漏掉一個 glob」的那一步。**永遠不要刪要交給使用者驗收的產出 `.pptx`**；臨時檔一律寫到 scratchpad 目錄，不要落在專案裡。
