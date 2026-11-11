# Database

PostgreSQL 16 (Supabase-compatible) via SQLAlchemy 2 async + psycopg 3. The schema lives in
`apps/api/app/models.py`; migrations are in `apps/api/alembic/versions` (`alembic upgrade head`).
JSON columns use `JSONB` on Postgres (and `JSON` on SQLite, which the tests use).

## Tables

| Group | Table | Purpose |
|---|---|---|
| Identity | `users` | Email, Argon2id hash (nullable for OAuth), role, demo flag, Google subject |
| | `candidate_profiles` | Experience, target role, onboarding state, preferences |
| Tenancy | `organizations` | Name, slug, kind, settings (pass threshold, retention days) |
| | `organization_members` | (org, user, role: admin\|reviewer\|candidate), unique per pair |
| Documents | `resumes` | Storage key, filename, MIME, size, extracted text |
| | `job_descriptions` | Pasted/uploaded JD text |
| Content | `interview_templates` | Org (or platform-wide when `organization_id` is null) rounds, weights, JD |
| | `questions` | Question bank: topic, kind, difficulty, concepts, follow-ups, roles |
| | `invites` | Tokenised links: max uses, expiry, email-domain restriction |
| Interviews | `interviews` | Plan, analysis, **persisted state machine** (`state` JSONB), consent, score, human review |
| | `interview_rounds` | Per-round status/timestamps |
| | `interview_questions` | Every question/follow-up actually asked, with expected concepts |
| | `responses` | Candidate answers |
| | `transcripts` | Ordered interviewer/candidate lines |
| | `code_sessions`, `code_executions` | Final code and every run/submit with results |
| | `design_sessions` | System design graph |
| | `screen_events` | Share started/stopped/denied + compressed snapshots and analysis |
| | `evaluations` | Per-answer `AnswerScore` (categories, verified evidence) |
| | `reports` | Final report JSON |
| Billing & ops | `plans`, `subscriptions`, `organization_limits` | Plans, assignment, per-org overrides |
| | `usage_records` | Every metered AI/voice/TTS/embedding/execution/storage event with cost |
| | `cost_records` | Per-interview cost roll-up (USD + INR) |
| | `analytics_events` | Product analytics events (see below) |
| | `audit_logs` | Security-relevant actions (login, consent, exports, deletes, admin changes) |
| | `knowledge_documents`, `knowledge_chunks` | RAG corpus with embeddings |
| | `app_settings` | Runtime overrides (pricing, FX rate) |

## Indexes

Every foreign key is indexed, plus `interviews (organization_id, status)`,
`interviews (candidate_id, created_at)`, `transcripts (interview_id, sequence)`,
`usage_records (organization_id, created_at)`, and unique indexes on `users.email`,
`organizations.slug`, `questions.bank_key` and `invites.token`.

## Tenant isolation

Organization-scoped rows carry `organization_id`. Org endpoints resolve the org from the caller's
membership (`app/deps.py::org_context`) and filter every query by it. Interview access goes through
`can_view_interview` (owner, super admin, or admin/reviewer of the interview's org). A request for a
resource outside the caller's tenant returns 404, so existence isn't revealed. The behaviour is
covered by `tests/python/test_api.py::test_organization_workflow_and_tenant_isolation`.

## Analytics events

`interview_created`, `interview_started`, `interview_completed`, `question_answered`,
`coding_started`, `code_run`, `code_submitted`, `screen_share_started`, `screen_share_stopped`,
`voice_session_started`, `report_generated`, `jd_uploaded`.

## Retention

The API's background loop runs `purge_expired()` hourly. It deletes interviews (cascading to
transcripts, code, snapshots, evaluations and reports) older than the organization's
`retention_days`, `DATA_RETENTION_DAYS` for individual candidates, or 7 days for demo sessions.

## Seed

`python -m app.seed [--reset]` loads plans, the question bank, templates, demo accounts and an
organization with 10 simulated candidates. See [DEMO_CREDENTIALS.md](../DEMO_CREDENTIALS.md).
