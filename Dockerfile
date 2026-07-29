FROM denoland/deno:bin-2.9.4 AS deno
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DENO_DIR=/tmp/deno-cache \
    PORT=8000

COPY --from=deno /deno /usr/local/bin/deno

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && deno --version

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY app ./app

RUN groupadd --system bot \
    && useradd --system --gid bot --home-dir /app bot \
    && mkdir -p /app/downloads /app/logs /tmp/deno-cache \
    && chown -R bot:bot /app /tmp/deno-cache

USER bot

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:${PORT}/health >/dev/null || exit 1

CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
