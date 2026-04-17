# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os
from typing import Annotated, Any, Literal

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

from agent_framework_hyperlight import HyperlightExecuteCodeTool

"""This sample demonstrates the standalone Hyperlight execute_code tool.

The sample adds `HyperlightExecuteCodeTool` directly to the agent. The tool's
own description advertises `call_tool(...)`, the registered sandbox tools, and
the current capability configuration, so no extra CodeAct-specific agent
instructions are required.
"""

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
    table: Annotated[str, "Name of the simulated table to query."],
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


async def main() -> None:
    """Run the standalone execute_code sample."""
    # 1. Create the packaged execute_code tool and register sandbox tools on it.
    execute_code = HyperlightExecuteCodeTool(
        tools=[compute, fetch_data],
        approval_mode="never_require",
    )

    # 2. Create the client and the agent.
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=AzureCliCredential(),
        ),
        name="HyperlightExecuteCodeToolAgent",
        instructions="You are a helpful assistant.",
        tools=execute_code,
    )

    # 3. Run one request through the direct-tool surface.
    print("=" * 60)
    print("Hyperlight execute_code tool sample")
    print("=" * 60)
    query = (
        "Fetch all users, find admins, multiply 6*7, and print the users, admins, "
        "and multiplication result. Use one execute_code call."
    )
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result.text}")


"""
Sample output (shape only):

============================================================
Hyperlight execute_code tool sample
============================================================
User: Fetch all users, find admins, multiply 6*7, ...
Agent: ...
"""


if __name__ == "__main__":
    asyncio.run(main())
