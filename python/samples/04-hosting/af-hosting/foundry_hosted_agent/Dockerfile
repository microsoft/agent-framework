FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Build context for this Dockerfile is THIS folder (see ``azure.yaml`` ->
# ``services.<svc>.project: .``). The workspace packages this sample edits
# editable-installs from ``./_vendor/`` — populated either by the azd
# ``prepackage`` hook (``scripts/vendor-packages.sh``) or manually before
# ``docker build``.
#
# ``Dockerfile.dockerignore`` (adjacent file, BuildKit) trims the upload to
# just the files COPYed below.

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY _vendor/ ./_vendor/
COPY app.py ./

# ``--frozen`` honors the committed uv.lock; ``--no-dev`` skips the dev
# group (which only contains ``openai`` for ``call_server.py``).
RUN uv sync --no-dev --frozen

ENV PORT=8000
EXPOSE 8000

CMD ["uv", "run", "python", "app.py"]
