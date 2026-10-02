# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-core",
#     "agent-framework-foundry",
#     "agent-framework-foundry-hosting",
#     "azure-ai-agentserver-core>=2.1.0,<3",
#     "azure-ai-projects>=2.2.0,<2.8.0",
#     "azure-identity",
#     "python-dotenv",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

"""Request-owned Foundry Memory with intentional, trusted user-wide sharing."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from contextlib import AsyncExitStack
from types import TracebackType

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, FoundryMemoryProvider
from agent_framework_foundry_hosting import FoundryRequestScope, ResponsesHostServer
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext, get_request_context
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential
from dotenv import load_dotenv


def memory_scope(config: AgentConfig, context: FoundryAgentRequestContext) -> str:
    """Hash the trusted user, deliberately excluding sandbox, conversation and call IDs."""
    if config.is_hosted:
        scope = FoundryRequestScope.from_context(config, context)
        user_id = scope.user_id
        if not user_id or not user_id.strip():
            raise RuntimeError("Foundry Memory requires a trusted platform user ID.")
    else:
        if context.user_id is not None or context.call_id is not None:
            raise RuntimeError("Local Memory does not trust platform identity headers; use LOCAL_MEMORY_USER_ID.")
        user_id = os.environ.get("LOCAL_MEMORY_USER_ID")
        if not user_id or not user_id.strip():
            raise RuntimeError("Set LOCAL_MEMORY_USER_ID explicitly for single-user local Memory.")
    identity = json.dumps(["foundry-memory-user-v1", user_id], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def create_agent() -> Agent:
    """Bind a fresh provider and first-party project client to this request."""
    config, context = AgentConfig.from_env(), get_request_context()
    scope = memory_scope(config, context)
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    store_name = os.environ["MEMORY_STORE_NAME"]
    headers = context.platform_headers()
    credential = (
        ManagedIdentityCredential(client_id=os.environ.get("FOUNDRY_AGENT_INSTANCE_CLIENT_ID"))
        if config.is_hosted
        else AzureCliCredential()
    )
    # Project-level Memory calls need the captured call ID too, not just model calls.
    project = AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True, headers=headers)

    class RequestClient(FoundryChatClient):
        async def __aenter__(self) -> RequestClient:
            return self

        async def __aexit__(
            self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None
        ) -> None:
            async with AsyncExitStack() as cleanup:
                cleanup.push_async_callback(credential.close)
                cleanup.push_async_callback(project.close)
                cleanup.push_async_callback(self.client.close)

    client = RequestClient(project_client=project, model=model, default_headers=headers)
    provider = FoundryMemoryProvider(project_client=project, memory_store_name=store_name, scope=scope)
    return Agent(
        client=client,
        instructions=(
            "You remember facts this user has shared across conversations. "
            "Use relevant retrieved memories when answering and acknowledge when relying on them."
        ),
        context_providers=[provider],
    )


async def main() -> None:
    load_dotenv()
    server = ResponsesHostServer(agent=create_agent, history_source="agent_server")
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
