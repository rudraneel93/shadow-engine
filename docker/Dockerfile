FROM python:3.12-slim

LABEL org.opencontainers.image.title="Shadow Engineer"
LABEL org.opencontainers.image.description="Self-improving background agent with persistent knowledge graph and parallel experimentation"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.source="https://github.com/shadow-engine/shadow-engine"

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash shadow
USER shadow
WORKDIR /home/shadow/app

COPY --chown=shadow:shadow pyproject.toml README.md ./
COPY --chown=shadow:shadow src/ ./src/

RUN pip install --no-cache-dir --user -e ".[dev]"
RUN pip install --no-cache-dir --user fastapi uvicorn redis

ENV SHADOW_ENGINE_PORT=8000
ENV SHADOW_ENGINE_HOST=0.0.0.0
ENV SHADOW_ENGINE_REDIS_URL=redis://redis:6379
ENV SHADOW_ENGINE_API_KEY=""
ENV SHADOW_ENGINE_STORAGE_PATH=/home/shadow/data
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /home/shadow/data

EXPOSE 8000

# Fix #9: Health check uses /health (served at both /health and /v1/health)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "shadow_engine.api_server.server:app", "--host", "0.0.0.0", "--port", "8000"]