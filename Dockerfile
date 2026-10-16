# Study Harness: one container serves the API and the web screen. Data lives on a volume at /data.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DB_PATH=/data/app.db WORKSPACE_ROOT=/data/workspaces PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY scripts/create_admin.py scripts/backup.py ./scripts/

RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown -R app:app /data /app
USER app
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/healthz',timeout=4)" || exit 1

# ONE worker: SQLite and the in-memory run state need a single process. --proxy-headers makes https cookies work behind the host's proxy.
CMD ["sh", "-c", "exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
