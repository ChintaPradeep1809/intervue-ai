# Product Requirements — IntervueAI (MVP)

"IntervueAI" is a working name; it is configured in `packages/config` (web) and `BRAND_NAME` (API).

## Problem
Candidates lack realistic, role-specific interview practice; colleges and companies can't run
consistent first-round technical screens at scale.

## Users & jobs-to-be-done
| Role | Primary jobs |
|---|---|
| Candidate | Practice a realistic interview for a target role; get evidence-based feedback and a study plan. |
| Organization admin (college, institute, company) | Create interview templates, invite candidates via link, review structured results, compare and export. |
| Super admin | Operate the platform: orgs, plans, question bank, usage, cost, health. |

## MVP scope (priority order)
**P0** — auth (email/password; Google OAuth when configured) · onboarding (resume PDF/DOCX, JD
paste/upload/role) · resume/JD analysis · interview plan · interview state machine · voice
interviewer (browser STT/TTS with server provider abstraction) · adaptive follow-ups · transcript ·
evaluation with verified evidence · final report.

**P1** — Monaco coding round (Python, JavaScript/TypeScript) · isolated execution · SQL round with
schema + graded execution · screen sharing with consented snapshots.

**P2** — system-design canvas · organization dashboard, templates, invites, compare, CSV export ·
multi-tenancy · RAG knowledge base · usage analytics.

**P3** — plans/subscriptions/limits (no payment processor yet) · command center · cost model.

## Flagship configuration
AWS Data Engineer — 2 years: SQL, Python, PySpark, AWS (S3, Glue, Athena, Redshift), Airflow,
Kafka, data modelling, ETL, data quality, system design, behavioural.

## Non-goals (MVP)
Automatic hiring decisions (AI assists, humans decide) · proctoring/anti-cheat · video recording ·
payment collection · native mobile apps.

## Acceptance criteria
- A new user can register, onboard with a resume, generate a plan and complete a full interview
  (voice or typed fallback) that includes a coding round, and see a report — with no API keys set.
- Every score shown in a report links to evidence that exists verbatim in the transcript or code.
- Candidate code never executes in the API process; the worker enforces time/memory/network limits.
- An org admin can create a template, generate an invite link, and see the invited candidate's
  result in the org dashboard; another org can't see it (tested).
- Mock/demo functionality is labelled in the UI.

## Privacy commitments
Explicit consent before microphone, screen share and AI analysis; no audio/video recording;
snapshots only on visible events; configurable retention (`DATA_RETENTION_DAYS`); org deletion.
