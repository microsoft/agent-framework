FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# The sample depends on hosting packages from Git refs until they publish to
# PyPI, so the remote builder needs git available during `uv sync`.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app.py ./

RUN uv sync --no-dev

ENV PORT=8000
EXPOSE 8000

CMD ["uv", "run", "python", "app.py"]
