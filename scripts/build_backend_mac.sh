#!/usr/bin/env bash
# 在 macOS 上编译后端 onefile 二进制：dist/backend
# 用法： bash scripts/build_backend_mac.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY=python3
if [ ! -d .venv ]; then
  $PY -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt pyinstaller

rm -f dist/backend
pyinstaller --onefile --clean --name backend \
  --distpath dist --workpath output/pybuild --specpath output \
  --add-data "app/static:app/static" \
  run_backend.py

echo "OK -> dist/backend ($(du -h dist/backend | cut -f1))"