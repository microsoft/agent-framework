# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from agent_framework import Agent, FunctionInvocationContext, function_middleware, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

from agent_framework_hyperlight import HyperlightCodeActProvider

"""This sample demonstrates the provider-owned Hyperlight CodeAct flow.

The sample keeps `compute` and `fetch_data` off the direct agent tool surface and
registers them only with `HyperlightCodeActProvider`. The model therefore sees a
single `execute_code` tool and must call the provider-owned tools from inside
the sandbox with `call_tool(...)`.
"""

load_dotenv()

_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_DIM = "\033[2m"
_RESET = "\033[0m"


class _ColoredFormatter(logging.Formatter):
    """Dim logger output so it does not compete with sample prints."""

    def format(self, record: logging.LogRecord) -> str:
        return f"{_DIM}{super().format(record)}{_RESET}"


logging.basicConfig(level=logging.WARNING)
logging.getLogger().handlers[0].setFormatter(
    _ColoredFormatter("[%(asctime)s] %(levelname)s: %(message)s"),
)


@function_middleware
async def log_function_calls(
    context: FunctionInvocationContext,
    call_next: Callable[[], Awaitable[None]],
) -> None:
    """Log tool calls, including readable execute_code blocks."""
    import time

    function_name = context.function.name
    arguments = context.arguments if isinstance(context.arguments, dict) else {}

    if function_name == "execute_code" and "code" in arguments:
        print(f"\n{_YELLOW}{'─' * 60}")
        print("▶ execute_code")
        print(f"{'─' * 60}{_RESET}")
        print(arguments["code"])
        print(f"{_YELLOW}{'─' * 60}{_RESET}")
    else:
        pairs = ", ".join(f"{name}={value!r}" for name, value in arguments.items())
        print(f"\n{_YELLOW}▶ {function_name}({pairs}){_RESET}")

    start = time.perf_counter()
    await call_next()
    elapsed = time.perf_counter() - start

    result = context.result
    if function_name == "execute_code" and isinstance(result, list):
        for item in result:
            if item.type != "code_interpreter_tool_result":
                continue

            for output in item.outputs or []:
                if output.type == "text" and output.text:
                    print(f"{_GREEN}stdout:\n{output.text}{_RESET}")
                if output.type == "error" and output.error_details:
                    print(f"{_YELLOW}stderr:\n{output.error_details}{_RESET}")
    else:
        print(f"{_YELLOW}◀ {function_name} → {result!r}{_RESET}")

    print(f"{_DIM}  ({elapsed:.4f}s){_RESET}")


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


async def main() -> None:
    """Run the provider-owned Hyperlight CodeAct sample."""
    # 1. Create the Hyperlight-backed provider and register sandbox tools on it.
    codeact = HyperlightCodeActProvider(
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
        name="HyperlightCodeActProviderAgent",
        instructions="You are a helpful assistant.",
        context_providers=[codeact],
        middleware=[log_function_calls],
    )

    # 3. Run a request that should use execute_code plus provider-owned tools.
    query = (
        "Fetch all users, find admins, multiply 7*(3*2), and print the users, "
        "admins, and multiplication result. Use execute_code and call_tool(...) "
        "inside the sandbox."
    )
    print(f"{_CYAN}{'=' * 60}")
    print("Hyperlight CodeAct provider sample")
    print(f"{'=' * 60}{_RESET}")
    print(f"{_CYAN}User: {query}{_RESET}")
    result = await agent.run(query)
    print(f"{_CYAN}Agent: {result.text}{_RESET}")


"""
Sample output (shape only):

============================================================
Hyperlight CodeAct provider sample
============================================================
User: Fetch all users, find admins, multiply 7*(3*2), ...

────────────────────────────────────────────────────────────
▶ execute_code
────────────────────────────────────────────────────────────
users = call_tool("fetch_data", table="users")
admins = [user for user in users if user["role"] == "admin"]
result = call_tool("compute", operation="multiply", a=7, b=6)
print("Users:", users)
print("Admins:", admins)
print("7 * 6 =", result)
────────────────────────────────────────────────────────────
stdout:
Users: [...]
Admins: [...]
7 * 6 = 42.0
  (0.0xxx s)
Agent: ...
"""


if __name__ == "__main__":
    asyncio.run(main())
