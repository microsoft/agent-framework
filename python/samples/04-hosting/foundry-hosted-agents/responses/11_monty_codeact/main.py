# Copyright (c) Microsoft. All rights reserved.

import logging
import os
from typing import Annotated, Any, Literal

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework.observability import enable_instrumentation
from agent_framework_foundry_hosting import ResponsesHostServer
from agent_framework_monty import MontyCodeActProvider
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file (no-op when injected by Foundry).
load_dotenv()

logger = logging.getLogger(__name__)


def _setup_telemetry() -> None:
    """Wire Agent Framework spans to the Application Insights resource attached to the Foundry project.

    Foundry-hosted runtimes inject ``APPLICATIONINSIGHTS_CONNECTION_STRING`` automatically;
    locally you can set it yourself (see README). When the connection string is present we
    configure Azure Monitor OTel exporters once and then flip the framework's instrumentation
    flag so it emits ``invoke_agent`` / ``chat`` / ``execute_tool`` spans. The hosting layer's
    incoming-request span becomes the parent automatically via OpenTelemetry context
    propagation when both layers share the same global tracer provider.
    """
    connection_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not connection_string:
        logger.info(
            "APPLICATIONINSIGHTS_CONNECTION_STRING is not set; Agent Framework spans will not "
            "be exported to Azure Monitor. Set the env var to enable telemetry."
        )
        return

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ImportError:
        logger.warning(
            "azure-monitor-opentelemetry is not installed; skipping Azure Monitor setup. "
            "Install it to export telemetry."
        )
        return

    # Configure the global OTel providers (tracer/meter/logger) to export to Azure Monitor.
    # Idempotent for repeated imports because we only call it from this entry point.
    configure_azure_monitor(connection_string=connection_string)
    # Flip the Agent Framework instrumentation flag so its spans are actually emitted on
    # the now-configured global providers.
    enable_instrumentation()
    logger.info("Azure Monitor + Agent Framework instrumentation enabled.")


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
    # Set up telemetry BEFORE building the client/agent so the framework picks up
    # the configured tracer provider when it lazily wires instrumentation.
    _setup_telemetry()

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
