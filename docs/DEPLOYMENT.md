# Deployment

## Components

| Component | Runtime | Scaling notes |
|---|---|---|
| `web` | Next.js (`next start`) or Vercel | Stateless; set `API_INTERNAL_URL` for the `/api` rewrite |
| `api` | FastAPI on uvicorn | Holds WebSocket connections; enable sticky sessions, or move the hub to Redis pub/sub for >1 replica |
| `worker` | FastAPI + container runtime | Isolated node pool, no public ingress, sandbox runtime (gVisor/Kata) |
| Postgres | RDS / Supabase / Cloud SQL | Run `alembic upgrade head` on deploy (the API image does this on start) |
| Object storage | S3 (or compatible) | `STORAGE_BACKEND=s3`, SSE-KMS, public access blocked |

## Docker Compose (single host / staging)

```bash
cp .env.example .env   # set ENVIRONMENT=production, AUTH_SECRET, WORKER_TOKEN, keys
docker compose -f infra/docker/docker-compose.yml --profile full up -d --build
docker compose -f infra/docker/docker-compose.yml exec api python -m app.seed   # optional demo data
```

The `worker` service mounts the Docker socket to launch sandboxes. That's acceptable on a dedicated
staging host but **not** on shared production hosts; see below.

## AWS reference (see `infra/terraform/main.tf`)

1. **Network:** VPC with public subnets (ALB) and private subnets (ECS tasks, RDS, worker).
2. **API & web:** ECS Fargate services behind an ALB. Raise the ALB idle timeout to ≥300 s for
   WebSockets. Two or more API tasks with sticky sessions, or a Redis-backed hub.
3. **Worker:** ECS on EC2 (or EKS) capacity reserved for sandboxes with the gVisor `runsc` runtime.
   Security groups allow ingress only from the API; sandbox containers run with `--network none`.
4. **Database:** RDS PostgreSQL 16 Multi-AZ, automated backups, `pgvector` extension.
5. **Storage:** S3 bucket from the Terraform skeleton; the API role gets `s3:GetObject/PutObject/DeleteObject` on it only.
6. **Secrets:** Secrets Manager → ECS task environment (`AUTH_SECRET`, `AI_API_KEY`, `VOICE_API_KEY`,
   `WORKER_TOKEN`, `DATABASE_URL`).
7. **Observability:** ship JSON logs to CloudWatch, alarm on `http_5xx`, `interviews_failed`, AI
   fallbacks and p95 latencies (all in the command center); add an error tracker (Sentry/OTel) behind
   `app/services/metrics.py`.

## Production checklist

- [ ] `ENVIRONMENT=production` (enforces a strong secret, non-default worker token, Secure cookies; disables `/api/docs`)
- [ ] `PUBLIC_WEB_URL`, `PUBLIC_API_URL` (wss behind TLS), `CORS_ORIGINS` set to real origins
- [ ] `EXECUTION_BACKEND=docker`, `EXECUTION_ALLOW_LOCAL=false`, worker on an isolated runtime
- [ ] `AI_PROVIDER=anthropic` with `AI_API_KEY`; optional `AI_FALLBACK_MODEL`
- [ ] Pricing reviewed in Admin → Plans & pricing; plan limits set
- [ ] S3 storage, backups, retention days per organization
- [ ] Rate limiter moved to Redis if running multiple API replicas
- [ ] Don't run `app.seed` against production (demo passwords)
