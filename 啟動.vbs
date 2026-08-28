' 啟動.vbs —— 開起圖形介面，全程沒有黑視窗。
'
' 與「啟動（顯示訊息）.bat」的差別只在後者留一個主控台視窗顯示訊息；這一邊
' 用 pythonw 啟動、並把主控台隱藏起來，所以只看得到 GUI。
'
' 代價是原本會印在那個視窗的東西（uv 的錯誤、Python 在 import 期就炸的
' traceback）沒有落點。作法：先收進系統暫存資料夾的一個暫存檔，程式沒能正常
' 結束時「當場把內容跳訊息框顯示出來」，然後把暫存檔刪掉——專案資料夾裡不留
' 任何 log（使用者 2026-08-24 指示「遇到錯誤就立刻顯示，不必寫檔」）。
'
' 程式自己的執行紀錄是另一回事：由 GUI 寫進專案底下的 logs 資料夾，一次執行
' 一個檔、保留 30 天。這裡攔的是「GUI 還沒能力做任何事」的那一段。
Option Explicit

' MsgBox 大約 1024 個字元就會被截掉，而有用的部分（例外的最後幾行）在尾巴
Const MAX_MSG = 900
' 這個結束碼是 GUI 用來說「失敗我自己已經跳過訊息框了，你不必再跳一次」的暗號
' （pdf2ppt_gui_2.py 的 SELF_REPORTED_RC，tests/test_docs.py 釘著兩邊一致）。
' 【注意】不可改成 1 或 2：那兩個是 Python 直譯器自己會回的（1＝未攔到的例外、
' 2＝連 .py 都打不開，也就是只複製了這支 .vbs 的情況），撞上去會讓那些真正該
' 顯示的失敗被靜靜吞掉。GUI 那邊也只在訊息框真的跳出來時才回這個值。
Const RC_SELF_REPORTED = 78
' sh.Run 自己丟例外時 RunHidden 回這個值（連 cmd.exe 都叫不動，那已經不是這支腳本
' 救得了的事）。挑負數是因為結束碼不會是負的，不可能跟真的 rc 撞在一起。
Const RC_LAUNCH_FAILED = -1
' 快速路徑「跑不到這麼久就非正常結束」就當作 GUI 根本沒開起來，改用 uv 再跑一次
' （理由見下面那段）。取 5 秒是往安全那一邊靠：使用者真的用過視窗的話，光是選檔
' 就不只 5 秒，所以不會把「用到一半才出錯」誤判成環境壞掉而白跑一次。
Const FALLBACK_SECS = 5
Const APP_TITLE = "NotebookLM PDF → PPT"

Dim sh, fso, here, q, target, capPath, pyw, t0, rc, out, msg, projFile, kitFile, missing

Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

here    = fso.GetParentFolderName(WScript.ScriptFullName)
q       = Chr(34)
target  = here & "\pdf2ppt_gui_2.py"
' 攔訊息用的暫存檔放系統暫存資料夾（GetSpecialFolder(2)）：專案資料夾裡不留東西
capPath = fso.BuildPath(fso.GetSpecialFolder(2).Path, fso.GetTempName())

sh.CurrentDirectory = here

