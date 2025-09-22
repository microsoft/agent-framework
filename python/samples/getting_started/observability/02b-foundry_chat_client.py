# Copyright (c) Microsoft. All rights reserved.
# type: ignore
import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import HostedCodeInterpreterTool
from agent_framework.foundry import FoundryChatClient
from agent_framework.observability import get_tracer, setup_observability
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from pydantic import Field

"""
This sample, shows you can leverage the built-in telemetry in Foundry.
It uses the Foundry client to setup the telemetry, this calls
out to Foundry for a telemetry connection strings,
and then call the setup_observability function in the agent framework.
If you want to compare with the trace sent to a generic OTLP endpoint,
switch the `use_foundry_telemetry` variable to False.
"""


# ANSI color codes for printing in blue and resetting after each print
BLUE = "\x1b[34m"
RESET = "\x1b[0m"


async def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    await asyncio.sleep(randint(0, 10) / 10.0)  # Simulate a network call
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    """Run an AI service.

    This function runs an AI service and prints the output.
    Telemetry will be collected for the service execution behind the scenes,
    and the traces will be sent to the configured telemetry backend.

    The telemetry will include information about the AI service execution.

    In foundry you will also see specific operations happening that are called by the Foundry implementation,
    such as `create_agent`.
    """
    use_foundry_obs = True
    questions = [
        "What's the weather in Amsterdam and in Paris?",
        "Why is the sky blue?",
        "Tell me about AI.",
        "Can you write a python function that adds two numbers? and use it to add 8483 and 5692?",
    ]
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential) as project,
        FoundryChatClient(client=project, setup_tracing=False) as client,
    ):
        if use_foundry_obs:
            await client.setup_foundry_observability(enable_live_metrics=True)
        else:
            setup_observability()

        with get_tracer().start_as_current_span(
            name="Foundry Telemetry from Agent Framework", kind=SpanKind.CLIENT
        ) as span:
            for question in questions:
                print(f"{BLUE}User: {question}{RESET}")
                print(f"{BLUE}Assistant: {RESET}", end="")
                async for chunk in client.get_streaming_response(
                    question, tools=[get_weather, HostedCodeInterpreterTool()]
                ):
                    if str(chunk):
                        print(f"{BLUE}{str(chunk)}{RESET}", end="")
                print(f"{BLUE}{RESET}")

            print(f"{BLUE}Done{RESET}")
            print(f"{BLUE}Operation ID: {format_trace_id(span.get_span_context().trace_id)}{RESET}")


if __name__ == "__main__":
    asyncio.run(main())
