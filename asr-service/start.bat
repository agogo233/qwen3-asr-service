@echo off
chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0"

set "PYTHONPATH=%~dp0"
set "PATH=%~dp0bin;%~dp0bin\python;%PATH%"
:: UTF-8 mode: redirected/piped stdout uses ANSI codepage on Windows Python (<3.15),
:: which crashes on non-ASCII help/log output; force UTF-8 for deterministic output
set "PYTHONUTF8=1"

:: Detect Python environment: portable first, then venv
set PYTHON_BIN=

if exist "bin\python\python.exe" (
    set PYTHON_BIN=bin\python\python.exe
    echo [INFO] Using portable Python
) else if exist "venv\Scripts\python.exe" (
    call venv\Scripts\activate.bat
    set PYTHON_BIN=venv\Scripts\python.exe
    echo [INFO] Using venv virtual environment
) else (
    echo [ERROR] No Python environment detected - neither portable nor venv exists
    echo Please run setup.bat first to configure the environment.
    pause
    exit /b 1
)

%PYTHON_BIN% -m app.main %*
