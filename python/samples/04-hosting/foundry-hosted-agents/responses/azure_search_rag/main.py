# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-core",
#     "agent-framework-foundry",
#     "agent-framework-foundry-hosting",
#     "agent-framework-azure-ai-search",
#     "azure-ai-agentserver-core>=2.1.0,<3",
#     "azure-identity",
#     "python-dotenv",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

"""Request-owned retrieval over an explicitly shared, read-only public sample index."""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from types import TracebackType

from agent_framework import Agent
from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.core import AgentConfig, get_request_context
from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential
from dotenv import load_dotenv


def create_agent() -> Agent:
    """Allocate a new Search provider and close its transports after this request."""
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    search_endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
    credential = (
        ManagedIdentityCredential(client_id=os.environ.get("FOUNDRY_AGENT_INSTANCE_CLIENT_ID"))
        if AgentConfig.from_env().is_hosted
        else AzureCliCredential()
    )

    search_provider = AzureAISearchContextProvider(
        source_id="azure_search_rag",
        endpoint=search_endpoint,
        index_name=index_name,
        credential=credential,
        mode="semantic",
        top_k=3,
    )

    class RequestClient(FoundryChatClient):
        async def __aenter__(self) -> RequestClient:
            try:
                await search_provider.__aenter__()
            except BaseException:
                await self.__aexit__(None, None, None)
                raise
            return self

        async def __aexit__(
            self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None
        ) -> None:
            async with AsyncExitStack() as cleanup:
                cleanup.push_async_callback(credential.close)
                cleanup.push_async_callback(self.project_client.close)
                cleanup.push_async_callback(self.client.close)
                cleanup.push_async_callback(search_provider.close)

    client = RequestClient(
        project_endpoint=endpoint,
        model=model,
        credential=credential,
        default_headers=get_request_context().platform_headers(),
    )
    return Agent(
        client=client,
        instructions=(
            "You are a support specialist for Contoso Outdoors. "
            "Answer using the provided public documentation and cite the source when available."
        ),
        context_providers=[search_provider],
    )


async def main() -> None:
    load_dotenv()
    server = ResponsesHostServer(agent=create_agent, history_source="agent_server")
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
