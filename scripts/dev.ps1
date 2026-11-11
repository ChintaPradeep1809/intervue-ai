# Start the full local stack on Windows: Postgres (docker), worker :8101, API :8100, web :3000.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
docker compose -f "$root/infra/docker/docker-compose.yml" up -d db | Out-Null
Start-Process -WindowStyle Minimized -WorkingDirectory "$root/apps/worker" "$root/.venv/Scripts/python.exe" "-m worker.serve"
Push-Location "$root/apps/api"; & "$root/.venv/Scripts/alembic.exe" upgrade head; Pop-Location
Start-Process -WindowStyle Minimized -WorkingDirectory "$root/apps/api" "$root/.venv/Scripts/python.exe" "-m app.serve"
Push-Location $root; npm run dev:web; Pop-Location
