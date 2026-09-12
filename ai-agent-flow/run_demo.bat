@echo off
setlocal
cd /d "%~dp0"
python seed.py
if errorlevel 1 goto :failed
python run_all.py --provider stub
if errorlevel 1 goto :failed
python dashboard.py
if errorlevel 1 goto :failed
pause
exit /b 0

:failed
echo Demo failed. See the error above.
pause
exit /b 1
