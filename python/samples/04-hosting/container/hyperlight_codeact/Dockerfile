# Build this image with the repository's `python/` directory as the build context so
# the in-tree agent-framework packages can be installed from source. From the repo root:
#
#   docker build \
#     -f python/samples/04-hosting/foundry-hosted-agents/responses/08_hyperlight_codeact/Dockerfile \
#     -t <acr>.azurecr.io/<image>:<tag> \
#     python/
FROM python:3.12-slim

WORKDIR /app

# Copy the in-tree agent-framework packages we need. Order matters for editable
# installs because of inter-package dependencies; we install in dependency order
# below. Hyperlight backends are platform gated, so we install them via pip
# resolution rather than copying the wheels.
COPY packages/core /opt/af/core
COPY packages/openai /opt/af/openai
COPY packages/foundry /opt/af/foundry
COPY packages/foundry_hosting /opt/af/foundry_hosting
COPY packages/hyperlight /opt/af/hyperlight

# Copy just the sample we care about into the user agent location.
COPY samples/04-hosting/foundry-hosted-agents/responses/08_hyperlight_codeact/ /app/user_agent/
WORKDIR /app/user_agent

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir /opt/af/core \
    && pip install --no-cache-dir /opt/af/openai \
    && pip install --no-cache-dir /opt/af/foundry \
    && pip install --no-cache-dir /opt/af/foundry_hosting \
    && pip install --no-cache-dir /opt/af/hyperlight \
    && if grep -Eq '^[[:space:]]*[^#[:space:]]' requirements.txt; then pip install --no-cache-dir -r requirements.txt; fi

EXPOSE 8088

CMD ["python", "main.py"]
