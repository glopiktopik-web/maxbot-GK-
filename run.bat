@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1

echo Installing dependencies...
python -m pip install -r requirements.txt

echo.
echo Starting bot. Press Ctrl+C to stop.
echo.
python bot.py

echo.
pause
