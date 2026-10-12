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
# git: the Git connector shells out to it (local repositories and https clones). Nothing else
# from apt; the parsing and tree-sitter dependencies come as wheels in the virtualenv.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 10001 knobridge \
    && useradd --system --uid 10001 --gid knobridge --no-create-home knobridge \
    # Default KNOBRIDGE_GIT_WORKDIR. Owned by the app user, so a named volume mounted here
    # starts writable (Docker copies the ownership into an empty volume).
    && mkdir -p /var/lib/knobridge/git \
    && chown -R knobridge:knobridge /var/lib/knobridge
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    KNOBRIDGE_API_HOST=0.0.0.0 \
    KNOBRIDGE_API_PORT=8000
# Smoke test of the native and optional dependencies on Linux: the build fails here, not at the
# first sync, if a tree-sitter grammar, a MarkItDown converter or git is missing.
RUN git --version \
    && python -c "import croniter, pathspec, pgvector.sqlalchemy; \
from knobridge.ingestion import parsing; \
from knobridge.ingestion.code_chunking import chunk_code; \
assert chunk_code('export function f(): number {\n  return 1;\n}\n', 'a.ts', 'typescript'); \
assert chunk_code('package a\n\nfunc F() int {\n\treturn 1\n}\n', 'a.go', 'go')"
USER knobridge
EXPOSE 8000
CMD ["knobridge-api"]
