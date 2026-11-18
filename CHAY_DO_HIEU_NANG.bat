@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)
echo.
echo WORKBOARD - DO HIEU NANG LOCAL
 echo KHONG su dung cong 5101-5103; chi dung 5201-5202 de do.
 echo Chu y: Docker Build co the mat thoi gian va dung dung luong o dia.
 echo.
echo [1] Xem ke hoach, khong chay lenh
 echo [2] Chay do that 3 lan (Test - Build - DEV - STAGING)
set /p CHOICE=Nhap 1 hoac 2: 
if "%CHOICE%"=="2" (
  "%PYTHON%" tools\do_pipeline_benchmark.py --runs 3 --execute
) else (
  "%PYTHON%" tools\do_pipeline_benchmark.py
)
echo.
echo Sau khi do, xem thu muc KET_QUA_DO va gui ket_qua_do_local.csv cho ChatGPT.
pause
