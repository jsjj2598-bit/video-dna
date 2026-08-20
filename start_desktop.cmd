@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set PY=.venv\Scripts\python.exe
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python^ not found.
        echo Run: python -m venv .venv
        echo Then: .venv\Scripts\pip install -r requirements.txt
        pause
        exit /b 1
    )
    set PY=python
)

echo [Backend]^ Starting Python server...
start /B "" "%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning

echo [Backend]^ Waiting for server...
:wait
timeout /t 2 /nobreak >nul 2>&1
powershell -Command "try{$r=curl.exe -s http://127.0.0.1:8000/health 2>$null; if($r -match 'ok'){exit 0}}catch{};exit 1" >nul 2>&1
if errorlevel 1 goto wait

echo [Backend]^ Ready!
echo [Desktop]^ Launching Electron...

if exist "dist\win-unpacked\Video DNA Analyzer.exe" (
    start "" "dist\win-unpacked\Video DNA Analyzer.exe"
) else (
    npx electron .
)

pause
