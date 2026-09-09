@echo off
setlocal
REM ============================================================
REM  Leaside Tracker - double-click this file.
REM  First run sets everything up. After that it just updates.
REM ============================================================

cd /d "%~dp0"

echo.
echo ==============================================
echo   Leaside Tracker
echo ==============================================
echo.

REM Find Python. The "py" launcher is the reliable one on Windows.
set PY=
py -3 --version >nul 2>&1 && set PY=py -3
if not defined PY (
  python --version >nul 2>&1 && set PY=python
)
if not defined PY (
  echo.
  echo  PROBLEM: Python is not installed, or Windows cannot find it.
  echo.
  echo  Fix it like this:
  echo    1. Go to  https://www.python.org/downloads/
  echo    2. Click the big yellow "Download Python" button.
  echo    3. Run the file you downloaded.
  echo    4. On the FIRST screen, tick the box "Add python.exe to PATH".
  echo       This box is easy to miss and nothing works without it.
  echo    5. Click "Install Now" and wait.
  echo    6. Close this window and double-click this file again.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First run. Setting up. This takes about a minute.
  echo.
  %PY% -m venv .venv
  if errorlevel 1 goto failed
  .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
  .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
  if errorlevel 1 goto failed
  echo Setup finished.
  echo.
)

echo ----------------------------------------------
echo  Step 1 of 4: checking which sources work (once a week)
echo ----------------------------------------------
.venv\Scripts\python.exe -m leaside.cli probe

echo.
echo ----------------------------------------------
echo  Step 2 of 4: collecting the news
echo ----------------------------------------------
.venv\Scripts\python.exe -m leaside.cli ingest

echo.
echo ----------------------------------------------
echo  Step 3 of 4: building your page
echo ----------------------------------------------
.venv\Scripts\python.exe -m leaside.cli build
if errorlevel 1 goto failed

echo.
echo ----------------------------------------------
echo  Step 4 of 4: checking the health of your data
echo ----------------------------------------------
.venv\Scripts\python.exe -m leaside.cli doctor
if errorlevel 1 goto failed

echo.
echo  Done. Opening your page in your web browser now.
echo.
echo  If Claude asks how the run went, send this one file:
echo      config\health-report.md
echo  It is opening in Notepad behind your browser.
echo.
start "" "site\index.html"
start "" notepad "config\health-report.md"
pause
exit /b 0

:failed
echo.
echo  Something went wrong. Select all the text in this window,
echo  copy it, and paste it to Claude. Do not worry, nothing is broken.
echo.
pause
exit /b 1
