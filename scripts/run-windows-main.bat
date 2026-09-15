@echo off
setlocal
REM Everything after the update step. Safe to change: by the time this runs, the
REM update has already happened, so it is never rewritten while executing.
cd /d "%~dp0\.."

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
) else (
  REM A pull can add a new dependency. Cheap to re-check, expensive to get wrong.
  .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
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
