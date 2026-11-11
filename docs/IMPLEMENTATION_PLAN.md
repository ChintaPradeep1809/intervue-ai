# Implementation plan

Each phase ends with: `pytest`, `ruff`, `mypy` (Python) and `eslint`, `tsc` (web), plus doc updates.

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Repo inspection, ARCHITECTURE.md, PRODUCT_REQUIREMENTS.md, monorepo skeleton | done |
| 1 | API foundation: settings, logging + request IDs, SQLAlchemy models for all tables, Alembic migration, auth (argon2 + JWT cookie), RBAC, tenant guard, rate limit, audit log, storage abstraction | done |
| 2 | AI layer: `AIProvider` (mock + Anthropic), structured outputs, retries/timeout/fallback, usage + cost metering; resume/JD parsing and analysis; interview plan generation | done |
| 3 | Interview engine: state machine, question bank + seed, adaptive selection, `FollowUpAgent`, interviewer tools, WebSocket orchestration | done |
| 4 | Web foundation: design system, landing page, auth pages, app shell, onboarding wizard, interviews list/new/setup | done |
| 5 | Interview room: voice (browser provider + server TTS provider), transcript, timer, connection states, barge-in, typed fallback | done |
| 6 | Coding: worker service (docker + dev-local backends), Python/JS/TS harness, SQL sandbox + grading, Monaco UI | done |
| 7 | Screen sharing: consent, `getDisplayMedia`, snapshot compression + upload, screen-analysis provider | done |
| 8 | Evaluation + report: per-answer scoring with verified evidence, category aggregation, report page | done |
| 9 | Organizations: dashboard, candidates, templates builder, invites, compare, CSV export, settings | done |
| 10 | Super admin: command center, users, orgs, usage/cost, question bank, plans/limits | done |
| 11 | System design canvas, RAG knowledge base, demo mode | done |
| 12 | Tests (API, engine, AI schema, authz, sandbox security, web critical path), docs, docker compose | done |
