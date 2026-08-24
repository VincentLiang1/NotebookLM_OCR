# 驗證與收尾的實際操作（指令、路徑、glob）

> ⚠️ **要跑回歸、要做視覺驗證，或一輪工作收尾之前請先讀這一份。**
>
> 「為什麼是這樣驗」在 `docs/spec/10-驗收準則與測試策略.md`（為什麼樣式的真值只有目視、為什麼回歸要求零差異、為什麼參考檔不可拿來校準）；這一份放**照著打就能跑**的指令與路徑。

## 1. 自動測試

```powershell
uv run pytest
```

兩支：`tests/test_docs.py`（文件與程式碼的一致性）與 `tests/test_docs_index.py`（指路不得斷掉、`CLAUDE.md` 字元上限）。

`tests/test_docs.py` 內部分兩份文件集合：

- `RULE_DOCS` = `CLAUDE.md` ＋ `docs/系統規格.md` ＋ `docs/spec/*.md` —— 死指路檢查用。
- `SYMBOL_DOCS` = 上面再加 `docs/dev/*.md` —— 常數值與符號指路檢查用。

⚠️ **`docs/dev/` 只進後者**：dev 文件裡有刻意寫出來的**示範路徑**（平台變體的目錄 `docs/spec/<平台>/`、姊妹 repo 的例子），死指路檢查會誤咬。真正的檔案路徑由 `tests/test_docs_index.py` 全 repo 掃，那一條要求副檔名、不會咬到目錄示範。

⚠️ **刻意提到、但程式裡已經沒有的符號**放進 `HISTORICAL` 白名單（目前只有 `_dilate`）。白名單自己也被斷言守著：往裡面加一個名字就少守一個符號，加之前先問「這真的是歷史記述，還是我剛改壞的指路？」

## 2. 回歸：四份 deck 全跑、逐行對照

```powershell
uv run python pdf2ppt.py "<pdf>" -o "<out>.pptx" --debug
```

`--debug` 會另外吐 `*.debug.json`（每行的 `text`／`font_pt`／`bold`／`bg_rgb`／`text_rgb`／`est_pt`）與疊框 PNG。改動前先跑一輪存成基準，改完再跑一輪對照，**預期零差異**。

語料（磁碟上的實際路徑）：

| 代稱 | 檔案 |
| --- | --- |
| `guard` | `C:\SOURCE5\AI協作開發的軟體品質護欄\AI_Quality_Guardrails.pdf` |
| `trans` | `C:\SOURCE5\Raw_Sources\大模型架構\Transformer_演進地圖_NotebookLM簡報.pdf` |
| `gptbp` | `C:\SOURCE5\Raw_Sources\大模型架構\GPT图解 大模型是怎样构建的\blueprint\The_GPT_Blueprint.pdf` |
| `rlbp` | `C:\SOURCE5\FUTURES\AI\Reinforcement_Learning_Blueprint.pdf` |

四份一起跑約 5 分鐘。⚠️ `guard` 同資料夾的 `.pptx` 是使用者自己的存檔，**不是基準**。

文字召回率比對（只在使用者提供參考檔時才做）：

```powershell
uv run python tools/compare_pptx.py generated.pptx reference.pptx
```

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
