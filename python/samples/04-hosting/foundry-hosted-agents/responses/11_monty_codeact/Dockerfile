FROM python:3.12-slim

# Bring in the `uv` binary from the official Astral image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

# Sync dependencies first to maximize Docker layer caching. The agent-framework-monty
# alpha wheel is vendored under wheels/ and referenced via [tool.uv.sources] in
# pyproject.toml, so the wheels directory must be present before `uv sync` runs.
COPY pyproject.toml ./
COPY wheels/ ./wheels/
RUN uv sync --no-install-project --no-cache

# Now copy the rest of the agent and finalize the environment.
COPY . ./
RUN uv sync --no-cache

EXPOSE 8088

CMD ["uv", "run", "--no-sync", "python", "main.py"]

