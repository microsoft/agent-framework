# Copyright (c) Microsoft. All rights reserved.

"""
GitHub Copilot Agent with OpenTelemetry Observability

This sample demonstrates how to enable OpenTelemetry tracing for GitHubCopilotAgent.
Traces are exported via OTLP (configure via environment variables) and/or to the
console for local development.

Environment variables (OTel):
- OTEL_EXPORTER_OTLP_ENDPOINT - OTLP endpoint (e.g., "http://localhost:4317")
- OTEL_SERVICE_NAME            - Service name shown in traces
- OTEL_EXPORTER_OTLP_PROTOCOL - "grpc" or "http/protobuf"

Environment variables (agent):
- GITHUB_COPILOT_CLI_PATH  - Path to the Copilot CLI executable
- GITHUB_COPILOT_MODEL     - Model to use (e.g., "gpt-5", "claude-sonnet-4")
- GITHUB_COPILOT_TIMEOUT   - Request timeout in seconds
- GITHUB_COPILOT_LOG_LEVEL - CLI log level
"""

import asyncio
from random import randint
from typing import Annotated

from agent_framework import tool
from agent_framework.github import GitHubCopilotAgent
from agent_framework.observability import configure_otel_providers
from copilot.generated.session_events import PermissionRequest
from copilot.session import PermissionRequestResult
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()


def prompt_permission(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
    """Permission handler that prompts the user for approval."""
    print(f"\n[Permission Request: {request.kind}]")

    if request.full_command_text is not None:
        print(f"  Command: {request.full_command_text}")

    response = input("Approve? (y/n): ").strip().lower()
    if response in ("y", "yes"):
        return PermissionRequestResult(kind="approved")
    return PermissionRequestResult(kind="denied-interactively-by-user")


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}C."


async def non_streaming_with_telemetry() -> None:
    """Non-streaming example with OTel tracing."""
    print("=== Non-streaming with Telemetry ===")

    agent = GitHubCopilotAgent(
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
        default_options={"on_permission_request": prompt_permission},
    )

    async with agent:
        query = "What's the weather like in Seattle and Tokyo?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


async def streaming_with_telemetry() -> None:
    """Streaming example with OTel tracing."""
    print("=== Streaming with Telemetry ===")

    agent = GitHubCopilotAgent(
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
        default_options={"on_permission_request": prompt_permission},
    )

    async with agent:
        query = "What's the weather like in Paris?"
        print(f"User: {query}")
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run(query, stream=True):
            if chunk.text:
                print(chunk.text, end="", flush=True)
        print("\n")


async def main() -> None:
    # Configure OTel providers before creating any agents.
    # - enable_console_exporters=True writes spans to stdout for local development.
    # - Set OTEL_EXPORTER_OTLP_ENDPOINT to send traces to a collector instead.
    configure_otel_providers(enable_console_exporters=True)

    print("=== GitHub Copilot Agent with OpenTelemetry ===\n")
    await non_streaming_with_telemetry()
    await streaming_with_telemetry()


if __name__ == "__main__":
    asyncio.run(main())
