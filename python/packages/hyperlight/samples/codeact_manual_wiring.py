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

"""This sample demonstrates manual static wiring of CodeAct without a provider.

Instead of using `HyperlightCodeActProvider` with `context_providers=`, this
sample creates a `HyperlightExecuteCodeTool` directly, extracts its CodeAct
instructions once, and passes both to the `Agent` constructor at build time.

This avoids the per-run provider lifecycle (`before_run` / `after_run`) and is
well-suited when the tool registry, file mounts, and network allow-list are
fixed for the agent's lifetime. The tradeoff is that dynamic tool or capability
changes between runs are not supported — any mutations to the tool would not
update the agent's instructions automatically.
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


@tool(approval_mode="never_require")
def send_email(
    to: Annotated[str, "Recipient email address."],
    subject: Annotated[str, "Email subject line."],
    body: Annotated[str, "Email body text."],
) -> str:
    """Simulate sending an email (direct-only tool, not available inside the sandbox)."""
    return f"Email sent to {to}: {subject}"


async def main() -> None:
    """Run the manual static-wiring sample."""
    # 1. Create the execute_code tool and register sandbox tools on it.
    execute_code = HyperlightExecuteCodeTool(
        tools=[compute, fetch_data],
        approval_mode="never_require",
    )

    # 2. Build CodeAct instructions once. Setting tools_visible_to_model=False
    #    tells the instructions builder that sandbox tools are not in the agent's
    #    direct tool list, so the model must use call_tool(...) inside execute_code.
    codeact_instructions = execute_code.build_instructions(tools_visible_to_model=False)

    # 3. Create the client and the agent with everything wired at construction time.
    #    - send_email is a direct-only tool (not available inside the sandbox).
    #    - execute_code carries sandbox tools (compute, fetch_data) via call_tool.
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=AzureCliCredential(),
        ),
        name="ManualWiringAgent",
        instructions=f"You are a helpful assistant.\n\n{codeact_instructions}",
        tools=[send_email, execute_code],
    )

    # 4. Run a request that exercises both the sandbox and the direct tool.
    print("=" * 60)
    print("Manual static-wiring CodeAct sample")
    print("=" * 60)
    query = (
        "Fetch all users, find admins, multiply 6*7, and print the users, admins, "
        "and multiplication result. Use one execute_code call. "
        "Then send an email to admin@example.com summarising the results."
    )
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result.text}")


"""
Sample output (shape only):

============================================================
Manual static-wiring CodeAct sample
============================================================
User: Fetch all users, find admins, multiply 6*7, ...
Agent: ...
"""


if __name__ == "__main__":
    asyncio.run(main())
