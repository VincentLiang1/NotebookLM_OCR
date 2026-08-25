# GUI 的啟動方式與錯誤留底（Windows / Tkinter 實作）

> **動到 `啟動.vbs`、`啟動（顯示訊息）.bat`、`pdf2ppt_gui_2.py` 的啟動或錯誤處理路徑之前先讀這一份。**
>
> 決策層級的那一句（「藏掉主控台就等於藏掉所有錯誤，所以要有東西接住」）在 `docs/spec/09-執行環境與效能.md` §9.3；這裡放綁著 Windows、VBScript、cmd 與 Tkinter 的實作細節。

## 為什麼有兩個啟動入口

使用者 2026-08-24 要求「雙擊之後不要有黑視窗，直接開 GUI」。`.bat` 做不到——**批次檔本身就是主控台程式**，執行它一定會有一個 console window，`start /b` 之類的技巧只能讓它閃一下，消不掉。所以新增 `啟動.vbs`：`wscript` 是 GUI 子系統程式，由它去啟動、並把底下的主控台隱藏起來，全程就只剩 GUI 一個視窗。

`啟動（顯示訊息）.bat` **保留**，當作看得到訊息的退路（見下一節：紀錄檔也可能寫不出來）。兩個入口指向同一支 `pdf2ppt_gui_2.py`，差別只在視窗與訊息落點。

| | `啟動.vbs` | `啟動（顯示訊息）.bat` |
| --- | --- | --- |
| 主控台 | 隱藏 | 可見 |
| 直譯器 | `pythonw`（GUI 子系統，不自帶 console） | `python` |
| 啟動期訊息落點 | 系統暫存檔 → **失敗時當場跳訊息框**，然後刪掉 | 主控台 |
| 執行期訊息落點 | 兩邊都一樣：`logs` 底下的執行紀錄（另見第 2 節） | 同左，外加主控台 |

⚠️ **專案資料夾裡不再有 `啟動.log`**（2026-08-24 使用者指示「遇到錯誤就立刻顯示出來，不必寫檔」）。舊版是把 `.vbs` 的重導向目的地放在專案根目錄、每次啟動覆寫，錯了要人自己去開那個檔；現在改成**當場顯示**，暫存檔用完就刪。程式自己的執行紀錄則從「一個會被覆寫的檔」升級成 `logs` 目錄下一次執行一個檔（作法照姊妹專案 `meeting-scribe`，使用者指定）。

## 三段接力：訊息從哪裡接住

藏掉主控台的代價是**把所有錯誤一起藏掉**。第一次使用忘了跑 `安裝.bat` 的人，看到的會是「雙擊之後什麼都沒發生」——沒有視窗、沒有訊息、沒有任何線索。三段各自負責一段生命週期，缺一段就有一段時間的錯誤會靜靜消失：

### 1. `.vbs` 層 —— 啟動期（Python 還沒起來）

`uv` 找不到環境、`pyproject.toml` 不在、Python 在 import 期就炸 —— 這些發生在 GUI 有能力做任何事之前，只能由啟動端接。

⚠️ **`WScript.Shell.Run` 自己不支援重導向**（沒有 `>`、沒有 `2>&1`），所以必須繞一層 `cmd /c`。目的地是**系統暫存資料夾**（`fso.GetSpecialFolder(2)` + `fso.GetTempName()`）：

```vbs
capPath = fso.BuildPath(fso.GetSpecialFolder(2).Path, fso.GetTempName())
cmd = "cmd /c " & q & "uv run pythonw " & q & target & q & _
      " > " & q & capPath & q & " 2>&1" & q
rc = sh.Run(cmd, 0, True)
```

⚠️ **`cmd /c` 的引號規則**：整串外層包一對引號，內層路徑照常用各自的引號。cmd 看到 `/c` 後第一個字元是引號時會剝掉最外層那一對，剩下的才是真正要跑的命令列。寫成 `""path""`（想用雙引號跳脫）是錯的——cmd 不吃那套。專案路徑含中文與可能的空格，這一點錯了就是「雙擊沒反應」。

`Run(cmd, 0, True)` 的兩個參數都不可改：`0` 是 `SW_HIDE`（cmd 與 uv 都看不到），`True` 是等它結束——**不等就拿不到結束碼**，也就沒辦法在失敗時跳訊息框。代價是 `wscript` 行程會活到 GUI 關閉為止，這是刻意的。

