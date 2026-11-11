# Local setup

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.12+ | API, worker, engine |
| Node.js | 20.9+ (24 recommended) | Web app; also runs JS/TS in the dev sandbox |
| Docker | 24+ with the daemon running | Postgres + code-execution sandbox containers |
| Chrome or Edge | recent | Voice interviewer (Web Speech API). Other browsers fall back to typed answers |

## One-command setup

```bash
bash scripts/setup.sh
```

This creates `.venv`, installs the Python packages in editable mode, installs the npm workspaces, and
writes `.env` with fresh `AUTH_SECRET` and `WORKER_TOKEN` values. It also pulls the sandbox images
(`python:3.12-alpine`, `node:24-alpine`), starts Postgres on port **54329**, runs Alembic migrations
and seeds demo data.

## Run

```bash
bash scripts/dev.sh       # macOS / Linux / Git Bash
pwsh scripts/dev.ps1      # Windows PowerShell
```

| Service | URL |
|---|---|
| Web | http://localhost:3000 |
| API (+ OpenAPI docs) | http://localhost:8100/api/docs |
| Worker health | http://localhost:8101/health |
| Postgres | `postgresql://intervue:intervue_local_dev@localhost:54329/intervue` |

The web app proxies `/api/*` to the API (same origin, so the httpOnly session cookie works). The
interview WebSocket connects directly to the API with a short-lived ticket.

## Manual steps (if you prefer)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e packages/security -e packages/ai -e packages/evaluation -e packages/coding \
            -e packages/voice -e packages/interview-engine -e apps/api -e apps/worker
npm install
cp .env.example .env    # then set AUTH_SECRET and WORKER_TOKEN
docker compose -f infra/docker/docker-compose.yml up -d db
cd apps/api && alembic upgrade head && python -m app.seed && cd ../..
(cd apps/worker && python -m worker.serve) &
(cd apps/api && python -m app.serve) &
npm run dev:web
```

On Windows, start the API with `python -m app.serve`, not with plain `uvicorn`. The serve module runs
uvicorn on a selector event loop, which the async Postgres driver needs.

## Enabling real providers

| Feature | Set in `.env` |
|---|---|
| **Free:** Gemini for analysis, interviewing, follow-ups, evaluation | `AI_PROVIDER=gemini`, `AI_API_KEY=` (free key from aistudio.google.com), `AI_MODEL=gemini-3.5-flash`, `AI_FAST_MODEL=gemini-3.5-flash-lite`, `AI_FALLBACK_MODEL=gemini-3.6-flash,gemini-3.1-flash-lite,gemini-3.7-flash,gemini-3.8-flash` (free tier: 20 requests/day per model) |
| **Free:** neural interviewer voice (Indian English) | `VOICE_PROVIDER=edge`, `VOICE_ID=en-IN-NeerjaNeural` (or `en-IN-PrabhatNeural`) |
| Groq / OpenRouter / local Ollama | `AI_PROVIDER=openai_compat`, `AI_BASE_URL=…`, `AI_API_KEY=…`, model names from that service |
| OpenAI for analysis, interviewing, follow-ups, evaluation | `AI_PROVIDER=openai`, `AI_API_KEY=sk-…`, `AI_MODEL=gpt-6.1-sol`, `AI_FAST_MODEL=gpt-6-luna`, `AI_FALLBACK_MODEL=gpt-6-luna` |
| Claude instead | `AI_PROVIDER=anthropic`, `AI_API_KEY=sk-ant-…`, optionally `AI_MODEL`, `AI_FAST_MODEL`, `AI_FALLBACK_MODEL` |
| Interviewer voice from ElevenLabs (server TTS) | `VOICE_PROVIDER=elevenlabs`, `VOICE_API_KEY=…`, `VOICE_ID=…` |
| Screen snapshots analysed by Claude vision | `SCREEN_ANALYSIS_PROVIDER=ai` (needs `AI_PROVIDER=anthropic`) |
| Google sign-in | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (redirect URI `http://localhost:3000/api/auth/google/callback`) |
| S3 storage | `STORAGE_BACKEND=s3`, `STORAGE_S3_BUCKET`, `STORAGE_S3_REGION`, plus AWS credentials from the standard chain |

## Code execution backends

The worker uses Docker by default. Each run gets a fresh container with no network, 256 MB of memory,
0.5 CPU, 64 PIDs, a read-only root filesystem and a non-root user. If Docker isn't running and
`EXECUTION_ALLOW_LOCAL=true` is set (development only), the worker falls back to a local subprocess.
The UI labels these runs "dev sandbox". The local backend is refused when `ENVIRONMENT=production`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "The code runner is unavailable" | Start the worker; check `curl localhost:8101/health` shows `"backend":"docker"` |
| Port already in use | Ports are configurable: `API_PORT`, `WORKER_PORT`, `PUBLIC_API_URL`, `WORKER_URL`, `API_INTERNAL_URL` |
| Voice says "unavailable" | Use Chrome/Edge and allow the microphone, or click **Type instead**. Browser speech recognition needs internet; when it can't connect the room switches to typing automatically and the interviewer keeps speaking |
| Can't hear the interviewer | Use **Play** on the setup page — it plays the real interviewer voice. Check the tab isn't muted and the system output device |
| Report stays "generating" | The API's background loop retries stuck evaluations every few seconds; check `api.log` |
| Command center shows "no credits" / provider disabled | Add credits to the AI or ElevenLabs account. Interviews keep working on the deterministic engine / browser voice meanwhile; the provider is retried automatically after 5–10 minutes |
