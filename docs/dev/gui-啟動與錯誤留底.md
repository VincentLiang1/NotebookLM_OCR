# GUI 的啟動方式與錯誤留底（Windows / Tkinter 實作）

> **動到 `啟動.vbs`、`啟動.bat`、`pdf2ppt_gui_2.py` 的啟動或錯誤處理路徑之前先讀這一份。**
>
> 決策層級的那一句（「藏掉主控台就等於藏掉所有錯誤，所以要有東西接住」）在 `docs/spec/09-執行環境與效能.md` §9.5；這裡放綁著 Windows、VBScript、cmd 與 Tkinter 的實作細節。

## 為什麼有兩個啟動入口

使用者 2026-08-24 要求「雙擊之後不要有黑視窗，直接開 GUI」。`.bat` 做不到——**批次檔本身就是主控台程式**，執行它一定會有一個 console window，`start /b` 之類的技巧只能讓它閃一下，消不掉。所以新增 `啟動.vbs`：`wscript` 是 GUI 子系統程式，由它去啟動、並把底下的主控台隱藏起來，全程就只剩 GUI 一個視窗。

`啟動.bat` **保留**，當作看得到訊息的退路（見下一節：log 也可能寫不出來）。兩個入口指向同一支 `pdf2ppt_gui_2.py`，差別只在視窗與訊息落點。

| | `啟動.vbs` | `啟動.bat` |
| --- | --- | --- |
| 主控台 | 隱藏 | 可見 |
| 直譯器 | `pythonw`（GUI 子系統，不自帶 console） | `python` |
| 訊息落點 | `啟動.log`（每次啟動覆寫） | 主控台 |

## 三段接力：訊息從哪裡接住

藏掉主控台的代價是**把所有錯誤一起藏掉**。第一次使用忘了跑 `安裝.bat` 的人，看到的會是「雙擊之後什麼都沒發生」——沒有視窗、沒有訊息、沒有任何線索。三段各自負責一段生命週期，缺一段就有一段時間的錯誤會靜靜消失：

### 1. `.vbs` 層 —— 啟動期（Python 還沒起來）

`uv` 找不到環境、`pyproject.toml` 不在、Python 在 import 期就炸 —— 這些發生在 GUI 有能力做任何事之前，只能由啟動端接。

⚠️ **`WScript.Shell.Run` 自己不支援重導向**（沒有 `>`、沒有 `2>&1`），所以必須繞一層 `cmd /c`：

```vbs
cmd = "cmd /c " & q & "uv run pythonw " & q & target & q & _
      " > " & q & logPath & q & " 2>&1" & q
rc = sh.Run(cmd, 0, True)
```

⚠️ **`cmd /c` 的引號規則**：整串外層包一對引號，內層路徑照常用各自的引號。cmd 看到 `/c` 後第一個字元是引號時會剝掉最外層那一對，剩下的才是真正要跑的命令列。寫成 `""path""`（想用雙引號跳脫）是錯的——cmd 不吃那套。專案路徑含中文與可能的空格，這一點錯了就是「雙擊沒反應」。

`Run(cmd, 0, True)` 的兩個參數都不可改：`0` 是 `SW_HIDE`（cmd 與 uv 都看不到），`True` 是等它結束——**不等就拿不到結束碼**，也就沒辦法在失敗時跳訊息框。代價是 `wscript` 行程會活到 GUI 關閉為止，這是刻意的。

結束碼非 0 時跳 `MsgBox` 並問要不要直接開啟 `啟動.log`。⚠️ 這裡要先 `fso.FileExists(logPath)` 再提「去看 log」——log 開不出來的情況（磁碟唯讀、防毒攔截）反而要把人導回 `啟動.bat`。

### 2. GUI 的一般錯誤 —— 執行期

`App.__init__` 把**啟動當下**的 `sys.stderr` 存進 `self._boot_stderr`，`_write_log()` 只寫它。

⚠️ **必須存這個參考，不可每次去讀 `sys.stderr`。** 轉檔期間 `_run_conversion` 會把 `sys.stdout`／`sys.stderr` 換成 `QueueWriter`（只流向介面下方的日誌區，關掉視窗就沒了），而**那段時間正是最需要留底的**——轉檔失敗是使用者事後最可能回來問的事。所以 `_run_conversion` 的 `except Exception` 除了丟進 `log_queue`，也呼叫 `_write_log()` 寫一份到真正的 log。

⚠️ **不可自己 `open()` 那個 log 檔。** cmd 的 `>` 全程握著它的 handle，Python 再開一次同一個檔會撞在一起（Windows 的共享模式不保證讓你寫）。寫回 `_boot_stderr` 這條管子則完全沒有這個問題——重導向是啟動端的事，GUI 不需要知道 log 在哪，也因此 `啟動.bat` 進來的時候同一段程式碼自動就寫到主控台。

⚠️ **`_write_log()` 全程吞例外**：留底失敗絕不能反過來變成新的例外，蓋掉真正要記的那一個。`_boot_stderr` 也可能是 `None`（`pythonw` 在完全沒有 handle 時），要當正常情況 no-op。

### 3. Tk callback 的例外 —— 最容易漏的一段

Tkinter 對 callback 裡漏出來的例外，預設行為是 `report_callback_exception` 印到 `sys.stderr`、**不彈任何東西**。有黑視窗時那還勉強看得到；沒有之後就是徹底靜默——**按鈕按下去沒反應，畫面上毫無說明**。

覆寫 `App.report_callback_exception`，三件事都做：寫 log、進日誌區、彈對話框。少任何一件都會留下一種「使用者看不到」的情境。

## 實測過的事（2026-08-24）

- **`pythonw` 在這條路上 `sys.stdout`／`sys.stderr` 不是 `None`。** uv 會把 handle 傳給子行程，所以拿到的是指向隱藏 console／重導向檔的有效串流。`None` 只在完全沒有 handle 時才會發生，程式碼仍要防（見上）。
- **更嚴苛的 `CREATE_NO_WINDOW` 情境也跑過完整轉檔**（含 RapidOCR 走 DirectML），沒有任何 C 擴充因為缺 console 而失敗。這是最初的疑慮——onnxruntime／pymupdf 這類會寫 stderr fd 的原生程式庫，在沒有 console 的環境下有可能爆掉。實測沒有。
- **可見視窗只有 GUI 一個**：跑起來之後 `cmd`、`conhost`、`uv`、`wscript` 的 `MainWindowHandle` 全部是 0，只有 `pythonw` 那一個有視窗。這是驗證「黑視窗真的消失了」的方法，用 `Get-Process | Where-Object { $_.MainWindowHandle -ne 0 }` 比對啟動前後。
- **中文 traceback 完整寫進 log**：`cmd` 的重導向對 UTF-8 輸出沒有破壞。

## 編碼

`.vbs` 與 `.bat` 一樣是 **cp950（Big5）、CRLF、無 BOM**——`wscript` 用系統 ANSI codepage 讀檔，編碼錯了會在解析階段就失敗。

⚠️ 但 `.vbs` **沒有也不需要 `chcp`**：那是主控台的東西，VBScript 不經過主控台。`.bat` 的「開頭必須 `chcp 950 >nul`」那條規則不要順手套過來。

## 產出物

`啟動.log` 落在專案根目錄、每次啟動覆寫，已列進 `.gitignore`。
