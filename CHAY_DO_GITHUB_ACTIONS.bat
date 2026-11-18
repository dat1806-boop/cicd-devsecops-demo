@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)
echo XUAT DU LIEU GITHUB ACTIONS - CHI DOC, KHONG KICH HOAT WORKFLOW
"%PYTHON%" tools\lay_so_lieu_github_actions.py --branch main --count 3
echo.
echo Xem file KET_QUA_DO_GITHUB\github_actions_jobs.csv
pause
