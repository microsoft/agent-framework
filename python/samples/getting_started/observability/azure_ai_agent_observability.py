# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

import dotenv
from agent_framework import ChatAgent
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
This sample shows you can can setup telemetry for an Azure AI agent.
It uses the Azure AI client to setup the telemetry, this calls out to
Azure AI for the connection string of the attached Application Insights
instance.

You must add an Application Insights instance to your Azure AI project
for this sample to work.
"""

# For loading the `AZURE_AI_PROJECT_ENDPOINT` environment variable
dotenv.load_dotenv()


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

    This will take the connection string from the AIProjectClient.
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


async def main():
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

        questions = ["What's the weather in Amsterdam?", "and in Paris, and which is better?", "Why is the sky blue?"]

        with get_tracer().start_as_current_span("Single Agent Chat", kind=SpanKind.CLIENT) as current_span:
            print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

            agent = ChatAgent(
                chat_client=client,
                tools=get_weather,
                name="WeatherAgent",
                instructions="You are a weather assistant.",
            )
            thread = agent.get_new_thread()
            for question in questions:
                print(f"User: {question}")
                print(f"{agent.display_name}: ", end="")
                async for update in agent.run_stream(
                    question,
                    thread=thread,
                ):
                    if update.text:
                        print(update.text, end="")


if __name__ == "__main__":
    asyncio.run(main())
