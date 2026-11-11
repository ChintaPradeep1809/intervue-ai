FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY packages ./packages
COPY apps/api ./apps/api
COPY config ./config
RUN pip install --no-cache-dir -e packages/security -e packages/ai -e packages/evaluation -e packages/coding \
    -e packages/voice -e packages/interview-engine -e apps/api \
 && useradd --create-home --uid 10001 app && mkdir -p /srv/var && chown -R app /srv/var
USER app
WORKDIR /srv/apps/api
ENV API_HOST=0.0.0.0 API_PORT=8100 PRICING_CONFIG_PATH=/srv/config/pricing.json
EXPOSE 8100
CMD ["sh", "-c", "alembic upgrade head && python -m app.serve"]
