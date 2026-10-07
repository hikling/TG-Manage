# Build frontend in the first stage.
# 与 .nvmrc、package.json engines 和 GitHub Actions 保持一致。
FROM node:22.23.1-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# TeleBox retains its original TypeScript runtime and native Node dependencies.
# It runs as an isolated child process for each Telegram account.
FROM node:24-bookworm-slim AS telebox-builder
WORKDIR /telebox
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ pkg-config libcairo2-dev libpango1.0-dev libjpeg-dev libgif-dev && rm -rf /var/lib/apt/lists/*
COPY telebox/package.json telebox/package-lock.json ./
RUN npm ci --include=dev --no-audit --no-fund

# Python runtime.
# Python 3.11 for Telethon + dependencies.
FROM python:3.11-slim-bookworm AS production

# Version and build time metadata injected via build args (e.g. CI / Docker build).
ARG APP_VERSION=dev
ARG GIT_SHA=unknown
ARG GIT_BRANCH=unknown
ARG BUILD_TIME=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  TZ=Asia/Shanghai \
  TG_MANAGE_DATA_DIR=/data \
  APP_VERSION=${APP_VERSION} \
  GIT_SHA=${GIT_SHA} \
  GIT_BRANCH=${GIT_BRANCH} \
  BUILD_TIME=${BUILD_TIME}

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential pkg-config tzdata gosu curl git libcairo2-dev libpango1.0-dev libjpeg-dev libgif-dev libpixman-1-0 libglib2.0-0 && \
  rm -rf /var/lib/apt/lists/*

# Install all Python dependencies in a single layer for faster builds.
# 注意：pyotp 直接使用官方依赖（pip 安装），仓库不再提供根级 pyotp.py shim，勿在此 COPY。
COPY pyproject.toml README.md /app/
COPY tg_manage/__init__.py /app/tg_manage/__init__.py
COPY backend /app/backend
COPY tg_manage /app/tg_manage
COPY telebox /app/telebox
COPY --from=telebox-builder /telebox/node_modules /app/telebox/node_modules
COPY --from=telebox-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=telebox-builder /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

ARG TARGETPLATFORM
RUN pip install --no-cache-dir . \
  "pydantic<2" \
  "fastapi==0.109.2" \
  "bcrypt==4.0.1" \
  uvicorn[standard] \
  sqlalchemy \
  "passlib[bcrypt]==1.7.4" \
  pyotp \
  qrcode[pil] \
  apscheduler \
  python-multipart \
  && if [ "${TARGETPLATFORM:-}" = "linux/amd64" ] || [ "$(uname -m)" = "x86_64" ]; then \
    pip install --no-cache-dir tgcrypto; \
  fi

# Frontend static files served from /web.
COPY --from=frontend-builder /frontend/dist /web

# Data dir + non-root user + entrypoint.
ARG APP_UID=10001
ARG APP_GID=10001
RUN mkdir -p /data && \
  groupadd -r -g ${APP_GID} app && \
  useradd -r -u ${APP_UID} -g app -d /app -s /usr/sbin/nologin app && \
  chown -R app:app /data

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

# Healthcheck uses the PORT env var.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\", \"8080\")}/healthz').read()"

# Start with env-driven PORT (Zeabur sets this automatically).
ENTRYPOINT ["/entrypoint.sh"]
