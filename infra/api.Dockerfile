FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/apps/api:/app
WORKDIR /app
RUN useradd --create-home --uid 10001 appuser
COPY pyproject.toml README.md LICENSE ./
COPY apps/api ./apps/api
COPY services ./services
COPY mcp_servers ./mcp_servers
RUN pip install --no-cache-dir .
RUN mkdir -p /app/runtime && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "uvicorn research_navigator.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