結束碼非 0 時把暫存檔讀回來、**內容直接放進 `MsgBox`**，然後刪檔。

⚠️ **有一個結束碼是例外**：`.vbs` 的 `RC_SELF_REPORTED` 常數（值就是 GUI 那邊的 `SELF_REPORTED_RC`(78)）代表「GUI 自己已經跳過訊息框了」（2026-08-25 使用者指示「讓 .vbs 把它當成已說明過，跳過那個框」）。收到它就 `Cleanup` 後 `WScript.Quit rc`：安靜收工、結束碼照傳。目前唯一會回這個值的是「同層找不到 `pdf2ppt` 套件」（`fail_no_project()`），而且**只在訊息框真的跳出來時才回**——Tk 起不來就回 1，讓這裡接手顯示。

⚠️ **暗號不可以是 1 或 2**：`1` 是未攔到的例外，**`2` 是直譯器連 `.py` 都打不開**（只複製了 `.vbs`、GUI 檔不在的情況）——撞上去等於把那次最需要跳框的失敗靜靜吞掉。78 是 sysexits 的 `EX_CONFIG`，uv 與 Python 都不會回。兩邊的常數由 `tests/test_docs.py::test_the_self_reported_exit_code_matches_the_launcher` 釘著。

三個實作上的坑：

- ⚠️ **子行程必須被指定成 UTF-8 輸出**（`sh.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"`，改的是本行程的環境區塊、`Run` 出去的子行程繼承它）。不設的話 Python 會照系統 codepage（cp950）寫，而**讀回來的那一端是照 UTF-8 解的**，中文 traceback 會整段變成亂碼——正好是最需要看懂的那一段。
- ⚠️ **讀檔要用 `ADODB.Stream` 指定 `Charset = "utf-8"`**，`FileSystemObject.OpenTextFile` 只會照系統 codepage 解。ADODB 被停用的機器（少見但存在）退回 FSO：中文變亂碼，但 traceback 的骨架仍讀得出來，比什麼都不顯示好。
- ⚠️ **`MsgBox` 大約 1024 個字元就會被截掉**，而有用的部分（例外的最後幾行）在**尾巴**，所以取 `Right(text, 900)` 而不是開頭。

暫存檔在**每一條路徑上都要刪**（成功、失敗、`Run` 自己丟例外）：它只是「把訊息端到訊息框」的通道。

⚠️ **這條路的單點是 `%TEMP%` 寫不進去**：重導向失敗會讓 `cmd` 直接回非 0，GUI 根本不會起來，而使用者看到的是「結束碼 1、沒有攔到任何訊息」。訊息框在這種情況會把人導向 `啟動（顯示訊息）.bat`。選 `%TEMP%` 而不是專案資料夾，是因為專案資料夾唯讀（放在共用磁碟、被同步工具鎖住）的機會實際上更高。

### 2. GUI 的執行紀錄 —— 執行期

`App.__init__` 在建介面**之前**開好這一趟的紀錄檔（`logs` 底下、檔名是啟動時間＋pid），順序不能反：建介面途中炸掉的話，那是唯一收得到的地方。作法照 `meeting-scribe`（使用者指定），四件事直接沿用：

- **一次執行一個檔**：一次啟動正好等於一個檔，不必另外定義邊界，跨午夜也不會被切成兩半。⚠️ **檔名要帶 pid 才真的成立**：雙擊兩次「啟動.vbs」會有兩個行程在同一秒走到 `open_run_log`，兩邊都是 `open("a")`，同一個檔被兩份輸出交錯寫進去——而那正是最難讀懂的一種紀錄，偏偏出事時要讀的就是它。
- **檔頭記程式版本**（版號讀 `pyproject.toml`、sha 直接讀 `.git`，**不叫 `git` 指令**——啟動路徑不該多開一個行程，而使用者拿到的可能是複製過去的資料夾）。三週後拿一份 log 出來看，沒有這行就只能從訊息長相反推是哪一版跑的。
- **逐次 flush**：使用者是直接關視窗收工的，留在緩衝區的會整段蒸發，而那正好是出事的那一段。
- **寫檔失敗一律靜靜關掉**，不重試也不拋：紀錄檔不該有辦法讓 GUI 掛掉或卡住。開檔失敗就是 `(None, None)`，一切照常跑。

