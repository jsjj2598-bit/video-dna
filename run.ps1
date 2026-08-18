$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    Write-Host "创建虚拟环境..."
    python -m venv .venv
}

Write-Host "安装依赖..."
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host "启动服务: http://127.0.0.1:8000"
& ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
