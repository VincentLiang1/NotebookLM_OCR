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
Const APP_TITLE = "NotebookLM PDF → PPT"

Dim sh, fso, here, q, target, capPath, cmd, rc, out, msg, projFile, kitFile, missing

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

' 透過 cmd /c 才有重導向：WScript.Shell.Run 自己不支援 > 與 2>&1。
' 【注意】cmd /c 的引號規則：整串外層包一對引號，內層路徑照常用各自的引號。
' 寫成兩個雙引號想跳脫是錯的——cmd 不吃那套，而專案路徑含中文與可能的空格，
' 這一點錯了就是「雙擊沒反應」。
cmd = "cmd /c " & q & "uv run pythonw " & q & target & q & _
      " > " & q & capPath & q & " 2>&1" & q

' 【注意】兩個參數都不可改：0 = SW_HIDE（cmd 與 uv 都看不到），True = 等它
' 結束——不等就拿不到結束碼，也就沒辦法在失敗時跳訊息框。代價是 wscript 行程
' 會活到 GUI 關閉為止，這是刻意的。
On Error Resume Next
rc = sh.Run(cmd, 0, True)
If Err.Number <> 0 Then
    MsgBox "無法啟動程式（" & Err.Description & "）。" & vbCrLf & vbCrLf & _
           "請先確認已安裝 uv（https://docs.astral.sh/uv/），" & vbCrLf & _
           "再執行「安裝.bat」建立環境。", vbCritical, APP_TITLE
    Cleanup fso, capPath
    WScript.Quit 1
End If
On Error GoTo 0

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
