# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-core",
#     "agent-framework-foundry",
#     "agent-framework-purview",
#     "agent-framework-tools",
#     "agent-framework-monty",
#     "agent-framework-foundry-hosting",
#     "azure-ai-agentserver-core>=2.1.0,<3",
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
    FOUNDRY_MODEL                  — Model deployment name for local runs
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
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from types import TracebackType

from agent import _build_purview_middleware, build_claw_agent
from agent_framework import (
    Agent,
    AgentContext,
    AgentResponseUpdate,
    BackgroundAgentsProvider,
    FileSystemAgentFileStore,
    InMemoryHistoryProvider,
    ResponseStream,
    agent_middleware,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import FoundryRequestScope, ResponsesHostServer
from azure.ai.agentserver.core import AgentConfig, get_request_context
from azure.identity import AzureCliCredential, ManagedIdentityCredential
from dotenv import load_dotenv

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

    Log variable names only, never user/session/call IDs, tokens or identity values.
    """
    foundry_vars = sorted(name for name in os.environ if name.startswith("FOUNDRY_"))
    logger.info("Platform-injected FOUNDRY_* variables present: %s", ", ".join(foundry_vars) or "(none)")
    logger.info(
        "Agent managed identity configured: %s",
        bool(os.environ.get("FOUNDRY_AGENT_INSTANCE_CLIENT_ID")),
    )


async def create_agent() -> Agent:
    """Build request-owned tools and scope file memory by trusted user and sandbox."""
    config, context = AgentConfig.from_env(), get_request_context()
    scope = FoundryRequestScope.from_context(config, context, local_session_id="local-development")
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ.get("FOUNDRY_MODEL") or os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    credential = (
        ManagedIdentityCredential(client_id=os.environ.get("FOUNDRY_AGENT_INSTANCE_CLIENT_ID"))
        if config.is_hosted
        else AzureCliCredential()
    )
    memory_dir = Path.home() / ".claw" / "agent-file-memory" / scope.storage_key

    class RequestClient(FoundryChatClient):
        async def __aenter__(self) -> RequestClient:
            return self

        async def __aexit__(
            self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None
        ) -> None:
            async with AsyncExitStack() as cleanup:
                cleanup.callback(credential.close)
                cleanup.push_async_callback(self.project_client.close)
                cleanup.push_async_callback(self.client.close)

    client = RequestClient(
        project_endpoint=endpoint,
        model=model,
        credential=credential,
        default_headers=context.platform_headers(),
        middleware=_build_purview_middleware(credential),
    )
    logger.info("File memory enabled (trusted user/sandbox-scoped filesystem).")
    agent = await build_claw_agent(
        credential=credential,
        client=client,
        history_provider=InMemoryHistoryProvider(load_messages=False),
        # Disable filesystem and shell access on the hosted container. Arbitrary read/write or
        # command execution in a shared hosted environment is a serious security risk, and the
        # local confirmations vault does not exist here. To keep file access when hosted, pass an
        # external file_access_store (e.g. one backed by Azure Blob Storage) instead of the disk.
        enable_file_access=False,
        enable_shell=False,
        file_memory_store=FileSystemAgentFileStore(memory_dir),
        # Purview authenticates via the container's managed identity; InteractiveBrowserCredential
        # cannot run on a headless hosted container.
        purview_credential=credential,
    )
    background_providers = [
        provider for provider in agent.context_providers if isinstance(provider, BackgroundAgentsProvider)
    ]

    @agent_middleware
    async def request_background_lifetime(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
        if context.session is None:
            raise RuntimeError("The hosted harness requires a request-owned AgentSession.")
        session = context.session

        @asynccontextmanager
        async def release_background() -> AsyncIterator[None]:
            run_failed = False
            try:
                yield
            except BaseException:
                run_failed = True
                raise
            finally:
                try:
                    for provider in background_providers:
                        await provider.release_session(session)
                except BaseException as cleanup_error:
                    logger.error("Failed to release request-owned background tasks (%s).", type(cleanup_error).__name__)
                    if not run_failed:
                        raise

        if context.stream:
            # Streaming returns before iteration; teardown must wrap consumption, not construction.
            try:
                await call_next()
            except BaseException:
                async with release_background():
                    raise
            inner = context.result
            if not isinstance(inner, ResponseStream):
                async with release_background():
                    raise RuntimeError("The streaming hosted harness must return a ResponseStream.")

            cleaned_up = False

            async def cleanup() -> None:
                nonlocal cleaned_up
                if cleaned_up:
                    return
                cleaned_up = True
                async with release_background():
                    await inner.close()

            async def updates() -> AsyncIterator[AgentResponseUpdate]:
                run_failed = False
                try:
                    async for update in inner:
                        yield update
                    await inner.get_final_response()
                except BaseException:
                    run_failed = True
                    raise
                finally:
                    try:
                        await cleanup()
                    except BaseException as cleanup_error:
                        logger.error("Failed to clean up the request stream (%s).", type(cleanup_error).__name__)
                        if not run_failed:
                            raise

            context.result = ResponseStream(
                updates(), finalizer=lambda _: inner.get_final_response(), cleanup_hooks=[cleanup]
            )
        else:
            async with release_background():
                await call_next()

    agent.middleware = [request_background_lifetime, *(agent.middleware or [])]
    return agent


async def main() -> None:
    """Expose the claw with a fresh agent and resource lifecycle for each request."""
    _configure_logging()
    load_dotenv()
    _log_environment()
    server = ResponsesHostServer(agent=create_agent, history_source="agent_server")
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