⚠️ **`_append` 是唯一的顯示漏斗，所以留底就掛在它身上**（`_log_write`），而且**要在 `insert` 之前寫**：`insert` 丟 `TclError` 時後面會直接 return，而顯示不出來的內容正是最該留底的那種。這個 repo 沒有用 `logging`（輸出是 `print` 到 stdout/stderr、再由 `QueueWriter` 導進日誌區），所以不像 `meeting-scribe` 那樣掛 handler。

⚠️ **`_log_write` 要上鎖**（`_log_lock`）：畫面上的內容是主執行緒經由 `_append` 寫的，而轉檔失敗的 traceback 是背景執行緒直接呼叫 `_write_log` 寫的，兩邊會撞在一起，交錯的結果是兩段內容都糊掉——而那正是要留的東西。

⚠️ **`\r` 只留最後一段**（緩衝在 `_log_pending` 裡跨 chunk 處理）：下載模型的進度條是原地重寫，整串收下來會在紀錄檔裡堆出上萬行，而這個檔要保持「貼得進對話」。

**保留 30 天**，清檔在開新檔**之前**做——否則剛建好的這一份會被自己的規則掃到（系統時鐘被往回調過的機器上真的會發生）。

`_write_log()` 走**兩個落點**，缺一個就有一種情況看不到東西：

1. 上面那份執行紀錄——事後找得回來、也是使用者要附給我們看的那一份。
2. `App.__init__` **存起來的** `_boot_stderr`。⚠️ **必須存這個參考，不可每次去讀 `sys.stderr`**：轉檔期間 `_run_conversion` 會把 `sys.stdout`／`sys.stderr` 換成 `QueueWriter`（只流向介面下方的日誌區，關掉視窗就沒了），而**那段時間正是最需要留底的**。從 `.bat` 進來時 `_boot_stderr` 就是主控台（使用者當場看得到），從 `.vbs` 進來時它是那個暫存檔（程式若沒能正常結束，內容會直接跳訊息框）；**紀錄檔開不起來時它是唯一的落點**。

⚠️ **`_write_log()` 全程吞例外**：留底失敗絕不能反過來變成新的例外，蓋掉真正要記的那一個。`_boot_stderr` 也可能是 `None`（`pythonw` 在完全沒有 handle 時），要當正常情況 no-op。

⚠️ **紀錄檔的位置要講出來**：`__init__` 最後往日誌區寫一行「執行紀錄：<路徑>」，未預期錯誤的對話框也帶著同一個路徑。叫使用者「去看 log」卻不說在哪，等於沒說。

### 2b. 紀錄檔裡的訊息本身 —— 噪音怎麼壓的

留底管道再完整，內容是三十行套件雜訊也等於沒有。決策層（為什麼壓、為什麼要分兩段）在 `docs/spec/09` §9.4，這裡只記綁著 RapidOCR 的作法：

- **開機那 12 行 INFO**（三個模型 × engine name／檔案驗過／使用路徑／provider）用**設定**壓：`OcrEngine.__init__` 的 `params` 加 `"Global.log_level": "warning"`。⚠️ **不能改成在建構前 `setLevel`**——`RapidOCR.__init__` 自己會呼叫 `logger.setLevel(cfg.Global.log_level.upper())`，先設的一律被蓋掉。留在 `warning` 而不是 `error`：模型下載失敗、檔案驗不過都是那一段才會發生的事。
- **探測性呼叫的 WARNING**（`The text detection result is empty`）在 `RapidOCR(params=...)` **回來之後**才用 `logging.getLogger("RapidOCR").setLevel(logging.ERROR)` 壓掉。順序反過來就會連下載失敗一起吞掉。
- **整頁偵測真的失敗時仍然看得見**：那一頁會印成 `page N: 0 lines`，是我們自己的訊息，不受這裡影響。
- **每頁做過哪些文字修正**存在 `OcrEngine.last_fixes`（`recognize()` 每次進來先清空、離開前寫入，只留非零的項），由 `cli.py` 在 `--debug` 時印成一行 `fixes:`，同時寫進除錯 JSON 的 `fixes` 欄。⚠️ **要在下一次 `recognize()` 之前讀**。

