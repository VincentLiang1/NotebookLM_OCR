# Windows 環境、相依鎖定與四個入口（實作細節）

> ⚠️ **動到相依版本、`.bat`／`.vbs`、字型檔路徑，或 GUI 的選項清單之前請先讀這一份。**
>
> 決策層級的那幾句在 `docs/spec/09-執行環境與效能.md`（為什麼要有 GPU build、為什麼要留一個有主控台的入口、字型為什麼是這一套）；這一份放**綁死 Windows／Python／這幾個函式庫**的細節。啟動與錯誤留底的實作在 `docs/dev/gui-啟動與錯誤留底.md`。

## 1. 相依鎖定：兩個會靜默壞掉的地方

環境由 `uv` 管，`pyproject.toml` 宣告、`uv.lock` 鎖版本。兩條**不可以放寬**的約束，理由都寫在 `pyproject.toml` 的註解裡。

### `onnxruntime-directml`，不是 `onnxruntime`

DirectML 版是「**取代**」CPU 版的完整 build（它同時提供 `CPUExecutionProvider`），裝了 CPU 版就**沒有 GPU**。兩個套件同時存在時匯入哪一個是未定義的，所以是取代不是並存。

⚠️ 這件事**不會當場發現**：DirectML **首次**執行要付一次性的驅動 shader 編譯（實測該次約 213s，看起來與 CPU 同速），編譯結果由 Intel 驅動存碟快取，第二次起才看得到加速。所以裝錯的症狀是「一直慢 4 倍」而不是「壞掉」。我們自己差點因為首跑數據下錯「GPU 沒用」的結論。

實測 Intel Arc 140V：**DirectML 全份 50s vs CPU 210s（快 4.2×）**。

### `rapidocr>=3.8,<3.9`

3.9.2 改掉了模型設定的 API，本專案的參數在它上面直接 `ValueError: Invalid OCR configuration.`（2026-08-23 用 `uv` 建環境時實際撞到）。

3.8.2 → 3.8.4 是安全的，而且更準：`Transformer_演進地圖` 全跑 288 行只差 1 行——`Caping` 被修正成 `Capping`。

### 效能雜項

`_dominant_color` 是全 pipeline 最熱的 helper，每行呼叫 6–10 次；改用 `bincount` 後快 9.3×（900 個真實裁切驗證輸出相同）。樣式估計 56 頁 1249 行由 59.5s 降到 39.2s（2026-08-23 的 `/simplify`，−34%）。

**量過而否決**：`rec_batch_num` 加大反而變慢（16: 0.98s vs 6: 0.80s/頁），維持預設。

## 2. 字型檔與量測

