#!/usr/bin/env sh
# One process, one port: http://127.0.0.1:8000  (macOS / Linux)
# Creates the venv, installs, seeds the working DB and builds the UI only when they are missing.
set -e
cd "$(dirname "$0")/.."

[ -d .venv ] || python3 -m venv .venv
PY=.venv/bin/python
$PY -m pip install --quiet -r backend/requirements.txt
[ -f var/pricing.db ] || $PY -m scripts.seed
if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm ci && npx vite build)
fi
echo "Rate Ledger on http://127.0.0.1:8000  (admin token: ADMIN_TOKEN in .env)"
exec $PY -m uvicorn app.main:app --app-dir backend/src --host 127.0.0.1 --port 8000
