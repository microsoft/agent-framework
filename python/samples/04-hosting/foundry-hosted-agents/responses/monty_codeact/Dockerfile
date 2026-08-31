FROM python:3.12-slim

# Bring in the `uv` binary from a pinned Astral image. Update this tag intentionally;
# `latest` would make rebuilds non-deterministic.
COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

# Sync dependencies first to maximize Docker layer caching.
COPY pyproject.toml ./
RUN uv sync --no-install-project --no-cache

# Now copy the rest of the agent and finalize the environment.
COPY . ./
RUN uv sync --no-cache

EXPOSE 8088

CMD ["uv", "run", "--no-sync", "python", "main.py"]

