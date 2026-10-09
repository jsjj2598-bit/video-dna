@echo off
chcp 65001 >nul
cd /d "%~dp0"

where go >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Go not found. Install Go 1.25 or use the packaged installer.
    pause
    exit /b 1
)

if not exist "node_modules" call npm ci
echo [Desktop] Building Go backend and launching Electron...
call npm start

pause