' 【複製不完整的守門】專案資料夾是整包複製搬家的，而漏掉檔案時 uv 與 Python 吐的
' 是英文訊息：那份訊息照樣會被下面攔下來跳出來，但它說不出「你少複製了東西」，
' 而那正是這個部署方式唯一的失敗模式。2026-08-27 實測過兩種，第二種更糟：
'     少了 pdf2ppt_gui_2.py -> can't open file ... No such file or directory（結束碼 2）
'     少了 pyproject.toml   -> uv 往上找不到專案，就拿一個沒有任何相依的臨時環境
'                              把 GUI 跑起來，啟動時完全沒有錯誤訊息，要等使用者
'                              按下轉檔才在日誌裡看到 import 失敗
' 【注意】這裡只檢查「GUI 自己檢查不到的那兩個」：套件本身（pdf2ppt\cli.py）由 GUI
' 的 is_project_dir()／fail_no_project() 負責，它講得更具體，也會把資料夾路徑一起
' 印出來——不要在這裡再做一份，兩份清單遲早只改一邊。
' 【注意】清單由 tests/test_docs.py 釘著：這裡列的路徑必須真的存在於專案裡，否則
' 守門會在正常的安裝上誤報，而症狀是每次啟動都跳「少了必要的檔案」、程式再也開不
' 起來。訊息裡的檔名一律用 GetFileName 從被檢查的那條路徑取，不要另外手打一份。
missing  = ""
projFile = fso.BuildPath(here, "pyproject.toml")
If Not fso.FileExists(projFile) Then
    missing = missing & vbCrLf & "　　" & fso.GetFileName(projFile)
End If
If Not fso.FileExists(target) Then
    missing = missing & vbCrLf & "　　" & fso.GetFileName(target)
End If
' 【共用包】winkit 住在隔壁資料夾，靠 pyproject.toml 的 [tool.uv.sources] 以相對
' 路徑相依進來（2026-08-28 接上）。那種相依【看不見】：只把這一個資料夾傳給別人
' 時 uv sync 會失敗，而它吐的是 uv 自己的路徑錯誤，說不出「你少複製了隔壁那個
' 資料夾」。使用者換電腦是複製整個 C:\SOURCE5\，那時兩個都在；會缺的是「只複製
' 了這一個」的情況。
' 【注意】這一行顯示的是【相對路徑】不是檔名：它跟專案自己那個同名，只印檔名的
' 話訊息框上會並排兩個一模一樣的 pyproject.toml，使用者分不出少的是哪一個。
kitFile = fso.BuildPath(here, "..\winkit\pyproject.toml")
If Not fso.FileExists(kitFile) Then
    missing = missing & vbCrLf & "　　..\winkit\pyproject.toml"
End If
If Len(missing) > 0 Then
    MsgBox "這個資料夾裡少了必要的檔案：" & vbCrLf & missing & vbCrLf & vbCrLf & _
           here & vbCrLf & vbCrLf & _
           "請把整個專案資料夾完整複製過來，再執行一次「安裝.bat」。" & vbCrLf & _
           "（上面若列出 ..\winkit，那是隔壁的共用資料夾，要跟專案一起複製。）", _
           vbCritical, APP_TITLE
    WScript.Quit 1
End If

' 子行程一律用 UTF-8 輸出，攔到的訊息才解得回來（主控台預設是 cp950，中文
' traceback 直接讀會是亂碼）。改的是本行程的環境區塊，Run 出去的子行程繼承它。
sh.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"

' 【先走環境裡的 pythonw，走不通才交給 uv】2026-08-28。uv run 每次啟動都要解析
' 專案、比對 uv.lock、確認環境同步，實測那一層要 35～40ms——而在「環境已經是新的」
' 時候那 35～40ms 是白工，使用者付的是「按下圖示到視窗出現」的時間。
' 【注意】剩下那一百多毫秒的 wscript 與 cmd 兩層【省不掉】：cmd 那一層是重導向、
' 也就是「藏掉主控台之後錯誤往哪裡去」唯一的來源（見 GuiCmd）。
'
' 【注意】uv run 順手做掉的「環境沒同步就自動補起來」是真的會用到的保護，改成直接
' 叫 pythonw 就沒有了，所以兩道都要留、缺一不可：
'   一、事前（EnvFresh）：.venv 在不在、而且它比 pyproject.toml／uv.lock／隔壁共用包
'       的 pyproject.toml 都新。任何一項對不上就整個走 uv，讓它去補。
'   二、事後（FALLBACK_SECS）：快速路徑非正常結束、而且結束得很快，就用 uv 再跑一次。
'       「.venv 被整包複製到另一台機器、但那台沒有同一版的 Python」只有這一道接得住
'       ——那時 pythonw.exe 根本起不來，而事前那道看不出任何異狀（檔案都在、時間也對）。
'
' 【注意】這裡刻意【不用】fso.BuildPath(here, ...) 組 .venv 的路徑：那個寫法被
' tests/test_docs.py 當成「複製不完整的守門清單」在檢查，列進去的每一條都必須真的
' 存在，否則正常安裝也會被擋下來。而 .venv 不存在是【合法】狀態——它的答案是安靜
' 退回 uv，不是跳錯誤框。
pyw = here & "\.venv\Scripts\pythonw.exe"

