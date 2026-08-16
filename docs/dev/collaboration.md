# 協作方式（完整版）

`CLAUDE.md` 的「協作方式」只抄了**必須當場生效**的部分（只有 `CLAUDE.md` 每次自動載入）。這一份放理由、沿革與實測災情——動到相關行為之前先讀這裡。

## 1. 「記住 / 記憶下來」= 寫進 repo，不是寫進 Claude Code 的記憶功能

2026-08-17 移植自 `C:\SOURCE5\Python\meeting-scribe`（該規則 2026-08-06 在 meeting-scribe 與 `MP4-2-SRT` 定案，2026-08-10 推及 `C:\SOURCE5\WIKI` 與 `C:\SOURCE5\FWIKI`，措辭一致；本專案是第五個）。

**Why**：記憶功能的目錄在 `%USERPROFILE%\.claude\projects\<由專案路徑編出來的名字>\`，**在 repo 之外、git 不追蹤**，而使用者換電腦的方式是**複製專案資料夾**——寫在那裡的東西一份都帶不走。更麻煩的是那個目錄名是從絕對路徑編出來的：光是把專案搬到別的資料夾，名字就對不上，記憶等於憑空消失。同理，`C:\Users\vli\.claude\CLAUDE.md`（全域規則）也帶不走，所以跨專案規則若對本專案是關鍵的，要在這裡再寫一份。

**How to apply**：聽到「記住 / 記憶下來 / 以後都要…」時——

1. **必須當場生效**的規則 → 寫進 repo 根目錄的 `CLAUDE.md`（只有它每次自動載入）。
2. **領域細節、沿革、災情紀錄** → 寫進 `docs/dev/`，並在 `CLAUDE.md` 留一句指路。**只寫在 `docs/dev/` 等於沒寫**——那要有人想到去讀才載得進來。
3. 然後**一併提交推送**（本專案本來就是自動 commit + push，見 §3）。
4. **在回覆裡說清楚寫進哪個檔**，讓使用者知道換機器之後還在。

`C:\Users\vli\.claude\projects\C--SOURCE5-Python-NotebookLM-OCR\memory\` 已退役，原地只留一份墓碑指回這裡。

## 2. 回覆語言

**回覆使用者一律用繁體中文（台灣用語），不必等他提醒。** 專有名詞、API 名稱、程式碼、路徑、log 原文照原樣保留。

使用者本身以繁中書寫，且**內容領域也是繁中**——這不只是溝通偏好，它直接決定了技術選擇：OCR 必須用 PP-OCRv5 **server** 辨識模型而不是預設的 v4 mobile（繁中準確度差很多），`--fast` 才切回 mobile。

## 3. commit 訊息、自動提交與 README 同步

**commit 訊息一律繁體中文**（標題與內文，使用者 2026-06-11 指示；技術名詞、函式名、常數、px 數值保留原文）。理由：專案文件本身就是繁中，兩邊一致。

**修正完成並驗證後自動 commit + push，不要再問**（使用者 2026-06-11 指示）。使用者把 GitHub repo（`VincentLiang1/NotebookLM_OCR`）當成即時紀錄，不想每輪下 git 指令。

**功能新增或修改時，`README.md` 要在同一輪同步更新後一起提交**——過時的 README 讓 repo 失去意義。判準是「使用者看得到的行為變了沒有」：新 CLI 選項、新行為、改掉的預設值都算；純內部重構不算。

⚠️ 訊息裡**避免雙引號**（PowerShell 5.1 會截斷），結尾加 `Co-Authored-By`。

⚠️ **`CLAUDE.md` 是被 git 追蹤的**——舊記憶裡寫「CLAUDE.md 被 gitignore」是**錯的**（`.gitignore` 只擋 `*.pdf` / `*.pptx` / `verify/` / `*.debug.*` 那幾類），提交時不要漏掉它。

## 4. 輸出字型是已經拍板的選擇

中文輸出字型是 **Microsoft YaHei**（使用者 2026-06-11 指示，先前為 Noto Sans TC）。

⚠️ **不要「好心」換成 Microsoft JhengHei**：使用者是繁中使用者，但他**明確選了 YaHei**，看的是 PowerPoint 裡的渲染結果。這個選擇還有下游後果——`style.py` 的 `_measure_em()` 固定載入 `C:\Windows\Fonts\msyh.ttc` 量寬度，整套寬度夾制、snap、標題足跡門檻都是以 YaHei 字寬校準的，換字型不會跟著換度量衡（GUI 的字型下拉選單旁有註明）。

## 5. 參考檔的來歷（拿錯檔會得到假的品質數字）

- `SOURCE.pptx` 是**文字**基準，**只**用於 `tools/compare_pptx.py` 的召回率比對。⚠️ **絕不可拿它校準樣式**：它的粗體/字級旗標是從我們自己更早的輸出繼承來的（使用者只修文字、不修樣式），2026-06-12 那批漏判的粗體在參考檔裡**同樣是錯的**。樣式的真值只有一個：**PDF 渲染圖的目視比對**。
- 使用者 OneDrive 裡的 `LLM WikiI資料攝入工作流.pptx` 是 DeckEdit 輸出**再由使用者手動修正過**的版本（可當文字真值）；`DECKEDIT結果.pptx` 是未修正的原始 DeckEdit 輸出。
- DeckEdit 在第 3、5、7、8、9、14、15 頁完全沒有輸出文字（我們的轉換器有），所以比對報表出現 `ref=0` 的列是預期內的。

專案目標（2026-06-11 起）是做 deckedit.com 的本地替代品：把純影像的簡報 PDF 轉成可編輯 PPTX。已確認的決策：RapidOCR 本地離線、完整 DeckEdit 式輸出（背景圖 + 色塊 + 樣式比對過的可編輯文字）、CLI 介面（後來另加桌面圖形介面）。

## 6. 收尾清掃：用一條完整的掃描指令，不要憑記憶手打

**這條失守過兩次**（2026-06-12、2026-06-14，使用者兩次都不高興）。兩次的成因**一模一樣**：我手打一條片段的 `rm`，漏掉 `--debug` 的疊圖 PNG（`*.debug.p*.png`）與臨時腳本。

⚠️ **根因不是文件缺漏**（`CLAUDE.md` 的驗證章節早就列了這些檔），而是兩件事疊在一起：手打指令會漏，而 `.gitignore` 已經涵蓋這些檔案，所以 `git status` 看起來是乾淨的、**把殘留藏起來了**。**乾淨的 git status 不等於乾淨的工作目錄。**

**How to apply**：每一輪修正的**最後一個動作**跑一次完整掃描，不要用眼睛掃：

```bash
rm -rf verify/ *.debug.json *.debug.p*.png dbg*.pptx dbg.* _dbg_*.py nul.* *.tmp.png
ls -1   # 目視確認只剩原始碼 + SOURCE.pdf / SOURCE.pptx / 產出的 .pptx
```

`ls -1` 那步是**強制**的——它才是抓得到「漏了一個 glob」的那一步。

⚠️ 永遠不要刪 `SOURCE.pdf`、`SOURCE.pptx`，以及要交給使用者驗收的產出 `.pptx`。臨時檔一律寫到 scratchpad 目錄，不要落在專案裡。
