@echo off
REM run_classify.bat
REM ダブルクリックで実行: 入力ファイルを選び、AI分類してExcelを作成し、出力フォルダを開く。
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Pythonが見つかりません。Python 3.10以降をインストールしてください。
    pause
    exit /b 1
)

python gui.py
if errorlevel 1 (
    echo.
    echo 処理中にエラーが発生しました。
    pause
)
