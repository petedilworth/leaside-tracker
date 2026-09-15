@echo off
setlocal
REM ============================================================
REM  Find residents' associations.
REM  Reads the FONTRA member list and the Leaside Residents
REM  Association resources page, follows every link, and tests
REM  each website for a news feed.
REM  Run this once. It takes a few minutes.
REM ============================================================

cd /d "%~dp0"

echo.
echo ==============================================
echo   Finding residents' associations
echo ==============================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo  Run run-windows.bat first. It does the one-time setup.
  echo.
  pause
  exit /b 1
)

.venv\Scripts\python.exe -m leaside.cli discover
if errorlevel 1 goto failed

echo.
echo  Done. The results are in:  config\associations-report.md
echo  Open that file and send the whole thing to Claude.
echo.
start "" notepad "config\associations-report.md"
pause
exit /b 0

:failed
echo.
echo  Something went wrong. Select all the text in this window,
echo  copy it, and paste it to Claude.
echo.
pause
exit /b 1
