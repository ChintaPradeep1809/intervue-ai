# The worker launches one throwaway sandbox container per execution via the Docker socket.
# In production prefer a dedicated sandbox host/runtime (gVisor, Firecracker or a separate node pool)
# rather than mounting the host socket. See docs/SECURITY.md.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends docker.io && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY packages/coding ./packages/coding
COPY apps/worker ./apps/worker
RUN pip install --no-cache-dir -e packages/coding -e apps/worker
WORKDIR /srv/apps/worker
ENV WORKER_HOST=0.0.0.0 WORKER_PORT=8101 EXECUTION_BACKEND=docker EXECUTION_ALLOW_LOCAL=false
EXPOSE 8101
CMD ["python", "-m", "worker.serve"]
