# Copyright (c) Microsoft. All rights reserved.

"""Smallest hosting sample — Responses + Invocations only.

This sample is intentionally minimal and is **runtime-compatible with the
Foundry Hosted Agents platform**: a host that exposes the Responses and
Invocations channels under their default mount roots can be packaged as a
container image and deployed to Foundry Hosted Agents without any protocol
shim (see ADR 0026 §11). The same image runs locally, behind any ASGI
server, or as a Hosted Agent.

History
-------
The agent uses :class:`FoundryHostedAgentHistoryProvider` so that conversation
history is loaded from the Foundry Hosted Agent storage backend when the
container runs inside Foundry. When ``previous_response_id`` is supplied on
an incoming Responses request, the channel routes it through to the
provider as the ``session_id``, and the provider fetches the prior turn
chain from ``{FOUNDRY_PROJECT_ENDPOINT}/storage/...``. Locally
(``FOUNDRY_HOSTING_ENVIRONMENT`` unset) the provider falls back to an
in-memory store so the same code runs in dev.

Setup
-----
- ``FOUNDRY_PROJECT_ENDPOINT`` — Foundry project endpoint URL.
- ``MODEL_DEPLOYMENT_NAME``   — model deployment name (the same env var
  the Foundry Hosted Agents manifest binds via the ``model`` resource —
  see ``agent.manifest.yaml``).
- ``FOUNDRY_HOSTING_ENVIRONMENT`` — set automatically by the Hosted Agents
  runtime; signals the history provider to talk to the Foundry storage API
  instead of the local in-memory fallback.
- ``APPLICATIONINSIGHTS_CONNECTION_STRING`` — when present, the sample
  wires Azure Monitor OpenTelemetry export at import time. Foundry Hosted
  Agents inject this when an Application Insights resource is bound to
  the project; locally it's optional.

Auth uses ``DefaultAzureCredential`` so any standard Azure auth chain
works (``az login`` locally, managed identity in Hosted Agents,
``AZURE_*`` env vars in CI, ...).

Run
---
- Local:      ``python app.py``  (binds ``0.0.0.0:8000``)
- ASGI:       ``hypercorn app:app --bind 0.0.0.0:8000``
- Docker:     ``docker build -t hosting-sample-hosted-agent . && \\
                 docker run -p 8000:8000 \\
                   -e FOUNDRY_PROJECT_ENDPOINT -e MODEL_DEPLOYMENT_NAME \\
                   hosting-sample-hosted-agent``
- Hosted Agent: build & push the image, then deploy via ``agent.yaml`` /
  ``agent.manifest.yaml`` in this folder.

Routes
------
- ``POST /responses``           — OpenAI Responses-shaped surface.
- ``POST /invocations/invoke``  — host-native JSON envelope.
"""

from __future__ import annotations

import logging
import os

from agent_framework import Agent
from agent_framework.observability import enable_instrumentation
from agent_framework_foundry import FoundryChatClient
from agent_framework_foundry_hosting import (
    FoundryHostedAgentHistoryProvider,
    foundry_response_id,
)
from agent_framework_hosting import AgentFrameworkHost
from agent_framework_hosting_invocations import InvocationsChannel
from agent_framework_hosting_responses import ResponsesChannel
from azure.identity.aio import DefaultAzureCredential

# Configure root logging early so library log records (in particular
# ``agent_framework_foundry_hosting._history_provider``) are captured by
# the container's stderr stream and surfaced in the Foundry portal /
# Azure Monitor. ``LOG_LEVEL`` overrides this for production tightening.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# Quiet noisy transports unless explicitly cranked up.
for _noisy in (
    "httpx",
    "httpcore",
    "azure.core.pipeline.policies.http_logging_policy",
    "urllib3",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def _configure_observability() -> None:
    """Wire Azure Monitor OpenTelemetry when a connection string is present.

    Foundry Hosted Agents inject ``APPLICATIONINSIGHTS_CONNECTION_STRING``
    into the container at runtime when an Application Insights resource is
    bound to the project. We honor the same env var locally so the same
    code path lights up in both environments. When the var is absent
    (typical local dev without an AI binding) we silently skip — the host
    still serves traffic, just without OTel export.
    """
    conn_str = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn_str:
        logger.info(
            "APPLICATIONINSIGHTS_CONNECTION_STRING not set — skipping Azure Monitor OpenTelemetry configuration.",
        )
        return
    # Imported lazily so the sample still starts when the optional
    # ``azure-monitor-opentelemetry`` dependency isn't installed (e.g. an
    # ultra-thin local dev image stripped of observability extras).
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(connection_string=conn_str)
    logger.info("Azure Monitor OpenTelemetry configured.")


def build_host() -> AgentFrameworkHost:
    # Single credential is shared by the chat client and the history
    # provider so we only authenticate (and refresh tokens) once.
    credential = DefaultAzureCredential()
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=project_endpoint,
            model=os.environ["MODEL_DEPLOYMENT_NAME"],
            credential=credential,
        ),
        name="HostedAgentSample",
        instructions="You are called Jarvis, a friendly assistant. Keep answers brief.",
        # Loads history from Foundry storage when running inside a Hosted
        # Agent (FOUNDRY_HOSTING_ENVIRONMENT set); falls back to an in-
        # memory store for local dev.
        context_providers=[
            FoundryHostedAgentHistoryProvider(
                credential=credential,
                endpoint=project_endpoint,
            ),
        ],
    )

    return AgentFrameworkHost(
        target=agent,
        channels=[
            # Mint Foundry-storage-compatible response ids
            # (``caresp_{18charPartitionKey}{32charEntropy}``). The
            # Foundry storage backend partitions records by extracting
            # this segment from the id; free-form ``resp_<uuid>`` ids
            # are rejected with an opaque ``HTTP 500 server_error``.
            ResponsesChannel(response_id_factory=foundry_response_id),
            InvocationsChannel(),
        ],
    )


# `app` is the canonical ASGI surface — hand it to any ASGI server, or let
# the Foundry Hosted Agents runtime pick it up via the standard entry point.
# Observability is configured at import time so trace/log export is wired
# before the host starts handling requests. Per-request Foundry isolation
# (the platform-injected ``x-agent-{user,chat}-isolation-key`` headers)
# is read by the host's installed ASGI middleware off every inbound HTTP
# request and lifted into a contextvar that
# :class:`FoundryHostedAgentHistoryProvider` consults on each storage call.
# Multi-turn persistence works out of the box in both local dev and the
# Hosted Agents container — no manual middleware wiring needed.
_configure_observability()
enable_instrumentation(enable_sensitive_data=True)
app = build_host().app


if __name__ == "__main__":
    # Serve the host's ASGI app directly. The Foundry isolation headers
    # are read by the host's installed ASGI middleware and threaded
    # through the storage provider via a contextvar; nothing extra to wire.
    import asyncio

    import hypercorn.asyncio
    import hypercorn.config

    config = hypercorn.config.Config()
    config.bind = [f"0.0.0.0:{int(os.environ.get('PORT', '8000'))}"]
    asyncio.run(hypercorn.asyncio.serve(app, config))  # type: ignore[arg-type]
