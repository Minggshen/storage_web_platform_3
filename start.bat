@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title CESS Energy Storage Platform

echo ========================================
echo   CESS Energy Storage Optimization
echo ========================================
echo.

cd /d "%~dp0"

echo [1/5] Checking Python environment...

set "PYTHON_EXE=python"

REM 1a. Bundled portable python\ (fully self-contained)
if exist "%~dp0python\python.exe" (
    set "PYTHON_EXE=%~dp0python\python.exe"
    set "PATH=%~dp0python;%~dp0python\Scripts;!PATH!"
    echo   Using bundled Python
    goto :deps_check
)

REM 1b. Local .venv (created from system Python on first launch)
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
    set "PATH=%~dp0.venv\Scripts;!PATH!"
    echo   Using local venv
    goto :deps_check
)

REM 1c. System Python >= 3.11 -- create local venv from it
python --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
    for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
        set "PY_MAJOR=%%a"
        set "PY_MINOR=%%b"
    )
    if "!PY_MAJOR!"=="3" if !PY_MINOR! GEQ 11 (
        echo   Found system Python !PY_VER!
        echo   Creating local venv (isolated from system^) ...
        python -m venv "%~dp0.venv"
        if exist "%~dp0.venv\Scripts\python.exe" (
            set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
            set "PATH=%~dp0.venv\Scripts;!PATH!"
            echo   Created .venv
            goto :deps_check
        )
        echo   [ERROR] Failed to create local .venv.
        echo   Please check Python installation and permissions, then retry.
        pause
        exit /b 1
    ) else (
        echo   System Python !PY_VER! is too old (need 3.11+^)
    )
)

echo.
echo   ========================================
echo   No suitable Python environment found.
echo   Please install 64-bit Python 3.11 or newer first,
echo   or provide python\python.exe / .venv in this folder.
echo   See README.md for setup instructions.
echo   ========================================
echo.
pause
exit /b 1

:deps_check
echo.
echo [2/5] Checking dependencies ...

if not exist "%~dp0.deps_installed" (
    echo   Installing (first launch, may take a few minutes^) ...
    "!PYTHON_EXE!" -m pip install -e ".[full]" --quiet 2>&1
    if errorlevel 1 (
        echo   [WARN] Full install failed, trying base install ...
        "!PYTHON_EXE!" -m pip install fastapi uvicorn "pydantic>=2" python-multipart numpy scipy pandas openpyxl pywin32 joblib scikit-learn osqp pytest ruff --quiet 2>&1
    )
    if errorlevel 1 (
        echo   [ERROR] Dependency installation failed.
        pause
        exit /b 1
    )
    type nul > "%~dp0.deps_installed"
    echo   Done.
) else (
    echo   Already installed.
)

echo.
echo [3/5] Checking configuration ...

if not exist "%~dp0.env" (
    if exist "%~dp0.env.example" (
        copy "%~dp0.env.example" "%~dp0.env" >nul 2>&1
        echo   Created .env from .env.example
    ) else (
        echo   No .env.example found, skipping
    )
) else (
    echo   .env already exists
)

echo.
echo [4/5] Pre-flight check ...

"!PYTHON_EXE!" -c "import fastapi, uvicorn, numpy, pandas, sklearn; print('  Core modules OK')" 2>&1
if errorlevel 1 (
    echo   [WARN] Some core modules may be missing
)

echo.
echo [5/5] Starting server ...
echo.
echo   ========================================
echo     Platform  : http://127.0.0.1:8000
echo     API Docs  : http://127.0.0.1:8000/docs
echo   ========================================
echo     Press Ctrl+C to stop the server.
echo   ========================================
echo.

start "" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "& { for ($i = 0; $i -lt 90; $i++) { try { $ProgressPreference='SilentlyContinue'; $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { Start-Process 'http://127.0.0.1:8000'; exit 0 } } catch { Start-Sleep -Seconds 1 } }; Write-Host 'Backend health check timed out; open http://127.0.0.1:8000 manually after startup.' }"

set "LOG_DIR=%~dp0logs"
cd /d "%~dp0backend"
"!PYTHON_EXE!" -m uvicorn storage_fastapi_backend:app --host 127.0.0.1 --port 8000

pause
