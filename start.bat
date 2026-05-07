@echo off
chcp 65001 >nul
title CESS Platform

echo ========================================
echo   CESS - Energy Storage Optimization
echo ========================================
echo.

cd /d "%~dp0"

echo [0/3] Cleaning up old processes...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5173 ^| findstr LISTENING 2^>nul') do (
    taskkill /f /pid %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING 2^>nul') do (
    taskkill /f /pid %%a >nul 2>&1
)
echo Done.

echo [1/3] Starting backend...
start "CESS-Backend" cmd /k "cd /d %~dp0backend && ..\.venv\Scripts\activate.bat && uvicorn storage_fastapi_backend:app --host 0.0.0.0 --port 8000 --reload"

echo [2/3] Starting frontend dev server...
start "CESS-Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo [3/3] Waiting for frontend to be ready...
timeout /t 5 /nobreak >nul
start "" http://localhost:5173

echo.
echo ========================================
echo   All started! Browser opened.
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo   Close this window without affecting servers.
echo ========================================
pause
