# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
from typing import Annotated, Any

from agent_framework import SequentialBuilder, tool
from agent_framework.openai import OpenAIChatClient
from pydantic import Field

"""
Sample: Workflow as Agent with kwargs Propagation to @tool Tools

This sample demonstrates how to flow custom context (skill data, user tokens, etc.)
through a workflow exposed via .as_agent() to @tool functions using the **kwargs pattern.

Key Concepts:
- Build a workflow using SequentialBuilder (or any builder pattern)
- Expose the workflow as a reusable agent via workflow.as_agent()
- Pass custom context as kwargs when invoking workflow_agent.run() or run_stream()
- kwargs are stored in SharedState and propagated to all agent invocations
- @tool functions receive kwargs via **kwargs parameter

When to use workflow.as_agent():
- To treat an entire workflow orchestration as a single agent
- To compose workflows into higher-level orchestrations
- To maintain a consistent agent interface for callers

Prerequisites:
- OpenAI environment variables configured
"""


# Define tools that accept custom context via **kwargs
# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_user_data(
    query: Annotated[str, Field(description="What user data to retrieve")],
    **kwargs: Any,
) -> str:
    """Retrieve user-specific data based on the authenticated context."""
    user_token = kwargs.get("user_token", {})
    user_name = user_token.get("user_name", "anonymous")
    access_level = user_token.get("access_level", "none")

    print(f"\n[get_user_data] Received kwargs keys: {list(kwargs.keys())}")
    print(f"[get_user_data] User: {user_name}")
    print(f"[get_user_data] Access level: {access_level}")

    return f"Retrieved data for user {user_name} with {access_level} access: {query}"


@tool(approval_mode="never_require")
def call_api(
    endpoint_name: Annotated[str, Field(description="Name of the API endpoint to call")],
    **kwargs: Any,
) -> str:
    """Call an API using the configured endpoints from custom_data."""
    custom_data = kwargs.get("custom_data", {})
    api_config = custom_data.get("api_config", {})

    base_url = api_config.get("base_url", "unknown")
    endpoints = api_config.get("endpoints", {})

    print(f"\n[call_api] Received kwargs keys: {list(kwargs.keys())}")
    print(f"[call_api] Base URL: {base_url}")
    print(f"[call_api] Available endpoints: {list(endpoints.keys())}")

    if endpoint_name in endpoints:
        return f"Called {base_url}{endpoints[endpoint_name]} successfully"
    return f"Endpoint '{endpoint_name}' not found in configuration"


async def main() -> None:
    print("=" * 70)
    print("Workflow as Agent kwargs Flow Demo")
    print("=" * 70)

    # Create chat client
    chat_client = OpenAIChatClient()

    # Create agent with tools that use kwargs
    agent = chat_client.as_agent(
        name="assistant",
        instructions=(
            "You are a helpful assistant. Use the available tools to help users. "
            "When asked about user data, use get_user_data. "
            "When asked to call an API, use call_api."
        ),
        tools=[get_user_data, call_api],
    )

    # Build a sequential workflow
    workflow = SequentialBuilder().participants([agent]).build()

    # Expose the workflow as an agent using .as_agent()
    workflow_agent = workflow.as_agent(name="WorkflowAgent")

    # Define custom context that will flow to tools via kwargs
    custom_data = {
        "api_config": {
            "base_url": "https://api.example.com",
            "endpoints": {
                "users": "/v1/users",
                "orders": "/v1/orders",
                "products": "/v1/products",
            },
        },
    }

    user_token = {
        "user_name": "bob@contoso.com",
        "access_level": "admin",
    }

    print("\nCustom Data being passed:")
    print(json.dumps(custom_data, indent=2))
    print(f"\nUser: {user_token['user_name']}")
    print("\n" + "-" * 70)
    print("Workflow Agent Execution (watch for [tool_name] logs showing kwargs received):")
    print("-" * 70)

    # Run workflow agent with kwargs - these will flow through to tools
    # Note: kwargs are passed to workflow_agent.run_stream() just like workflow.run_stream()
    print("\n===== Streaming Response =====")
    async for update in workflow_agent.run_stream(
        "Please get my user data and then call the users API endpoint.",
        custom_data=custom_data,
        user_token=user_token,
    ):
        if update.text:
            print(update.text, end="", flush=True)
    print()

    print("\n" + "=" * 70)
    print("Sample Complete")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
