@echo off
title AI-Bot M-100
cd /d "%~dp0"

echo ===================================================
echo   Starting AI Bot (M-100)...
echo ===================================================

if not exist "%~dp0venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found in venv folder!
    pause
    exit /b
)

"%~dp0venv\Scripts\python.exe" "%~dp0main.py"

echo.
echo Bot stopped.
pause
