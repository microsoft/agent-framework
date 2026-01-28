# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
from typing import Annotated, Any

from agent_framework import (
    ChatMessage,
    SequentialBuilder,
    WorkflowExecutor,
    WorkflowOutputEvent,
    tool,
)
from agent_framework.openai import OpenAIChatClient

"""
Sample: Sub-Workflow kwargs Propagation

This sample demonstrates how custom context (kwargs) flows from a parent workflow
through to agents in sub-workflows. When you pass kwargs to the parent workflow's
run_stream() or run(), they automatically propagate to nested sub-workflows.

Key Concepts:
- kwargs passed to parent workflow.run_stream() propagate to sub-workflows
- Sub-workflow agents receive the same kwargs as the parent workflow
- Works with nested WorkflowExecutor compositions at any depth
- Useful for passing authentication tokens, configuration, or request context

Prerequisites:
- OpenAI environment variables configured
"""


# Define tools that access custom context via **kwargs
# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_authenticated_data(
    resource: Annotated[str, "The resource to fetch"],
    **kwargs: Any,
) -> str:
    """Fetch data using the authenticated user context from kwargs."""
    user_token = kwargs.get("user_token", {})
    user_name = user_token.get("user_name", "anonymous")
    access_level = user_token.get("access_level", "none")

    print(f"\n[get_authenticated_data] kwargs keys: {list(kwargs.keys())}")
    print(f"[get_authenticated_data] User: {user_name}, Access: {access_level}")

    return f"Fetched '{resource}' for user {user_name} ({access_level} access)"


@tool(approval_mode="never_require")
def call_configured_service(
    service_name: Annotated[str, "Name of the service to call"],
    **kwargs: Any,
) -> str:
    """Call a service using configuration from kwargs."""
    config = kwargs.get("service_config", {})
    services = config.get("services", {})

    print(f"\n[call_configured_service] kwargs keys: {list(kwargs.keys())}")
    print(f"[call_configured_service] Available services: {list(services.keys())}")

    if service_name in services:
        endpoint = services[service_name]
        return f"Called service '{service_name}' at {endpoint}"
    return f"Service '{service_name}' not found in configuration"


async def main() -> None:
    print("=" * 70)
    print("Sub-Workflow kwargs Propagation Demo")
    print("=" * 70)

    # Create chat client
    chat_client = OpenAIChatClient()

    # Create an agent with tools that use kwargs
    inner_agent = chat_client.as_agent(
        name="data_agent",
        instructions=(
            "You are a data access agent. Use the available tools to help users. "
            "When asked to fetch data, use get_authenticated_data. "
            "When asked to call a service, use call_configured_service."
        ),
        tools=[get_authenticated_data, call_configured_service],
    )

    # Build the inner (sub) workflow with the agent
    inner_workflow = SequentialBuilder().participants([inner_agent]).build()

    # Wrap the inner workflow in a WorkflowExecutor to use it as a sub-workflow
    subworkflow_executor = WorkflowExecutor(
        workflow=inner_workflow,
        id="data_subworkflow",
    )

    # Build the outer (parent) workflow containing the sub-workflow
    outer_workflow = SequentialBuilder().participants([subworkflow_executor]).build()

    # Define custom context that will flow through to the sub-workflow's agent
    user_token = {
        "user_name": "alice@contoso.com",
        "access_level": "admin",
        "session_id": "sess_12345",
    }

    service_config = {
        "services": {
            "users": "https://api.example.com/v1/users",
            "orders": "https://api.example.com/v1/orders",
            "inventory": "https://api.example.com/v1/inventory",
        },
        "timeout": 30,
    }

    print("\nContext being passed to parent workflow:")
    print(f"  user_token: {json.dumps(user_token, indent=4)}")
    print(f"  service_config: {json.dumps(service_config, indent=4)}")
    print("\n" + "-" * 70)
    print("Workflow Execution (kwargs flow: parent -> sub-workflow -> agent -> tool):")
    print("-" * 70)

    # Run the OUTER workflow with kwargs
    # These kwargs will automatically propagate to the inner sub-workflow
    async for event in outer_workflow.run_stream(
        "Please fetch my profile data and then call the users service.",
        user_token=user_token,
        service_config=service_config,
    ):
        if isinstance(event, WorkflowOutputEvent):
            output_data = event.data
            if isinstance(output_data, list):
                for item in output_data:  # type: ignore
                    if isinstance(item, ChatMessage) and item.text:
                        print(f"\n[Final Answer]: {item.text}")

    print("\n" + "=" * 70)
    print("Sample Complete - kwargs successfully flowed through sub-workflow!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
