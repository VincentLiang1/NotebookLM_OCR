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
:next
echo.
echo ====== 轉換 %~nx1 ======
uv run python pdf2ppt.py "%~f1"
if errorlevel 1 (
  set FAILED=1
  echo [失敗] %~nx1
)
shift
if not "%~1"=="" goto next

echo.
if "!FAILED!"=="1" (
  echo 有檔案轉換失敗，訊息在上面。
) else (
  echo 全部完成，.pptx 就在 PDF 旁邊。
)
pause
