# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = [
#     "agent-framework-core",
#     "agent-framework-foundry",
#     "agent-framework-foundry-hosting",
#     "agent-framework-monty",
#     "azure-ai-agentserver-core>=2.1.0,<3",
#     "azure-identity",
#     "python-dotenv",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

"""Request-owned Monty CodeAct and Foundry clients."""

from __future__ import annotations

import os
from contextlib import AsyncExitStack
from types import TracebackType
from typing import Annotated, Any, Literal

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework.monty import MontyCodeActProvider
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.core import AgentConfig, get_request_context
from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential
from dotenv import load_dotenv
from pydantic import Field


@tool(approval_mode="never_require")
def compute(
    operation: Annotated[
        Literal["add", "subtract", "multiply", "divide"],
        Field(description="Math operation: add, subtract, multiply, or divide."),
    ],
    a: Annotated[float, Field(description="First numeric operand.")],
    b: Annotated[float, Field(description="Second numeric operand.")],
) -> float:
    """Perform a math operation used by sandboxed code."""
    operations = {
        "add": a + b,
        "subtract": a - b,
        "multiply": a * b,
        "divide": a / b if b else float("inf"),
    }
    return operations[operation]


@tool(approval_mode="never_require")
def fetch_data(
    table: Annotated[str, Field(description="Name of the simulated table to query.")],
) -> list[dict[str, Any]]:
    """Fetch simulated records from a named table."""
    data: dict[str, list[dict[str, Any]]] = {
        "users": [
            {"id": 1, "name": "Alice", "role": "admin"},
            {"id": 2, "name": "Bob", "role": "user"},
            {"id": 3, "name": "Charlie", "role": "admin"},
        ],
        "products": [
            {"id": 101, "name": "Widget", "price": 9.99},
            {"id": 102, "name": "Gadget", "price": 19.99},
        ],
    }
    return data.get(table, [])


def create_agent() -> Agent:
    """Create a new interpreter provider and client for the current request."""
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

    client = RequestClient(
        project_endpoint=endpoint,
        model=model,
        credential=credential,
        default_headers=get_request_context().platform_headers(),
    )

    # MontyCodeActProvider injects a sandboxed `execute_code` tool into every
    # agent run, plus dynamic instructions describing the registered host tools.
    # The host tools are hidden from the model - they can only be invoked from
    # inside the sandbox (`await compute(...)` or `call_tool(...)`).
    codeact = MontyCodeActProvider(
        tools=[compute, fetch_data],
        approval_mode="never_require",
    )

    return Agent(
        client=client,
        instructions=(
            "You are a friendly assistant. Use `execute_code` to combine "
            "Python control flow with the provided host tools whenever the "
            "task requires lookups, transformations, or computation."
        ),
        context_providers=[codeact],
    )


def main() -> None:
    """Host a Monty CodeAct agent over the Responses protocol."""
    load_dotenv()
    server = ResponsesHostServer(agent=create_agent, history_source="agent_server")
    server.run()


if __name__ == "__main__":
    main()
