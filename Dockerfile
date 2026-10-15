FROM python:3.14-slim

# ENVIRONMENT=production makes the server refuse to start without JWT_SECRET.
# FORWARDED_ALLOW_IPS lets uvicorn read the client IP from the hosting
# platform's proxy, which the login rate limiter relies on.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ENVIRONMENT=production \
    DATABASE_PATH=/data/app.db \
    PORT=8000 \
    FORWARDED_ALLOW_IPS=*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /data \
    && chown app:app /data

COPY server.py index.html login.html docker-entrypoint.sh ./
# Builds from a Windows checkout can carry CRLF line endings, which break sh
RUN sed -i 's/\r$//' docker-entrypoint.sh

# Starts as root only to fix /data ownership; the server itself runs as "app".
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), timeout=4)"

# Single worker: SQLite has one writer and the login limiter is in-memory.
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
