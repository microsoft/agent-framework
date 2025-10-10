# Copyright (c) Microsoft. All rights reserved.

"""Example of using Agent Framework DevUI with in-memory entity registration.

This demonstrates the simplest way to serve agents and workflows as OpenAI-compatible API endpoints.
Includes both agents and a basic workflow to showcase different entity types.
"""

import logging
import os
from typing import Annotated

from agent_framework import ChatAgent, Executor, WorkflowBuilder, WorkflowContext, handler
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.devui import serve
from typing_extensions import Never


# Tool functions for the agent
def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    temperature = 53
    return f"The weather in {location} is {conditions[0]} with a high of {temperature}°C."


def get_time(
    timezone: Annotated[str, "The timezone to get time for."] = "UTC",
) -> str:
    """Get current time for a timezone."""
    from datetime import datetime

    # Simplified for example
    return f"Current time in {timezone}: {datetime.now().strftime('%H:%M:%S')}"


# Basic workflow executors
class UpperCase(Executor):
    """Convert text to uppercase."""

    @handler
    async def to_upper(self, text: str, ctx: WorkflowContext[str]) -> None:
        """Convert input to uppercase and forward to next executor."""
        result = text.upper()
        await ctx.send_message(result)


class AddExclamation(Executor):
    """Add exclamation mark to text."""

    @handler
    async def add_exclamation(self, text: str, ctx: WorkflowContext[Never, str]) -> None:
        """Add exclamation and yield as workflow output."""
        result = f"{text}!"
        await ctx.yield_output(result)


def main():
    """Main function demonstrating in-memory entity registration."""
    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)

    # Create Azure OpenAI chat client
    chat_client = AzureOpenAIChatClient(
        api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        model_id=os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "gpt-4o"),
    )

    # Create agents
    weather_agent = ChatAgent(
        name="weather-assistant",
        description="Provides weather information and time",
        instructions=(
            "You are a helpful weather and time assistant. Use the available tools to "
            "provide accurate weather information and current time for any location."
        ),
        chat_client=chat_client,
        tools=[get_weather, get_time],
    )

    simple_agent = ChatAgent(
        name="general-assistant",
        description="A simple conversational agent",
        instructions="You are a helpful assistant.",
        chat_client=chat_client,
    )

    # Create a basic workflow: Input -> UpperCase -> AddExclamation -> Output
    upper_executor = UpperCase(id="upper_case")
    exclaim_executor = AddExclamation(id="add_exclamation")

    basic_workflow = (
        WorkflowBuilder(
            name="Text Transformer",
            description="Simple 2-step workflow that converts text to uppercase and adds exclamation",
        )
        .set_start_executor(upper_executor)
        .add_edge(upper_executor, exclaim_executor)
        .build()
    )

    # Collect entities for serving
    entities = [weather_agent, simple_agent, basic_workflow]

    logger.info("Starting DevUI on http://localhost:8090")
    logger.info("Entities available:")
    logger.info("  - Agents: weather-assistant, general-assistant")
    logger.info("  - Workflow: basic text transformer (uppercase + exclamation)")

    # Launch server with auto-generated entity IDs
    serve(entities=entities, port=8090, auto_open=True)


if __name__ == "__main__":
    main()
