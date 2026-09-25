FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/

RUN useradd -m -u 10001 botuser && chown -R botuser:botuser /app
USER botuser

# Liveness: bot/services heartbeat touches /tmp/bot_heartbeat every 60s.
HEALTHCHECK --interval=60s --timeout=10s --start-period=90s --retries=3 \
  CMD python -c "import os,tempfile,time,sys; p=os.path.join(tempfile.gettempdir(), 'bot_heartbeat'); sys.exit(0 if (os.path.exists(p) and time.time()-os.path.getmtime(p)<180) else 1)"

CMD ["python", "-m", "bot.main"]
