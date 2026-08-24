@echo off
chcp 950 >nul
cd /d %~dp0
setlocal enabledelayedexpansion

if "%~1"=="" (
  echo 用法：把一個或多個 PDF 拖到這個檔案上面。
  echo.
  echo 會用預設選項轉檔，.pptx 直接輸出到 PDF 旁邊、同名。
  echo 要調選項請改用「啟動.vbs」的圖形介面。
  echo.
  pause
  exit /b 1
)

set FAILED=0
set DEGRADED=0
:next
echo.
echo ====== 轉換 %~nx1 ======
uv run python pdf2ppt.py "%~f1"
rem 代碼 3 = 檔案有了、但至少一頁降級（cli.py 的 PARTIAL_RC）。errorlevel N
rem 是「大於等於 N」，所以一定要先比 3 再比 1，否則降級會被當成失敗。
rem 【注意】這個 3 是手抄 cli.py 的，改那邊要回頭改這裡。
if errorlevel 3 (
  set DEGRADED=1
  echo [部分降級] %~nx1 有頁面只保留原圖，頁碼見上面的 WARNING
) else if errorlevel 1 (
  set FAILED=1
  echo [失敗] %~nx1
)
shift
if not "%~1"=="" goto next

echo.
if "!FAILED!"=="1" (
  echo 有檔案轉換失敗，訊息在上面。
) else if "!DEGRADED!"=="1" (
  echo 完成，但上面標記 [部分降級] 的檔案有幾頁只保留了原圖、沒有可編輯文字。
) else (
  echo 全部完成，.pptx 就在 PDF 旁邊。
)
pause
