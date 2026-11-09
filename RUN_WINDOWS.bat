@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===============================================
echo       WORKBOARD - INTERACTIVE CI/CD LAB
echo ===============================================
if not exist .venv\Scripts\python.exe (
  echo [1/3] Tao moi truong Python...
  py -3.12 -m venv .venv
  if errorlevel 1 goto error
)
echo [2/3] Cai dat thu vien cho Python 3.12...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if errorlevel 1 goto error
echo [3/3] Khoi dong website...
echo Trang chu: http://127.0.0.1:5000/
echo Phong CI/CD: http://127.0.0.1:5000/lab
echo Nhan Ctrl+C de dung server.
.venv\Scripts\python.exe app.py
goto end
:error
echo.
echo Co loi khi cai dat. Hay chup man hinh cua so nay gui de duoc ho tro.
pause
:end
