# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

import dotenv
from agent_framework import HostedCodeInterpreterTool
from agent_framework.azure import AzureAIAgentClient
from agent_framework.observability import get_tracer
from azure.ai.agents.aio import AgentsClient
from azure.ai.projects.aio import AIProjectClient
from azure.core.exceptions import ResourceNotFoundError
from azure.identity.aio import AzureCliCredential
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from pydantic import Field

"""
This sample, shows you can leverage the built-in telemetry in Azure AI.
It uses the Azure AI client to setup the telemetry, this calls out to
Azure AI for the connection string of the attached Application Insights
instance.

You must add an Application Insights instance to your Azure AI project
for this sample to work.
"""

# For loading the `AZURE_AI_PROJECT_ENDPOINT` environment variable
dotenv.load_dotenv()

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


async def setup_azure_ai_observability(
    project_client: AIProjectClient, enable_sensitive_data: bool | None = None
) -> None:
    """Use this method to setup tracing in your Azure AI Project.

    This will take the connection string from the AIProjectClient instance.
    It will override any connection string that is set in the environment variables.
    It will disable any OTLP endpoint that might have been set.
    """
    try:
        conn_string = await project_client.telemetry.get_application_insights_connection_string()
    except ResourceNotFoundError:
        print("No Application Insights connection string found for the Azure AI Project.")
        return
    from agent_framework.observability import setup_observability

    setup_observability(applicationinsights_connection_string=conn_string, enable_sensitive_data=enable_sensitive_data)


async def main() -> None:
    """Run an AI service.

    This function runs an AI service and prints the output.
    Telemetry will be collected for the service execution behind the scenes,
    and the traces will be sent to the configured telemetry backend.

    The telemetry will include information about the AI service execution.

    In azure_ai you will also see specific operations happening that are called by the Azure AI implementation,
    such as `create_agent`.
    """
    questions = [
        "What's the weather in Amsterdam and in Paris?",
        "Why is the sky blue?",
        "Tell me about AI.",
        "Can you write a python function that adds two numbers? and use it to add 8483 and 5692?",
    ]
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project_client,
        AgentsClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as agents_client,
        AzureAIAgentClient(agents_client=agents_client) as client,
    ):
        # This will enable tracing and configure the application to send telemetry data to the
        # Application Insights instance attached to the Azure AI project.
        # This will override any existing configuration.
        await setup_azure_ai_observability(project_client)

        with get_tracer().start_as_current_span(
            name="Foundry Telemetry from Agent Framework", kind=SpanKind.CLIENT
        ) as current_span:
            print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

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


if __name__ == "__main__":
    asyncio.run(main())