t0 = Timer
If fso.FileExists(pyw) And EnvFresh(fso, here) Then
    rc = RunHidden(sh, GuiCmd(q, q & pyw & q, target, capPath))
    If rc <> 0 And rc <> RC_SELF_REPORTED And Elapsed(t0) < FALLBACK_SECS Then
        rc = RunHidden(sh, GuiCmd(q, "uv run pythonw", target, capPath))
    End If
Else
    rc = RunHidden(sh, GuiCmd(q, "uv run pythonw", target, capPath))
End If

If rc = RC_LAUNCH_FAILED Then
    MsgBox "無法啟動程式。" & vbCrLf & vbCrLf & _
           "請先確認已安裝 uv（https://docs.astral.sh/uv/），" & vbCrLf & _
           "再執行「安裝.bat」建立環境。", vbCritical, APP_TITLE
    Cleanup fso, capPath
    WScript.Quit 1
End If

If rc = RC_SELF_REPORTED Then
    ' GUI 自己已經把原因說清楚了，這裡再跳一個「結束碼 78」的框只是噪音。
    ' 安靜收工，但結束碼照樣往外傳（腳本呼叫得到的那一端仍看得出這趟失敗了）。
    Cleanup fso, capPath
    WScript.Quit rc
End If

If rc <> 0 Then
    out = Captured(fso, capPath)
    msg = "圖形介面沒有正常結束（結束碼 " & rc & "）。" & vbCrLf & vbCrLf
    If Len(out) > 0 Then
        msg = msg & out
    Else
        msg = msg & "沒有攔到任何訊息。若是第一次使用，請先執行「安裝.bat」；" & _
              "仍然這樣的話，在這個資料夾按住 Shift 點右鍵選在終端機中開啟，" & _
              "執行 uv run python pdf2ppt_gui_2.py，訊息會直接顯示在視窗裡。"
    End If
    MsgBox msg, vbCritical, APP_TITLE
End If

Cleanup fso, capPath


' 組出那條 cmd：透過 cmd /c 才有重導向（WScript.Shell.Run 自己不支援 > 與 2>&1）。
' 【注意】cmd /c 的引號規則：整串外層包一對引號，內層路徑照常用各自的引號。寫成兩個
' 雙引號想跳脫是錯的——cmd 不吃那套，而專案路徑含中文與可能的空格，這一點錯了就是
' 「雙擊沒反應」。exe 那一段由呼叫端決定要不要加引號：帶路徑的要（可能有空格），
' 「uv run pythonw」那種是三個 token、加了引號 cmd 會把整串當成一個檔名去找。
Function GuiCmd(q, exe, script, capPath)
    GuiCmd = "cmd /c " & q & exe & " " & q & script & q & _
             " > " & q & capPath & q & " 2>&1" & q
End Function


' 跑一趟並回結束碼。
' 【注意】兩個參數都不可改：0 = SW_HIDE（cmd 與 uv 都看不到），True = 等它結束——
' 不等就拿不到結束碼，也就沒辦法在失敗時跳訊息框。代價是 wscript 行程會活到 GUI
' 關閉為止，這是刻意的。
Function RunHidden(sh, cmd)
    On Error Resume Next
    RunHidden = sh.Run(cmd, 0, True)
    If Err.Number <> 0 Then
        RunHidden = RC_LAUNCH_FAILED
        Err.Clear
    End If
    On Error GoTo 0
