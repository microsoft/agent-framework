# Copyright (c) Microsoft. All rights reserved.

import os
from typing import Annotated, Any, Literal

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from agent_framework_monty import MontyCodeActProvider
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file (no-op when injected by Foundry).
load_dotenv()


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


def main() -> None:
    """Host a Monty CodeAct agent over the Responses protocol."""
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    # MontyCodeActProvider injects a sandboxed `execute_code` tool into every
    # agent run, plus dynamic instructions describing the registered host tools.
    # The host tools are hidden from the model - they can only be invoked from
    # inside the sandbox (`await compute(...)` or `call_tool(...)`).
    codeact = MontyCodeActProvider(
        tools=[compute, fetch_data],
        approval_mode="never_require",
    )

    agent = Agent(
        client=client,
        instructions=(
            "You are a friendly assistant. Use `execute_code` to combine "
            "Python control flow with the provided host tools whenever the "
            "task requires lookups, transformations, or computation."
        ),
        context_providers=[codeact],
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
