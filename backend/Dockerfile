# Single backend image for the API, the Temporal worker and migrations.
# Default command: knobridge-api. Compose picks `knobridge-worker` or `alembic upgrade head`.

# Official uv image, used only to copy its static binary (pinned for reproducible builds).
FROM ghcr.io/astral-sh/uv:0.11.11 AS uv

FROM python:3.12-slim AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app

# Dependencies first, so source changes do not invalidate this layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Then the package itself, installed non-editable into the virtualenv.
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime
RUN groupadd --system --gid 10001 knobridge \
    && useradd --system --uid 10001 --gid knobridge --no-create-home knobridge
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    KNOBRIDGE_API_HOST=0.0.0.0 \
    KNOBRIDGE_API_PORT=8000
USER knobridge
EXPOSE 8000
CMD ["knobridge-api"]
