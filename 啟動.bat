@echo off
chcp 950 >nul
cd /d %~dp0
echo 正在啟動圖形介面...
echo.
echo 第一次轉檔會下載 OCR 模型（約 100MB），需要一次網路連線。
echo 之後全部在本機執行，不會上傳任何內容。
echo.
echo 這個黑視窗請不要關閉，關掉它程式就跟著結束。
echo.
uv run python pdf2ppt_gui_2.py
if errorlevel 1 pause
