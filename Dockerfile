# Stage 1: Build React + TypeScript + Tailwind SPA
FROM node:20-slim AS frontend-builder
WORKDIR /build/frontend-app
COPY frontend-app/package.json frontend-app/package-lock.json ./
RUN npm ci
COPY frontend-app/ ./
RUN npm run build

# Stage 2: Production Python 3.12 Backend + Compiled SPA
FROM python:3.12-slim
ARG INSTALL_LOCAL_WHISPER=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
RUN if [ "$INSTALL_LOCAL_WHISPER" = "1" ]; then \
      pip install --no-cache-dir -r requirements.txt; \
    else \
      grep -vE '^(mlx-whisper|faster-whisper)' requirements.txt > /tmp/req-core.txt && \
      pip install --no-cache-dir -r /tmp/req-core.txt; \
    fi

COPY backend/ ./backend/
COPY run.py openapi.json ./
COPY --from=frontend-builder /build/frontend/static/dist ./frontend/static/dist

RUN mkdir -p /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
