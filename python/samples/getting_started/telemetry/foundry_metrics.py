# Copyright (c) Microsoft. All rights reserved.
# type: ignore
import asyncio
import logging
import os
from random import randint
from typing import Annotated

from agent_framework import __version__
from agent_framework_foundry import FoundryChatClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.attributes import service_attributes
from opentelemetry.trace import SpanKind
from pydantic import Field

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

    Args:
        chat_client: The chat client to use for the AI service.

    Remarks:
        When function calling is outside the open telemetry loop
        each of the call to the model is handled as a seperate span,
        while when the open telemetry is put last, a single span
        is shown, which might include one or more rounds of function calling.

        So for the scenario below, with one function call result, and then a second `get_response` with those results,
        giving back a final result, you get the following:
        function_calling_outside == True:
            1 Client span, with 4 children:
                2 Internal span with gen_ai.operation.name=chat
                    The first has finish_reason "tool_calls"
                    The second has finish_reason "stop"
                2 Internal span with gen_ai.operation.name=execute_tool
            In this case there is one chat span, followed by two simultanous (and almost instant) execute_tool spans,
            followed by another chat span
        function_calling_outside == False:
            1 Client span, with 1 child:
                1 Internal span with gen_ai.operation.name=chat, with 2 children:
                    2 Internal spans with gen_ai.operation.name=execute_tool
                    and the finish_reason is "stop"
            In this case the Client span and the child are almost the same length.
        The total time for the client span is pretty much the same for both methods.
    """
    questions = ["What's the weather in Amsterdam and in Paris?", "Why is the sky blue?"]
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential) as client,
    ):
        connection_string = await client.telemetry.get_application_insights_connection_string()
        resource = Resource.create({service_attributes.SERVICE_NAME: "FoundryTelemetry"})
        configure_azure_monitor(
            connection_string=connection_string,
            logger_name="agent_framework",
            resource=resource,
        )
        logger = logging.getLogger()
        # Set the logging level to NOTSET to allow all records to be processed by the handler.
        logger.setLevel(logging.NOTSET)
        chat_client = (
            FoundryChatClient(client=client).with_function_calling().with_open_telemetry(enable_sensitive_data=True)
        )
        tracer = trace.get_tracer("agent_framework", __version__)
        with tracer.start_as_current_span(name="Foundry Telemetry from Agent Framework", kind=SpanKind.CLIENT):
            for question in questions:
                print(f"{BLUE}User: {question}{RESET}")
                print(f"{BLUE}Assistant: {RESET}", end="")
                async for chunk in chat_client.get_streaming_response(question, tools=get_weather):
                    if str(chunk):
                        print(f"{BLUE}{str(chunk)}{RESET}", end="")
                print(f"{BLUE}{RESET}")


if __name__ == "__main__":
    asyncio.run(main())
