# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

import dotenv
from agent_framework import ChatAgent
from agent_framework import tool
from agent_framework.azure import AzureAIClient
from agent_framework.observability import get_tracer
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from pydantic import Field

"""
This sample shows you can can setup telemetry for an Azure AI agent.
It uses the Azure AI client to setup the telemetry, this calls out to
Azure AI for the connection string of the attached Application Insights
instance.

You must add an Application Insights instance to your Azure AI project
for this sample to work.
"""

# For loading the `AZURE_AI_PROJECT_ENDPOINT` environment variable
dotenv.load_dotenv()

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
async def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    await asyncio.sleep(randint(0, 10) / 10.0)  # Simulate a network call
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main():
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project_client,
        AzureAIClient(project_client=project_client) as client,
    ):
        # This will enable tracing and configure the application to send telemetry data to the
        # Application Insights instance attached to the Azure AI project.
        # This will override any existing configuration.
        await client.configure_azure_monitor(enable_live_metrics=True)

        questions = ["What's the weather in Amsterdam?", "and in Paris, and which is better?", "Why is the sky blue?"]

        with get_tracer().start_as_current_span("Single Agent Chat", kind=SpanKind.CLIENT) as current_span:
            print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

            agent = ChatAgent(
                chat_client=client,
                tools=get_weather,
                name="WeatherAgent",
                instructions="You are a weather assistant.",
                id="edvan-weather-agent",
            )
            thread = agent.get_new_thread()
            for question in questions:
                print(f"\nUser: {question}")
                print(f"{agent.name}: ", end="")
                async for update in agent.run_stream(
                    question,
                    thread=thread,
                ):
                    if update.text:
                        print(update.text, end="")


if __name__ == "__main__":
    asyncio.run(main())
