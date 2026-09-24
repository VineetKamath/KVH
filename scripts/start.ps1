# One process, one port: http://127.0.0.1:8000  (Windows PowerShell)
# Creates the venv, installs, seeds the working DB and builds the UI only when they are missing.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".venv")) { python -m venv .venv }
.\.venv\Scripts\python -m pip install --quiet -r backend\requirements.txt
if (-not (Test-Path "var\pricing.db")) { .\.venv\Scripts\python -m scripts.seed }
if (-not (Test-Path "frontend\dist\index.html")) {
    Push-Location frontend
    npm ci
    npx vite build
    Pop-Location
}
Write-Host "Rate Ledger on http://127.0.0.1:8000  (admin token: ADMIN_TOKEN in .env)"
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend\src --host 127.0.0.1 --port 8000
