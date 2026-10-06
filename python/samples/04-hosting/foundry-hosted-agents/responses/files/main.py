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

"""Expose only explicitly uploaded session files with request-owned SDK resources."""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from types import TracebackType

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient, FoundryToolbox
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.core import AgentConfig, get_request_context
from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential
from dotenv import load_dotenv
from file_access import list_uploaded_files, read_uploaded_file


@tool(description="List regular files uploaded to this session's sample_files folder.", approval_mode="never_require")
def list_files() -> list[str]:
    """List this sandbox's uploads without accepting an arbitrary directory."""
    return list_uploaded_files()


@tool(
    description="Read one named UTF-8 file uploaded to this session's sample_files folder.",
    approval_mode="never_require",
)
def read_file(filename: str) -> str:
    """Read a bounded upload, rejecting paths, symlinks and non-regular files."""
    return read_uploaded_file(filename)


def create_agent() -> Agent:
    """Create the client and Toolbox as request-owned resources."""
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
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
    return Agent(
        client=RequestClient(
            project_endpoint=endpoint,
            model=model,
            credential=credential,
            default_headers=get_request_context().platform_headers(),
        ),
        instructions=(
            "Use list_files and read_file only for explicitly uploaded files in sample_files. "
            "Pass a single filename, never a directory or absolute path. "
            "Use the code interpreter for calculations on the returned text."
        ),
        tools=[list_files, read_file, toolbox],
    )


async def main() -> None:
    load_dotenv()
    server = ResponsesHostServer(agent=create_agent, history_source="agent_server")
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
