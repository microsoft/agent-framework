# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import Annotated, Any, Literal

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from agent_framework_hyperlight import HyperlightCodeActProvider
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@tool(approval_mode="never_require")
def compute(
    operation: Annotated[
        Literal["add", "subtract", "multiply", "divide"],
        "Math operation: add, subtract, multiply, or divide.",
    ],
    a: Annotated[float, "First numeric operand."],
    b: Annotated[float, "Second numeric operand."],
) -> float:
    """Perform a math operation for sandboxed code."""
    operations = {
        "add": a + b,
        "subtract": a - b,
        "multiply": a * b,
        "divide": a / b if b else float("inf"),
    }
    return operations[operation]


@tool(approval_mode="never_require")
async def fetch_data(
    table: Annotated[str, "Name of the simulated table to query."],
) -> list[dict[str, Any]]:
    """Fetch records from a named table."""
    await asyncio.sleep(0.5)
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


def main():
    # 1. Create the Foundry chat client.
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    # 2. Register sandbox tools on a Hyperlight CodeAct provider. The model only
    #    sees `execute_code`; `compute` and `fetch_data` are reachable from
    #    inside the sandbox via `call_tool(...)`.
    codeact = HyperlightCodeActProvider(
        tools=[compute, fetch_data],
        approval_mode="never_require",
    )

    # 3. Build the agent. History is managed by the hosting infrastructure, so
    #    request the model not to persist server-side conversation state.
    agent = Agent(
        client=client,
        instructions="You are a helpful assistant. Keep your answers brief.",
        context_providers=[codeact],
        default_options={"store": False},
    )

    # 4. Serve the agent over the Foundry Responses protocol.
    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
