' 啟動.vbs — 不開黑視窗，雙擊就直接開圖形介面
'
' 與「啟動.bat」的差別只在視窗：.bat 留一個主控台視窗顯示訊息，
' 這一支改用 pythonw 啟動、並將主控台隱藏，所以只看得到 GUI。
'
' 既然沒有黑視窗可看，原本會印在那裡的東西（uv 的錯誤、Python 的
' traceback）全部重導向到這一支旁邊的「啟動.log」，每次啟動覆寫。
' GUI 自己的未預期錯誤也寫進同一份（它寫回原始 stderr，不另開檔，
' 所以不會和這裡的重導向搶同一個檔案 handle）。
' 轉檔過程的訊息照舊顯示在介面下方的日誌區。
Option Explicit

Dim sh, fso, here, q, target, logPath, cmd, rc, msg

Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

here    = fso.GetParentFolderName(WScript.ScriptFullName)
q       = Chr(34)
target  = here & "\pdf2ppt_gui_2.py"
logPath = here & "\啟動.log"

sh.CurrentDirectory = here

' 透過 cmd /c 才有重導向；WScript.Shell.Run 自己不支援 > 與 2>&1。
' cmd /c 的引號規則：整串外層包一對引號，內層路徑照常用引號。
cmd = "cmd /c " & q & "uv run pythonw " & q & target & q & _
      " > " & q & logPath & q & " 2>&1" & q

' 0 = 隱藏視窗（cmd 與 uv 都看不到）；True = 等它結束才拿得到結束碼
On Error Resume Next
rc = sh.Run(cmd, 0, True)
If Err.Number <> 0 Then
    MsgBox "無法啟動程式（" & Err.Description & "）。" & vbCrLf & vbCrLf & _
           "請先確認已安裝 uv（https://docs.astral.sh/uv/），" & vbCrLf & _
           "再雙擊「安裝.bat」建立環境。", _
           vbCritical, "NotebookLM PDF 轉 PPT"
    WScript.Quit 1
End If
On Error GoTo 0

If rc <> 0 Then
    msg = "圖形介面沒有正常結束（結束碼 " & rc & "）。" & vbCrLf & vbCrLf
    If fso.FileExists(logPath) Then
        msg = msg & "錯誤訊息已寫進：" & vbCrLf & logPath & vbCrLf & vbCrLf & _
                    "按「是」直接開啟它。"
        If MsgBox(msg, vbExclamation + vbYesNo, "NotebookLM PDF 轉 PPT") = vbYes Then
            sh.Run q & logPath & q, 1, False
        End If
    Else
        MsgBox msg & "若是第一次使用，請先執行「安裝.bat」。", _
               vbExclamation, "NotebookLM PDF 轉 PPT"
    End If
End If
