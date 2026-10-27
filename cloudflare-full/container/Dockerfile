FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1 \
    HOUSEHOLD_WEB_HOST=127.0.0.1 \
    HOUSEHOLD_WEB_PORT=8001 \
    HOUSEHOLD_WEB_DATA_DIR=/data \
    HOUSEHOLD_WEB_ALLOW_REMOTE=1

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir "Pillow>=10.0" "cryptography>=43.0"

COPY bookkeeping /app/bookkeeping
COPY cloudflare-full/container/gateway.py /app/gateway.py
RUN mkdir -p /data

EXPOSE 8000
CMD ["python", "/app/gateway.py"]
