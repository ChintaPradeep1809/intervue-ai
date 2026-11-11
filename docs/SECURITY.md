# Security

## Threat model (summary)

| Asset | Threats | Controls |
|---|---|---|
| Candidate data (resumes, transcripts, code, snapshots) | Cross-tenant access, leakage | Server-side tenant resolution, 404 on foreign resources, signed short-lived file URLs, retention purge, account/interview deletion |
| Platform hosts | Malicious candidate code | Execution only in the separate worker; per-run Docker sandbox with no network |
| Accounts | Credential stuffing, session theft, CSRF | Argon2id, rate limits, httpOnly SameSite=Lax cookies, Origin allow-list for unsafe methods |
| AI pipeline | Prompt injection via resume/JD/answers, hallucinated claims | Structured outputs, schema validation, deterministic business rules, evidence verification, skill verification |
| Secrets | Exposure to browser/logs | Server-only env vars, never logged, never sent to the client |

## Authentication & authorization

- Passwords: Argon2id (`argon2-cffi`), minimum 8 characters, rehashed on login when parameters change.
- Sessions: HS256 JWT in an httpOnly cookie, `Secure` in production, `SameSite=Lax`, 72 h TTL.
  Purpose-bound tokens: `session`, `ws` (120 s ticket bound to one interview).
- Roles: `candidate`, `organization_admin`, `super_admin`. Org membership roles: `admin`, `reviewer`,
  `candidate`. The API checks roles on every endpoint; the web route guard is only cosmetic.
- CSRF: cookie auth plus `SameSite=Lax`, and unsafe methods with a foreign `Origin` are rejected (403).
- Google OAuth: `state` parameter checked against a cookie, and the email must be verified.

## Tenant isolation

The client-supplied `organization_id` is never trusted. The org is derived from membership, and
`X-Org-Id` only picks between orgs the caller already belongs to. Tested in
`test_organization_workflow_and_tenant_isolation` and `test_candidate_cannot_access_other_candidates_interview`.

## Code execution isolation (`apps/worker`)

- The API never executes candidate code. It calls the worker over HTTP with a shared `WORKER_TOKEN`.
- Docker backend, one container per run: `--network none`, `--memory 256m --memory-swap 256m`,
  `--cpus 0.5`, `--pids-limit 64`, `--read-only`, `--tmpfs /tmp (16 MB, nosuid)`, `--cap-drop ALL`,
  `--security-opt no-new-privileges`, `--user 65534:65534`, `--ulimit nofile/fsize`, `--init`, plus
  an in-container `timeout -s KILL`. A timed-out container is force-removed. Code goes in over
  stdin; nothing from the host is mounted.
- Expected outputs never enter the sandbox. The harness returns actual values and the API grades them,
  so candidates can't read hidden expectations. Hidden test arguments aren't returned to the client either.
- SQL runs on an in-memory SQLite database with an authorizer that allows only SELECT/READ/FUNCTION,
  blocks `load_extension`/file functions, allows one statement, and stops runaway queries with a
  progress-handler deadline.
- Inputs are validated: `function_name` must be an identifier, the language is allow-listed, and code
  and test sizes are capped.
- The local backend is for development only. It is refused when `ENVIRONMENT=production` and its runs
  are labelled in the UI.
- Production hardening: run the worker on a dedicated node pool with gVisor/Kata/Firecracker and talk
  to the container runtime without mounting the host Docker socket.

These properties are covered by `tests/python/test_coding_sandbox.py`.

## Uploads & storage

- Allow-listed extensions, and content-sniffed MIME types must match (a PDF must start with `%PDF-`; a
  DOCX must be a ZIP containing `word/document.xml`). Size limits apply, filenames are sanitised, and
  files are never executed.
- Text extraction is capped at 20 pages and 60k characters; encrypted PDFs are rejected.
- Screen snapshots are re-decoded and re-encoded server-side (metadata stripped, ≤1280 px, JPEG q70),
  and only accepted when screen-share consent was given.
- Local storage serves files only with a valid HMAC signature and expiry; S3 uses presigned URLs, SSE
  and blocked public access. Served files get `nosniff` and a sandboxed CSP.

## Rate limiting

In-process sliding window per IP and route group: login 10/min, register 5/min, demo 5/h, uploads
20/h, interview creation 30/h, code runs 30/min, everything else 600/min. The WebSocket allows 120
messages/min. For multiple API replicas, swap `RateLimiter` for a Redis implementation with the same
interface.

## AI guardrails

- Every LLM output is validated against a Pydantic schema; invalid output is retried, falls back to the
  next provider, and finally to the deterministic engine.
- Resume skills claimed by the model are kept only if present in the resume text. The interviewer may
  reference only verified skills.
- Evaluator quotes must appear verbatim in the transcript, code or design; unverifiable quotes are
  dropped and confidence is lowered. Code correctness is pinned to measured test results.
- The state machine owns all transitions. The LLM can propose follow-ups but can't skip rounds, extend
  time or change scores after the fact. Only read-only tools are exposed to the model.
- No automatic hiring decisions: reports carry a disclaimer, and orgs record human review decisions.

## Logging, audit, privacy

- JSON logs with request IDs and interview IDs. Passwords, tokens and keys are never logged; failed
  logins record only the attempted email.
- `audit_logs` records registration and login, consent, exports, deletions, reviews, template and
  invite changes, and admin changes.
- Consent covers AI processing, data storage, microphone and screen sharing, each explicit and
  recorded with a timestamp and IP. No audio or video is recorded; camera is self-view only.
- Candidates can delete interviews or their account; orgs can delete themselves; retention is
  configurable.

## Reporting vulnerabilities

Email the address in `NEXT_PUBLIC_SUPPORT_EMAIL`. Please don't open public issues for security reports.
