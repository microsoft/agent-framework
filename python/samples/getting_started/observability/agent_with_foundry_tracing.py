# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import os
from random import randint
from typing import Annotated

import dotenv
from agent_framework import ChatAgent
from agent_framework import tool
from agent_framework.observability import create_resource, enable_instrumentation, get_tracer
from agent_framework.openai import OpenAIResponsesClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from pydantic import Field

"""
This sample shows you can can setup telemetry in Microsoft Foundry for a custom agent.
First ensure you have a Foundry workspace with Application Insights enabled.
And use the Operate tab to Register an Agent.
Set the OpenTelemetry agent ID to the value used below in the ChatAgent creation: `weather-agent` (or change both).
The sample uses the Azure Monitor OpenTelemetry exporter to send traces to Application Insights.
So ensure you have the `azure-monitor-opentelemetry` package installed.
"""

# For loading the `AZURE_AI_PROJECT_ENDPOINT` environment variable
dotenv.load_dotenv()

logger = logging.getLogger(__name__)

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
    ):
        # This will enable tracing and configure the application to send telemetry data to the
        # Application Insights instance attached to the Azure AI project.
        # This will override any existing configuration.
        try:
            conn_string = await project_client.telemetry.get_application_insights_connection_string()
        except Exception:
            logger.warning(
                "No Application Insights connection string found for the Azure AI Project. "
                "Please ensure Application Insights is configured in your Azure AI project, "
                "or call configure_otel_providers() manually with custom exporters."
            )
            return
        configure_azure_monitor(
            connection_string=conn_string,
            enable_live_metrics=True,
            resource=create_resource(),
            enable_performance_counters=False,
        )
        # This call is not necessary if you have the environment variable ENABLE_INSTRUMENTATION=true set
        # If not or set to false, or if you want to enable or disable sensitive data collection, call this function.
        enable_instrumentation(enable_sensitive_data=True)
        print("Observability is set up. Starting Weather Agent...")

        questions = ["What's the weather in Amsterdam?", "and in Paris, and which is better?", "Why is the sky blue?"]

        with get_tracer().start_as_current_span("Weather Agent Chat", kind=SpanKind.CLIENT) as current_span:
            print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

            agent = ChatAgent(
                chat_client=OpenAIResponsesClient(),
                tools=get_weather,
                name="WeatherAgent",
                instructions="You are a weather assistant.",
                id="weather-agent",
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
