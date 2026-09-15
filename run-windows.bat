@echo off
setlocal
REM ============================================================
REM  Leaside Tracker - double-click this file.
REM
REM  THIS FILE MUST NEVER CHANGE. Windows reads a batch file while
REM  it runs, so if an update rewrote this file mid-run, the rest
REM  of the run would execute garbage. This stub only collects the
REM  update, then hands over to scripts\run-windows-main.bat, which
REM  the update is free to have replaced.
REM ============================================================

cd /d "%~dp0"

echo.
echo ==============================================
echo   Leaside Tracker
echo ==============================================
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo  Note: git is not installed, so updates cannot be collected automatically.
  echo.
) else (
  echo ----------------------------------------------
  echo  Step 0 of 4: collecting updates
  echo ----------------------------------------------
  git pull --ff-only
  if errorlevel 1 (
    echo.
    echo  A file in this folder looks edited to git, so it refused to
    echo  update. Trying to clear it automatically...
    echo.
    git checkout -- . && git pull --ff-only
    if errorlevel 1 (
      echo.
      echo  ============================================================
      echo   COULD NOT UPDATE. The results below will be OUT OF DATE.
      echo  ============================================================
      echo  Copy this whole window and send it to Claude. Nothing is lost:
      echo  the news is collected fresh every run, and what you have read
      echo  is stored in your browser, not here.
      echo.
      git status --short
      echo.
      pause
    ) else (
      echo.
      echo  Cleared. Updated successfully.
      echo.
    )
  )
  echo.
)

if not exist "scripts\run-windows-main.bat" (
  echo  The main script is missing. The update above should have brought it.
  echo  Copy this window and send it to Claude.
  pause
  exit /b 1
)

call "scripts\run-windows-main.bat"
