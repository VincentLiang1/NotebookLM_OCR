' 啟動.vbs —— 開起圖形介面的視窗，全程沒有黑框。
'
' 這一邊用 pythonw 啟動、並把主控台整個藏起來，所以桌面上只看得到程式自己的視窗。
'
' 代價是原本會印在那個視窗的東西（uv 的錯誤、Python 在 import 期就炸的
' traceback）沒有落點。作法：先收進系統暫存資料夾的一個暫存檔，程式沒能正常
' 結束時「當場把內容跳訊息框顯示出來」，然後把暫存檔刪掉——專案資料夾裡不留
' 任何東西。
'
' 【注意】這裡攔的是「視窗還沒能力做任何事」的那一段。程式自己的執行紀錄是另
' 一回事：由外層寫進專案底下的 logs 資料夾，一次執行一個檔、保留 30 天。
'
' 開頭那段「少了什麼檔案」的檢查擋的是這個部署方式唯一的失敗模式：整包複製搬家
' 時漏掉東西，而 uv 與 Python 只吐得出英文的建置／匯入錯誤，說不出「你少複製了
' 什麼」——最惡劣的是漏掉 pyproject.toml，那時連錯誤訊息都沒有。
'
' 【這個檔是產生出來的，不要手改】骨架住在 winkit（launcher.vbs.tmpl），這一份是
' 它套上本專案的欄位之後的產物。改了骨架或欄位就重跑 tools/make_launcher.py，
' 產物跟著程式碼一起進版（同 make_skin.py / make_icon.py 的規矩）。
'
' 【啟動的快路與退路】環境還是新的時候，直接跑 .venv 裡的 pythonw，跳過 uv 每次
' 啟動都要做的專案解析與 lock 比對。換掉 uv run 就等於換掉它順手做的「環境沒同步
' 就自動補起來」，所以退路有兩道、缺一不可：事前看 site-packages 的時間戳（任何一
' 項輸入比它新就整個走 uv），事後看「非正常結束、而且不到 5 秒就結束」（那是 .venv
' 被整包複製到另一台機器、而那台沒有同一版 Python 的樣子）。兩道各自的理由寫在
' 下面它們自己那段。
Option Explicit

' MsgBox 大約 1024 個字元就會被截掉，而有用的部分（例外的最後幾行）在尾巴
Const MAX_MSG = 900
Const APP_TITLE = "NotebookLM PDF → PPT 轉檔工具"
' 這個結束碼是與程式講好的暗號：「我自己已經把訊息跳出來了，你不必再說一次」。
' 【注意】不可以改成 1 或 2：那兩個是直譯器自己會回的值（1 = 未攔到的例外、
' 2 = 連 .py 都打不開，也就是只複製了這個 .vbs 的情況），撞上去會讓那些真的需要
' 顯示的失敗被靜靜吞掉。
Const RC_SELF_REPORTED = 78

Dim sh, fso, here, q, capPath, cmd, rc, out, msg, missing
Dim usedFast, started, spent

Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

here    = fso.GetParentFolderName(WScript.ScriptFullName)
q       = Chr(34)
' 攔訊息用的暫存檔放系統暫存資料夾（GetSpecialFolder(2)）：專案資料夾裡不留東西
capPath = fso.BuildPath(fso.GetSpecialFolder(2).Path, fso.GetTempName())

sh.CurrentDirectory = here

' 【複製不完整的守門】專案資料夾是整包複製搬家的，而漏掉 src 或 pyproject.toml
' 時，uv 與 Python 吐的是英文的建置／匯入錯誤。那份訊息照樣會被下面攔下來跳出
' 來，但它說不出「你少複製了東西」這件事——而那正是這個部署方式唯一的失敗模式。
' 【注意】檢查的清單由 tests/test_launcher.py 釘著：這裡列的路徑必須真的存在於
' 專案裡，否則守門會在正常的安裝上誤報。
missing = ""
If Not fso.FileExists(fso.BuildPath(here, "pyproject.toml")) Then
    missing = missing & vbCrLf & "　　pyproject.toml"
End If
If Not fso.FileExists(fso.BuildPath(here, "pdf2ppt_gui_2.py")) Then
    missing = missing & vbCrLf & "　　pdf2ppt_gui_2.py"
End If
If Not fso.FileExists(fso.BuildPath(here, "..\winkit\pyproject.toml")) Then
    missing = missing & vbCrLf & "　　..\winkit\pyproject.toml"
End If
If Len(missing) > 0 Then
    MsgBox "這個資料夾裡少了必要的檔案：" & vbCrLf & missing & vbCrLf & vbCrLf & _
           here & vbCrLf & vbCrLf & _
           "請把整個專案資料夾完整複製過來，再執行一次「安裝.bat」。" & vbCrLf & _
           "（上面若列出 .. 開頭的路徑，那是隔壁的共用資料夾，要跟專案一起複製。）", _
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
cmd = WrapCmd("uv run pythonw pdf2ppt_gui_2.py", q, capPath)
usedFast = False
' 【快速路徑】環境還是新的就直接跑 .venv 裡的 pythonw，跳過 uv 的專案解析與
' lock 比對（實測那一層 32ms）。環境有任何一點對不上就不走這條，讓 uv 去補。
If EnvFresh(fso, here) Then
    cmd = WrapCmd(q & here & "\.venv\Scripts\pythonw.exe" & q & " pdf2ppt_gui_2.py", q, capPath)
    usedFast = True
