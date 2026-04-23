FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7.3 /uv /uvx /bin/

WORKDIR /app
WORKDIR /app/user_agent

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . ./

EXPOSE 8088

CMD ["uv", "run", "main.py"]
