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

rem 建好之後真的叫一次：uv sync 成功不代表跑得起來。import pdf2ppt.cli 會拉到
rem numpy／pymupdf／python-pptx／Pillow，是真的在驗環境；rapidocr 維持延後載入
rem （它的模型是第一次轉檔才下載的，不該在安裝時扯進來）。
uv run python -c "import pdf2ppt.cli" >nul 2>&1
if errorlevel 1 goto broken

rem 捷徑要指的三段路徑只有這一刻算得出來：使用者把專案放在哪裡是他的自由
rem （換電腦的方式就是複製整個資料夾），所以啟動器、工作目錄與圖示都由腳本
rem 從自己的位置往上推，一段都不寫死。中文全留在那支 UTF-8 的 Python 裡，
rem 這一行維持純 ASCII —— 字串經 cmd 這一層會被重新編碼。
rem 捷徑建不出來不算安裝失敗，只是換一句話收尾。
uv run python tools/make_shortcut.py
if errorlevel 1 goto nolnk

echo.
echo 安裝完成。以後從桌面或「開始」功能表的圖示啟動即可。
echo   註：OCR 模型（約 100MB）會在第一次轉檔時自動下載，需要一次網路。
pause
exit /b 0

:nolnk
echo.
echo 安裝完成。捷徑沒建起來不影響使用：雙擊這個資料夾裡的「啟動.vbs」一樣能開。
echo   註：OCR 模型（約 100MB）會在第一次轉檔時自動下載，需要一次網路。
pause
exit /b 0

:broken
echo.
echo [錯誤] 環境建好了，但實際執行時失敗。最常見的原因是防毒或資安軟體
echo 把 Python 隔離了。請把這個工具資料夾與 %%APPDATA%%\uv 加入白名單，
echo 再執行一次這個檔案。
pause
exit /b 1
