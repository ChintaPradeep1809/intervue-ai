# Architecture

IntervueAI is a multi-tenant SaaS for AI-conducted technical interviews. This document is the
system map; deeper dives live in [docs/](docs/).

## 1. System diagram

```
                         ┌──────────────────────────────────────────────┐
  Browser (Next.js 16)   │  apps/web                                     │
  ───────────────────    │  • Landing, auth, onboarding, dashboards      │
  Web Speech STT/TTS ◄──►│  • Interview room (voice, transcript, timer)  │
  getDisplayMedia ──────►│  • Monaco editor, SQL console, design canvas  │
                         │  • lib/voice: VoiceProvider (browser|server)  │
                         └───────┬───────────────────────┬──────────────┘
                     REST /api/* │ (Next rewrite → :8100)│ WebSocket /ws/interviews/{id}?ticket=
                                 ▼                       ▼
                         ┌──────────────────────────────────────────────┐
                         │  apps/api  (FastAPI)                          │
                         │  routers → services → repositories (SQLA 2)   │
                         │  ├─ auth / RBAC / tenant guard / rate limit   │
                         │  ├─ InterviewOrchestrator  (packages/         │
                         │  │    interview-engine: state machine, tools, │
                         │  │    follow-up agent, question selection)    │
                         │  ├─ Evaluation (packages/evaluation)          │
                         │  ├─ AI + Embedding providers (packages/ai)    │
                         │  ├─ Voice providers (packages/voice)          │
                         │  ├─ Storage (local signed URLs | S3)          │
                         │  └─ Usage, cost, analytics, audit log         │
                         └───────┬───────────────────────┬──────────────┘
                                 │ HTTP (internal token) │ SQL
                                 ▼                       ▼
                ┌───────────────────────────┐   ┌──────────────────────┐
                │ apps/worker (FastAPI)     │   │ PostgreSQL 16        │
                │ code execution service    │   │ (Supabase-compatible)│
                │ backend=docker: one-shot  │   └──────────────────────┘
                │  container per run,       │
                │  --network none, mem/cpu/ │   ┌──────────────────────┐
                │  pids limits, read-only   │   │ Object storage       │
                │ backend=local: dev only   │   │ local FS | S3        │
                │ SQL: in-memory SQLite     │   └──────────────────────┘
                │  with authorizer          │
                └───────────────────────────┘
```

## 2. Monorepo layout

| Path | Language | Purpose |
|---|---|---|
| `apps/web` | TS / Next.js 16 | All UI. Client-rendered app pages, static landing page. |
| `apps/api` | Python / FastAPI | REST + WebSocket API, persistence, orchestration. |
| `apps/worker` | Python / FastAPI | Isolated code execution service (never runs in the API process). |
| `packages/ai` | Python | `AIProvider`, `EmbeddingProvider`, structured-output helper, pricing/cost. |
| `packages/interview-engine` | Python | State machine, interview state schema, planner, question selection, `FollowUpAgent`, interviewer tools. |
| `packages/evaluation` | Python | Per-answer scoring, evidence verification, category aggregation, report builder. |
| `packages/voice` | Python | Server-side `VoiceProvider` (browser passthrough, ElevenLabs TTS, mock). |
| `packages/coding` | Python | Problem catalogue, test harness generation, SQL datasets + SQL grading, worker client. |
| `packages/security` | Python | Password hashing, JWT, file validation, signed URLs, rate limiter. |
| `packages/types` | TS | Shared API/WS types used by the web app. |
| `packages/config` | TS | Branding + public product configuration (name is never hard-coded). |
| `infra/docker` | — | Compose file (Postgres, API, worker, web) + sandbox images. |
| `infra/terraform` | — | Skeleton for AWS deployment (documented, not applied). |

> `components/ui` (shadcn primitives) lives inside `apps/web` because shadcn generates into the
> consuming app; a separate `packages/ui` would only re-export it.

## 3. Key design decisions

1. **The interview is a state machine, not a chat.** `packages/interview-engine` owns phases
   (`INTERVIEW_SETUP → INTRODUCTION → TECHNICAL_QUESTION ⇄ FOLLOW_UP → CODING → CODE_REVIEW →
   SYSTEM_DESIGN → BEHAVIORAL → FINAL_EVALUATION → COMPLETED`). Transitions are validated by a
   table; the LLM can only *propose* actions from an enum. Business rules (time budget, max
   follow-ups, no repeated questions, difficulty adaptation) are deterministic Python.
2. **LLM output is always schema-validated.** Every AI call goes through
   `structured_call(schema=PydanticModel)` with retries, timeout and model fallback. Invalid output
   never reaches the UI.
3. **Evidence can't be fabricated.** Evaluator evidence is verified against the transcript/code by
   normalized substring match; unverifiable evidence is dropped. Resume skills claimed by the LLM
   are verified against resume text before the interviewer may reference them.
4. **Runs without any API keys.** `AI_PROVIDER=mock` uses a deterministic rule-based provider
   (taxonomy-based resume analysis, concept-coverage scoring, curated follow-ups). Voice defaults
   to the browser's Web Speech API. Everything mock is labelled in the UI.
5. **Code never runs in the API.** The API calls the worker over HTTP with an internal token. The
   worker's `docker` backend runs each execution in a fresh container with no network, memory,
   CPU, PID and time limits, a read-only root FS and a non-root user. The `local` backend exists
   for development only, is refused when `ENVIRONMENT=production`, and is labelled in the UI.
6. **Tenant isolation is server-side.** Every org-scoped query goes through `TenantContext`
   resolved from the authenticated membership; `organization_id` from clients is only accepted
   after a membership check.
7. **Screen sharing is consent-first and event-based.** The browser holds the display stream;
   only compressed snapshots (≤1280px JPEG) captured on explicit events are sent to the API.
8. **Cost is a first-class record.** Every AI/voice/embedding/execution/storage call writes a
   `usage_records` row; `cost_records` aggregate per interview using `config/pricing.json`
   (editable by super admin), with a configurable USD→INR rate.

## 4. Request lifecycle (answering a question)

1. Browser STT produces a final transcript → WS `CANDIDATE_ANSWER`.
2. `InterviewOrchestrator.handle_answer` loads state (row lock), appends transcript, emits
   `TRANSCRIPT_FINAL`, `AI_THINKING`.
3. `Evaluator.score_answer` → structured score + verified evidence → `responses` / `evaluations`.
4. `FollowUpAgent.decide` → follow-up (clarification/challenge/edge_case/optimization) **or**
   `QuestionSelector.next` (adaptive difficulty, no repeats) **or** round transition.
5. State persisted; WS `FOLLOWUP_GENERATED`/`QUESTION_STARTED` + `AI_SPEAKING` with text.
6. Browser TTS speaks; barge-in (candidate speech) cancels playback.

## 5. Real-time event schema

```json
{ "event_type": "QUESTION_STARTED", "interview_id": "uuid", "timestamp": "ISO-8601", "payload": {} }
```
See [docs/API.md](docs/API.md#websocket) for the full list.

## 6. Data model

See [docs/DATABASE.md](docs/DATABASE.md). PostgreSQL in all real environments; the test suite uses
SQLite in-memory through the same SQLAlchemy models.

## 7. Further reading

- [docs/AI_ARCHITECTURE.md](docs/AI_ARCHITECTURE.md) — providers, prompts, tools, guardrails
- [docs/SECURITY.md](docs/SECURITY.md) — threat model and controls
- [docs/COST_MODEL.md](docs/COST_MODEL.md) — usage metering and unit economics
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
