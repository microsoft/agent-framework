# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-core",
#     "agent-framework-foundry",
#     "agent-framework-purview",
#     "agent-framework-tools",
#     "agent-framework-monty",
#     "agent-framework-foundry-hosting",
#     "mcp",
#     "httpx",
#     "azure-identity",
#     "python-dotenv",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

"""Foundry Hosted Agent host for the production-ready claw.

Observability requires no exporter setup here. Agent Framework is natively instrumented (on by
default), and the Foundry hosting runtime collects and exports the traces, metrics, and logs — so
there is no ``configure_otel_providers()`` call. When deployed, Foundry injects
``APPLICATIONINSIGHTS_CONNECTION_STRING`` automatically. To capture prompt/response content, set
``ENABLE_SENSITIVE_DATA=true`` (see ``agent.yaml``). Because the exporters are Foundry-managed, run
this host with ``azd ai agent run`` to see telemetry; running it directly won't export anything.

File access and shell are disabled on the hosted container (see ``enable_file_access`` /
``enable_shell`` below). File memory stays enabled, but its store is pointed at a writable directory
under the home directory.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT       — Microsoft Foundry project endpoint URL
    AZURE_AI_MODEL_DEPLOYMENT_NAME — Model deployment name for the hosted agent
    TOOLBOX_MCP_SERVER_URL         — Optional Foundry Toolbox MCP endpoint URL
    PURVIEW_CLIENT_APP_ID          — Optional app/client ID; enables Purview
    ENABLE_SENSITIVE_DATA          — Enables sensitive telemetry capture (prompts/responses) when true

Run locally:
    uv run --prerelease=allow \
        python/samples/02-agents/harness/build_your_own_claw/claw_step04_production_ready/hosted.py
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from agent import build_claw_agent
from agent_framework import FileSystemAgentFileStore, InMemoryHistoryProvider
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# File memory writes to disk, and the deployed code directory is read-only on Foundry hosted agents,
# so the harness default of ``{cwd}/agent-file-memory`` cannot be created. The home directory is
# writable, so root the store there.
_FILE_MEMORY_DIR = Path.home() / ".claw" / "agent-file-memory"

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Route startup diagnostics to stderr so they survive on a Foundry hosted agent.

    Two constraints make this necessary:

    * Foundry surfaces the container's **stderr** stream, so ``print`` (stdout) output never
      appears in the hosted logs.
    * The agentserver SDK attaches its own stderr handler to the root logger, but only once the
      host starts — which is *after* the agent is built below. Without this call, the diagnostics
      emitted while building the agent would reach a handler-less root logger and be dropped by
      ``logging.lastResort`` (level ``WARNING``).

    The SDK skips adding its handler when one is already present, so this does not double-log.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _log_environment() -> None:
    """Log which platform variables are present, to make misconfiguration self-evident.

    Only variable *names* are logged for the platform-injected ``FOUNDRY_*`` set: their values can
    carry session and project details. ``FOUNDRY_AGENT_INSTANCE_CLIENT_ID`` is the exception. It is
    the client id of the managed identity the container authenticates as, and that identity needs
    the ``Foundry User`` role to read Toolbox skill content — so when a skill fails to load, this
    line names the exact principal to grant the role to (see the README).
    """
    foundry_vars = sorted(name for name in os.environ if name.startswith("FOUNDRY_"))
    logger.info("Platform-injected FOUNDRY_* variables present: %s", ", ".join(foundry_vars) or "(none)")
    logger.info(
        "Agent managed identity (grant it the Foundry User role): %s",
        os.environ.get("FOUNDRY_AGENT_INSTANCE_CLIENT_ID") or "(not set)",
    )


async def main() -> None:
    """Build the claw and expose it with the Foundry Responses host server."""
    _configure_logging()
    load_dotenv()
    _log_environment()

    credential = DefaultAzureCredential()
    logger.info("File memory enabled (local filesystem at %s).", _FILE_MEMORY_DIR)
    agent = await build_claw_agent(
        credential=credential,
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        default_options={"store": False},
        history_provider=InMemoryHistoryProvider(load_messages=False),
        # Disable filesystem and shell access on the hosted container. Arbitrary read/write or
        # command execution in a shared hosted environment is a serious security risk, and the
        # local confirmations vault does not exist here. To keep file access when hosted, pass an
        # external file_access_store (e.g. one backed by Azure Blob Storage) instead of the disk.
        enable_file_access=False,
        enable_shell=False,
        # File memory is on by default; keep it, but on a writable path (see _FILE_MEMORY_DIR).
        file_memory_store=FileSystemAgentFileStore(_FILE_MEMORY_DIR),
        # Purview authenticates via the container's managed identity; InteractiveBrowserCredential
        # cannot run on a headless hosted container.
        purview_credential=credential,
    )
    server = ResponsesHostServer(agent)
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
