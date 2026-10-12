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

"""Request-owned hosted MCP configuration with a deployment-owned GitHub PAT."""

from __future__ import annotations

import os
from contextlib import AsyncExitStack
from types import TracebackType

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.core import AgentConfig, get_request_context
from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential
from dotenv import load_dotenv


def create_agent() -> Agent:
    """Build fresh tool configuration without accepting caller-supplied credentials."""
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ.get("FOUNDRY_MODEL") or os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    github_pat = os.environ.get("GITHUB_PAT")
    if not github_pat or not github_pat.strip():
        raise RuntimeError("Configure GITHUB_PAT separately before using the GitHub MCP sample.")
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

    client = RequestClient(
        project_endpoint=endpoint,
        model=model,
        credential=credential,
        default_headers=get_request_context().platform_headers(),
    )
    github_tool = client.get_mcp_tool(
        name="GitHub",
        url="https://api.githubcopilot.com/mcp/",
        headers={"Authorization": f"Bearer {github_pat}"},
        allowed_tools=["get_me", "search_repositories", "get_file_contents"],
        approval_mode="never_require",
    )
    return Agent(
        client=client,
        instructions="You are a friendly assistant. Keep your answers brief.",
        tools=[github_tool],
    )


def main() -> None:
    load_dotenv()
    server = ResponsesHostServer(agent=create_agent, history_source="agent_server")
    server.run()


if __name__ == "__main__":
    main()
