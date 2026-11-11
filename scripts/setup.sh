#!/usr/bin/env bash
# One-time setup: Python venv + packages, npm deps, .env, sandbox images, database migration + seed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 -m venv .venv
PIP=".venv/bin/pip"; [ -f .venv/Scripts/pip.exe ] && PIP=".venv/Scripts/pip"
$PIP install -q --upgrade pip
$PIP install -q -e packages/security -e packages/ai -e packages/evaluation -e packages/coding -e packages/voice \
  -e packages/interview-engine -e apps/api -e apps/worker pytest pytest-asyncio pytest-timeout ruff mypy
npm install
[ -f .env ] || { cp .env.example .env; python3 - <<'PY'
import re, secrets, pathlib
p = pathlib.Path(".env"); s = p.read_text()
s = re.sub(r"^AUTH_SECRET=.*$", "AUTH_SECRET=" + secrets.token_urlsafe(48), s, flags=re.M)
s = re.sub(r"^WORKER_TOKEN=.*$", "WORKER_TOKEN=" + secrets.token_urlsafe(24), s, flags=re.M)
p.write_text(s)
PY
}
docker pull -q python:3.12-alpine && docker pull -q node:24-alpine
docker compose -f infra/docker/docker-compose.yml up -d db
sleep 3
PY=".venv/bin/python"; [ -f .venv/Scripts/python.exe ] && PY=".venv/Scripts/python"
(cd apps/api && "../../$PY" -m alembic upgrade head && "../../$PY" -m app.seed)
echo "Setup complete. Start everything with scripts/dev.sh (or scripts/dev.ps1 on Windows)."