End Function


' 這一趟花了幾秒。
' 【注意】Timer 回的是「今天過了幾秒」，跨過午夜會歸零而讓差變成負的——不修的話，
' 半夜那一刻啟動的失敗會被當成「一瞬間就結束」，白白多跑一次 uv。
Function Elapsed(t0)
    Elapsed = Timer - t0
    If Elapsed < 0 Then Elapsed = Elapsed + 86400
End Function


' .venv 夠不夠新：拿 site-packages 的修改時間比對「會改變相依的那幾個檔」。
' 【注意】比的是那個資料夾、不是 pyvenv.cfg：後者只在建立環境那一次寫，之後 uv sync
' 裝了什麼、拿掉什麼都不會動到它，拿它當時間戳等於永遠回答「環境是新的」。
' 【注意】這一支的失效方向是【誤判成舊的】：uv sync 認定沒事可做時不會動到
' site-packages，於是只改了 pyproject.toml 的註解也會讓這裡回 False。那只是退回
' uv run——也就是這次改動之前的行為，慢一點而已，不會壞。反過來（誤判成新的）才會
' 讓「相依改了卻沒補」溜過去，所以任何一項對不上就整個放棄快速路徑。
Function EnvFresh(fso, here)
    Dim stamp, site
    EnvFresh = False
    site = here & "\.venv\Lib\site-packages"
    If Not fso.FolderExists(site) Then Exit Function
    stamp = fso.GetFolder(site).DateLastModified
    If Not NotNewer(fso, here & "\pyproject.toml", stamp) Then Exit Function
    If Not NotNewer(fso, here & "\uv.lock", stamp) Then Exit Function
    ' 隔壁的共用包：它的【相依】改了，這邊的環境同樣要重裝（它的原始碼改了不必——
    ' 那是 editable 安裝，import 直接讀那個資料夾）。
    If Not NotNewer(fso, here & "\..\winkit\pyproject.toml", stamp) Then Exit Function
    EnvFresh = True
End Function


' path 沒有比 stamp 新（不在也算過關——「檔案在不在」是上面那段守門的事，不是這裡的）
Function NotNewer(fso, path, stamp)
    If fso.FileExists(path) Then
        NotNewer = (fso.GetFile(path).DateLastModified <= stamp)
    Else
        NotNewer = True
    End If
End Function


' 讀回攔到的訊息。優先用 ADODB.Stream 解 UTF-8（子行程就是用 UTF-8 寫的）；
' 那個元件被停用時退回 FileSystemObject —— 中文會變亂碼，但 traceback 的骨架
' 仍讀得出來，比什麼都不顯示好。
Function Captured(fso, path)
    Dim st, f, text
    Captured = ""
    If Not fso.FileExists(path) Then Exit Function

    text = ""
    On Error Resume Next
    Set st = CreateObject("ADODB.Stream")
    If Err.Number = 0 Then
        st.Type = 2 : st.Charset = "utf-8" : st.Open
        st.LoadFromFile path
        text = st.ReadText
        st.Close
    End If
    If Err.Number <> 0 Or Len(text) = 0 Then
        Err.Clear
        Set f = fso.OpenTextFile(path, 1)
        If Err.Number = 0 Then
            If Not f.AtEndOfStream Then text = f.ReadAll
            f.Close
        End If
    End If
    On Error GoTo 0

    text = Trim(text)
    If Len(text) > MAX_MSG Then
        text = "（訊息很長，以下只顯示最後 " & MAX_MSG & " 個字）" & _
               vbCrLf & vbCrLf & Right(text, MAX_MSG)
    End If
    Captured = text
End Function


' 暫存檔一律刪掉：它只是「把訊息端到訊息框」的通道，不是要留下來的東西。
Sub Cleanup(fso, path)
    On Error Resume Next
    If fso.FileExists(path) Then fso.DeleteFile path, True
    On Error GoTo 0
End Sub