End If

' 【注意】兩個參數都不可改：0 = SW_HIDE（cmd 與 uv 都看不到），True = 等它
' 結束——不等就拿不到結束碼，也就沒辦法在失敗時跳訊息框。代價是 wscript 行程
' 會活到視窗關閉為止，這是刻意的。
On Error Resume Next
started = Timer
rc = sh.Run(cmd, 0, True)
If Err.Number <> 0 Then
    MsgBox "無法啟動程式（" & Err.Description & "）。" & vbCrLf & vbCrLf & _
           "請先確認已安裝 uv（https://docs.astral.sh/uv/），" & vbCrLf & _
           "再執行「安裝.bat」建立環境。", vbCritical, APP_TITLE
    Cleanup fso, capPath
    WScript.Quit 1
End If
On Error GoTo 0

' 【事後退路】快速路徑非正常結束、而且不到 5 秒就結束，就用 uv 再跑一次。
' 這一道接的是事前那道看不見的情況：.venv 被整包複製到另一台機器、但那台沒有同一
' 版 Python——檔案都在、時間也對，而 pythonw.exe 根本起不來。
' 【注意】5 秒是往安全那邊靠：使用者真的用過視窗的話，光是選檔就不只 5 秒，所以
' 「用到一半才出錯」不會被誤判成環境壞掉而重跑一次（那會讓視窗開兩次）。
' 【注意】Timer 是「今天過了幾秒」，跨午夜會歸零、讓差變成負的，所以補 +86400。
If usedFast And rc <> 0 And rc <> RC_SELF_REPORTED Then
    spent = Timer - started
    If spent < 0 Then spent = spent + 86400
    If spent < 5 Then
        cmd = WrapCmd("uv run pythonw pdf2ppt_gui_2.py", q, capPath)
        rc = sh.Run(cmd, 0, True)
    End If
End If

' 程式自己已經說明過了，這裡再跳一個「結束碼 N」的框只是噪音。
' 安靜收工，但結束碼照傳出去（誰呼叫這支就看得出它失敗了）。
If rc = RC_SELF_REPORTED Then
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
              "仍然這樣的話，在這個資料夾按住 Shift 點右鍵選在終端機中開啟，執行 uv run python pdf2ppt_gui_2.py，訊息會直接顯示在視窗裡。"
    End If
    MsgBox msg, vbCritical, APP_TITLE
End If

Cleanup fso, capPath


' 把要跑的那一串包成 cmd /c 的形狀。透過 cmd /c 才有重導向：WScript.Shell.Run
' 自己不支援 > 與 2>&1。
Function WrapCmd(inner, q, capPath)
    WrapCmd = "cmd /c " & q & inner & " > " & q & capPath & q & " 2>&1" & q
End Function

' 環境還新不新：.venv\Lib\site-packages 的修改時間，不比下面那幾個輸入舊。
' 任何一項比它新就整個走 uv，讓 uv run 順手做掉「環境沒同步就自動補起來」——那件事在快速路徑上
' 沒有別人做了。
' 【注意】比的是 site-packages 這個資料夾，不是 pyvenv.cfg：後者只在建立環境的那
' 一次寫，之後 uv sync 裝了什麼、拿掉什麼都不會動到它，拿它當時間戳等於永遠回答
' 「環境是新的」。
' 【注意】這一支的失效方向是「誤判成舊的」：uv sync 沒事可做時不會動 site-packages，
' 於是連改個註解都會讓它回 False——那只是退回改動前的行為，慢一點而已，不會壞。
' 反過來（該補環境卻回 True）才危險，而事後那道退路正是為它準備的。
Function EnvFresh(fso, here)
    Dim stamp
    EnvFresh = False
    If Not fso.FolderExists(here & "\.venv\Lib\site-packages") Then Exit Function
    If Not fso.FileExists(here & "\.venv\Scripts\pythonw.exe") Then Exit Function
    stamp = fso.GetFolder(here & "\.venv\Lib\site-packages").DateLastModified
    If Not NotNewer(fso, here & "\pyproject.toml", stamp) Then Exit Function
    If Not NotNewer(fso, here & "\uv.lock", stamp) Then Exit Function
    If Not NotNewer(fso, here & "\..\winkit\pyproject.toml", stamp) Then Exit Function
    EnvFresh = True
End Function


' 這個檔不比 stamp 新。
' 【注意】不存在的檔案不構成「環境過期」的理由：uv.lock 在還沒同步過的專案裡就
' 不存在，而那種情況該由 EnvFresh 開頭那兩道（site-packages、pythonw）擋下來。
Function NotNewer(fso, path, stamp)
    NotNewer = True
    If Not fso.FileExists(path) Then Exit Function
    NotNewer = (fso.GetFile(path).DateLastModified <= stamp)
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