### 3. Tk callback 的例外 —— 最容易漏的一段

Tkinter 對 callback 裡漏出來的例外，預設行為是 `report_callback_exception` 印到 `sys.stderr`、**不彈任何東西**。有黑視窗時那還勉強看得到；沒有之後就是徹底靜默——**按鈕按下去沒反應，畫面上毫無說明**。

覆寫 `App.report_callback_exception`，三件事都做：寫紀錄檔、進日誌區、彈對話框。少任何一件都會留下一種「使用者看不到」的情境。

## 實測過的事

**2026-08-24（第一版，隱藏主控台）**

- **`pythonw` 在這條路上 `sys.stdout`／`sys.stderr` 不是 `None`。** uv 會把 handle 傳給子行程，所以拿到的是指向隱藏 console／重導向檔的有效串流。`None` 只在完全沒有 handle 時才會發生，程式碼仍要防（見上）。
- **更嚴苛的 `CREATE_NO_WINDOW` 情境也跑過完整轉檔**（含 RapidOCR 走 DirectML），沒有任何 C 擴充因為缺 console 而失敗。這是最初的疑慮——onnxruntime／pymupdf 這類會寫 stderr fd 的原生程式庫，在沒有 console 的環境下有可能爆掉。實測沒有。
- **可見視窗只有 GUI 一個**：跑起來之後 `cmd`、`conhost`、`uv`、`wscript` 的 `MainWindowHandle` 全部是 0，只有 `pythonw` 那一個有視窗。這是驗證「黑視窗真的消失了」的方法，用 `Get-Process | Where-Object { $_.MainWindowHandle -ne 0 }` 比對啟動前後。

**2026-08-24（第二版，改成當場顯示 + `logs` 目錄）**

- **整條攔截鏈跑過一次**：拿一個「寫中文 traceback 到 stderr 再 `sys.exit(3)`」的假目標跑同一份 `.vbs`（`MsgBox` 換成 `WScript.Echo`、用 `cscript` 跑），結束碼 3 被接到、UTF-8 的中文 traceback 原樣還原。**正常結束的那一路完全安靜、暫存資料夾裡也沒有殘留 `.tmp`**。
- **雙擊 `.vbs` 的完整路徑跑過**：GUI 起來、`logs` 自動建好、檔頭帶著版號與 sha；用 `CloseMainWindow()` 正常關閉時收到「結束」那一行（強制砍掉則沒有，但逐次 flush 保證前面的內容不會少）。

**2026-08-25（`RC_SELF_REPORTED`）**

- **兩個分支各跑一次**（同樣的假目標手法：`MsgBox` 換 `WScript.Echo`、`cscript` 跑）：假目標 `sys.exit(78)` → `.vbs` **一個字都沒印、自己的結束碼是 78**；假目標 `sys.exit(1)` → 照舊跳框，UTF-8 的中文訊息原樣還原。兩趟的暫存檔都刪乾淨了。
- **GUI 那一半也分兩個分支量過**：空資料夾裡跑 `main()` 得 `rc=78`（訊息框跳出來一次）；把 `tk.Tk` 換成會丟例外的假物件再跑一次得 `rc=1`（stderr 那一份仍完整）。

## 編碼

`.vbs` 與 `.bat` 一樣是 **cp950（Big5）、CRLF、無 BOM**——`wscript` 用系統 ANSI codepage 讀檔，編碼錯了會在解析階段就失敗。

⚠️ 但 `.vbs` **沒有也不需要 `chcp`**：那是主控台的東西，VBScript 不經過主控台。`.bat` 的「開頭必須 `chcp 950 >nul`」那條規則不要順手套過來。

⚠️ **cp950 編不出 `U+26A0`（⚠）**，所以 `.vbs`／`.bat` 的註解裡不能用這個 repo 慣用的警告符號，改寫成「【注意】」。這是寫檔當下才會炸出 `UnicodeEncodeError` 的那種錯，跟中文本身無關（中文、破折號、全形括號、`→` 都編得出來）。

## 產出物

- `logs\<啟動時間>-<pid>.log` —— GUI 每次啟動一個檔，保留 30 天，已列進 `.gitignore`（`logs/` 與 `*.log` 兩條都有）。
- `.vbs` 的暫存檔在 `%TEMP%`，用完即刪，**不留在專案資料夾**。
