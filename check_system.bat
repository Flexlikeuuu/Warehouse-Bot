@echo off
title Check System M-100
cd /d "%~dp0"

echo ===================================================
echo   System Diagnostics (M-100)
echo ===================================================

"%~dp0venv\Scripts\python.exe" "%~dp0scripts\check_system.py"

echo.
pause
