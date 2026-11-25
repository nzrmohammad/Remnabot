FROM node:20-alpine AS assets

WORKDIR /build
COPY package.json package-lock.json tailwind.config.js ./
RUN npm ci --no-audit --no-fund
COPY bot/web/ ./bot/web/
COPY scripts/ ./scripts/
RUN npm run build:css && npm run build:js

FROM python:3.12-slim

WORKDIR /app

RUN mkdir -p /app/backups /app/data && \
    useradd -m -u 10001 botuser && \
    chown -R botuser:botuser /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=botuser:botuser alembic.ini ./
COPY --chown=botuser:botuser alembic/ ./alembic/
COPY --chown=botuser:botuser bot/ ./bot/
COPY --from=assets --chown=botuser:botuser /build/bot/web/static/css/tailwind.min.css ./bot/web/static/css/tailwind.min.css
COPY --from=assets --chown=botuser:botuser /build/bot/web/static/js/dist ./bot/web/static/js/dist
USER botuser

# Liveness: bot/services heartbeat touches /tmp/bot_heartbeat every 60s.
HEALTHCHECK --interval=60s --timeout=10s --start-period=90s --retries=3 \
  CMD python -c "import os,tempfile,time,sys; p=os.path.join(tempfile.gettempdir(), 'bot_heartbeat'); sys.exit(0 if (os.path.exists(p) and time.time()-os.path.getmtime(p)<180) else 1)"

CMD ["sh", "-c", "python -m bot.db.migrate && exec python -m bot.main"]
