# IntervueAI

AI-powered, role-specific interview practice and assessment. A candidate uploads a resume and a job
description, gets a personalised plan, and goes through a voice interview with adaptive follow-ups,
live coding in an isolated sandbox, SQL and system design rounds. The interview ends with an
evidence-based report. Colleges and companies run the same interviews at scale through templates
and invite links, with cohort dashboards.

> "IntervueAI" is a placeholder name. Change `NEXT_PUBLIC_BRAND_NAME` / `BRAND_NAME` to rebrand.

## What works out of the box (no API keys)

| Area | Status |
|---|---|
| Auth (email/password, Google OAuth when configured), RBAC, tenant isolation | ✅ |
| Onboarding: profile → resume (PDF/DOCX) → JD (role / paste / upload) → preferences → plan | ✅ |
| Resume/JD analysis with hallucination guard, plan generation | ✅ (deterministic engine; Claude when `AI_PROVIDER=anthropic`) |
| Interview state machine, adaptive difficulty, follow-ups, no repeated questions | ✅ |
| Voice interviewer (browser speech-to-text + text-to-speech, barge-in, typed fallback) | ✅ (Chrome/Edge; ElevenLabs TTS optional) |
| Monaco coding (Python / JavaScript / TypeScript) with hidden tests in Docker sandbox | ✅ |
| SQL round on an isolated read-only database | ✅ |
| Screen sharing with consented, compressed snapshots | ✅ |
| System design canvas | ✅ |
| Evidence-verified evaluation + report (9 categories, practice plan, PDF export) | ✅ |
| Organization dashboard, candidates, compare, CSV export, templates, invite links, knowledge base (RAG) | ✅ |
| Super-admin command center, usage & cost per interview, question bank, plans & pricing | ✅ |
| Demo mode (no sign-up, AWS Data Engineer) | ✅ |

Everything that is mock or local is labelled in the UI, for example "Local AI engine (mock)" and "dev sandbox".

## Quick start

```bash
bash scripts/setup.sh        # venv, npm install, .env with fresh secrets, Postgres, migrations, seed
bash scripts/dev.sh          # worker :8101, API :8100, web :3000   (Windows: scripts/dev.ps1)
```

Open http://localhost:3000. Use **Try a Demo**, or sign in with the accounts in
[DEMO_CREDENTIALS.md](DEMO_CREDENTIALS.md). The full guide is in [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md).

To use Claude for analysis, interviewing and evaluation, set `AI_PROVIDER=anthropic` and
`AI_API_KEY=…` in `.env` and restart the API.

## Repository

```
apps/web          Next.js 16 + React 19 + Tailwind 4 + shadcn/ui (Base UI) — all UI
apps/api          FastAPI — REST + WebSocket, persistence, orchestration
apps/worker       Isolated code-execution service (Docker sandbox)
packages/ai               AIProvider / EmbeddingProvider / pricing
packages/interview-engine State machine, planner, question bank, FollowUpAgent, tools
packages/evaluation       Scoring, evidence verification, report aggregation
packages/coding           Problems, harness, SQL sandbox, grading, worker client
packages/voice            Server VoiceProvider (browser / ElevenLabs / mock)
packages/security         Argon2, JWT, upload validation, signed URLs, rate limiter
packages/types|config     Shared TS types and branding
infra/docker|terraform    Compose stack, Dockerfiles, AWS reference
tests/python              pytest suite (unit, API, authz, sandbox security)
apps/web/tests            Vitest unit tests + Playwright critical-path e2e
```

## Quality gates

```bash
.venv/Scripts/python -m pytest -q          # 45 Python tests
ruff check . && ruff format --check .      # Python lint
mypy packages/*/intervue_* apps/api/app apps/worker/worker
npm run lint -w web && npm run typecheck -w web && npm run test -w web
npm run test:e2e -w web                    # needs the stack running + seeded
```

## Documentation

[ARCHITECTURE.md](ARCHITECTURE.md) · [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md) ·
[docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md) · [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) ·
[docs/API.md](docs/API.md) · [docs/DATABASE.md](docs/DATABASE.md) · [docs/SECURITY.md](docs/SECURITY.md) ·
[docs/AI_ARCHITECTURE.md](docs/AI_ARCHITECTURE.md) · [docs/COST_MODEL.md](docs/COST_MODEL.md) ·
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) · [docs/PRODUCT_ROADMAP.md](docs/PRODUCT_ROADMAP.md) ·
[docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)
