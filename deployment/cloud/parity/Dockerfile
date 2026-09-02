FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/apps/api:/workspace

WORKDIR /opt/build
RUN pip install --no-cache-dir uv==0.8.17
COPY pyproject.toml uv.lock README.md ./
COPY apps/api ./apps/api
RUN UV_PROJECT_ENVIRONMENT=/opt/rn-venv UV_CACHE_DIR=/opt/uv-cache \
    uv sync --frozen --extra dev

WORKDIR /workspace
ENV VIRTUAL_ENV=/opt/rn-venv \
    PATH=/opt/rn-venv/bin:$PATH \
    PYTHONPATH=/workspace/apps/api:/workspace:/workspace/deployment/cloud/parity

LABEL org.researchnavigator.runtime="offline-parity" \
      org.researchnavigator.source="host-verified-commit"
