# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
from pathlib import Path
from typing import Any

from agent_framework import ChatAgent
from agent_framework_azure_ai import AzureAIAgentClient
from azure.ai.agents.models import OpenApiAnonymousAuthDetails, OpenApiTool
from azure.identity.aio import AzureCliCredential

"""
The following sample demonstrates how to create a simple, Azure AI agent that
uses OpenAPI tools to answer user questions.
"""

# Simulate a conversation with the agent
USER_INPUTS = [
    "What is the name and population of the country that uses currency with abbreviation THB?",
    "What is the current weather in the capital city of that country?",
]


def load_openapi_specs() -> tuple[dict[str, Any], dict[str, Any]]:
    """Load OpenAPI specification files."""
    resources_path = Path(__file__).parent.parent / "resources"

    with open(resources_path / "weather.json") as weather_file:
        weather_spec = json.load(weather_file)

    with open(resources_path / "countries.json") as countries_file:
        countries_spec = json.load(countries_file)

    return weather_spec, countries_spec


async def main() -> None:
    """Main function demonstrating Azure AI agent with OpenAPI tools."""
    # 1. Load OpenAPI specifications (synchronous operation)
    weather_openapi_spec, countries_openapi_spec = load_openapi_specs()

    # 2. Use AzureAIAgentClient as async context manager for automatic cleanup
    async with AzureAIAgentClient(async_credential=AzureCliCredential()) as client:
        # 3. Create OpenAPI tools using Azure AI's OpenApiTool
        auth = OpenApiAnonymousAuthDetails()

        openapi_weather = OpenApiTool(
            name="get_weather",
            spec=weather_openapi_spec,
            description="Retrieve weather information for a location using wttr.in service",
            auth=auth,
        )

        openapi_countries = OpenApiTool(
            name="get_country_info",
            spec=countries_openapi_spec,
            description="Retrieve country information including population and capital city",
            auth=auth,
        )

        # 4. Create an agent with OpenAPI tools
        # Note: We need to pass the Azure AI native OpenApiTool definitions directly
        # since the agent framework doesn't have a HostedOpenApiTool wrapper yet
        async with ChatAgent(
            chat_client=client,
            name="OpenAPIAgent",
            instructions=(
                "You are a helpful assistant that can search for country information "
                "and weather data using APIs. When asked about countries, use the country "
                "API to find information. When asked about weather, use the weather API. "
                "Provide clear, informative answers based on the API results."
            ),
            # Pass the raw tool definitions from Azure AI's OpenApiTool
            tools=[*openapi_countries.definitions, *openapi_weather.definitions],
        ) as agent:
            # 5. Simulate conversation with the agent maintaining thread context
            print("=== Azure AI Agent with OpenAPI Tools ===\n")

            # Create a thread to maintain conversation context across multiple runs
            thread = agent.get_new_thread()

            for user_input in USER_INPUTS:
                print(f"User: {user_input}")
                # Pass the thread to maintain context across multiple agent.run() calls
                response = await agent.run(user_input, thread=thread)
                print(f"Agent: {response.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
