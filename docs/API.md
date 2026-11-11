# API

Base URL: `/api` (the web app proxies it). Interactive OpenAPI docs: `http://localhost:8100/api/docs`
(disabled in production).

Authentication uses an httpOnly `iv_session` cookie, a JWT set by login, register or the Google
callback. A `Bearer` header is also accepted. Unsafe methods must come from an allowed `Origin`.
Errors are always `{"detail": "<human-readable message>"}`; validation errors add an `errors` array.

## Public

| Method | Path | Description |
|---|---|---|
| GET | `/config` | Brand, enabled features, voice config, whether the AI is mock |
| GET | `/catalog` | Roles, topics, interview types, durations, round kinds, languages |
| GET | `/plans` | Public plans |
| GET | `/health` | DB status and provider summary |
| POST | `/demo/start` | Creates a guest session and a short AWS Data Engineer interview |
| GET | `/invites/{token}` | Invite details (org, template) |

## Auth & profile

| Method | Path | Body / notes |
|---|---|---|
| POST | `/auth/register` | `{email, password(≥8), full_name, account_type: candidate\|organization}` |
| POST | `/auth/login` | `{email, password}` |
| POST | `/auth/logout` | |
| GET | `/auth/me` | Current user + org memberships |
| GET | `/auth/google/start` → `/auth/google/callback` | OAuth (only when configured) |
| GET/PUT | `/me/profile` | Experience, target role, headline… |
| DELETE | `/me` | Delete the account and all candidate data |

## Documents

| Method | Path | Notes |
|---|---|---|
| POST | `/documents/resume` | multipart `file` (PDF/DOCX ≤ 8 MB, content-sniffed). Returns detected skills |
| GET | `/documents/resume/{id}/url` | Short-lived signed URL (owner or org reviewer) |
| POST | `/documents/jd` | `{title, text}` |
| POST | `/documents/jd/upload` | multipart `file` (PDF/DOCX/TXT), `title` |
| GET | `/files/{key}?exp&sig` | Serves local-storage objects with a valid signature |

## Interviews (candidate)

| Method | Path | Notes |
|---|---|---|
| GET | `/interviews` | Own interviews |
| POST | `/interviews` | `{role_key, interview_type, duration_minutes, difficulty, resume_id?, jd_id?}` → analysis + plan. Enforces plan limits (402) |
| GET | `/interviews/{id}` | Plan, analysis, consent, `live` state |
| DELETE | `/interviews/{id}` | Deletes transcript, code, snapshots, report |
| POST | `/interviews/{id}/consent` | `{microphone, ai_processing*, data_retention_ack*, screen_share, camera}` |
| POST | `/interviews/{id}/ws-ticket` | `{ticket, ws_url, voice}`. Ticket valid 120 s, bound to this interview |
| GET | `/interviews/{id}/transcript` | Owner or org reviewer |
| GET | `/interviews/{id}/report` | 409 while still generating |
| POST | `/interviews/{id}/code/run` | `{code, language}`. Visible tests (or SQL result) |
| POST | `/interviews/{id}/code/submit` | All tests incl. hidden; triggers the code-review question |
| GET | `/interviews/{id}/code` | Code sessions and executions |
| GET/PUT | `/interviews/{id}/design` | System design graph `{nodes, edges, notes}` |
| POST | `/interviews/{id}/screen-events` | multipart `event_type` (started/stopped/snapshot/denied), `reason`, `image` (requires screen consent) |
| POST | `/invites/{token}/accept` | Joins the org as candidate and creates the templated interview |

## WebSocket

`ws://<api>/ws/interviews/{id}?ticket=<ticket>`. Every server message has the same shape:

```json
{ "event_type": "QUESTION_STARTED", "interview_id": "…", "timestamp": "2026-10-07T17:00:00Z", "payload": { } }
```

**Client → server:** `START`, `ANSWER {text, source: voice|typed}`, `TRANSCRIPT_PARTIAL {text}`,
`CODE_CHANGED {code}`, `END`, `PING`, `REQUEST_STATE`, `VOICE_SESSION_STARTED {provider}`,
`VOICE_USAGE {stt_seconds, avg_latency_ms, provider}`.

**Server → client:** `STATE_SYNC` (full public state; sent on connect, flagged `resumed` when
resuming), `INTERVIEW_STARTED`, `ROUND_STARTED`, `QUESTION_STARTED`, `FOLLOWUP_GENERATED`,
`CODING_STARTED`, `CODE_EXECUTED`, `CODE_REVIEW_STARTED`, `ROUND_COMPLETED`,
`AI_SPEAKING {segments[], audio?}`, `AI_THINKING`, `TRANSCRIPT_PARTIAL`, `TRANSCRIPT_FINAL`,
`SCREEN_SHARE_STARTED`, `SCREEN_SHARE_STOPPED`, `SCREEN_SNAPSHOT_RECEIVED`, `INTERVIEW_ENDING`,
`INTERVIEW_COMPLETED {report_id}`, `ERROR {code, message}`, `PONG`.

Scores are never sent over the socket during the interview, so the candidate doesn't get coached.

## Organization (admin/reviewer of the caller's org)

The organization is resolved from the caller's membership. `X-Org-Id` can only pick between orgs the
caller already belongs to.

| Method | Path | Notes |
|---|---|---|
| POST | `/organizations` | Create org (caller becomes admin; 30-day College trial) |
| GET | `/organization` | Dashboard stats, top/weak skills, distributions, recent |
| GET | `/organization/candidates` | Filters: `q, role, status, review, min_score, max_score, sort, page` |
| GET | `/organization/candidates/{user_id}` | Profile, resumes, interviews, latest report |
| PATCH | `/organization/interviews/{id}/review` | `{review_status, notes}` (human decision) |
| GET | `/organization/compare?ids=a,b,c` | Side-by-side (max 4) |
| GET | `/organization/export.csv` | CSV-injection-safe export |
| GET | `/organization/reports` | Cohort aggregates |
| GET/POST/PUT/DELETE | `/organization/templates[/{id}]` | Template builder |
| POST | `/organization/templates/{id}/invites` | `{label, max_uses, expires_in_days, email_domain?}` |
| PATCH | `/organization/invites/{id}?active=` | Enable/disable |
| PUT | `/organization/settings` | Name, kind, pass threshold, retention days |
| POST | `/organization/delete` | `{confirm_name}` |
| GET/POST/DELETE | `/organization/knowledge[/{id}]` | RAG documents (text or file) |
| POST | `/organization/knowledge/search` | `{query}` → top chunks |

## Super admin

`/admin/command-center`, `/admin/users` (+PATCH), `/admin/organizations` (+PATCH plan/limits),
`/admin/usage`, `/admin/questions` (CRUD), `/admin/billing`, `/admin/billing/plans/{id}` (PUT),
`/admin/billing/pricing` (PUT pricing JSON + FX rate), `/admin/audit-logs`.

## Worker (internal; `X-Worker-Token` required)

`POST /execute {language, code, function_name, tests[{name,args}], timeout_ms}` ·
`POST /sql {dataset, query, timeout_ms}` · `GET /health`
