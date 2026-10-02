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

"""Local tools on a request-owned Responses agent; approvals remain host-persisted."""

from __future__ import annotations

import os
import subprocess
from contextlib import AsyncExitStack
from random import randint
from types import TracebackType
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.core import AgentConfig, get_request_context
from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential
from dotenv import load_dotenv
from pydantic import Field


@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


@tool(approval_mode="always_require")
def run_bash(command: str) -> str:
    """Execute a shell command locally and return stdout, stderr, and exit code."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        parts: list[str] = []
        if result.stdout:
            parts.append(result.stdout)
        if result.stderr:
            parts.append(f"stderr: {result.stderr}")
        parts.append(f"exit_code: {result.returncode}")
        return "\n".join(parts)
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds"
    except Exception as e:
        return f"Error executing command: {e}"


def create_agent() -> Agent:
    """Create client state per request rather than keeping history on the agent."""
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

    client = RequestClient(
        project_endpoint=endpoint,
        model=model,
        credential=credential,
        default_headers=get_request_context().platform_headers(),
    )

    return Agent(
        client=client,
        instructions="You are a friendly assistant. Keep your answers brief.",
        tools=[get_weather, run_bash],
    )


def main() -> None:
    load_dotenv()
    server = ResponsesHostServer(agent=create_agent, history_source="agent_server")
    server.run()


if __name__ == "__main__":
    main()
