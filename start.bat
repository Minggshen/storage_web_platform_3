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
    for /f "tokens=2 delims=." %%a in ("!PY_VER!") do set "PY_MINOR=%%a"
    if !PY_MINOR! GEQ 11 (
        echo   Found system Python !PY_VER!
        echo   Creating local venv (isolated from system^) ...
        python -m venv "%~dp0.venv"
        if exist "%~dp0.venv\Scripts\python.exe" (
            set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
            set "PATH=%~dp0.venv\Scripts;!PATH!"
            echo   Created .venv
            goto :deps_check
        )
        echo   [WARN] venv creation failed, trying portable Python...
    ) else (
        echo   System Python !PY_VER! is too old (need 3.11+^)
    )
)

REM 1d. Nothing usable -- download portable Python into project folder
echo.
echo   ========================================
echo   No suitable Python found.
echo   Downloading portable Python 3.11 ...
echo   (one-time setup, ~8 MB, project folder only)
echo   ========================================
echo.

set "PYTHON_ZIP=%~dp0python_temp.zip"
set "PYTHON_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"

echo   [*] Downloading ...
powershell -NoProfile -Command "& { try { $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_ZIP%' -ErrorAction Stop } catch { exit 1 } }"
if not exist "%PYTHON_ZIP%" (
    echo   [ERROR] Download failed. Check your internet connection.
    pause
    exit /b 1
)

echo   [*] Extracting to python\ ...
if not exist "%~dp0python" mkdir "%~dp0python"
powershell -NoProfile -Command "& { Expand-Archive -Path '%PYTHON_ZIP%' -DestinationPath '%~dp0python' -Force }"
del "%PYTHON_ZIP%" 2>nul

if not exist "%~dp0python\python.exe" (
    echo   [ERROR] Extraction failed. Check disk space.
    pause
    exit /b 1
)

REM Enable site-packages in embeddable Python (required for pip)
echo   [*] Enabling site-packages ...
set "PTH_FILE=%~dp0python\python311._pth"
if exist "!PTH_FILE!" (
    powershell -NoProfile -Command "& { (Get-Content '!PTH_FILE!') -replace '#import site', 'import site' | Set-Content '!PTH_FILE!' }"
)

REM Install pip
echo   [*] Installing pip ...
powershell -NoProfile -Command "& { try { $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%~dp0python\get-pip.py' -ErrorAction Stop } catch { exit 1 } }"
if exist "%~dp0python\get-pip.py" (
    "%~dp0python\python.exe" "%~dp0python\get-pip.py" --no-warn-script-location >nul 2>&1
    del "%~dp0python\get-pip.py" 2>nul
)

set "PYTHON_EXE=%~dp0python\python.exe"
set "PATH=%~dp0python;%~dp0python\Scripts;!PATH!"
echo   Portable Python 3.11 ready.

:deps_check
echo.
echo [2/5] Checking dependencies ...

if not exist "%~dp0.deps_installed" (
    echo   Installing (first launch, may take a few minutes^) ...
    "!PYTHON_EXE!" -m pip install -e ".[full]" --quiet 2>&1
    if errorlevel 1 (
        echo   [WARN] Full install failed, trying base install ...
        "!PYTHON_EXE!" -m pip install fastapi uvicorn "pydantic>=2" python-multipart numpy scipy pandas openpyxl pywin32 joblib --quiet 2>&1
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

"!PYTHON_EXE!" -c "import fastapi, uvicorn, numpy, pandas; print('  Core modules OK')" 2>&1
if errorlevel 1 (
    echo   [WARN] Some core modules may be missing
)

echo.
echo [5/5] Starting server ...
echo.
echo   ========================================
echo     Platform  : http://localhost:8000
echo     API Docs  : http://localhost:8000/docs
echo   ========================================
echo     Press Ctrl+C to stop the server.
echo   ========================================
echo.

timeout /t 2 /nobreak >nul
start "" http://localhost:8000

set "LOG_DIR=%~dp0logs"
cd /d "%~dp0backend"
"!PYTHON_EXE!" -m uvicorn storage_fastapi_backend:app --host 0.0.0.0 --port 8000

pause
