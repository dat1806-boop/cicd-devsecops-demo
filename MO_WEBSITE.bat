@echo off
title CI/CD WorkBoard
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Khong tim thay moi truong Python .venv!
    pause
    exit /b 1
)

echo Dang khoi dong CI/CD WorkBoard...

".venv\Scripts\python.exe" app.py

pause