| 用途 | 檔案 |
| --- | --- |
| 寬度量測（預設） | `C:\Windows\Fonts\msyh.ttc` |
| 純拉丁且 ≥3 字的行 | `arial.ttf` |
| 出生估字級 ≥28 的行，其拉丁段 | `ARIALN.TTF`（與輸出的 Arial Narrow 一致） |
| 備援中文字型 | `%LOCALAPPDATA%\Microsoft\Windows\Fonts\` 下的 Noto Sans TC |

每個 run 同時設 `<a:latin>` 與 `<a:ea>`，PowerPoint 按字元類別自動選用，**中英混排同一行雙字型、不需拆 run**。

⚠️ 兩個不可改的細節：**2 字短串**的寬度夾制騎在 snap 平手點上（曾把 p8「98」籌片從 20pt 推成 24pt 粗體），所以短串維持原規則；`_cjk_band_height` 的單字映射**一律維持 YaHei 度量**。

## 3. 主控台與 shell

- Windows 11、Python 3.14；主控台是 **cp950**。印中文的腳本需要 `python -X utf8`（`cli.py` 自己會重設 stdout）。
- PowerShell 會吃掉 `python -c` 單行指令中的雙引號；這類情況改用 Bash 工具或腳本檔。**git commit 訊息中的雙引號也會被截斷**——訊息避免使用雙引號。
- `.bat` 與 `.vbs` 是唯二不用 UTF-8 的檔案：**cp950（Big5）、CRLF、無 BOM**，`.bat` 開頭（任何中文之前）還必須 `chcp 950 >nul`。
- ⚠️ 自己跑完 `.bat` 之後，同一次呼叫的最後一行必須還原 `chcp 65001`——**`chcp` 改的是主控台不是行程**，不還原會讓使用者畫面整片亂碼。
- `.vbs` 沒有 `chcp` 這回事：`wscript` 用系統 ANSI codepage 讀檔，所以編碼要對，但**不需要也不能**下 `chcp`。
- ⚠️ **cp950 編不出 `U+26A0`（⚠）**：`.bat`／`.vbs` 的註解不能用這個 repo 慣用的警告符號，改寫「【注意】」。中文、破折號、全形括號、`→` 都編得出來，只有這一個字會在寫檔當下丟 `UnicodeEncodeError`。

## 4. 兩個入口（2026-08-25 起）

| 檔案 | 做什麼 |
| --- | --- |
| `安裝.bat` | `uv sync` ＋ 煙霧測試 ＋ 建立桌面／「開始」功能表捷徑（見 §5.3） |
| `啟動.vbs` | 開圖形介面，**不開黑視窗**（使用者 2026-08-24 要求；平常用這個） |

⚠️ **本來有四個，`啟動（顯示訊息）.bat`（保留主控台的退路）與 `轉檔.bat`（拖放批次轉檔）在 2026-08-25 依使用者指示刪掉**：「未來希望盡量單純檔案，不要給使用者太多」。兩者的功能都沒有消失，只是改成**不佔交付檔案**的形式——看訊息＝從終端機跑 `uv run python pdf2ppt_gui_2.py`，批次轉檔＝`uv run python pdf2ppt.py a.pdf b.pdf`。判準與通則寫在 `docs/spec/09-執行環境與效能.md` §9.3。⚠️ **新增檔案之前先過那條判準**：這個資料夾裡每多一個長得像入口的檔案，就多一次「我該點哪一個」。

⚠️ **圖形介面每次啟動會在 `logs` 底下寫一份執行紀錄**（檔名是啟動時間＋pid，保留 30 天）；`啟動.vbs` 在程式沒能正常結束時**當場把攔到的訊息跳訊息框**、不落檔（專案資料夾裡沒有 `啟動.log` 這個東西了）。細節見 `docs/dev/gui-啟動與錯誤留底.md`。

⚠️ **`安裝.bat` 在 `uv sync` 之後會真的 import 一次**（`import pdf2ppt.cli`，0.3s，會拉到 numpy／pymupdf／python-pptx／Pillow）：`uv sync` 成功不等於跑得起來——Python 被防毒隔離、uv 的 trampoline 生不出子行程，都是「安裝看似成功、雙擊啟動卻沒反應」。那種事要在安裝當下就講，不要等使用者雙擊「啟動.vbs」才發現，那時他已經不知道該回頭做什麼了。⚠️ **不可改成 `import pdf2ppt`**（那是空的 `__init__.py`，什麼都驗不到），也**不要**扯進 rapidocr（它的模型是第一次轉檔才下載的）。

## 5. GUI 的選項清單是手抄的

⚠️ **`pdf2ppt_gui_2.py` 的選項清單是手抄 `cli.py` 的 argparse 定義**，已經漂移過一次（`--lang` 在 CLI 與 README 都有、GUI 完全沒有，2026-08-16 補上）。現在由 `tests/test_docs.py` 釘著，漏抄就紅。

⚠️ 手抄的是**旗標**。版面上刻意偏離的只有一件事（使用者 2026-08-23／08-24 指示）：**主畫面一個選項都不露出來**，只留輸入／輸出檔，其餘全部收進預設收合的「進階選項」區（`_toggle_advanced`）——那些值日常一項都不必動，攤在主畫面上只是擋住主線。

**2026-08-25 使用者又指示了三件事**（都在 `_build_ui`／`_toggle_advanced` 一帶）：

1. **「開始轉檔」排到收合按鈕之上**、緊接檔案區底下。主線是「選檔 → 按下去」，把終點排在一個日常不必碰的東西後面等於把主線切斷；展開進階區時它還會被推到很下面。連帶：展開的兩區改用 `before=self.progress` 插回去（也就是收合按鈕的正下方），不再是 `before=self.actions_frame`。
2. **主要動作按鈕要明顯**：藍底白字的實心鈕。⚠️ 這一項當天做了兩版——先用 `tk.Button` 自己塗色（因為 Windows 的 vista 佈景把 `ttk.Button` 的底交給原生主題畫，`style.configure(background=…)` 完全沒有效果），換上 Sun Valley 佈景之後改成佈景自己的 **`Accent.TButton`**（`Run.Accent.TButton` 只加大字級與內距）。⚠️ 樣式名**必須以 `.Accent.TButton` 結尾**才繼承得到那組圖片元件；`_set_run_enabled` 也因此瘦成一行 `state()`，hover／pressed／disabled 全部由佈景畫。
3. **收合要把高度還回去**（`_restore_height_after_collapse`）。原本是「只長不縮」，理由寫在程式註解裡：視窗管理員可能把我們要的高度夾掉一截，「還原成展開前的高度」會失效。⚠️ 那個顧慮只對**減法**成立（現在的高度減掉展開時加的量，會把被夾掉的那幾像素永久留下、按幾次愈長愈高）；改成**記下展開前實際量到的高度**再還原就沒事，實測 620 → 941 → 620，第二輪仍是 620。另外記下撐開後量到的高度，使用者展開期間自己拉過視窗（差 >8px）就整個不動——那是他要的尺寸，不是我們借的。

### 沒有「選擇專案資料夾…」這件事了（2026-08-25）

使用者當天指示「UI 上有專案位置的選擇，這個請拿掉，預設目錄下應該就有，如果預設目錄讀不到，就出現錯誤訊息，程式不啟動」。決策層的理由寫在 `docs/spec/09-執行環境與效能.md` §9.7，這裡記形狀與**一起清掉的殘骸**：

- `PROJECT_DIR = Path(__file__).resolve().parent`，模組層級一個常數，**沒有第二個候選**。`APP_ICON`、`log_dir()`、`_git_sha()`、版號讀的 `pyproject.toml` 全部改成從它出發（本來各自寫一次 `Path(__file__).resolve().parent`）。
- 驗證放在 `main()`、**在 `App()` 之前**：`is_project_dir(PROJECT_DIR)` 不過就呼叫 `fail_no_project()` 然後 `return 2`，視窗完全不建。
- `fail_no_project()` 的訊息有兩個落點：`messagebox.showerror`（自己起一個 withdraw 掉的 `tk.Tk()`，因為此刻還沒有主視窗）＋ `sys.stderr`。對話框是給雙擊「啟動.vbs」的人看的（那條路沒有主控台）；stderr 是給從終端機跑的人、**以及對話框跳不出來時**看的。⚠️ `tk.Tk()` 起不來也要吞掉例外，否則錯誤訊息本身變成 traceback。
- ⚠️ **只讓使用者看到一個框**（使用者 2026-08-25 追加指示）：`.vbs` 本來在結束碼非 0 時會把攔到的 stderr 再跳一次，於是同一件事說兩遍。改法是一個雙方講好的暗號——`fail_no_project()` **回傳訊息框有沒有真的跳出來**，`main()` 據此回 `SELF_REPORTED_RC`(78) 或 1；`.vbs` 收到 78 就 `Cleanup` 後 `WScript.Quit rc`，安靜收工但結束碼照傳。⚠️ **暗號不可以是 1 或 2**：`1` 是未攔到的例外，**`2` 是直譯器連 `.py` 都打不開**（只複製了 `.vbs`、GUI 檔不在的情況）——撞上去就會把那次最需要跳框的失敗靜靜吞掉。78 是 sysexits 的 `EX_CONFIG`，uv 與 Python 都不會回。⚠️ **也不可以無條件回 78**：Tk 起不來的機器上那等於什麼都沒說，所以「跳不出來就回 1」那一半是這條規則的另一半。兩個常數由 `tests/test_docs.py::test_the_self_reported_exit_code_matches_the_launcher` 釘著。
- **跟著刪掉的殘骸**（位置固定之後它們在定義上不會再被用到）：`~/.notebooklm_pdf2ppt_gui.json` 這個設定檔與 `load_config()`／`save_config()`（它只存過 `project_dir` 一個鍵，連同 `import json` 一起沒了）、`find_project_dir()` 的三段 fallback、`App.project_dir`／`App.loaded_from`、`_refresh_project_label()`／`_pick_project()`、`_run_conversion()` 裡「換過資料夾就把 `sys.modules` 裡的 `pdf2ppt` 清掉」那一段，以及 `_start()` 開頭的位置檢查。⚠️ **`_run_conversion()` 的 `ModuleNotFoundError` 分流要留著**：`pdf2ppt` 自己不見了（啟動後才被搬走）與缺相依套件（沒跑 `uv sync`）的處方不同。
- 版面連帶：主畫面第一個區塊從「專案位置」變成「檔案」，多出來的高度落給日誌區（`geometry` 的 760×640 沒有跟著改）。

## 5.1 外觀：DPI、字型、佈景（2026-08-25）

使用者當天回報「UI 字體有鋸齒狀」、要求介面全部改用 **Microsoft JhengHei UI**，並問「有沒有其他 Theme 可以選」、能不能改成 [WinUI 3](https://learn.microsoft.com/zh-tw/windows/apps/winui/winui3/)。三件事分開處理：

**① 鋸齒的成因不是字型，是 DPI。** 本機顯示縮放 150%，而 Tk 行程預設**不是 DPI-aware**：Windows 讓它以 96dpi 畫完整個視窗，再**點陣放大** 1.5 倍貼上去，所有筆畫因此糊掉。修法是 `enable_dpi_awareness()`（`SetProcessDpiAwareness(1)`，⚠️ **必須在建 Tk 之前**，Tk 只在啟動時問一次 DPI）。實測 `winfo fpixels 1i` 95.9 → 143.9、螢幕 1707×960 → 2560×1440。⚠️ **連帶代價**：點數指定的字型會自己換算，**寫死的像素不會**——`geometry`、`padx`、`wraplength` 全部要過 `App.px()`，漏一個就在 150% 下縮成 2/3。另外本機的 `TkDefaultFont` 本來就已經是 Microsoft JhengHei UI，所以「換字型」本身治不了鋸齒。

**② 字型走 Tk 的具名字型**（`TkDefaultFont`／`TkTextFont`／…）：ttk 控制項預設就吃這幾個，改一次全部跟著換。⚠️ 連 `TkFixedFont` 與日誌區的 `Consolas` 都換掉了（使用者說「全部的字體」）——代價是日誌區不再等寬，`tqdm` 之類的欄位對齊會鬆掉；要換回等寬只需改 `_build_ui` 裡日誌 `tk.Text` 的 `font=`。⚠️ 佈景自帶的 `SunValley*Font` 是 **Segoe UI Variable + 像素單位**（`-14`），既不是使用者要的字型、在 DPI-aware 的 150% 下也小一號，所以一併改成我們的家族名 + 點數。

⚠️ **介面字型與輸出字型是兩回事、不可互相「順手統一」**：`UI_FONT`（Microsoft JhengHei UI）只管介面自己的字，`--font`（預設 Microsoft YaHei）是**寫進 PPTX 的東亞字型**——`style.py` 的 `_measure_em()` 固定載入 `msyh.ttc` 量寬度，整套寬度夾制、snap 與標題足跡門檻都照 YaHei 校準，換掉它不會跟著換度量衡。兩個名字長得像、住在同一支檔案裡，是這個專案最容易被「統一」掉的一對。

**③ 佈景：`sv-ttk`（Sun Valley）**，一套模仿 Windows 11 Fluent／WinUI 的 ttk 佈景（圓角、細框線、Fluent 輸入框、亮／暗兩套，MIT，純 Tcl+PNG 約 100KB）。內建可選的只有 `winnative / clam / alt / default / classic / vista / xpnative`——其中只有 `clam` 吃得下自訂配色（vista/winnative 的控制項是原生主題畫的），而手工調 clam 只能做到「乾淨」，做不出圓角（圓角要圖片元件）。亮／暗跟隨 Windows 的「應用程式模式」（`preferred_theme_mode()` 直接讀 registry 的 `AppsUseLightTheme`，不為了一個值加 `darkdetect` 依賴），`NOTEBOOKLM_PDF2PPT_THEME=light|dark` 可覆寫；深色時連標題列也用 DWM 屬性 20 一起變深。

⚠️ **切完佈景要自己補一發 `<<ThemeChanged>>`，而且要先 `update_idletasks()`**：sv-ttk 的顏色不寫在佈景定義裡，而是掛在該事件上的 `configure_colors` 設的，Tk 8.6.15 在 `ttk::style theme use` 時**不會**把事件送到根視窗。實測 `ttk::style configure .` 在 `set_theme()` 之後仍是空字串；只補 `event_generate`（`tail` 或 `now` 都一樣）也沒用，**視窗還沒實體化前那個 class binding 根本不會觸發**——補上 `update_idletasks()` 兩者才成立。症狀非常好認：深色模式下一堆**白底黑字的標籤**散在深色視窗上（那是母佈景 clam 的預設灰）。

⚠️ **沒有 `sv_ttk` 也必須開得起來**：`apply_ui_style` 的 `except` 會留在系統原生佈景、只換字型。GUI 是使用者的主要入口，為了外觀讓它開不了完全不划算（測法：`sys.modules["sv_ttk"] = None` 再開一次）。

### 為什麼不是真的 WinUI 3

使用者問了兩次（[microsoft-ui-xaml](https://github.com/microsoft/microsoft-ui-xaml)、[sotanakamura/winui-python](https://github.com/sotanakamura/winui-python)）。WinUI 3 是 C++/C#/XAML 的原生框架（WinAppSDK），**Tk 的視窗裡放不進 XAML 控制項**，所以「改成 WinUI 3」等於換掉整個前端，三條路的代價：

| 路 | 代價 | 換到什麼 |
| --- | --- | --- |
| 現況：Tk + Sun Valley | 一個 100KB 的 MIT 依賴，程式碼零改寫 | 很像 Win11 的外觀（圓角、Fluent 控制項、亮暗自動） |
| `winui-python`（`win32more`） | 使用者機器要另外裝 **Windows App Runtime**；UI 全部改寫成 XAML；背景執行緒要改走 `DispatcherQueue`；那個 repo 是 **16 個 commit 的範例集**，不是框架 | 真的 WinUI 3 控制項、Mica 背景 |
| PySide6 + Fluent widgets | 約 150MB 依賴 + 前端全改寫 | 很接近 WinUI 的外觀，但仍不是 WinUI |

⚠️ 第二條的**風險落點是啟動**：這支 GUI 的價值有一半在「雙擊就開、出事有 log」（`啟動.vbs`、`logs\<時間>-<pid>.log`、訊息框留底），而多一個必須預先安裝的執行階段正好打在那裡。要走這條路的話，先做一個**只有一個視窗、一顆按鈕**的 PoC 確認 Runtime 在使用者機器上裝得起來，再談移植。

**預設值現在三方一致**（2026-08-24 起）。曾經不一致的只有色塊那一項：2026-08-23 到 08-24 之間它是主畫面上唯一的核取方塊、且刻意與 `cli.py` 相反（使用者要拿它做 A/B，看「只有文字方塊帶底色」在 PowerPoint 裡的可編輯性）；量完之後 `cli.py` 的預設改成 `--no-cover`（理由與完整量測見 `docs/spec/06-流程-顏色、蓋板與裁切.md` §6.4），GUI 那一項也收進進階區。

⚠️ **GUI 存的是反向旗標**：進階區那一格叫「色塊獨立畫成矩形」、對應 `self.cover`、預設不勾，勾了才送 `--cover`。所以 `tests/test_docs.py` 的三方一致例外清單是 `{"--no-cover", "--output"}`——`--no-cover` 是預設值、GUI 不需要它的字面。測試只檢查旗標有沒有對應控制項，**預設值本身沒有機器守得住**，改 `cli.py` 的預設時要自己回頭看這一段。

## 5.2 應用程式圖示（2026-08-25）

`assets/` 底下那一組（`icon.svg`／`icon-small.svg`／`icon-mark.svg`／`icon.ico`／兩張 PNG）**全部是 `tools/make_icon.py` 的產物**，幾何與色票的唯一真值在那支腳本裡。改顏色或比例的作法是改腳本、重跑 `uv run python tools/make_icon.py`，然後把 `assets/` 一起提交——不要單獨手改 SVG，下一次重跑就被蓋掉了。

**立意是 OCR 的定義本身：把光學影像認成字元。** 藍色圓角磚，四個白色取景角框住一個白色的「文」。取景角是辨識的通用符號、在 16px 也認得出來；框住的東西刻意是**一個繁體字**而不是拉丁字母，因為這個專案整套是為繁中調的（PP-OCRv5 server 辨識模型、s2tw、頁面詞彙校正）。

### 「文」是量出來的，不是畫出來的

⚠️ **憑感覺畫會變成「女」**——第一版就是，使用者當場指出。文與女的差別**不在撇捺的形狀**（兩個都是交叉的兩筆），而在三件事：

| | 文 | 女 |
| --- | --- | --- |
| 點 | 有 | 沒有 |
| 橫 | 在撇捺**之上**，不穿過它們 | **穿過**撇捺 |
| 交叉點 | 在橫**之下**，字身約 59% | 在橫**之上** |

第一版把橫畫在 y=210、交叉點落在 y=313（77%），三條全踩，於是整個字讀成「女」。

現在的骨架是**從 `msyhbd.ttc` 的「文」量出來的**：把真字形縮進字身框 (160,138)-(352,362)、逐列取墨水游程中心當骨架，撇捺做三次貝茲最小平方擬合（殘差 3px）。量到的數字寫在 `WEN_SKELETON`：橫在 y 173..203（厚 31、近滿寬），撇捺從橫的正下方 y=204 出發，**交叉點 y≈291**。⚠️ 要重畫的話，做法是**重跑那個量測**（把真字形與手畫的疊圖比對），不是改座標試到看起來順眼——「看起來順眼」正是第一版失敗的方式。

⚠️ **點與橫之間要留得開**：點的圓端加上橫的半筆寬很容易吃掉那道縫，黏起來就少掉判別特徵①。

⚠️ **16–32 px 另有一版簡化圖形**（`icon-small.svg`：取景角臂變短、筆畫加粗到 44–46）。滿版那版的筆畫是 30/512，換算下來 16 px 只剩 0.9 px，整個字會斷掉。`.ico` 裡 ≤`SMALL_MAX`(32) 的四個尺寸一律取簡化版。

### 上一版的殘骸與教訓

2026-08-25 稍早有過一版**「NotebookLM 的弧 + 一張投影片」**（取自使用者提供的 `notebook-logo.svg`），同一天被這個 OCR 立意取代。留一條可重用的教訓：⚠️ **一道弧的兩隻腳只要露在方塊兩側，整張圖就會讀成一把掛鎖**（當時排 10 個變體目視，露腳的 5 個全中）。⚠️ 另外，**不可直接沿用 NotebookLM 的商標圖形**——那一版是刻意改成對稱同心、換掉色票才用的；現在這版已經完全不含那個語彙。

### 工作列那顆圖示走的是另一條路（AppUserModelID）

⚠️ **標題列的圖示對了，不代表工作列那顆也對**。使用者 2026-08-25 回報「工作列上的 ICON 不是我設計的」，實際看到的是 **wscript 的圖示**。兩顆的來源不同：

| | 來源 |
| --- | --- |
| 標題列 / Alt-Tab | 視窗的 `WM_SETICON` —— `iconbitmap` 設的就是它 |
| **工作列按鈕** | 先把視窗歸到某個 **AppUserModelID**，再用**那個身分**的圖示 |

行程沒有自己宣告身分時，Windows 會沿用啟動鏈上游的執行檔，而這條鏈是「捷徑 → `wscript.exe` → `cmd` → `uv` → `pythonw`」，於是拿到 wscript 的圖示。

修法有**兩半，缺一半就只修好一半**：

1. **行程端**：`pdf2ppt_gui_2.py` 的 `set_app_user_model_id()` 呼叫 `SetCurrentProcessExplicitAppUserModelID(APP_ID)`。⚠️ **必須在建立第一個視窗之前**（和 `enable_dpi_awareness()` 一樣）——視窗一建出來就已經被工作列歸隊了。
2. **捷徑端**：`.lnk` 也要寫上同一個 `PKEY_AppUserModel_ID`（`tools/make_shortcut.py` 的 `IPropertyStore` 那一段）。少了這一半，使用者把捷徑**釘到工作列**之後，釘的那顆（身分從 `wscript.exe` 推出來）與執行中的視窗（身分是我們宣告的）會變成**兩個各自獨立的按鈕**。

⚠️ **那個字串只有一份**：寫在 GUI 的 `APP_ID`，`make_shortcut.py` 用正規表示式讀走（作法同 `app_name()`）。兩邊不一致就是上面那個「兩顆按鈕」的症狀，而且不會有任何錯誤訊息。

⚠️ **不要找 `InitPropVariantFromString`**：那是 `propvarutil.h` 的 **inline** 函式，`propsys.dll` 沒有匯出這個符號（2026-08-25 實測 `not found`）。`_PROPVARIANT` 是自己排的，⚠️ **尾巴那個 `pad` 欄位不可省**——真正的 PROPVARIANT 是 24 bytes（x64），而 `PropVariantClear` 會把整個結構清成零，宣告短了就是寫出界。字串要用 `CoTaskMemAlloc` 配置（`PropVariantClear` 負責收），⚠️ 而 `CoTaskMemAlloc.restype` 一定要設成 `c_void_p`，否則 x64 上回傳值會被截成 32 位元。

驗收方式（不要靠截圖，那會截到使用者的實機桌面而且不可靠）：`GetCurrentProcessExplicitAppUserModelID` 讀回行程那一邊，`IPropertyStore::GetValue` 讀回 `.lnk` 那一邊，兩個字串要相同。

### `.ico` 與 GUI 端

`.ico` 是**自己組容器**寫出來的（`build_ico`）：Pillow 的 `sizes=` 只會把同一張圖縮放，承載不了「小尺寸換一套圖形」這件事。256 用 PNG 承載、其餘用 DIB，⚠️ DIB 的兩段點陣都是**由下往上**存、AND 遮罩每列要補齊到 4 位元組——遮罩全零（＝全部不透明）的話圓角磚在 Windows 上會露出方角。驗收方式是 `PIL.Image.open(...).ico.sizes()` 讀得回八個尺寸，加上 `tk.Tk().iconbitmap()` 真的吃得下去。

GUI 端在 `pdf2ppt_gui_2.py` 的 `App._apply_window_icon()`。⚠️ 兩個點：路徑以 `PROJECT_DIR`（＝`Path(__file__)` 所在資料夾）為基準而不是 cwd（`啟動.vbs`／捷徑進來時工作目錄不一定對）；失敗一律吞掉（圖示是純外觀，`assets` 不在就讓它沒有圖示，不該讓程式開不起來——`啟動.vbs` 藏著主控台，那會變成「雙擊沒反應」）。`iconbitmap(default=…)` 的 `default=` 不能省，少了它 filedialog／messagebox 那些之後才建的 Toplevel 換不到。

## 5.3 桌面與「開始」功能表的捷徑（2026-08-25）

`tools/make_shortcut.py`，由「安裝.bat」在環境驗過之後呼叫；資料夾搬過位置要重建就直接跑 `uv run python tools/make_shortcut.py`。作法整體移植自姊妹專案 `meeting-scribe` 裡同名的那支腳本（在它的 `scripts` 底下，不是本 repo 的路徑），**但有一處關鍵差異**，見下。

⚠️ **捷徑指的是 `wscript.exe`，`啟動.vbs` 當參數 —— 不是直接指 `.vbs`**。這就是與 `meeting-scribe` 的差異：那邊的入口是 `啟動.bat`，直接指就好；`.vbs` 當捷徑目標有兩個坑，都會讓「雙擊桌面圖示」與「雙擊 `啟動.vbs`」表現不一致：

1. **副檔名關聯被改掉**——不少公司把 `.vbs` 關聯到記事本當防毒措施，那時捷徑會打開原始碼而不是執行。
2. **預設主機若是 `cscript` 就會蹦出黑視窗**，而那正是 `啟動.vbs` 存在的唯一理由（`docs/dev/gui-啟動與錯誤留底.md`）。

把主機釘成 `wscript.exe`、`.vbs` 當參數，兩個都繞開了。找不到 `wscript.exe` 才退回直接指 `.vbs`。

⚠️ **三段路徑一段都不可以寫死**（啟動器、工作目錄、圖示）：使用者換電腦的方式是複製整個專案資料夾，寫死的那條在別台機器上就是一顆指向不存在路徑的死圖示，**比沒有更糟**。全部從腳本自己的 `__file__` 往上推。同名一律覆寫——「搬過位置就重跑安裝.bat」那句話要成立，就得真的把舊捷徑改回來。

⚠️ **桌面路徑不可以用 `~/Desktop` 猜**：OneDrive 的「資料夾備份」會把桌面整個重導到 `%USERPROFILE%\OneDrive\Desktop`，而寫死的那條往往還在、只是沒人看——捷徑建立成功，使用者卻永遠看不到。先用 `SHGetKnownFolderPath` 問 Windows，問不到才退回猜。

⚠️ **不叫 PowerShell 的 `WScript.Shell`**：`.lnk` 在 Windows 上只有 COM 一條路，而 PowerShell 正是公司電腦最常被群組原則收走的東西（執行原則、Constrained Language Mode 都擋得掉）。改用 ctypes 直接叫 `IShellLinkW`，不經過任何外部行程、也不必為一顆捷徑多拉一個相依。⚠️ vtable 是照**順序**呼叫的（`_SET_PATH`=20、`_SET_ARGUMENTS`=11…），數錯一格是當場 crash 不是回錯誤碼，所以介面宣告整段抄在原始碼的註解裡對照。

⚠️ **中文不從 .bat 傳進來**：批次檔是 cp950，字串經 cmd 那一層會被重新編碼。捷徑名稱與所有訊息都寫在那支 UTF-8 的 Python 裡，「安裝.bat」只負責呼叫一行**純 ASCII** 的指令。捷徑名字本身是**從 `pdf2ppt_gui_2.py` 的 `APP_TITLE` 讀正規表示式抓出來的**（不是 import，那會拉進 tkinter；也不是寫死，那會漂移成桌面圖示叫舊名字）。

⚠️ **建不出來絕不能擋住安裝**：走到那一步環境已經好了。桌面被群組原則重導到唯讀網路磁碟、OneDrive 沒登入、資安軟體擋寫入都會失敗，那時該講的是「雙擊資料夾裡的啟動.vbs 一樣能用」。離開碼只拿來讓「安裝.bat」挑最後那句話怎麼寫，**0 與 3 都算安裝成功**。
