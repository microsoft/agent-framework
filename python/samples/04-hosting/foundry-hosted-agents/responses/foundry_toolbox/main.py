# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-core",
#     "agent-framework-foundry",
#     "agent-framework-foundry-hosting",
#     "azure-ai-agentserver-core>=2.1.0,<3",
#     "azure-identity",
#     "python-dotenv",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

"""Request-owned Foundry Toolbox connections for the Responses protocol."""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from types import TracebackType

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, FoundryToolbox
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.core import AgentConfig, get_request_context
from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential
from dotenv import load_dotenv


def create_agent() -> Agent:
    """Create request-owned SDK resources and close them with the agent."""
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ.get("FOUNDRY_MODEL") or os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    credential = (
        ManagedIdentityCredential(client_id=os.environ.get("FOUNDRY_AGENT_INSTANCE_CLIENT_ID"))
        if AgentConfig.from_env().is_hosted
        else AzureCliCredential()
    )

    class RequestClient(FoundryChatClient):
        async def __aenter__(self) -> RequestClient:
            return self

        async def __aexit__(
            self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None
        ) -> None:
            async with AsyncExitStack() as cleanup:
                cleanup.push_async_callback(credential.close)
                cleanup.push_async_callback(self.project_client.close)
                cleanup.push_async_callback(self.client.close)

    toolbox = FoundryToolbox(credential)
    client = RequestClient(
        project_endpoint=endpoint,
        model=model,
        credential=credential,
        default_headers=get_request_context().platform_headers(),
    )
    return Agent(
        client=client,
        instructions="You are a friendly assistant. Keep your answers brief.",
        tools=toolbox,
    )


async def main() -> None:
    load_dotenv()
    server = ResponsesHostServer(agent=create_agent, history_source="agent_server")
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
