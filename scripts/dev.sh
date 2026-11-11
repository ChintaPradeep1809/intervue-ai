#!/usr/bin/env bash
# Start the full local stack on macOS/Linux: Postgres (docker), worker :8101, API :8100, web :3000.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
docker compose -f "$ROOT/infra/docker/docker-compose.yml" up -d db
(cd "$ROOT/apps/worker" && "$PY" -m worker.serve) &
(cd "$ROOT/apps/api" && "$ROOT/.venv/bin/alembic" upgrade head && "$PY" -m app.serve) &
trap 'kill 0' EXIT
cd "$ROOT" && npm run dev:web
