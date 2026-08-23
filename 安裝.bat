@echo off
chcp 950 >nul
cd /d %~dp0
echo 正在建立執行環境並安裝相依套件...
echo   第一次會下載約 300MB（含 onnxruntime-directml），請耐心等候。
echo.
uv sync
if errorlevel 1 (
  echo.
  echo 安裝失敗。請確認已安裝 uv：https://docs.astral.sh/uv/
  pause
  exit /b 1
)
echo.
echo 安裝完成。之後請雙擊「啟動.vbs」開圖形介面，或把 PDF 拖到「轉檔.bat」上面。
echo   註：OCR 模型（約 100MB）會在第一次轉檔時自動下載，需要一次網路。
pause
