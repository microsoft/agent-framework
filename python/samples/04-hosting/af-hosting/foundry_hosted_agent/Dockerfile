FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Build context for this Dockerfile is THIS folder (see ``azure.yaml`` ->
# ``services.<svc>.project: .``). The workspace packages this sample
# depends on are fetched from GitHub by ``uv sync`` (see the ``[tool.uv.sources]``
# git refs in ``pyproject.toml``). The build needs network access to GitHub
# during ``uv sync`` — no local vendoring step is required.
#
# ``Dockerfile.dockerignore`` (adjacent file, BuildKit) trims the upload to
# just the files COPYed below.

WORKDIR /app

COPY pyproject.toml ./
COPY app.py ./

# ``--no-dev`` skips the dev group (which only contains ``openai`` for
# ``call_server.py``). Locks fresh against the GitHub-hosted hosting
# packages declared in ``[tool.uv.sources]``.
RUN uv sync --no-dev

ENV PORT=8000
EXPOSE 8000

CMD ["uv", "run", "python", "app.py"]
