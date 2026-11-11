# Environment variables

All configuration comes from the environment (`.env` at the repo root in development). Secrets are
never sent to the browser. Only `NEXT_PUBLIC_*` variables reach client code.

## API (`apps/api/app/config.py`)

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` enforces a strong `AUTH_SECRET`, a non-default `WORKER_TOKEN` and secure cookies |
| `BRAND_NAME` | `IntervueAI` | Product name used by the API |
| `PUBLIC_WEB_URL` | `http://localhost:3000` | Invite links, OAuth redirects, allowed origin |
| `PUBLIC_API_URL` | `http://localhost:8100` | Used to build the WebSocket URL |
| `CORS_ORIGINS` | `["http://localhost:3000", …]` | JSON list; also the CSRF origin allow-list |
| `DATABASE_URL` | local Postgres on 54329 | `postgresql+psycopg://…`; tests use `sqlite+aiosqlite://…` |
| `AUTH_SECRET` | dev placeholder | **Required** in production; ≥32 random characters |
| `SESSION_TTL_HOURS` | `72` | Session cookie lifetime |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | empty | Google button appears only when both are set |
| `AI_PROVIDER` | `mock` | `mock` (deterministic local engine), `gemini` (free tier), `openai`, `anthropic` or `openai_compat` |
| `AI_API_KEY` | empty | API key for the selected provider |
| `AI_BASE_URL` | empty | Required for `openai_compat` (e.g. `https://api.groq.com/openai/v1`, `http://localhost:11434/v1` for Ollama) |
| `AI_MODEL` | `claude-opus-5-5` | Primary model (scoring, analysis, report). Local `.env` uses `gpt-6.1-sol` |
| `AI_FALLBACK_MODEL` | empty | Optional fallback model(s), comma-separated, tried in order before the deterministic fallback |
| `AI_FAST_MODEL` | empty | Model for live turns (follow-ups, personalisation, code-review questions); e.g. `gpt-6-luna` |
| `AI_TIMEOUT_SECONDS` | `60` | Per-call timeout |
| `VOICE_PROVIDER` | `browser` | `browser`, `edge` (free neural voices, no key), `elevenlabs` or `mock` |
| `VOICE_API_KEY`, `VOICE_ID` | empty / premade voice | ElevenLabs key and voice (free plans can only use *premade* voices). For `edge`, `VOICE_ID` is an Edge voice name such as `en-IN-NeerjaNeural`; its locale also sets the speech-recognition language |
| `SCREEN_ANALYSIS_PROVIDER` | `mock` | `ai` uses vision through `AI_PROVIDER` |
| `EMBEDDING_PROVIDER` | `local` | Feature-hashing embeddings (no key) |
| `STORAGE_BACKEND` | `local` | `local` (HMAC-signed URLs) or `s3` (presigned URLs) |
| `STORAGE_LOCAL_ROOT` | `var/storage` | Local object store |
| `STORAGE_S3_BUCKET`, `STORAGE_S3_REGION`, `STORAGE_URL` | — | S3 settings |
| `VECTOR_DB_URL`, `VECTOR_DB_API_KEY` | empty | Reserved for an external vector store |
| `WORKER_URL` | `http://localhost:8101` | Execution worker |
| `WORKER_TOKEN` | placeholder | Shared secret between API and worker |
| `PRICING_CONFIG_PATH` | `config/pricing.json` | Unit prices for the cost model |
| `USD_INR_RATE` | `83.0` | Default FX rate; super admins can override it at runtime |
| `DATA_RETENTION_DAYS` | `365` | Default retention for individual candidates (orgs set their own) |
| `MAX_UPLOAD_MB` | `8` | Resume/JD upload limit |
| `DEMO_ENABLED`, `DEMO_DURATION_MINUTES` | `true`, `8` | Demo mode |
| `MAX_FOLLOWUPS` | `2` | Follow-ups per primary question |
| `API_HOST`, `API_PORT`, `LOG_LEVEL` | `127.0.0.1`, `8100`, `info` | Server |

## Worker (`apps/worker/worker/main.py`)

| Variable | Default | Notes |
|---|---|---|
| `WORKER_TOKEN` | — | Must match the API |
| `EXECUTION_BACKEND` | `docker` | `docker` or `local` |
| `EXECUTION_ALLOW_LOCAL` | `false` | Allows the local subprocess backend (ignored in production) |
| `SANDBOX_PYTHON_IMAGE`, `SANDBOX_NODE_IMAGE` | `python:3.12-alpine`, `node:24-alpine` | Sandbox images |
| `WORKER_CONCURRENCY` | `4` | Parallel executions |
| `WORKER_HOST`, `WORKER_PORT` | `127.0.0.1`, `8101` | Server |

## Web (`apps/web`)

| Variable | Default | Notes |
|---|---|---|
| `API_INTERNAL_URL` | `http://localhost:8100` | Rewrite target for `/api/*` (server side) |
| `NEXT_PUBLIC_BRAND_NAME` | `IntervueAI` | Product name in the UI |
| `NEXT_PUBLIC_SUPPORT_EMAIL` | `support@example.com` | Footer/contact links |
| `E2E_BASE_URL` | `http://localhost:3000` | Playwright target |
